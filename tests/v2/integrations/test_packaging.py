"""Qualify a built bundle without opening windows or the installed app.

Run with the build script's --output result:
  python tests/v2/integrations/test_packaging.py --bundle /absolute/LocalFlow.app
The probe imports AppKit but never creates NSApplication or starts the app.
Visible Dock/reopen/permissions acceptance requires separate native qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
WEB = Path("localflow/v2/ui/companion/web")


def production_paths(folder, resources):
    return sorted(path.relative_to(resources).as_posix()
                  for path in folder.rglob("*")
                  if path.is_file() and "__pycache__" not in path.relative_to(resources).parts
                  and path.name != "BUILD.json")


def verify_provenance(resources, source_root=None):
    """Check the manifest's inventory and bytes, then optional source drift.

    Frontend source_sha256 describes the embedded frontend BUILD, not an
    assertion that an unbuilt frontend source tree matches those assets.
    """
    record = json.loads((resources / "BUILD.json").read_text())
    assert set(record) == {"source_revision", "dirty", "production", "frontend"}
    assert isinstance(record["dirty"], bool)
    for key, folder in (("production", resources / "localflow"),
                        ("frontend", resources / WEB)):
        section = record[key]
        paths = [entry["path"] for entry in section["files"]]
        assert paths == sorted(set(paths)), f"{key}: unsorted or duplicate paths"
        assert paths == production_paths(folder, resources), f"{key}: file inventory changed"
        digest = hashlib.sha256()
        for entry in section["files"]:
            assert set(entry) == {"path", "sha256"}
            relative = entry["path"]
            actual = hashlib.sha256((resources / relative).read_bytes()).hexdigest()
            assert entry["sha256"] == actual, f"bundled bytes changed: {relative}"
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(actual.encode("ascii") + b"\0")
            if source_root is not None:
                source = source_root / relative
                assert source.is_file(), f"source file missing: {relative}"
                assert hashlib.sha256(source.read_bytes()).hexdigest() == actual, \
                    f"source changed since packaging: {relative}"
        assert section["sha256"] == digest.hexdigest(), f"{key}: manifest hash changed"
        if source_root is not None:
            assert paths == production_paths(source_root / folder.relative_to(resources), source_root), \
                f"{key}: source inventory changed since packaging"
    frontend_build = (resources / WEB / "BUILD.json").read_bytes()
    assert record["frontend"]["build_sha256"] == hashlib.sha256(frontend_build).hexdigest(), \
        "frontend BUILD changed"
    assert record["frontend"]["source_sha256"] == json.loads(frontend_build)["source_sha256"], \
        "frontend source hash changed"
    if source_root is not None:
        assert (source_root / WEB / "BUILD.json").read_bytes() == frontend_build, \
            "frontend BUILD source changed since packaging"
    return record


class PackagingTests(unittest.TestCase):
    bundle: Path

    @classmethod
    def setUpClass(cls):
        cls.resources = cls.bundle / "Contents/Resources"
        cls.executable = cls.bundle / "Contents/MacOS/LocalFlow"
        result = subprocess.run([str(cls.executable), "--localflow-runtime-check"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(f"native runtime probe failed: {result.returncode}: {result.stderr}")
        cls.probe = json.loads(result.stdout)

    def test_appkit_import_runs_inside_the_native_main_bundle(self):
        self.assertEqual(self.probe["bundle_id"], "com.danny.localflow")
        self.assertEqual(Path(self.probe["bundle_path"]), self.bundle)
        self.assertEqual(Path(self.probe["executable"]), self.executable)
        self.assertEqual(self.probe["process_name"], "LocalFlow")
        self.assertEqual(self.probe["name"], "LocalFlow")
        self.assertEqual(self.executable.read_bytes()[:4], b"\xcf\xfa\xed\xfe")

    def test_runtime_and_worker_interpreter_are_separate_from_ui_executable(self):
        self.assertEqual(Path(self.probe["python"]), self.resources / "venv/bin/python")
        self.assertEqual(Path(self.probe["prefix"]), self.resources / "venv")
        self.assertEqual(Path(self.probe["base_prefix"]), self.resources / "runtime")
        result = subprocess.run([self.probe["python"], "-c",
            "import json,sys; print(json.dumps({'prefix':sys.prefix}))"],
            capture_output=True, text=True, cwd=self.resources, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["prefix"]), self.resources / "venv")

    def test_icon_decodes_in_appkit_and_has_all_scaled_representations(self):
        self.assertTrue(self.probe["icon"])
        self.assertTrue(self.probe["icon_loadable"])
        data = (self.resources / "LocalFlow.icns").read_bytes()
        self.assertEqual(data[:4], b"icns")
        self.assertEqual(struct.unpack(">I", data[4:8])[0], len(data))
        kinds = set()
        offset = 8
        while offset < len(data):
            kind = data[offset:offset + 4]
            size = struct.unpack(">I", data[offset + 4:offset + 8])[0]
            self.assertGreater(size, 8)
            self.assertEqual(data[offset + 8:offset + 16], b"\x89PNG\r\n\x1a\n")
            kinds.add(kind)
            offset += size
        self.assertEqual(offset, len(data))
        self.assertEqual(kinds, {b"icp4", b"ic11", b"icp5", b"ic12", b"ic07",
                                 b"ic13", b"ic08", b"ic14", b"ic09", b"ic10"})

    def test_bundle_keeps_existing_agent_identity_and_microphone_disclosure(self):
        info = plistlib.loads((self.bundle / "Contents/Info.plist").read_bytes())
        self.assertTrue(info["LSUIElement"])
        self.assertEqual(info["CFBundleExecutable"], "LocalFlow")
        self.assertEqual(info["CFBundleIdentifier"], self.probe["bundle_id"])
        self.assertIn("NSMicrophoneUsageDescription", info)

    def test_source_and_frontend_provenance_match_built_inputs(self):
        record = verify_provenance(self.resources, ROOT)
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        self.assertEqual(record["source_revision"], revision)

    def test_existing_qualification_output_is_refused(self):
        result = subprocess.run(["/bin/zsh", str(ROOT / "scripts/build_app.sh"),
                                 "--output", str(self.bundle)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Output already exists", result.stderr)


class ProvenanceTests(unittest.TestCase):
    """Synthetic copied resources exercise the build's actual provenance code."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="localflow-packaging-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resources = self.root / "bundle/Contents/Resources"
        self.resources.mkdir(parents=True)
        for relative, content in {
            "localflow/zeta.py": "VALUE = 1\n",
            "localflow/a/file.py": "# Synthetic production module\n",
            "localflow/a.py": "# Sort relative paths as strings\n",
            "localflow/__pycache__/zeta.cpython-314.pyc": "ignored bytecode",
            "localflow/legacy.pyc": "copied sourceless module",
            f"{WEB}/index.html": '<script src="./assets/test.js"></script>',
            f"{WEB}/assets/test.js": "export const synthetic = true;\n",
            f"{WEB}/assets/test.css": "body { color: black; }\n",
            f"{WEB}/THIRD_PARTY_NOTICES.txt": "Synthetic notice\n",
            f"{WEB}/BUILD.json": json.dumps({"source_sha256": "a" * 64}),
            "config.json": '{"synthetic_private_value":"do-not-record-content"}',
        }.items():
            path = self.resources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.source = self.root / "source"
        shutil.copytree(self.resources / "localflow", self.source / "localflow")
        script = (ROOT / "scripts/build_app.sh").read_text()
        self.builder = script.split("<<'PROVENANCE'\n", 1)[1].split("\nPROVENANCE\n", 1)[0]
        self.build_record()

    def build_record(self, resources=None, dirty="true"):
        result = subprocess.run([sys.executable, "-c", self.builder,
                                 str(resources or self.resources), "1" * 40, dirty],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return (resources or self.resources) / "BUILD.json"

    def test_manifest_is_deterministic_relative_and_records_copied_bytes(self):
        record = verify_provenance(self.resources, self.source)
        self.assertEqual(record["source_revision"], "1" * 40)
        self.assertTrue(record["dirty"])
        paths = [entry["path"] for entry in record["production"]["files"]]
        self.assertEqual(len(paths), 8)
        self.assertEqual(paths[:2], ["localflow/a.py", "localflow/a/file.py"])
        self.assertIn(f"{WEB}/assets/test.js", paths)
        self.assertIn("localflow/legacy.pyc", paths)
        self.assertEqual(record["frontend"]["source_sha256"], "a" * 64)
        self.assertEqual(len(record["frontend"]["files"]), 4)
        text = (self.resources / "BUILD.json").read_text()
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("config.json", text)
        self.assertNotIn("do-not-record-content", text)
        relocated = self.root / "relocated/Resources"
        shutil.copytree(self.resources, relocated)
        self.assertEqual(self.build_record(relocated).read_text(), text)
        self.assertFalse(json.loads(self.build_record(dirty="false").read_text())["dirty"])

    def test_backend_tampering_is_detected_without_a_revision_change(self):
        for relative in ("localflow/zeta.py", "localflow/legacy.pyc"):
            with self.subTest(path=relative):
                path = self.resources / relative
                original = path.read_bytes()
                path.write_bytes(b"changed executable bytes")
                with self.assertRaisesRegex(AssertionError, f"bundled bytes changed: {relative}"):
                    verify_provenance(self.resources)
                path.write_bytes(original)

    def test_frontend_asset_tampering_is_detected(self):
        (self.resources / WEB / "assets/test.js").write_text("export const synthetic = false;\n")
        with self.assertRaisesRegex(AssertionError, "bundled bytes changed: .*assets/test.js"):
            verify_provenance(self.resources)

    def test_added_or_removed_production_files_are_detected(self):
        extra = self.resources / "localflow/added.py"
        extra.write_text("# Synthetic additional module\n")
        with self.assertRaisesRegex(AssertionError, "file inventory changed"):
            verify_provenance(self.resources)
        extra.unlink()
        (self.resources / "localflow/zeta.py").unlink()
        with self.assertRaisesRegex(AssertionError, "file inventory changed"):
            verify_provenance(self.resources)

    def test_manifest_metadata_corruption_is_detected(self):
        path = self.resources / "BUILD.json"
        original = path.read_text()
        for key in ("production", "frontend"):
            with self.subTest(section=key):
                record = json.loads(original)
                record[key]["sha256"] = "0" * 64
                path.write_text(json.dumps(record))
                with self.assertRaisesRegex(AssertionError, f"{key}: manifest hash changed"):
                    verify_provenance(self.resources)
        record = json.loads(original)
        record["production"]["files"].append(record["production"]["files"][0])
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(AssertionError, "unsorted or duplicate paths"):
            verify_provenance(self.resources)

    def test_backend_source_drift_is_detected_with_the_same_git_revision(self):
        (self.source / "localflow/zeta.py").write_text("VALUE = 2\n")
        with self.assertRaisesRegex(AssertionError, "source changed since packaging: localflow/zeta.py"):
            verify_provenance(self.resources, self.source)
        self.assertEqual(json.loads((self.resources / "BUILD.json").read_text())["source_revision"], "1" * 40)

    def test_new_source_module_is_detected_as_stale(self):
        (self.source / "localflow/added.py").write_text("# Synthetic new source\n")
        with self.assertRaisesRegex(AssertionError, "source inventory changed since packaging"):
            verify_provenance(self.resources, self.source)

    def test_frontend_build_tampering_and_source_drift_are_detected(self):
        changed = json.dumps({"source_sha256": "b" * 64})
        (self.source / WEB / "BUILD.json").write_text(changed)
        with self.assertRaisesRegex(AssertionError, "frontend BUILD source changed since packaging"):
            verify_provenance(self.resources, self.source)
        (self.resources / WEB / "BUILD.json").write_text(changed)
        with self.assertRaisesRegex(AssertionError, "frontend BUILD changed"):
            verify_provenance(self.resources)

    def test_frontend_source_hash_metadata_corruption_is_detected(self):
        path = self.resources / "BUILD.json"
        record = json.loads(path.read_text())
        record["frontend"]["source_sha256"] = "b" * 64
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(AssertionError, "frontend source hash changed"):
            verify_provenance(self.resources)

    def test_cache_build_record_and_config_are_not_production_inputs(self):
        original = (self.resources / "BUILD.json").read_bytes()
        (self.resources / "localflow/__pycache__/new.pyc").write_bytes(b"synthetic cache")
        (self.resources / "config.json").write_text("changed private config")
        self.assertEqual(self.build_record().read_bytes(), original)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    args, remainder = parser.parse_known_args()
    PackagingTests.bundle = args.bundle.resolve()
    unittest.main(argv=[sys.argv[0], *remainder], verbosity=2)
