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
        schema_results = await _async_probe_schema(client)
        nested_results = await _async_probe_nested_reading_variants(client, data.account_number)
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

    if nested_results:
        print("Nested reading query variants:")
        for result in nested_results:
            print(f"  {result}")

    if schema_results:
        print("Schema probes:")
        for result in schema_results:
            print(f"  {result}")

    return 0


async def _async_probe_schema(client: EdfKrakenApiClient) -> list[str]:
    """Ask GraphQL which meter reading fields are available, if introspection works."""
    query = """
    query SchemaProbe {
      queryType: __type(name: "Query") {
        fields {
          name
          args {
            name
            type {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                }
              }
            }
          }
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
      electricityMeter: __type(name: "ElectricityMeter") {
        fields {
          name
          args {
            name
          }
        }
      }
      gasMeter: __type(name: "GasMeter") {
        fields {
          name
          args {
            name
          }
        }
      }
      meterReading: __type(name: "MeterReading") {
        fields {
          name
        }
      }
      meterReadingEventType: __type(name: "MeterReadingEventType") {
        enumValues {
          name
        }
      }
    }
    """
    try:
        payload = await client._request(query, {}, authenticated=True)  # noqa: SLF001
    except Exception as err:  # noqa: BLE001
        return [f"introspection: error - {err}"]

    results: list[str] = []
    query_type = payload.get("queryType")
    if isinstance(query_type, dict):
        fields = query_type.get("fields")
        if isinstance(fields, list):
            interesting = [
                field
                for field in fields
                if isinstance(field, dict)
                and any(token in str(field.get("name", "")).lower() for token in ("meter", "reading"))
            ]
            for field in sorted(interesting, key=lambda item: str(item.get("name", ""))):
                args = field.get("args")
                arg_names = [
                    f"{arg.get('name')}: {_format_graphql_type(arg.get('type'))}"
                    for arg in args or []
                    if isinstance(arg, dict) and arg.get("name")
                ]
                results.append(
                    f"Query.{field.get('name')}({', '.join(arg_names)})"
                    f": {_format_graphql_type(field.get('type'))}"
                )

    for type_key, label in (("electricityMeter", "ElectricityMeter"), ("gasMeter", "GasMeter")):
        type_payload = payload.get(type_key)
        if not isinstance(type_payload, dict):
            results.append(f"{label}: unavailable")
            continue
        fields = type_payload.get("fields")
        if not isinstance(fields, list):
            results.append(f"{label}: no fields")
            continue
        for field in sorted(fields, key=lambda item: str(item.get("name", ""))):
            if not isinstance(field, dict):
                continue
            name = str(field.get("name", ""))
            if "reading" not in name.lower():
                continue
            args = field.get("args")
            arg_names = [
                str(arg.get("name"))
                for arg in args or []
                if isinstance(arg, dict) and arg.get("name")
            ]
            results.append(f"{label}.{name}({', '.join(arg_names)})")

    meter_reading = payload.get("meterReading")
    if isinstance(meter_reading, dict) and isinstance(meter_reading.get("fields"), list):
        field_names = [
            str(field.get("name"))
            for field in meter_reading["fields"]
            if isinstance(field, dict) and field.get("name")
        ]
        results.append(f"MeterReading fields: {', '.join(sorted(field_names))}")
    else:
        results.append("MeterReading: unavailable")

    event_type = payload.get("meterReadingEventType")
    if isinstance(event_type, dict) and isinstance(event_type.get("enumValues"), list):
        values = [
            str(value.get("name"))
            for value in event_type["enumValues"]
            if isinstance(value, dict) and value.get("name")
        ]
        results.append(f"MeterReadingEventType values: {', '.join(values)}")
    else:
        results.append("MeterReadingEventType: unavailable")

    return results or ["introspection: ok - no matching fields"]


def _format_graphql_type(type_payload: object) -> str:
    """Return a compact GraphQL type name from introspection type payloads."""
    if not isinstance(type_payload, dict):
        return "unknown"
    kind = str(type_payload.get("kind") or "")
    name = type_payload.get("name")
    of_type = type_payload.get("ofType")
    if kind == "NON_NULL":
        return f"{_format_graphql_type(of_type)}!"
    if kind == "LIST":
        return f"[{_format_graphql_type(of_type)}]"
    return str(name or kind or "unknown")


async def _async_probe_nested_reading_variants(
    client: EdfKrakenApiClient,
    account_number: str,
) -> list[str]:
    """Try account topology queries with minimal nested readings selections."""
    results: list[str] = []
    for variant_name, query in _nested_reading_variant_queries():
        try:
            payload = await client._request(  # noqa: SLF001
                query,
                {"accountNumber": account_number},
                authenticated=True,
            )
        except Exception as err:  # noqa: BLE001
            results.append(f"{variant_name}: error - {err}")
            continue

        count = 0
        account = payload.get("account")
        if isinstance(account, dict):
            for property_item in account.get("properties") or []:
                if not isinstance(property_item, dict):
                    continue
                for key in ("electricityMeterPoints", "gasMeterPoints"):
                    for meter_point in property_item.get(key) or []:
                        if not isinstance(meter_point, dict):
                            continue
                        for meter in meter_point.get("meters") or []:
                            if not isinstance(meter, dict):
                                continue
                            readings = meter.get("readings")
                            if isinstance(readings, dict) and isinstance(readings.get("edges"), list):
                                count += len(readings["edges"])
        results.append(f"{variant_name}: ok - {count} readings")
    return results


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


def _nested_reading_variant_queries() -> list[tuple[str, str]]:
    return [
        (
            "nested_count_only",
            """
            query AccountNestedReadings($accountNumber: String!) {
              account(accountNumber: $accountNumber) {
                properties {
                  electricityMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edgeCount
                        totalCount
                      }
                    }
                  }
                  gasMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edgeCount
                        totalCount
                      }
                    }
                  }
                }
              }
            }
            """,
        ),
        (
            "nested_read_at",
            """
            query AccountNestedReadings($accountNumber: String!) {
              account(accountNumber: $accountNumber) {
                properties {
                  electricityMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            readAt
                          }
                        }
                      }
                    }
                  }
                  gasMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            readAt
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
        ),
        (
            "nested_register_value",
            """
            query AccountNestedReadings($accountNumber: String!) {
              account(accountNumber: $accountNumber) {
                properties {
                  electricityMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            registers {
                              identifier
                              value
                            }
                          }
                        }
                      }
                    }
                  }
                  gasMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            registers {
                              identifier
                              value
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
        ),
        (
            "nested_full_without_register_id",
            """
            query AccountNestedReadings($accountNumber: String!) {
              account(accountNumber: $accountNumber) {
                properties {
                  electricityMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            readAt
                            readingSource
                            readingType
                            source
                            registers {
                              identifier
                              value
                            }
                          }
                        }
                      }
                    }
                  }
                  gasMeterPoints {
                    meters(includeInactive: true) {
                      readings(first: 1) {
                        edges {
                          node {
                            readAt
                            readingSource
                            readingType
                            source
                            registers {
                              identifier
                              value
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """,
        ),
    ]


def _reading_variant_queries(field_name: str) -> list[tuple[str, str]]:
    return [
        (
            "count_only",
            f"""
            query MeterReadings($accountNumber: String!, $meterId: String!) {{
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
            query MeterReadings($accountNumber: String!, $meterId: String!) {{
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
