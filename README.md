# Mirror Brain

**Mirror Brain v1.0** — A personal AI memory and reflection system.

## Overview

Mirror Brain captures, organizes, and surfaces your thoughts, notes, and interactions
to build a long-term memory layer. Think of it as an externalized, searchable
extension of your own mind.

## Stack

- **Language:** Python 3.11+
- **Package manager:** uv
- **Dependencies:** stdlib only (no third-party packages yet)

## Project Structure

```
mirror-brain/
├── pyproject.toml
├── README.md
├── .gitignore
└── src/
    └── mirror_brain/
        └── __init__.py
```

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd mirror-brain

# Create a virtual environment
uv venv

# Activate it
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Install in editable mode (no deps yet)
uv pip install -e .
```

## License

Private — not yet licensed.
