# Research: RE2 Technique and Evaluation Infrastructure

**Date:** 2025-01-17
**Source:** Gemini research query
**Purpose:** Foundation for RE3 paper - extending RE2 with tokenization manipulation

---

## 1. RE2 (Re-Reading) Technique

### Paper
**"Re-Reading Improves Reasoning in Large Language Models"** (Xu et al.)
- First appeared late 2023
- Gained significant traction late 2024 / January 2025

### Mechanical Operation
- Input format: `Question: [Q] Read the question again: [Q] Answer:`
- The model receives the question twice, separated by instruction

### Why It Works
In decoder-only transformers, attention is **unidirectional** (causal) - tokens can only attend to previous tokens. By repeating the prompt:
- The second pass can attend to the *entire* first pass
- Information from the end of the question is now "in the past"
- Effectively simulates **bidirectional attention**

### Improvements Demonstrated
- Consistent gains across **14 reasoning datasets** (arithmetic, commonsense, symbolic)
- Up to **5-10% improvement** on complex reasoning tasks
- Highly compatible with **Chain-of-Thought (CoT)** - additive benefits
- No model size increase required

### Limitations
- **Cost/Context:** Doubling prompt increases token count, cost, and latency
- **Redundancy:** Minimal benefit for simple retrieval or already-high-accuracy tasks
- **Diminishing returns:** Very long prompts may suffer "lost in the middle" effects even when repeated

---

## 2. Evaluation Benchmarks

### Retrieval & Long-Context Recall

| Benchmark | Description | Use Case |
|-----------|-------------|----------|
| **Needle In A Haystack (NIAH)** | Find specific fact hidden in long context (up to 128k+ tokens) | Testing recall at different context lengths |
| **RULER (NVIDIA)** | Multi-hop retrieval and aggregation; measures "effective" context length | More robust than NIAH |
| **NarrativeQA** | Complex questions requiring understanding of long stories | Long-form comprehension |

### Reasoning & General Proficiency

| Benchmark | Description | Use Case |
|-----------|-------------|----------|
| **MMLU** | 57 subjects across STEM, humanities, etc. | General knowledge/reasoning |
| **HellaSwag** | Commonsense sentence completion | Quick commonsense test |
| **GSM8K** | Grade school math word problems | Highly sensitive to RE2 and CoT |
| **TriviaQA** | Factual recall | Retrieval baseline |

### Evaluation Frameworks

| Tool | Type | Key Features |
|------|------|--------------|
| **Promptfoo** | Open-source CLI | Matrix tests in YAML, side-by-side comparison |
| **LangSmith** | Platform (LangChain) | Deep tracing, LLM-as-judge evaluators |
| **Braintrust** | Enterprise platform | Version tracking, cost/latency/quality scores |

---

## 3. Tokenization Sensitivity Research

### Capitalization Effects
- Tokenizers (BPE) assign different IDs to `Apple`, `apple`, `APPLE`
- Training data distribution affects which casing is "familiar"
- `ALL CAPS` can force unfamiliar subword fragments

### Space/Position Sensitivity
- `" hello"` (leading space) vs `"hello"` often tokenize differently
- Trailing spaces in prompts affect next-token prediction
- Critical for few-shot prompting consistency

### Special Characters
- Delimiters like `***` or `###` can "reset" attention focus
- Missing final punctuation can leave model in "continuation" vs "answering" state

### Numerical Tokenization
- Numbers tokenize inconsistently: `381` might be `[38, 1]` or `[3, 8, 1]`
- **Spacing digits** (e.g., `3 8 1`) can **improve** arithmetic
- Forces model to process each digit as distinct, stable token

---

## Key Insight for RE3

RE2 provides bidirectional attention simulation through repetition. Our extension:
- Instead of just `[A][A]`, use `[A][B]` where B is a **re-tokenized** version of A
- Hypothesis: Different tokenization passes provide complementary information
- The model gets both the bidirectional attention benefit AND multiple tokenization perspectives

### Open Questions
1. What re-tokenization strategies are most effective?
2. Does order matter? (AB vs BA vs ABA vs etc.)
3. Are there task-specific optimal configurations?
4. How do benefits scale with context length?
