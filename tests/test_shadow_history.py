import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quant_task_orchestrator.shadow_history import MAX_BYTES, summarize_shadows

SHA = "a" * 64


class ShadowHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, number=1, **updates):
        name = f"{number:032x}"
        directory = self.root / name
        directory.mkdir()
        value = dict(
            schema="quant.data_shadow.v1",
            run_id=name,
            config_sha256=SHA,
            status="SUCCEEDED",
            shadow_only=True,
            production_schedule_changed=False,
            qualified_research_ready=False,
            promotion_authorized=False,
            new_model_calls=0,
            steps=[{"private": "/secret/raw/path"}],
        )
        value.update(updates)
        path = directory / "assessment.json"
        path.write_text(json.dumps(value))
        return path

    def summary(self, **kw):
        return summarize_shadows(self.root, SHA, **kw)

    def test_legacy_is_unknown_and_redacted(self):
        self.put()
        result = self.summary()
        self.assertEqual(result["unknown_timestamp_assessments"], 1)
        self.assertEqual(result["observation_window"], "insufficient")
        self.assertIsNone(result["observed_span_seconds"])
        self.assertNotIn("/secret", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_rapid_repeats_not_daily_stability(self):
        now = datetime.now(UTC) - timedelta(hours=1)
        for number in range(1, 9):
            self.put(
                number,
                observed_at=(now + timedelta(seconds=number)).isoformat(),
                duration_seconds=0.2,
            )
        result = self.summary()
        self.assertEqual(result["matched_assessments"], 8)
        self.assertEqual(result["distinct_utc_dates"], 1)
        self.assertEqual(result["observed_span_seconds"], 7)
        self.assertEqual(result["measured_latency"]["samples"], 8)
        self.assertEqual(result["observation_window"], "insufficient")

    def test_week_window_and_failure(self):
        now = datetime.now(UTC) - timedelta(days=10)
        for number in range(1, 9):
            self.put(number, observed_at=(now + timedelta(days=number)).isoformat())
        self.assertEqual(self.summary()["observation_window"], "sufficient")
        self.put(9, status="FAILED", observed_at=now.isoformat())
        result = self.summary()
        self.assertEqual(result["failed_assessments"], 1)
        self.assertEqual(result["observation_window"], "insufficient")
        self.assertFalse(result["promotion_authorized"])

    def test_exact_pin(self):
        self.put(config_sha256="b" * 64, status="FAILED")
        result = self.summary()
        self.assertEqual(result["matched_assessments"], 0)
        self.assertEqual(result["other_config_assessments"], 1)
        self.assertEqual(result["observation_window"], "insufficient")

    def test_invalid_records(self):
        bad = [
            dict(run_id="../other"),
            dict(config_sha256="bad"),
            dict(status="success"),
            dict(observed_at="2026-01-01"),
            dict(observed_at="not a date"),
            dict(observed_at="9999-01-01T00:00:00Z"),
            dict(duration_seconds=-1),
            dict(duration_seconds=True),
            dict(duration_seconds=10**400),
            dict(duration_seconds=31 * 86400 + 1),
            dict(promotion_authorized=True),
            dict(new_model_calls=False),
        ]
        for index, updates in enumerate(bad, 1):
            self.put(index, **updates)
        result = self.summary()
        self.assertEqual(result["errors"]["INVALID_OR_UNREADABLE_ASSESSMENT"], len(bad))
        self.assertEqual(result["matched_assessments"], 0)

    def test_malformed_duplicate_nonfinite_and_oversize(self):
        bodies = [
            "{",
            '{"schema":1,"schema":2}',
            '{"duration_seconds":NaN}',
            '{"steps":[1e999]}',
            " " * (MAX_BYTES + 1),
        ]
        for index, body in enumerate(bodies, 1):
            self.put(index).write_text(body)
        self.assertEqual(self.summary()["errors"]["INVALID_OR_UNREADABLE_ASSESSMENT"], 5)

    def test_symlink_file_directory_and_root(self):
        target = self.put()
        second = self.root / f"{2:032x}"
        second.mkdir()
        (second / "assessment.json").symlink_to(target)
        (self.root / f"{3:032x}").symlink_to(target.parent, target_is_directory=True)
        self.assertEqual(self.summary()["errors"]["INVALID_OR_UNREADABLE_ASSESSMENT"], 2)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertIn("ROOT_UNAVAILABLE_OR_UNSAFE", summarize_shadows(alias, SHA)["errors"])

    def test_limit_missing_and_argument_guards(self):
        self.put(1)
        self.put(2)
        result = self.summary(limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["entries_scanned"], 1)
        self.assertEqual(result["assessment_integrity"], "invalid")
        self.assertIn(
            "ROOT_UNAVAILABLE_OR_UNSAFE", summarize_shadows(self.root / "missing", SHA)["errors"]
        )
        for limit in [0, -1, True, 1001, "2"]:
            with self.assertRaises(ValueError):
                self.summary(limit=limit)
        with self.assertRaises(ValueError):
            summarize_shadows(self.root, "../sha")

    def test_unknown_entries_are_not_silently_skipped(self):
        (self.root / "notes").write_text("private")
        self.assertEqual(self.summary()["errors"]["INVALID_OR_UNREADABLE_ASSESSMENT"], 1)


if __name__ == "__main__":
    unittest.main()
