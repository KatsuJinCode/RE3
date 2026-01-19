"""
Progress Tracking - Coordinate distributed test execution.

Tracks which slices (config × strategy × benchmark) are pending, claimed,
or completed. Enables multiple workers to split work without duplication.
"""

import json
import os
import socket
import getpass
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum


class SliceStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SliceInfo:
    """Information about a single slice."""
    slice_id: str
    config_id: str
    strategy: str
    benchmark: str
    status: SliceStatus = SliceStatus.PENDING
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results_file: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'SliceInfo':
        d = d.copy()
        d['status'] = SliceStatus(d['status'])
        return cls(**d)


@dataclass
class ProgressState:
    """Complete progress state for the experiment."""
    slices: Dict[str, SliceInfo] = field(default_factory=dict)
    workers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            'slices': {k: v.to_dict() for k, v in self.slices.items()},
            'workers': self.workers,
            'created_at': self.created_at,
            'last_updated': self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ProgressState':
        slices = {k: SliceInfo.from_dict(v) for k, v in d.get('slices', {}).items()}
        return cls(
            slices=slices,
            workers=d.get('workers', {}),
            created_at=d.get('created_at', ''),
            last_updated=d.get('last_updated', ''),
        )


# Valid configurations
CONFIGS = [
    ("C01", "A"), ("C02", "B"),
    ("C03", "AA"), ("C04", "AB"), ("C05", "BA"), ("C06", "BB"),
    ("C07", "AAA"), ("C08", "AAB"), ("C09", "ABA"), ("C10", "ABB"),
    ("C11", "BAA"), ("C12", "BAB"), ("C13", "BBA"), ("C14", "BBB"),
]

# Strategies
STRATEGIES = [
    'none',
    'b1a_camelcase_pairs', 'b1b_camelcase_all', 'b1c_underscore_join',
    'b1d_hyphenation', 'b1e_compound_split', 'b2a_digit_spacing',
    'b3a_lowercase_all', 'b3b_uppercase_all', 'b4a_delimiter_swap',
    'b6b_word_numbers',
]

MATH_ONLY_STRATEGIES = {'b2a_digit_spacing', 'b6b_word_numbers'}

BENCHMARKS = ['gsm8k', 'mmlu', 'hellaswag', 'niah']


def get_worker_id() -> str:
    """Generate a worker ID from username and hostname."""
    user = getpass.getuser()
    host = socket.gethostname()
    return f"{user}@{host}"


def generate_all_slices() -> List[SliceInfo]:
    """Generate all valid slice combinations."""
    slices = []

    for config_id, pattern in CONFIGS:
        uses_b = 'B' in pattern

        for strategy in STRATEGIES:
            # Skip 'none' strategy for configs that use B
            if strategy == 'none' and uses_b:
                continue
            # Skip non-none strategies for configs that don't use B
            if strategy != 'none' and not uses_b:
                continue

            for benchmark in BENCHMARKS:
                # Skip math-only strategies for non-math benchmarks
                if strategy in MATH_ONLY_STRATEGIES and benchmark != 'gsm8k':
                    continue

                slice_id = f"{config_id}_{strategy}_{benchmark}"
                slices.append(SliceInfo(
                    slice_id=slice_id,
                    config_id=config_id,
                    strategy=strategy,
                    benchmark=benchmark,
                ))

    return slices


def get_priority_slices(phase: str = "1a") -> List[str]:
    """
    Get slice IDs in priority order for phased execution.

    Phase 1A (~10K tests): Core comparisons
    - C01, C03 (baselines) - all benchmarks
    - C04, C09 (key RE3 patterns) - top 3 strategies, all benchmarks
    - Remaining configs - GSM8K only, top 3 strategies

    Phase 1B: Fill in remaining combinations
    """
    priority = []

    top_strategies = ['b1a_camelcase_pairs', 'b3a_lowercase_all', 'b4a_delimiter_swap']

    if phase == "1a":
        # Baselines first (no strategy needed)
        for benchmark in BENCHMARKS:
            priority.append(f"C01_none_{benchmark}")
            priority.append(f"C03_none_{benchmark}")

        # Key RE3 patterns with top strategies
        for config_id in ['C04', 'C09']:
            for strategy in top_strategies:
                if strategy in MATH_ONLY_STRATEGIES:
                    priority.append(f"{config_id}_{strategy}_gsm8k")
                else:
                    for benchmark in BENCHMARKS:
                        priority.append(f"{config_id}_{strategy}_{benchmark}")

        # Remaining configs - GSM8K only
        remaining_configs = ['C02', 'C05', 'C06', 'C07', 'C08', 'C10', 'C11', 'C12', 'C13', 'C14']
        for config_id in remaining_configs:
            pattern = dict(CONFIGS)[config_id] if config_id in dict(CONFIGS) else ""
            uses_b = 'B' in pattern

            if uses_b:
                for strategy in top_strategies:
                    priority.append(f"{config_id}_{strategy}_gsm8k")
            else:
                priority.append(f"{config_id}_none_gsm8k")

    return priority


class ProgressTracker:
    """
    Manages progress state for distributed execution.

    Usage:
        tracker = ProgressTracker("progress.json")

        # Claim next available slice
        slice_info = tracker.claim_next()

        # Or claim specific slice
        slice_info = tracker.claim("C01_none_gsm8k")

        # Mark as running
        tracker.start(slice_info.slice_id)

        # ... run tests ...

        # Mark complete
        tracker.complete(slice_info.slice_id, stats={'accuracy': 0.75, ...})
    """

    def __init__(self, progress_file: str = "progress.json"):
        self.progress_file = Path(progress_file)
        self.worker_id = get_worker_id()
        self.state: Optional[ProgressState] = None

    def load(self) -> ProgressState:
        """Load progress state from file, or initialize if not exists."""
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                data = json.load(f)
            self.state = ProgressState.from_dict(data)
        else:
            # Initialize with all slices
            self.state = ProgressState()
            for slice_info in generate_all_slices():
                self.state.slices[slice_info.slice_id] = slice_info
            self.save()

        return self.state

    def save(self):
        """Save progress state to file."""
        if self.state is None:
            return

        self.state.last_updated = datetime.now(timezone.utc).isoformat()
        self.state.workers[self.worker_id] = {
            'last_seen': datetime.now(timezone.utc).isoformat()
        }

        with open(self.progress_file, 'w') as f:
            json.dump(self.state.to_dict(), f, indent=2)

    def get_slice(self, slice_id: str) -> Optional[SliceInfo]:
        """Get info for a specific slice."""
        if self.state is None:
            self.load()
        return self.state.slices.get(slice_id)

    def claim(self, slice_id: str, force: bool = False) -> Optional[SliceInfo]:
        """
        Claim a slice for this worker.

        Returns SliceInfo if claimed, None if already claimed by another.
        """
        if self.state is None:
            self.load()

        slice_info = self.state.slices.get(slice_id)
        if slice_info is None:
            return None

        # Check if already claimed by another
        if slice_info.status in (SliceStatus.CLAIMED, SliceStatus.RUNNING):
            if slice_info.claimed_by != self.worker_id and not force:
                return None

        # Check if already completed
        if slice_info.status == SliceStatus.COMPLETED and not force:
            return None

        # Claim it
        slice_info.status = SliceStatus.CLAIMED
        slice_info.claimed_by = self.worker_id
        slice_info.claimed_at = datetime.now(timezone.utc).isoformat()
        self.save()

        return slice_info

    def claim_next(self, priority_order: Optional[List[str]] = None, reverse: bool = False) -> Optional[SliceInfo]:
        """
        Claim the next available slice.

        Args:
            priority_order: Optional list of slice IDs in priority order
            reverse: If True, start from the end of the list

        Returns:
            SliceInfo if a slice was claimed, None if all done/claimed
        """
        if self.state is None:
            self.load()

        # Get order
        if priority_order:
            order = priority_order
        else:
            order = list(self.state.slices.keys())

        if reverse:
            order = list(reversed(order))

        # Find first unclaimed
        for slice_id in order:
            slice_info = self.state.slices.get(slice_id)
            if slice_info and slice_info.status == SliceStatus.PENDING:
                return self.claim(slice_id)

        return None

    def start(self, slice_id: str):
        """Mark a slice as running."""
        if self.state is None:
            self.load()

        slice_info = self.state.slices.get(slice_id)
        if slice_info:
            slice_info.status = SliceStatus.RUNNING
            slice_info.started_at = datetime.now(timezone.utc).isoformat()
            self.save()

    def complete(self, slice_id: str, stats: Dict[str, Any], results_file: Optional[str] = None):
        """Mark a slice as completed with stats."""
        if self.state is None:
            self.load()

        slice_info = self.state.slices.get(slice_id)
        if slice_info:
            slice_info.status = SliceStatus.COMPLETED
            slice_info.completed_at = datetime.now(timezone.utc).isoformat()
            slice_info.stats = stats
            slice_info.results_file = results_file
            self.save()

    def fail(self, slice_id: str, error: str):
        """Mark a slice as failed."""
        if self.state is None:
            self.load()

        slice_info = self.state.slices.get(slice_id)
        if slice_info:
            slice_info.status = SliceStatus.FAILED
            slice_info.error = error
            slice_info.completed_at = datetime.now(timezone.utc).isoformat()
            self.save()

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if self.state is None:
            self.load()

        counts = {status: 0 for status in SliceStatus}
        total_correct = 0
        total_tests = 0

        for slice_info in self.state.slices.values():
            counts[slice_info.status] += 1
            if slice_info.stats:
                total_correct += slice_info.stats.get('correct', 0)
                total_tests += slice_info.stats.get('total', 0)

        return {
            'total_slices': len(self.state.slices),
            'pending': counts[SliceStatus.PENDING],
            'claimed': counts[SliceStatus.CLAIMED],
            'running': counts[SliceStatus.RUNNING],
            'completed': counts[SliceStatus.COMPLETED],
            'failed': counts[SliceStatus.FAILED],
            'total_tests': total_tests,
            'total_correct': total_correct,
            'accuracy': total_correct / total_tests if total_tests > 0 else 0,
            'workers': list(self.state.workers.keys()),
        }

    def display_progress(self):
        """Display progress matrix to console."""
        if self.state is None:
            self.load()

        summary = self.get_summary()

        print()
        print("=" * 70)
        print("  RE3 PROGRESS")
        print("=" * 70)
        print(f"  Slices: {summary['completed']}/{summary['total_slices']} completed "
              f"({summary['completed']/summary['total_slices']*100:.1f}%)")
        print(f"  Tests:  {summary['total_tests']} run, {summary['total_correct']} correct "
              f"({summary['accuracy']:.1%})")
        print(f"  Status: {summary['pending']} pending, {summary['claimed']} claimed, "
              f"{summary['running']} running, {summary['failed']} failed")
        print(f"  Workers: {', '.join(summary['workers']) or 'none'}")
        print()

        # Matrix display
        # Group by config
        print("  Config    | gsm8k | mmlu  | hella | niah  ")
        print("  ----------+-------+-------+-------+-------")

        status_chars = {
            SliceStatus.PENDING: '.',
            SliceStatus.CLAIMED: 'c',
            SliceStatus.RUNNING: 'R',
            SliceStatus.COMPLETED: '#',
            SliceStatus.FAILED: 'X',
        }

        for config_id, pattern in CONFIGS:
            uses_b = 'B' in pattern
            strategies_for_config = [s for s in STRATEGIES
                                     if (s == 'none') != uses_b]

            row = f"  {config_id} ({pattern:3s}) |"

            for benchmark in BENCHMARKS:
                # Count statuses for this config×benchmark
                cell_statuses = []
                for strategy in strategies_for_config:
                    if strategy in MATH_ONLY_STRATEGIES and benchmark != 'gsm8k':
                        continue
                    slice_id = f"{config_id}_{strategy}_{benchmark}"
                    slice_info = self.state.slices.get(slice_id)
                    if slice_info:
                        cell_statuses.append(slice_info.status)

                if not cell_statuses:
                    row += "  --  |"
                else:
                    completed = sum(1 for s in cell_statuses if s == SliceStatus.COMPLETED)
                    total = len(cell_statuses)
                    if completed == total:
                        row += " done |"
                    elif completed > 0:
                        row += f" {completed}/{total}  |"
                    else:
                        row += "      |"

            print(row)

        print()
        print("  Legend: done=all complete, N/M=partial, blank=pending")
        print("=" * 70)


if __name__ == "__main__":
    import sys

    tracker = ProgressTracker("progress.json")
    tracker.load()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "init":
            print(f"Initialized progress.json with {len(tracker.state.slices)} slices")

        elif cmd == "status":
            tracker.display_progress()

        elif cmd == "claim" and len(sys.argv) > 2:
            slice_id = sys.argv[2]
            result = tracker.claim(slice_id)
            if result:
                print(f"Claimed: {slice_id}")
            else:
                print(f"Could not claim: {slice_id}")

        elif cmd == "next":
            reverse = "--reverse" in sys.argv
            result = tracker.claim_next(reverse=reverse)
            if result:
                print(f"Claimed: {result.slice_id}")
            else:
                print("No slices available")

        elif cmd == "list":
            for slice_id, info in tracker.state.slices.items():
                print(f"{slice_id}: {info.status.value}")

        else:
            print("Usage: progress.py [init|status|claim <id>|next [--reverse]|list]")
    else:
        tracker.display_progress()
