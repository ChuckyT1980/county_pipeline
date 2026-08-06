import pandas as pd
import json

data = [{
    'parcel_number': '123-456-789-000',
    'county': 'shasta',
    'v_total_balance': '$12,500.00',
    'v_delinquent': True,
    'owner_vesting': json.dumps({
        'primary_name': 'SMITH JOHN AND JANE',
        'entity_type': 'INDIVIDUAL',
        'vesting_doc_type': 'GRANT DEED',
        'acquisition_date': '2015-06-01',
        'ownership_verification_status': 'MATCHES_ASSESSOR',
        'verified_current_owner_name': 'SMITH JOHN AND JANE'
    }),
    'chain_of_title': json.dumps([
        {'doc_type': 'DEED OF TRUST', 'role': 'DEBT', 'recorded_date': '2015-06-05'},
        {'doc_type': 'NOTICE OF DEFAULT', 'role': 'DEFAULT', 'recorded_date': '2025-01-10'}
    ])
}]

df = pd.DataFrame(data)
df.to_csv('shasta/shasta_test_stage3.csv', index=False)
print('Mocked distressed record saved to shasta/shasta_test_stage3.csv')
