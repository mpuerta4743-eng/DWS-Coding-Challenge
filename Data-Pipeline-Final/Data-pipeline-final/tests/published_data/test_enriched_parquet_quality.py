"""Quality tests against the actual published Parquet; generate it before running."""

from pathlib import Path
import sys
import unittest


from data_pipeline.quality_checks import check_enriched_parquet


class EnrichedParquetQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = check_enriched_parquet()
        print("\nEnriched Parquet quality counts:", cls.report)

    def test_every_trade_has_a_security(self):
        self.assertEqual(self.report["trades_without_security"], 0,
                         f'{self.report["trades_without_security"]} trades have BOOLEAN_HAS_SECURITY=FALSE')
        self.assertEqual(self.report["null_security_flags"], 0, "Security flags must not be null")

    def test_trade_ids_are_unique(self):
        self.assertEqual(self.report["duplicate_trade_id_rows"], 0,
                         f'{self.report["duplicate_trade_id_rows"]} rows share {self.report["duplicate_trade_ids"]} duplicated trade IDs')
        self.assertEqual(self.report["null_trade_ids"], 0, "Trade IDs must not be null")

    def test_side_is_sell_or_buy(self):
        self.assertEqual(self.report["invalid_side_rows"], 0,
                         f'{self.report["invalid_side_rows"]} rows have STRING_SIDE outside SELL/BUY (including nulls)')

    def test_every_trade_has_valid_quality_and_usd_value(self):
        self.assertEqual(
            self.report["invalid_quality_rows"], 0,
            f'{self.report["invalid_quality_rows"]} rows are marked invalid or contain quality flags',
        )
        self.assertEqual(
            self.report["invalid_usd_value_rows"], 0,
            f'{self.report["invalid_usd_value_rows"]} rows have missing or non-finite USD values',
        )


if __name__ == "__main__":
    unittest.main()
