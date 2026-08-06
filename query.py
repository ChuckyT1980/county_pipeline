"""
query.py — interrogate the unified county dataset.

    python query.py --county fresno --where "tax_deed='yes'"
    python query.py --county fresno --sql "SELECT * FROM parcels WHERE values != '' LIMIT 5"
    python query.py --county fresno --summary

The state store is plain SQLite — any SQL tool works too.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.county import CountyConfig, list_counties


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", required=True, choices=list_counties())
    ap.add_argument("--sql", default="", help="raw SQL query")
    ap.add_argument("--where", default="", help="WHERE clause on parcels")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)

    cfg = CountyConfig.load(args.county)
    db = cfg.data_dir() / "state.sqlite"
    if not db.exists():
        print(f"no state store yet for {cfg.county} — run: pipeline.py --county {cfg.county} --stage source")
        return

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    if args.summary:
        cols = conn.execute("PRAGMA table_info(parcels)").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM parcels").fetchone()[0]
        print(f"{cfg.county}: {total:,} parcels in state\n")
        for c in cols:
            if c["name"].endswith("_known"):
                f = c["name"][:-6]
                n = conn.execute(f'SELECT COUNT(*) FROM parcels WHERE "{c["name"]}"=1').fetchone()[0]
                print(f"  {f:16s} {n:>10,} known ({100*n/total:.0f}%)")
        # passes log
        print("\nloop passes:")
        for row in conn.execute("SELECT * FROM passes ORDER BY id DESC LIMIT 10"):
            print(f"  {row['ts']}  {row['action']:20s} {row['count']}")
        conn.close()
        return

    if args.sql:
        q = args.sql
    elif args.where:
        q = ('SELECT apn, owner, former_owner, tax_deed, "values", '
             'situs, use, mailing FROM parcels WHERE '
             + args.where + f" LIMIT {args.limit}")
    else:
        q = ('SELECT apn, owner, former_owner, tax_deed, "values", situs '
             f"FROM parcels LIMIT {args.limit}")

    try:
        for row in conn.execute(q):
            print(" | ".join(f"{k}={row[k]}" for k in row.keys() if row[k] not in (None, "")))
    except sqlite3.Error as e:
        print(f"SQL error: {e}")
    conn.close()


if __name__ == "__main__":
    main()
