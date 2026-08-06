#!/usr/bin/env python3
"""
Parse Tehma distressed property PDF reports and generate an HTML page
with clickable assessor portal links for each lead.
"""
import pdfplumber
import re
import os

def parse_lead_block(text):
    lines = text.strip().split('\n')
    lead = {}
    
    for line in lines:
        l = line.strip()
        if 'Parcel/APN:' in l:
            m = re.search(r'([\d]{3}-[\d]{3}-[\d]{3}-[\d]{3})', l)
            if m:
                lead['apn'] = m.group(1)
        if 'First Name:' in l:
            lead['first_name'] = l.split('First Name:')[1].split('Parcel')[0].strip()
        if 'Last Name:' in l:
            lead['last_name'] = l.split('Last Name:')[1].split('Property')[0].strip()
        if 'Property Address:' in l:
            lead['property_address'] = l.split('Property Address:')[1].strip()
        if 'Mailing Address:' in l:
            lead['mailing_address'] = l.split('Mailing Address:')[1].split('Intent Score')[0].strip()
        if 'Intent Score:' in l:
            m = re.search(r'Intent Score:\s*([\d.]+)', l)
            if m:
                lead['intent_score'] = float(m.group(1))
        if 'Distress Signals:' in l:
            lead['distress_signals'] = l.split('Distress Signals:')[1].strip()
    
    return lead

def extract_leads_from_pdf(path):
    leads = []
    with pdfplumber.open(path) as pdf:
        full_text = ''
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full_text += t + '\n'
    
    blocks = re.split(r'(?=Lead #\d+:)', full_text)
    for block in blocks:
        if not block.strip():
            continue
        lead = parse_lead_block(block)
        if lead.get('apn'):
            leads.append(lead)
    return leads

def build_assessor_url(apn):
    compact = re.sub(r'\D', '', apn)
    if len(compact) != 12:
        return None
    return f"https://common1.mptsweb.com/MBC/tehama/tax/main/{compact}/2025/0000"

def render_html(all_leads):
    rows_html = ''
    for i, lead in enumerate(all_leads):
        apn = lead.get('apn', '')
        assessor_url = build_assessor_url(apn) or '#'
        name = f"{lead.get('last_name', '')}, {lead.get('first_name', '')}".strip(', ')
        address = lead.get('property_address', '')
        score = lead.get('intent_score', 0)
        signals = lead.get('distress_signals', '')
        
        star_count = 1 if score >= 5 else 1 if score > 0 else 0
        star_label = 'HOT LEAD' if score >= 10 else 'ACCELERATED' if score >= 4 else 'LEAD'
        
        rows_html += f'''
        <tr>
            <td class="font-bold {"text-emerald-400" if score >= 10 else "text-amber-400"}">{"⭐" * min(int(score/3)+1, 5)} {star_label}</td>
            <td class="font-bold">{name}</td>
            <td><a href="{assessor_url}" target="_blank" class="assessor-link">{apn}</a></td>
            <td>{address}</td>
            <td class="font-mono text-emerald-400 font-bold">{score}</td>
            <td class="text-xs text-slate-400">{signals[:60]}{"..." if len(signals) > 60 else ""}</td>
        </tr>'''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Tehama Distressed Property Intelligence</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
    <style>
        body {{ background-color: #0f172a; color: #e2e8f0; font-family: 'Inter', sans-serif; }}
        .dataTables_wrapper .dataTables_length, .dataTables_wrapper .dataTables_filter,
        .dataTables_wrapper .dataTables_info, .dataTables_wrapper .dataTables_processing,
        .dataTables_wrapper .dataTables_paginate {{ color: #e2e8f0; }}
        table.dataTable tbody tr {{ background-color: #1e293b; }}
        table.dataTable tbody tr:hover {{ background-color: #334155; }}
        table.dataTable thead th, table.dataTable thead td {{ border-bottom: 1px solid #475569; }}
        table.dataTable.no-footer {{ border-bottom: 1px solid #475569; }}
        .assessor-link {{ color: #60a5fa; text-decoration: underline; font-weight: 600; }}
        .assessor-link:hover {{ color: #93c5fd; text-shadow: 0 0 8px rgba(96,165,250,0.5); }}
    </style>
</head>
<body class="p-8">
    <div class="max-w-7xl mx-auto">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-3xl font-bold text-white tracking-wider">TEHAMA DISTRESSED PROPERTY INTELLIGENCE</h1>
            <div class="text-emerald-400 font-semibold border border-emerald-400 px-4 py-2 rounded shadow-[0_0_15px_rgba(52,211,153,0.3)]">
                {len(all_leads)} Total Leads
            </div>
        </div>
        
        <div class="bg-slate-800 rounded-xl shadow-2xl p-8 border border-slate-700">
            <table id="leadTable" class="display w-full text-sm">
                <thead>
                    <tr>
                        <th class="text-left text-slate-300">Priority</th>
                        <th class="text-left text-slate-300">Owner Name</th>
                        <th class="text-left text-slate-300">APN</th>
                        <th class="text-left text-slate-300">Property Address</th>
                        <th class="text-left text-slate-300">Intent Score</th>
                        <th class="text-left text-slate-300">Distress Signals</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        
        <div class="mt-8 bg-slate-800 rounded-xl shadow-2xl p-6 border border-slate-700">
            <h2 class="text-xl font-bold text-white mb-4">How to Use</h2>
            <p class="text-slate-300">Click any <span class="text-blue-400 underline">APN number</span> to open the <strong>Tehama County Assessor Portal</strong> for that property directly. You will see the full tax assessment, property characteristics, and owner information.</p>
        </div>
    </div>
    <script>
        $(document).ready(function() {{
            $('#leadTable').DataTable({{
                "order": [[ 4, "desc" ]],
                "pageLength": 50,
                "language": {{ "search": "Search Leads:" }}
            }});
        }});
    </script>
</body>
</html>'''
    return html

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    pdfs = [
        'Tehama_Top_5_Distressed_Property_Intelligence_Report.pdf',
        'Tehama_35_Distressed_Property_Intelligence_Report.pdf',
    ]
    
    all_leads = []
    for pdf_name in pdfs:
        path = os.path.join(base_dir, pdf_name)
        if os.path.exists(path):
            leads = extract_leads_from_pdf(path)
            print(f'{pdf_name}: {len(leads)} leads extracted')
            all_leads.extend(leads)
        else:
            print(f'NOT FOUND: {path}')
    
    print(f'Total: {len(all_leads)} leads')
    
    if all_leads:
        html = render_html(all_leads)
        out_path = os.path.join(base_dir, 'tehama_distressed_leads_with_links.html')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Wrote {out_path}')
        
        # Also verify what we parsed
        for lead in all_leads:
            apn = lead.get('apn', 'NO APN')
            url = build_assessor_url(apn)
            name = f"{lead.get('last_name', '')}, {lead.get('first_name', '')}"
            print(f'  {apn} -> {url} | {name}')
