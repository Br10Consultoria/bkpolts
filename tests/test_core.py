import os
import unittest
from pathlib import Path
from unittest.mock import patch

from common.helpers import redact_secrets
from common.parser import parse_olts
from common.vendors import VENDORS, vendor_map


class VendorCatalogTests(unittest.TestCase):
    def test_catalog_has_a_real_driver_and_unique_model_variables(self):
        seen = set()
        project = Path(__file__).resolve().parent.parent
        for vendor, definition in VENDORS.items():
            self.assertTrue((project / "vendors" / definition["driver"] / "backup.py").is_file())
            self.assertTrue(definition["models"], vendor)
            for model in definition["models"]:
                self.assertNotIn(model["env_var"], seen)
                self.assertTrue(set(model["protocols"]) <= {"ftp", "tftp", "scp", "sftp"})
                seen.add(model["env_var"])

    def test_vendor_map_is_derived_from_catalog(self):
        self.assertEqual(vendor_map()["zte"], ["ZTE_OLTS", "ZTE_TITAN_OLTS"])
        self.assertIn("INTELBRAS_G16_OLTS", vendor_map()["intelbras_g16"])


class ParserAndSecurityTests(unittest.TestCase):
    def test_parser_preserves_colons_in_password(self):
        with patch.dict(os.environ, {"TEST_OLTS": "OLT1:10.0.0.1:admin:a:b:c"}, clear=False):
            self.assertEqual(parse_olts("TEST_OLTS")[0]["password"], "a:b:c")

    def test_command_logging_redacts_known_credentials(self):
        with patch.dict(os.environ, {"FTP_PASSWORD": "segredo123"}, clear=False):
            command = "copy ftp user admin password segredo123 //admin:segredo123@host/file"
            result = redact_secrets(command)
            self.assertNotIn("segredo123", result)
            self.assertIn("****", result)


if __name__ == "__main__":
    unittest.main()
