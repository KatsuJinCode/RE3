# RE3: Re-Reading with Re-Tokenization

## Abstract

RE2 (Re-Reading) demonstrated that repeating an input prompt enables a second attention pass where tokens can attend to their earlier copies, approximating bidirectional attention in decoder-only transformers. We propose RE3: extending RE2 by using intelligently re-tokenized variants (B) alongside the original prompt (A), creating patterns like AB, ABA, etc. The hypothesis is that different tokenizations of the same semantic content provide complementary attention pathways, potentially improving reasoning accuracy beyond simple repetition.

## Background: RE2

Google's RE2 technique (January 2025) showed that repeating a prompt twice (AA pattern) allows the model's attention mechanism to function more like bidirectional attention:

- In the first pass, each token can only attend to previous tokens
- In the second pass, each token can attend to the entire first copy
- This enables information flow that approximates BERT-style bidirectional encoding

RE2 showed consistent improvements across reasoning benchmarks with minimal computational overhead (just doubling input length).

## RE3 Hypothesis

If repetition helps by enabling richer attention patterns, what if the repeated content is semantically equivalent but tokenized differently? Different tokenizations could:

1. Create different attention "entry points" to the same concepts
2. Force the model to reconcile multiple representations
3. Provide redundancy that aids error correction

We test this by replacing the second (or third) copy with a re-tokenized variant, creating patterns like:
- **AB**: Original + re-tokenized variant
- **ABA**: Symmetric sandwich with variant in middle
- **ABB**: Original + double variant

## Methodology

### Configurations Tested

14 exhaustive A/B patterns up to length 3:

| ID | Pattern | Description | Context Multiplier |
|----|---------|-------------|-------------------|
| C01 | A | Baseline (single pass) | 1x |
| C02 | B | Re-tokenized only | 1x |
| C03 | AA | RE2 standard | 2x |
| C04 | AB | Original + variant | 2x |
| C05 | BA | Variant + original | 2x |
| C06 | BB | Double variant | 2x |
| C07 | AAA | Triple original | 3x |
| C08 | AAB | Double original + variant | 3x |
| C09 | ABA | Symmetric sandwich | 3x |
| C10 | ABB | Original + double variant | 3x |
| C11 | BAA | Variant + double original | 3x |
| C12 | BAB | Alternating, variant-first | 3x |
| C13 | BBA | Double variant + original | 3x |
| C14 | BBB | Triple variant | 3x |

### Re-Tokenization Strategies

10 strategies that alter tokenization while preserving semantics:

| ID | Strategy | Example |
|----|----------|---------|
| b1a | Camelcase pairs | "the quick brown" -> "theQuick brown" |
| b1b | Camelcase all | "the quick brown" -> "theQuickBrown" |
| b1c | Underscore join | "the quick" -> "the_quick" |
| b1d | Hyphenation | "computer" -> "com-pu-ter" |
| b1e | Compound split | "blackbird" -> "black bird" |
| b2a | Digit spacing | "42" -> "4 2" |
| b3a | Lowercase all | "Hello World" -> "hello world" |
| b3b | Uppercase all | "Hello World" -> "HELLO WORLD" |
| b4a | Delimiter swap | "####" -> "----" |
| b6b | Word numbers | "42" -> "forty-two" |

### Benchmarks

- **GSM8K**: Grade school math word problems (tests reasoning)
- **MMLU**: Multi-domain knowledge questions (tests recall)
- **HellaSwag**: Commonsense completion (tests world knowledge)
- **NIAH**: Needle-in-a-haystack retrieval (tests context utilization)

### Infrastructure

- Local LLM via LM Studio (google/gemma-3n-e4b)
- safe-model-load.sh gateway for request management
- JSONL logging with summary CSV generation

## Preliminary Results

Mini phase: 20 items each, GSM8K benchmark, b1a_camelcase_pairs strategy

| Config | Pattern | Accuracy | vs Baseline |
|--------|---------|----------|-------------|
| C01 | A (baseline) | 75.0% | - |
| C03 | AA (RE2) | 85.0% | +10.0% |
| C04 | AB (RE3) | 80.0% | +5.0% |
| C09 | ABA (RE3) | 85.0% | +10.0% |

### Initial Observations

1. **RE2 replicates**: AA shows +10% over baseline, consistent with RE2 findings
2. **ABA matches AA**: The symmetric sandwich pattern achieves parity with RE2
3. **AB underperforms AA**: Simple AB may be worse than pure repetition
4. **Small sample caveat**: n=20 per config, confidence intervals are wide

## Pattern Timing Analysis

Patterns have different context lengths, affecting processing time:

| Pattern Length | Context Multiplier | Expected Relative Time | Configurations |
|----------------|-------------------|----------------------|----------------|
| 1 | 1x | Fastest | C01, C02 |
| 2 | 2x | ~2x baseline | C03, C04, C05, C06 |
| 3 | 3x | ~3x baseline | C07-C14 |

**Recommendation for efficient data collection:**
1. Run all length-1 patterns first (fastest, establish baselines)
2. Run length-2 patterns (includes RE2 comparison)
3. Run length-3 patterns (most expensive but most novel)

Within each length, prioritize:
- Patterns with A-first (more comparable to RE2)
- Diverse B positions (ABA, ABB, AAB provide different data points)

## Progress Checklist

### Phase 1: Full Matrix (14 configs x 10 strategies x ~200 items = ~28,000 runs)

#### Length-1 Patterns (Baselines)
- [ ] C01 (A) - all strategies, all benchmarks
- [ ] C02 (B) - all strategies, all benchmarks

#### Length-2 Patterns (RE2 Comparison)
- [ ] C03 (AA) - all strategies, all benchmarks
- [ ] C04 (AB) - all strategies, all benchmarks
- [ ] C05 (BA) - all strategies, all benchmarks
- [ ] C06 (BB) - all strategies, all benchmarks

#### Length-3 Patterns (Novel Combinations)
- [ ] C07 (AAA) - all strategies, all benchmarks
- [ ] C08 (AAB) - all strategies, all benchmarks
- [ ] C09 (ABA) - all strategies, all benchmarks
- [ ] C10 (ABB) - all strategies, all benchmarks
- [ ] C11 (BAA) - all strategies, all benchmarks
- [ ] C12 (BAB) - all strategies, all benchmarks
- [ ] C13 (BBA) - all strategies, all benchmarks
- [ ] C14 (BBB) - all strategies, all benchmarks

### Strategies per Configuration
Each configuration above requires testing with:
- [ ] b1a_camelcase_pairs
- [ ] b1b_camelcase_all
- [ ] b1c_underscore_join
- [ ] b1d_hyphenation
- [ ] b1e_compound_split
- [ ] b2a_digit_spacing
- [ ] b3a_lowercase_all
- [ ] b3b_uppercase_all
- [ ] b4a_delimiter_swap
- [ ] b6b_word_numbers

### Benchmarks per Configuration
Each configuration requires testing on:
- [ ] GSM8K (50 items)
- [ ] MMLU (50 items)
- [ ] HellaSwag (50 items)
- [ ] NIAH (50 items)

## Implementation Status

### Completed
- [x] Harness architecture
- [x] Gateway integration (llm_interface.py)
- [x] Re-tokenization strategies (retokenizers.py)
- [x] Answer extraction (evaluators.py)
- [x] Data recording (data_recorder.py)
- [x] Main orchestrator (run_tests.py)
- [x] Smoke test validation
- [x] Mini phase validation (4 configs x 20 items)

### Pending
- [ ] Async batching for efficient LLM utilization
- [ ] Full Phase 1 execution
- [ ] Statistical analysis pipeline
- [ ] Paper draft

## Next Steps

1. **Implement batching**: Current sequential processing underutilizes LM Studio. Need queue depth > 0 to maintain GPU utilization.

2. **Full Phase 1**: After batching validated, run complete matrix (~2-3 days estimated).

3. **Analysis**: Statistical significance testing, effect size calculations, interaction analysis.

4. **Paper**: Write up findings for submission.

## Raw Data Location

- Run logs: `data/runs/phase1_*.jsonl`
- Summaries: `data/summaries/phase1_*_summary.csv`
- Research notes: `research/`
