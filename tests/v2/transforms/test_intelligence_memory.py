"""Integration with the separately implemented memory domain, synthetic only."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.store import Store
from localflow.v2.transforms_store import TransformStore
from localflow.v2.transforms.conversations import INTELLIGENCE_MIGRATIONS
from localflow.v2.transforms.intelligence import IntelligenceService, memory_callbacks
from localflow.v2.ui.companion.bridge import Bridge
from localflow.v2.ui.companion.surfaces.intelligence import register

try:
    from localflow.v2.memory import MEMORY_MIGRATIONS, MemoryStore
except ModuleNotFoundError:
    MemoryStore = None


class LexicalFixture:
    implementation = "synthetic-lexical-fixture"

    def encode(self, text):
        return None


@unittest.skipIf(MemoryStore is None, "memory domain has not been integrated")
class MemoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.store = Store(self.root / "db", artifacts_dir=self.root / "artifacts",
                           backup_dir=self.root / "backups")
        self.store.submit(lambda db: [db.execute(s) for s in
                                     [*MEMORY_MIGRATIONS, *INTELLIGENCE_MIGRATIONS]])
        self.memory = MemoryStore(self.store, embedding=LexicalFixture())
        self.transforms = TransformStore(self.store)
        self.transforms.seed_built_ins()
        self.service = IntelligenceService(self.store, self.transforms, object(),
                                           **memory_callbacks(self.memory))
        self.bridge = Bridge()
        self.clipboard = []
        register(SimpleNamespace(bridge=self.bridge, spec={"intelligence_service": self.service,
            "memory_service": self.memory}, state=SimpleNamespace(reload_transforms=lambda: None),
            coordinator=SimpleNamespace(hubCopyText=lambda text: self.clipboard.append(text))))

    def tearDown(self):
        self.service.close()
        self.store.close()
        self.temp.cleanup()

    def call(self, command, payload):
        return self.bridge.handle(json.dumps({"bridge_version": 1, "request_id": "test:1",
                                              "command": command, "payload": payload}))

    def finish(self, job_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = self.service.read_job(job_id)
            if job["status"] not in ("pending", "running"):
                return job
            time.sleep(0.01)
        self.fail("job did not settle")

    def project(self, name):
        root = self.root / name
        root.mkdir()
        return self.memory.create_project(name, str(root))

    def test_context_scope_pinning_exclusion_and_memory_off(self):
        a, b = self.project("Project A"), self.project("Project B")
        first = self.memory.remember("The encoder is serial.", kind="project_fact", project_id=a)
        other = self.memory.remember("The encoder is parallel.", kind="project_fact", project_id=b)
        callbacks = memory_callbacks(self.memory)
        common = dict(query="encoder", use_memory=False, purpose="transform")
        pack_a = callbacks["assemble_context"](project_id=a, **common)
        pack_b = callbacks["assemble_context"](project_id=b, **common)
        self.assertEqual([i["id"] for i in pack_a["items"]], [first["id"]])
        self.assertEqual([i["id"] for i in pack_b["items"]], [other["id"]])
        off = callbacks["assemble_context"](project_id=None, **common)
        self.assertFalse(off["items"])
        excluded = callbacks["assemble_context"](project_id=a,
            excluded_context_ids=[first["id"]], **common)
        self.assertFalse(excluded["items"])
        pinned = callbacks["assemble_context"](query="unrelated", project_id=a, use_memory=False,
            purpose="refinement", pinned_context_ids=[first["id"]])
        self.assertEqual(pinned["items"][0]["reason"], "pinned_by_user")
        with self.assertRaisesRegex(ValueError, "pinned_context_unavailable"):
            callbacks["assemble_context"](project_id=a, pinned_context_ids=[other["id"]], **common)

    def test_bridge_memory_create_edit_cas_forget_and_retry(self):
        payload = {"text": "Prefer concise reports.", "kind": "preference",
                   "scope_kind": "personal", "scope_id": None, "operation_token": "remember:1"}
        first = self.call("memories.remember", payload)
        self.assertEqual(first["status"], "success", first)
        self.assertEqual(first, self.call("memories.remember", payload))
        memory = first["result"]["memory"]
        self.assertTrue(memory["updated_at"].endswith(("-04:00", "-05:00")))
        changed = self.call("memories.update", {"memory_id": memory["id"],
            "expected_revision": 1, "changes": {"text": "Prefer detailed reports."}})
        self.assertEqual(changed["status"], "success", changed)
        stale = self.call("memories.forget", {"memory_id": memory["id"], "expected_revision": 1})
        self.assertEqual(stale["status"], "stale", stale)
        removed = self.call("memories.forget", {"memory_id": memory["id"], "expected_revision": 2})
        self.assertEqual(removed["status"], "success", removed)
        pending = self.call("memories.search", {"query": "reports", "limit": 100})
        self.assertEqual(pending["status"], "success", pending)
        done = self.finish(pending["result"]["job_id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["result"]["memories"], [])

    def test_context_preview_job_revokes_cached_result(self):
        project_id = self.project("Project")
        memory = self.memory.remember("The encoder is serial.", project_id=project_id)
        pending = self.call("context.preview", {"query": "encoder", "project_id": project_id,
            "use_memory": False, "pinned_context_ids": [memory["id"]]})
        self.assertEqual(pending["status"], "success", pending)
        done = self.finish(pending["result"]["job_id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["result"]["items"][0]["id"], memory["id"])
        self.memory.forget(memory["id"])
        revoked = self.service.read_job(done["job_id"])
        self.assertEqual(revoked["error"], "context_revoked")
        self.assertIsNone(revoked["result"])

    def test_copy_uses_existing_native_coordinator(self):
        session = self.service.create_session("A synthetic prompt.", "copy:session")
        result = self.call("prompt_sessions.copy", {"session_id": session["id"], "expected_revision": 1})
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(self.clipboard, ["A synthetic prompt."])

    def test_real_eligible_observations_suggest_and_revoke(self):
        project_id = self.project("Project")
        self.memory.set_learning(True)
        first = self.memory.add_source("Write a bug report from these debugging notes.",
            project_id=project_id, independent_key="episode:1")
        self.memory.add_source("Write a bug report from these debugging notes.",
            project_id=project_id, independent_key="episode:1")
        self.assertFalse(any(s["personalized"] for s in self.service.suggestions.refresh(project_id)))
        second = self.memory.add_source("Make this crash report reproducible.",
            project_id=project_id, independent_key="episode:2")
        self.memory.add_source("A quoted bug report from someone else.",
            project_id=project_id, quoted=True)
        patterns = self.service.patterns(project_id)
        self.assertEqual(len(patterns), 2)
        self.assertIn(second, {p["source_id"] for p in patterns})
        candidates = self.service.suggestions.refresh(project_id)
        self.assertEqual(candidates[0]["category"], "bug_report")
        self.assertTrue(candidates[0]["personalized"])
        self.memory.expire_source(candidates[0]["evidence"][0]["source_id"])
        self.assertFalse(any(s["personalized"] for s in self.service.suggestions.list(project_id)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
