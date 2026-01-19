"""
RE3 Test Orchestrator

Runs the full test matrix: configurations × strategies × benchmarks × items
Uses Option C ordering: complete each (config, strategy, benchmark) slice before moving on.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
from dataclasses import dataclass
import json

# Add harness to path
sys.path.insert(0, str(Path(__file__).parent))

from llm_interface import send_prompt, check_gateway_status, LLMResponse
from retokenizers import apply_transform, TRANSFORMERS, MATH_ONLY_STRATEGIES
from evaluators import evaluate, EvalResult
from data_recorder import DataRecorder, estimate_tokens
from batch_runner import BatchRunner, BatchResponse
from progress import ProgressTracker, SliceStatus, get_priority_slices


# ============================================================================
# CONFIGURATION DEFINITIONS
# ============================================================================

@dataclass
class Config:
    """Test configuration (pattern of A and B passes)."""
    id: str
    pattern: str  # e.g., "ABA"

    @property
    def length(self) -> int:
        return len(self.pattern)

    @property
    def uses_b(self) -> bool:
        return 'B' in self.pattern


# All 14 configurations: exhaustive A/B combinations up to length 3
CONFIGURATIONS = [
    # Length 1
    Config("C01", "A"),
    Config("C02", "B"),
    # Length 2
    Config("C03", "AA"),
    Config("C04", "AB"),
    Config("C05", "BA"),
    Config("C06", "BB"),
    # Length 3
    Config("C07", "AAA"),
    Config("C08", "AAB"),
    Config("C09", "ABA"),
    Config("C10", "ABB"),
    Config("C11", "BAA"),
    Config("C12", "BAB"),
    Config("C13", "BBA"),
    Config("C14", "BBB"),
]

CONFIG_BY_ID = {c.id: c for c in CONFIGURATIONS}

# Default separator between passes
DEFAULT_SEPARATOR = "\n\nRead the question again:\n\n"


# ============================================================================
# PROMPT ASSEMBLY
# ============================================================================

def assemble_prompt(prompt_a: str,
                    prompt_b: Optional[str],
                    pattern: str,
                    separator: str = DEFAULT_SEPARATOR) -> str:
    """
    Assemble final prompt from A, B, and pattern.

    Args:
        prompt_a: Original prompt
        prompt_b: Re-tokenized prompt (can be None if pattern is all A's)
        pattern: Pattern like "ABA"
        separator: Text between repetitions

    Returns:
        Assembled prompt string
    """
    parts = []
    for char in pattern:
        if char == 'A':
            parts.append(prompt_a)
        elif char == 'B':
            if prompt_b is None:
                raise ValueError(f"Pattern '{pattern}' requires B but prompt_b is None")
            parts.append(prompt_b)
        else:
            raise ValueError(f"Invalid pattern character: {char}")

    return separator.join(parts)


# ============================================================================
# BENCHMARK LOADING
# ============================================================================

def load_gsm8k_subset(n: int = 50) -> List[Dict[str, Any]]:
    """Load GSM8K subset. Returns list of {question, answer, id}."""
    try:
        from datasets import load_dataset
        ds = load_dataset("openai/gsm8k", "main", split="test")
        items = []
        for i, item in enumerate(ds):
            if i >= n:
                break
            items.append({
                'id': f"gsm8k_test_{i}",
                'question': item['question'],
                'answer': item['answer'],
                'benchmark': 'gsm8k',
            })
        return items
    except ImportError:
        print("WARNING: datasets library not installed. Using placeholder data.")
        return _placeholder_gsm8k(n)


def load_mmlu_subset(n: int = 50) -> List[Dict[str, Any]]:
    """Load MMLU subset across multiple subjects."""
    try:
        from datasets import load_dataset
        subjects = ['abstract_algebra', 'anatomy', 'astronomy', 'college_physics', 'world_religions']
        items_per_subject = n // len(subjects)
        items = []
        idx = 0
        for subj in subjects:
            ds = load_dataset("cais/mmlu", subj, split="test")
            for i, item in enumerate(ds):
                if i >= items_per_subject:
                    break
                items.append({
                    'id': f"mmlu_{subj}_{i}",
                    'question': item['question'],
                    'choices': item['choices'],
                    'answer': str(item['answer']),
                    'benchmark': 'mmlu',
                    'subset': subj,
                })
                idx += 1
        return items
    except ImportError:
        print("WARNING: datasets library not installed. Using placeholder data.")
        return _placeholder_mmlu(n)


def load_hellaswag_subset(n: int = 50) -> List[Dict[str, Any]]:
    """Load HellaSwag subset."""
    try:
        from datasets import load_dataset
        ds = load_dataset("Rowan/hellaswag", split="validation")
        items = []
        for i, item in enumerate(ds):
            if i >= n:
                break
            items.append({
                'id': f"hellaswag_{i}",
                'context': item['ctx'],
                'endings': item['endings'],
                'answer': str(item['label']),
                'benchmark': 'hellaswag',
            })
        return items
    except ImportError:
        print("WARNING: datasets library not installed. Using placeholder data.")
        return _placeholder_hellaswag(n)


def load_niah_synthetic(n: int = 20, context_tokens: int = 1000) -> List[Dict[str, Any]]:
    """Generate synthetic Needle-in-a-Haystack items."""
    import random
    items = []

    # Filler text (simple repetitive content)
    filler = "The quick brown fox jumps over the lazy dog. " * 50

    for i in range(n):
        # Generate random needle
        secret_num = random.randint(1000, 9999)
        needle = f"The secret code for this document is {secret_num}."
        question = "What is the secret code mentioned in the document?"

        # Calculate filler needed
        needle_tokens = estimate_tokens(needle)
        question_tokens = estimate_tokens(question)
        filler_tokens_needed = context_tokens - needle_tokens - question_tokens

        # Truncate filler to fit
        filler_chars = max(100, filler_tokens_needed * 4)
        truncated_filler = filler[:filler_chars]

        # Insert needle at random position
        depth = random.random()
        insert_pos = int(len(truncated_filler) * depth)
        context = truncated_filler[:insert_pos] + " " + needle + " " + truncated_filler[insert_pos:]

        items.append({
            'id': f"niah_{context_tokens}_{i}",
            'context': context,
            'question': question,
            'needle': needle,
            'needle_content': str(secret_num),
            'depth': depth,
            'benchmark': 'niah',
            'subset': f'{context_tokens}tok',
        })

    return items


# Placeholder functions for when datasets library isn't available
def _placeholder_gsm8k(n: int) -> List[Dict[str, Any]]:
    return [{
        'id': f"gsm8k_placeholder_{i}",
        'question': f"What is {i+1} + {i+2}?",
        'answer': f"#### {i+1 + i+2}",
        'benchmark': 'gsm8k',
    } for i in range(n)]


def _placeholder_mmlu(n: int) -> List[Dict[str, Any]]:
    return [{
        'id': f"mmlu_placeholder_{i}",
        'question': f"What is the capital of country {i}?",
        'choices': ['Paris', 'London', 'Berlin', 'Madrid'],
        'answer': str(i % 4),
        'benchmark': 'mmlu',
        'subset': 'placeholder',
    } for i in range(n)]


def _placeholder_hellaswag(n: int) -> List[Dict[str, Any]]:
    return [{
        'id': f"hellaswag_placeholder_{i}",
        'context': f"A person walks into a room and...",
        'endings': ['sits down', 'leaves', 'jumps', 'sleeps'],
        'answer': str(i % 4),
        'benchmark': 'hellaswag',
    } for i in range(n)]


# ============================================================================
# PROMPT FORMATTING PER BENCHMARK
# ============================================================================

def format_prompt(item: Dict[str, Any]) -> str:
    """Format benchmark item into prompt for the model."""
    benchmark = item['benchmark']

    if benchmark == 'gsm8k':
        return f"Solve this math problem step by step, then give your final answer after ####.\n\nProblem: {item['question']}"

    elif benchmark == 'mmlu':
        choices_str = "\n".join(f"{chr(65+i)}. {c}" for i, c in enumerate(item['choices']))
        return f"Answer the following multiple choice question. Reply with just the letter (A, B, C, or D).\n\nQuestion: {item['question']}\n\n{choices_str}"

    elif benchmark == 'hellaswag':
        endings_str = "\n".join(f"{i}. {e}" for i, e in enumerate(item['endings']))
        return f"Complete the sentence. Reply with just the number (0, 1, 2, or 3).\n\nContext: {item['context']}\n\nOptions:\n{endings_str}"

    elif benchmark == 'niah':
        return f"Read the following document carefully, then answer the question.\n\nDocument:\n{item['context']}\n\nQuestion: {item['question']}"

    else:
        raise ValueError(f"Unknown benchmark: {benchmark}")


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_single_test(item: Dict[str, Any],
                    config: Config,
                    strategy: str,
                    recorder: DataRecorder,
                    separator: str = DEFAULT_SEPARATOR) -> bool:
    """
    Run a single test and record the result.

    Returns:
        True if test completed (even if answer wrong), False if error
    """
    benchmark = item['benchmark']

    # Format prompt A
    prompt_a = format_prompt(item)

    # Generate prompt B if needed
    prompt_b = None
    if config.uses_b:
        prompt_b = apply_transform(prompt_a, strategy)

    # Assemble final prompt
    try:
        assembled = assemble_prompt(prompt_a, prompt_b, config.pattern, separator)
    except ValueError as e:
        recorder.record(
            config_id=config.id,
            pattern=config.pattern,
            pattern_length=config.length,
            b_strategy=strategy,
            benchmark=benchmark,
            benchmark_subset=item.get('subset'),
            item_id=item['id'],
            item_index=0,
            prompt_a=prompt_a,
            prompt_b=prompt_b,
            assembled_prompt="",
            separator=separator,
            tokens_a=estimate_tokens(prompt_a),
            tokens_b=estimate_tokens(prompt_b) if prompt_b else None,
            tokens_total_input=0,
            tokens_output=0,
            temperature=0.0,
            response_raw="",
            response_truncated=False,
            latency_ms=0,
            expected_answer=item.get('answer', ''),
            extracted_answer="",
            extraction_method="error",
            correct=False,
            error=str(e),
            notes=None,
        )
        return False

    # Send to LLM
    response = send_prompt(assembled, temperature=0.0)

    if response.error:
        recorder.record(
            config_id=config.id,
            pattern=config.pattern,
            pattern_length=config.length,
            b_strategy=strategy,
            benchmark=benchmark,
            benchmark_subset=item.get('subset'),
            item_id=item['id'],
            item_index=0,
            prompt_a=prompt_a,
            prompt_b=prompt_b,
            assembled_prompt=assembled,
            separator=separator,
            tokens_a=estimate_tokens(prompt_a),
            tokens_b=estimate_tokens(prompt_b) if prompt_b else None,
            tokens_total_input=estimate_tokens(assembled),
            tokens_output=0,
            temperature=0.0,
            response_raw="",
            response_truncated=False,
            latency_ms=response.latency_ms,
            expected_answer=item.get('answer', ''),
            extracted_answer="",
            extraction_method="error",
            correct=False,
            error=response.error,
            notes=None,
        )
        return False

    # Evaluate response
    eval_kwargs = {}
    if benchmark == 'mmlu':
        eval_kwargs['choices'] = item['choices']
    elif benchmark == 'hellaswag':
        eval_kwargs['endings'] = item['endings']
    elif benchmark == 'niah':
        eval_kwargs['needle_content'] = item.get('needle_content', item.get('needle', ''))

    eval_result = evaluate(
        benchmark=benchmark,
        response=response.text,
        expected=item.get('answer', item.get('needle_content', '')),
        **eval_kwargs
    )

    # Record result
    recorder.record(
        config_id=config.id,
        pattern=config.pattern,
        pattern_length=config.length,
        b_strategy=strategy,
        benchmark=benchmark,
        benchmark_subset=item.get('subset'),
        item_id=item['id'],
        item_index=0,
        prompt_a=prompt_a,
        prompt_b=prompt_b,
        assembled_prompt=assembled,
        separator=separator,
        tokens_a=estimate_tokens(prompt_a),
        tokens_b=estimate_tokens(prompt_b) if prompt_b else None,
        tokens_total_input=estimate_tokens(assembled),
        tokens_output=estimate_tokens(response.text),
        temperature=0.0,
        response_raw=response.text,
        response_truncated=False,
        latency_ms=response.latency_ms,
        expected_answer=eval_result.expected_answer,
        extracted_answer=eval_result.extracted_answer,
        extraction_method=eval_result.extraction_method,
        correct=eval_result.correct,
        error=None,
        notes=None,
    )

    return True


@dataclass
class TestJob:
    """A prepared test job for batched execution."""
    config: Config
    strategy: str
    benchmark: str
    item: Dict[str, Any]
    prompt_a: str
    prompt_b: Optional[str]
    assembled: str
    separator: str


def prepare_test_job(item: Dict[str, Any],
                     config: Config,
                     strategy: str,
                     separator: str = DEFAULT_SEPARATOR) -> TestJob:
    """Prepare a test job (prompt assembly) without sending to LLM."""
    benchmark = item['benchmark']
    prompt_a = format_prompt(item)

    prompt_b = None
    if config.uses_b:
        prompt_b = apply_transform(prompt_a, strategy)

    assembled = assemble_prompt(prompt_a, prompt_b, config.pattern, separator)

    return TestJob(
        config=config,
        strategy=strategy,
        benchmark=benchmark,
        item=item,
        prompt_a=prompt_a,
        prompt_b=prompt_b,
        assembled=assembled,
        separator=separator,
    )


def record_batch_result(job: TestJob,
                        response: BatchResponse,
                        recorder: DataRecorder) -> bool:
    """Record result from a batch response. Returns True if successful."""
    item = job.item
    benchmark = job.benchmark

    if response.error:
        recorder.record(
            config_id=job.config.id,
            pattern=job.config.pattern,
            pattern_length=job.config.length,
            b_strategy=job.strategy,
            benchmark=benchmark,
            benchmark_subset=item.get('subset'),
            item_id=item['id'],
            item_index=0,
            prompt_a=job.prompt_a,
            prompt_b=job.prompt_b,
            assembled_prompt=job.assembled,
            separator=job.separator,
            tokens_a=estimate_tokens(job.prompt_a),
            tokens_b=estimate_tokens(job.prompt_b) if job.prompt_b else None,
            tokens_total_input=estimate_tokens(job.assembled),
            tokens_output=0,
            temperature=0.0,
            response_raw="",
            response_truncated=False,
            latency_ms=response.latency_ms,
            expected_answer=item.get('answer', ''),
            extracted_answer="",
            extraction_method="error",
            correct=False,
            error=response.error,
            notes=None,
        )
        return False

    # Evaluate response
    eval_kwargs = {}
    if benchmark == 'mmlu':
        eval_kwargs['choices'] = item['choices']
    elif benchmark == 'hellaswag':
        eval_kwargs['endings'] = item['endings']
    elif benchmark == 'niah':
        eval_kwargs['needle_content'] = item.get('needle_content', item.get('needle', ''))

    eval_result = evaluate(
        benchmark=benchmark,
        response=response.text,
        expected=item.get('answer', item.get('needle_content', '')),
        **eval_kwargs
    )

    recorder.record(
        config_id=job.config.id,
        pattern=job.config.pattern,
        pattern_length=job.config.length,
        b_strategy=job.strategy,
        benchmark=benchmark,
        benchmark_subset=item.get('subset'),
        item_id=item['id'],
        item_index=0,
        prompt_a=job.prompt_a,
        prompt_b=job.prompt_b,
        assembled_prompt=job.assembled,
        separator=job.separator,
        tokens_a=estimate_tokens(job.prompt_a),
        tokens_b=estimate_tokens(job.prompt_b) if job.prompt_b else None,
        tokens_total_input=estimate_tokens(job.assembled),
        tokens_output=estimate_tokens(response.text),
        temperature=0.0,
        response_raw=response.text,
        response_truncated=False,
        latency_ms=response.latency_ms,
        expected_answer=eval_result.expected_answer,
        extracted_answer=eval_result.extracted_answer,
        extraction_method=eval_result.extraction_method,
        correct=eval_result.correct,
        error=None,
        notes=None,
    )

    return True


def iterate_test_matrix(configs: List[Config],
                        strategies: List[str],
                        benchmarks: Dict[str, List[Dict]]) -> Iterator[tuple]:
    """
    Generate test matrix in Option C order.

    Yields:
        (config, strategy, benchmark_name, item)
    """
    for config in configs:
        for strategy in strategies:
            # Skip 'none' strategy for configs that use B
            if strategy == 'none' and config.uses_b:
                continue
            # Skip non-none strategies for configs that don't use B
            if strategy != 'none' and not config.uses_b:
                continue

            for benchmark_name, items in benchmarks.items():
                # Skip math-only strategies for non-math benchmarks
                if strategy in MATH_ONLY_STRATEGIES and benchmark_name != 'gsm8k':
                    continue

                for item in items:
                    yield (config, strategy, benchmark_name, item)


def format_time(seconds: float) -> str:
    """Format seconds as human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m{s:02d}s"
    else:
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        return f"{h}h{m:02d}m"


def run_batched_tests(configs: List[Config],
                      strategies: List[str],
                      benchmarks: Dict[str, List[Dict]],
                      recorder: DataRecorder,
                      max_pending: int = 4,
                      separator: str = DEFAULT_SEPARATOR) -> None:
    """
    Run tests using batched execution for efficient LLM utilization.

    Maintains queue depth of max_pending to keep LLM continuously busy.
    Outputs line-item receipt with running stats.
    """
    import time as time_module

    # Build all jobs first
    jobs = []
    for config, strategy, benchmark_name, item in iterate_test_matrix(configs, strategies, benchmarks):
        job = prepare_test_job(item, config, strategy, separator)
        jobs.append(job)

    total = len(jobs)

    # Print header
    print()
    print("=" * 70)
    print(f"  RE3 TEST RUN - {total} tests")
    print("=" * 70)
    print(f"  Mode: Batched (max_pending={max_pending})")
    print(f"  Configs: {', '.join(c.id for c in configs)}")
    print("=" * 70)
    print()

    runner = BatchRunner(max_pending=max_pending, temperature=0.0)

    completed = 0
    correct_count = 0
    error_count = 0
    job_index = 0
    start_time = time_module.time()
    total_latency_ms = 0

    # Track current slice for context
    current_slice = None

    # Submit initial batch
    while job_index < len(jobs) and runner.pending_count() < max_pending:
        job = jobs[job_index]
        runner.submit(job.assembled, context=job)
        job_index += 1

    # Process results and submit more
    while completed < total:
        result = runner.get_result(block=True)
        if result is None:
            break

        job = result.context

        # SANITY CHECK: 0ms latency means harness failure, not a real result
        if result.latency_ms == 0 or (result.latency_ms < 50 and result.error):
            result.error = f"Invalid result (latency={result.latency_ms}ms): {result.error or 'instant failure'}"

        success = record_batch_result(job, result, recorder)

        completed += 1
        total_latency_ms += result.latency_ms

        # Track slice changes
        slice_id = f"{job.config.id}|{job.strategy}|{job.benchmark}"
        if slice_id != current_slice:
            current_slice = slice_id
            print(f"\n--- Slice: {slice_id} ---")

        # Determine status
        if not success:
            status_icon = "ERR"
            error_count += 1
        elif recorder.records[-1].correct:
            status_icon = "ok"
            correct_count += 1
        else:
            status_icon = "--"

        # Calculate running stats
        accuracy = correct_count / completed if completed > 0 else 0
        elapsed = time_module.time() - start_time
        avg_time = elapsed / completed if completed > 0 else 0
        eta = avg_time * (total - completed)

        # Format line-item receipt
        # Format: [N/Total] item_id ... status (Xms) | running: X/Y = Z% | elapsed: T, eta: T
        item_short = job.item['id'].replace('gsm8k_test_', 'g').replace('mmlu_', 'm').replace('hellaswag_', 'h').replace('niah_', 'n')

        print(f"  [{completed:4d}/{total}] {item_short:12s} {status_icon:3s} ({result.latency_ms:5d}ms) | "
              f"acc: {correct_count}/{completed}={accuracy:5.1%} | "
              f"elapsed: {format_time(elapsed)}, eta: {format_time(eta)}")

        # Submit next job if available
        if job_index < len(jobs):
            next_job = jobs[job_index]
            runner.submit(next_job.assembled, context=next_job)
            job_index += 1

    # Final summary
    elapsed = time_module.time() - start_time
    avg_latency = total_latency_ms / completed if completed > 0 else 0

    print()
    print("=" * 70)
    print("  COMPLETED")
    print("=" * 70)
    print(f"  Total:    {completed} tests")
    print(f"  Correct:  {correct_count} ({correct_count/completed:.1%})" if completed > 0 else "  Correct:  0")
    print(f"  Errors:   {error_count}")
    print(f"  Duration: {format_time(elapsed)}")
    print(f"  Avg time: {avg_latency:.0f}ms per test")
    print("=" * 70)

    # SANITY CHECK: Detect catastrophic failure (all instant errors)
    if completed > 0 and error_count == completed and avg_latency < 100:
        print()
        print("!" * 70)
        print("  SANITY CHECK FAILED - RUN INVALIDATED")
        print("!" * 70)
        print("  All tests failed instantly (<100ms avg latency, 100% errors).")
        print("  This indicates a harness/connection problem, not test results.")
        print("  Data has been cleared. Fix the issue and retry.")
        print("!" * 70)
        recorder.records.clear()
        raise RuntimeError("Sanity check failed: all tests failed instantly")


def run_smoke_test(data_dir: Path) -> bool:
    """
    Run minimal smoke test to verify harness works.

    Tests: 1 config (baseline) × 5 GSM8K items
    """
    print("=" * 60)
    print("SMOKE TEST")
    print("=" * 60)

    # Check gateway
    print("\nChecking gateway status...")
    status = check_gateway_status()
    print(f"  {status['message']}")
    if not status['ok']:
        print("ERROR: Gateway not available. Cannot proceed.")
        return False

    # Load minimal data
    print("\nLoading test data (5 items)...")
    items = load_gsm8k_subset(5)
    print(f"  Loaded {len(items)} items")

    # Setup recorder
    recorder = DataRecorder(data_dir, phase=0, model_id="smoke_test")

    # Run baseline config only
    config = CONFIG_BY_ID["C01"]
    strategy = "none"

    print(f"\nRunning {len(items)} tests with config {config.id} ({config.pattern})...")

    for i, item in enumerate(items):
        print(f"  [{i+1}/{len(items)}] {item['id']}...", end=" ", flush=True)
        success = run_single_test(item, config, strategy, recorder)
        if success:
            last_record = recorder.records[-1]
            status_str = "CORRECT" if last_record.correct else "WRONG"
            print(f"{status_str} ({last_record.latency_ms}ms)")
        else:
            print("ERROR")

    # Report
    stats = recorder.get_stats()
    print(f"\n{'=' * 60}")
    print("SMOKE TEST RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total runs: {stats['total']}")
    print(f"  Successful: {stats['valid']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Correct: {stats['correct']}")
    print(f"  Accuracy: {stats['accuracy']:.1%}")

    if stats['errors'] == 0 and stats['valid'] > 0:
        print("\nSMOKE TEST PASSED - Harness is working!")
        return True
    else:
        print("\nSMOKE TEST FAILED - Check errors above")
        return False


def run_slice(slice_id: str,
              data_dir: Path,
              n: int = 50,
              max_pending: int = 4,
              progress_file: str = "progress.json") -> bool:
    """
    Run a single slice with progress tracking.

    Args:
        slice_id: Slice ID in format "CONFIG_STRATEGY_BENCHMARK"
        data_dir: Directory for output data
        n: Number of items to test
        max_pending: Queue depth for batching
        progress_file: Path to progress.json

    Returns:
        True if successful, False if error
    """
    import time as time_module

    # Parse slice ID
    parts = slice_id.split('_')
    if len(parts) < 3:
        print(f"ERROR: Invalid slice_id format: {slice_id}")
        return False

    config_id = parts[0]
    benchmark = parts[-1]
    strategy = '_'.join(parts[1:-1])

    if config_id not in CONFIG_BY_ID:
        print(f"ERROR: Unknown config: {config_id}")
        return False

    config = CONFIG_BY_ID[config_id]

    # Initialize progress tracker
    tracker = ProgressTracker(progress_file)
    tracker.load()

    # Check if already done
    slice_info = tracker.get_slice(slice_id)
    if slice_info is None:
        print(f"ERROR: Slice not found: {slice_id}")
        return False

    if slice_info.status == SliceStatus.COMPLETED:
        print(f"Slice already completed: {slice_id}")
        return True

    # Claim if not already claimed by us
    if slice_info.status == SliceStatus.PENDING:
        claimed = tracker.claim(slice_id)
        if not claimed:
            print(f"ERROR: Could not claim slice: {slice_id}")
            return False

    # Mark as running
    tracker.start(slice_id)

    print()
    print("=" * 70)
    print(f"  SLICE: {slice_id}")
    print(f"  Config: {config_id} ({config.pattern})")
    print(f"  Strategy: {strategy}")
    print(f"  Benchmark: {benchmark}")
    print("=" * 70)

    # Check gateway
    print("\nChecking gateway...")
    status = check_gateway_status()
    if not status['ok']:
        print(f"ERROR: Gateway not available: {status['message']}")
        tracker.fail(slice_id, "Gateway not available")
        return False
    print(f"  {status['message']}")

    # Load benchmark data
    print(f"\nLoading {benchmark} ({n} items)...")
    if benchmark == 'gsm8k':
        items = load_gsm8k_subset(n)
    elif benchmark == 'mmlu':
        items = load_mmlu_subset(n)
    elif benchmark == 'hellaswag':
        items = load_hellaswag_subset(n)
    elif benchmark == 'niah':
        items = load_niah_synthetic(n // 2)
    else:
        print(f"ERROR: Unknown benchmark: {benchmark}")
        tracker.fail(slice_id, f"Unknown benchmark: {benchmark}")
        return False

    print(f"  Loaded {len(items)} items")

    # Setup recorder
    recorder = DataRecorder(data_dir, phase=1, model_id="local")

    # Run batched tests for this slice
    configs = [config]
    strategies = [strategy]
    benchmarks_dict = {benchmark: items}

    try:
        run_batched_tests(configs, strategies, benchmarks_dict, recorder, max_pending=max_pending)

        # Get final stats
        stats = recorder.get_stats()

        # Mark complete
        tracker.complete(slice_id, {
            'total': stats['total'],
            'correct': stats['correct'],
            'errors': stats['errors'],
            'accuracy': stats['accuracy'],
            'mean_latency_ms': sum(r.latency_ms for r in recorder.records) // len(recorder.records) if recorder.records else 0,
        }, results_file=str(recorder.jsonl_path))

        # Generate summary
        summary_path = recorder.generate_summary()
        print(f"\nSummary: {summary_path}")
        print(f"Raw data: {recorder.jsonl_path}")

        # Show updated progress
        tracker.display_progress()

        return True

    except Exception as e:
        tracker.fail(slice_id, str(e))
        print(f"ERROR: {e}")
        return False


def run_next_slice(data_dir: Path,
                   n: int = 50,
                   max_pending: int = 4,
                   reverse: bool = False,
                   priority: bool = True,
                   progress_file: str = "progress.json") -> bool:
    """
    Claim and run the next available slice.

    Args:
        reverse: Start from end of list (for worker 2)
        priority: Use priority ordering (Phase 1A first)
    """
    tracker = ProgressTracker(progress_file)
    tracker.load()

    # Get priority order if requested
    priority_order = get_priority_slices("1a") if priority else None

    # Claim next
    slice_info = tracker.claim_next(priority_order=priority_order, reverse=reverse)

    if slice_info is None:
        print("No slices available to claim.")
        tracker.display_progress()
        return False

    print(f"Claimed: {slice_info.slice_id}")
    return run_slice(slice_info.slice_id, data_dir, n, max_pending, progress_file)


def main():
    parser = argparse.ArgumentParser(description="RE3 Test Harness")
    parser.add_argument('--smoke', action='store_true', help="Run smoke test only")
    parser.add_argument('--phase', type=int, default=1, help="Experiment phase")
    parser.add_argument('--config', type=str, help="Specific config ID to run (e.g., C01)")
    parser.add_argument('--strategy', type=str, help="Specific strategy to run")
    parser.add_argument('--benchmark', type=str, help="Specific benchmark to run")
    parser.add_argument('--n', type=int, default=50, help="Items per benchmark")
    parser.add_argument('--data-dir', type=str, default='./data', help="Data directory")
    parser.add_argument('--model-id', type=str, default='local', help="Model identifier for logging")
    parser.add_argument('--batch', action='store_true', help="Use batched execution for efficiency")
    parser.add_argument('--max-pending', type=int, default=4, help="Max concurrent requests in batch mode")

    # Slice-based execution (for distributed runs)
    parser.add_argument('--slice', type=str, help="Run specific slice (e.g., C01_none_gsm8k)")
    parser.add_argument('--next', action='store_true', help="Claim and run next available slice")
    parser.add_argument('--reverse', action='store_true', help="Start from end (for worker 2)")
    parser.add_argument('--progress-file', type=str, default='progress.json', help="Progress tracking file")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Slice-based execution modes
    if args.slice:
        success = run_slice(args.slice, data_dir, args.n, args.max_pending, args.progress_file)
        sys.exit(0 if success else 1)

    if args.next:
        success = run_next_slice(data_dir, args.n, args.max_pending, args.reverse, True, args.progress_file)
        sys.exit(0 if success else 1)

    if args.smoke:
        success = run_smoke_test(data_dir)
        sys.exit(0 if success else 1)

    # Full test run
    print("=" * 60)
    print(f"RE3 TEST HARNESS - Phase {args.phase}")
    print("=" * 60)

    # Check gateway
    print("\nChecking gateway status...")
    status = check_gateway_status()
    print(f"  {status['message']}")
    if not status['ok']:
        print("ERROR: Gateway not available.")
        sys.exit(1)

    # Load benchmarks
    print(f"\nLoading benchmarks ({args.n} items each)...")
    benchmarks = {}

    if not args.benchmark or args.benchmark == 'gsm8k':
        benchmarks['gsm8k'] = load_gsm8k_subset(args.n)
        print(f"  gsm8k: {len(benchmarks['gsm8k'])} items")

    if not args.benchmark or args.benchmark == 'mmlu':
        benchmarks['mmlu'] = load_mmlu_subset(args.n)
        print(f"  mmlu: {len(benchmarks['mmlu'])} items")

    if not args.benchmark or args.benchmark == 'hellaswag':
        benchmarks['hellaswag'] = load_hellaswag_subset(args.n)
        print(f"  hellaswag: {len(benchmarks['hellaswag'])} items")

    if not args.benchmark or args.benchmark == 'niah':
        benchmarks['niah'] = load_niah_synthetic(args.n // 2)
        print(f"  niah: {len(benchmarks['niah'])} items")

    # Select configs and strategies
    if args.config:
        configs = [CONFIG_BY_ID[args.config]]
    else:
        configs = CONFIGURATIONS

    if args.strategy:
        strategies = [args.strategy]
    else:
        strategies = list(TRANSFORMERS.keys())

    # Setup recorder
    recorder = DataRecorder(data_dir, phase=args.phase, model_id=args.model_id)

    # Run tests (batched or sequential)
    if args.batch:
        run_batched_tests(configs, strategies, benchmarks, recorder, max_pending=args.max_pending)
    else:
        # Count total tests
        total = sum(1 for _ in iterate_test_matrix(configs, strategies, benchmarks))
        print(f"\nTotal tests to run: {total}")

        # Run tests sequentially
        completed = 0
        for config, strategy, benchmark_name, item in iterate_test_matrix(configs, strategies, benchmarks):
            completed += 1
            print(f"[{completed}/{total}] {config.id}|{strategy}|{benchmark_name}|{item['id']}...", end=" ", flush=True)

            success = run_single_test(item, config, strategy, recorder)

            if success:
                last_record = recorder.records[-1]
                status_str = "+" if last_record.correct else "-"
                print(f"{status_str} ({last_record.latency_ms}ms)")
            else:
                print("ERR")

            # Periodic stats
            if completed % 100 == 0:
                stats = recorder.get_stats()
                print(f"  ... Progress: {stats['correct']}/{stats['valid']} correct ({stats['accuracy']:.1%})")

    # Final summary
    print(f"\n{'=' * 60}")
    print("FINAL RESULTS")
    print(f"{'=' * 60}")
    stats = recorder.get_stats()
    print(f"  Total runs: {stats['total']}")
    print(f"  Successful: {stats['valid']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Correct: {stats['correct']}")
    print(f"  Accuracy: {stats['accuracy']:.1%}")

    # Generate summary
    summary_path = recorder.generate_summary()
    print(f"\nSummary written to: {summary_path}")
    print(f"Raw data: {recorder.jsonl_path}")


if __name__ == "__main__":
    main()
