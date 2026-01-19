# RE3: Re-Reading with Re-Tokenization

## Core Hypothesis

RE2 demonstrates that repeating input enables pseudo-bidirectional attention. RE3 extends this: **if repetition helps, does repetition with varied tokenization help more?**

The model receives:
- **A**: Original prompt (standard tokenization)
- **B**: Same semantic content, different tokenization

By combining A and B in various configurations, we potentially provide:
1. Bidirectional attention benefits (from RE2)
2. Multiple tokenization perspectives on the same content
3. Robustness against tokenization-induced blind spots

---

## Re-Tokenization Strategies (B variants)

Each strategy transforms A into B while preserving semantic content:

| ID | Strategy | Example | Rationale |
|----|----------|---------|-----------|
| B1 | **CamelCase injection** | "the quick brown fox" → "theQuick brownFox" | Forces different token boundaries |
| B2 | **Digit spacing** | "381" → "3 8 1" | Known to improve arithmetic |
| B3 | **Capitalization shift** | "Hello World" → "HELLO WORLD" or "hello world" | Different token IDs, different trained associations |
| B4 | **Delimiter variation** | Using `###` vs `---` vs `***` | Changes attention anchoring |
| B5 | **Hyphenation** | "understanding" → "under-standing" | Exposes morphological structure |
| B6 | **Synonym substitution** | "big" → "large" | Different tokens, same meaning (control) |
| B7 | **Whitespace normalization** | Collapse/expand whitespace patterns | Changes positional tokenization |

**Phase 1 Focus:** B1 (CamelCase), B2 (digit spacing), B3 (capitalization)
- These are pure tokenization changes with no semantic drift
- B6 (synonyms) introduces semantic variance - use as control

---

## Configuration Matrix

### Baseline Configurations
| Config | Pattern | Description |
|--------|---------|-------------|
| C0 | A | Standard single-pass (baseline) |
| C1 | AA | RE2 standard (replication baseline) |

### RE3 Two-Pass Configurations
| Config | Pattern | Hypothesis |
|--------|---------|------------|
| C2 | AB | Re-tokenized second pass |
| C3 | BA | Re-tokenized first pass |
| C4 | BB | Double re-tokenized (control) |

### RE3 Three-Pass Configurations
| Config | Pattern | Hypothesis |
|--------|---------|------------|
| C5 | AAB | RE2 + tokenization variety |
| C6 | ABA | Sandwich: original, variant, original |
| C7 | ABB | Original + double variant |
| C8 | BAA | Variant prime + RE2 |
| C9 | BAB | Alternating start with variant |
| C10 | BBA | Double variant + original anchor |

### RE3 Four-Pass Configurations
| Config | Pattern | Hypothesis |
|--------|---------|------------|
| C11 | AABB | Paired blocks |
| C12 | ABAB | Alternating |
| C13 | ABBA | Palindromic (symmetric attention) |
| C14 | BAAB | Variant sandwich |
| C15 | BABA | Alternating start with variant |

### Priority Configurations for Initial Testing
Based on theoretical reasoning, test these first:
1. **C0** (A) - Baseline
2. **C1** (AA) - RE2 baseline
3. **C2** (AB) - Minimal RE3
4. **C6** (ABA) - Symmetric three-pass
5. **C13** (ABBA) - Symmetric four-pass

If these show signal, expand to full matrix.

---

## Test Matrix Dimensions

### Task Types
| Category | Benchmark | Items | Purpose |
|----------|-----------|-------|---------|
| Arithmetic | GSM8K subset | 50 | Highly sensitive to tokenization |
| Retrieval-short | Custom NIAH (1k context) | 20 | Baseline retrieval |
| Retrieval-medium | Custom NIAH (4k context) | 20 | Medium context |
| Retrieval-long | Custom NIAH (16k context) | 20 | Long context effects |
| Reasoning | HellaSwag subset | 50 | Commonsense |
| Knowledge | MMLU subset (mixed) | 50 | General knowledge |

**Total test items:** ~210

### Full Matrix Size
- Configurations: 16 (C0-C15)
- Re-tokenization strategies: 3 (B1, B2, B3) + control
- Task categories: 6
- Items per category: ~35 average

**Worst case:** 16 configs × 4 strategies × 210 items = **13,440 runs**

### Reduction Strategy
1. **Phase 1:** Priority configs (5) × B1 only × all tasks = 1,050 runs
2. **Phase 2:** If signal found, expand promising configs × all B strategies
3. **Phase 3:** Full matrix on winning combinations only

---

## Success Metrics

### Primary Metrics
- **Accuracy:** Correct answers / total (per task type)
- **Accuracy Delta:** Performance vs C0 baseline
- **RE2 Delta:** Performance vs C1 (AA) baseline

### Secondary Metrics
- **Token cost:** Total tokens used per configuration
- **Efficiency:** Accuracy improvement per additional token
- **Consistency:** Variance across runs (if using temperature > 0)

### Statistical Requirements
- Minimum 30 samples per cell for significance testing
- Report 95% confidence intervals
- Use McNemar's test for paired accuracy comparisons

---

## Expected Outcomes

### Optimistic
- RE3 configurations outperform RE2 by 2-5%
- Specific task types show larger gains (arithmetic with digit spacing)
- Optimal configuration emerges (likely symmetric like ABA or ABBA)

### Neutral
- RE3 matches RE2 performance
- Paper contribution: systematic exploration, null result documented

### Concerning
- RE3 underperforms RE2
- Re-tokenization introduces noise rather than signal
- Would indicate tokenization consistency > variety

---

## Open Questions for Investigation

1. **Interaction effects:** Do B1+B2 combined outperform either alone?
2. **Task specificity:** Does optimal config vary by task type?
3. **Model specificity:** Do results transfer across model families?
4. **Context length scaling:** Does RE3 benefit increase/decrease with length?
5. **Instruction positioning:** Where in the prompt should the re-read instruction go?
