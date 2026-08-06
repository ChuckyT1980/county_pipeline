"""
core/auction.py

Unified auction-platform connector.

  realauction  — poll a county's Realauction preview page (login-backed
                 persistent session) and extract the item list when it
                 populates.
  pdf          — fetch + parse a published auction/Notice-of-Sale PDF
                 (Playwright-backed where Akamai-protected).

Both emit the standard auction_list.csv:
    county, source, auction_date, item_no, apn, min_bid,
    sales_price, excess_proceeds
"""
import csv
import os
import re
from pathlib import Path


def import_sold_results(cfg, out_path=None) -> Path:
    """Import the county's published sold-results CSV (the 'Report of
    Properties Sold and Excess Proceeds' list) into the standard
    auction_list.csv schema. Expected input columns: apn, min_bid,
    sales_price (or sold_price/winning_bid_amount), excess_proceeds (or
    computed), auction_date, optionally item_no/source_pdf.

    This is what feeds the excess-proceeds track: min_bid + sold price +
    county-published excess, joined in state with the tax-deed former
    owner and deed date from the recorder.
    """
    out_path = out_path or cfg.auction_path()
    src = cfg.data_dir() / "sold_results.csv"
    if not src.exists():
        print(f"[auction:{cfg.county}] no sold_results.csv at {src}")
        return out_path

    import json
    rows = []
    with open(src, newline="", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            apn = (row.get("apn") or "").strip().replace("-", "")
            if not apn:
                continue
            price = (row.get("sales_price") or row.get("sold_price")
                     or row.get("winning_bid_amount") or "").strip()
            excess = (row.get("excess_proceeds") or "").strip()
            rows.append({
                "county": cfg.county,
                "source": row.get("source_pdf") or row.get("source") or "sold_results",
                "auction_date": (row.get("auction_date") or "").strip(),
                "item_no": (row.get("item_no") or "").strip(),
                "apn": apn,
                "min_bid": (row.get("min_bid") or "").strip(),
                "sales_price": price,
                "excess_proceeds": excess,
            })
    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            "county", "source", "auction_date", "item_no", "apn",
            "min_bid", "sales_price", "excess_proceeds"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[auction:{cfg.county}] sold results: {len(rows)} rows -> {out_path}")
    return out_path


def poll_preview(cfg, out_path=None, session_dir=None) -> Path:
    """Poll the Realauction preview for the configured auction dates.

    Returns the path to auction_list.csv (empty file if no items yet).
    """
    out_path = out_path or cfg.auction_path()
    backend = cfg.auction.backend
    if backend != "realauction":
        # GovEase / unconfigured placeholders: write an empty list rather
        # than fail — these counties simply have no live auction source.
        print(f"[auction:{cfg.county}] backend '{backend}' has no live "
              f"poller; empty list")
        with open(out_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=[
                "county", "source", "auction_date", "item_no", "apn",
                "min_bid", "sales_price", "excess_proceeds"])
            writer.writeheader()
        return out_path

    session_dir = session_dir or (Path(__file__).resolve().parent.parent / "fresno" / ".playwright_session")
    rows = _realauction_extract(cfg, session_dir)

    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=[
            "county", "source", "auction_date", "item_no", "apn",
            "min_bid", "sales_price", "excess_proceeds"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[auction:{cfg.county}] preview: {len(rows)} items -> {out_path}")
    return out_path


def _realauction_extract(cfg, session_dir):
    import asyncio
    from playwright.async_api import async_playwright

    dates = getattr(cfg.auction, "auction_dates", None) or []
    if not dates:
        return []

    async def run():
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir), headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                viewport={"width": 1440, "height": 1000})
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            rows = []
            for d in dates:
                url = f"{cfg.auction.preview_url}{d}"
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(5000)
                    html = await page.content()
                    # item rows: look for APN-like tokens + item markers
                    items = _parse_items_html(html, d)
                    print(f"[auction:{cfg.county}] {d}: {len(items)} items")
                    rows.extend(items)
                except Exception as e:
                    print(f"[auction:{cfg.county}] {d} ERR: {type(e).__name__} {str(e)[:100]}")
            await ctx.close()
            return rows

    return asyncio.run(run())


def _parse_items_html(html, date) -> list[dict]:
    """Extract item rows from a Realauction preview page.

    Item rows contain APNs (e.g. XXX-XXX-XX) and parcel descriptions.
    Empty list means the list isn't published yet.
    """
    rows = []
    # APN pattern in item rows
    apn_re = re.compile(r"(\d{3}-\d{3}-\d{2}[ST]?)", re.I)
    seen = set()
    for m in apn_re.finditer(html):
        apn = m.group(1)
        if apn in seen:
            continue
        seen.add(apn)
        rows.append({"county": "", "source": "realauction", "auction_date": date,
                     "item_no": "", "apn": apn, "min_bid": "",
                     "sales_price": "", "excess_proceeds": ""})
    return rows


def fetch_pdf(cfg, out_path=None, download_dir=None) -> Path:
    """Fetch + parse a published auction list PDF (Playwright for Akamai)."""
    out_path = out_path or cfg.auction_path()
    download_dir = download_dir or (Path(__file__).resolve().parent.parent / "fresno" / "downloaded_pdfs")
    raise NotImplementedError("PDF auction intake — wire after preview poller validated")
