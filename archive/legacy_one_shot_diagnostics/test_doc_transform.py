from tyler_recorder_client import apply_doc_transform

cases = [
    ('2024R0030607', '2024-0030607'),
    ('2024R0016848', '2024-0016848'),
    ('2018R0038646', '2018-0038646'),
    ('1998R45023',   '1998-45023'),
    ('2021-0012345', '2021-0012345'),
]
all_pass = True
for raw, expected in cases:
    got = apply_doc_transform(raw, 'r_to_hyphen')
    ok = got == expected
    if not ok:
        all_pass = False
    status = "OK" if ok else "FAIL"
    print(f"  {raw:<20s} -> {got:<20s}  expected={expected:<20s}  {status}")

print()
print("All pass:", all_pass)
