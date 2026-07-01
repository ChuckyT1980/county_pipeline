import re
from typing import List, Tuple
from source_provider import SourceProvider
from ala1 import APNLossAuditor

class APNDiscoverer:
    def __init__(self, provider: SourceProvider):
        self.provider = provider
        
    def discover(self, county: str, state: str) -> dict:
        """
        Returns full audit report dictionary.
        """
        query = f"{county} county {state} delinquent tax list"
        results = self.provider.search(query)
        
        auditor = APNLossAuditor()
        
        pattern = re.compile(r'\b[\d]{3}[-\s]?[\d]{3}[-\s]?[\d]{3,4}(?:[-\s]?[\d]{3,4})?\b')
        
        candidates_seen = set()
        
        for r in results:
            text = r.title + " " + r.snippet + " " + r.body_text
            
            # Find raw candidates
            matches = pattern.findall(text)
            
            for m in matches:
                # Deduplicate before auditing to avoid duplicate logs
                clean_str = m.strip()
                if clean_str not in candidates_seen:
                    candidates_seen.add(clean_str)
                    auditor.audit_candidate(clean_str)
                    
        # In a real scenario, we might also look for generic digit clumps if we want to be more aggressive,
        # but the pattern above is a decent filter. To truly test loss auditor, let's also grab
        # strings matching 'APN:\s*\w+' or 'Parcel:\s*\w+'
        alt_pattern = re.compile(r'(?:APN|Parcel):?\s*([a-zA-Z0-9-]{6,16})', re.IGNORECASE)
        for r in results:
            text = r.title + " " + r.snippet + " " + r.body_text
            matches = alt_pattern.findall(text)
            for m in matches:
                clean_str = m.strip()
                if clean_str not in candidates_seen:
                    candidates_seen.add(clean_str)
                    auditor.audit_candidate(clean_str)
                    
        return auditor.get_audit_report()
