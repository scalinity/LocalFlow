"""Capability/geometry tests for POLICY-D03; no live AX or pasteboard."""
import unittest
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.insertion.editable_target import (
    EditableTargetSnapshot, resolve_editable_hit)


class Host:
    def __init__(self):
        self.hit = "field"
        self.nodes = {
            "field": {"AXRole": "AXTextArea", "AXEnabled": True,
                      "AXWindow": "window", "frame": (10, 10, 100, 100),
                      "writes": {"AXSelectedText"}, "pid": 7},
            "window": {"AXRole": "AXWindow", "frame": (0, 0, 200, 200),
                       "pid": 7},
        }

    def is_trusted(self):
        return True

    def element_at_position(self, pid, point):
        return self.hit

    def element_pid(self, el):
        return self.nodes.get(el, {}).get("pid")

    def element_frame(self, el):
        return self.nodes.get(el, {}).get("frame")

    def attribute(self, el, name):
        assert name not in ("AXValue", "AXSelectedText", "AXSelectedTextRange")
        return self.nodes.get(el, {}).get(name)

    def is_settable(self, el, name):
        return name in self.nodes.get(el, {}).get("writes", ())


class EditableHitTests(unittest.TestCase):
    def test_text_field_area_search_capabilities(self):
        for role, subrole in (("AXTextField", None), ("AXTextArea", None),
                              ("AXTextField", "AXSearchField")):
            h = Host()
            h.nodes["field"].update(AXRole=role, AXSubrole=subrole)
            self.assertEqual(resolve_editable_hit(h, 7, (20, 20)).element, "field")

    def test_rich_editable_container_from_rendered_hit(self):
        h = Host()
        h.nodes["field"].update(AXRole="AXGroup", AXEditable=True,
                                writes={"AXSelectedTextRange"})
        h.nodes["child"] = {"AXRole": "AXStaticText", "AXParent": "field",
                            "frame": (15, 15, 40, 40), "pid": 7}
        h.hit = "child"
        self.assertEqual(resolve_editable_hit(h, 7, (20, 20)).element, "field")

    def test_control_boundaries_cannot_inherit_editability(self):
        for role in ("AXWindow", "AXToolbar", "AXButton", "AXRow", "AXMenu",
                     "AXScrollArea"):
            h = Host()
            h.nodes["control"] = {"AXRole": role, "AXParent": "field",
                                  "frame": (15, 15, 40, 40), "pid": 7}
            h.hit = "control"
            self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)), role)

    def test_static_or_background_without_editable_ancestor(self):
        for role in ("AXStaticText", "AXGroup"):
            h = Host()
            h.nodes["field"].update(AXRole=role, writes=set(), AXParent="window")
            self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)))

    def test_disabled_readonly_secure_or_unknown_abstain(self):
        for patch in ({"AXEnabled": False},
                      {"AXEditable": False}, {"writes": set()},
                      {"AXSubrole": "AXSecureTextField"},
                      {"AXRole": "AXUnknown"}):
            h = Host()
            h.nodes["field"].update(patch)
            self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)), patch)

    def test_missing_enabled_with_positive_text_write_capability(self):
        # Native TextEdit AXTextArea omits AXEnabled. Its settable text
        # capability proves writability; explicit disabled still refuses.
        h = Host()
        del h.nodes["field"]["AXEnabled"]
        self.assertIsNotNone(resolve_editable_hit(h, 7, (20, 20)))

    def test_geometry_owner_and_window_must_be_proven(self):
        for patch in ({"frame": None}, {"frame": (50, 50, 20, 20)},
                      {"pid": 8}, {"AXWindow": None}):
            h = Host()
            h.nodes["field"].update(patch)
            self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)), patch)
        h = Host()
        h.nodes["window"]["pid"] = 8
        self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)))

    def test_cycle_and_nonfinite_point_abstain(self):
        h = Host()
        h.nodes["field"].update(AXRole="AXGroup", writes=set(), AXParent="field")
        self.assertIsNone(resolve_editable_hit(h, 7, (20, 20)))
        self.assertIsNone(resolve_editable_hit(h, 7, (float("nan"), 20)))

    def test_target_revalidation_refuses_other_same_role_field(self):
        h = Host()
        t = EditableTargetSnapshot(target_snapshot_id="synthetic", app_pid=7,
                                   element="field", window_element="window")
        self.assertTrue(t.matches_element(h, "field"))
        h.nodes["other"] = dict(h.nodes["field"])
        self.assertFalse(t.matches_element(h, "other"))
        h.nodes["field"]["AXEnabled"] = False
        self.assertFalse(t.matches_element(h, "field"))
        self.assertNotIn("element", t.to_json())
        self.assertNotIn("window_element", t.to_json())


if __name__ == "__main__":
    unittest.main()
