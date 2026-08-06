from bs4 import BeautifulSoup
import re

with open("tehama_results.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

print("Checking classes...")
# Look for something that contains "2018007697"
for el in soup.find_all():
    if el.string and "2018007697" in el.string:
        print(f"Found exactly in: {el.name} class={el.get('class')} id={el.get('id')}")
        
    text = el.get_text(separator=' ', strip=True)
    if text.startswith("D 2018007697") or "2018007697" in text:
        if el.name in ['li', 'div', 'tr', 'ul']:
            # We want container elements
            classes = el.get('class', [])
            if classes:
                print(f"Container {el.name} class={classes}")

# Dump all li classes
print("\nAll li classes in document:")
classes_seen = set()
for li in soup.find_all('li'):
    cls = tuple(li.get('class', []))
    if cls and cls not in classes_seen:
        classes_seen.add(cls)
        print(cls)
