"""LLM spike: can a local model reliably turn a paragraph into a valid TravelerProfile?

    python -m ai.benchmark [--model llama3]        (or: make llm-spike)

Runs extract_profile over the hand-written descriptions in
fixtures/traveler-descriptions.json and writes docs/llm-spike.md and docs/llm-spike.json.
"Valid" means the profile passed contract validation within the retry budget. Each
description also lists what a correct profile must show (`expect`), so the report says how
often the profile was right, not only well formed.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ai.llm import DEFAULT_MODEL, LLM, LLMError, LLMUnavailable, OllamaLLM
from ai.profile import MAX_ATTEMPTS, ProfileExtractionError, extract_profile

REPO_ROOT = Path(__file__).resolve().parents[1]
DESCRIPTIONS = REPO_ROOT / "fixtures" / "traveler-descriptions.json"


def check_expectations(profile: dict[str, Any], expect: dict[str, Any]) -> list[tuple[str, bool]]:
    """(check, passed) for every expectation of one description."""
    interests = profile["interests"]
    checks: list[tuple[str, bool]] = []
    for name in expect.get("high", []):
        checks.append((f"{name} high", interests.get(name, 0) >= 0.7))
    for name in expect.get("low", []):
        checks.append((f"{name} low", interests.get(name, 1) <= 0.3))
    if "pace" in expect:
        wanted = expect["pace"]
        ok = profile["pace"] <= 0.4 if wanted == "relaxed" else profile["pace"] >= 0.6
        checks.append((f"pace {wanted}", ok))
    for term in expect.get("dietary", []):
        checks.append((f"dietary {term}", any(term in d for d in profile["dietary"])))
    if "dietary" not in expect:
        # Nobody in these descriptions states a diet without it being expected, so any
        # diet the model reports here is invented.
        checks.append(("no invented diet", not profile["dietary"]))
    if expect.get("accessibility"):
        checks.append(("accessibility", bool(profile["accessibility"])))
    for category in expect.get("avoid", []):
        checks.append((f"avoid {category}", category in profile["avoid"]))
    if "budget_total" in expect:
        want = expect["budget_total"]
        checks.append((f"budget {want}", abs(profile["budget"]["total"] - want) <= 0.05 * want))
    if "currency" in expect:
        want = expect["currency"]
        checks.append((f"currency {want}", profile["budget"]["currency"] == want))
    if "max_walk_at_most" in expect:
        limit = expect["max_walk_at_most"]
        checks.append((f"walk <= {limit}", profile["max_walk_minutes"] <= limit))
    if "max_walk_at_least" in expect:
        limit = expect["max_walk_at_least"]
        checks.append((f"walk >= {limit}", profile["max_walk_minutes"] >= limit))
    # Zero-padded HH:MM strings compare correctly as text.
    if "day_start_at_or_after" in expect:
        t = expect["day_start_at_or_after"]
        checks.append((f"start >= {t}", profile["day_start"] >= t))
    if "day_start_at_or_before" in expect:
        t = expect["day_start_at_or_before"]
        checks.append((f"start <= {t}", profile["day_start"] <= t))
    if "day_end_at_or_before" in expect:
        t = expect["day_end_at_or_before"]
        checks.append((f"end <= {t}", profile["day_end"] <= t))
    return checks


def run(llm: LLM, descriptions: list[dict[str, Any]], *, clock=time.perf_counter) -> list[dict]:
    """Extract a profile for every description. LLMUnavailable stops the run."""
    results = []
    for item in descriptions:
        started = clock()
        profile, attempts, error = None, MAX_ATTEMPTS, None
        try:
            extracted = extract_profile(item["text"], llm)
            profile, attempts = extracted.profile, extracted.attempts
        except ProfileExtractionError as exc:
            error = "; ".join(exc.errors)
        except LLMUnavailable:
            raise
        except LLMError as exc:
            error = str(exc)
        seconds = clock() - started
        checks = check_expectations(profile, item.get("expect", {})) if profile else []
        results.append(
            {
                "id": item["id"],
                "valid": profile is not None,
                "attempts": attempts,
                "seconds": round(seconds, 2),
                "checks_passed": sum(ok for _, ok in checks),
                "checks_total": len(checks),
                "failed_checks": [name for name, ok in checks if not ok],
                "error": error,
                "profile": profile,
            }
        )
    return results


def summarize(results: list[dict]) -> dict[str, Any]:
    n = len(results)
    valid = [r for r in results if r["valid"]]
    seconds = [r["seconds"] for r in results]
    checks_total = sum(r["checks_total"] for r in valid)
    return {
        "descriptions": n,
        "valid": len(valid),
        "valid_rate": len(valid) / n if n else 0.0,
        "valid_first_try": sum(1 for r in valid if r["attempts"] == 1),
        "mean_attempts": float(np.mean([r["attempts"] for r in results])) if n else 0.0,
        "p50_seconds": float(np.percentile(seconds, 50)) if n else 0.0,
        "p95_seconds": float(np.percentile(seconds, 95)) if n else 0.0,
        "max_seconds": max(seconds, default=0.0),
        "checks_passed": sum(r["checks_passed"] for r in valid),
        "checks_total": checks_total,
        "fully_correct": sum(
            1 for r in valid if r["checks_total"] and r["checks_passed"] == r["checks_total"]
        ),
    }


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def render(summary: dict[str, Any], results: list[dict], model: str, machine: str, today: str):
    s = summary
    lines = [
        "# LLM spike (AI): free text to TravelerProfile",
        "",
        "**Question:** Can a local 8B-class model (via Ollama) reliably turn a paragraph into a",
        "valid `TravelerProfile`?",
        "",
        f"Generated {today} by `python -m ai.benchmark` on {machine}. Each description gets up to",
        f"{MAX_ATTEMPTS} attempts; invalid replies are sent back to the model with the problems",
        "listed. Latency is the whole extraction including retries, after one warm-up call that",
        "loads the model.",
        "",
        "## Answer",
        "",
        "| Model | Valid-output rate | p95 latency (s) | Notes |",
        "|-------|------------------:|----------------:|-------|",
        f"| {model} | {_pct(s['valid'], s['descriptions'])} ({s['valid']}/{s['descriptions']}) "
        f"| {s['p95_seconds']:.1f} | median {s['p50_seconds']:.1f} s, "
        f"{s['valid_first_try']}/{s['descriptions']} valid on the first try |",
        "",
        "## Was the profile right, not just valid?",
        "",
        "Each description lists what a correct profile must show, for example \"food high\" or",
        "\"currency JPY\" (`fixtures/traveler-descriptions.json`).",
        "",
        f"- Checks passed: {s['checks_passed']}/{s['checks_total']} "
        f"({_pct(s['checks_passed'], s['checks_total'])})",
        f"- Descriptions with every check passed: {s['fully_correct']}/{s['descriptions']}",
        f"- Mean attempts per description: {s['mean_attempts']:.2f}",
        "",
        "| Description | Valid | Attempts | Seconds | Checks | Missed |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in results:
        missed = ", ".join(r["failed_checks"]) or (r["error"] or "")
        lines.append(
            f"| {r['id']} | {'yes' if r['valid'] else 'no'} | {r['attempts']} | "
            f"{r['seconds']:.1f} | {r['checks_passed']}/{r['checks_total']} | {missed} |"
        )
    lines += [
        "",
        "## Decision this informs",
        "",
        "Whether the local model is good enough for the demo, or whether extraction should fall",
        "back to a hosted model through the provider abstraction in `ai/llm.py`. Either way the",
        "traveler reviews the extracted profile in the form before planning, and the API lists",
        "which fields were not mentioned and filled with defaults.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the LLM profile-extraction spike.")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--descriptions", default=str(DESCRIPTIONS))
    ap.add_argument("--docs", default=str(REPO_ROOT / "docs"))
    args = ap.parse_args(argv)

    llm = OllamaLLM(args.model, args.ollama_url)
    items = json.loads(Path(args.descriptions).read_text(encoding="utf-8"))["descriptions"]
    try:
        extract_profile("A short city break.", llm)  # warm-up: loads the model
        results = run(llm, items)
    except LLMUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summary = summarize(results)
    machine = f"{platform.system()} {platform.machine()}"
    docs = Path(args.docs)
    docs.mkdir(parents=True, exist_ok=True)
    report = render(summary, results, args.model, machine, date.today().isoformat())
    (docs / "llm-spike.md").write_text(report, encoding="utf-8")
    payload = {"model": args.model, "summary": summary, "results": results}
    (docs / "llm-spike.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"valid {summary['valid']}/{summary['descriptions']}, p95 {summary['p95_seconds']:.1f}s")
    print(f"wrote {docs / 'llm-spike.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
