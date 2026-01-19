"""
LLM Interface - Unified interface for RE3 testing harness.

Uses bundled lm_studio.py for direct LM Studio communication.
Falls back to gateway script if available (for advanced features).
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Try bundled direct interface first
try:
    from lm_studio import send_prompt as lm_send, check_lm_studio, LMResponse as LMResp
    USE_DIRECT = True
except ImportError:
    USE_DIRECT = False


@dataclass
class LLMResponse:
    """Response from LLM including metadata."""
    text: str
    latency_ms: int
    error: Optional[str] = None


def send_prompt(prompt: str,
                system_prompt: Optional[str] = None,
                temperature: float = 0.0,
                max_retries: int = 2,
                poll_interval: float = 1.0,
                timeout: float = 300.0) -> LLMResponse:
    """
    Send prompt to LLM.

    Uses direct LM Studio interface (bundled).

    Args:
        prompt: The prompt text to send
        system_prompt: Optional system prompt
        temperature: Sampling temperature (0.0 for deterministic)
        max_retries: Number of retries on failure
        poll_interval: (unused with direct interface)
        timeout: Maximum seconds to wait for response

    Returns:
        LLMResponse with text, latency, and optional error
    """
    import time

    for attempt in range(max_retries + 1):
        try:
            response = lm_send(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                timeout=timeout
            )

            if response.error is None:
                return LLMResponse(
                    text=response.text,
                    latency_ms=response.latency_ms,
                    error=None
                )

            # If error, retry unless last attempt
            if attempt < max_retries:
                time.sleep(2)
                continue

            return LLMResponse(
                text="",
                latency_ms=response.latency_ms,
                error=response.error
            )

        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            return LLMResponse(
                text="",
                latency_ms=0,
                error=f"Exception after {max_retries + 1} attempts: {str(e)}"
            )

    return LLMResponse(text="", latency_ms=0, error="Unexpected: exhausted retries")


def check_gateway_status() -> dict:
    """
    Check LLM availability.

    Returns:
        Dict with 'ok' bool and 'message' string
    """
    try:
        status = check_lm_studio()
        ok = status['running'] and status['model_loaded'] is not None
        return {
            "ok": ok,
            "message": status['message']
        }
    except Exception as e:
        return {"ok": False, "message": f"Status check failed: {str(e)}"}


if __name__ == "__main__":
    # Quick test
    print("Checking LM Studio status...")
    status = check_gateway_status()
    print(f"Status: {status}")

    if status["ok"]:
        print("\nSending test prompt...")
        response = send_prompt("What is 2 + 2? Answer with just the number.")
        print(f"Response: {response.text}")
        print(f"Latency: {response.latency_ms}ms")
        if response.error:
            print(f"Error: {response.error}")
