"""Synthetic official-API responses: pagination, normalization, and key safety."""

from copy import deepcopy
import io
import json
from unittest import TestCase, main
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from aa_api import API_ENDPOINTS, APIError, fetch_models, normalize_api_models


def model(number=1, **changes):
    result = {
        "id": f"synthetic-{number}",
        "slug": f"synthetic-model-{number}",
        "name": f"Synthetic model {number}",
        "release_date": "2026-06-15",
        "model_creator": {"id": "synthetic-creator", "name": "Example Lab"},
        "evaluations": {"artificial_analysis_intelligence_index": 42.5},
        "artificial_analysis_intelligence_index_cost": {
            "total_cost": 300,
            "cost_per_task": {"total_cost": 0.0372},
        },
        "pricing": {"price_1m_input_tokens": 1, "price_1m_output_tokens": 2},
    }
    result.update(changes)
    return result


def page(models=None, *, current=1, total=1, version=4.3, tier="free"):
    return {
        "tier": tier,
        "intelligence_index_version": version,
        "pagination": {"page": current, "page_size": 100, "total_pages": total, "has_more": current < total},
        "data": [model()] if models is None else models,
        "future_server_field": "ignored",
    }


def response(payload):
    content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    result = io.BytesIO(content)
    result.status = 200
    return result


class FetchTests(TestCase):
    def test_fetches_all_pages_and_records_provenance_without_key(self):
        opener = Mock(side_effect=[response(page(current=1, total=2)), response(page([model(2)], current=2, total=2))])
        progress = Mock()
        result = fetch_models("synthetic-secret-do-not-log", opener=opener, progress=progress)
        self.assertEqual([m["id"] for m in result["data"]], ["synthetic-1", "synthetic-2"])
        self.assertEqual(result["metadata"]["pages_fetched"], 2)
        self.assertEqual(result["intelligence_index_version"], 4.3)
        self.assertEqual(result["metadata"]["endpoint"], API_ENDPOINTS["free"])
        self.assertNotIn("synthetic-secret-do-not-log", json.dumps(result))
        self.assertEqual(opener.call_args_list[1].args[0].full_url, API_ENDPOINTS["free"] + "?page=2")
        self.assertEqual(opener.call_args_list[0].args[0].get_header("X-api-key"), "synthetic-secret-do-not-log")
        self.assertEqual(progress.call_count, 2)

    def test_pro_is_explicit_without_free_fallback(self):
        opener = Mock(return_value=response(page(tier="pro")))
        self.assertEqual(fetch_models("example", tier="pro", opener=opener)["requested_tier"], "pro")
        self.assertTrue(opener.call_args.args[0].full_url.startswith(API_ENDPOINTS["pro"] + "?"))

    def test_paid_key_can_return_paid_tier_from_free_endpoint(self):
        self.assertEqual(fetch_models("example", opener=Mock(return_value=response(page(tier="commercial"))))["tier"], "commercial")

    def test_missing_key_and_invalid_tier_fail_before_network(self):
        opener = Mock()
        for key, tier in [("", "free"), ("  ", "free"), ("bad\nkey", "free"), ("bad key", "free"), ("bad\u2603key", "free"), ("example", "unknown")]:
            with self.subTest(tier=tier), self.assertRaises(APIError):
                fetch_models(key, tier=tier, opener=opener)
        opener.assert_not_called()

    def test_index_version_and_pagination_cannot_change_mid_download(self):
        mutations = [
            {"intelligence_index_version": 5},
            {"tier": "pro"},
            {"pagination": {"page": 2, "page_size": 50, "total_pages": 2, "has_more": False}},
            {"pagination": {"page": 2, "page_size": 100, "total_pages": 3, "has_more": True}},
        ]
        for mutation in mutations:
            next_page = page([model(2)], current=2, total=2)
            next_page.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(APIError):
                fetch_models("example", opener=Mock(side_effect=[response(page(total=2)), response(next_page)]))

    def test_duplicate_ids_or_slugs_reject_whole_download(self):
        for duplicate in [model(2, id="synthetic-1"), model(2, slug="synthetic-model-1")]:
            with self.subTest(duplicate=duplicate), self.assertRaisesRegex(APIError, "duplicate"):
                fetch_models("example", opener=Mock(side_effect=[response(page(total=2)), response(page([duplicate], current=2, total=2))]))

    def test_invalid_pagination_is_bounded(self):
        mutations = [
            {"page": 2}, {"page": True}, {"page_size": 0}, {"total_pages": 101},
            {"total_pages": -1}, {"has_more": True}, {"has_more": "false"},
        ]
        for mutation in mutations:
            payload = page()
            payload["pagination"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(APIError):
                fetch_models("example", opener=Mock(return_value=response(payload)))

    def test_empty_single_page_response_is_preserved_for_caller(self):
        for total in [0, 1]:
            self.assertEqual(fetch_models("example", opener=Mock(return_value=response(page([], total=total))))["data"], [])

    def test_empty_intermediate_page_fails(self):
        with self.assertRaisesRegex(APIError, "empty page"):
            fetch_models("example", opener=Mock(return_value=response(page([], total=2))))

    def test_malformed_response_or_version_fails(self):
        for payload in [[], {}, page(version=True), page(version="4.3"), page(version=float("nan")), page([{}])]:
            with self.subTest(payload=payload), self.assertRaises(APIError):
                fetch_models("example", opener=Mock(return_value=response(payload)))
        with self.assertRaisesRegex(APIError, "invalid JSON"):
            fetch_models("example", opener=Mock(return_value=response(b"not-json")))

    def test_http_errors_are_useful_and_never_echo_key_or_body(self):
        for status, expected in [(401, "key"), (403, "permissions"), (429, "rate limit"), (500, "HTTP 500")]:
            secret = "synthetic-sensitive-value"
            problem = HTTPError("https://example.invalid/" + secret, status, secret, {}, io.BytesIO(secret.encode()))
            with self.subTest(status=status), self.assertRaises(APIError) as caught:
                fetch_models(secret, opener=Mock(side_effect=problem))
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn(secret, str(caught.exception))

    def test_timeout_and_connection_errors_do_not_echo_exception(self):
        for problem, expected in [(TimeoutError("synthetic-sensitive-value"), "timed out"), (URLError("synthetic-sensitive-value"), "connect")]:
            with self.subTest(problem=type(problem)), self.assertRaises(APIError) as caught:
                fetch_models("synthetic-sensitive-value", opener=Mock(side_effect=problem))
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("synthetic-sensitive-value", str(caught.exception))


class NormalizeTests(TestCase):
    def test_exact_task_cost_path_and_country_registry(self):
        records, audit = normalize_api_models(page(), {"example lab": "US"})
        record = records[0]
        self.assertEqual(record["cost_per_task"], 0.0372)
        self.assertEqual(record["country"], "us")
        self.assertEqual(record["country_source"], "registry")
        self.assertIsNone(record["estimated"])
        self.assertEqual(record["source_score_status"], "api_published")
        self.assertEqual(audit["unknown_score_status"], 1)

    def test_api_country_precedes_registry(self):
        records, _ = normalize_api_models(page([model(model_creator={"name": "Example Lab", "country": "CN"})]), {"Example Lab": "us"})
        self.assertEqual(records[0]["country"], "cn")
        self.assertEqual(records[0]["country_source"], "api_metadata")

    def test_unknown_country_is_never_guessed(self):
        records, audit = normalize_api_models(page())
        self.assertIsNone(records[0]["country"])
        self.assertEqual(records[0]["country_source"], "unknown")
        self.assertEqual(audit["unknown_creators"], ["Example Lab"])

    def test_missing_task_cost_never_uses_total_or_token_prices(self):
        for cost in [None, {"total_cost": 1000}, {"total_cost": 1000, "cost_per_task": None}]:
            with self.subTest(cost=cost):
                records, audit = normalize_api_models(page([model(artificial_analysis_intelligence_index_cost=cost)]))
                self.assertIsNone(records[0]["cost_per_task"])
                self.assertEqual(audit["missing_cost"], 1)

    def test_zero_cost_retained_and_audited_not_treated_as_positive(self):
        records, audit = normalize_api_models(page([model(artificial_analysis_intelligence_index_cost={"cost_per_task": {"total_cost": 0}})]))
        self.assertEqual(records[0]["cost_per_task"], 0)
        self.assertEqual(audit["zero_cost"], 1)
        self.assertEqual(audit["with_positive_cost"], 0)

    def test_null_missingness_and_future_fields_are_preserved_safely(self):
        missing = model(release_date=None, model_creator=None, evaluations={}, reasoning_model=False, future_field="unused")
        records, audit = normalize_api_models(page([missing]))
        self.assertIsNone(records[0]["intelligence"])
        self.assertIsNone(records[0]["release_date"])
        self.assertFalse(records[0]["reasoning"])
        self.assertEqual(audit["missing_score"], 1)
        self.assertEqual(audit["missing_release_date"], 1)
        self.assertEqual(audit["unknown_creators"], ["(missing creator)"])

    def test_invalid_scores_costs_and_dates_fail(self):
        for value in [float("nan"), float("inf"), -1, "42", True]:
            for changes in [
                {"evaluations": {"artificial_analysis_intelligence_index": value}},
                {"artificial_analysis_intelligence_index_cost": {"cost_per_task": {"total_cost": value}}},
            ]:
                with self.subTest(value=value, changes=changes), self.assertRaises(APIError):
                    normalize_api_models(page([model(**changes)]))
        for release_date in ["2026-02-30", "20260615", "2026-06", 123]:
            with self.subTest(release_date=release_date), self.assertRaises(APIError):
                normalize_api_models(page([model(release_date=release_date)]))

    def test_country_registry_rejects_bad_or_conflicting_entries(self):
        for registry in [{"Example Lab": "USA"}, {"": "us"}, {"Lab": "us", "LAB": "cn"}]:
            with self.subTest(registry=registry), self.assertRaises(APIError):
                normalize_api_models(page(), registry)

    def test_normalization_does_not_mutate_input_or_registry(self):
        payload = page()
        original = deepcopy(payload)
        registry = {"Example Lab": "US"}
        normalize_api_models(payload, registry)
        self.assertEqual(payload, original)
        self.assertEqual(registry, {"Example Lab": "US"})


if __name__ == "__main__":
    main()
