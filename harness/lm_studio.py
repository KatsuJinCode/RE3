"""
Direct LM Studio Interface - Simple HTTP client for local LLM.

No external dependencies beyond requests (or urllib).
Talks directly to LM Studio's OpenAI-compatible API.
"""

import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


LM_STUDIO_URL = "http://localhost:1234/v1"
REQUIRED_MODEL = "gemma"  # Partial match - any gemma model works


@dataclass
class LMResponse:
    """Response from LM Studio."""
    text: str
    latency_ms: int
    model: str
    error: Optional[str] = None


def check_lm_studio() -> Dict[str, Any]:
    """
    Check LM Studio status and loaded model.

    Returns dict with:
        - running: bool
        - model_loaded: str or None
        - model_ok: bool (True if compatible model loaded)
        - available_models: list of model IDs
        - message: human-readable status
    """
    result = {
        'running': False,
        'model_loaded': None,
        'model_ok': False,
        'available_models': [],
        'message': ''
    }

    try:
        # Check /v1/models endpoint
        req = urllib.request.Request(f"{LM_STUDIO_URL}/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        result['running'] = True

        # Get loaded model
        if 'data' in data and len(data['data']) > 0:
            model_id = data['data'][0].get('id', '')
            result['model_loaded'] = model_id
            result['available_models'] = [m.get('id', '') for m in data['data']]

            # Check if it's a compatible model
            if REQUIRED_MODEL.lower() in model_id.lower():
                result['model_ok'] = True
                result['message'] = f"OK: {model_id} loaded"
            else:
                result['message'] = f"WARNING: {model_id} loaded, but {REQUIRED_MODEL} recommended"
                result['model_ok'] = True  # Still usable, just warn
        else:
            result['message'] = "LM Studio running but no model loaded"

    except urllib.error.URLError as e:
        result['message'] = f"LM Studio not running: {e.reason}"
    except Exception as e:
        result['message'] = f"Error checking LM Studio: {e}"

    return result


def list_local_models() -> List[str]:
    """
    Try to find downloaded models in LM Studio's cache.

    Returns list of model directory names found.
    """
    import os
    from pathlib import Path

    # Common LM Studio model locations
    possible_paths = [
        Path.home() / ".cache" / "lm-studio" / "models",
        Path.home() / "AppData" / "Local" / "LM Studio" / "models",
        Path.home() / ".lmstudio" / "models",
    ]

    models = []
    for path in possible_paths:
        if path.exists():
            try:
                for item in path.iterdir():
                    if item.is_dir():
                        models.append(item.name)
            except:
                pass

    return models


def send_prompt(prompt: str,
                system_prompt: Optional[str] = None,
                temperature: float = 0.0,
                max_tokens: int = 2048,
                timeout: float = 300.0) -> LMResponse:
    """
    Send prompt to LM Studio and get response.

    Args:
        prompt: User message
        system_prompt: Optional system message
        temperature: Sampling temperature (0.0 = deterministic)
        max_tokens: Max tokens to generate
        timeout: Request timeout in seconds

    Returns:
        LMResponse with text, latency, and optional error
    """
    start_time = time.time()

    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Build request
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            f"{LM_STUDIO_URL}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())

        latency_ms = int((time.time() - start_time) * 1000)

        # Extract response text
        if 'choices' in result and len(result['choices']) > 0:
            text = result['choices'][0].get('message', {}).get('content', '')
            model = result.get('model', 'unknown')
            return LMResponse(text=text.strip(), latency_ms=latency_ms, model=model)
        else:
            return LMResponse(
                text='',
                latency_ms=latency_ms,
                model='unknown',
                error=f"Unexpected response format: {result}"
            )

    except urllib.error.URLError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return LMResponse(
            text='',
            latency_ms=latency_ms,
            model='unknown',
            error=f"Connection error: {e.reason}"
        )
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return LMResponse(
            text='',
            latency_ms=latency_ms,
            model='unknown',
            error=str(e)
        )


def print_status():
    """Print human-readable status for CLI."""
    print("=== LM Studio Status ===")
    print()

    status = check_lm_studio()

    if status['running']:
        print(f"Server: Running (localhost:1234)")
        print(f"Model:  {status['model_loaded'] or 'None loaded'}")

        if not status['model_loaded']:
            print()
            print("ACTION REQUIRED:")
            print("  1. Open LM Studio")
            print("  2. Load a model (recommended: google/gemma-3n-e4b)")
            print("  3. Go to 'Local Server' tab and start server")

            # Check for downloaded models
            local = list_local_models()
            if local:
                print()
                print("Downloaded models found:")
                for m in local[:5]:
                    print(f"  - {m}")
                if len(local) > 5:
                    print(f"  ... and {len(local) - 5} more")
    else:
        print("Server: NOT RUNNING")
        print()
        print("ACTION REQUIRED:")
        print("  1. Open LM Studio")
        print("  2. Download model: google/gemma-3n-e4b")
        print("     (Search in LM Studio's model browser)")
        print("  3. Load the model")
        print("  4. Go to 'Local Server' tab")
        print("  5. Click 'Start Server'")

    print()
    return status['running'] and status['model_loaded']


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Quick test
        print("Testing LM Studio connection...")
        response = send_prompt("What is 2+2? Answer with just the number.")
        print(f"Response: {response.text}")
        print(f"Latency: {response.latency_ms}ms")
        print(f"Model: {response.model}")
        if response.error:
            print(f"Error: {response.error}")
    else:
        ok = print_status()
        sys.exit(0 if ok else 1)
