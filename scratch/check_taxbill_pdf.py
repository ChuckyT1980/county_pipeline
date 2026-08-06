import requests
import io
import pdfplumber

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
})

url = 'https://apps.mptsweb.com/TaxBillv2/Default.aspx?County=shasta&Asmt=070050072000&TaxYear=2025&RollCat=SS&RollType=S'
resp = session.get(url, timeout=15)
print('Status:', resp.status_code)
print('Content-Type:', resp.headers.get('Content-Type'))
print('Size:', len(resp.content))

# The PDF starts with %PDF
content = resp.content
if content.startswith(b'%PDF'):
    print('It IS a PDF!')
    # Extract text from PDF
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            print('\n=== Page %d ===' % (i+1))
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for l in lines:
                if any(k in l.upper() for k in ['OWNER', 'ASSESSEE', 'NAME', 'MAIL', 'SITUS', 'TAXPAYER', 'KERRYJEN']):
                    print('  FOUND:', l)
            # Print full text
            for l in lines[:50]:
                print('  ' + l)
else:
    print('Not a PDF, first 500 bytes:')
    print(content[:500])
