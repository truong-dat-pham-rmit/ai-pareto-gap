"""Check that the maintainer publishes aggregate analysis, never source records."""

from datetime import date
import json
import unittest

from publish_snapshot import build_public_snapshot


def source_payload(tier="pro"):
    return {"tier": tier, "intelligence_index_version": 4.4,
            "metadata": {"fetched_at_utc": "2026-10-18T01:00:00+00:00"},
            "data": [
                {"id": "private-us", "slug": "PRIVATE_US_MODEL", "name": "PRIVATE_US_MODEL",
                 "release_date": "2026-03-01", "model_creator": {"name": "PRIVATE_US_CREATOR", "country": "us"},
                 "evaluations": {"artificial_analysis_intelligence_index": 40},
                 "artificial_analysis_intelligence_index_cost": {"cost_per_task": {"total_cost": .1}}},
                {"id": "private-cn", "slug": "PRIVATE_CN_MODEL", "name": "PRIVATE_CN_MODEL",
                 "release_date": "2026-03-01", "model_creator": {"name": "PRIVATE_CN_CREATOR", "country": "cn"},
                 "evaluations": {"artificial_analysis_intelligence_index": 38},
                 "artificial_analysis_intelligence_index_cost": {"cost_per_task": {"total_cost": .1}}},
            ]}


class PublisherTests(unittest.TestCase):
    def test_only_country_aggregates_are_exported(self):
        report = build_public_snapshot(source_payload(), {"version": "test", "countries": {}}, date(2026, 10, 18))
        text = json.dumps(report)
        for forbidden in ("PRIVATE_US_MODEL", "PRIVATE_CN_MODEL", "PRIVATE_US_CREATOR", "private-us", "cost_per_task", "latest_frontiers"):
            self.assertNotIn(forbidden, text)
        self.assertEqual(report["metadata"]["refresh_status"], "published_snapshot")
        self.assertEqual(report["metadata"]["snapshot_date"], "2026-10-18")
        self.assertEqual(report["metadata"]["intelligence_index_version"], "4.4")
        self.assertTrue(all(s["score_policy"] == "api_published" for s in report["scenarios"]))

    def test_free_key_is_not_treated_as_external_publication_access(self):
        with self.assertRaisesRegex(ValueError, "Free key"):
            build_public_snapshot(source_payload("free"), {"version": "test", "countries": {}}, date(2026, 10, 18))


if __name__ == "__main__":
    unittest.main()
