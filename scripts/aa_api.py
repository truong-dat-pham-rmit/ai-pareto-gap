"""Download and normalize Artificial Analysis' documented language-model API.

Only the official API is used. API keys are never included in returned metadata
or error messages. The Free endpoint also works with Pro/Commercial keys.
"""

from collections import Counter
from datetime import date, datetime, timezone
import json
import math
import socket
from urllib import error as urllib_error
from urllib import request as urllib_request


API_ENDPOINTS = {
    "free": "https://artificialanalysis.ai/api/v2/language/models/free",
    "pro": "https://artificialanalysis.ai/api/v2/language/models",
}
MAX_PAGES = 100
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
TIMEOUT_SECONDS = 30


class APIError(RuntimeError):
    """A safe, user-readable API or schema error."""


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Never forward a credential to a redirect destination.
        return None


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _http_error(status):
    if status == 401:
        return APIError("AA rejected the API key (HTTP 401). Check your key in your AA account.")
    if status == 403:
        return APIError("AA denied access (HTTP 403). Check your key's permissions and selected API tier.")
    if status == 429:
        return APIError("AA's API rate limit was reached (HTTP 429). Wait before running again.")
    return APIError(f"AA's API returned HTTP {status}. Try again later or check your AA account.")


def fetch_models(api_key, *, tier="free", opener=None, progress=None):
    """Fetch every page from one API endpoint, validating a consistent snapshot.

    ``opener`` may be a urlopen-compatible callable for testing. No retries or
    automatic tier fallbacks are performed. ``progress`` receives plain text.
    """
    if tier not in API_ENDPOINTS:
        raise APIError("API tier must be 'free' or 'pro'.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise APIError("An AA API key is required. Create one in your Artificial Analysis account.")
    key = api_key.strip()
    if not key.isascii() or any(ord(character) < 33 or ord(character) > 126 for character in key):
        raise APIError("The AA API key contains invalid characters. Paste the key on one line without spaces.")
    open_request = opener or urllib_request.build_opener(_NoRedirect()).open
    endpoint = API_ENDPOINTS[tier]
    data = []
    seen_ids, seen_slugs = set(), set()
    expected_version = expected_tier = expected_pages = expected_page_size = None

    for page in range(1, MAX_PAGES + 1):
        if progress:
            progress(f"Fetching Artificial Analysis API page {page}.")
        request = urllib_request.Request(
            f"{endpoint}?page={page}",
            headers={"x-api-key": key, "Accept": "application/json", "User-Agent": "ai-pareto-gap/1"},
        )
        try:
            with open_request(request, timeout=TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
                if isinstance(status, int) and status >= 400:
                    raise _http_error(status)
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib_error.HTTPError as exc:
            raise _http_error(exc.code) from None
        except (TimeoutError, socket.timeout):
            raise APIError("The AA API request timed out. Check your connection and try again.") from None
        except urllib_error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise APIError("The AA API request timed out. Check your connection and try again.") from None
            raise APIError("Could not connect to the AA API. Check your internet connection and try again.") from None
        except OSError:
            raise APIError("Could not read the AA API response. Check your connection and try again.") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise APIError("AA returned an unexpectedly large API page; download stopped.")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            raise APIError("AA returned invalid JSON. Try again later.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise APIError("AA's response has an unsupported shape: expected a data list.")
        response_tier = payload.get("tier")
        if response_tier not in {"free", "pro", "commercial"}:
            raise APIError("AA's response is missing a valid API tier.")
        version = payload.get("intelligence_index_version")
        if not _number(version) or version <= 0:
            raise APIError("AA's response is missing a numeric Intelligence Index version.")
        pagination = payload.get("pagination")
        if not isinstance(pagination, dict):
            raise APIError("AA's response is missing pagination metadata.")
        current = pagination.get("page")
        page_size = pagination.get("page_size")
        total_pages = pagination.get("total_pages")
        has_more = pagination.get("has_more")
        if (
            not _integer(current) or current != page
            or not _integer(page_size) or page_size < 1
            or not _integer(total_pages) or not 0 <= total_pages <= MAX_PAGES
            or not isinstance(has_more, bool)
        ):
            raise APIError("AA returned invalid or excessive pagination metadata; download stopped.")
        if total_pages == 0:
            if page != 1 or payload["data"] or has_more:
                raise APIError("AA returned inconsistent empty pagination metadata.")
        elif current > total_pages or has_more != (current < total_pages):
            raise APIError("AA returned inconsistent pagination metadata.")
        if len(payload["data"]) > page_size:
            raise APIError("AA returned more models than its reported page size.")
        if page == 1:
            expected_version, expected_tier = version, response_tier
            expected_pages, expected_page_size = total_pages, page_size
        elif (version, response_tier, total_pages, page_size) != (
            expected_version, expected_tier, expected_pages, expected_page_size
        ):
            raise APIError("AA's index version or pagination changed during download. Run again for a consistent snapshot.")
        if not payload["data"] and total_pages > 1:
            raise APIError("AA returned an empty page inside a paginated result; download stopped.")
        for model in payload["data"]:
            if not isinstance(model, dict):
                raise APIError("AA returned a model that is not an object.")
            model_id, slug = model.get("id"), model.get("slug")
            if not isinstance(model_id, str) or not model_id.strip() or not isinstance(slug, str) or not slug.strip():
                raise APIError("AA returned a model without a valid ID and slug.")
            if model_id in seen_ids or slug in seen_slugs:
                raise APIError("AA returned duplicate model IDs or slugs. Run again for a consistent snapshot.")
            seen_ids.add(model_id)
            seen_slugs.add(slug)
            data.append(model)
        if not has_more:
            return {
                "requested_tier": tier,
                "tier": expected_tier,
                "intelligence_index_version": expected_version,
                "data": data,
                "metadata": {
                    "pages_fetched": page,
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "endpoint": endpoint,
                    "price_basis": "AA weighted average Intelligence Index cost per task, USD; API rounds to four decimal places.",
                },
            }
    raise APIError("AA exceeded the maximum permitted page count; download stopped.")


def _country(value):
    if isinstance(value, str) and len(value.strip()) == 2 and value.strip().isascii() and value.strip().isalpha():
        return value.strip().lower()
    return None


def normalize_api_models(payload, creator_countries=None):
    """Adapt API records to the analysis schema without inventing missing values.

    The Free API omits creator country and score-estimation status. An explicit
    creator-name registry can supply countries; it never overrides API metadata.
    Token prices are retained for context and never substitute for task costs.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise APIError("Expected an AA API payload with a data list.")
    registry = {}
    for name, value in (creator_countries or {}).items():
        code = _country(value)
        if not isinstance(name, str) or not name.strip() or code is None:
            raise APIError("Country registry entries must map creator names to two-letter country codes.")
        normalized_name = name.strip().casefold()
        if normalized_name in registry and registry[normalized_name] != code:
            raise APIError("Country registry contains conflicting creator-name entries.")
        registry[normalized_name] = code
    records = []
    seen_ids, seen_slugs = set(), set()
    unknown_creators = Counter()
    for model in payload["data"]:
        if not isinstance(model, dict):
            raise APIError("AA returned a model that is not an object.")
        model_id, slug = model.get("id"), model.get("slug")
        if not isinstance(model_id, str) or not model_id.strip() or not isinstance(slug, str) or not slug.strip():
            raise APIError("AA returned a model without a valid ID and slug.")
        if model_id in seen_ids or slug in seen_slugs:
            raise APIError("AA payload contains duplicate model IDs or slugs.")
        seen_ids.add(model_id)
        seen_slugs.add(slug)
        creator = model.get("model_creator") or {}
        if not isinstance(creator, dict):
            raise APIError("AA returned invalid model-creator metadata.")
        creator_name = creator.get("name")
        creator_name = creator_name if isinstance(creator_name, str) and creator_name.strip() else None
        country = _country(creator.get("country"))
        country_source = "api_metadata" if country else "unknown"
        if country is None and creator_name:
            country = registry.get(creator_name.strip().casefold())
            if country:
                country_source = "registry"
        if country is None:
            unknown_creators[creator_name or "(missing creator)"] += 1
        evaluations = model.get("evaluations") or {}
        cost = model.get("artificial_analysis_intelligence_index_cost") or {}
        pricing = model.get("pricing") or {}
        if not all(isinstance(item, dict) for item in (evaluations, cost, pricing)):
            raise APIError("AA returned invalid evaluation, cost, or pricing metadata.")
        per_task = cost.get("cost_per_task") or {}
        if not isinstance(per_task, dict):
            raise APIError("AA returned invalid cost-per-task metadata.")
        intelligence = evaluations.get("artificial_analysis_intelligence_index")
        task_cost = per_task.get("total_cost")
        if intelligence is not None and (not _number(intelligence) or intelligence < 0):
            raise APIError("AA returned an invalid Intelligence Index score.")
        if task_cost is not None and (not _number(task_cost) or task_cost < 0):
            raise APIError("AA returned an invalid cost per task.")
        release_date = model.get("release_date")
        if release_date is not None:
            try:
                if not isinstance(release_date, str) or date.fromisoformat(release_date).isoformat() != release_date:
                    raise ValueError
            except ValueError:
                raise APIError("AA returned an invalid model release date; expected YYYY-MM-DD.") from None
        records.append({
            "id": model_id,
            "slug": slug,
            "name": model.get("name"),
            "creator": creator_name,
            "country": country,
            "country_source": country_source,
            "release_date": release_date,
            "release_date_precision": "AA API supplied date; original announcement precision not independently audited",
            "intelligence": intelligence,
            "estimated": None,
            "source_score_status": "api_published",
            "cost_per_task": task_cost,
            "blended_price": pricing.get("price_1m_blended_7_to_2_to_1"),
            "input_price_per_million": pricing.get("price_1m_input_tokens"),
            "output_price_per_million": pricing.get("price_1m_output_tokens"),
            "cache_hit_price_per_million": pricing.get("price_1m_cache_hit_tokens"),
            "deprecated": None,
            "open_weights": None,
            "reasoning": model.get("reasoning_model"),
            "effort": None,
            "hosting_basis": None,
            "source_url": "https://artificialanalysis.ai/models/" + slug,
        })
    audit = {
        "total_models": len(records),
        "country_counts": dict(Counter(m["country"] or "unknown" for m in records)),
        "country_sources": dict(Counter(m["country_source"] for m in records)),
        "unknown_creators": sorted(unknown_creators),
        "unknown_creator_counts": dict(sorted(unknown_creators.items())),
        "with_score": sum(m["intelligence"] is not None for m in records),
        "with_positive_cost": sum(m["cost_per_task"] is not None and m["cost_per_task"] > 0 for m in records),
        "missing_release_date": sum(m["release_date"] is None for m in records),
        "missing_score": sum(m["intelligence"] is None for m in records),
        "missing_cost": sum(m["cost_per_task"] is None for m in records),
        "zero_cost": sum(m["cost_per_task"] == 0 for m in records),
        "unknown_score_status": len(records),
        "score_status_note": "The documented AA API does not expose an estimated-score flag; API-published scores retain estimated=null.",
    }
    return records, audit
