# RE3 Data Collection Schema

## Overview

The observation table is the empirical foundation of the paper. Every run is recorded with full context for reproducibility and analysis.

---

## Primary Table: `runs`

Each row represents one test execution (prompt → model → response → evaluation).

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | UUID | Unique identifier |
| `timestamp` | ISO-8601 | When run executed |
| `phase` | int | Experiment phase (1, 2, 3) |
| **Configuration** | | |
| `config_id` | string | C01-C14 |
| `pattern` | string | e.g., "ABA" |
| `pattern_length` | int | 1, 2, or 3 |
| `b_strategy` | string | "camelcase", "digit_space", "cap_shift" |
| **Benchmark** | | |
| `benchmark` | string | "gsm8k", "mmlu", "niah", "hellaswag" |
| `benchmark_subset` | string | e.g., "abstract_algebra" for MMLU |
| `item_id` | string | Original dataset item identifier |
| `item_index` | int | Position in our subset |
| **Prompts** | | |
| `prompt_a` | text | Original prompt |
| `prompt_b` | text | Re-tokenized prompt (null if B not used) |
| `assembled_prompt` | text | Full prompt sent to model |
| `separator` | string | Text between repetitions |
| **Tokens** | | |
| `tokens_a` | int | Token count of A |
| `tokens_b` | int | Token count of B (null if not used) |
| `tokens_total_input` | int | Total input tokens |
| `tokens_output` | int | Output tokens generated |
| **Model** | | |
| `model_id` | string | e.g., "llama-3.1-8b-instruct" |
| `temperature` | float | Always 0.0 for determinism |
| `max_tokens` | int | Output limit |
| **Response** | | |
| `response_raw` | text | Complete model output |
| `response_truncated` | bool | Was output cut off? |
| `latency_ms` | int | Time to complete |
| **Evaluation** | | |
| `expected_answer` | string | Ground truth |
| `extracted_answer` | string | Parsed from response |
| `extraction_method` | string | "regex", "index_match", "exact" |
| `correct` | bool | extracted == expected |
| `confidence` | float | Optional: model's stated confidence |
| **Metadata** | | |
| `error` | string | Null if success, error message if failed |
| `notes` | string | Any manual annotations |

### Example Row

```json
{
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "timestamp": "2025-01-17T14:32:01Z",
  "phase": 1,
  "config_id": "C09",
  "pattern": "ABA",
  "pattern_length": 3,
  "b_strategy": "camelcase",
  "benchmark": "gsm8k",
  "benchmark_subset": null,
  "item_id": "gsm8k_test_042",
  "item_index": 42,
  "prompt_a": "Janet's ducks lay 16 eggs per day. She eats three for breakfast...",
  "prompt_b": "Janet's ducksLay 16 eggsper day. sheEats three forBreakfast...",
  "assembled_prompt": "[prompt_a]\n\nRead the question again:\n\n[prompt_b]\n\nRead once more:\n\n[prompt_a]\n\nAnswer:",
  "separator": "\n\nRead the question again:\n\n",
  "tokens_a": 87,
  "tokens_b": 85,
  "tokens_total_input": 267,
  "tokens_output": 42,
  "model_id": "llama-3.1-8b-instruct",
  "temperature": 0.0,
  "max_tokens": 256,
  "response_raw": "Let me solve this step by step...\n#### 18",
  "response_truncated": false,
  "latency_ms": 1847,
  "expected_answer": "18",
  "extracted_answer": "18",
  "extraction_method": "regex",
  "correct": true,
  "confidence": null,
  "error": null,
  "notes": null
}
```

---

## Aggregation Table: `summary`

Computed from `runs` for analysis and visualization.

| Column | Type | Description |
|--------|------|-------------|
| `config_id` | string | Configuration |
| `pattern` | string | Pattern |
| `b_strategy` | string | Re-tokenization strategy |
| `benchmark` | string | Benchmark name |
| `n_total` | int | Total runs |
| `n_correct` | int | Correct answers |
| `n_error` | int | Runs with errors |
| `accuracy` | float | n_correct / (n_total - n_error) |
| `accuracy_95ci_low` | float | 95% CI lower bound |
| `accuracy_95ci_high` | float | 95% CI upper bound |
| `avg_latency_ms` | float | Mean latency |
| `avg_tokens_input` | float | Mean input tokens |
| `avg_tokens_output` | float | Mean output tokens |

### Derived Metrics (computed at analysis time)

| Metric | Formula | Purpose |
|--------|---------|---------|
| `delta_vs_baseline` | accuracy - accuracy(C01) | Improvement over single-pass |
| `delta_vs_re2` | accuracy - accuracy(C03) | Improvement over standard RE2 |
| `efficiency` | delta_vs_baseline / (avg_tokens_input - tokens_baseline) | Accuracy gain per extra token |
| `significance` | McNemar test p-value | Statistical significance vs baseline |

---

## File Formats

### Raw Data: JSONL
- One JSON object per line
- Append-only during execution
- File per phase: `data/runs/phase1_YYYYMMDD_HHMMSS.jsonl`

### Summary: CSV
- Computed after each phase
- File: `data/summaries/phase1_summary.csv`

### Backup: SQLite
- Mirror of JSONL for querying
- File: `data/re3_results.db`

---

## Storage Estimates

| Phase | Runs | Avg Row Size | Total |
|-------|------|--------------|-------|
| 1 | 2,660 | ~5 KB | ~13 MB |
| 2 | 750 | ~5 KB | ~4 MB |
| 3 | 600 | ~5 KB | ~3 MB |
| **Total** | 4,010 | | **~20 MB** |

Very manageable for local storage.

---

## Analysis Queries

### Top configurations by accuracy
```sql
SELECT config_id, pattern, benchmark, accuracy, delta_vs_re2
FROM summary
WHERE benchmark = 'gsm8k'
ORDER BY accuracy DESC;
```

### Statistical significance check
```sql
SELECT config_id, pattern,
       accuracy, accuracy_95ci_low, accuracy_95ci_high
FROM summary
WHERE accuracy_95ci_low > (SELECT accuracy FROM summary WHERE config_id = 'C03' AND benchmark = ?)
```

### Token efficiency
```sql
SELECT config_id, pattern,
       delta_vs_baseline,
       avg_tokens_input - (SELECT avg_tokens_input FROM summary WHERE config_id = 'C01') as extra_tokens,
       delta_vs_baseline / NULLIF(extra_tokens, 0) as efficiency
FROM summary
ORDER BY efficiency DESC;
```

---

## Data Integrity

### Validation Rules
1. Every run must have non-null: run_id, timestamp, config_id, benchmark, item_id
2. If pattern contains 'B', b_strategy must be non-null
3. If correct is true, extracted_answer must equal expected_answer
4. tokens_total_input must equal sum of component tokens

### Checksums
- JSONL files include SHA-256 hash in filename suffix after completion
- Enables verification that data hasn't been corrupted

---

## Visualization Requirements

The observation table must support these paper figures:

1. **Accuracy heatmap:** config_id × benchmark
2. **Bar chart:** Accuracy by pattern length (1, 2, 3)
3. **Line plot:** Accuracy vs token cost (efficiency frontier)
4. **Error bars:** Accuracy with 95% CI for top configurations
5. **Comparison table:** RE3 best vs RE2 vs baseline across all benchmarks
