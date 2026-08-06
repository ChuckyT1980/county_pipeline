# Setup Guide

## Recommended Python Version

Use **Python 3.11 or 3.12** (current LTS/stable releases).  
Python 3.14 is pre-release and may introduce standard-library breaking changes.

## Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Install Playwright Browsers (required for cloud enrichment and tax pipeline)

```bash
playwright install chromium
```

## Run Tests

```bash
python3 -m unittest discover tests/ -v
```

## Run the Pipeline

```bash
make run
# or
python3 run_controller.py
```

## Notes

- The project uses SQLite with WAL mode enabled for scheduler concurrency.
- All paths are relative to the project root; do not rely on `C:\Users\...` hardcoded paths.
