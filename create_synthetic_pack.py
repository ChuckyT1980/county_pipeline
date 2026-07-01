import os

apns = [
    "057-120-045-000",
    "068-110-004-000",
    "005-090-096-000",
    "041-330-018-000",
    "012-004-771-000"
]

data = [
    {
        "apn": apns[0],
        "assessor": """<div class="field">Owner Name:</div>
<div class="value">SMITH FAMILY TRUST</div>
<div class="field">Owner:</div>
<div class="value">JOHN SMITH</div>
<div class="field">Situs Address:</div>
<div class="value">456 RURAL RD</div>""",
        "tax": """<div class="label">Taxes Due</div>
<div class="value">$8,421.22</div>""",
        "parcel": """<table>
<tr><td>Land Use Code</td><td>SFR</td></tr>
<tr><td>Acreage</td><td>1.25</td></tr>
</table>"""
    },
    {
        "apn": apns[1],
        "assessor": """<div>Registered Owner: JOHNSON HOLDINGS LLC</div>
<div>Property Location</div>
<div>321 SHASTA LAKE RD</div>""",
        "tax": """<div>Delinquent Amount:</div>
<div>$1,200</div>""",
        "parcel": """<span>Use:</span> VACANT LAND
<span>Size (acres):</span> 5.0"""
    },
    {
        "apn": apns[2],
        "assessor": """<div class="field">Owner Name:</div>
<div class="value">EST OF WILLIAMS, ROBERT</div>""",
        "tax": """<!-- MISSING ENTIRELY -->""",
        "parcel": """<div>Land Use: SFR</div>
<div>Acreage: 0.8</div>"""
    },
    {
        "apn": apns[3],
        "assessor": """<div class="row"><span>Owner</span><span>LEE PROPERTY TRUST</span></div>
<div class="row"><span>Owner Name</span><span>LEE FAMILY TRUST</span></div>""",
        "tax": """<div>Taxes Due</div>
<div>$12,904.50</div>""",
        "parcel": """<div>Acreage</div>
<div>1,250 acres</div>"""
    },
    {
        "apn": apns[4],
        "assessor": """<div>Owner: UNKNOWN</div>""",
        "tax": """<div>Amount Due:</div>
<div>N/A</div>""",
        "parcel": """<!-- EMPTY PAGE -->"""
    }
]

def build():
    out_dir = "data/raw/synthetic_shasta"
    os.makedirs(out_dir, exist_ok=True)
    
    for item in data:
        apn = item["apn"]
        for src in ["assessor", "tax", "parcel"]:
            with open(f"{out_dir}/{apn}_{src}.html", "w") as f:
                f.write(item[src])

if __name__ == "__main__":
    build()
