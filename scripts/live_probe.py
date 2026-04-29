"""Run a sanitized live EDF Kraken API probe.

Required environment variables:
  EDF_KRAKEN_EMAIL
  EDF_KRAKEN_PASSWORD

Optional environment variables:
  EDF_KRAKEN_ACCOUNT_NUMBER

This script is intentionally not used by CI. It is for local real-account
validation while developing the custom integration.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import sys
import types

from aiohttp import ClientSession


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "edf_kraken"

sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
package = types.ModuleType("custom_components.edf_kraken")
package.__path__ = [str(INTEGRATION)]
sys.modules["custom_components.edf_kraken"] = package

for module_name in ("const", "api"):
    spec = importlib.util.spec_from_file_location(
        f"custom_components.edf_kraken.{module_name}",
        INTEGRATION / f"{module_name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

api = sys.modules["custom_components.edf_kraken.api"]
EdfKrakenApiClient = api.EdfKrakenApiClient


async def _async_main() -> int:
    email = os.environ.get("EDF_KRAKEN_EMAIL")
    password = os.environ.get("EDF_KRAKEN_PASSWORD")
    account_number = os.environ.get("EDF_KRAKEN_ACCOUNT_NUMBER")

    if not email or not password:
        print("Set EDF_KRAKEN_EMAIL and EDF_KRAKEN_PASSWORD before running this script.")
        return 2

    async with ClientSession() as session:
        client = EdfKrakenApiClient(session, retries=0)
        await client.authenticate(email, password)
        discovered_account = account_number or await client.get_first_account_number()
        data = await client.get_account_data(discovered_account)

    print(f"Account: {data.account_number}")
    print(f"Readings: {len(data.readings)}")
    print(f"Daily usages: {len(data.daily_usages)}")
    print(f"Metadata: {len(data.metadata)}")
    print(f"Topology error: {data.topology_error or '<none>'}")
    print("Query diagnostics:")
    for item in data.query_diagnostics:
        detail = f" - {item.detail}" if item.detail else ""
        print(f"  {item.stage}: {item.status}{detail}")

    if data.readings:
        print("Readings:")
        for reading in data.readings:
            print(
                "  "
                f"{reading.fuel} "
                f"{reading.name}: "
                f"{reading.value} {reading.unit} "
                f"read_at={reading.read_at or '<unknown>'} "
                f"meter_point={reading.meter_point_id or '<unknown>'} "
                f"meter={reading.meter_id or '<unknown>'} "
                f"serial={reading.serial_number or '<unknown>'}"
            )

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
