"""
County Pipeline Intelligence Dashboard v2

Runs alongside the existing dashboard.py. Focused on the new products
built in this session:
  - Auction leads (Butte call sheet + full verification stack)
  - Surplus recovery (open claims + outreach tracking)
  - Recorder graph explorer (portfolio + partner network)
  - Financial pipeline (revenue projection + skip-trace spend)

Data sources:
  - verification.sqlite (recorder graph, verification runs, field provenance)
  - surplus.sqlite (surplus opportunities, skip trace, outreach events)
  - butte/butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (live call sheet)

Launch:
  streamlit run dashboard_intel.py
"""
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# ── Config ─────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
VERIFICATION_DB = REPO_ROOT / "verification.sqlite"
SURPLUS_DB      = REPO_ROOT / "surplus.sqlite"
BUTTE_CALL_SHEET = REPO_ROOT / "butte" / "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"

st.set_page_config(
    page_title="County Pipeline Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Data loaders (cached with short TTL for near-real-time refresh) ───

@st.cache_data(ttl=30)
def load_call_sheet(csv_path: Path = BUTTE_CALL_SHEET) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path, dtype=str)
    # Numeric coercions for filtering
    for col in ["priority_score", "portfolio_apn_count", "portfolio_apn_balance",
                "distress_signal_score", "ownership_confidence", "verification_score"]:
        if col in df.columns:
            df[col + "_num"] = pd.to_numeric(df[col], errors="coerce")
    df["balance_num"] = df["v_total_balance"].apply(_money_to_float)
    return df


@st.cache_data(ttl=30)
def load_surplus() -> pd.DataFrame:
    if not SURPLUS_DB.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(str(SURPLUS_DB))
    df = pd.read_sql_query(
        """SELECT s.*,
                  st.current_address AS trace_current_address,
                  st.phones_json AS trace_phones_json,
                  st.emails_json AS trace_emails_json,
                  st.is_deceased AS trace_deceased,
                  st.provider AS trace_provider
             FROM surplus_opportunities s
             LEFT JOIN skip_trace_results st ON st.canonical_name = s.former_owner_canonical
            ORDER BY s.surplus_amount DESC""",
        conn,
    )
    conn.close()
    if not df.empty:
        df["surplus_amount"] = pd.to_numeric(df["surplus_amount"], errors="coerce")
        df["days_left"] = df["claim_deadline_at"].apply(_days_until)
    return df


@st.cache_data(ttl=30)
def load_graph_stats() -> dict:
    if not VERIFICATION_DB.exists():
        return {}
    conn = sqlite3.connect(str(VERIFICATION_DB))
    row = conn.execute(
        """SELECT
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='doc') AS docs,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='person') AS persons,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='entity') AS entities,
            (SELECT COUNT(*) FROM graph_nodes WHERE node_kind='parcel') AS parcels,
            (SELECT COUNT(*) FROM graph_edges) AS edges,
            (SELECT COUNT(*) FROM verification_runs) AS runs,
            (SELECT COUNT(*) FROM verification_flags WHERE severity IN ('warn','error')) AS flags
        """
    ).fetchone()
    conn.close()
    return {
        "docs": row[0] or 0, "persons": row[1] or 0, "entities": row[2] or 0,
        "parcels": row[3] or 0, "edges": row[4] or 0,
        "runs": row[5] or 0, "flags": row[6] or 0,
    }


@st.cache_data(ttl=30)
def load_skip_trace_ledger() -> pd.DataFrame:
    if not SURPLUS_DB.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(str(SURPLUS_DB))
    df = pd.read_sql_query(
        "SELECT * FROM skip_trace_ledger ORDER BY requested_at DESC LIMIT 1000",
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=30)
def load_outreach_events() -> pd.DataFrame:
    if not SURPLUS_DB.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(str(SURPLUS_DB))
    df = pd.read_sql_query(
        "SELECT * FROM outreach_events ORDER BY sent_at DESC LIMIT 500",
        conn,
    )
    conn.close()
    return df


def graph_query_by_owner(canonical_name: str) -> pd.DataFrame:
    """All documents where this person is grantor or grantee."""
    if not VERIFICATION_DB.exists() or not canonical_name:
        return pd.DataFrame()
    conn = sqlite3.connect(str(VERIFICATION_DB))
    df = pd.read_sql_query(
        """
        SELECT DISTINCT doc.doc_number,
                        json_extract(doc.extra_json, '$.doc_type') AS doc_type,
                        json_extract(doc.extra_json, '$.recording_date') AS recorded,
                        e.edge_kind AS role
          FROM graph_nodes p
          JOIN graph_edges e ON e.from_node_id = p.id AND e.edge_kind IN ('grantor','grantee')
          JOIN graph_nodes doc ON doc.id = e.to_node_id AND doc.node_kind='doc'
         WHERE p.canonical_name = ?
         ORDER BY recorded DESC""",
        conn, params=(canonical_name,),
    )
    conn.close()
    return df


# ── Helpers ────────────────────────────────────────────────────────────

def _money_to_float(v):
    if pd.isna(v):
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def _fmt_money(v):
    if v is None or pd.isna(v):
        return "-"
    return f"${v:,.0f}"


def _days_until(iso_date):
    if not iso_date or pd.isna(iso_date):
        return None
    try:
        d = date.fromisoformat(str(iso_date)[:10])
        return (d - date.today()).days
    except (ValueError, TypeError):
        return None


def _urgency_emoji(days):
    if days is None:
        return "?"
    if days < 0:
        return "X"       # expired
    if days < 60:
        return "!!"      # urgent
    if days < 180:
        return "!"
    return "OK"


def update_surplus_status(surplus_id: int, new_status: str, notes: str = "") -> None:
    conn = sqlite3.connect(str(SURPLUS_DB))
    now_iso = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE surplus_opportunities SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, now_iso, surplus_id),
    )
    # Also log an outreach event for the status change
    channel_map = {
        "traced": "trace", "mailed": "mail", "signed": "signed",
        "filed": "filed", "paid": "paid", "disqualified": "disqualified",
    }
    conn.execute(
        """INSERT INTO outreach_events (surplus_id, channel, outcome, notes, sent_at)
             VALUES (?, ?, ?, ?, ?)""",
        (surplus_id, channel_map.get(new_status, "manual"), new_status, notes, now_iso),
    )
    conn.commit()
    conn.close()
    st.cache_data.clear()


# ── Sidebar: page selector ────────────────────────────────────────────

st.sidebar.title("Intelligence")
page = st.sidebar.radio(
    "Section",
    ["Overview", "Auction Leads", "Surplus Recovery", "Outreach Pipeline",
     "Graph Explorer", "Financial"],
)

st.sidebar.divider()
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(f"Last refresh: {datetime.now():%Y-%m-%d %H:%M:%S}")


# ── Page: Overview ────────────────────────────────────────────────────

if page == "Overview":
    st.title("County Pipeline Intelligence")
    st.caption("Live rollup across the tax pipeline and surplus recovery products")

    call_sheet = load_call_sheet()
    surplus = load_surplus()
    graph = load_graph_stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Auction leads (Butte)", len(call_sheet) if not call_sheet.empty else 0)
    c2.metric("Surplus opportunities", len(surplus) if not surplus.empty else 0)
    c3.metric("Recorder graph docs", f"{graph.get('docs', 0):,}")
    c4.metric("Cross-referenced people/entities",
              f"{graph.get('persons', 0) + graph.get('entities', 0):,}")

    st.divider()

    if not call_sheet.empty:
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("Tax Pipeline")
            total_bal = call_sheet["balance_num"].sum()
            portfolio_ct = int((call_sheet.get("portfolio_apn_count_num", pd.Series()) >= 2).sum())
            absentee_ct = int((call_sheet.get("out_of_state") == "Y").sum())
            st.metric("Total defaulted balance", _fmt_money(total_bal))
            st.metric("Portfolio owners (>=2 parcels)", portfolio_ct)
            st.metric("Out-of-state absentees", absentee_ct)
        with col_r:
            st.subheader("Surplus Recovery")
            if not surplus.empty:
                open_claims = surplus[surplus["days_left"] > 0]
                total_surplus = open_claims["surplus_amount"].sum()
                expected_fees = total_surplus * 0.10   # 10% contingency
                st.metric("Open claims (in window)", len(open_claims))
                st.metric("Total open surplus", _fmt_money(total_surplus))
                st.metric("Expected @ 10% (if all convert)", _fmt_money(expected_fees))
            else:
                st.info("No surplus opportunities ingested yet. Run: `python -m surplus.ingest`")

    st.divider()
    st.subheader("Data health")
    st.write(f"- Verification DB: {'OK' if VERIFICATION_DB.exists() else 'MISSING'}   ({VERIFICATION_DB})")
    st.write(f"- Surplus DB:      {'OK' if SURPLUS_DB.exists() else 'MISSING'}   ({SURPLUS_DB})")
    st.write(f"- Call sheet CSV:  {'OK' if BUTTE_CALL_SHEET.exists() else 'MISSING'}   ({BUTTE_CALL_SHEET})")
    st.write(f"- Verification runs: {graph.get('runs', 0)}  |  Open verification flags: {graph.get('flags', 0)}")


# ── Page: Auction Leads ───────────────────────────────────────────────

elif page == "Auction Leads":
    st.title("Auction Leads")
    df = load_call_sheet()
    if df.empty:
        st.warning("No call sheet loaded. Expected at: " + str(BUTTE_CALL_SHEET))
        st.stop()

    # Filters in sidebar
    st.sidebar.markdown("### Filters")
    min_score = st.sidebar.slider("Min priority score", 0, 100, 50)
    min_balance = st.sidebar.number_input("Min defaulted balance", value=0, step=1000)
    absentee_only = st.sidebar.checkbox("Absentee only")
    portfolio_only = st.sidebar.checkbox("Portfolio owners only (>=2 parcels)")
    fire_hazard_only = st.sidebar.checkbox("Fire hazard only (High/Very High)")
    with_distress = st.sidebar.checkbox("Has distress signals")

    mask = df["priority_score_num"] >= min_score
    mask &= df["balance_num"] >= min_balance
    if absentee_only:
        mask &= df["out_of_state"] == "Y"
    if portfolio_only:
        mask &= df["portfolio_apn_count_num"] >= 2
    if fire_hazard_only:
        mask &= df["fire_hazard_zone"].isin(["High", "Very High"])
    if with_distress:
        mask &= df["distress_signal_score_num"] > 0

    filtered = df[mask].sort_values("priority_score_num", ascending=False)

    st.write(f"**{len(filtered)}** of {len(df)} leads match your filters")

    # Summary strip
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total balance", _fmt_money(filtered["balance_num"].sum()))
    c2.metric("Avg priority", f"{filtered['priority_score_num'].mean():.1f}" if len(filtered) else "-")
    c3.metric("Absentee",
              int((filtered.get("out_of_state") == "Y").sum()) if len(filtered) else 0)
    c4.metric("Portfolio owners",
              int((filtered.get("portfolio_apn_count_num", pd.Series()) >= 2).sum()) if len(filtered) else 0)

    # Table
    display_cols = [
        "priority_score", "apn", "verified_current_owner_name", "ownership_class",
        "v_total_balance", "situs_address", "mailing_address", "out_of_state",
        "fire_hazard_zone", "flood_zone", "portfolio_apn_count", "distress_signal_score",
        "distress_signals", "recorder_doc_numbers",
    ]
    display_cols = [c for c in display_cols if c in filtered.columns]
    st.dataframe(filtered[display_cols], use_container_width=True, height=600)

    # Row detail expander
    if len(filtered):
        st.divider()
        st.subheader("Lead detail")
        selected_apn = st.selectbox(
            "Select an APN for full profile",
            options=filtered["apn"].tolist(),
            index=0,
        )
        row = filtered[filtered["apn"] == selected_apn].iloc[0]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"### {row.get('verified_current_owner_name', '(no name)')}")
            st.markdown(f"**APN:** {row.get('apn')}")
            st.markdown(f"**Priority:** {row.get('priority_score')} / 100")
            st.markdown(f"**Balance:** {row.get('v_total_balance')}")
            st.markdown(f"**Ownership type:** {row.get('ownership_class', '?')}")
            st.markdown(f"**Ownership confidence:** {row.get('ownership_confidence', '?')}")
            st.markdown(f"**Situs:** {row.get('situs_address', '-')}")
            st.markdown(f"**Mailing:** {row.get('mailing_address', '-')}")
            st.markdown(f"**Absentee:** {row.get('out_of_state', 'N')} ({row.get('owner_state', '?')})")
        with c2:
            st.markdown("**Environmental**")
            st.markdown(f"- Fire hazard: {row.get('fire_hazard_zone', 'unmapped')} ({row.get('fire_responsibility_area', '')})")
            st.markdown(f"- Flood zone: {row.get('flood_zone', 'unmapped')}")
            st.markdown("**Portfolio**")
            st.markdown(f"- Parcels held: {row.get('portfolio_apn_count', 1)}")
            st.markdown(f"- Portfolio $: ${row.get('portfolio_apn_balance', 0)}")
            sibs = row.get("portfolio_sibling_apns", "")
            if sibs and str(sibs).strip():
                st.markdown(f"- Siblings: {sibs.replace('|', ', ')}")
            st.markdown("**Distress**")
            st.markdown(f"- Score: {row.get('distress_signal_score', 0)}")
            st.markdown(f"- Signals: {row.get('distress_signals', '-')}")
            st.markdown(f"- Partners: {row.get('business_partners', '-').replace('|', ', ')}")
            st.markdown("**Recorder**")
            st.markdown(f"- Doc #: {row.get('recorder_doc_numbers', '-')}")
            st.markdown(f"- Type: {row.get('recorder_doc_types', '-')}")
            st.markdown(f"- Recorded: {row.get('recorder_doc_dates', '-')}")

        st.divider()
        # Regenerate bundle button
        if st.button("Regenerate delivery bundle for Butte"):
            import subprocess
            with st.spinner("Building XLSX + PDF + 105 dossiers..."):
                res = subprocess.run(
                    ["python", str(REPO_ROOT / "butte" / "package_delivery.py")],
                    capture_output=True, text=True, timeout=300,
                )
                if res.returncode == 0:
                    st.success("Bundle rebuilt. See butte/delivery/")
                    st.text(res.stdout[-1500:])
                else:
                    st.error(res.stderr[-1500:])


# ── Page: Surplus Recovery ─────────────────────────────────────────────

elif page == "Surplus Recovery":
    st.title("Surplus Recovery")
    df = load_surplus()
    if df.empty:
        st.warning("No surplus opportunities ingested. Run: `python -m surplus.ingest`")
        st.stop()

    st.sidebar.markdown("### Filters")
    show_expired = st.sidebar.checkbox("Show expired claims")
    min_surplus = st.sidebar.number_input("Min surplus amount", value=5000, step=500)
    county_filter = st.sidebar.multiselect(
        "County", options=sorted(df["county"].dropna().unique().tolist()), default=[],
    )
    status_filter = st.sidebar.multiselect(
        "Status", options=sorted(df["status"].dropna().unique().tolist()), default=[],
    )

    mask = df["surplus_amount"] >= min_surplus
    if not show_expired:
        mask &= df["days_left"] > 0
    if county_filter:
        mask &= df["county"].isin(county_filter)
    if status_filter:
        mask &= df["status"].isin(status_filter)

    filtered = df[mask]

    st.write(f"**{len(filtered)}** of {len(df)} claims match your filters")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total surplus", _fmt_money(filtered["surplus_amount"].sum()))
    c2.metric("Expected @ 10%", _fmt_money(filtered["surplus_amount"].sum() * 0.10))
    c3.metric("Urgent (<60 days)", int((filtered["days_left"] < 60).sum()) if len(filtered) else 0)
    c4.metric("Deceased flagged", int((filtered.get("trace_deceased", 0) == 1).sum()) if len(filtered) else 0)

    # Table
    show = filtered.copy()
    if "days_left" in show.columns:
        show["urgency"] = show["days_left"].apply(_urgency_emoji)
    display_cols = ["urgency", "county", "apn", "former_owner_raw",
                    "surplus_amount", "days_left", "claim_deadline_at",
                    "status", "trace_current_address", "trace_provider"]
    display_cols = [c for c in display_cols if c in show.columns]
    st.dataframe(show[display_cols], use_container_width=True, height=500)

    # Row actions
    st.divider()
    st.subheader("Update lead status")
    if len(filtered):
        sel_id = st.selectbox(
            "Select opportunity (id : owner)",
            options=filtered["id"].tolist(),
            format_func=lambda i: f"{i} : {filtered[filtered['id']==i]['former_owner_raw'].iloc[0]} (${filtered[filtered['id']==i]['surplus_amount'].iloc[0]:,.0f})",
        )
        row = filtered[filtered["id"] == sel_id].iloc[0]
        current_status = row["status"]
        st.write(f"Current status: **{current_status}**")

        new_status = st.selectbox(
            "New status",
            options=["open", "traced", "traced_no_hit", "mailed", "signed",
                     "filed", "paid", "expired", "disqualified"],
            index=["open", "traced", "traced_no_hit", "mailed", "signed",
                   "filed", "paid", "expired", "disqualified"].index(current_status)
                   if current_status in ["open", "traced", "traced_no_hit", "mailed",
                                          "signed", "filed", "paid", "expired", "disqualified"]
                   else 0,
        )
        notes = st.text_input("Notes for the log", value="")
        if st.button("Update", type="primary"):
            update_surplus_status(int(sel_id), new_status, notes)
            st.success(f"Updated #{sel_id} -> {new_status}")
            st.rerun()


# ── Page: Outreach Pipeline ────────────────────────────────────────────

elif page == "Outreach Pipeline":
    st.title("Outreach Pipeline")
    surplus = load_surplus()
    events = load_outreach_events()

    if surplus.empty:
        st.warning("No surplus opportunities to track outreach on yet.")
        st.stop()

    # Kanban-style status buckets
    st.subheader("Pipeline by status")
    statuses = ["open", "traced", "mailed", "signed", "filed", "paid"]
    cols = st.columns(len(statuses))
    for col, status in zip(cols, statuses):
        subset = surplus[surplus["status"] == status]
        with col:
            st.metric(status.upper(), len(subset))
            st.metric("$ surplus", _fmt_money(subset["surplus_amount"].sum()))
            st.metric("$ our fee @ 10%", _fmt_money(subset["surplus_amount"].sum() * 0.10))

    st.divider()
    st.subheader("Recent outreach events")
    if events.empty:
        st.info("No outreach events logged yet. Update a lead status on the Surplus Recovery page to log one.")
    else:
        st.dataframe(events.head(50), use_container_width=True)


# ── Page: Graph Explorer ───────────────────────────────────────────────

elif page == "Graph Explorer":
    st.title("Recorder Graph Explorer")
    stats = load_graph_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Docs", f"{stats.get('docs', 0):,}")
    c2.metric("Persons", f"{stats.get('persons', 0):,}")
    c3.metric("Entities", f"{stats.get('entities', 0):,}")
    c4.metric("Parcels", f"{stats.get('parcels', 0):,}")
    c5.metric("Edges", f"{stats.get('edges', 0):,}")

    st.divider()
    st.subheader("Lookup a person or entity")
    name = st.text_input("Canonical name (uppercase, no punctuation)", value="ABADIR PERRY")
    if name:
        docs = graph_query_by_owner(name.strip().upper())
        if docs.empty:
            st.info(f"No documents in graph for {name!r}. Try common Butte owners: ABADIR PERRY, GRIDLEY BUSINESS TRUST, DEWSNUP KYLE, MORRIS RONALD, BIRTWELL LESLIE")
        else:
            st.write(f"**{len(docs)}** documents involving this name")
            st.dataframe(docs, use_container_width=True, height=400)


# ── Page: Financial ────────────────────────────────────────────────────

elif page == "Financial":
    st.title("Financial")
    ledger = load_skip_trace_ledger()
    surplus = load_surplus()
    events = load_outreach_events()

    st.subheader("Skip trace spend")
    if ledger.empty:
        st.info("No skip trace activity yet.")
    else:
        total_cents = ledger["cost_cents"].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total spend", f"${total_cents/100:.2f}")
        c2.metric("Total lookups", len(ledger))
        c3.metric("Hit rate", f"{ledger['hit'].mean()*100:.0f}%" if len(ledger) else "0%")
        st.dataframe(ledger.head(50), use_container_width=True)

    st.divider()
    st.subheader("Revenue pipeline (surplus recovery @ 10%)")
    if surplus.empty:
        st.info("No surplus opportunities ingested.")
    else:
        # Projection: assume 20% signup conversion, 90% claim success
        open_now = surplus[surplus["days_left"] > 0]
        total_surplus = open_now["surplus_amount"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Open claims $", _fmt_money(total_surplus))
        c2.metric("Fees if all convert @ 10%", _fmt_money(total_surplus * 0.10))
        c3.metric("Expected @ 20% conversion", _fmt_money(total_surplus * 0.10 * 0.20))
        c4.metric("Expected @ 40% conversion", _fmt_money(total_surplus * 0.10 * 0.40))

        st.subheader("By status")
        by_status = surplus.groupby("status").agg(
            count=("id", "count"),
            surplus_total=("surplus_amount", "sum"),
        ).reset_index()
        by_status["fee_at_10pct"] = by_status["surplus_total"] * 0.10
        st.dataframe(by_status, use_container_width=True)
