import pandas as pd
df = pd.read_csv('butte_auction_105_ENRICHED.csv', dtype=str)
# Convert default_year to numeric for bucketing
df['default_year'] = pd.to_numeric(df['default_year'], errors='coerce')
# has_doc is True if v_document_number is not null/empty
df['has_doc'] = df['v_document_number'].fillna('').str.strip() != ''

# group by decade or 5-year buckets
bins = [1980, 1990, 2000, 2010, 2015, 2020, 2026]
df['year_bucket'] = pd.cut(df['default_year'], bins=bins, right=False)

summary = df.groupby('year_bucket', observed=False)['has_doc'].agg(['count', 'mean'])
summary['missing_pct'] = (1 - summary['mean']) * 100
summary['has_doc_pct'] = summary['mean'] * 100

print("--- Document Number Coverage by Default Year ---")
print(summary[['count', 'missing_pct', 'has_doc_pct']].round(1))
