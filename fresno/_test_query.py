import sys
sys.path.insert(0, '.')
from query import main

# LLC owners with value over 500k (top of the roll by value)
main(['--county', 'fresno',
      '--where', 'owner LIKE \'%LLC%\' AND cast("values" as integer) > 500000',
      '--limit', '8'])
print()
# parcels with a tax deed flagged (only the 4 test APNs right now)
main(['--county', 'fresno', '--where', 'tax_deed=\'yes\'', '--limit', '8'])
