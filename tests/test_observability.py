import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.observability import dashboard_data, record_snmp_sample, tracked_backup
from import_inventory import import_devices
from snmp_collector import communities, devices_from_env


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "test.db")
        self.env = patch.dict(os.environ, {"BKPOLTS_DB": self.db, "BACKUP_SOURCE": "test"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_backup_success_and_failure_are_persisted(self):
        @tracked_backup("zte", "ftp")
        def backup(olt, succeeds):
            return succeeds

        olt = {"name": "OLT-A", "ip": "10.0.0.1"}
        self.assertTrue(backup(olt, True))
        self.assertFalse(backup(olt, False))
        data = dashboard_data()
        self.assertEqual(data["totals"]["success"], 1)
        self.assertEqual(data["totals"]["failure"], 1)
        self.assertIn("não concluído", data["recent"][0]["error_message"])

    def test_snmp_latest_sample_is_aggregated(self):
        device = {"name": "OLT-A", "ip": "10.0.0.1", "vendor": "zte"}
        record_snmp_sample(device, True, {"sys_name": "olt-a", "uptime_ticks": 100})
        self.assertEqual(dashboard_data()["totals"], {})

    def test_import_keeps_communities_only_in_env_mapping(self):
        devices = [{"name": "OLT-A", "ip": "10.0.0.1", "vendor": "zte",
                    "model": "c3xx", "snmp_community": "private-secret"}]
        env_file = Path(self.temp.name) / ".env"
        import_devices(devices, "bkpolt", "password", env_file)
        raw = env_file.read_text(encoding="utf-8")
        self.assertIn("SNMP_COMMUNITIES_JSON", raw)
        mapping_line = next(x for x in raw.splitlines() if x.startswith("SNMP_COMMUNITIES_JSON="))
        parsed = json.loads(mapping_line.split("=", 1)[1])
        self.assertEqual(parsed["10.0.0.1"], "private-secret")
        self.assertEqual(communities({"SNMP_COMMUNITIES_JSON": json.dumps(parsed)}), parsed)

    def test_disabled_olt_is_not_polled(self):
        env = {"ZTE_OLTS": "OLT-A:10.0.0.1:user:pass", "ZTE_OLTS_DISABLED": "OLT-A"}
        self.assertEqual(devices_from_env(env), [])


if __name__ == "__main__":
    unittest.main()
