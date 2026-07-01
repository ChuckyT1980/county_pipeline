from .base import BaseConnector
from .tehama import TehamaConnector

def get_connector(county: str) -> BaseConnector:
    """
    County dispatch factory. Returns the correct connector for a given county string.
    Supports: 'tehama', 'shasta' (shasta requires connectors/shasta.py to exist).
    """
    county = county.lower().strip()
    if county == "tehama":
        return TehamaConnector(county=county)
    elif county == "shasta":
        try:
            from .shasta import ShastaConnector
            return ShastaConnector(county=county)
        except ImportError:
            raise ImportError(
                "ShastaConnector not found. Create connectors/shasta.py before using county='shasta'."
            )
    else:
        raise ValueError(
            f"Unknown county '{county}'. Supported values: 'tehama', 'shasta'."
        )

__all__ = ["BaseConnector", "TehamaConnector", "get_connector"]
