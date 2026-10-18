"""Preserve AA's public bulk snapshot and prepare analysis records without imputation."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def normalize(model):
    creator = model.get("creator") or {}
    cost = ((model.get("intelligenceIndexCostPerTask") or {}).get("cost") or {}).get("total")
    return {
        "id": model.get("id"),
        "slug": model["slug"],
        "name": model.get("name"),
        "creator": creator.get("name"),
        "country": creator.get("country"),
        "release_date": model.get("releaseDate"),
        "release_date_precision": "AA supplied date; original announcement precision not independently audited",
        "intelligence": model.get("intelligenceIndex"),
        "estimated": model.get("intelligenceIndexIsEstimated"),
        "cost_per_task": cost,
        "blended_price": model.get("price1mBlended7To2To1"),
        "input_price_per_million": model.get("price1mInputTokens"),
        "output_price_per_million": model.get("price1mOutputTokens"),
        "cache_hit_price_per_million": model.get("cacheHitPrice"),
        "deprecated": model.get("deprecated"),
        "open_weights": model.get("isOpenWeights"),
        "reasoning": model.get("isReasoning"),
        "effort": model.get("effort"),
        "hosting_basis": model.get("performanceDataSource"),
        "source_url": "https://artificialanalysis.ai/models/" + model["slug"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="aa-bulk-public.json")
    parser.add_argument("--output", default="data/models-2026-10-07.json")
    args = parser.parse_args()
    raw = Path(args.input).read_bytes()
    payload = json.loads(raw)
    models = [normalize(m) for m in payload["models"]]
    assert len({m["slug"] for m in models}) == len(models), "Duplicate model slugs"
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "as_of_local_date": "2026-10-07",
        "timezone": "Asia/Saigon",
        "source": "Artificial Analysis",
        "source_url": "https://artificialanalysis.ai/models/",
        "intelligence_index_version": "4.3.2",
        "version_source": "https://artificialanalysis.ai/methodology/intelligence-benchmarking",
        "price_basis": "Current snapshot cost per Intelligence Index task, USD; not historical prices",
        "blended_price_basis": "USD per million tokens, 7 cache : 2 input : 1 output, source field retained only",
        "date_basis": "Cumulative AA release dates. Historical availability and withdrawal dates unavailable.",
        "source_payload_sha256": hashlib.sha256(raw).hexdigest(),
        "source_payload_file": str(Path(args.input)),
        "model_count": len(models),
        "country_counts": dict(collections.Counter(m["country"] or "unknown" for m in models)),
        "normalization": "Source values copied, missing values retained as null, no score/cost estimates invented.",
    }
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
