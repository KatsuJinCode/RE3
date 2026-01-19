# RE3 Testing Harness Usage

## Quick Start

```bash
cd "RE3"

# Check everything is working
just smoke

# Install benchmark data (one time, ~220MB download)
just install-datasets

# Run full Phase 1 experiment (batched, recommended)
just phase1-batch
```

## Available Commands

| Command | What it does |
|---------|--------------|
| `just smoke` | Quick test (5 items, no real data needed) |
| `just install-datasets` | Install HuggingFace datasets library |
| `just phase1-batch` | Run full Phase 1 with batching (recommended) |
| `just phase1` | Run full Phase 1 sequentially |
| `just test-batch C01` | Test specific config with batching |
| `just gsm8k` | Run just math benchmark (50 items) |
| `just mmlu` | Run just knowledge benchmark (50 items) |
| `just gateway-status` | Check if LM Studio is ready |
| `just results` | View latest summary CSV |
| `just runs` | View last 10 raw test records |
| `just show-transforms` | See examples of each re-tokenization strategy |

## Batched Execution

Batched mode keeps multiple requests in flight, preventing LM Studio from ramping down between requests:

```bash
# Run with batching (4 concurrent requests, default)
just phase1-batch

# Custom concurrency level
just phase1-batch "model-name" 6

# Test specific config with batching
just test-batch C09 b1a_camelcase_pairs gsm8k 20 4
```

## Prerequisites

1. **LM Studio running** with server enabled
2. **Python 3.8+** with pip
3. **datasets library** (run `just install-datasets`)

## Experiment Phases

### Phase 1: Full Matrix
- 14 configurations (all A/B patterns up to length 3)
- 10 re-tokenization strategies
- ~200 benchmark items
- **~28,000 runs total**
- Estimated time: 2-3 days on local LLM

### Running Specific Tests

```bash
# Test single configuration
just test-config C09 b1a_camelcase_pairs gsm8k 10

# Test baseline only
just test-config C01
```

## Output Files

```
data/
├── runs/
│   └── phase1_YYYYMMDD_HHMMSS.jsonl   # Raw test records
└── summaries/
    └── phase1_YYYYMMDD_HHMMSS_summary.csv  # Aggregated results
```

## Configuration Reference

| ID | Pattern | Description |
|----|---------|-------------|
| C01 | A | Baseline (single pass) |
| C02 | B | Re-tokenized only |
| C03 | AA | RE2 standard |
| C04 | AB | Original + variant |
| C05 | BA | Variant + original |
| C06 | BB | Double variant |
| C07 | AAA | Triple original |
| C08 | AAB | Double original + variant |
| C09 | ABA | Symmetric sandwich |
| C10 | ABB | Original + double variant |
| C11 | BAA | Variant + double original |
| C12 | BAB | Alternating, variant-first |
| C13 | BBA | Double variant + original |
| C14 | BBB | Triple variant |

## Strategy Reference

| ID | Strategy | Applies to |
|----|----------|------------|
| b1a_camelcase_pairs | Join word pairs: "the quick" → "theQuick" | All |
| b1b_camelcase_all | Join all words | All |
| b1c_underscore_join | Spaces to underscores | All |
| b1d_hyphenation | Add syllable hyphens | All |
| b1e_compound_split | Split compounds | All |
| b2a_digit_spacing | "42" → "4 2" | Math only |
| b3a_lowercase_all | Force lowercase | All |
| b3b_uppercase_all | Force uppercase | All |
| b4a_delimiter_swap | Change ### to --- etc. | All |
| b6b_word_numbers | "42" → "forty-two" | Math only |
