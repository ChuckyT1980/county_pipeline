"""
pipeline.py — root entry point for the unified county system.

    python pipeline.py --county fresno --stage source
    python pipeline.py --county fresno --stage all
    python pipeline.py --county tehama --stage predict

See core/pipeline.py for stage definitions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.pipeline import main

if __name__ == "__main__":
    main()
