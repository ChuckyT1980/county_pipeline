from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        pass

class MockSearchProvider(SearchProvider):
    def __init__(self):
        # We simulate what a real search engine would return for queries
        self.mock_index = {
            "shasta county ca property tax": [
                SearchResult(
                    title="Shasta County Property Tax Search",
                    url="https://mptsweb.co.shasta.ca.us/search.asp",
                    snippet="Search and pay your Shasta County property taxes online. Enter your Fee Parcel or Assessment Number."
                ),
                SearchResult(
                    title="Shasta County Assessor",
                    url="https://www.co.shasta.ca.us/assessor",
                    snippet="Official page for the Shasta County Assessor."
                )
            ],
            "tehama county ca property tax": [
                SearchResult(
                    title="Tehama County Property Tax",
                    url="https://mptsweb.co.tehama.ca.us/taxsearch",
                    snippet="View Tehama County taxes via Megabyte Systems."
                )
            ],
            "fake_aumentum county ca property tax": [
                SearchResult(
                    title="Property Tax Portal",
                    url="https://taxes.fakeaumentum.ca.us/Aumentum/search",
                    snippet="Powered by Aumentum Technologies."
                )
            ],
            "fake_govos county ca property tax": [
                SearchResult(
                    title="GovOS Property Search",
                    url="https://search.fakegovos.ca.us/records",
                    snippet="Official Kofile / GovOS records search for the county."
                )
            ]
        }
        
    def search(self, query: str) -> List[SearchResult]:
        query_lower = query.lower()
        for k, results in self.mock_index.items():
            if k in query_lower:
                return results
        return []
