"""
tests/test_sales_equity.py — Unit tests for sales_equity.py module
"""

import unittest
from datetime import date
from sales_equity import (
    BUTTE_TRANSFER_TAX_RATE,
    calculate_price_from_transfer_tax,
    calculate_tenure_years,
    compute_sales_equity_layer,
    evaluate_equity_gate,
    is_non_arms_length_transfer,
    resolve_sale_price,
)
from contracts import (
    EquityBand,
    EquityConfidence,
    MarketEstimateSource,
    SalePriceConfidence,
)


class TestSalesEquity(unittest.TestCase):
    def test_transfer_tax_calculation(self):
        # Tax $110.00 at $1.10 per $1000 = $100,000 price
        price = calculate_price_from_transfer_tax(110.00)
        self.assertEqual(price, 100000.0)

        # Tax $55.00 = $50,000
        price2 = calculate_price_from_transfer_tax(55.00)
        self.assertEqual(price2, 50000.0)

        # Zero tax returns None
        self.assertIsNone(calculate_price_from_transfer_tax(0.0))

    def test_non_arms_length_detection(self):
        # Family surname match
        self.assertTrue(is_non_arms_length_transfer(grantor="SMITH JOHN", grantee="SMITH MARY"))

        # Quitclaim deed
        self.assertTrue(is_non_arms_length_transfer(doc_type="QUITCLAIM DEED"))

        # Nominal transfer tax
        self.assertTrue(is_non_arms_length_transfer(transfer_tax=0.55))

        # Arm's length
        self.assertFalse(
            is_non_arms_length_transfer(
                grantor="JOHNSON ALICE",
                grantee="WILLIAMS ROBERT",
                doc_type="GRANT DEED",
                transfer_tax=165.00,
            )
        )

    def test_resolution_ladder(self):
        # Tier 1: Recorder-verified for top tier
        price, conf, sale_date, rec_price = resolve_sale_price(
            assessed_total=150000.0,
            recorder_deed_date="2020-05-15",
            recorder_transfer_tax=220.0,  # $200k price
            is_top_tier=True,
        )
        self.assertEqual(price, 200000.0)
        self.assertEqual(conf, SalePriceConfidence.RECORDER_VERIFIED)
        self.assertEqual(sale_date, "2020-05-15")

        # Tier 3: Assessor proxy (bulk path)
        price_proxy, conf_proxy, date_proxy, _ = resolve_sale_price(
            assessed_total=150000.0,
            recorder_deed_date="2020-05-15",
            recorder_transfer_tax=220.0,
            is_top_tier=False,  # Not escalated
        )
        self.assertEqual(price_proxy, 150000.0)
        self.assertEqual(conf_proxy, SalePriceConfidence.ASSESSOR_PROXY)

        # Tier 4: No deed on file
        price_none, conf_none, _, _ = resolve_sale_price(
            assessed_total=None,
            recorder_deed_date=None,
            recorder_transfer_tax=None,
        )
        self.assertIsNone(price_none)
        self.assertEqual(conf_none, SalePriceConfidence.NO_DEED_UNKNOWN)

    def test_tenure_years_calculation(self):
        ref = date(2026, 8, 2)
        tenure = calculate_tenure_years("2016-08-02", ref_date=ref)
        self.assertAlmostEqual(tenure, 10.0, delta=0.1)

    def test_measured_equity_gap(self):
        # Market estimate $300k, proxy $150k -> gap $150k (>50% = high)
        res = compute_sales_equity_layer(
            apn="022-210-078-000",
            county="butte",
            assessed_total=150000.0,
            market_estimate=300000.0,
            market_estimate_source=MarketEstimateSource.COMPS,
        )
        self.assertEqual(res.equity_estimate, 150000.0)
        self.assertEqual(res.equity_confidence, EquityConfidence.MEASURED)
        self.assertEqual(res.equity_band, EquityBand.HIGH)

    def test_tenure_proxy_equity(self):
        # 16.5-year hold -> tenure_mid
        res_mid = compute_sales_equity_layer(
            apn="027-290-021-000",
            county="butte",
            assessed_total=50000.0,
            recorder_deed_date="2010-01-01",
        )
        self.assertIsNone(res_mid.equity_estimate)  # Not coerced
        self.assertEqual(res_mid.equity_confidence, EquityConfidence.TENURE_PROXY)
        self.assertEqual(res_mid.equity_band, EquityBand.TENURE_MID)

        # 30-year hold -> tenure_long
        res_long = compute_sales_equity_layer(
            apn="027-290-022-000",
            county="butte",
            assessed_total=50000.0,
            recorder_deed_date="1996-01-01",
        )
        self.assertEqual(res_long.equity_band, EquityBand.TENURE_LONG)

        # 5-year hold -> tenure_short
        res_short = compute_sales_equity_layer(
            apn="027-290-023-000",
            county="butte",
            assessed_total=50000.0,
            recorder_deed_date="2021-01-01",
        )
        self.assertEqual(res_short.equity_band, EquityBand.TENURE_SHORT)

    def test_unknown_equity_no_coercion(self):
        # Estate with no deed or sale record -> unknown equity, excess candidate
        res = compute_sales_equity_layer(
            apn="035-143-011-000",
            county="butte",
            assessed_total=75000.0,
            is_estate_or_deceased=True,
        )
        self.assertIsNone(res.equity_estimate)  # MUST NOT be 0.0
        self.assertEqual(res.equity_confidence, EquityConfidence.UNKNOWN)
        self.assertEqual(res.equity_band, EquityBand.UNKNOWN)
        self.assertTrue(res.excess_proceeds_candidate)

    def test_equity_gate_evaluation(self):
        res_pass = compute_sales_equity_layer(
            apn="001",
            county="butte",
            assessed_total=100000.0,
            market_estimate=200000.0,
        )
        status, _ = evaluate_equity_gate(res_pass)
        self.assertEqual(status, "PASS")

        res_unknown = compute_sales_equity_layer(
            apn="002",
            county="butte",
            assessed_total=100000.0,
            is_estate_or_deceased=True,
        )
        status_unk, _ = evaluate_equity_gate(res_unknown)
        self.assertEqual(status_unk, "UNKNOWN_ROUTE")

        res_thin = compute_sales_equity_layer(
            apn="003",
            county="butte",
            assessed_total=100000.0,
            market_estimate=105000.0,  # 5% gap = thin
        )
        status_thin, _ = evaluate_equity_gate(res_thin)
        self.assertEqual(status_thin, "FAIL_DEMOTE")


if __name__ == "__main__":
    unittest.main()
