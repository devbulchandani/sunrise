"""LLM urgency calibration benchmark.

Replays recent analyzed events through one or two models and reports:
  - self-consistency: |fresh score - stored score| stats for the primary model
  - distribution: how many events land in each alert bucket (61 = push floor)
  - cross-model A/B (optional): pairwise urgency deltas between two models

Usage (from backend/, with the root .env loaded):
  python -m app.calibrate --limit 20
  python -m app.calibrate --limit 20 --compare-model google/gemini-2.5-flash \
      --compare-base-url https://openrouter.ai/api/v1 --compare-key-env OPENROUTER_API_KEY
"""

import argparse
import asyncio
import os
import statistics

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import get_session_factory
from app.llm.client import LLMError, get_llm
from app.llm.schemas import MarketAnalysis
from app.models.models import MarketEvent
from app.services.analysis.analyzer import SYSTEM_PROMPT, _build_user_prompt

setup_logging()

BUCKETS = [(0, 20, "LOW"), (21, 40, "MODERATE"), (41, 60, "RELEVANT"),
           (61, 80, "HIGH"), (81, 100, "CRITICAL")]


def bucket(score: int) -> str:
    for lo, hi, name in BUCKETS:
        if lo <= score <= hi:
            return name
    return "?"


async def _score_events(limit: int) -> list[dict]:
    """Fetch recent DONE events and their articles for replay."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(MarketEvent)
            .where(MarketEvent.analysis_status == "DONE")
            .order_by(MarketEvent.last_updated_at.desc())
            .limit(limit)
        )
        events = list(result.scalars().all())
        out = []
        for ev in events:
            arts = list(ev.articles)[:5]
            if not arts:
                continue
            out.append({
                "id": ev.id,
                "headline": ev.headline,
                "stored_urgency": ev.urgency,
                "category": ev.category,
                "prompt": _build_user_prompt(
                    ev, arts, [a.source.name if a.source else "unknown" for a in arts]
                ),
            })
    return out


async def run_model(label: str, model: str | None, base_url: str | None,
                    api_key: str | None, samples: list[dict]) -> dict[int, int]:
    s = get_settings()
    saved = (s.llm_model, s.llm_base_url, s.llm_api_key)
    try:
        s.llm_model = model or s.llm_model
        if base_url is not None:
            s.llm_base_url = base_url
        if api_key is not None:
            s.llm_api_key = api_key
        llm = get_llm()
        scores: dict[int, int] = {}
        for i, sample in enumerate(samples):
            try:
                analysis = await llm.structured(
                    MarketAnalysis, SYSTEM_PROMPT, sample["prompt"], max_tokens=2000
                )
                scores[sample["id"]] = analysis.urgency
                print(f"  [{label}] {i + 1}/{len(samples)} ev{sample['id']}"
                      f" ai_urgency={analysis.urgency}")
            except LLMError as exc:
                print(f"  [{label}] {i + 1}/{len(samples)} ev{sample['id']} FAILED: {str(exc)[:100]}")
        return scores
    finally:
        s.llm_model, s.llm_base_url, s.llm_api_key = saved


def report(label: str, scores: dict[int, int], samples: list[dict]) -> None:
    stored = {s["id"]: s["stored_urgency"] for s in samples}
    diffs = [abs(scores[eid] - stored[eid]) for eid in scores]
    print(f"\n=== {label} ===")
    print(f"scored: {len(scores)}/{len(samples)}")
    if diffs:
        print(f"self-consistency vs stored blended urgency: "
              f"mean_abs_diff={statistics.mean(diffs):.1f} "
              f"median={statistics.median(diffs):.0f} max={max(diffs)}")
    dist: dict[str, int] = {}
    for eid, sc in scores.items():
        dist[bucket(sc)] = dist.get(bucket(sc), 0) + 1
    print("distribution:", dict(sorted(dist.items(), key=lambda kv: -kv[1])))
    over_floor = sum(1 for sc in scores.values() if sc >= 61)
    print(f"above Telegram push floor (61): {over_floor}/{len(scores)}"
          f" ({(over_floor / len(scores) * 100):.0f}%)" if scores else "")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--compare-model", default=None)
    parser.add_argument("--compare-base-url", default=None)
    parser.add_argument("--compare-key-env", default=None,
                        help="env var holding the comparison model's API key")
    args = parser.parse_args()

    samples = await _score_events(args.limit)
    if not samples:
        print("no DONE events with articles found")
        return
    print(f"replaying {len(samples)} recent DONE events\n")

    primary = await run_model("primary:" + get_settings().llm_model, None, None, None, samples)
    report("primary:" + get_settings().llm_model, primary, samples)

    if args.compare_model:
        key = os.environ.get(args.compare_key_env, "") if args.compare_key_env else None
        secondary = await run_model(
            f"compare:{args.compare_model}", args.compare_model,
            args.compare_base_url, key or None, samples,
        )
        report(f"compare:{args.compare_model}", secondary, samples)

        shared = sorted(set(primary) & set(secondary))
        if shared:
            deltas = [secondary[eid] - primary[eid] for eid in shared]
            print(f"\n=== A/B: {args.compare_model} vs {get_settings().llm_model} ===")
            print(f"pairwise mean delta={statistics.mean(deltas):+.1f} "
                  f"(positive => compare model scores HIGHER)")
            flips = sum(
                1 for eid in shared
                if bucket(primary[eid]) != bucket(secondary[eid])
            )
            print(f"bucket changes across models: {flips}/{len(shared)}")


if __name__ == "__main__":
    asyncio.run(main())
