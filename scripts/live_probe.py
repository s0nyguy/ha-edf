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
        variant_results = await _async_probe_reading_variants(client, data.account_number)

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

    if variant_results:
        print("Reading query variants:")
        for result in variant_results:
            print(f"  {result}")

    return 0


async def _async_probe_reading_variants(
    client: EdfKrakenApiClient,
    account_number: str,
) -> list[str]:
    """Try tiny reading query variants when the main path still finds no readings."""
    payload = await client._request(  # noqa: SLF001
        """
        query AccountMeterTopology($accountNumber: String!) {
          account(accountNumber: $accountNumber) {
            properties {
              electricityMeterPoints {
                meters(includeInactive: true) {
                  id
                }
              }
              gasMeterPoints {
                meters(includeInactive: true) {
                  id
                }
              }
            }
          }
        }
        """,
        {"accountNumber": account_number},
        authenticated=True,
    )

    account = payload.get("account")
    if not isinstance(account, dict):
        return []

    results: list[str] = []
    probes = []
    for property_item in account.get("properties") or []:
        if not isinstance(property_item, dict):
            continue
        for meter_point in property_item.get("electricityMeterPoints") or []:
            for meter in meter_point.get("meters") or []:
                meter_id = meter.get("id") if isinstance(meter, dict) else None
                if meter_id:
                    probes.append(("electricity", "electricityMeterReadings", str(meter_id)))
        for meter_point in property_item.get("gasMeterPoints") or []:
            for meter in meter_point.get("meters") or []:
                meter_id = meter.get("id") if isinstance(meter, dict) else None
                if meter_id:
                    probes.append(("gas", "gasMeterReadings", str(meter_id)))

    for fuel, field_name, meter_id in probes:
        for variant_name, query in _reading_variant_queries(field_name):
            try:
                result = await client._request(  # noqa: SLF001
                    query,
                    {"accountNumber": account_number, "meterId": meter_id},
                    authenticated=True,
                )
            except Exception as err:  # noqa: BLE001
                results.append(f"{fuel} {meter_id} {variant_name}: error - {err}")
                continue
            connection = result.get(field_name)
            edge_count = connection.get("edgeCount") if isinstance(connection, dict) else None
            edges = connection.get("edges") if isinstance(connection, dict) else None
            result_count = len(edges) if isinstance(edges, list) else edge_count
            results.append(f"{fuel} {meter_id} {variant_name}: ok - {result_count} readings")

    return results


def _reading_variant_queries(field_name: str) -> list[tuple[str, str]]:
    return [
        (
            "count_only",
            f"""
            query MeterReadings($accountNumber: String!, $meterId: ID!) {{
              {field_name}(accountNumber: $accountNumber, meterId: $meterId, first: 1) {{
                edgeCount
                totalCount
              }}
            }}
            """,
        ),
        (
            "basic_node",
            f"""
            query MeterReadings($accountNumber: String!, $meterId: ID!) {{
              {field_name}(accountNumber: $accountNumber, meterId: $meterId, first: 1) {{
                edges {{
                  node {{
                    readAt
                    registers {{
                      identifier
                      value
                    }}
                  }}
                }}
              }}
            }}
            """,
        ),
    ]


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))


if __name__ == "__main__":
    main()
