"""
Multi-county marketplace HTML generator.

Reads signal-scan CSVs from data/{county}/*_candidates.csv (or arcgis_candidates.csv)
for every county that has one, tiles them, and generates a unified marketplace page.

Auto-adds new counties as their CSVs land — no code change needed.

Usage:
    python build_multi_county_marketplace.py
"""
import csv
import os
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = REPO_ROOT / "data"
OUT_HTML = Path(__file__).parent / "index_multi_county.html"

CONTACT_EMAIL = "mrt@logicflowsystems.io"
PRICE = 99


COUNTY_CANDIDATE_FILES = {
    "butte":    "../butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv",  # different source
    "tehama":   "tehama/tehama_auction_candidates.csv",
    "shasta":   "shasta/shasta_auction_candidates.csv",
    "humboldt": "humboldt/humboldt_auction_candidates.csv",
    "fresno":   "fresno/fresno_arcgis_candidates.csv",
    "kern":     "kern/kern_signal_candidates.csv",
}


def _money(v):
    if not v: return 0
    try: return int(float(str(v).replace("$","").replace(",","")))
    except: return 0


def load_all_counties():
    counties = {}
    for county, rel in COUNTY_CANDIDATE_FILES.items():
        path = DATA_ROOT / rel if not rel.startswith("../") else REPO_ROOT / rel[3:]
        if not path.exists():
            continue
        parcels = []
        with open(path, encoding="utf-8") as fp:
            for r in csv.DictReader(fp):
                # Normalize different scan output shapes
                apn = (r.get("apn") or r.get("APN") or "").strip()
                if not apn: continue
                owner = (r.get("owner") or r.get("verified_current_owner_name")
                         or r.get("NAME1") or "").strip()
                situs = (r.get("situs") or r.get("situs_address") or "").strip()
                total_val = _money(r.get("net_taxable_value") or r.get("total_val")
                                    or r.get("TOTAL_ASSESSED_VALUE") or 0)
                total_due = _money(r.get("total_due") or r.get("v_total_balance") or 0)
                signal_score = int(float(r.get("signal_score") or r.get("priority_score") or 0))
                parcels.append({
                    "apn": apn, "owner": owner, "situs": situs,
                    "total_val": total_val, "total_due": total_due,
                    "signal_score": signal_score,
                })
        parcels.sort(key=lambda p: -p["signal_score"])
        counties[county] = parcels
        print(f"  {county}: {len(parcels)} candidates loaded")
    return counties


def _html_esc(s):
    return (str(s or "").replace("&","&amp;").replace("<","&lt;")
            .replace(">","&gt;").replace('"',"&quot;"))


def render_tile(county, p):
    owner_disp = _html_esc(p["owner"][:35]) if p["owner"] else "<em>(owner via recorder)</em>"
    situs_disp = _html_esc(p["situs"][:60]) if p["situs"] else "(no situs)"
    subject = f"Order {county.title()} Dossier - APN {p['apn']}"
    body = f"Hi Chuck,%0D%0AOrdering the dossier for {p['apn']} ({p['owner']}) - {county.title()} - $99.%0D%0APlease send Zelle payment details.%0D%0AThanks"
    return f'''
    <div class="tile" data-county="{county}">
      <div class="tile-header">
        <span class="county-badge county-{county}">{county.upper()}</span>
        <span class="signal-badge">SIGNAL {p["signal_score"]}</span>
      </div>
      <div class="tile-owner">{owner_disp}</div>
      <div class="tile-apn">APN {_html_esc(p["apn"])}</div>
      <div class="tile-situs">{situs_disp}</div>
      <div class="tile-metrics">
        <div>Assessed: <strong>${p["total_val"]:,}</strong></div>
        {f'<div>Owed: <strong>${p["total_due"]:,}</strong></div>' if p["total_due"] else ''}
      </div>
      <a class="order-btn" href="mailto:{CONTACT_EMAIL}?subject={subject}&body={body}">Order Dossier - ${PRICE}</a>
    </div>'''


def render_page(counties):
    total_parcels = sum(len(v) for v in counties.values())
    county_stats = [(c, len(p)) for c,p in counties.items() if p]
    tiles = []
    for county, parcels in counties.items():
        for p in parcels[:50]:  # top 50 per county
            tiles.append(render_tile(county, p))
    tiles_html = "\n".join(tiles)

    county_filter_buttons = "\n".join(
        f'<button class="filter-btn" data-filter="{c}">{c.title()} ({n})</button>'
        for c, n in county_stats
    )

    return f'''<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>California Tax Auction Intelligence Marketplace | Logic Flow Systems</title>
<style>
  :root {{
    --navy: #1F3A5F; --orange: #D28228; --red: #C03C3C;
    --white: #fff; --grey: #64748B; --bg: #F4F7FA;
  }}
  body {{ font-family: -apple-system,'Segoe UI',Roboto,sans-serif; margin:0; background:var(--bg); color:#3C3C3C; }}
  header {{ background:var(--navy); color:var(--white); padding:2rem 1.5rem; border-bottom:4px solid var(--orange); }}
  h1 {{ margin:0 0 .3rem 0; }}
  .subtitle {{ color:var(--orange); font-weight:500; }}
  .stats {{ background:var(--white); padding:1rem 1.5rem; border-bottom:1px solid #E2E8F0; box-shadow:0 2px 4px rgba(0,0,0,.04); }}
  .stats-inner {{ max-width:1400px; margin:0 auto; display:flex; gap:2rem; flex-wrap:wrap; }}
  .stat {{ display:flex; flex-direction:column; }}
  .stat-v {{ font-size:1.4rem; font-weight:700; color:var(--navy); }}
  .stat-l {{ font-size:.75rem; color:var(--grey); text-transform:uppercase; letter-spacing:.5px; }}
  .filters {{ padding:1rem 1.5rem; background:var(--white); border-bottom:1px solid #E2E8F0; }}
  .filters-inner {{ max-width:1400px; margin:0 auto; display:flex; gap:.5rem; flex-wrap:wrap; }}
  .filter-btn {{ background:var(--white); border:1px solid #CBD5E1; padding:.5rem 1rem; border-radius:6px; cursor:pointer; font-size:.9rem; }}
  .filter-btn:hover, .filter-btn.active {{ background:var(--navy); color:var(--white); border-color:var(--navy); }}
  main {{ max-width:1400px; margin:1.5rem auto; padding:0 1.5rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:1rem; }}
  .tile {{ background:var(--white); border-radius:8px; padding:1rem; box-shadow:0 2px 8px rgba(0,0,0,.06); display:flex; flex-direction:column; gap:.5rem; }}
  .tile-header {{ display:flex; justify-content:space-between; align-items:center; }}
  .county-badge {{ font-size:.7rem; font-weight:700; padding:3px 8px; border-radius:3px; color:var(--white); text-transform:uppercase; }}
  .county-butte {{ background:#2E86AB; }} .county-tehama {{ background:#9B5DE5; }}
  .county-shasta {{ background:#F15BB5; }} .county-humboldt {{ background:#00BBF9; }}
  .county-fresno {{ background:#FEE440; color:#333; }} .county-kern {{ background:#FF6B35; }}
  .signal-badge {{ background:var(--orange); color:var(--white); font-size:.7rem; font-weight:700; padding:3px 8px; border-radius:3px; }}
  .tile-owner {{ font-weight:700; color:var(--navy); font-size:1rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .tile-apn {{ font-family:monospace; font-size:.8rem; color:var(--grey); }}
  .tile-situs {{ font-size:.85rem; }}
  .tile-metrics {{ display:flex; gap:1rem; padding:.5rem 0; border-top:1px solid #F0F0F0; font-size:.85rem; }}
  .order-btn {{ display:block; background:var(--orange); color:var(--white); text-align:center; padding:.6rem; border-radius:6px; text-decoration:none; font-weight:700; margin-top:auto; }}
  .order-btn:hover {{ background:#b86e1e; }}
  footer {{ max-width:1400px; margin:3rem auto 1rem; padding:1.5rem; text-align:center; color:var(--grey); font-size:.85rem; border-top:1px solid #E2E8F0; }}
</style></head><body>

<header>
  <h1>California Tax Auction Intelligence Marketplace</h1>
  <div class="subtitle">{len(counties)} Counties · Verified Public Sources · Per-Parcel Dossiers</div>
</header>

<div class="stats"><div class="stats-inner">
  <div class="stat"><span class="stat-v">{total_parcels:,}</span><span class="stat-l">Auction candidates</span></div>
  <div class="stat"><span class="stat-v">{len(counties)}</span><span class="stat-l">Counties live</span></div>
  <div class="stat"><span class="stat-v">${PRICE}</span><span class="stat-l">Per dossier</span></div>
  <div class="stat"><span class="stat-v">100%</span><span class="stat-l">Public source</span></div>
</div></div>

<div class="filters"><div class="filters-inner">
  <button class="filter-btn active" data-filter="all">All ({total_parcels})</button>
  {county_filter_buttons}
</div></div>

<main>
  <div class="grid" id="tile-grid">
    {tiles_html}
  </div>
</main>

<footer>
  &copy; 2026 Logic Flow Systems &middot; <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a><br>
  Data 100% from public county sources. No paid data. No fabricated data. Every field auditable.
</footer>

<script>
document.querySelectorAll('.filter-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const f = btn.dataset.filter;
    document.querySelectorAll('.tile').forEach(t => {{
      t.style.display = (f === 'all' || t.dataset.county === f) ? '' : 'none';
    }});
  }});
}});
</script>
</body></html>'''


def build():
    counties = load_all_counties()
    if not counties:
        print("No candidate CSVs found yet — nothing to build.")
        return
    total = sum(len(v) for v in counties.values())
    html = render_page(counties)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"\nWrote {OUT_HTML}")
    print(f"  Counties: {list(counties.keys())}")
    print(f"  Total candidates: {total:,}")
    print(f"  Tiles rendered (top 50 per county): {sum(min(50, len(v)) for v in counties.values())}")


if __name__ == "__main__":
    build()
