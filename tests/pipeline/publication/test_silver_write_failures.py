from importlib import import_module
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

pipeline = import_module("data_pipeline.data_pipeline")


class SilverWriteTests(unittest.TestCase):
    def test_partial_parquet_failure_preserves_previous_file_and_reports_cause(self):
        frame = pd.DataFrame({"INT_ID": [1]})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "trades_enriched.parquet"
            frame.to_parquet(path, index=False)
            original = path.read_bytes()
            error = OSError("disk full")
            def fail_write(frame, path, **kwargs):
                Path(path).write_bytes(b"partial")
                raise error
            with patch.object(pd.DataFrame, "to_parquet", fail_write):
                with self.assertLogs(pipeline.LOGGER, level="ERROR") as logs:
                    with self.assertRaises(pipeline.SilverWriteError) as caught:
                        pipeline.write_silver(frame, root)
            self.assertIs(caught.exception.__cause__, error)
            self.assertIn(str(path), str(caught.exception))
            self.assertIn("disk full", str(caught.exception))
            self.assertIn("Parquet write FAILED", "\n".join(logs.output))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [path])

    def test_replace_failure_reports_locked_destination_and_removes_temporary(self):
        frame = pd.DataFrame({"INT_ID": [1]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trades_enriched.parquet"
            frame.to_parquet(path, index=False)
            original = path.read_bytes()
            with patch.object(Path, "replace", side_effect=PermissionError("destination locked")):
                with self.assertLogs(pipeline.LOGGER, level="ERROR"):
                    with self.assertRaisesRegex(pipeline.SilverWriteError, "destination locked"):
                        pipeline.write_parquet(frame, path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(temp).iterdir()), [path])

