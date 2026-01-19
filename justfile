# RE3 Testing Harness
# Usage: just <command>

default:
    @just --list

# ============================================================================
# SETUP (run these first)
# ============================================================================

# Check all dependencies and show what's missing
check:
    @echo "=== RE3 Dependency Check ==="
    @echo ""
    @echo "Python:"
    @python --version || echo "  MISSING: Install Python 3.8+"
    @echo ""
    @echo "Datasets library:"
    @python -c "import datasets; print('  OK: datasets', datasets.__version__)" 2>/dev/null || echo "  MISSING: Run 'just setup'"
    @echo ""
    @echo "LM Studio gateway:"
    @bash ~/.claude/scripts/safe-model-load.sh status 2>/dev/null || echo "  MISSING: See SETUP.md for LM Studio configuration"
    @echo ""
    @echo "Progress file:"
    @test -f progress.json && echo "  OK: progress.json exists" || echo "  MISSING: Run 'just init'"

# Install Python dependencies
setup:
    pip install datasets

# Initialize progress tracking (creates progress.json)
init:
    python harness/progress.py init

# ============================================================================
# EXPERIMENT (main commands)
# ============================================================================

# Run one slice of the experiment (auto-coordinates via git)
experiment n="50" pending="4":
    python harness/distributed_runner.py --n {{n}} --max-pending {{pending}}

# Keep running slices until experiment complete
experiment-all n="50" pending="4":
    python harness/distributed_runner.py --continuous --n {{n}} --max-pending {{pending}}

# Show experiment progress
progress:
    python harness/progress.py status

# ============================================================================
# TESTING
# ============================================================================

# Quick smoke test (verifies harness works)
smoke:
    python harness/run_tests.py --smoke --data-dir ./data

# Test specific configuration
test config strategy="none" benchmark="gsm8k" n="10":
    python harness/run_tests.py --config {{config}} --strategy {{strategy}} --benchmark {{benchmark}} --n {{n}} --batch --max-pending 2 --data-dir ./data

# ============================================================================
# DATA
# ============================================================================

# View latest results
results:
    @ls -t data/summaries/*.csv 2>/dev/null | head -1 | xargs cat 2>/dev/null || echo "No results yet"

# View recent raw records
records:
    @ls -t data/runs/*.jsonl 2>/dev/null | head -1 | xargs tail -10 2>/dev/null || echo "No records yet"

# Show re-tokenization strategy examples
transforms:
    python harness/retokenizers.py
