import glob, os, json, re
from bs4 import BeautifulSoup

captured_files = glob.glob(r'C:\Users\chuck\Downloads\county_pipeline\kern\govease_captured_*.json')

for fpath in captured_files:
    fname = os.path.basename(fpath)
    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if any(term in content for term in ['005-222-10', 'Bakersfield', 'HUGGINS', 'Parcel', 'APN', 'AuctionID', '1348']):
            if '<html' in content.lower():
                soup = BeautifulSoup(content, 'html.parser')
                title = soup.title.string.strip() if soup.title and soup.title.string else 'No title'
                tables = soup.find_all('table')
                print(f'{fname}: HTML, title="{title}", tables={len(tables)}')
            else:
                print(f'{fname}: Non-HTML text (len={len(content)})')
