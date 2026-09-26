"""Skill manifest discovery and the frozen skill registry (V2 M10,
Spec S17 "developer mode").

Discovery reads ONLY explicitly configured local manifests and
directories (config ``skill_manifest_paths``) plus explicitly configured
workspace-relative directories (``workspace_skill_dirs``) resolved
against the active document's directory. Nothing scans the home
directory, no skill is ever executed during discovery, and only the
manifest's declared identity (name, aliases) is read.

Filesystem authority (contracts/profiles.md): a configured path is the
authority the user granted — it is opened as named (a configured path
that is itself a symbolic link names its target explicitly). Nothing
BELOW it is followed: every child directory and every ``SKILL.md`` is
opened relative to its parent's descriptor with ``O_NOFOLLOW``, so a
child link (planted, or swapped in after the listing) is refused instead
of read. A workspace directory is opened component by component the
same way under the document's directory.

Work is bounded by what is admitted, not by what is returned: a skill
directory lists at most ``SKILL_DIR_ENTRY_LIMIT`` entries (a larger one
is refused whole — never sampled), a ``SKILL.md`` contributes at most
its first ``FRONTMATTER_READ_LIMIT`` bytes and a JSON manifest at most
``MANIFEST_BYTES_LIMIT`` bytes; each file is read once, and its record's
revision fingerprints exactly the bytes that were parsed.

Every source yields a content-free outcome (``DiscoveryResult``); one
failing source never aborts the others and contributes nothing itself.
The registry freezes per job (pre-decode) like the vocabulary snapshot.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import re
import stat as stat_mod
from types import MappingProxyType
from typing import Optional

# A SKILL.md contributes at most this many leading bytes: the
# frontmatter block must open on the first line and close inside it.
FRONTMATTER_READ_LIMIT = 4096
# A JSON manifest larger than this is refused (identity data only).
MANIFEST_BYTES_LIMIT = 256 * 1024
# A configured skill directory listing more entries than this is
# refused whole (deterministic: never a partial sample).
SKILL_DIR_ENTRY_LIMIT = 512

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


@dataclasses.dataclass(frozen=True)
class SkillRecord:
    """One discovered skill: identity + provenance, no behavior."""

    name: str                     # exact slash name ("brainstorm")
    aliases: tuple[str, ...] = ()  # spoken aliases (word tokens)
    source: str = "manifest"      # manifest | dictionary (merged later)
    manifest_path: Optional[str] = None
    manifest_revision: Optional[str] = None  # fingerprint of the bytes
                                             # the record was parsed from
    scope: str = "global"         # global | workspace:<name>

    def __post_init__(self):
        _validate_name(self.name)
        object.__setattr__(self, "aliases", tuple(self.aliases))


@dataclasses.dataclass(frozen=True)
class WorkspaceDir:
    """A workspace skill directory: ``relative`` (a validated relative
    path, no ``..``) under ``base`` (the active document's directory),
    opened component by component without following links."""

    base: str
    relative: str


@dataclasses.dataclass(frozen=True)
class DiscoveryResult:
    """Records plus one content-free outcome per configured source and
    the fingerprint of every file/listing actually admitted."""

    records: tuple
    outcomes: tuple
    fingerprint: tuple

    def summary(self) -> dict:
        refused = sum(1 for o in self.outcomes
                      if o["outcome"] in ("refused", "invalid"))
        return {"sources": len(self.outcomes), "refused_sources": refused,
                "refused_children": sum(o.get("refused_children", 0)
                                        for o in self.outcomes),
                "reasons": sorted({o["reason"] for o in self.outcomes
                                   if o.get("reason")})}


class ManifestRefused(ValueError):
    """A content-free refusal: ``code`` names the rule, never content."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_name(name) -> str:
    if not isinstance(name, str):
        raise ValueError("skill name must be a string")
    name = name.strip()
    if not name or any(c.isspace() for c in name):
        raise ValueError(f"skill name must be one token: {name!r}")
    return name


def _validate_alias(alias) -> str:
    if not isinstance(alias, str):
        raise ValueError("skill alias must be a string")
    alias = " ".join(alias.split()).lower()
    if not alias or not all(p.isalpha() for p in alias.split()):
        raise ValueError(f"skill alias must be word tokens: {alias!r}")
    return alias


def _revision(data: bytes, size: int) -> str:
    return hashlib.sha256(data + b"\0" + str(size).encode()).hexdigest()[:12]


def _stat_key(st) -> tuple:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
            st.st_ctime_ns)


def _read_bounded(fd: int, limit: int) -> bytes:
    chunks, total = [], 0
    while total < limit:
        b = os.read(fd, min(65536, limit - total))
        if not b:
            break
        chunks.append(b)
        total += len(b)
    return b"".join(chunks)


# ---- frontmatter (leading, closed, bounded) --------------------------------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(.*)$")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _alias_items(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") or raw.endswith("]"):
        if not (raw.startswith("[") and raw.endswith("]")):
            raise ManifestRefused("invalid_alias_list")
        raw = raw[1:-1]
    return [_unquote(p) for p in raw.split(",") if p.strip()]


def parse_frontmatter(data: bytes):
    """(name or None, aliases, reason) from a SKILL.md prefix.

    The block must OPEN on the first line (``---``, an optional UTF-8
    BOM before it) and CLOSE on a later ``---`` line inside the bounded
    prefix; anything else is not frontmatter. Supported fields: ``name``
    (one token) and ``aliases`` (a comma list, a ``[flow, list]`` or an
    indented ``- item`` block); other keys and their continuation lines
    are ignored. Returns reason ``no_frontmatter`` when the file does not
    start with a block (the directory name then names the skill), or
    raises ``ManifestRefused`` for a block that is present but malformed
    (unclosed, not UTF-8, a duplicate or invalid field)."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    first_nl = data.find(b"\n")
    first = data if first_nl < 0 else data[:first_nl]
    if first.rstrip(b"\r \t") != b"---":
        return None, (), "no_frontmatter"
    lines = data.split(b"\n")
    close = next((i for i in range(1, len(lines))
                  if lines[i].rstrip(b"\r \t") == b"---"), None)
    if close is None:
        raise ManifestRefused("frontmatter_unclosed")
    try:
        header = [ln.decode("utf-8").rstrip("\r")
                  for ln in lines[1:close]]
    except UnicodeDecodeError:
        raise ManifestRefused("frontmatter_not_utf8")
    name = None
    aliases: list[str] = []
    seen = set()
    current = None           # the key whose block list is open
    for line in header:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace():
            item = line.strip()
            if current == "aliases" and item.startswith("-"):
                aliases.append(_unquote(item[1:]))
            continue         # a continuation of an ignored key
        m = _KEY_RE.match(line)
        if m is None:
            raise ManifestRefused("frontmatter_malformed_line")
        key, value = m.group(1), m.group(2)
        current = key
        if key not in ("name", "aliases"):
            continue
        if key in seen:
            raise ManifestRefused("frontmatter_duplicate_field")
        seen.add(key)
        if key == "name":
            name = _unquote(value)
            if not name:
                name = None
        elif value.strip():
            aliases.extend(_alias_items(value))
    try:
        if name is not None:
            name = _validate_name(name)
        out_aliases = tuple(_validate_alias(a) for a in aliases)
    except ValueError:
        raise ManifestRefused("frontmatter_invalid_field")
    return name, out_aliases, None


# ---- JSON manifests (validated shape) --------------------------------------

def parse_json_manifest(data: bytes) -> list[tuple[str, tuple]]:
    """[(name, aliases)] from manifest bytes, the shape validated before
    use: ``{"skills": [{"name": str, "aliases": [str, ...]}, ...]}``
    (``aliases`` optional; other keys ignored)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ManifestRefused("manifest_not_utf8")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        raise ManifestRefused("manifest_json_syntax")
    if not isinstance(doc, dict):
        raise ManifestRefused("manifest_not_an_object")
    skills = doc.get("skills", [])
    if not isinstance(skills, list):
        raise ManifestRefused("manifest_skills_not_a_list")
    out = []
    for item in skills:
        if not isinstance(item, dict):
            raise ManifestRefused("manifest_skill_not_an_object")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise ManifestRefused("manifest_aliases_not_a_list")
        try:
            out.append((_validate_name(item.get("name")),
                        tuple(_validate_alias(a) for a in aliases)))
        except ValueError:
            raise ManifestRefused("manifest_invalid_field")
    return out


# ---- descriptor-relative reads ---------------------------------------------

def _configured_path(spec) -> str:
    """A configured source as an absolute path string. A relative path
    would resolve against whatever the current directory is — never
    configured authority — and a non-path value is refused."""
    try:
        path = os.fspath(spec)
    except TypeError:
        raise ManifestRefused("path_not_a_string")
    if not isinstance(path, str) or not path:
        raise ManifestRefused("path_not_a_string")
    if "\x00" in path:
        raise ManifestRefused("path_invalid")
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        raise ManifestRefused("path_not_absolute")
    return path


def _open_configured(path: str) -> int:
    """Open a CONFIGURED path as named (the explicit authority)."""
    return os.open(path, os.O_RDONLY | _O_NONBLOCK | _O_CLOEXEC)


def _open_child_dir(parent_fd: int, name: str) -> int:
    return os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW
                   | _O_CLOEXEC, dir_fd=parent_fd)


def _open_child_file(parent_fd: int, name: str) -> int:
    return os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK
                   | _O_CLOEXEC, dir_fd=parent_fd)


def _list_dir(fd: int):
    """Sorted (name, is_real_dir, is_link) for at most
    SKILL_DIR_ENTRY_LIMIT entries; ManifestRefused when larger."""
    entries = []
    with os.scandir(fd) as it:
        for entry in it:
            if len(entries) >= SKILL_DIR_ENTRY_LIMIT:
                raise ManifestRefused("directory_too_large")
            try:
                link = entry.is_symlink()
                is_dir = (not link) and entry.is_dir(follow_symlinks=False)
            except OSError:
                link, is_dir = False, False
            entries.append((entry.name, is_dir, link))
    entries.sort()
    return entries


def _read_skill_dir(fd: int, source_path: str, scope: str, fp: list):
    """Records of one skill directory (one level of ``<skill>/SKILL.md``)
    read through ``fd``; returns (records, refused_children)."""
    records, refused = [], 0
    entries = _list_dir(fd)
    fp.append(("dir", tuple(n for n, _, _ in entries)))
    for name, is_dir, link in entries:
        if link:
            # A child link is never followed: planted or swapped, its
            # target lies outside the authority this directory grants.
            refused += 1
            continue
        if not is_dir:
            continue
        try:
            cfd = _open_child_dir(fd, name)
        except OSError:
            refused += 1   # vanished, or replaced by a link since listed
            continue
        try:
            try:
                mfd = _open_child_file(cfd, "SKILL.md")
            except FileNotFoundError:
                continue
            except OSError:
                refused += 1   # a SKILL.md link, or unreadable
                # An unreadable regular file still keys the fingerprint
                # as the pre-pass sees it (its metadata, not its bytes).
                try:
                    lst = os.stat("SKILL.md", dir_fd=cfd,
                                  follow_symlinks=False)
                    if stat_mod.S_ISREG(lst.st_mode):
                        fp.append(("file", name, _stat_key(lst)))
                except OSError:
                    pass
                continue
            try:
                st = os.fstat(mfd)
                if not stat_mod.S_ISREG(st.st_mode):
                    refused += 1
                    continue
                data = _read_bounded(mfd, FRONTMATTER_READ_LIMIT)
            finally:
                os.close(mfd)
            fp.append(("file", name, _stat_key(st)))
            try:
                skill_name, aliases, _reason = parse_frontmatter(data)
                # The directory names the skill when the header does not
                # (never the body: without a leading block nothing but
                # the directory name is identity).
                skill_name = _validate_name(skill_name or name)
            except ValueError:
                refused += 1
                continue
            records.append(SkillRecord(
                name=skill_name, aliases=aliases, source="manifest",
                manifest_path=os.path.join(source_path, name, "SKILL.md"),
                manifest_revision=_revision(data, st.st_size), scope=scope))
        finally:
            os.close(cfd)
    return records, refused


def _read_json_fd(fd: int, st, source_path: str, scope: str, fp: list):
    data = _read_bounded(fd, MANIFEST_BYTES_LIMIT + 1)
    if len(data) > MANIFEST_BYTES_LIMIT:
        raise ManifestRefused("manifest_too_large")
    fp.append(("file", "", _stat_key(st)))
    rev = _revision(data, st.st_size)
    return [SkillRecord(name=n, aliases=a, source="manifest",
                        manifest_path=source_path, manifest_revision=rev,
                        scope=scope)
            for n, a in parse_json_manifest(data)]


def _open_workspace_dir(wd: WorkspaceDir) -> int:
    """Open ``wd.relative`` under ``wd.base`` one component at a time
    without following any link below the base."""
    if "\x00" in str(wd.base) or "\x00" in str(wd.relative):
        raise ManifestRefused("path_invalid")
    rel = pathlib.PurePosixPath(wd.relative)
    if rel.is_absolute() or not rel.parts or any(
            p in ("..", "") for p in rel.parts):
        raise ManifestRefused("workspace_dir_not_relative")
    fd = os.open(wd.base, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC)
    try:
        for part in rel.parts:
            if part == ".":
                continue
            nxt = _open_child_dir(fd, part)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def _discover_source(kind: str, index: int, spec, scope: str):
    """(records, outcome, fingerprint parts) for one configured source."""
    fp: list = []
    outcome = {"source": index, "kind": kind, "outcome": "read",
               "reason": None, "records": 0, "refused_children": 0}
    fd = None
    try:
        if isinstance(spec, WorkspaceDir):
            fd = _open_workspace_dir(spec)
            path = os.path.join(spec.base, spec.relative)
        else:
            path = _configured_path(spec)
            fd = _open_configured(path)
        st = os.fstat(fd)
        if stat_mod.S_ISDIR(st.st_mode):
            records, refused = _read_skill_dir(fd, path, scope, fp)
            outcome["refused_children"] = refused
        elif stat_mod.S_ISREG(st.st_mode) and not isinstance(
                spec, WorkspaceDir):
            records = _read_json_fd(fd, st, path, scope, fp)
        else:
            raise ManifestRefused("not_a_regular_file_or_directory")
    except FileNotFoundError:
        outcome.update(outcome="missing", reason="not_found")
        return [], outcome, (index, "missing")
    except ManifestRefused as e:
        outcome.update(outcome="invalid" if e.code.startswith(
            ("manifest_", "frontmatter_")) else "refused", reason=e.code)
        # The fingerprint names what was READ, not what it parsed to: a
        # source read and then refused keys exactly as the warm pre-pass
        # sees it, so an unchanged bad manifest is not re-read per job.
        if fp:
            return [], outcome, (index, "read", tuple(fp))
        return [], outcome, (index, "refused", e.code, ())
    except OSError as e:
        outcome.update(outcome="refused",
                       reason=f"os_error:{type(e).__name__}")
        return [], outcome, (index, "oserror", type(e).__name__)
    except ValueError:
        # Anything else this source cannot be opened with (one bad
        # path never aborts the other sources).
        outcome.update(outcome="refused", reason="path_invalid")
        return [], outcome, (index, "refused", "path_invalid", ())
    finally:
        if fd is not None:
            os.close(fd)
    outcome["records"] = len(records)
    return records, outcome, (index, "read", tuple(fp))


def discover_detailed(manifest_paths=(), workspace_dirs=(),
                      workspace_name: Optional[str] = None
                      ) -> DiscoveryResult:
    """Read every configured source. Directory entries are skill
    directories; file entries are JSON manifests; ``workspace_dirs`` are
    ``WorkspaceDir`` pairs (or paths) whose records are workspace-scoped.
    Failures are per source and content-free."""
    records, outcomes, fps = [], [], []
    ws_scope = f"workspace:{workspace_name}" if workspace_name \
        else "workspace"
    for i, p in enumerate(manifest_paths):
        r, o, f = _discover_source("configured", i, p, "global")
        records.extend(r)
        outcomes.append(o)
        fps.append(f)
    for i, p in enumerate(workspace_dirs):
        r, o, f = _discover_source("workspace", i, p, ws_scope)
        records.extend(r)
        outcomes.append(o)
        fps.append(f)
    return DiscoveryResult(records=tuple(records), outcomes=tuple(outcomes),
                           fingerprint=tuple(fps))


def discover(manifest_paths=(), workspace_dirs=(),
             workspace_name: Optional[str] = None) -> list[SkillRecord]:
    """The records of ``discover_detailed`` (the historical signature)."""
    return list(discover_detailed(manifest_paths, workspace_dirs,
                                  workspace_name).records)


def fingerprint(manifest_paths=(), workspace_dirs=()) -> tuple:
    """A metadata-only pre-pass producing the same fingerprint a
    discovery of these sources records (listing names; per admitted file
    device, inode, size, mtime and ctime — ctime moves on every write and
    on ``utime`` itself, so an in-place edit that restores the mtime
    still changes it). Equal fingerprints mean nothing a discovery would
    read has changed; the caller then reuses its frozen records."""
    out = []

    def one(index, spec):
        fp: list = []
        fd = None
        try:
            if isinstance(spec, WorkspaceDir):
                fd = _open_workspace_dir(spec)
            else:
                fd = _open_configured(_configured_path(spec))
            st = os.fstat(fd)
            if stat_mod.S_ISDIR(st.st_mode):
                entries = _list_dir(fd)
                fp.append(("dir", tuple(n for n, _, _ in entries)))
                for name, is_dir, link in entries:
                    if link or not is_dir:
                        continue
                    try:
                        cfd = _open_child_dir(fd, name)
                    except OSError:
                        continue
                    try:
                        cst = os.stat("SKILL.md", dir_fd=cfd,
                                      follow_symlinks=False)
                    except OSError:
                        continue
                    finally:
                        os.close(cfd)
                    if stat_mod.S_ISREG(cst.st_mode):
                        fp.append(("file", name, _stat_key(cst)))
                return (index, "read", tuple(fp))
            if stat_mod.S_ISREG(st.st_mode) and not isinstance(
                    spec, WorkspaceDir):
                if st.st_size > MANIFEST_BYTES_LIMIT:
                    return (index, "refused", "manifest_too_large", ())
                return (index, "read", (("file", "", _stat_key(st)),))
            return (index, "refused", "not_a_regular_file_or_directory",
                    ())
        except FileNotFoundError:
            return (index, "missing")
        except ManifestRefused as e:
            return (index, "refused", e.code, tuple(fp))
        except OSError as e:
            return (index, "oserror", type(e).__name__)
        except ValueError:
            return (index, "refused", "path_invalid", ())
        finally:
            if fd is not None:
                os.close(fd)

    for i, p in enumerate(manifest_paths):
        out.append(one(i, p))
    for i, p in enumerate(workspace_dirs):
        out.append(one(i, p))
    return tuple(out)


def records_revision(records) -> str:
    """Content hash over a manifest record set (mtime-independent): the
    freeze compares this to detect a manifest edit between jobs."""
    payload = json.dumps(
        [{"name": r.name, "aliases": list(r.aliases),
          "scope": r.scope, "manifest_path": r.manifest_path}
         for r in sorted(records, key=lambda r: (r.scope, r.name,
                                                 r.manifest_path or ""))],
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


class SkillRegistry:
    """The immutable frozen registry one job captures (pre-decode).

    ``policy_skills`` is the alias→exact-name map for the M04 layer-3
    skill grammar; ``dictionary_skills`` merges in with collision
    masking (same alias, different names → unregistered, recorded).
    ``stale_workspace`` records that the registry was rebuilt because
    the destination workspace changed under the manifest set. The
    object is sealed after construction and every export is a fresh
    copy, so ``revision`` keeps identifying what the job captured."""

    def __init__(self, records, dictionary_skills=None, *,
                 stale_workspace: bool = False,
                 dictionary_provenance=None):
        _set = object.__setattr__
        _set(self, "records", tuple(records))
        _set(self, "stale_workspace", bool(stale_workspace))
        # M05-AUDIT-09: alias → (approving dictionary entry id,
        # verification) from the M05 snapshot. Carried only for keys the
        # dictionary actually registered — a manifest skill never gets a
        # fabricated M05 identity.
        dict_prov = {k: (str(v[0]), str(v[1]))
                     for k, v in dict(dictionary_provenance or {}).items()}
        merged: dict[str, list[tuple[str, str]]] = {}
        # key → [(provenance, exact name)]; manifest skills and
        # dictionary skills carry the same layer-3 weight, so a
        # same-key collision is ambiguous — masked, never ordered.
        for r in self.records:
            # Keys are spoken word phrases: a hyphenated name's spoken
            # form ("code review" for "code-review") resolves to the
            # exact hyphenated token the grammar emits.
            keys = set(r.aliases) | {r.name.lower()}
            spoken = r.name.lower().replace("-", " ").replace("_", " ")
            if spoken != r.name.lower():
                keys.add(spoken)
            for k in keys:
                merged.setdefault(k, []).append(("manifest", r.name))
        dictionary_skills = dict(dictionary_skills or {})
        dict_keys: set[str] = set()
        for alias, name in dictionary_skills.items():
            merged.setdefault(alias, []).append(("dictionary", name))
            dict_keys.add(alias)
        skills: dict[str, str] = {}
        conflicts = []
        for key, cands in merged.items():
            names = sorted({name for _, name in cands})
            if len(names) > 1:
                conflicts.append(MappingProxyType({
                    "alias": key, "names": tuple(names),
                    "reason": "ambiguous_skill_alias",
                }))
            else:
                skills[key] = names[0]
        _set(self, "conflicts", tuple(conflicts))
        _set(self, "_skills", MappingProxyType(skills))
        _set(self, "_dict_keys",
             frozenset(k for k in dict_keys if k in skills))
        _set(self, "policy_skills", MappingProxyType(dict(skills)))
        _set(self, "policy_provenance", MappingProxyType({
            k: dict_prov[k] for k in sorted(self._dict_keys)
            if k in dict_prov}))
        payload = json.dumps({
            "records": [
                {"name": r.name, "aliases": list(r.aliases),
                 "source": r.source, "manifest_path": r.manifest_path,
                 "manifest_revision": r.manifest_revision,
                 "scope": r.scope}
                for r in sorted(self.records,
                                key=lambda r: (r.scope, r.name))],
            "dictionary_skills": dictionary_skills,
            "stale_workspace": self.stale_workspace,
            # Hashed only when present (manifest-only registries keep
            # their historical revision).
            **({"dictionary_provenance": {
                k: list(v) for k, v in self.policy_provenance.items()}}
               if self.policy_provenance else {}),
        }, sort_keys=True, ensure_ascii=False)
        _set(self, "revision", f"m10skill:{hashlib.sha256(
            payload.encode()).hexdigest()[:12]}")

    def __setattr__(self, name, value):
        raise AttributeError("a frozen skill registry is immutable")

    @property
    def manifest_count(self) -> int:
        return sum(1 for r in self.records if r.source == "manifest")

    def to_json(self) -> dict:
        return {
            "revision": self.revision,
            "manifest_skills": self.manifest_count,
            "dictionary_skill_aliases": len(self._dict_keys),
            # Opaque approving entry ids of the registered dictionary
            # skills (ids only — no alias text in this summary).
            "dictionary_rule_ids": sorted({v[0] for v in
                                           self.policy_provenance.values()}),
            "registered_aliases": len(self._skills),
            "stale_workspace": self.stale_workspace,
            "conflicts": [{"alias": c["alias"], "names": list(c["names"]),
                           "reason": c["reason"]} for c in self.conflicts],
            "records": [
                {"name": r.name, "aliases": list(r.aliases),
                 "scope": r.scope,
                 "manifest_revision": r.manifest_revision}
                for r in self.records],
        }
