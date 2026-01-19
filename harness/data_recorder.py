"""
Data Recorder for RE3 testing harness.

Handles JSONL append-only writing and summary CSV generation.
"""

import json
import csv
import uuid
import socket
import platform
import getpass
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
import statistics


def get_environment_info() -> Dict[str, Any]:
    """Collect machine/environment information for reproducibility."""
    env = {
        'hostname': socket.gethostname(),
        'username': getpass.getuser(),
        'platform': platform.system(),
        'platform_release': platform.release(),
        'platform_version': platform.version(),
        'architecture': platform.machine(),
        'python_version': platform.python_version(),
        'cwd': os.getcwd(),
    }

    # Try to get GPU info (if nvidia-smi available)
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            env['gpu'] = result.stdout.strip()
    except:
        env['gpu'] = 'unknown'

    return env


@dataclass
class RunRecord:
    """Single test run record."""
    run_id: str
    timestamp: str
    phase: int
    # Configuration
    config_id: str
    pattern: str
    pattern_length: int
    b_strategy: str
    # Benchmark
    benchmark: str
    benchmark_subset: Optional[str]
    item_id: str
    item_index: int
    # Prompts
    prompt_a: str
    prompt_b: Optional[str]
    assembled_prompt: str
    separator: str
    # Tokens (estimated)
    tokens_a: int
    tokens_b: Optional[int]
    tokens_total_input: int
    tokens_output: int
    # Model
    model_id: str
    temperature: float
    # Response
    response_raw: str
    response_truncated: bool
    latency_ms: int
    # Evaluation
    expected_answer: str
    extracted_answer: str
    extraction_method: str
    correct: bool
    # Metadata
    error: Optional[str]
    notes: Optional[str]
    # Environment (for reproducibility)
    hostname: Optional[str] = None
    worker_id: Optional[str] = None
    gpu: Optional[str] = None
    platform_info: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DataRecorder:
    """Records test runs to JSONL and generates summaries."""

    def __init__(self, data_dir: Path, phase: int = 1, model_id: str = "unknown"):
        self.data_dir = Path(data_dir)
        self.phase = phase
        self.model_id = model_id

        # Capture environment once at init
        self.env = get_environment_info()
        self.worker_id = f"{self.env['username']}@{self.env['hostname']}"

        # Create directories
        self.runs_dir = self.data_dir / "runs"
        self.summaries_dir = self.data_dir / "summaries"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

        # Current session file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.runs_dir / f"phase{phase}_{timestamp}.jsonl"
        self.records: List[RunRecord] = []

    def record(self, **kwargs) -> RunRecord:
        """
        Record a single test run.

        Args:
            All fields from RunRecord (see dataclass definition)

        Returns:
            The created RunRecord
        """
        # Generate ID and timestamp if not provided
        if 'run_id' not in kwargs:
            kwargs['run_id'] = str(uuid.uuid4())
        if 'timestamp' not in kwargs:
            kwargs['timestamp'] = datetime.now().isoformat()
        if 'phase' not in kwargs:
            kwargs['phase'] = self.phase
        if 'model_id' not in kwargs:
            kwargs['model_id'] = self.model_id

        # Add environment info
        if 'hostname' not in kwargs:
            kwargs['hostname'] = self.env.get('hostname')
        if 'worker_id' not in kwargs:
            kwargs['worker_id'] = self.worker_id
        if 'gpu' not in kwargs:
            kwargs['gpu'] = self.env.get('gpu')
        if 'platform_info' not in kwargs:
            kwargs['platform_info'] = f"{self.env.get('platform')} {self.env.get('platform_release')}"

        # Create record
        record = RunRecord(**kwargs)
        self.records.append(record)

        # Append to JSONL (immediate persistence)
        with open(self.jsonl_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record.to_dict()) + '\n')

        return record

    def generate_summary(self, output_path: Optional[Path] = None) -> Path:
        """
        Generate summary CSV from recorded runs.

        Args:
            output_path: Optional custom output path

        Returns:
            Path to generated summary file
        """
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.summaries_dir / f"phase{self.phase}_{timestamp}_summary.csv"

        # Group records by (config_id, b_strategy, benchmark)
        groups: Dict[tuple, List[RunRecord]] = {}
        for record in self.records:
            key = (record.config_id, record.b_strategy, record.benchmark)
            if key not in groups:
                groups[key] = []
            groups[key].append(record)

        # Calculate summary stats for each group
        summaries = []
        for (config_id, b_strategy, benchmark), records in groups.items():
            valid_records = [r for r in records if r.error is None]
            correct_count = sum(1 for r in valid_records if r.correct)
            error_count = len(records) - len(valid_records)

            n_total = len(records)
            n_valid = len(valid_records)
            accuracy = correct_count / n_valid if n_valid > 0 else 0.0

            # Confidence interval (Wilson score for binomial)
            ci_low, ci_high = self._wilson_ci(correct_count, n_valid)

            # Latency stats
            latencies = [r.latency_ms for r in valid_records]
            avg_latency = statistics.mean(latencies) if latencies else 0

            # Token stats
            input_tokens = [r.tokens_total_input for r in valid_records]
            output_tokens = [r.tokens_output for r in valid_records]

            summaries.append({
                'config_id': config_id,
                'pattern': records[0].pattern if records else '',
                'b_strategy': b_strategy,
                'benchmark': benchmark,
                'n_total': n_total,
                'n_correct': correct_count,
                'n_error': error_count,
                'accuracy': round(accuracy, 4),
                'accuracy_95ci_low': round(ci_low, 4),
                'accuracy_95ci_high': round(ci_high, 4),
                'avg_latency_ms': round(avg_latency, 1),
                'avg_tokens_input': round(statistics.mean(input_tokens), 1) if input_tokens else 0,
                'avg_tokens_output': round(statistics.mean(output_tokens), 1) if output_tokens else 0,
            })

        # Sort by accuracy descending
        summaries.sort(key=lambda x: x['accuracy'], reverse=True)

        # Write CSV
        if summaries:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=summaries[0].keys())
                writer.writeheader()
                writer.writerows(summaries)

        return output_path

    def _wilson_ci(self, successes: int, n: int, z: float = 1.96) -> tuple:
        """Calculate Wilson score confidence interval."""
        if n == 0:
            return (0.0, 0.0)

        p = successes / n
        denominator = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denominator
        margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denominator

        return (max(0, center - margin), min(1, center + margin))

    def load_existing(self, jsonl_path: Path) -> int:
        """
        Load existing records from JSONL file.

        Args:
            jsonl_path: Path to JSONL file

        Returns:
            Number of records loaded
        """
        count = 0
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    record = RunRecord(**data)
                    self.records.append(record)
                    count += 1
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        if not self.records:
            return {'total': 0}

        valid = [r for r in self.records if r.error is None]
        correct = sum(1 for r in valid if r.correct)

        return {
            'total': len(self.records),
            'valid': len(valid),
            'errors': len(self.records) - len(valid),
            'correct': correct,
            'accuracy': correct / len(valid) if valid else 0,
            'configs_tested': len(set(r.config_id for r in self.records)),
            'strategies_tested': len(set(r.b_strategy for r in self.records)),
            'benchmarks_tested': len(set(r.benchmark for r in self.records)),
        }


def estimate_tokens(text: str) -> int:
    """
    Rough token count estimate.

    Uses ~4 chars per token heuristic for English text.
    More accurate would require actual tokenizer, but this is sufficient
    for relative comparisons within the experiment.
    """
    return max(1, len(text) // 4)


if __name__ == "__main__":
    # Test the recorder
    recorder = DataRecorder(Path("./test_data"), phase=1, model_id="test-model")

    # Record some test runs
    for i in range(5):
        recorder.record(
            config_id="C01",
            pattern="A",
            pattern_length=1,
            b_strategy="none",
            benchmark="gsm8k",
            benchmark_subset=None,
            item_id=f"test_{i}",
            item_index=i,
            prompt_a="What is 2+2?",
            prompt_b=None,
            assembled_prompt="What is 2+2?",
            separator="",
            tokens_a=10,
            tokens_b=None,
            tokens_total_input=10,
            tokens_output=5,
            temperature=0.0,
            response_raw="4",
            response_truncated=False,
            latency_ms=100 + i * 10,
            expected_answer="4",
            extracted_answer="4",
            extraction_method="last_number",
            correct=(i % 2 == 0),  # Alternate correct/incorrect for testing
            error=None,
            notes=None,
        )

    print(f"Recorded {len(recorder.records)} runs")
    print(f"Stats: {recorder.get_stats()}")

    summary_path = recorder.generate_summary()
    print(f"Summary written to: {summary_path}")
