# RE3 Testing Harness Specification

## Exhaustive Configuration Set

Based on RE2 findings that 3 repetitions rarely helps but sometimes can, we test all combinations of A (original) and B (re-tokenized) up to length 3:

### Complete Configuration Matrix (14 total)

| ID | Pattern | Length | Description |
|----|---------|--------|-------------|
| C01 | A | 1 | Baseline single pass |
| C02 | B | 1 | Re-tokenized only |
| C03 | AA | 2 | RE2 standard |
| C04 | AB | 2 | Original + variant |
| C05 | BA | 2 | Variant + original |
| C06 | BB | 2 | Double variant |
| C07 | AAA | 3 | Triple original |
| C08 | AAB | 3 | Double original + variant |
| C09 | ABA | 3 | Symmetric sandwich |
| C10 | ABB | 3 | Original + double variant |
| C11 | BAA | 3 | Variant + double original |
| C12 | BAB | 3 | Alternating, variant-first |
| C13 | BBA | 3 | Double variant + original |
| C14 | BBB | 3 | Triple variant |

**Phase 1:** Single B strategy (e.g., CamelCase injection)
**Phase 2:** If signal found, test additional B strategies

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     TEST ORCHESTRATOR                        │
│  (Python script - manages test queue, collects results)     │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   PROMPT TRANSFORMER                         │
│  (Applies re-tokenization strategy B to create variants)    │
│  Input: prompt A, strategy ID                                │
│  Output: prompt B                                            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  CONFIGURATION BUILDER                       │
│  (Assembles final prompt from pattern like ABA)             │
│  Input: A, B, pattern                                        │
│  Output: concatenated prompt with separators                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    LOCAL LLM INTERFACE                       │
│  (Calls safe-model-load.sh or direct LM Studio API)         │
│  Input: assembled prompt                                     │
│  Output: model response                                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    RESULT EVALUATOR                          │
│  (Compares response to ground truth)                         │
│  Input: response, expected answer                            │
│  Output: correct/incorrect, confidence score                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA RECORDER                             │
│  (Writes all results to observation table)                   │
│  Output: CSV/SQLite with full run data                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Schema

### Run Record (one per test execution)

```json
{
  "run_id": "uuid",
  "timestamp": "ISO-8601",
  "config_id": "C09",
  "pattern": "ABA",
  "b_strategy": "camelcase",
  "benchmark": "gsm8k",
  "item_id": "gsm8k_042",
  "prompt_a": "original prompt text",
  "prompt_b": "reTokenized prompt text",
  "assembled_prompt": "full prompt sent to model",
  "token_count_input": 1234,
  "token_count_output": 56,
  "response_raw": "model output",
  "expected_answer": "42",
  "extracted_answer": "42",
  "correct": true,
  "latency_ms": 1523,
  "model_id": "llama-3.1-8b"
}
```

### Summary Table (aggregated)

| config_id | pattern | benchmark | n_correct | n_total | accuracy | accuracy_vs_baseline | accuracy_vs_re2 |
|-----------|---------|-----------|-----------|---------|----------|---------------------|-----------------|

---

## Re-Tokenization Strategies

### B1: CamelCase Injection

Transform word boundaries to camelCase:
- "the quick brown fox" → "theQuick brownFox jumps"
- Preserves some spaces to maintain readability
- Implementation: Split on spaces, join pairs with camelCase

```python
def camelcase_inject(text: str) -> str:
    words = text.split()
    result = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and random.random() < 0.5:
            # Join two words with camelCase
            result.append(words[i] + words[i+1].capitalize())
            i += 2
        else:
            result.append(words[i])
            i += 1
    return ' '.join(result)
```

### B2: Digit Spacing

Add spaces between digits:
- "381" → "3 8 1"
- "The answer is 42" → "The answer is 4 2"

```python
def digit_space(text: str) -> str:
    return re.sub(r'(\d)(\d)', r'\1 \2', text)
```

### B3: Capitalization Shift

Alternate case or uniform shift:
- "Hello World" → "HELLO WORLD" or "hello world"

```python
def cap_shift(text: str, mode='lower') -> str:
    return text.lower() if mode == 'lower' else text.upper()
```

---

## Benchmark Integration

### GSM8K (Arithmetic)
- Source: HuggingFace `gsm8k` dataset
- Format: Question → numerical answer
- Evaluation: Extract final number, compare to ground truth
- Subset: First 100 items (Phase 1)

### MMLU (Knowledge)
- Source: HuggingFace `cais/mmlu`
- Format: Multiple choice (A/B/C/D)
- Evaluation: Extract letter choice, compare
- Subset: Mixed 50 items across categories

### Custom NIAH (Retrieval)
- Create synthetic: Hide fact in varying context lengths
- Format: "The secret number is X" buried in text
- Evaluation: Extract X from response
- Variants: 1k, 4k, 8k context lengths

---

## Execution Plan

### Phase 1: Proof of Concept
- Configurations: All 14
- B strategy: B1 (CamelCase) only
- Benchmark: GSM8K subset (50 items)
- **Total runs: 14 × 50 = 700**

### Phase 2: Strategy Comparison
- Configurations: Top 5 from Phase 1
- B strategies: B1, B2, B3
- Benchmark: GSM8K subset (50 items)
- **Total runs: 5 × 3 × 50 = 750**

### Phase 3: Full Evaluation
- Configurations: Top 3 from Phase 2
- B strategy: Best from Phase 2
- Benchmarks: All (GSM8K, MMLU, NIAH variants)
- **Total runs: 3 × 1 × 200 = 600**

### Estimated Total: ~2,050 runs

---

## Local LLM Requirements

### Model Selection
- Recommended: Llama 3.1 8B (good balance of speed/quality)
- Alternative: Phi-3 or Mistral 7B for faster iteration
- Must support: Reasonable context window (8k minimum)

### LM Studio Configuration
- Server must be running with API enabled
- Temperature: 0.0 (deterministic)
- Max tokens: Sufficient for answer extraction

### Interface
Primary: `safe-model-load.sh` for compatibility
Fallback: Direct HTTP to `localhost:1234/v1/chat/completions`

---

## Output Files

```
RE3/
├── data/
│   ├── runs/
│   │   └── YYYY-MM-DD_HHMMSS_phase1.jsonl  # Raw run records
│   ├── summaries/
│   │   └── YYYY-MM-DD_HHMMSS_phase1_summary.csv
│   └── benchmarks/
│       ├── gsm8k_subset.json
│       ├── mmlu_subset.json
│       └── niah_synthetic.json
├── analysis/
│   └── (Jupyter notebooks for visualization)
└── harness/
    ├── run_tests.py
    ├── transformers.py
    ├── evaluators.py
    └── config.yaml
```
