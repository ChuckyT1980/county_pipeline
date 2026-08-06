import re

_APN_DASH_RE = re.compile(r"(\d{3,4})-?(\d{3,4})-?(\d{3,4})-?(\d{3})$")


def normalize_apn(raw: str) -> str:
    raw = raw.strip().upper()
    m = _APN_DASH_RE.match(raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}"
    digit_only = re.sub(r"[^0-9]", "", raw)
    if len(digit_only) == 13:
        return f"{digit_only[:3]}-{digit_only[3:6]}-{digit_only[6:9]}-{digit_only[9:]}"
    if len(digit_only) == 15:
        return f"{digit_only[:4]}-{digit_only[4:7]}-{digit_only[7:10]}-{digit_only[10:]}"
    if len(digit_only) == 9:
        return f"{digit_only[:3]}-{digit_only[3:6]}-{digit_only[6:]}"
    return digit_only  # fallback


def apn_sort_key(apn: str) -> tuple:
    parts = apn.replace("-", "").split("-")
    digits = re.sub(r"[^0-9]", "", apn)
    return (len(digits), digits.zfill(20))
