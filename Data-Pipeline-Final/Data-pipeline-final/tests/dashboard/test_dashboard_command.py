"""Verify the installed dashboard launcher respects input and server options."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from Dashboard import cli


class DashboardCommandTests(unittest.TestCase):
    @patch.object(sys, "argv", ["trade-dashboard", "--port", "8502", "--trades-path", "custom.parquet"])
    @patch.object(cli.subprocess, "run", return_value=Mock(returncode=7))
    def test_source_options_and_server_exit_code_are_forwarded(self, run):
        with self.assertRaises(SystemExit) as caught:
            cli.main()
        self.assertEqual(caught.exception.code, 7)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [sys.executable, "-m", "streamlit", "run"])
        self.assertTrue(Path(command[4]).is_file())
        self.assertIn("--server.port=8502", command)
        self.assertIn("--server.address=127.0.0.1", command)
        self.assertIn("--theme.base=light", command)
        self.assertEqual(run.call_args.kwargs["env"]["DWS_TRADES_PATH"], str(Path("custom.parquet").resolve()))

    @patch.object(sys, "argv", ["trade-dashboard", "--port", "0"])
    @patch.object(cli.subprocess, "run")
    def test_invalid_port_does_not_start_server(self, run):
        with self.assertRaises(SystemExit) as caught:
            cli.main()
        self.assertEqual(caught.exception.code, 2)
        run.assert_not_called()
