import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import webui.app as web
from common.env_store import load_env


class OltManagementTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tempdir.name) / ".env"
        self.env_file.write_text(
            "WEBUI_USER=admin\nWEBUI_PASSWORD=test\n"
            "DATACOM_OLTS=OLT1:10.0.0.1:admin:oldpass\n",
            encoding="utf-8",
        )
        self.patch = patch.object(web, "ENV_FILE", self.env_file)
        self.patch.start()
        web.app.config.update(TESTING=True)
        self.client = web.app.test_client()
        with self.client.session_transaction() as session:
            session["logged_in"] = True
            session["csrf"] = "token"

    def tearDown(self):
        self.patch.stop()
        self.tempdir.cleanup()

    def test_disable_and_enable_olt(self):
        url = "/vendor/datacom/toggle/OLT1"
        data = {"csrf": "token", "list_var": "DATACOM_OLTS"}
        self.client.post(url, data=data)
        self.assertEqual(load_env(self.env_file)["DATACOM_OLTS_DISABLED"], "OLT1")
        self.client.post(url, data=data)
        self.assertEqual(load_env(self.env_file)["DATACOM_OLTS_DISABLED"], "")

    def test_edit_preserves_password_when_left_blank(self):
        response = self.client.post(
            "/vendor/datacom/edit/OLT1",
            data={
                "csrf": "token",
                "list_var": "DATACOM_OLTS",
                "name": "OLT_NOVA",
                "ip": "10.0.0.9",
                "user": "backup",
                "password": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            load_env(self.env_file)["DATACOM_OLTS"],
            "OLT_NOVA:10.0.0.9:backup:oldpass",
        )


if __name__ == "__main__":
    unittest.main()
