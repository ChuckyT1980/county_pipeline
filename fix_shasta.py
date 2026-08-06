import sys
import os
import re

with open('tax_pipeline/stage2_recorder_enrich.py', 'r', encoding='utf-8') as f:
    content = f.read()

# I need to restore format_doc_number.
# Currently it looks like:
"""
def format_doc_number(doc_str, county="shasta"):
    if not doc_str or pd.isna(doc_str): return None
    doc_str = str(doc_str).strip()
    
from shasta_recorder_api import ShastaRecorderClient

def run_stage2_shasta_http(input_csv, county):
"""
# And at the end of run_stage2_shasta_http, I have:
"""
    print(f"Saved final to {out_csv}")
    if county.lower() == "tehama":
        return doc_str.replace('R', '') if isinstance(doc_str, str) else doc_str
    if county.lower() == "shasta":
        if 'R' in doc_str:
            return doc_str.replace('R', '-')
        if '-' not in doc_str and len(doc_str) >= 11:
            return doc_str[:4] + '-' + doc_str[4:]
    return doc_str
"""

# Let's just pull out the code for run_stage2_shasta_http, fix format_doc_number, and put it all back properly!
match = re.search(r'def format_doc_number\(doc_str, county="shasta"\):.*?doc_str = str\(doc_str\)\.strip\(\)', content, flags=re.DOTALL)
if match:
    proper_format_doc_number = '''def format_doc_number(doc_str, county="shasta"):
    if not doc_str or pd.isna(doc_str): return None
    doc_str = str(doc_str).strip()
    if county.lower() == "tehama":
        return doc_str.replace('R', '') if isinstance(doc_str, str) else doc_str
    if county.lower() == "shasta":
        if 'R' in doc_str:
            return doc_str.replace('R', '-')
        if '-' not in doc_str and len(doc_str) >= 11:
            return doc_str[:4] + '-' + doc_str[4:]
    return doc_str
'''
    content = re.sub(r'def format_doc_number\(doc_str, county="shasta"\):.*?return doc_str\n', proper_format_doc_number, content, flags=re.DOTALL)
    
    # We need to extract the shasta_http block if it was swallowed
    shasta_match = re.search(r'(from shasta_recorder_api import ShastaRecorderClient\n\ndef run_stage2_shasta_http\(input_csv, county\):.*?print\(f"Saved final to \{out_csv\}"\)\n)', content, flags=re.DOTALL)
    if shasta_match:
        shasta_code = shasta_match.group(1)
        # Remove it from where it might be (it's already removed by the above sub if it was swallowed, wait no it wasn't because the sub above replaced up to return doc_str\n which was at the very end of the file or something.
        
with open('tax_pipeline/stage2_recorder_enrich.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Check if format_doc_number is restored properly!")
