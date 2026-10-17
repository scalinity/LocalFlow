use fs2::FileExt;
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
};
type Result<T> = std::result::Result<T, String>;
fn err(_: impl std::fmt::Display) -> String {
    "The session file could not be accessed safely.".into()
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Candidate {
    pub text: String,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pair {
    pub pair_id: String,
    pub case_id: String,
    pub source: String,
    pub a: Candidate,
    pub b: Candidate,
    pub vocabulary: Vec<(String, String)>,
}
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Choice {
    A,
    B,
    Tie,
    BothWrong,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Annotation {
    pub pair_id: String,
    pub choice: Option<Choice>,
    pub note: String,
    pub seconds: f64,
    pub annotated_at: String,
}
#[derive(Default, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Session {
    queue: Vec<String>,
    drafts: BTreeMap<String, String>,
    dataset: String,
}
#[derive(Serialize)]
pub struct Progress {
    pub total: usize,
    pub completed: usize,
    pub counts: BTreeMap<String, usize>,
    pub median_seconds: Option<f64>,
    /// Each judged pair's seconds, oldest judgment first, for the time-left estimate.
    pub timings: Vec<(String, f64)>,
}
#[derive(Serialize)]
pub struct Snapshot {
    pairs: Vec<Pair>,
    queue: Vec<String>,
    drafts: BTreeMap<String, String>,
    progress: Progress,
    can_undo: bool,
}
pub struct Store {
    pairs: Vec<Pair>,
    records: Vec<Annotation>,
    session: Session,
    file: File,
    annotations: PathBuf,
    state_path: PathBuf,
    valid_len: u64,
    poisoned: bool,
}
fn allowed(path: &Path, filename: &str) -> Result<()> {
    if path.file_name().and_then(|x| x.to_str()) != Some(filename) {
        return Err("Use the documented session filenames.".into());
    }
    match fs::symlink_metadata(path) {
        Ok(meta) if !meta.is_file() || meta.file_type().is_symlink() => {
            return Err("Session files must be regular files, not links.".into())
        }
        Err(e) if e.kind() != std::io::ErrorKind::NotFound => return Err(err(e)),
        _ => (),
    }
    Ok(())
}
fn replay(bytes: &[u8]) -> Result<(Vec<Annotation>, u64)> {
    let end = bytes
        .iter()
        .rposition(|b| *b == b'\n')
        .map(|i| i + 1)
        .unwrap_or(0);
    let mut records = Vec::new();
    for line in bytes[..end]
        .split(|b| *b == b'\n')
        .filter(|line| !line.is_empty())
    {
        let record: Annotation = serde_json::from_slice(line).map_err(|_| {
            "A completed annotation line is invalid. Restore it before continuing.".to_string()
        })?;
        if !record.seconds.is_finite()
            || record.seconds < 0.0
            || chrono::DateTime::parse_from_rfc3339(&record.annotated_at).is_err()
        {
            return Err("An annotation contains invalid timing.".into());
        }
        records.push(record);
    }
    Ok((records, end as u64))
}
fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = path.with_extension("pending");
    if fs::symlink_metadata(&tmp).is_ok_and(|m| m.file_type().is_symlink())
        || fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink())
    {
        return Err("A state file is a link.".into());
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(&tmp)
        .map_err(err)?;
    file.write_all(bytes).map_err(err)?;
    file.flush().map_err(err)?;
    file.sync_all().map_err(err)?;
    fs::rename(&tmp, path).map_err(err)?;
    File::open(path.parent().ok_or("Missing output folder.")?)
        .map_err(err)?
        .sync_all()
        .map_err(err)
}
impl Store {
    pub fn open(pairs_path: PathBuf, annotations: PathBuf, state_path: PathBuf) -> Result<Self> {
        allowed(&pairs_path, "pairs.jsonl")?;
        allowed(&annotations, "annotations.jsonl")?;
        let input = fs::read_to_string(&pairs_path).map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                "PAIRS_MISSING".to_string()
            } else {
                "The configured pairs file is unavailable.".to_string()
            }
        })?;
        let pairs: Vec<Pair> = input
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(|l| {
                serde_json::from_str(l)
                    .map_err(|_| "The pairs file does not match the blinded format.".to_string())
            })
            .collect::<Result<_>>()?;
        let mut ids = HashSet::new();
        if pairs.is_empty()
            || pairs
                .iter()
                .any(|p| p.pair_id.is_empty() || !ids.insert(p.pair_id.clone()))
        {
            return Err("Pairs must have unique, nonempty IDs.".into());
        }
        let mut file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&annotations)
            .map_err(err)?;
        file.try_lock_exclusive()
            .map_err(|_| "This annotation file is already open in another session.".to_string())?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes).map_err(err)?;
        let (records, valid_len) = replay(&bytes)?;
        if records.iter().any(|r| !ids.contains(&r.pair_id)) {
            return Err("The annotations do not belong to these pairs.".into());
        }
        let state_parent = state_path.parent().ok_or("Missing session state folder.")?;
        fs::create_dir_all(state_parent).map_err(err)?;
        // State is deliberately outside the annotation directory; no neighboring data is read.
        if fs::canonicalize(state_parent).map_err(err)?
            == fs::canonicalize(annotations.parent().ok_or("Missing annotation folder.")?)
                .map_err(err)?
        {
            return Err("Session state must be outside the annotation folder.".into());
        }
        let dataset = format!(
            "{}\n{}\n{}",
            fs::canonicalize(&pairs_path).map_err(err)?.display(),
            fs::canonicalize(&annotations).map_err(err)?.display(),
            input
        );
        if fs::symlink_metadata(&state_path)
            .is_ok_and(|m| !m.is_file() || m.file_type().is_symlink())
        {
            return Err("Session state must be a regular file, not a link.".into());
        }
        let mut session = match fs::read(&state_path) {
            Ok(bytes) => serde_json::from_slice::<Session>(&bytes)
                .map_err(|_| "The saved session state is invalid.".to_string())?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Session::default(),
            Err(e) => return Err(err(e)),
        };
        if session.dataset != dataset {
            session = Session {
                dataset,
                ..Session::default()
            };
        }
        let mut store = Self {
            pairs,
            records,
            session,
            file,
            annotations,
            state_path,
            valid_len,
            poisoned: false,
        };
        store.reconcile();
        store.save_state()?;
        Ok(store)
    }
    fn latest(&self) -> BTreeMap<String, &Annotation> {
        let mut map = BTreeMap::new();
        for record in &self.records {
            map.insert(record.pair_id.clone(), record);
        }
        map
    }
    fn reconcile(&mut self) {
        let active: HashSet<_> = self
            .latest()
            .into_iter()
            .filter(|(_, r)| r.choice.is_some())
            .map(|(id, _)| id)
            .collect();
        let ids: HashSet<_> = self.pairs.iter().map(|p| p.pair_id.clone()).collect();
        let mut seen = HashSet::new();
        self.session
            .queue
            .retain(|id| ids.contains(id) && !active.contains(id) && seen.insert(id.clone()));
        // A crash between a durable undo and the state save must restore the undone pair first.
        for record in self.records.iter().rev() {
            if record.choice.is_none()
                && !active.contains(&record.pair_id)
                && seen.insert(record.pair_id.clone())
            {
                self.session.queue.insert(0, record.pair_id.clone());
                self.session
                    .drafts
                    .insert(record.pair_id.clone(), record.note.clone());
            }
        }
        for pair in &self.pairs {
            if !active.contains(&pair.pair_id) && seen.insert(pair.pair_id.clone()) {
                self.session.queue.push(pair.pair_id.clone());
            }
        }
        self.session
            .drafts
            .retain(|id, _| ids.contains(id) && !active.contains(id));
    }
    fn save_state(&self) -> Result<()> {
        atomic_write(
            &self.state_path,
            &serde_json::to_vec(&self.session).map_err(err)?,
        )
    }
    pub fn progress(&self) -> Progress {
        let latest = self.latest();
        // A pair's last record decides; walking the log keeps those records in the order they were made.
        let timings = self
            .records
            .iter()
            .filter(|r| {
                r.choice.is_some() && latest.get(&r.pair_id).is_some_and(|l| std::ptr::eq(*l, *r))
            })
            .map(|r| (r.pair_id.clone(), r.seconds))
            .collect();
        let active: Vec<_> = latest
            .into_values()
            .filter(|r| r.choice.is_some())
            .collect();
        let mut counts: BTreeMap<String, usize> = ["a", "b", "tie", "both_wrong"]
            .into_iter()
            .map(|k| (k.into(), 0))
            .collect();
        let mut times: Vec<_> = active
            .iter()
            .map(|r| {
                let key = match r.choice.unwrap() {
                    Choice::A => "a",
                    Choice::B => "b",
                    Choice::Tie => "tie",
                    Choice::BothWrong => "both_wrong",
                };
                *counts.get_mut(key).unwrap() += 1;
                r.seconds
            })
            .collect();
        times.sort_by(|a, b| a.total_cmp(b));
        let n = times.len();
        Progress {
            total: self.pairs.len(),
            completed: n,
            counts,
            median_seconds: if n == 0 {
                None
            } else {
                Some((times[(n - 1) / 2] + times[n / 2]) / 2.0)
            },
            timings,
        }
    }
    pub fn snapshot(&self) -> Snapshot {
        Snapshot {
            pairs: self.pairs.clone(),
            queue: self.session.queue.clone(),
            drafts: self.session.drafts.clone(),
            can_undo: self.last_active().is_some(),
            progress: self.progress(),
        }
    }
    fn last_active(&self) -> Option<Annotation> {
        let mut seen = HashSet::new();
        self.records
            .iter()
            .rev()
            .find(|r| seen.insert(r.pair_id.clone()) && r.choice.is_some())
            .cloned()
    }
    fn append(&mut self, record: Annotation) -> Result<()> {
        if self.poisoned {
            return Err("Restart the session to check the last write.".into());
        }
        let mut bytes = serde_json::to_vec(&record).map_err(err)?;
        bytes.push(b'\n');
        let result = (|| -> Result<()> {
            // Only an unterminated crash fragment is discarded. No complete line is rewritten.
            self.file.set_len(self.valid_len).map_err(err)?;
            self.file.seek(SeekFrom::End(0)).map_err(err)?;
            self.file.write_all(&bytes).map_err(err)?;
            self.file.flush().map_err(err)?;
            self.file.sync_all().map_err(err)?;
            File::open(self.annotations.parent().unwrap())
                .map_err(err)?
                .sync_all()
                .map_err(err)?;
            Ok(())
        })();
        if result.is_err() {
            self.poisoned = true;
            return result;
        }
        self.valid_len += bytes.len() as u64;
        self.records.push(record);
        Ok(())
    }
    fn check_current(&self, id: &str) -> Result<()> {
        if self.poisoned {
            return Err("Restart the session to check the last write.".into());
        }
        if self.session.queue.first().map(String::as_str) != Some(id) {
            return Err("The current pair has changed.".into());
        }
        Ok(())
    }
    pub fn judge(
        &mut self,
        id: String,
        choice: Choice,
        note: String,
        seconds: f64,
    ) -> Result<Snapshot> {
        self.check_current(&id)?;
        if !seconds.is_finite() || seconds < 0.0 || note.chars().count() > 2000 {
            return Err("The judgment has invalid values.".into());
        }
        self.append(Annotation {
            pair_id: id.clone(),
            choice: Some(choice),
            note,
            seconds,
            annotated_at: chrono::Utc::now().to_rfc3339(),
        })?;
        self.session.queue.remove(0);
        self.session.drafts.remove(&id);
        if let Err(e) = self.save_state() {
            self.poisoned = true;
            return Err(e);
        }
        Ok(self.snapshot())
    }
    pub fn undo(&mut self) -> Result<Snapshot> {
        if let Some(record) = self.last_active() {
            self.append(Annotation {
                choice: None,
                seconds: 0.0,
                annotated_at: chrono::Utc::now().to_rfc3339(),
                ..record.clone()
            })?;
            self.session.queue.retain(|id| id != &record.pair_id);
            self.session.queue.insert(0, record.pair_id.clone());
            self.session.drafts.insert(record.pair_id, record.note);
            if let Err(e) = self.save_state() {
                self.poisoned = true;
                return Err(e);
            }
        }
        Ok(self.snapshot())
    }
    pub fn skip(&mut self, id: String) -> Result<Snapshot> {
        self.check_current(&id)?;
        let previous = self.session.clone();
        self.session.queue.rotate_left(1);
        if let Err(e) = self.save_state() {
            self.session = previous;
            return Err(e);
        }
        Ok(self.snapshot())
    }
    pub fn draft(&mut self, id: String, note: String) -> Result<()> {
        self.check_current(&id)?;
        if note.chars().count() > 2000 {
            return Err("The note is too long.".into());
        }
        self.session.drafts.insert(id, note);
        self.save_state()
    }
    pub fn export(&self) -> Result<()> {
        if self.poisoned {
            return Err("Restart before exporting.".into());
        }
        atomic_write(
            &self.annotations.with_file_name("summary.json"),
            &serde_json::to_vec_pretty(&self.progress()).map_err(err)?,
        )
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (tempfile::TempDir, PathBuf, PathBuf, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let data = dir.path().join("data");
        fs::create_dir(&data).unwrap();
        let pairs = data.join("pairs.jsonl");
        let annotations = data.join("annotations.jsonl");
        let state = dir.path().join("state/session.json");
        let input=(0..3).map(|i|serde_json::json!({"pair_id":format!("p{i}"),"case_id":format!("c{i}"),"source":"a source","a":{"text":"A source."},"b":{"text":"Source."},"vocabulary":[]}).to_string()).collect::<Vec<_>>().join("\n");
        fs::write(&pairs, input).unwrap();
        (dir, pairs, annotations, state)
    }
    #[test]
    fn durable_append_reload_undo_and_last_wins() {
        let (_dir, p, a, s) = fixture();
        {
            let mut store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
            store
                .judge("p0".into(), Choice::A, "note".into(), 3.0)
                .unwrap();
            store.undo().unwrap();
            store
                .judge("p0".into(), Choice::B, "new".into(), 5.0)
                .unwrap();
        }
        let store = Store::open(p, a.clone(), s).unwrap();
        assert_eq!(store.progress().completed, 1);
        assert_eq!(store.progress().counts["b"], 1);
        assert_eq!(store.progress().median_seconds, Some(5.0));
        assert_eq!(store.session.queue[0], "p1");
        assert_eq!(fs::read_to_string(a).unwrap().lines().count(), 3);
    }
    #[test]
    fn timings_follow_judgment_order_and_drop_undone_pairs() {
        let (_dir, p, a, s) = fixture();
        let mut store = Store::open(p, a, s).unwrap();
        store.judge("p0".into(), Choice::A, "".into(), 3.0).unwrap();
        store.judge("p1".into(), Choice::B, "".into(), 7.0).unwrap();
        store.undo().unwrap();
        store.judge("p1".into(), Choice::Tie, "".into(), 4.0).unwrap();
        store.judge("p2".into(), Choice::A, "".into(), 2.0).unwrap();
        let ids = |s: &Store| s.progress().timings.into_iter().map(|(id, t)| format!("{id}:{t}")).collect::<Vec<_>>();
        assert_eq!(ids(&store), ["p0:3", "p1:4", "p2:2"]);
        store.undo().unwrap();
        assert_eq!(ids(&store), ["p0:3", "p1:4"]);
    }
    #[test]
    fn truncated_last_line_is_ignored_and_next_append_recovers() {
        let (_dir, p, a, s) = fixture();
        {
            let mut store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
            store
                .judge("p0".into(), Choice::Tie, "".into(), 2.0)
                .unwrap();
        }
        let original = fs::read(&a).unwrap();
        OpenOptions::new()
            .append(true)
            .open(&a)
            .unwrap()
            .write_all(b"{\"pair_id\":\"p1\",\"note\":\"\xf0\x9f")
            .unwrap();
        {
            let mut store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
            assert_eq!(store.progress().completed, 1);
            store
                .judge("p1".into(), Choice::BothWrong, "".into(), 4.0)
                .unwrap();
        }
        let store = Store::open(p, a.clone(), s).unwrap();
        assert_eq!(store.progress().completed, 2);
        assert_eq!(store.progress().median_seconds, Some(3.0));
        assert!(fs::read(a).unwrap().starts_with(&original));
    }
    #[test]
    fn missing_pairs_wait_without_creating_output_or_state() {
        let (_d, p, a, s) = fixture();
        fs::remove_file(&p).unwrap();
        let error = Store::open(p, a.clone(), s.clone()).err().unwrap();
        assert_eq!(error, "PAIRS_MISSING");
        assert!(!a.exists());
        assert!(!s.exists());
    }
    #[test]
    fn unreadable_pairs_are_not_reported_as_missing() {
        let (_d, p, a, s) = fixture();
        fs::write(&p, [0xff, 0xfe]).unwrap();
        let error = Store::open(p, a.clone(), s).err().unwrap();
        assert_eq!(error, "The configured pairs file is unavailable.");
        assert!(!a.exists());
    }
    #[test]
    fn malformed_completed_line_is_rejected() {
        let (_d, p, a, s) = fixture();
        fs::write(&a, b"broken\n").unwrap();
        assert!(Store::open(p, a, s).is_err());
    }
    #[test]
    fn skip_and_draft_resume_exactly() {
        let (_d, p, a, s) = fixture();
        {
            let mut store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
            store.draft("p0".into(), "keep this".into()).unwrap();
            store.skip("p0".into()).unwrap();
            store.judge("p1".into(), Choice::A, "".into(), 1.0).unwrap();
        }
        let store = Store::open(p, a, s).unwrap();
        assert_eq!(store.session.queue, vec!["p2", "p0"]);
        assert_eq!(store.session.drafts["p0"], "keep this");
    }
    #[test]
    fn exclusive_writer_and_bounded_paths() {
        let (_d, p, a, s) = fixture();
        let _store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
        assert!(Store::open(p.clone(), a.clone(), s.clone()).is_err());
        assert!(allowed(&p.with_file_name("pairs-key.json"), "pairs.jsonl").is_err());
        #[cfg(unix)]
        {
            let other = p.with_file_name("link");
            fs::create_dir(&other).unwrap();
            std::os::unix::fs::symlink(&p, other.join("pairs.jsonl")).unwrap();
            assert!(allowed(&other.join("pairs.jsonl"), "pairs.jsonl").is_err());
        }
    }
    #[test]
    fn undo_crash_before_state_write_reconciles() {
        let (_d, p, a, s) = fixture();
        {
            let mut store = Store::open(p.clone(), a.clone(), s.clone()).unwrap();
            store
                .judge("p0".into(), Choice::A, "restore".into(), 1.0)
                .unwrap();
            store
                .append(Annotation {
                    pair_id: "p0".into(),
                    choice: None,
                    note: "restore".into(),
                    seconds: 0.0,
                    annotated_at: chrono::Utc::now().to_rfc3339(),
                })
                .unwrap();
        }
        let store = Store::open(p, a, s).unwrap();
        assert_eq!(store.session.queue[0], "p0");
        assert_eq!(store.session.drafts["p0"], "restore");
    }
    #[test]
    fn failed_write_does_not_advance_or_accept_more_judgments() {
        let (_d, p, a, s) = fixture();
        let mut store = Store::open(p, a.clone(), s).unwrap();
        store.file = File::open(&a).unwrap(); // A read-only handle forces an actual storage error.
        assert!(store.judge("p0".into(), Choice::A, "".into(), 1.0).is_err());
        assert_eq!(store.progress().completed, 0);
        assert_eq!(store.session.queue[0], "p0");
        assert!(store.judge("p0".into(), Choice::B, "".into(), 1.0).is_err());
        assert!(fs::read(a).unwrap().is_empty());
    }
    #[cfg(unix)]
    #[test]
    fn linked_session_state_is_rejected_before_reading() {
        let (_d, p, a, s) = fixture();
        fs::create_dir_all(s.parent().unwrap()).unwrap();
        std::os::unix::fs::symlink(p.with_file_name("pairs-key.json"), &s).unwrap();
        assert!(Store::open(p, a, s).is_err());
    }
    #[test]
    fn exports_counts_without_reading_neighboring_files() {
        let (_d, p, a, s) = fixture();
        let mut store = Store::open(p, a.clone(), s).unwrap();
        store
            .judge("p0".into(), Choice::Tie, "".into(), 4.0)
            .unwrap();
        store.export().unwrap();
        let summary: serde_json::Value =
            serde_json::from_slice(&fs::read(a.with_file_name("summary.json")).unwrap()).unwrap();
        assert_eq!(summary["counts"]["tie"], 1);
    }
}
