# RE3 Setup

## Quick Start

```bash
git clone https://github.com/KatsuJinCode/RE3.git
cd RE3
./re3 setup    # Install dependencies
./re3 run      # Run experiments
```

On Windows: use `re3` instead of `./re3`

## Prerequisites

- **Python 3.8+**
- **LM Studio** with a model loaded

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

## Contributing Results

Anyone can clone and run experiments locally. To **contribute your results back** to the shared dataset:

```bash
./re3 request    # Request push access (creates GitHub issue)
```

Once approved, your results automatically sync to the shared repo.

### For Repo Owner

```bash
./re3 approve <username>    # Grant push access
```

## How It Works

Multiple people can run simultaneously. Git coordinates:

1. Pull latest progress
2. Claim a random available slice
3. Run tests (50 per slice)
4. Push results

Each slice is one config/strategy/benchmark combination.
