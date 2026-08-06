"""
Daily poller: runs auction + predict for the configured counties until the
auction list publishes. Safe to run daily (resume-friendly, idempotent).

    python monitor\daily_poll.py --counties fresno,tehama,shasta,butte
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.county import CountyConfig, list_counties
from core.pipeline import run_stage

LOG = Path(__file__).resolve().parent / "daily_poll.log"


def log(msg: str):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--counties", default=",".join(list_counties()))
    args = ap.parse_args(argv)

    names = [c for c in args.counties.split(",") if c]
    for name in names:
        try:
            cfg = CountyConfig.load(name)
            log(f"=== {name} ===")
            # 1. Poll the auction platform for a published list.
            run_stage(cfg, "auction")
            ap = cfg.auction_path()
            if ap.exists() and ap.stat().st_size > 200:
                log(f"{name}: AUCTION LIST LIVE ({ap.stat().st_size} bytes)")
            else:
                log(f"{name}: list not published yet")
            # 2. Fold any finished recorder-pool output into state.
            run_stage(cfg, "import")
            # 3. Dynamic loop: fill remaining high-value gaps.
            run_stage(cfg, "loop")
        except Exception as e:
            log(f"{name} ERROR: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()
