from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class SourceResult:
    title: str
    url: str
    snippet: str
    body_text: str = "" # Used for adversarial APN discovery

class SourceProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> List[SourceResult]:
        pass

class MockSourceProvider(SourceProvider):
    def __init__(self):
        # We simulate what a real search engine would return for queries
        self.mock_index = {
            "shasta county ca property tax": [
                SourceResult(
                    title="Shasta County Property Tax Search",
                    url="https://mptsweb.co.shasta.ca.us/search.asp",
                    snippet="Search and pay your Shasta County property taxes online."
                ),
                SourceResult(
                    title="Shasta County Assessor",
                    url="https://www.co.shasta.ca.us/assessor",
                    snippet="Official page for the Shasta County Assessor."
                )
            ],
            # Adversarial Delinquent Tax List Query
            "shasta county delinquent tax list": [
                SourceResult(
                    title="Shasta County Tax Sale - Public Auction",
                    url="https://www.co.shasta.ca.us/docs/tax_sale.pdf",
                    snippet="Tax Defaulted Property: 057-120-045-000, APN:068110004000. Parcel: 005-090-096",
                    body_text="""
                    Here is the list of properties:
                    057-120-045-000 (Valid format)
                    057120045000 (Duplicate, no dashes)
                    068-110-004-000 (Valid format)
                    068-110-04-000 (Malformed short segment)
                    APN:041330018000 (No spaces, no dashes)
                    Assessor Parcel No. 012-004-771 (Missing suffix)
                    Random numbers 123456 that are not APNs.
                    123-456-789-000 (Another valid APN)
                    """
                ),
                SourceResult(
                    title="Empty Notice",
                    url="https://www.co.shasta.ca.us/docs/notice.pdf",
                    snippet="There are no properties available at this time.",
                    body_text="No properties."
                )
            ],
            "tehama county ca property tax": [
                SourceResult(
                    title="Tehama County Property Tax",
                    url="https://mptsweb.co.tehama.ca.us/taxsearch",
                    snippet="View Tehama County taxes via Megabyte Systems."
                )
            ],
            "fake_aumentum county ca property tax": [
                SourceResult(
                    title="Property Tax Portal",
                    url="https://taxes.fakeaumentum.ca.us/Aumentum/search",
                    snippet="Powered by Aumentum Technologies."
                )
            ],
            "fake_govos county ca property tax": [
                SourceResult(
                    title="GovOS Property Search",
                    url="https://search.fakegovos.ca.us/records",
                    snippet="Official Kofile / GovOS records search for the county."
                )
            ]
        }
        
    def search(self, query: str) -> List[SourceResult]:
        query_lower = query.lower()
        # Simple keyword matching for mock
        for k, results in self.mock_index.items():
            # If all words in index key are in query
            if all(word in query_lower for word in k.split()):
                return results
            # Fallback exact substring match
            if k in query_lower:
                return results
        return []
