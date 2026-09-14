import tempfile
import unittest
from pathlib import Path

from common.env_store import load_env, parse_olts_raw
from import_inventory import import_devices, load_devices


class InventoryImportTests(unittest.TestCase):
    def test_initial_inventory_contains_only_supported_requested_vendors(self):
        path = Path(__file__).resolve().parent.parent / "inventory" / "initial_olts.json"
        devices, username = load_devices(path)
        self.assertEqual(len(devices), 20)
        self.assertEqual(username, "bkpolt")
        self.assertEqual({d["vendor"] for d in devices}, {"datacom", "zte", "huawei"})
        self.assertEqual(len([d for d in devices if d["vendor"] == "zte" and d["model"] == "titan"]), 2)
        self.assertNotIn("password", path.read_text(encoding="utf-8").lower())

    def test_import_is_idempotent_by_ip_and_updates_credentials(self):
        inventory = Path(__file__).resolve().parent.parent / "inventory" / "initial_olts.json"
        devices, _ = load_devices(inventory)
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text(
                "VENDOR=datacom\nDATACOM_OLTS=NOME_EXISTENTE:10.10.10.34:old:old\n",
                encoding="utf-8",
            )
            first = import_devices(devices, "bkpolt", "secret", env_file)
            second = import_devices(devices, "bkpolt", "newsecret", env_file)
            env = load_env(env_file)
            total = sum(len(parse_olts_raw(env.get(key, ""))) for key in
                        ["DATACOM_OLTS", "ZTE_OLTS", "ZTE_TITAN_OLTS", "HUAWEI_OLTS"])
            self.assertEqual(total, 20)
            self.assertEqual(first["added"], 19)
            self.assertEqual(second["added"], 0)
            existing = parse_olts_raw(env["DATACOM_OLTS"])[0]
            self.assertEqual(existing["name"], "NOME_EXISTENTE")
            self.assertEqual(existing["password"], "newsecret")
            self.assertEqual(set(env["VENDOR"].split(",")), {"datacom", "zte", "huawei"})


if __name__ == "__main__":
    unittest.main()
