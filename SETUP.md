# RE3 Setup

## Quick Start (2 commands)

```bash
python bootstrap.py setup    # Install dependencies
python bootstrap.py run      # Start running experiment
```

## Prerequisites

- **Python 3.8+** (you probably have this)
- **LM Studio** with a model loaded

### LM Studio Setup

1. Open LM Studio
2. Search and download: `google/gemma-3n-e4b` (or any gemma model)
3. Load the model
4. Go to **Local Server** tab → **Start Server**

That's it. The bootstrap script checks everything else.

## Commands

| Command | What it does |
|---------|--------------|
| `python bootstrap.py` | Check setup status |
| `python bootstrap.py setup` | Install Python dependencies |
| `python bootstrap.py run` | Run one experiment slice |
| `python bootstrap.py run-all` | Run until all slices complete |

## Collaborative Running

Multiple people can run simultaneously. Git handles coordination:

```bash
python bootstrap.py run-all
```

Each run: pulls latest → claims random slice → pushes claim → runs → pushes results.

## Alternatives

If you have `just` installed:
```bash
just experiment      # Same as bootstrap.py run
just experiment-all  # Same as bootstrap.py run-all
```

If you have `make`:
```bash
make run      # Same as bootstrap.py run
make run-all  # Same as bootstrap.py run-all
```
