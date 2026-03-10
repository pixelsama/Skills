#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEXT_KEYS = (
    "translated_text",
    "output",
    "translation",
    "target_text",
    "text",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split batch translation payloads into babeldoc-jobpack translations.json."
    )
    parser.add_argument("batches_json", help="Packed batches JSON created by pack_jobs.py")
    parser.add_argument("translated_json", help="Batch translation output from agent/model.")
    parser.add_argument("--out", required=True, help="Output path for translations JSON.")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow missing translated items.",
    )
    parser.add_argument(
        "--fallback-source",
        action="store_true",
        help="When missing translation, fallback to source_text from packed jobs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    batches_path = Path(args.batches_json).expanduser().resolve()
    translated_path = Path(args.translated_json).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    batches_payload = load_json(batches_path)
    translated_payload = load_json(translated_path)

    expected_ids, source_by_id = collect_expected_ids_and_source(batches_payload)
    translated_map = collect_translations(translated_payload)

    ordered_output: dict[str, str] = {}
    missing_ids: list[str] = []
    for job_id in expected_ids:
        text = translated_map.get(job_id)
        if text is None and args.fallback_source:
            text = source_by_id.get(job_id, "")
        if text is None:
            missing_ids.append(job_id)
            continue
        ordered_output[job_id] = text

    if missing_ids and not args.allow_missing:
        preview = ", ".join(missing_ids[:20])
        raise ValueError(f"Missing translations for IDs: {preview}")

    out_path.write_text(json.dumps(ordered_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out_path),
                "expected_count": len(expected_ids),
                "written_count": len(ordered_output),
                "missing_count": len(missing_ids),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def collect_expected_ids_and_source(payload) -> tuple[list[str], dict[str, str]]:
    batches = payload.get("batches") if isinstance(payload, dict) else None
    if not isinstance(batches, list):
        raise ValueError("batches_json must contain a top-level 'batches' array")

    ordered_ids: list[str] = []
    source_by_id: dict[str, str] = {}
    seen: set[str] = set()
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        jobs = batch.get("jobs", [])
        if not isinstance(jobs, list):
            continue
        for job in jobs:
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("id", "")).strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            ordered_ids.append(job_id)
            source_by_id[job_id] = str(job.get("source_text", ""))
    return ordered_ids, source_by_id


def collect_translations(payload) -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
            return

        if isinstance(node, dict):
            # Direct {id: text} map.
            if is_plain_string_map(node):
                for k, v in node.items():
                    out[str(k)] = str(v)
                return

            # Single translation item.
            if "id" in node:
                job_id = str(node.get("id", "")).strip()
                text = pick_text(node)
                if job_id and text is not None:
                    out[job_id] = text

            # Nested common keys.
            for key in ("translations", "items", "batches", "results", "output"):
                child = node.get(key)
                if isinstance(child, (list, dict)):
                    walk(child)
            return

    walk(payload)
    return out


def is_plain_string_map(node: dict) -> bool:
    if not node:
        return False
    reserved = {"translations", "items", "batches", "results", "output", "id", *TEXT_KEYS}
    if any(key in reserved for key in node.keys()):
        return False
    return all(isinstance(value, str) for value in node.values())


def pick_text(item: dict) -> str | None:
    for key in TEXT_KEYS:
        value = item.get(key)
        if value is not None:
            return str(value)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
