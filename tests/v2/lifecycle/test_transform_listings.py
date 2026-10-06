"""Transform listings hide the preserved V1 (legacy) rows.

The two uploaded V1 definitions stay in the store (an old definition is never
erased, S16/M11-AC01) but they duplicate the built-in Polish and Prompt
Engineer, so neither the menu-bar Transforms submenu nor the Hub / companion
Transforms list shows them. The store itself still returns them (covered by
transforms/test_transform_definitions.py).

Run from this directory: ../../../.venv/bin/python test_transform_listings.py
"""

import sys
import types

from AppKit import NSMenu

from test_lifecycle import Harness
from localflow.v2 import transforms as tf
from localflow.v2.ui.state import HubState


def _defn(transform_id, name, origin):
    return tf.TransformDefinition(
        transform_id=transform_id, name=name, mode="custom", origin=origin,
        description="", prompt="p", edit_types=(), examples=(),
        shortcut=None, target_profiles=(), auto_apply=False, enabled=True,
        revision=1, source_locator=None, legacy_key=None)


DEFS = [
    _defn("builtin:polish", "Polish", "builtin"),
    _defn("builtin:prompt_engineer", "Prompt Engineer", "builtin"),
    _defn("legacy:transform:1:e7eb86b1", "Polish", "legacy"),
    _defn("legacy:transform:2:e7eb86b1", "Prompt Engineer", "legacy"),
    _defn("user:mine", "Mine", "user"),
]
KEPT = ["builtin:polish", "builtin:prompt_engineer", "user:mine"]


def test_menu_lists_no_legacy_rows():
    h = Harness(durations=[1.0])
    try:
        d = h.d
        d._tf_store = None  # no hotkey prefs needed to list titles
        d._transforms_snapshot = lambda: types.SimpleNamespace(
            definitions=tuple(DEFS))
        menu = NSMenu.alloc().init()
        d.transforms_menu = menu
        d.menuNeedsUpdate_(menu)
        ids = [str(i.representedObject()) for i in menu.itemArray()]
        titles = [str(i.title()) for i in menu.itemArray()]
        assert ids == KEPT, (ids, titles)
        assert not any("legacy" in t for t in titles), titles
        assert titles == ["Polish", "Prompt Engineer", "Mine"], (
            f"titles repeat the mode in parentheses: {titles}")
    finally:
        h.close()
    print("ok  menu: legacy duplicates hidden, built-in and own rows kept")


def test_hub_and_companion_list_has_no_legacy_rows():
    class _Service:
        def definitions(self):
            return list(DEFS)

        def hotkeys(self):
            return {d.transform_id: {"binding": None, "source": "default"}
                    for d in DEFS}

        def hotkey_conflicts(self):
            return []

    published = {}
    stub = types.SimpleNamespace(
        transforms_service=_Service(),
        _publish_locked=lambda view, req, **kw: published.update(kw))
    HubState._load_transforms(stub, req=None)
    assert published.get("error") is None, published
    got = [t["transform_id"] for t in published["data"]["transforms"]]
    assert got == KEPT, got
    print("ok  hub / companion list: legacy duplicates hidden")


def main():
    test_menu_lists_no_legacy_rows()
    test_hub_and_companion_list_has_no_legacy_rows()
    print("all transform listing tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
