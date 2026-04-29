"""Validate the repository shape required by HACS for this integration."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "edf_kraken"
REQUIRED_MANIFEST_KEYS = {
    "codeowners",
    "config_flow",
    "documentation",
    "domain",
    "iot_class",
    "issue_tracker",
    "name",
    "version",
}


def main() -> None:
    """Validate HACS and Home Assistant metadata."""
    custom_components = ROOT / "custom_components"
    integration_path = custom_components / DOMAIN
    hacs_path = ROOT / "hacs.json"
    manifest_path = integration_path / "manifest.json"

    assert custom_components.is_dir(), "custom_components directory is missing"
    integrations = [path for path in custom_components.iterdir() if path.is_dir()]
    assert integrations == [integration_path], (
        "HACS expects exactly one integration directory under custom_components"
    )

    assert hacs_path.is_file(), "hacs.json is missing from repository root"
    hacs = json.loads(hacs_path.read_text(encoding="utf-8"))
    assert hacs.get("name") == "EDF Kraken", "hacs.json name is incorrect"

    assert manifest_path.is_file(), "manifest.json is missing"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = REQUIRED_MANIFEST_KEYS - set(manifest)
    assert not missing, f"manifest.json is missing required keys: {sorted(missing)}"
    assert manifest["domain"] == DOMAIN, "manifest domain does not match integration directory"
    assert manifest["version"], "manifest version must be set for HACS releases"

    print("HACS metadata ok")


if __name__ == "__main__":
    main()
