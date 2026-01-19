"""
Evaluators for RE3 benchmarks.

Each evaluator extracts an answer from model response and compares to ground truth.
"""

import re
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class EvalResult:
    """Result of evaluating a model response."""
    extracted_answer: str
    expected_answer: str
    correct: bool
    extraction_method: str
    confidence: Optional[float] = None


def evaluate_gsm8k(response: str, expected: str) -> EvalResult:
    """
    Evaluate GSM8K (math) response.

    Extracts the final number from response, comparing to expected.
    GSM8K answers are formatted with #### prefix in ground truth.

    Args:
        response: Model's response text
        expected: Ground truth (may include #### prefix)

    Returns:
        EvalResult with extracted answer and correctness
    """
    # Clean expected answer (remove #### if present)
    expected_clean = expected.strip()
    if '####' in expected_clean:
        expected_clean = expected_clean.split('####')[-1].strip()

    # Try to extract number from expected
    expected_num = re.search(r'-?\d+\.?\d*', expected_clean)
    if expected_num:
        expected_clean = expected_num.group(0)

    # Extract answer from response
    extracted = ""
    method = "none"

    # Method 1: Look for #### pattern (if model follows GSM8K format)
    match = re.search(r'####\s*(-?\d+\.?\d*)', response)
    if match:
        extracted = match.group(1)
        method = "gsm8k_format"
    else:
        # Method 2: Look for "answer is X" patterns
        match = re.search(r'(?:answer|result|total|sum)\s*(?:is|=|:)\s*(-?\d+\.?\d*)', response, re.IGNORECASE)
        if match:
            extracted = match.group(1)
            method = "answer_pattern"
        else:
            # Method 3: Take the last number in the response
            numbers = re.findall(r'-?\d+\.?\d*', response)
            if numbers:
                extracted = numbers[-1]
                method = "last_number"

    # Normalize for comparison (handle floats vs ints)
    def normalize_num(s: str) -> str:
        try:
            f = float(s)
            if f == int(f):
                return str(int(f))
            return str(f)
        except:
            return s

    extracted_norm = normalize_num(extracted)
    expected_norm = normalize_num(expected_clean)

    return EvalResult(
        extracted_answer=extracted,
        expected_answer=expected_clean,
        correct=(extracted_norm == expected_norm),
        extraction_method=method
    )


def evaluate_mmlu(response: str, expected: str, choices: list) -> EvalResult:
    """
    Evaluate MMLU (multiple choice) response.

    Args:
        response: Model's response text
        expected: Ground truth (index 0-3 or letter A-D)
        choices: List of answer choices

    Returns:
        EvalResult with extracted answer and correctness
    """
    # Normalize expected to letter
    if expected.isdigit():
        expected_letter = chr(ord('A') + int(expected))
    else:
        expected_letter = expected.upper()

    extracted = ""
    method = "none"

    # Method 1: Look for explicit letter at start or after "answer is"
    match = re.search(r'(?:answer\s*(?:is)?:?\s*)?([A-Da-d])(?:\)|\.|\s|$)', response)
    if match:
        extracted = match.group(1).upper()
        method = "letter_match"
    else:
        # Method 2: Look for the choice text in the response
        response_lower = response.lower()
        for i, choice in enumerate(choices):
            if choice.lower() in response_lower:
                extracted = chr(ord('A') + i)
                method = "choice_text_match"
                break

    if not extracted:
        # Method 3: First capital letter A-D in response
        match = re.search(r'\b([A-D])\b', response)
        if match:
            extracted = match.group(1)
            method = "first_letter"

    return EvalResult(
        extracted_answer=extracted,
        expected_answer=expected_letter,
        correct=(extracted == expected_letter),
        extraction_method=method
    )


def evaluate_hellaswag(response: str, expected: str, endings: list) -> EvalResult:
    """
    Evaluate HellaSwag (sentence completion) response.

    Args:
        response: Model's response text
        expected: Ground truth index (as string)
        endings: List of possible endings

    Returns:
        EvalResult with extracted answer and correctness
    """
    expected_idx = str(expected)

    extracted = ""
    method = "none"

    # Method 1: Look for explicit number/index
    match = re.search(r'(?:option|choice|answer)?\s*#?\s*([0-3])', response, re.IGNORECASE)
    if match:
        extracted = match.group(1)
        method = "index_match"
    else:
        # Method 2: Look for ending text in response
        response_lower = response.lower()
        for i, ending in enumerate(endings):
            # Check if substantial part of ending appears
            ending_words = ending.lower().split()[:5]  # First 5 words
            if len(ending_words) >= 3:
                snippet = ' '.join(ending_words)
                if snippet in response_lower:
                    extracted = str(i)
                    method = "ending_text_match"
                    break

    return EvalResult(
        extracted_answer=extracted,
        expected_answer=expected_idx,
        correct=(extracted == expected_idx),
        extraction_method=method
    )


def evaluate_niah(response: str, needle_content: str) -> EvalResult:
    """
    Evaluate Needle-in-a-Haystack response.

    Args:
        response: Model's response text
        needle_content: The content that should be retrieved

    Returns:
        EvalResult with extracted answer and correctness
    """
    # For NIAH, we check if the key information from the needle is present
    # The needle is typically a specific fact like "The secret number is 7392"

    extracted = response.strip()
    method = "full_response"

    # Check for presence of key needle content
    # This is a simple substring check - could be made more sophisticated
    needle_lower = needle_content.lower()
    response_lower = response.lower()

    # Extract any numbers from needle for numeric needles
    needle_numbers = re.findall(r'\d+', needle_content)

    correct = False

    if needle_numbers:
        # For numeric needles, check if the number appears in response
        for num in needle_numbers:
            if num in response:
                correct = True
                extracted = num
                method = "number_extraction"
                break
    else:
        # For text needles, check for substantial overlap
        # Extract key phrases (words > 4 chars)
        key_words = [w for w in needle_content.split() if len(w) > 4]
        matches = sum(1 for w in key_words if w.lower() in response_lower)
        if matches >= len(key_words) * 0.5:  # 50% of key words present
            correct = True
            method = "keyword_overlap"

    return EvalResult(
        extracted_answer=extracted[:100],  # Truncate for storage
        expected_answer=needle_content[:100],
        correct=correct,
        extraction_method=method
    )


# Registry of evaluators by benchmark type
EVALUATORS = {
    'gsm8k': evaluate_gsm8k,
    'mmlu': evaluate_mmlu,
    'hellaswag': evaluate_hellaswag,
    'niah': evaluate_niah,
}


def evaluate(benchmark: str, response: str, expected: str, **kwargs) -> EvalResult:
    """
    Evaluate a response for the given benchmark.

    Args:
        benchmark: Benchmark name ('gsm8k', 'mmlu', 'hellaswag', 'niah')
        response: Model's response text
        expected: Ground truth answer
        **kwargs: Additional args (choices for MMLU, endings for HellaSwag, etc.)

    Returns:
        EvalResult with extracted answer and correctness
    """
    if benchmark not in EVALUATORS:
        raise ValueError(f"Unknown benchmark: {benchmark}. Available: {list(EVALUATORS.keys())}")

    evaluator = EVALUATORS[benchmark]

    if benchmark == 'mmlu':
        return evaluator(response, expected, kwargs.get('choices', []))
    elif benchmark == 'hellaswag':
        return evaluator(response, expected, kwargs.get('endings', []))
    elif benchmark == 'niah':
        return evaluator(response, kwargs.get('needle_content', expected))
    else:
        return evaluator(response, expected)


if __name__ == "__main__":
    # Test evaluators
    print("Testing GSM8K evaluator:")
    result = evaluate_gsm8k(
        "Let me solve this step by step. 5 + 3 = 8. So the answer is 8.",
        "#### 8"
    )
    print(f"  Extracted: {result.extracted_answer}, Correct: {result.correct}")

    print("\nTesting MMLU evaluator:")
    result = evaluate_mmlu(
        "The answer is B because...",
        "1",  # Index 1 = B
        ["Option A", "Option B", "Option C", "Option D"]
    )
    print(f"  Extracted: {result.extracted_answer}, Correct: {result.correct}")

    print("\nTesting NIAH evaluator:")
    result = evaluate_niah(
        "Based on the context, the secret number mentioned was 7392.",
        "The secret number is 7392"
    )
    print(f"  Extracted: {result.extracted_answer}, Correct: {result.correct}")
