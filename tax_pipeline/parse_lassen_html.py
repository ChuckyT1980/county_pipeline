from bs4 import BeautifulSoup

with open("lassen_step1.html", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

print("=== INPUT FIELDS ===")
for inp in soup.find_all("input"):
    attrs = {k: v for k, v in inp.attrs.items() if k in ["id", "name", "type", "value", "placeholder"]}
    print(attrs)

print("\n=== SELECT MENUS ===")
for sel in soup.find_all("select"):
    attrs = {k: v for k, v in sel.attrs.items() if k in ["id", "name"]}
    print(attrs)

print("\n=== BUTTONS ===")
for btn in soup.find_all(["button", "input"]):
    if btn.name == "button" or btn.get("type") in ["submit", "button"]:
        attrs = {k: v for k, v in btn.attrs.items() if k in ["id", "name", "type", "value", "onclick"]}
        print(attrs)
