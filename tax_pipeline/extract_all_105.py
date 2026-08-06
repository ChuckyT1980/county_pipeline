import pdfplumber, re

"""
Re-extract ALL 105 auction parcels from the Butte County reoffer PDF.
Handle multi-line entries and combined APNs properly.
"""

parcels = []
current_apn = None
current_owner = ""
current_address = ""

with pdfplumber.open('reoffer_aug2026.pdf') as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Check if line starts with an APN
            m_apn = re.match(r'(\d{3}-\d{3}-\d{3}-\d{3})(?:\s*/\s*(\d{3}-\d{3}-\d{3}-\d{3}))?', line)
            if m_apn:
                # Save previous parcel if exists
                if current_apn:
                    parcels.append({
                        'apn': current_apn,
                        'owner': current_owner.strip().rstrip('$').strip(),
                        'address': current_address.strip().rstrip('$').strip(),
                    })
                current_apn = m_apn.group(1)
                # Handle combined APNs like 071-270-029-000/990-322-648-000
                combined = m_apn.group(2)
                if combined:
                    current_apn = current_apn + '/' + combined
                
                # Rest of line after APN
                rest = line[m_apn.end():].strip()
                
                # Try to parse owner and address from rest
                # Format: OWNER ADDRESS $ AMOUNT
                bid_m = re.search(r'\$[\d,]+', rest)
                if bid_m:
                    before_bid = rest[:bid_m.start()].strip().rstrip('$').strip()
                    bid_str = bid_m.group()
                    current_owner = before_bid
                    current_address = ''
                else:
                    current_owner = rest
                    current_address = ''
            else:
                # Continuation line (multi-line owner name or address)
                # Check if it has a bid amount at the end
                bid_m = re.search(r'\$[\d,]+', line)
                if bid_m:
                    before_bid = line[:bid_m.start()].strip().rstrip('$').strip()
                    current_owner = (current_owner + ' ' + before_bid).strip()
                else:
                    current_owner = (current_owner + ' ' + line).strip()

# Don't forget the last one
if current_apn:
    parcels.append({
        'apn': current_apn,
        'owner': current_owner.strip().rstrip('$').strip(),
        'address': current_address.strip().rstrip('$').strip(),
    })

print("Total parcels extracted: %d" % len(parcels))
print()
for p in parcels:
    print("%-30s | %s" % (p['apn'], p['owner'][:60]))
