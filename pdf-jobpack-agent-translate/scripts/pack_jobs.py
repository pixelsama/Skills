#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pack BabelDOC jobs.json into larger agent translation batches."
    )
    parser.add_argument("jobs_json", help="Path to jobs.json exported by babeldoc-jobpack.")
    parser.add_argument("--out", required=True, help="Output path for packed batches JSON.")
    parser.add_argument(
        "--max-items",
        type=int,
        default=100,
        help="Maximum number of jobs in one batch.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=12000,
        help="Maximum estimated token count in one batch.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include jobs whose source_text is empty.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_items <= 0:
        raise ValueError("--max-items must be > 0")
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be > 0")

    jobs_path = Path(args.jobs_json).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    jobs = load_jobs(jobs_path)
    batches = make_batches(
        jobs=jobs,
        max_items=args.max_items,
        max_tokens=args.max_tokens,
        include_empty=args.include_empty,
    )
    payload = {
        "schema_version": 1,
        "source_jobs": str(jobs_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_items": args.max_items,
        "max_tokens": args.max_tokens,
        "total_jobs": sum(len(batch["jobs"]) for batch in batches),
        "batch_count": len(batches),
        "batches": batches,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out_path),
                "batch_count": payload["batch_count"],
                "total_jobs": payload["total_jobs"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_jobs(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"jobs.json not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("jobs.json must be an array")
    rows: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if "id" not in item:
            continue
        rows.append(item)
    return rows


def make_batches(
    *,
    jobs: list[dict],
    max_items: int,
    max_tokens: int,
    include_empty: bool,
) -> list[dict]:
    batches: list[dict] = []
    current_jobs: list[dict] = []
    current_tokens = 0
    batch_index = 1

    for job in jobs:
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue
        source_text = str(job.get("source_text", ""))
        if not include_empty and not source_text.strip():
            continue
        token_count = normalize_token_count(job.get("token_count"), source_text)

        if current_jobs and (
            len(current_jobs) >= max_items or current_tokens + token_count > max_tokens
        ):
            batches.append(build_batch(batch_index, current_jobs, current_tokens))
            batch_index += 1
            current_jobs = []
            current_tokens = 0

        item = {
            "id": job_id,
            "source_text": source_text,
            "token_count": token_count,
            "page_index": job.get("page_index"),
            "paragraph_index": job.get("paragraph_index"),
            "layout_label": job.get("layout_label"),
            "placeholders": job.get("placeholders", []),
            "original_placeholder_tokens": job.get("original_placeholder_tokens", {}),
        }
        current_jobs.append(item)
        current_tokens += token_count

    if current_jobs:
        batches.append(build_batch(batch_index, current_jobs, current_tokens))
    return batches


def build_batch(batch_index: int, jobs: list[dict], total_tokens: int) -> dict:
    return {
        "batch_id": f"b{batch_index:04d}",
        "job_count": len(jobs),
        "total_tokens": total_tokens,
        "job_ids": [item["id"] for item in jobs],
        "jobs": jobs,
    }


def normalize_token_count(raw, source_text: str) -> int:
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str):
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    # Small fallback heuristic to keep batch size bounded without external tokenizers.
    return max(1, len(source_text) // 4)


if __name__ == "__main__":
    raise SystemExit(main())
