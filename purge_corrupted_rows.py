import pandas as pd
import json

file_path = 'tehama/tehama_15_percent_sample_VERIFIED_ENRICHED_partial.parquet'
df = pd.read_parquet(file_path)
initial_len = len(df)

def is_corrupted(row):
    doc_fmt = str(row.get('v_document_number'))
    recorder_chain = row.get('recorder_chain')
    if doc_fmt and doc_fmt != 'nan' and doc_fmt != 'None' and recorder_chain:
        try:
            chain = json.loads(recorder_chain)
            if chain:
                for event in chain:
                    if str(event.get('doc_number')) != doc_fmt:
                        return True
        except:
            pass
    return False

mask = df.apply(is_corrupted, axis=1)
corrupted_count = mask.sum()

df_clean = df[~mask]
df_clean.to_parquet(file_path, index=False)

print(f"Original rows: {initial_len}")
print(f"Corrupted rows dropped: {corrupted_count}")
print(f"Remaining rows: {len(df_clean)}")
