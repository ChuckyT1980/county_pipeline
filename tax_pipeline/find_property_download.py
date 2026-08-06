import re

with open('bid4assets_butte_aug2026.html', encoding='utf-8') as f:
    html = f.read()

idx = html.find('propertyListDownloadWindow')
if idx >= 0:
    print(html[idx:idx+1000])
else:
    print('Function not in page')
    for m in re.finditer(r'<script[^>]*src=[\'"]([^\'"]*(?:storefront|auction)[^\'"]*)[\'"]', html, re.I):
        print('JS:', m.group(1))
