#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod store;
use std::{path::{Path, PathBuf}, sync::Mutex};
use store::{Choice, Snapshot, Store};
use tauri::Manager;
struct AppState {
    store: Mutex<Option<Store>>,
}
fn with_store<T>(
    state: &AppState,
    f: impl FnOnce(&mut Store) -> Result<T, String>,
) -> Result<T, String> {
    let mut guard = state
        .store
        .lock()
        .map_err(|_| "Restart the session.".to_string())?;
    f(guard.as_mut().ok_or("Open the session first.")?)
}
#[tauri::command]
fn load_session(app: tauri::AppHandle, state: tauri::State<AppState>) -> Result<Snapshot, String> {
    let mut guard = state
        .store
        .lock()
        .map_err(|_| "Restart the session.".to_string())?;
    // Dropping the old handle releases its lock before a retry.
    *guard = None;
    // The packet sits in the study's ignored artifacts folder, two levels above this crate.
    let default=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../artifacts/research/annotation");
    let pairs = std::env::var_os("LOCALFLOW_ANNOTATE_PAIRS")
        .map(PathBuf::from)
        .unwrap_or(default.join("pairs.jsonl"));
    let annotations = std::env::var_os("LOCALFLOW_ANNOTATE_ANNOTATIONS")
        .map(PathBuf::from)
        .unwrap_or(default.join("annotations.jsonl"));
    let state_dir = std::env::var_os("LOCALFLOW_ANNOTATE_STATE_DIR")
        .map(PathBuf::from)
        .unwrap_or(
            app.path()
                .app_data_dir()
                .map_err(|_| "App storage is unavailable.".to_string())?,
        );
    let store = Store::open(pairs, annotations, state_dir.join("session.json"))?;
    let snapshot = store.snapshot();
    *guard = Some(store);
    Ok(snapshot)
}
#[tauri::command]
fn judge(
    state: tauri::State<AppState>,
    pair_id: String,
    choice: Choice,
    note: String,
    seconds: f64,
) -> Result<Snapshot, String> {
    with_store(&state, |s| s.judge(pair_id, choice, note, seconds))
}
#[tauri::command]
fn undo(state: tauri::State<AppState>) -> Result<Snapshot, String> {
    with_store(&state, |s| s.undo())
}
#[tauri::command]
fn skip(state: tauri::State<AppState>, pair_id: String) -> Result<Snapshot, String> {
    with_store(&state, |s| s.skip(pair_id))
}
#[tauri::command]
fn save_draft(state: tauri::State<AppState>, pair_id: String, note: String) -> Result<(), String> {
    with_store(&state, |s| s.draft(pair_id, note))
}
#[tauri::command]
fn export_summary(state: tauri::State<AppState>) -> Result<(), String> {
    with_store(&state, |s| s.export())
}
fn main() {
    tauri::Builder::default()
        .manage(AppState {
            store: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            load_session,
            judge,
            undo,
            skip,
            save_draft,
            export_summary
        ])
        .run(tauri::generate_context!())
        .expect("The annotation window could not start.");
}
