# RE3 Setup

## Quick Start

```bash
./re3 setup    # Install dependencies
./re3 run      # Start running experiment
```

On Windows: use `re3` instead of `./re3`

## Prerequisites

- **Python 3.8+**
- **LM Studio** with a model loaded
- **GitHub CLI** (`gh`) - for collaboration features

### LM Studio Setup

1. Open LM Studio
2. Search and download: `google/gemma-3n-e4b` (or any gemma model)
3. Load the model
4. Go to **Local Server** tab → **Start Server**

## Commands

| Command | What it does |
|---------|--------------|
| `./re3 run` | Run one experiment slice |
| `./re3 run-all` | Run until all slices complete |
| `./re3 status` | Check experiment progress |
| `./re3 setup` | Install Python dependencies |
| `./re3 check` | Verify setup is ready |

## Collaboration

### Requesting Access

If you want to contribute test runs:

```bash
./re3 request
```

This creates a GitHub issue requesting collaborator access. The repo owner will approve you.

### For Repo Owner - Approving Collaborators

```bash
./re3 approve <username>
```

This adds the user as a collaborator so they can push results.

## How It Works

Multiple people can run simultaneously. Git handles coordination:

1. **Pull** latest progress
2. **Claim** a random available slice (push to lock it)
3. **Run** the tests
4. **Push** results when done

Each slice is 50 tests of one config/strategy/benchmark combination.
