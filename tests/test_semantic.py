import unittest
from canonical import init_intelligence_record
from signals import generate_signals
from scoring import process_record

class TestSemanticMeaning(unittest.TestCase):
    
    def test_estate_semantic_mapping(self):
        """
        Prove that OVERMAN, FRANKLIN CHARLES DECD EST OF correctly maps to:
        - deceased_owner = True
        - heir_probability = High (0.9)
        - ownership_complexity is increased
        """
        raw = {
            "apn": "123",
            "owner_raw": "OVERMAN, FRANKLIN CHARLES DECD EST OF",
            "address_raw": "123 MAIN ST",
            "amount_raw": "5000"
        }
        record = init_intelligence_record(raw, "shasta")
        generate_signals(record)
        
        self.assertTrue(record.signals.deceased_owner)
        self.assertFalse(record.signals.trust_owner)
        
        process_record(record)
        
        self.assertEqual(record.states.heir_probability, 0.9)
        self.assertGreater(record.states.ownership_complexity, 0.1) # Higher than baseline
        self.assertLess(record.states.ownership_stability, 0.9) # Lower than baseline
        self.assertGreater(record.opportunity.resolution_difficulty, 0.5) # Friction should be high

    def test_trust_semantic_mapping(self):
        """
        Prove that SMITH FAMILY REVOC TR correctly maps to:
        - trust_owner = True
        - ownership_complexity is increased, but not as much as estate
        """
        raw = {
            "apn": "456",
            "owner_raw": "SMITH FAMILY REVOC TR",
            "address_raw": "456 OAK ST",
            "amount_raw": "2000"
        }
        record = init_intelligence_record(raw, "shasta")
        generate_signals(record)
        
        self.assertTrue(record.signals.trust_owner)
        self.assertFalse(record.signals.deceased_owner)
        
        process_record(record)
        
        self.assertEqual(record.states.heir_probability, 0.0)
        self.assertGreater(record.states.ownership_complexity, 0.1)

    def test_owner_occupied_heuristic(self):
        """
        Prove that identical mailing and situs address implies owner_occupied.
        """
        raw = {
            "apn": "789",
            "owner_raw": "JOHN DOE",
            "address_raw": "789 PINE ST",
            "situs_raw": "789 PINE ST",
            "amount_raw": "100"
        }
        record = init_intelligence_record(raw, "shasta")
        generate_signals(record)
        self.assertTrue(record.signals.owner_occupied)

    def test_missing_data_confidence_penalty(self):
        """
        Prove that missing acreage or assessed value drops the confidence score.
        """
        raw = {
            "apn": "999",
            "owner_raw": "JOHN", # Too short
            "amount_raw": "0"
        }
        record = init_intelligence_record(raw, "shasta")
        # Explicitly not adding acreage, land_use, assessed_value
        process_record(record)
        
        self.assertLess(record.confidence.data_confidence, 1.0)
        self.assertLess(record.confidence.ownership_confidence, 1.0)
        self.assertLess(record.confidence.valuation_confidence, 1.0)
        self.assertLess(record.confidence.overall_confidence, 1.0)

if __name__ == '__main__':
    unittest.main()
