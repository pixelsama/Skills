# Jobpack Formats

## `jobs.json` (from `babeldoc-export-jobs`)

Top-level array. Each item has:

- `id`: stable paragraph job id (`p{page}-q{paragraph}`)
- `source_text`: text that must be translated
- `token_count`: estimated token count
- `placeholders` / `original_placeholder_tokens`: formatting placeholders that should be preserved

## `batches.json` (from `pack_jobs.py`)

Top-level object:

- `batches`: array of batch objects
- `batches[].batch_id`: batch id
- `batches[].jobs[]`: source jobs included in the batch
- `batches[].jobs[].id`: paragraph id used for final apply

## Accepted Translation Inputs for `unpack_batch_translations.py`

It accepts several shapes:

1. Direct map:

```json
{
  "p0-q0": "翻译文本A",
  "p0-q1": "翻译文本B"
}
```

2. Flat list:

```json
[
  { "id": "p0-q0", "translated_text": "翻译文本A" },
  { "id": "p0-q1", "output": "翻译文本B" }
]
```

3. Batch nested:

```json
{
  "batches": [
    {
      "batch_id": "b0001",
      "translations": [
        { "id": "p0-q0", "translation": "翻译文本A" },
        { "id": "p0-q1", "translated_text": "翻译文本B" }
      ]
    }
  ]
}
```

## `translations.json` (for `babeldoc-apply-jobs`)

Top-level object:

```json
{
  "p0-q0": "翻译文本A",
  "p0-q1": "翻译文本B"
}
```

Keys must match `jobs.json` IDs.
