# Re-Tokenization Strategy Taxonomy

## Principles

BPE tokenizers create different token sequences for superficially similar text. Different token sequences activate different model pathways. A good B variant has:
- Same semantic content as A
- Different token sequence
- Minimal semantic drift

---

## Strategy Categories

### Category 1: Token Boundary Manipulation

These change where token boundaries fall without changing characters.

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B1a | **CamelCase merge (pairs)** | Join adjacent word pairs | "the quick brown" → "theQuick brown" | All text |
| B1b | **CamelCase merge (all)** | Join all words | "the quick brown" → "theQuickBrown" | All text |
| B1c | **Underscore join** | Replace spaces with underscores | "the quick" → "the_quick" | All text |
| B1d | **Hyphenation** | Add hyphens at syllable boundaries | "understanding" → "under-standing" | All text |
| B1e | **Compound splitting** | Split compounds | "something" → "some thing" | All text |

### Category 2: Character Spacing

These add spaces to force per-character or per-unit tokenization.

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B2a | **Digit spacing** | Space between digits | "381" → "3 8 1" | Math/numbers |
| B2b | **Full character spacing** | Space between all chars | "word" → "w o r d" | Short critical terms only |
| B2c | **Acronym expansion** | Space acronyms | "NASA" → "N A S A" | Text with acronyms |

### Category 3: Case Manipulation

These change character case, which often changes token IDs.

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B3a | **Lowercase all** | Force lowercase | "Hello World" → "hello world" | All text |
| B3b | **Uppercase all** | Force uppercase | "Hello World" → "HELLO WORLD" | All text |
| B3c | **Title case** | Capitalize each word | "hello world" → "Hello World" | All text |
| B3d | **Sentence case normalize** | Only first letter caps | "Hello World" → "Hello world" | All text |

### Category 4: Delimiter Variation

These change structural markers that affect attention patterns.

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B4a | **Delimiter swap (### → ---)** | Change section markers | "### Question" → "--- Question" | Structured prompts |
| B4b | **Bullet style change** | Alter list markers | "- item" → "* item" or "• item" | Lists |
| B4c | **Quote style change** | Alter quotation marks | "word" → 'word' or «word» | Quoted text |

### Category 5: Punctuation Manipulation

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B5a | **Period to newline** | Replace periods with line breaks | "A. B." → "A\nB" | Multi-sentence |
| B5b | **Add trailing period** | Ensure period at end | "Answer" → "Answer." | All text |
| B5c | **Remove trailing period** | Remove final period | "Answer." → "Answer" | All text |

### Category 6: Numeric Representation

| ID | Strategy | Transformation | Example | Applicable To |
|----|----------|----------------|---------|---------------|
| B6a | **Digit spacing** | (same as B2a) | "42" → "4 2" | Math |
| B6b | **Word numbers** | Digits to words | "42" → "forty-two" | Math |
| B6c | **Comma insertion** | Add thousand separators | "1000" → "1,000" | Large numbers |
| B6d | **Leading zeros** | Pad numbers | "42" → "042" | Math |

---

## Phase 1 Strategy Selection

For initial testing, select strategies that:
1. Apply broadly (not just one benchmark)
2. Are clearly distinct from each other
3. Have theoretical grounding

### Proposed Phase 1 Set (10 strategies)

| Priority | ID | Strategy | Rationale |
|----------|-----|----------|-----------|
| 1 | B1a | CamelCase merge (pairs) | Classic boundary manipulation |
| 2 | B1b | CamelCase merge (all) | Aggressive boundary manipulation |
| 3 | B3a | Lowercase all | Common case normalization |
| 4 | B3b | Uppercase all | Opposite case extreme |
| 5 | B2a | Digit spacing | Known to help arithmetic |
| 6 | B1d | Hyphenation | Exposes morphological structure |
| 7 | B1c | Underscore join | Programming-style tokenization |
| 8 | B4a | Delimiter swap | Structural variation |
| 9 | B6b | Word numbers | Radical numeric representation change |
| 10 | B1e | Compound splitting | Inverse of joining |

---

## Implementation Notes

### CamelCase Variants

Multiple valid approaches:
```
Original: "the quick brown fox jumps"

B1a (pairs, random): "theQuick brown foxJumps" or "the quickBrown fox jumps"
B1a (pairs, deterministic): "theQuick brownFox jumps"  # every other pair
B1b (all): "theQuickBrownFoxJumps"
```

**Decision needed:** Random vs deterministic pairing?
- Random: More variety but less reproducible
- Deterministic: Reproducible but might miss optimal pairings

**Recommendation:** Deterministic for Phase 1 (reproducibility), explore random in Phase 2.

### Hyphenation

Requires syllable detection. Options:
- Use `pyphen` library (dictionary-based)
- Simple heuristic (split at vowel-consonant boundaries)
- Only apply to words > 6 characters

### Compound Splitting

Requires compound detection. Options:
- Dictionary lookup for known compounds
- Simple heuristic (split at common prefixes: un-, re-, pre-, etc.)
- Only apply to words > 8 characters

---

## Test Matrix Calculation

**Phase 1:**
- Configurations: 14 (all A/B patterns up to length 3)
- Strategies: 10 (as listed above)
- Benchmarks: 4 (GSM8K, MMLU, NIAH, HellaSwag)
- Items per benchmark: ~50

But not all strategies apply to all benchmarks:
- B2a (digit spacing) and B6b (word numbers): Only GSM8K
- Others: All benchmarks

**Adjusted calculation:**
- 8 universal strategies × 14 configs × 4 benchmarks × 50 items = 22,400
- 2 math strategies × 14 configs × 1 benchmark × 50 items = 1,400
- **Total: ~23,800 runs per model**

At 5 seconds average: ~33 hours per model
At 30 seconds average: ~200 hours per model

**Realistic estimate:** Mix of fast (5s) and slow (60s) → ~50-80 hours per model

---

## Multi-Model Strategy

Run full matrix on primary model first (e.g., Llama 3.1 8B). Identify top 5 configurations. Run reduced matrix on additional models.

| Phase | Scope | Runs |
|-------|-------|------|
| 1a | Full matrix, Model 1 | ~24,000 |
| 1b | Top configs, Model 2-5 | ~5,000 |
| 2 | Expanded strategies on winners | TBD |

---

## Open Questions

1. **Deterministic vs random for CamelCase pairing?**
2. **Hyphenation library or heuristic?**
3. **Which model to start with?**
4. **Run overnight or in background during day?**
