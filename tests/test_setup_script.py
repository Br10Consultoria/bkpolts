import unittest
from pathlib import Path


class SetupRegressionTests(unittest.TestCase):
    def test_empty_inventory_is_not_skipped_by_old_flag(self):
        script = (Path(__file__).resolve().parent.parent / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("configured_olts=$(grep -Ec", script)
        self.assertIn('[[ "$configured_olts" -gt 0 ]]', script)
        self.assertIn("--force-recreate olt-backup webui snmp-monitor", script)


if __name__ == "__main__":
    unittest.main()
