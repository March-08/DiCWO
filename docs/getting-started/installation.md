# Installation

## Requirements

- Python 3.11+
- An API key for OpenAI and/or OpenRouter

## Install

Clone the repository and install in editable mode:

```bash
git clone https://github.com/marcellopoliti/MAS-Mission-Planning.git
cd MAS-Mission-Planning
pip install -e .
```

This installs all dependencies: `openai`, `tiktoken`, `pyyaml`, `pydantic`, `pandas`, `matplotlib`, `python-dotenv`, `rich`.

## API Keys

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Add at least one key:

```title=".env"
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
```

!!! tip "Using OpenRouter"
    [OpenRouter](https://openrouter.ai) gives access to many models (including free tiers) through a single API key. You can use cheap models for agents and route judge calls to stronger models — all through OpenRouter.

## Verify

```bash
python3 -c "from src.core.config import ExperimentConfig; print('OK')"
```

## Optional: Documentation site

To build and serve the docs locally:

```bash
pip install mkdocs-material
mkdocs serve
```

Then open [http://localhost:8000](http://localhost:8000).
