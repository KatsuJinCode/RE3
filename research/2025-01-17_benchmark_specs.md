# Benchmark Dataset Specifications

**Date:** 2025-01-17
**Source:** Gemini research
**Purpose:** Technical specs for harness implementation

---

## 1. GSM8K (Grade School Math 8K)

### Access
- **HuggingFace:** `openai/gsm8k`
- **Config:** `main`
- **Split:** `test` (1,319 items)

### Structure
```json
{
  "question": "Janet's ducks lay 16 eggs per day...",
  "answer": "Janet sells 16 - 3 - 4 = <<16-3-4=9>>9 duck eggs a day...\n#### 18"
}
```

### Answer Extraction
Final answer prefixed with `####`. Parse: `re.search(r'####\s*(\d+)', answer).group(1)`

### Loading Code
```python
from datasets import load_dataset
dataset = load_dataset("openai/gsm8k", "main", split="test")
subset = dataset.select(range(50))  # Phase 1 subset
```

---

## 2. MMLU (Massive Multitask Language Understanding)

### Access
- **HuggingFace:** `cais/mmlu`
- **Config:** Subject name (e.g., `abstract_algebra`, `college_medicine`)
- **57 subjects total**

### Structure
```json
{
  "question": "Find the degree for the given field extension...",
  "choices": ["0", "2", "4", "6"],
  "answer": 1  // Index into choices (0-3 maps to A-D)
}
```

### Answer Extraction
Convert index to letter: `chr(ord('A') + answer)`

### Loading Code
```python
from datasets import load_dataset

# Load multiple subjects for diversity
subjects = ['abstract_algebra', 'anatomy', 'astronomy', 'college_physics', 'world_religions']
items = []
for subj in subjects:
    ds = load_dataset("cais/mmlu", subj, split="test")
    items.extend(ds.select(range(10)))  # 10 per subject = 50 total
```

---

## 3. Needle in a Haystack (NIAH)

### Access
- **Synthetic** - no standard HuggingFace dataset
- **Reference Implementation:** https://github.com/gkamradt/LLMTest_NeedleInAHaystack
- **Haystack Source:** Paul Graham essays (available in repo)

### Standard Approach
1. **Needle:** Distinctive fact unrelated to haystack content
   - Classic: "The best thing to do in San Francisco is eat a sandwich and sit in Dolores Park on a sunny day."
2. **Haystack:** Filler text (essays, random text) to target token count
3. **Depth:** Insert needle at specified percentage through the context
4. **Query:** Question specifically about the needle

### Generation Parameters
| Parameter | Values to Test |
|-----------|---------------|
| Context length | 1k, 4k, 8k, 16k tokens |
| Needle depth | 10%, 25%, 50%, 75%, 90% |

### Synthetic Generator
```python
def create_niah_item(needle: str, question: str, haystack_text: str,
                     target_tokens: int, depth_percent: float) -> dict:
    """
    Returns:
        {
            "prompt": assembled context with needle,
            "question": question about needle,
            "expected": answer extracted from needle,
            "depth": depth_percent,
            "context_tokens": actual token count
        }
    """
    # Truncate/expand haystack to target - needle length
    # Insert needle at depth_percent position
    # Append question
    pass
```

---

## 4. HellaSwag

### Access
- **HuggingFace:** `Rowan/hellaswag`
- **Split:** `train` or `validation`

### Structure
```json
{
  "ctx": "A woman is outside with a bucket and a dog...",
  "endings": [
    "She continues to walk the dog.",
    "She throws the ball at the dog.",
    "She pours water on the dog.",
    "She puts on a leash on the dog."
  ],
  "label": "2"  // String index of correct ending
}
```

### Answer Extraction
Match response to endings, or check if model outputs correct index.

### Loading Code
```python
from datasets import load_dataset
dataset = load_dataset("Rowan/hellaswag", split="validation")
subset = dataset.select(range(50))
```

---

## Phase 1 Dataset Composition

| Benchmark | Source | Items | Purpose |
|-----------|--------|-------|---------|
| GSM8K | HuggingFace | 50 | Arithmetic (tokenization-sensitive) |
| MMLU | HuggingFace (5 subjects) | 50 | Knowledge/reasoning diversity |
| NIAH-1k | Synthetic | 20 | Short context retrieval |
| NIAH-4k | Synthetic | 20 | Medium context retrieval |
| HellaSwag | HuggingFace | 50 | Commonsense baseline |

**Total: 190 items per configuration**
**14 configurations × 190 items = 2,660 runs (Phase 1)**

---

## Dependencies

```bash
pip install datasets transformers
```

Note: HuggingFace datasets library handles download/caching automatically.
