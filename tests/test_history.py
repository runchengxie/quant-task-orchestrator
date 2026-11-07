import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.history import install_history, search_history
from quant_task_orchestrator.store import Store


def projection():
    records = []
    for index, classification in enumerate(("operational_failure", "research_conclusion")):
        records.append(
            {
                "record_id": str(index) * 64,
                "source_kind": "campaign",
                "status": "BLOCKED" if index == 0 else "DISCARDED",
                "stage": None,
                "decision": None if index == 0 else "DISCARDED",
                "classification": classification,
                "evidence_stage": "not_verified" if index == 0 else "owner_recorded",
                "provenance": {
                    "source_revision": "a" * 40,
                    "source_database_sha256": "b" * 64,
                    "annotations_sha256": None,
                    "owner_source_revision": None,
                    "dataset_fingerprint_sha256": None,
                },
                "evidence_handles": [],
                "topic_tags": ["synthetic"],
                "reason_codes": [],
                "revisit_conditions": [],
            }
        )
    return {
        "schema": "quant.research_history.v1",
        "owner": "quant-research",
        "source_revision": "a" * 40,
        "source_id": "synthetic",
        "records": records,
    }


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "consumer.sqlite")
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS research_history_snapshots(snapshot_sha256 TEXT PRIMARY KEY,source_revision TEXT NOT NULL,payload TEXT NOT NULL)"
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def install(self, value):
        raw = json.dumps(value).encode()
        path = self.root / "owner.json"
        path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        return install_history(self.store, path, sha), sha

    def test_pinned_import_search_pagination_and_readonly(self):
        receipt, sha = self.install(projection())
        self.assertEqual(receipt["record_count"], 2)
        page = search_history(self.store, snapshot_sha256=sha, limit=1)
        self.assertEqual(page["next_offset"], 1)
        self.assertEqual(len(search_history(self.store, offset=1)["records"]), 1)
        self.assertEqual(
            search_history(self.store, classification="research_conclusion")["records"][0][
                "decision"
            ],
            "DISCARDED",
        )
        self.assertEqual(search_history(self.store, topic_tags="synthetic")["total"], 2)
        self.assertEqual(search_history(self.store, q="BLOCKED")["total"], 1)
        with Store(self.store.path, readonly=True) as reader:
            self.assertEqual(search_history(reader)["total"], 2)
            with self.assertRaisesRegex(ValueError, "READ_ONLY"):
                install_history(reader, self.root / "owner.json", sha)
        self.assertEqual(
            self.store.db.execute("SELECT count(*) FROM research_history_snapshots").fetchone()[0],
            1,
        )

    def test_reject_unpinned_private_or_malformed(self):
        self.install(projection())
        with self.assertRaisesRegex(ValueError, "DIGEST"):
            install_history(self.store, self.root / "owner.json", "0" * 64)
        for mutate in (
            lambda value: value.update(owner="other"),
            lambda value: value["records"][0].update(hypothesis="private"),
            lambda value: value["records"][0]["evidence_handles"].append("/private/path"),
            lambda value: value["records"][0]["topic_tags"].append("uncontrolled prose"),
            lambda value: value["records"].append(copy.deepcopy(value["records"][0])),
        ):
            value = projection()
            mutate(value)
            with self.assertRaises(ValueError):
                self.install(value)
        self.assertEqual(search_history(self.store)["total"], 2)

    def test_typed_filters_and_empty_history(self):
        self.assertEqual(search_history(self.store)["total"], 0)
        for kwargs in (
            {"limit": True},
            {"limit": 101},
            {"offset": -1},
            {"unknown": "x"},
            {"q": None},
            {"status": []},
        ):
            with self.assertRaises(ValueError):
                search_history(self.store, **kwargs)

    def test_strict_json_and_enum_types(self):
        self.install(projection())
        raw = (json.dumps(projection())[:-1] + ',"owner":"quant-research"}').encode()
        path = self.root / "ambiguous.json"
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            install_history(self.store, path, hashlib.sha256(raw).hexdigest())
        for field in ("source_kind", "classification", "evidence_stage"):
            value = projection()
            value["records"][0][field] = []
            with self.assertRaises(ValueError):
                self.install(value)
        value = projection()
        value["records"][0]["evidence_handles"] = ["artifact://sha256/" + "b" * 64] * 1001
        with self.assertRaises(ValueError):
            self.install(value)
        raw = json.dumps(projection()).replace('"stage": null', '"stage": NaN').encode()
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "CONSTANT"):
            install_history(self.store, path, hashlib.sha256(raw).hexdigest())

    def test_legacy_readonly_store_is_empty(self):
        self.store.db.execute("DROP TABLE research_history_snapshots")
        self.store.db.commit()
        with Store(self.store.path, readonly=True) as reader:
            self.assertEqual(search_history(reader)["total"], 0)
        self.assertFalse(
            self.store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='research_history_snapshots'"
            ).fetchone()
        )

    def test_corrupted_cached_projection_fails_its_pin(self):
        self.install(projection())
        self.store.db.execute("UPDATE research_history_snapshots SET payload=payload || ' '")
        self.store.db.commit()
        with self.assertRaisesRegex(ValueError, "DIGEST"):
            search_history(self.store)
