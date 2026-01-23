"""
Batch Runner - Maintains queue depth for efficient LLM utilization.

Instead of sequential request-wait-request, this submits multiple requests
upfront and polls for responses, keeping the LLM continuously busy.
"""

import subprocess
import sys
import time
import json
import os
import platform
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def _get_gateway_path() -> str:
    """Get gateway script path in format suitable for shell=True subprocess."""
    home = os.environ.get('HOME', os.environ.get('USERPROFILE', ''))
    home = home.replace('\\', '/')
    return home + '/.claude/scripts/safe-model-load.sh'


GATEWAY_SCRIPT_PATH = _get_gateway_path()
GATEWAY_SCRIPT = Path.home() / ".claude" / "scripts" / "safe-model-load.sh"


@dataclass
class PendingRequest:
    """A request that has been submitted but not yet completed."""
    request_id: int
    prompt: str
    response_file: str
    submit_time: float
    context: Any = None  # Caller-provided context (e.g., item, config)
    temp_files: List[str] = field(default_factory=list)


@dataclass
class BatchResponse:
    """Response from a completed batch request."""
    request_id: int
    text: str
    latency_ms: int
    context: Any
    error: Optional[str] = None


class BatchRunner:
    """
    Manages a queue of LLM requests with configurable concurrency.

    Usage:
        runner = BatchRunner(max_pending=4)

        # Submit work
        for item in items:
            runner.submit(prompt, context=item)

        # Process results as they complete
        for response in runner.results():
            process(response)
    """

    def __init__(self,
                 max_pending: int = 4,
                 poll_interval: float = 0.5,
                 timeout: float = 300.0,
                 temperature: float = 0.0):
        """
        Args:
            max_pending: Maximum concurrent requests (queue depth)
            poll_interval: Seconds between polling for responses
            timeout: Maximum seconds to wait for any single response
            temperature: LLM sampling temperature
        """
        self.max_pending = max_pending
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.temperature = temperature

        self._pending: Dict[int, PendingRequest] = {}
        self._results: List[BatchResponse] = []
        self._next_id = 0
        self._lock = threading.Lock()

    def _submit_request(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Submit a single request to the gateway. Returns response file path or None (non-blocking)."""
        temp_files = []

        try:
            # Write prompt to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(prompt)
                prompt_file = f.name
                temp_files.append(prompt_file)

            # Create response file (empty, will be written by subprocess)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                response_file = f.name
                temp_files.append(response_file)

            # Call Python gateway in background thread (non-blocking)
            python_code = f'''
import sys
sys.stdout.reconfigure(encoding='utf-8')
from safe_loading_gateway import get_gateway
with open(r"{prompt_file}", "r", encoding="utf-8") as f:
    prompt = f.read()
result = get_gateway().request_text(prompt)
with open(r"{response_file}", "w", encoding="utf-8") as f:
    f.write(result)
'''
            def run_in_background():
                try:
                    subprocess.run(
                        [sys.executable, '-c', python_code],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout,
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                    )
                except Exception:
                    pass  # Timeout or error - response file stays empty

            thread = threading.Thread(target=run_in_background, daemon=True)
            thread.start()

            return response_file, temp_files

        except Exception as e:
            for tf in temp_files:
                try:
                    os.unlink(tf)
                except:
                    pass
            return None

    def _read_response(self, file_path: str) -> Optional[str]:
        """Read and parse response from file. Returns text or None if not ready."""
        if not os.path.exists(file_path):
            return None

        if os.path.getsize(file_path) == 0:
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                response_text = f.read()

            # Parse JSON response
            try:
                response_json = json.loads(response_text)

                if "error" in response_json:
                    return f"ERROR: {response_json['error']}"

                if "choices" in response_json and len(response_json["choices"]) > 0:
                    content = response_json["choices"][0].get("message", {}).get("content", "")
                    return content.strip()

                return response_text.strip()

            except json.JSONDecodeError:
                return response_text.strip()

        except Exception:
            return None

    def submit(self, prompt: str, context: Any = None, system_prompt: Optional[str] = None) -> int:
        """
        Submit a request. Blocks if queue is full until a slot opens.

        Args:
            prompt: The prompt text
            context: Arbitrary context to return with the response
            system_prompt: Optional system prompt

        Returns:
            Request ID
        """
        # Wait for slot if queue is full
        while len(self._pending) >= self.max_pending:
            self._poll_once()
            if len(self._pending) >= self.max_pending:
                time.sleep(self.poll_interval)

        # Submit request
        result = self._submit_request(prompt, system_prompt)

        with self._lock:
            request_id = self._next_id
            self._next_id += 1

        if result is None:
            # Immediate failure
            self._results.append(BatchResponse(
                request_id=request_id,
                text="",
                latency_ms=0,
                context=context,
                error="Failed to submit request to gateway"
            ))
        else:
            file_path, temp_files = result
            pending = PendingRequest(
                request_id=request_id,
                prompt=prompt,
                response_file=file_path,
                submit_time=time.time(),
                context=context,
                temp_files=temp_files
            )
            with self._lock:
                self._pending[request_id] = pending

        return request_id

    def _poll_once(self):
        """Check all pending requests and move completed ones to results."""
        with self._lock:
            completed_ids = []

            for req_id, pending in self._pending.items():
                elapsed = time.time() - pending.submit_time

                # Check for timeout
                if elapsed > self.timeout:
                    self._results.append(BatchResponse(
                        request_id=req_id,
                        text="",
                        latency_ms=int(elapsed * 1000),
                        context=pending.context,
                        error=f"Timeout after {elapsed:.1f}s"
                    ))
                    completed_ids.append(req_id)
                    # Clean up temp files
                    for tf in pending.temp_files:
                        try:
                            os.unlink(tf)
                        except:
                            pass
                    continue

                # Try to read response
                text = self._read_response(pending.response_file)
                if text is not None:
                    latency_ms = int((time.time() - pending.submit_time) * 1000)

                    error = None
                    if text.startswith("ERROR:"):
                        error = text[6:].strip()
                        text = ""

                    self._results.append(BatchResponse(
                        request_id=req_id,
                        text=text,
                        latency_ms=latency_ms,
                        context=pending.context,
                        error=error
                    ))
                    completed_ids.append(req_id)
                    # Clean up temp files
                    for tf in pending.temp_files:
                        try:
                            os.unlink(tf)
                        except:
                            pass

            # Remove completed from pending
            for req_id in completed_ids:
                del self._pending[req_id]

    def pending_count(self) -> int:
        """Return number of pending requests."""
        return len(self._pending)

    def has_results(self) -> bool:
        """Return True if there are completed results to retrieve."""
        self._poll_once()
        return len(self._results) > 0

    def get_result(self, block: bool = True) -> Optional[BatchResponse]:
        """
        Get next completed result.

        Args:
            block: If True, wait for a result. If False, return None immediately if none ready.

        Returns:
            BatchResponse or None
        """
        while True:
            self._poll_once()

            if self._results:
                return self._results.pop(0)

            if not block:
                return None

            if not self._pending:
                return None  # Nothing pending, nothing to wait for

            time.sleep(self.poll_interval)

    def drain(self) -> Iterator[BatchResponse]:
        """Yield all results, waiting for pending requests to complete."""
        while self._pending or self._results:
            result = self.get_result(block=True)
            if result:
                yield result
            else:
                break

    def flush(self):
        """Wait for all pending requests to complete and return results."""
        results = list(self.drain())
        return results


def run_batched_tests(items: List[Any],
                      prepare_fn: Callable[[Any], str],
                      process_fn: Callable[[Any, BatchResponse], None],
                      max_pending: int = 4,
                      temperature: float = 0.0,
                      progress_fn: Optional[Callable[[int, int, int], None]] = None):
    """
    Convenience function to run batched tests.

    Args:
        items: List of test items
        prepare_fn: Function that takes item and returns prompt string
        process_fn: Function that takes (item, response) and processes result
        max_pending: Queue depth
        temperature: LLM temperature
        progress_fn: Optional callback(completed, pending, total) for progress updates
    """
    runner = BatchRunner(max_pending=max_pending, temperature=temperature)

    total = len(items)
    submitted = 0
    completed = 0

    # Submit initial batch
    for item in items:
        prompt = prepare_fn(item)
        runner.submit(prompt, context=item)
        submitted += 1

        # Process any ready results
        while runner.has_results():
            result = runner.get_result(block=False)
            if result:
                process_fn(result.context, result)
                completed += 1
                if progress_fn:
                    progress_fn(completed, runner.pending_count(), total)

    # Drain remaining results
    for result in runner.drain():
        process_fn(result.context, result)
        completed += 1
        if progress_fn:
            progress_fn(completed, runner.pending_count(), total)


if __name__ == "__main__":
    # Simple test
    print("Testing batch runner with 4 requests, max_pending=2...")

    runner = BatchRunner(max_pending=2)

    prompts = [
        "What is 2 + 2? Answer with just the number.",
        "What is 3 + 3? Answer with just the number.",
        "What is 4 + 4? Answer with just the number.",
        "What is 5 + 5? Answer with just the number.",
    ]

    # Submit all
    for i, p in enumerate(prompts):
        print(f"Submitting {i+1}... (pending: {runner.pending_count()})")
        runner.submit(p, context=f"test_{i}")

    print(f"\nAll submitted. Pending: {runner.pending_count()}")

    # Drain results
    for result in runner.drain():
        print(f"Result for {result.context}: '{result.text}' ({result.latency_ms}ms)")
        if result.error:
            print(f"  Error: {result.error}")

    print("\nDone!")
