import copy
import hashlib
import unittest

from v2.acknowledgment_data import normalize_approved_acknowledgment


class AcknowledgmentDataTests(unittest.TestCase):
    def row(self):
        return {
            "split": "train", "pair_id": "fixture-base", "case_id": "fixture-case",
            "family_id": "fixture-family", "contrast_group_id": "fixture-contrast",
            "raw_input": "Okay the banner was green green — keep it.",
            "model_input": "Okay the banner was green green — keep it.",
            "target": "Okay, the banner was green — keep it.\n", "is_noop": False,
            "gold_lines": ["green"], "gold_offsets": [[20, 25]],
            "protected_spans": [[36, 40]], "engine_oracle": {"exact": True},
            "normalization_edits": [[0, 1, "O"]], "normalization_changed": True,
            "source_offsets": [[10, 14]], "source_offset": 10, "window_range": [0, 40],
            "source_coordinates": {"start": 0, "end": 40}, "source_map": [1, 2],
            "obsolete_values": ["green"], "removed_fillers": ["um"],
            "calls": [{"prompt": "stale prompt"}], "target_claude": "original teacher target",
            "provenance": {"generator": "fixture", "nested": ["original"]},
        }

    def normalize(self, row, **overrides):
        approval = {"expected_target_sha256": hashlib.sha256(row["target"].encode()).hexdigest(),
                    "approval_reason": "Reviewed opening acknowledgment; retain the word repair."}
        return normalize_approved_acknowledgment(row, **(approval | overrides))

    def test_useful_repair_and_every_other_target_byte_are_preserved(self):
        row = self.row()
        before = copy.deepcopy(row)
        normalized, control = self.normalize(row)
        self.assertEqual(normalized["target"], "Okay the banner was green — keep it.\n")
        old, new = row["target"].encode(), normalized["target"].encode()
        self.assertEqual(old, new[:4] + b"," + new[4:])
        self.assertEqual(len(old) - len(new), 1)
        self.assertEqual(normalized["raw_input"], row["raw_input"])
        self.assertEqual(normalized["model_input"], row["model_input"])
        self.assertFalse(normalized["is_noop"])
        self.assertNotIn("engine_oracle", normalized)
        self.assertEqual(row, before)
        normalized["provenance"]["nested"].append("changed")
        control["provenance"]["nested"].append("control change")
        self.assertEqual(row, before)

    def test_case_differences_preserve_legitimate_capitalization_repair(self):
        for raw, model, target in (("okay", "okay", "Okay"), ("OKAY", "Okay", "okay")):
            with self.subTest(raw=raw, model=model, target=target):
                row = self.row()
                row.update(raw_input=raw + " keep this.", model_input=model + " keep this.",
                           target=target + ", keep this.")
                normalized, control = self.normalize(row)
                self.assertEqual(normalized["target"], target + " keep this.")
                self.assertEqual(control["model_input"], normalized["target"])

    def test_missing_or_stale_approval_rejects(self):
        row = self.row()
        for overrides in ({"approval_reason": None}, {"approval_reason": " "},
                          {"expected_target_sha256": None}, {"expected_target_sha256": "0" * 64}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.normalize(row, **overrides)
        with self.assertRaises(TypeError):
            normalize_approved_acknowledgment(row)
        stale_hash = hashlib.sha256(row["target"].encode()).hexdigest()
        row["target"] += "Changed."
        with self.assertRaisesRegex(ValueError, "hash"):
            self.normalize(row, expected_target_sha256=stale_hash)

    def test_non_train_rows_are_rejected(self):
        for split in ("test", "validation", "dev", "TRAIN", None):
            row = self.row()
            row["split"] = split
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "TRAIN"):
                self.normalize(row)

    def test_existing_source_comma_and_nonmatching_openings_are_rejected(self):
        for field in ("raw_input", "model_input"):
            for source in ("Okay, retain this.", "Well retain this.", " Okay retain this.", "Okay\tretain this."):
                row = self.row()
                row[field] = source
                with self.subTest(field=field, source=source), self.assertRaises(ValueError):
                    self.normalize(row)
        for target in ("Okay retain this.", "Well, retain this.", "Okay,, retain this.", "Okay,\tretain this."):
            row = self.row()
            row["target"] = target
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.normalize(row)

    def test_control_has_fresh_identity_and_metadata(self):
        row = self.row()
        normalized, control = self.normalize(row, control_suffix="-control")
        for key in ("pair_id", "case_id", "family_id"):
            self.assertEqual(normalized[key], row[key])
            self.assertEqual(control[key], row[key] + "-control")
        self.assertEqual(control["contrast_group_id"], row["contrast_group_id"])
        self.assertEqual(control["split"], "train")
        for key in ("raw_input", "model_input", "target"):
            self.assertEqual(control[key], normalized["target"])
        self.assertTrue(control["is_noop"])
        self.assertTrue(control["spec_is_noop"])
        self.assertFalse(control["normalization_changed"])
        for key in ("gold_lines", "gold_offsets", "protected_spans", "normalization_edits",
                    "obsolete_values", "removed_fillers"):
            self.assertEqual(control[key], [])
        for key in ("engine_oracle", "source_offset", "source_offsets", "source_coordinates", "source_map",
                    "window_range", "calls", "target_claude"):
            self.assertNotIn(key, control)
        transform = control["acknowledgment_transform"]
        self.assertEqual(transform["source_ids"], {key: row[key] for key in ("pair_id", "case_id", "family_id")})
        self.assertEqual(transform["original_target_sha256"], hashlib.sha256(row["target"].encode()).hexdigest())
        self.assertEqual(transform["normalized_target_sha256"], hashlib.sha256(control["target"].encode()).hexdigest())
        self.assertTrue(transform["approval_reason"])
        self.assertEqual((transform["byte_offset"], transform["removed_byte"]), (4, ","))
        self.assertEqual(control["provenance"], row["provenance"])

    def test_comma_only_label_becomes_noop_and_ids_are_required(self):
        row = self.row()
        row.update(raw_input="Okay keep this.", model_input="Okay keep this.", target="Okay, keep this.")
        normalized, _ = self.normalize(row)
        self.assertTrue(normalized["is_noop"])
        for key in ("pair_id", "case_id", "family_id"):
            invalid = dict(row, **{key: ""})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "IDs"):
                self.normalize(invalid)
        with self.assertRaisesRegex(ValueError, "suffix"):
            self.normalize(row, control_suffix="")


if __name__ == "__main__":
    unittest.main()
