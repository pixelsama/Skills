#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLACEHOLDER_PATTERN = re.compile(r"</?b\d+>|\{v\d+\}", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate babeldoc-jobpack translations against exported jobs."
    )
    parser.add_argument("jobs_json", help="Path to jobs.json")
    parser.add_argument("translations_json", help="Path to translations JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any missing/placeholder issue is detected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs_path = Path(args.jobs_json).expanduser().resolve()
    translations_path = Path(args.translations_json).expanduser().resolve()

    jobs = load_jobs(jobs_path)
    translations = load_translations(translations_path)

    expected_ids = [str(job.get("id")) for job in jobs if job.get("id") is not None]
    missing_ids: list[str] = []
    empty_ids: list[str] = []
    placeholder_issues: list[dict] = []

    for job in jobs:
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue
        translated_text = translations.get(job_id)
        if translated_text is None:
            missing_ids.append(job_id)
            continue
        if not translated_text.strip():
            empty_ids.append(job_id)

        expected_placeholders = collect_placeholders_from_job(job)
        actual_placeholders = collect_placeholders(translated_text)
        missing_placeholders = sorted(expected_placeholders - actual_placeholders)
        if missing_placeholders:
            placeholder_issues.append(
                {
                    "id": job_id,
                    "missing_placeholders": missing_placeholders,
                }
            )

    report = {
        "expected_count": len(expected_ids),
        "translated_count": len(translations),
        "missing_count": len(missing_ids),
        "empty_count": len(empty_ids),
        "placeholder_issue_count": len(placeholder_issues),
        "missing_ids": missing_ids[:100],
        "empty_ids": empty_ids[:100],
        "placeholder_issues": placeholder_issues[:100],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    has_issues = bool(missing_ids or empty_ids or placeholder_issues)
    if args.strict and has_issues:
        return 1
    return 0


def load_jobs(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"jobs.json not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("jobs.json must be an array")
    return [item for item in raw if isinstance(item, dict)]


def load_translations(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"translations file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            job_id = item.get("id")
            text = item.get("translated_text", item.get("output", item.get("translation")))
            if job_id is None or text is None:
                continue
            out[str(job_id)] = str(text)
        return out
    raise ValueError("translations JSON must be an object or an array")


def collect_placeholders_from_job(job: dict) -> set[str]:
    result = set(collect_placeholders(str(job.get("source_text", ""))))

    original_tokens = job.get("original_placeholder_tokens")
    if original_tokens is not None:
        for token in walk_scalars(original_tokens):
            result.update(collect_placeholders(token))

    for placeholder in job.get("placeholders", []) or []:
        for token in walk_scalars(placeholder):
            result.update(collect_placeholders(token))
    return result


def collect_placeholders(text: str) -> set[str]:
    return {match.group(0) for match in PLACEHOLDER_PATTERN.finditer(text)}


def walk_scalars(value):
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from walk_scalars(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from walk_scalars(item)


if __name__ == "__main__":
    raise SystemExit(main())
