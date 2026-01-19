"""
Batch Runner - Maintains queue depth for efficient LLM utilization.

Instead of sequential request-wait-request, this submits multiple requests
upfront and polls for responses, keeping the LLM continuously busy.
"""

import subprocess
import time
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
import threading


def _get_gateway_path() -> str:
    """Get gateway script path in format suitable for shell=True subprocess."""
    home = os.environ.get('HOME', os.environ.get('USERPROFILE', ''))
    home = home.replace('\\', '/')
    return home + '/.claude/scripts/safe-model-load.sh'


GATEWAY_SCRIPT_PATH = _get_gateway_path()
GATEWAY_SCRIPT = Path.home() / ".claude" / "scripts" / "safe-model-load.sh"


def _gateway_available() -> bool:
    return bool(shutil.which("bash")) and GATEWAY_SCRIPT.exists()



@dataclass
class PendingRequest:
    """A request that has been submitted but not yet completed."""
    request_id: int
    prompt: str
    response_file: Optional[str]
    submit_time: float
    context: Any = None  # Caller-provided context (e.g., item, config)
    temp_files: List[str] = field(default_factory=list)
    future: Any = None  # Used in direct mode (no gateway)



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

        # Gateway mode uses ~/.claude/scripts/safe-model-load.sh via bash.
        # On Windows setups without that, fall back to direct LM Studio HTTP.
        self._use_gateway = _gateway_available()

        self._executor: Optional[ThreadPoolExecutor] = None
        self._direct_send: Optional[Callable[..., Any]] = None
        if not self._use_gateway:
            from lm_studio import send_prompt as direct_send

            self._direct_send = direct_send
            self._executor = ThreadPoolExecutor(max_workers=max_pending)

        self._pending: Dict[int, PendingRequest] = {}
        self._results: List[BatchResponse] = []
        self._next_id = 0
        self._lock = threading.Lock()

    def _submit_request(self, prompt: str, system_prompt: Optional[str] = None):
        """Submit a single request.

        Returns:
            None on failure, otherwise tuple (mode, handle, temp_files)
            - mode == "gateway": handle is response file path
            - mode == "direct":  handle is a Future
        """
        if not self._use_gateway:
            assert self._executor is not None
            assert self._direct_send is not None
            future = self._executor.submit(
                self._direct_send,
                prompt,
                system_prompt=system_prompt,
                temperature=self.temperature,
                timeout=self.timeout,
            )
            return "direct", future, []

        prompt_file = None
        system_file = None
        temp_files = []

        try:
            # Write prompt to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(prompt)
                prompt_file = f.name
                temp_files.append(prompt_file)
            prompt_file_unix = prompt_file.replace('\\', '/')

            # Build command
            cmd_parts = [
                'bash',
                f'"{GATEWAY_SCRIPT_PATH}"',
                'request',
                'text',
                '--prompt-file', f'"{prompt_file_unix}"',
                '--temperature', str(self.temperature)
            ]

            if system_prompt:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                    f.write(system_prompt)
                    system_file = f.name
                    temp_files.append(system_file)
                system_file_unix = system_file.replace('\\', '/')
                cmd_parts.extend(['--system-file', f'"{system_file_unix}"'])

            cmd = ' '.join(cmd_parts)

            # Execute gateway script (returns immediately with FILE= path)
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                for tf in temp_files:
                    try:
                        os.unlink(tf)
                    except:
                        pass
                return None

            # Parse FILE= from output
            file_path = None
            for line in result.stdout.strip().split('\n'):
                if line.startswith("FILE="):
                    file_path = line[5:]
                    break

            if not file_path:
                for tf in temp_files:
                    try:
                        os.unlink(tf)
                    except:
                        pass
                return None

            # Convert Unix-style path to Windows-style
            if platform.system() == "Windows" and file_path.startswith('/'):
                if len(file_path) >= 3 and file_path[2] == '/':
                    file_path = file_path[1].upper() + ':' + file_path[2:]

            return "gateway", file_path, temp_files

        except Exception:
            for tf in temp_files:
                try:
                    os.unlink(tf)
                except:
                    pass
            return None

    def _read_response(self, file_path: Optional[str]) -> Optional[str]:
        """Read and parse response from file. Returns text or None if not ready."""
        if not file_path:
            return None
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
        submitted = self._submit_request(prompt, system_prompt)

        with self._lock:
            request_id = self._next_id
            self._next_id += 1

        if submitted is None:
            # Immediate failure
            self._results.append(BatchResponse(
                request_id=request_id,
                text="",
                latency_ms=0,
                context=context,
                error="Failed to submit request"
            ))
        else:
            mode, handle, temp_files = submitted  # ("direct"|"gateway", handle, temp_files)

            response_file = None
            future = None
            if mode == "gateway":
                assert isinstance(handle, str)
                response_file = handle
            else:
                future = handle

            pending = PendingRequest(
                request_id=request_id,
                prompt=prompt,
                response_file=response_file,
                submit_time=time.time(),
                context=context,
                temp_files=temp_files,
                future=future,
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

                # Direct mode: poll future
                if pending.future is not None:
                    if not pending.future.done():
                        continue
                    try:
                        resp = pending.future.result()
                        latency_ms = getattr(resp, "latency_ms", None)
                        if latency_ms is None:
                            latency_ms = int((time.time() - pending.submit_time) * 1000)

                        err = getattr(resp, "error", None)
                        txt = getattr(resp, "text", "") or ""
                        self._results.append(BatchResponse(
                            request_id=req_id,
                            text=txt,
                            latency_ms=int(latency_ms),
                            context=pending.context,
                            error=err,
                        ))
                    except Exception as e:
                        elapsed2 = time.time() - pending.submit_time
                        self._results.append(BatchResponse(
                            request_id=req_id,
                            text="",
                            latency_ms=int(elapsed2 * 1000),
                            context=pending.context,
                            error=str(e),
                        ))
                    completed_ids.append(req_id)
                    continue

                # Gateway mode: read response file
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
