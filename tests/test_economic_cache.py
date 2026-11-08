"""Cached economic envelopes retain exact file pins and never execute Owners."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from test_economic_results import receipt

from quant_task_orchestrator.economic_cache import compare_cached, import_result, list_results
from quant_task_orchestrator.store import Store


class EconomicCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = Store(self.root / "db.sqlite")
        self.addCleanup(self.store.close)

    def put(self, n=1):
        value = receipt()
        value["result_id"] = f"{n:064x}"
        path = self.root / f"{n}.json"
        path.write_text(json.dumps(value, indent=2))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return path, sha

    def test_import_idempotency_pagination_and_cached_comparison(self):
        a, sha = self.put()
        b, other = self.put(2)
        import_result(self.store, a, sha)
        import_result(self.store, a, sha)
        import_result(self.store, b, other)
        a.unlink()
        b.unlink()
        result = list_results(self.store, limit=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["next_offset"], 1)
        self.assertNotIn(str(self.root), json.dumps(result))
        comparison = compare_cached(self.store, sha, other)
        self.assertEqual(comparison["status"], "comparable")
        self.assertFalse(comparison["provenance_verified"])
        self.assertEqual(comparison["input_pins"]["before_sha256"], sha)
        self.assertEqual(list_results(self.store, offset=2)["results"], [])

    def test_corrupt_payloads_and_invalid_pins_fail_closed(self):
        path, sha = self.put()
        import_result(self.store, path, sha)
        self.store.db.execute("UPDATE economic_result_snapshots SET payload=?", (b"{}",))
        self.store.db.commit()
        with self.assertRaises(ValueError):
            list_results(self.store)
        with self.assertRaises(ValueError):
            import_result(self.store, path, sha)
        with self.assertRaises(ValueError):
            compare_cached(self.store, "wrong", sha)
        with self.assertRaises(ValueError):
            list_results(self.store, limit=True)

    def test_readonly_old_database_returns_empty_without_migration(self):
        old = self.root / "old.sqlite"
        with closing(sqlite3.connect(old)) as db:
            db.execute("CREATE TABLE old(value TEXT)")
        with Store(old, readonly=True) as store:
            self.assertEqual(list_results(store)["total"], 0)
            self.assertFalse(
                store.db.execute(
                    "SELECT name FROM sqlite_master WHERE name='economic_result_snapshots'"
                ).fetchall()
            )
            path, sha = self.put()
            with self.assertRaises(ValueError):
                import_result(store, path, sha)
