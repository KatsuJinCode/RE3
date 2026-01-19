"""
Distributed Runner - Single command for collaborative test execution.

Handles everything: git pull, claim random slice, push lock, run tests,
periodic progress pushes.

Usage:
    python distributed_runner.py              # Run next available slice
    python distributed_runner.py --continuous # Keep running until done
"""

import subprocess
import sys
import time
import random
from pathlib import Path
from typing import Optional, List

# Add harness to path
sys.path.insert(0, str(Path(__file__).parent))

from progress import ProgressTracker, SliceStatus, get_priority_slices


def git_commit_local() -> bool:
    """Commit any local changes (data files, progress) before pull."""
    try:
        # Add data files and progress
        subprocess.run(['git', 'add', 'progress.json', 'data/'],
                      capture_output=True, timeout=10)

        # Commit if there are changes
        result = subprocess.run(
            ['git', 'commit', '-m', 'Auto-save progress'],
            capture_output=True, text=True, timeout=10
        )
        # Return code 1 means nothing to commit, that's fine
        return True
    except Exception as e:
        print(f"  git commit error: {e}")
        return False


def git_pull() -> bool:
    """Commit local changes then pull latest from remote."""
    try:
        # First commit any local changes so pull doesn't fail
        git_commit_local()

        result = subprocess.run(
            ['git', 'pull', '--rebase'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  git pull failed: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"  git pull error: {e}")
        return False


def git_push(message: str = "Update progress") -> bool:
    """Commit progress.json and push. Returns True if successful."""
    try:
        # Add progress file
        subprocess.run(['git', 'add', 'progress.json'], capture_output=True, timeout=10)

        # Commit (may fail if nothing changed, that's ok)
        subprocess.run(
            ['git', 'commit', '-m', message],
            capture_output=True, text=True, timeout=10
        )

        # Push
        result = subprocess.run(
            ['git', 'push'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # If push fails, try pull then push again
            git_pull()
            result = subprocess.run(
                ['git', 'push'],
                capture_output=True, text=True, timeout=30
            )

        return result.returncode == 0
    except Exception as e:
        print(f"  git push error: {e}")
        return False


def claim_random_slice(tracker: ProgressTracker, priority_slices: List[str]) -> Optional[str]:
    """
    Claim a random available slice from priority list.

    Random selection reduces race condition probability when two workers
    start simultaneously.
    """
    # Get all pending slices from priority list
    available = []
    for slice_id in priority_slices:
        info = tracker.get_slice(slice_id)
        if info and info.status == SliceStatus.PENDING:
            available.append(slice_id)

    if not available:
        # Check non-priority slices too
        for slice_id, info in tracker.state.slices.items():
            if info.status == SliceStatus.PENDING and slice_id not in priority_slices:
                available.append(slice_id)

    if not available:
        return None

    # Pick random to reduce collision probability
    return random.choice(available)


def run_one_slice(n: int = 50, max_pending: int = 4, push_every: int = 100) -> bool:
    """
    Run one slice with full git coordination.

    1. Pull latest progress
    2. Claim random available slice
    3. Push claim (file lock)
    4. Run tests
    5. Push progress periodically and on completion

    Returns True if a slice was run, False if none available.
    """
    from run_tests import (
        run_batched_tests, CONFIG_BY_ID, load_gsm8k_subset,
        load_mmlu_subset, load_hellaswag_subset, load_niah_synthetic
    )
    from data_recorder import DataRecorder

    print("\n" + "=" * 70)
    print("  RE3 DISTRIBUTED RUNNER")
    print("=" * 70)

    # Step 1: Pull latest
    print("\n[1/5] Pulling latest progress...")
    if not git_pull():
        print("  WARNING: Could not pull, continuing with local state")

    # Step 2: Load progress and find slice
    print("\n[2/5] Finding available slice...")
    tracker = ProgressTracker("progress.json")
    tracker.load()

    priority = get_priority_slices("1a")
    slice_id = claim_random_slice(tracker, priority)

    if not slice_id:
        print("  No slices available!")
        tracker.display_progress()
        return False

    print(f"  Selected: {slice_id}")

    # Step 3: Claim and push immediately (file lock)
    print("\n[3/5] Claiming slice...")
    claimed = tracker.claim(slice_id)
    if not claimed:
        print("  Failed to claim (already taken?)")
        return False

    tracker.start(slice_id)
    print("  Pushing claim to lock...")
    if not git_push(f"Claim {slice_id}"):
        print("  WARNING: Could not push claim, continuing anyway")

    # Parse slice ID
    parts = slice_id.split('_')
    config_id = parts[0]
    benchmark = parts[-1]
    strategy = '_'.join(parts[1:-1])

    config = CONFIG_BY_ID[config_id]

    print(f"\n[4/5] Running slice: {slice_id}")
    print(f"  Config: {config_id} ({config.pattern})")
    print(f"  Strategy: {strategy}")
    print(f"  Benchmark: {benchmark}")

    # Load benchmark data
    print(f"\n  Loading {benchmark}...")
    if benchmark == 'gsm8k':
        items = load_gsm8k_subset(n)
    elif benchmark == 'mmlu':
        items = load_mmlu_subset(n)
    elif benchmark == 'hellaswag':
        items = load_hellaswag_subset(n)
    elif benchmark == 'niah':
        items = load_niah_synthetic(n // 2)
    else:
        print(f"  ERROR: Unknown benchmark: {benchmark}")
        tracker.fail(slice_id, f"Unknown benchmark: {benchmark}")
        return False

    print(f"  Loaded {len(items)} items")

    # Setup recorder
    data_dir = Path("./data")
    recorder = DataRecorder(data_dir, phase=1)

    # Run tests
    configs = [config]
    strategies = [strategy]
    benchmarks = {benchmark: items}

    try:
        run_batched_tests(configs, strategies, benchmarks, recorder, max_pending=max_pending)

        # Get final stats
        stats = recorder.get_stats()

        # Step 5: Complete and push
        print("\n[5/5] Saving results...")
        mean_latency = sum(r.latency_ms for r in recorder.records) // len(recorder.records) if recorder.records else 0

        tracker.complete(slice_id, {
            'total': stats['total'],
            'correct': stats['correct'],
            'errors': stats['errors'],
            'accuracy': stats['accuracy'],
            'mean_latency_ms': mean_latency,
        }, results_file=str(recorder.jsonl_path))

        # Generate summary
        summary_path = recorder.generate_summary()
        print(f"  Summary: {summary_path}")
        print(f"  Raw data: {recorder.jsonl_path}")

        # Push final progress
        git_push(f"Complete {slice_id}: {stats['accuracy']:.1%}")

        # Show updated progress
        tracker.display_progress()

        return True

    except Exception as e:
        print(f"\n  ERROR: {e}")
        tracker.fail(slice_id, str(e))
        git_push(f"Failed {slice_id}: {e}")
        return False


def run_continuous(n: int = 50, max_pending: int = 4):
    """Keep running slices until none remain."""
    print("\n" + "=" * 70)
    print("  CONTINUOUS MODE - Running until complete")
    print("=" * 70)

    count = 0
    while True:
        success = run_one_slice(n=n, max_pending=max_pending)
        if not success:
            break
        count += 1
        print(f"\n--- Completed {count} slices, checking for more... ---\n")
        time.sleep(2)  # Brief pause between slices

    print(f"\nFinished. Completed {count} slices total.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RE3 Distributed Runner")
    parser.add_argument('--continuous', '-c', action='store_true',
                        help="Keep running until all slices complete")
    parser.add_argument('--n', type=int, default=50,
                        help="Items per benchmark")
    parser.add_argument('--max-pending', type=int, default=4,
                        help="Queue depth for batching")

    args = parser.parse_args()

    if args.continuous:
        run_continuous(n=args.n, max_pending=args.max_pending)
    else:
        run_one_slice(n=args.n, max_pending=args.max_pending)
