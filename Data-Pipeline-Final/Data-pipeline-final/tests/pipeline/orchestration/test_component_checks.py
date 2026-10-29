"""The component test flags select isolated suites without starting processing."""
import sys
from unittest.mock import Mock, patch
import unittest

from data_pipeline import cli, data_pipeline, fx_api, testing


class ComponentCheckTests(unittest.TestCase):
    @patch.object(sys, "argv", ["trade-api-usd-exchange-rates", "--test"])
    @patch.object(testing, "run_unit_checks", return_value=3)
    @patch.object(fx_api, "refresh_currency_table")
    def test_api_test_flag_propagates_failure_without_refreshing(self, refresh, checks):
        with self.assertRaises(SystemExit) as caught:
            fx_api.main()
        self.assertEqual(caught.exception.code, 3)
        checks.assert_called_once_with("api-usd-exchange-rates")
        refresh.assert_not_called()

    @patch.object(sys, "argv", ["trade-transform", "--test"])
    @patch.object(testing, "run_unit_checks", return_value=0)
    @patch.object(data_pipeline, "run_bronze_to_silver")
    def test_transform_test_flag_does_not_transform_datasets(self, transform, checks):
        with self.assertRaises(SystemExit) as caught:
            data_pipeline.main()
        self.assertEqual(caught.exception.code, 0)
        checks.assert_called_once_with("transform")
        transform.assert_not_called()

    @patch.object(testing.subprocess, "run", return_value=Mock(returncode=0))
    def test_transform_selection_excludes_external_and_published_data(self, run):
        testing.run_unit_checks("transform")
        command = run.call_args.args[0]
        selected = command[4:]
        self.assertTrue(selected)
        self.assertTrue(all(module.startswith(("tests.pipeline.transformation.", "tests.pipeline.enrichment.", "tests.pipeline.semantics.", "tests.pipeline.publication.")) for module in selected))

    @patch.object(sys, "argv", ["trade", "quality-checks", "example.parquet"])
    @patch("data_pipeline.quality_checks.main")
    def test_quality_subcommand_forwards_explicit_path(self, quality):
        cli.main()
        quality.assert_called_once_with(["example.parquet"])
