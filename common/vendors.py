"""Catálogo central de fabricantes, modelos e drivers suportados.

O CLI, scheduler, testes e painel web consomem este catálogo de runtime.
"""

VENDORS = {
    "datacom": {
        "label": "Datacom",
        "driver": "datacom",
        "models": [
            {"key": "dmos", "label": "DM4615 / DM4618 / DmOS", "env_var": "DATACOM_OLTS", "protocols": ["tftp"]},
        ],
    },
    "zte": {
        "label": "ZTE",
        "driver": "zte",
        "models": [
            {"key": "c3xx", "label": "C300 / C320 / C350", "env_var": "ZTE_OLTS", "protocols": ["ftp"]},
            {"key": "titan", "label": "Titan / C600", "env_var": "ZTE_TITAN_OLTS", "protocols": ["ftp"]},
        ],
    },
    "parks": {
        "label": "Parks",
        "driver": "parks",
        "models": [
            {"key": "fiberlink", "label": "Fiberlink", "env_var": "PARKS_OLTS", "protocols": ["ftp"]},
        ],
    },
    "fiberhome": {
        "label": "Fiberhome",
        "driver": "fiberhome",
        "models": [
            {"key": "an5xxx", "label": "AN5516 / AN6000", "env_var": "FIBERHOME_OLTS", "protocols": ["ftp"]},
        ],
    },
    "huawei": {
        "label": "Huawei",
        "driver": "huawei",
        "models": [
            {"key": "ma5xxx", "label": "MA5600 / MA5800", "env_var": "HUAWEI_OLTS", "protocols": ["ftp"]},
        ],
    },
    "intelbras_g16": {
        "label": "Intelbras",
        "driver": "intelbras_g16",
        "models": [
            {"key": "g16", "label": "G16", "env_var": "INTELBRAS_G16_OLTS", "protocols": ["ftp", "tftp"]},
        ],
    },
}


def vendor_map() -> dict[str, list[str]]:
    return {key: [m["env_var"] for m in value["models"]] for key, value in VENDORS.items()}


def vendor_labels() -> dict[str, str]:
    labels = {}
    for key, value in VENDORS.items():
        protocols = sorted({p.upper() for m in value["models"] for p in m["protocols"]})
        labels[key] = f"{value['label']} (Telnet + {'/'.join(protocols)})"
    return labels


def model_for_env(vendor: str, env_var: str) -> dict | None:
    for model in VENDORS.get(vendor, {}).get("models", []):
        if model["env_var"] == env_var:
            return model
    return None
