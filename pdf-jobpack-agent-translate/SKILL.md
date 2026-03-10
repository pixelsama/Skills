---
name: pdf-jobpack-agent-translate
description: Agent-native PDF translation workflow based on babeldoc-jobpack. Use this when the task is to translate PDF files by exporting structured paragraph jobs, letting the agent provide translations, then applying translations back into a rendered PDF. Supports job batching (merge/split) and placeholder validation for safer document reconstruction.
---

# PDF Jobpack Agent Translate

Use this skill when a PDF must be translated with stable paragraph IDs and re-rendered.

## Non-Negotiable Behavior

- The agent must translate the content itself.
- Translation work is owned by the agent, not the user.
- Do not ask the user to manually translate batches unless the user explicitly requests manual mode.
- Do not switch to external translation CLIs/services by default.
- Batch count is derived from script output; do not force a specific number of batches.

## Default Pipeline

1. Bootstrap a skill-local `.venv` and install `babeldoc-jobpack` from PyPI.
2. Export input PDF into `jobs.json`.
3. Pack jobs into `batches.json`.
4. Agent translates all `source_text` into Chinese and writes `translated_batches.json`.
5. Normalize to `translations.json`.
6. Validate placeholder integrity.
7. Apply translations back to PDF.

## Run Backend Commands

Use [jobpack_backend.py](./scripts/jobpack_backend.py) to call `babeldoc-export-jobs` and `babeldoc-apply-jobs`.

- The first action is to bootstrap a skill-local isolated virtualenv at `<skill_dir>/.venv`.
- Dependencies are installed only into that `.venv`.
- Package source is PyPI package spec only (default: `babeldoc-jobpack`).
- No source-repo fallback.

It does not require `uv`.

## Export Jobs

```bash
python3 /absolute/path/to/pdf-jobpack-agent-translate/scripts/jobpack_backend.py \
  export /absolute/path/to/input.pdf --job-dir /absolute/path/to/jobpack --lang-in en --lang-out zh
```

## Batch Jobs for Agent Translation

Pack with default batching heuristics:

```bash
python3 /absolute/path/to/pdf-jobpack-agent-translate/scripts/pack_jobs.py \
  /absolute/path/to/jobpack/jobs.json \
  --out /absolute/path/to/jobpack/batches.json
```

Then the agent must translate batches itself and produce `/absolute/path/to/translated_batches.json`.

Expected format:

```json
{
  "batches": [
    {
      "batch_id": "b0001",
      "translations": [
        { "id": "p0-q0", "translated_text": "中文翻译" }
      ]
    }
  ]
}
```

Normalize into `id -> translated_text`:

```bash
python3 /absolute/path/to/pdf-jobpack-agent-translate/scripts/unpack_batch_translations.py \
  /absolute/path/to/jobpack/batches.json \
  /absolute/path/to/translated_batches.json \
  --out /absolute/path/to/jobpack/translations.json
```

Validate before apply:

```bash
python3 /absolute/path/to/pdf-jobpack-agent-translate/scripts/validate_translations.py \
  /absolute/path/to/jobpack/jobs.json \
  /absolute/path/to/jobpack/translations.json \
  --strict
```

## Apply Translations

```bash
python3 /absolute/path/to/pdf-jobpack-agent-translate/scripts/jobpack_backend.py \
  apply /absolute/path/to/jobpack \
  --translations /absolute/path/to/jobpack/translations.json \
  --output-dir /absolute/path/to/out
```

## JSON Format Reference

Read [jobpack-formats.md](./references/jobpack-formats.md) when constructing or debugging translation payloads.
