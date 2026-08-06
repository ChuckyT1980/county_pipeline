"""
Build the Logic Flow Systems marketplace HTML page.

Reads the Butte call sheet, generates one tile per mail-ready parcel with:
  - Aerial thumbnail (Esri satellite when we have geocode)
  - Owner name, APN, situs city, defaulted balance, priority score
  - "Order Dossier - $99" mailto: button (MVP — manual fulfillment via Zelle)

Ships:
  marketplace/index.html         (static, deployable to Netlify)
  marketplace/thumbs/<APN>.png   (aerial thumbnails)
  marketplace/README.md          (deployment + workflow instructions)

MVP fulfillment flow:
  1. Buyer clicks "Order Dossier - $99" on a tile
  2. Their email client opens with pre-filled subject "Order Dossier - APN <apn>"
  3. Chuck receives the order email
  4. Chuck replies with Zelle payment request
  5. Buyer sends $99 via Zelle
  6. Chuck emails the dossier PDF
  7. Turnaround: <30 minutes if Chuck is online

Upgrade path: replace mailto: with Stripe Checkout URLs. Zero HTML changes needed
beyond the href.
"""
import csv
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
CALL_SHEET = REPO_ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"
DOSSIER_DIR = REPO_ROOT / "butte" / "delivery" / "butte_auction_2026-07-31" / "dossiers"
AERIAL_DIR = REPO_ROOT / "butte" / "parcel_images"

MARKETPLACE = REPO_ROOT / "marketplace"
THUMBS = MARKETPLACE / "thumbs"

CONTACT_EMAIL = "mrt@logicflowsystems.io"
PRICE = 99


def _money(v):
    if not v:
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _extract_city(situs):
    if not situs or situs.lower() in ("nan", "none", ""):
        return "No Situs"
    parts = situs.strip().upper().split()
    for city in ["STIRLING CITY", "BERRY CREEK", "FEATHER FALLS", "FOREST RANCH",
                 "YANKEE HILL", "CLIPPER MILLS", "PARADISE", "MAGALIA", "OROVILLE",
                 "CONCOW", "CHICO", "GRIDLEY", "BIGGS", "COHASSET", "PALERMO",
                 "BANGOR", "DURHAM"]:
        if situs.strip().upper().endswith(city):
            return city.title()
    return parts[-1].title() if parts else "Unknown"


def load_parcels():
    rows = []
    with open(CALL_SHEET, encoding="utf-8") as fp:
        for r in csv.DictReader(fp):
            if r.get("mail_ready_status") != "yes":
                continue
            apn = r.get("apn", "").strip()
            if not apn:
                continue
            rows.append({
                "apn": apn,
                "owner": r.get("verified_current_owner_name", "").strip(),
                "situs_city": _extract_city(r.get("situs_address", "")),
                "situs_full": r.get("situs_address", "").strip(),
                "balance": _money(r.get("v_total_balance")),
                "priority": float(r.get("priority_score", 0) or 0),
                "distress": int(float(r.get("distress_signal_score", 0) or 0)),
                "absentee": r.get("out_of_state") == "Y",
                "owner_state": r.get("owner_state", "").strip(),
                "land_val": _money(r.get("land_value")),
                "imp_val": _money(r.get("improvements_value")),
            })
    rows.sort(key=lambda r: r["priority"], reverse=True)
    return rows


def copy_thumbs(parcels):
    """Copy aerial images to marketplace/thumbs/ for public serving."""
    THUMBS.mkdir(parents=True, exist_ok=True)
    have_thumb = set()
    for p in parcels:
        src = AERIAL_DIR / f"{p['apn']}_sat.png"
        if src.exists():
            dst = THUMBS / f"{p['apn']}.png"
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                shutil.copy(src, dst)
            have_thumb.add(p["apn"])
    return have_thumb


def render_tile(p, has_thumb):
    thumb_html = (
        f'<img src="thumbs/{p["apn"]}.png" alt="Aerial {p["apn"]}" loading="lazy" />'
        if has_thumb
        else '<div class="thumb-placeholder">No aerial available</div>'
    )

    absentee_pill = (
        f'<span class="pill pill-absentee">OUT-OF-STATE ({p["owner_state"]})</span>'
        if p["absentee"] else ""
    )
    distress_pill = (
        f'<span class="pill pill-distress">DISTRESS {p["distress"]}</span>'
        if p["distress"] >= 40 else ""
    )

    subject = f"Order Dossier - APN {p['apn']}"
    body = (
        f"Hi Chuck,%0D%0A%0D%0A"
        f"I would like to order the dossier for APN {p['apn']} ({p['owner']}) for $99.%0D%0A%0D%0A"
        f"Please send Zelle payment details.%0D%0A%0D%0A"
        f"Thanks,%0D%0A"
    )
    order_href = f"mailto:{CONTACT_EMAIL}?subject={subject}&body={body}"

    return f'''
    <div class="tile">
      <div class="tile-thumb">{thumb_html}</div>
      <div class="tile-body">
        <div class="tile-header">
          <span class="tile-priority">PRIORITY {p["priority"]:.0f}</span>
          {absentee_pill}
          {distress_pill}
        </div>
        <div class="tile-owner">{_html_escape(p["owner"])}</div>
        <div class="tile-apn">APN {p["apn"]}</div>
        <div class="tile-situs">{_html_escape(p["situs_city"])}</div>
        <div class="tile-metrics">
          <div class="metric">
            <div class="metric-label">Defaulted</div>
            <div class="metric-value">${p["balance"]:,.0f}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Assessed</div>
            <div class="metric-value">${(p["land_val"] + p["imp_val"]):,.0f}</div>
          </div>
        </div>
        <a class="order-btn" href="{order_href}">Order Dossier &mdash; ${PRICE}</a>
      </div>
    </div>
    '''


def _html_escape(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_page(parcels, thumb_set):
    total_balance = sum(p["balance"] for p in parcels)
    tiles_html = "\n".join(render_tile(p, p["apn"] in thumb_set) for p in parcels)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>California Tax Auction Intelligence Marketplace | Logic Flow Systems</title>
<meta name="description" content="Verified per-parcel intelligence dossiers for California tax auctions. $99 each. Butte County Aug 7-10 auction inventory now available.">
<style>
  :root {{
    --navy: #1F3A5F; --navy-light: #2E86AB; --orange: #D28228;
    --red: #C03C3C; --grey-dark: #3C3C3C; --grey-mid: #78788C;
    --bg-light: #E8F1F7; --white: #FFFFFF; --shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         margin: 0; background: #F4F7FA; color: var(--grey-dark); line-height: 1.5; }}
  header {{ background: var(--navy); color: var(--white); padding: 2rem 1.5rem;
            border-bottom: 4px solid var(--orange); }}
  header .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ margin: 0 0 0.5rem 0; font-size: 1.9rem; }}
  header .tagline {{ margin: 0; color: var(--orange); font-weight: 500; }}

  .stats-bar {{ background: var(--white); padding: 1rem 1.5rem; box-shadow: var(--shadow);
                border-bottom: 1px solid #E2E8F0; }}
  .stats-bar .container {{ max-width: 1200px; margin: 0 auto; display: flex; gap: 2rem;
                            flex-wrap: wrap; align-items: center; }}
  .stat {{ display: flex; flex-direction: column; }}
  .stat-value {{ font-size: 1.3rem; font-weight: 700; color: var(--navy); }}
  .stat-label {{ font-size: 0.8rem; color: var(--grey-mid); text-transform: uppercase;
                  letter-spacing: 0.5px; }}

  .intro {{ background: var(--bg-light); padding: 1.5rem; border-left: 4px solid var(--navy-light); }}
  .intro .container {{ max-width: 1200px; margin: 0 auto; }}
  .intro p {{ margin: 0.5rem 0; }}
  .intro strong {{ color: var(--navy); }}

  main {{ max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }}
  h2 {{ color: var(--navy); font-size: 1.4rem; margin: 0 0 0.5rem 0; }}
  .county-note {{ color: var(--grey-mid); font-size: 0.9rem; margin-bottom: 1.5rem; }}

  .tile-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: 1.5rem; }}

  .tile {{ background: var(--white); border-radius: 8px; overflow: hidden;
           box-shadow: var(--shadow); display: flex; flex-direction: column;
           transition: transform 0.15s ease, box-shadow 0.15s ease; }}
  .tile:hover {{ transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12); }}

  .tile-thumb {{ height: 160px; background: #E8E8E8; overflow: hidden; position: relative; }}
  .tile-thumb img {{ width: 100%; height: 100%; object-fit: cover; }}
  .thumb-placeholder {{ display: flex; align-items: center; justify-content: center;
                         height: 100%; color: var(--grey-mid); font-size: 0.9rem;
                         font-style: italic; }}

  .tile-body {{ padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem; flex: 1; }}
  .tile-header {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.3rem; }}
  .pill {{ font-size: 0.65rem; font-weight: 700; padding: 3px 8px; border-radius: 3px;
           color: var(--white); text-transform: uppercase; letter-spacing: 0.5px; }}
  .tile-priority {{ background: var(--navy-light); color: var(--white); font-size: 0.7rem;
                     font-weight: 700; padding: 3px 8px; border-radius: 3px; letter-spacing: 0.5px; }}
  .pill-absentee {{ background: var(--orange); }}
  .pill-distress {{ background: var(--red); }}

  .tile-owner {{ font-weight: 700; font-size: 1.05rem; color: var(--navy);
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .tile-apn {{ font-size: 0.8rem; color: var(--grey-mid); font-family: monospace; }}
  .tile-situs {{ font-size: 0.9rem; color: var(--grey-dark); }}

  .tile-metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;
                    margin: 0.5rem 0; padding: 0.5rem 0; border-top: 1px solid #F0F0F0;
                    border-bottom: 1px solid #F0F0F0; }}
  .metric-label {{ font-size: 0.7rem; color: var(--grey-mid); text-transform: uppercase;
                    letter-spacing: 0.5px; }}
  .metric-value {{ font-size: 1rem; font-weight: 700; color: var(--navy); }}

  .order-btn {{ display: block; background: var(--orange); color: var(--white);
                text-align: center; padding: 0.7rem; border-radius: 6px;
                text-decoration: none; font-weight: 700; margin-top: auto;
                transition: background 0.15s ease; }}
  .order-btn:hover {{ background: #b06f1e; }}

  footer {{ max-width: 1200px; margin: 3rem auto 1rem; padding: 2rem 1.5rem;
            border-top: 1px solid #E2E8F0; color: var(--grey-mid); font-size: 0.85rem;
            text-align: center; }}
  footer a {{ color: var(--navy); }}
</style>
</head>
<body>

<header>
  <div class="container">
    <h1>California Tax Auction Intelligence Marketplace</h1>
    <p class="tagline">Verified per-parcel dossiers  |  Public sources  |  Live-verified</p>
  </div>
</header>

<div class="stats-bar">
  <div class="container">
    <div class="stat"><span class="stat-value">{len(parcels)}</span><span class="stat-label">Parcels available</span></div>
    <div class="stat"><span class="stat-value">${total_balance:,.0f}</span><span class="stat-label">Total defaulted</span></div>
    <div class="stat"><span class="stat-value">${PRICE}</span><span class="stat-label">Per dossier</span></div>
    <div class="stat"><span class="stat-value">Aug 7-10</span><span class="stat-label">Auction dates</span></div>
  </div>
</div>

<div class="intro">
  <div class="container">
    <p><strong>Each dossier includes:</strong> Owner name + mailing + situs + defaulted balance + assessed values + recorder document history + distress signals + fire/flood hazard + aerial view + tax bill archive.</p>
    <p><strong>How it works:</strong> Click <em>Order Dossier &mdash; $99</em> on any parcel. Your email client will open with a pre-filled order. Chuck will reply with Zelle payment details. You get the PDF within 30 minutes of payment.</p>
    <p><strong>Guarantee:</strong> If any material field is wrong &mdash; owner, mailing, defaulted balance &mdash; full refund on that parcel. Every field cross-referenced against live county records.</p>
  </div>
</div>

<main>
  <h2>Butte County  |  Aug 7-10, 2026 Auction</h2>
  <p class="county-note">{len(parcels)} mail-ready parcels sorted by priority score. Fresno &amp; other counties launching Sept 2026.</p>

  <div class="tile-grid">
    {tiles_html}
  </div>
</main>

<footer>
  <p>&copy; 2026 Logic Flow Systems &middot; Charles Terrell &middot; <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
  <p>Data sourced 100% from public county records. No fabricated data. Every parcel verified against live tax collector, assessor, and recorder systems.</p>
</footer>

</body>
</html>
'''


def build():
    MARKETPLACE.mkdir(parents=True, exist_ok=True)
    parcels = load_parcels()
    print(f"Loaded {len(parcels)} mail-ready parcels")

    thumb_set = copy_thumbs(parcels)
    print(f"Copied {len(thumb_set)} aerial thumbs")

    html = render_page(parcels, thumb_set)
    out = MARKETPLACE / "index.html"
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size
    print(f"Wrote {out} ({size:,} bytes, {len(parcels)} tiles)")

    # Also generate a small README for deployment
    readme = MARKETPLACE / "README.md"
    readme.write_text(f"""# Logic Flow Systems Marketplace

**Deploy to Netlify:**
1. Go to https://app.netlify.com/drop
2. Drag this entire `marketplace/` folder onto the page
3. Get a live URL like `xyz.netlify.app`
4. Optionally: point `intel.logicflowsystems.io` DNS at Netlify

**Local test:**
Open `index.html` in your browser. All tiles work as `mailto:` orders.

**Fulfillment workflow:**
1. Buyer clicks tile → email opens with order details
2. You receive email, reply with Zelle request for $99
3. Buyer pays → you email the dossier PDF from `butte/delivery/butte_auction_2026-07-31/dossiers/`
4. Turnaround target: <30 min while you're online

**Upgrade to automated Stripe:**
Replace the `mailto:` href in each tile with a Stripe Checkout URL. Set up
one Stripe product per parcel or use dynamic pricing. Webhook triggers auto-email
of the dossier PDF on payment success.

**Files:**
- `index.html` — the marketplace page ({len(parcels)} tiles, static, no backend needed)
- `thumbs/` — aerial thumbnails ({len(thumb_set)} images)
- `README.md` — this file
""", encoding="utf-8")
    print(f"Wrote {readme}")

    return out


if __name__ == "__main__":
    build()
