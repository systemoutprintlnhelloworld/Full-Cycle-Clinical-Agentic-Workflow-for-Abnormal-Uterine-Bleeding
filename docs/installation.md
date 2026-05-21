# Installation

## Recommended environment

- Python 3.12.
- Windows is the canonical development environment for Word/COM manuscript
  automation.
- Linux or macOS can run most data, metric, prompt, source-data, and figure
  organization scripts that do not require Microsoft Word COM.

## Create an environment with pip

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Create an environment with conda

```bash
conda env create -f environment.yml
conda activate aub-agentic-workflow-review
```

## Credential configuration

Copy `.env.example` to `.env` and fill only the provider keys available in
your review environment. Never commit `.env`.

```bash
cp .env.example .env
```

The offline demo does not require `.env`. Full workflow reruns require
OpenAI-compatible chat-completion endpoints configured in the auto-evaluation
system snapshot and controlled raw-data access.

## Data access boundary

This repository does not include private raw clinical records. It includes
code, prompts, specifications, paper-facing source-data assets, and synthetic
toy demo data. Full raw-data reproduction requires controlled institutional
data access outside this repository.
