"""Physical transform shortcuts, separate from semantic revisions.

Preferences occupy namespaced transform_meta rows. A persisted source plus
nullable binding distinguishes shipped defaults from user overrides/clears.
"""
import json

MODIFIERS = ("control", "option", "shift", "command")
DEFAULTS = {"builtin:polish": 18, "builtin:prompt_engineer": 19,
            "builtin:concise": 20}
# macOS ANSI virtual key identities, never the Option-produced Unicode.
KEY_LABELS = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z",
    7: "X", 8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E",
    15: "R", 16: "Y", 17: "T", 18: "1", 19: "2", 20: "3", 21: "4",
    22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
    29: "0", 30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P",
    36: "Return", 37: "L", 38: "J", 39: "'", 40: "K", 41: ";",
    42: "\\", 43: ",", 44: "/", 45: "N", 46: "M", 47: ".",
    48: "Tab", 49: "Space", 50: "`", 51: "Delete", 53: "Escape",
    123: "←", 124: "→", 125: "↓", 126: "↑",
}
GLYPHS = {"control": "⌃", "option": "⌥", "shift": "⇧", "command": "⌘"}


def normalize(binding):
    if binding is None:
        return None
    if not isinstance(binding, dict) or set(binding) != {"key_code", "modifiers"}:
        raise ValueError("shortcut requires a physical key and modifiers")
    code, mods = binding["key_code"], binding["modifiers"]
    if type(code) is not int or code not in KEY_LABELS:
        raise ValueError("shortcut requires a supported physical key")
    if not isinstance(mods, (list, tuple)) or not mods or any(
            m not in MODIFIERS for m in mods) or len(set(mods)) != len(mods):
        raise ValueError("shortcut requires at least one distinct modifier")
    return {"key_code": code, "modifiers": [m for m in MODIFIERS if m in mods]}


def identity(binding):
    b = normalize(binding)
    return (b["key_code"], tuple(b["modifiers"])) if b else None


def display(binding):
    b = normalize(binding)
    return "".join(GLYPHS[m] for m in b["modifiers"]) + KEY_LABELS[b["key_code"]] if b else "No shortcut"


def legacy_binding(shortcut):
    if not shortcut:
        return None
    code = next((k for k, v in KEY_LABELS.items() if v.lower() == shortcut.lower()), None)
    return {"key_code": code, "modifiers": ["command"]} if code is not None else None


def conn_preferences(db):
    out = {}
    for tid, shortcut, origin in db.execute(
            "SELECT transform_id, shortcut, origin FROM transforms").fetchall():
        key = "hotkey:" + tid
        row = db.execute("SELECT value FROM transform_meta WHERE key=?", (key,)).fetchone()
        if row:
            pref = json.loads(row[0])
        else:
            # Preserve old menu assignments as Command + physical key where
            # representable. Never rewrite their preserved definitions.
            if shortcut:
                pref = {"source": "user", "binding": legacy_binding(shortcut)}
            elif tid in DEFAULTS:
                pref = {"source": "default", "binding": {
                    "key_code": DEFAULTS[tid], "modifiers": ["option"]}}
            else:
                pref = {"source": "user", "binding": None}
            db.execute("INSERT INTO transform_meta(key,value) VALUES(?,?)", (key, json.dumps(pref)))
        out[tid] = pref
    return out


def conn_conflicts(db):
    prefs = conn_preferences(db)
    seen, conflicts = {}, []
    for tid, in db.execute("SELECT transform_id FROM transforms WHERE enabled=1 ORDER BY transform_id"):
        binding = prefs[tid]["binding"]
        chord = identity(binding)
        if chord is None:
            continue
        if chord in seen:
            conflicts.append({"shortcut": display(binding), "transform_ids": [seen[chord], tid]})
        else:
            seen[chord] = tid
    return conflicts


def conn_check(db, tid, binding):
    ident = identity(binding)
    if ident is None:
        return
    prefs = conn_preferences(db)
    for other, name in db.execute("SELECT transform_id,name FROM transforms WHERE enabled=1 AND transform_id!=?", (tid,)):
        if identity(prefs[other]["binding"]) == ident:
            raise ValueError(f"shortcut {display(binding)} is used by {name}")


def conn_write(db, tid, binding, reset=False):
    row = db.execute("SELECT enabled,origin FROM transforms WHERE transform_id=?", (tid,)).fetchone()
    if row is None:
        raise ValueError("transform not found")
    if row[1] == "legacy":
        raise ValueError("legacy transform shortcuts are preserved and unbound")
    if reset:
        if tid not in DEFAULTS:
            raise ValueError("this transform has no shipped default")
        binding = {"key_code": DEFAULTS[tid], "modifiers": ["option"]}
    binding = normalize(binding)
    # Even a disabled definition's reset never steals an occupied default.
    if row[0] or reset:
        conn_check(db, tid, binding)
    pref = {"source": "default" if reset else "user", "binding": binding}
    db.execute("INSERT INTO transform_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("hotkey:" + tid, json.dumps(pref)))
    return pref


class ShortcutRouter:
    """Only registered chords are consumed; no key reposting at all."""
    def __init__(self, invoke):
        self.invoke = invoke
        self.bindings = {}
        self.down = set()
        self.suspended = False

    def replace(self, bindings):
        self.bindings = dict(bindings)

    def handle(self, kind, code, modifiers, repeat=False):
        if kind == "up":
            if code in self.down:
                self.down.remove(code)
                return True
            return False
        if code in self.down:
            return True
        if self.suspended:
            return False
        tid = self.bindings.get((code, tuple(m for m in MODIFIERS if m in modifiers))) if all(m in MODIFIERS for m in modifiers) else None
        if tid is None:
            return False
        self.down.add(code)
        if not repeat:
            self.invoke(tid)
        return True
