"""Count Tehama parcels with recorder-indexable doc numbers but no owner."""
import sqlite3

con = sqlite3.connect(r"C:\Users\chuck\Downloads\county_pipeline\data\counties\tehama\state.sqlite")
total_docs = con.execute("SELECT COUNT(*) FROM parcels WHERE current_doc_number IS NOT NULL AND current_doc_number != ''").fetchone()[0]
r_docs = con.execute("SELECT COUNT(*) FROM parcels WHERE current_doc_number LIKE '%R%'").fetchone()[0]
r_docs_no_owner = con.execute(
    "SELECT COUNT(*) FROM parcels WHERE current_doc_number LIKE '%R%' "
    "AND (owner IS NULL OR owner = '')"
).fetchone()[0]
r_modern = con.execute(
    "SELECT COUNT(*) FROM parcels WHERE current_doc_number LIKE '20%%R%' "
    "AND (owner IS NULL OR owner = '')"
).fetchone()[0]
r_pre2004 = con.execute(
    "SELECT COUNT(*) FROM parcels WHERE current_doc_number LIKE '200%%R%' "
    "AND (owner IS NULL OR owner = '')"
).fetchone()[0]
r_2004plus = con.execute(
    "SELECT COUNT(*) FROM parcels WHERE current_doc_number LIKE '2004R%' OR current_doc_number LIKE '2005R%' "
    "OR current_doc_number LIKE '2006R%' OR current_doc_number LIKE '2007R%' OR current_doc_number LIKE '2008R%' "
    "OR current_doc_number LIKE '2009R%' OR current_doc_number LIKE '201%R%' OR current_doc_number LIKE '202%R%' "
    "AND (owner IS NULL OR owner = '')"
).fetchone()[0]
print(f"total docs: {total_docs:,}")
print(f"R-form docs: {r_docs:,}")
print(f"R-form no owner: {r_docs_no_owner:,}")
print(f"  2000-2003 (legacy, not indexed): {r_pre2004:,}")
print(f"  2004+ (modern): {r_2004plus:,}")
