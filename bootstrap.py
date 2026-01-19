#!/usr/bin/env python3
"""
RE3 Bootstrap - One command setup and run.

Usage:
    python bootstrap.py          # Check setup and show next steps
    python bootstrap.py setup    # Install dependencies
    python bootstrap.py run      # Run one experiment slice
    python bootstrap.py run-all  # Run until complete
"""

import subprocess
import sys
import os
from pathlib import Path


def check_python():
    """Check Python version."""
    v = sys.version_info
    if v.major >= 3 and v.minor >= 8:
        print(f"  [OK] Python {v.major}.{v.minor}.{v.micro}")
        return True
    else:
        print(f"  [!!] Python {v.major}.{v.minor} - need 3.8+")
        return False


def check_datasets():
    """Check if datasets library is installed."""
    try:
        import datasets
        print(f"  [OK] datasets {datasets.__version__}")
        return True
    except ImportError:
        print("  [!!] datasets - not installed")
        print("       Run: python bootstrap.py setup")
        return False


def check_lm_studio():
    """Check LM Studio status."""
    # Add harness to path
    sys.path.insert(0, str(Path(__file__).parent / "harness"))

    try:
        from lm_studio import check_lm_studio as check, list_local_models
        status = check()

        if status['running'] and status['model_loaded']:
            print(f"  [OK] LM Studio - {status['model_loaded']}")
            return True
        elif status['running']:
            print("  [!!] LM Studio running but no model loaded")
            print("       Open LM Studio and load a model")

            # Check for downloaded models
            local = list_local_models()
            gemma = [m for m in local if 'gemma' in m.lower()]
            if gemma:
                print(f"       Recommended: {gemma[0]}")
            return False
        else:
            print("  [!!] LM Studio not running")
            print("       1. Open LM Studio")
            print("       2. Download: google/gemma-3n-e4b")
            print("       3. Load the model")
            print("       4. Start Local Server")
            return False
    except Exception as e:
        print(f"  [!!] LM Studio check failed: {e}")
        return False


def check_progress():
    """Check if progress.json exists."""
    if Path("progress.json").exists():
        print("  [OK] progress.json")
        return True
    else:
        print("  [--] progress.json - not initialized")
        print("       Will be created on first run")
        return True  # Not blocking


def install_deps():
    """Install Python dependencies."""
    print("\nInstalling dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "datasets"], check=True)
    print("\nDone! Run 'python bootstrap.py' to check status.")


def init_progress():
    """Initialize progress tracking."""
    sys.path.insert(0, str(Path(__file__).parent / "harness"))
    from progress import ProgressTracker
    tracker = ProgressTracker("progress.json")
    tracker.load()
    print(f"Initialized progress.json with {len(tracker.state.slices)} slices")


def run_experiment(continuous=False):
    """Run experiment slice(s)."""
    # Check ready
    print("Checking setup...")
    if not check_lm_studio():
        print("\nCannot run: LM Studio not ready")
        return False

    if not check_datasets():
        print("\nCannot run: datasets not installed")
        print("Run: python bootstrap.py setup")
        return False

    # Initialize progress if needed
    if not Path("progress.json").exists():
        init_progress()

    # Run
    print("\nStarting experiment...\n")
    cmd = [sys.executable, "harness/distributed_runner.py"]
    if continuous:
        cmd.append("--continuous")
    subprocess.run(cmd)
    return True


def show_status():
    """Show overall status."""
    print("=" * 50)
    print("  RE3 Setup Status")
    print("=" * 50)
    print()

    checks = [
        ("Python", check_python),
        ("Datasets", check_datasets),
        ("LM Studio", check_lm_studio),
        ("Progress", check_progress),
    ]

    all_ok = True
    for name, check_fn in checks:
        result = check_fn()
        if not result:
            all_ok = False

    print()
    if all_ok:
        print("Ready! Run: python bootstrap.py run")
    else:
        print("Some checks failed - see above for fixes")

    return all_ok


def main():
    os.chdir(Path(__file__).parent)

    if len(sys.argv) < 2:
        show_status()
    elif sys.argv[1] == "setup":
        install_deps()
    elif sys.argv[1] == "run":
        run_experiment(continuous=False)
    elif sys.argv[1] == "run-all":
        run_experiment(continuous=True)
    elif sys.argv[1] == "init":
        init_progress()
    elif sys.argv[1] == "status":
        show_status()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
