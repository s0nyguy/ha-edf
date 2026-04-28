"""Tests for EDF Kraken API normalization."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


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

parse_account_data = sys.modules["custom_components.edf_kraken.api"].parse_account_data


def test_parse_dual_fuel_readings() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "120001",
                                "meters": [
                                    {
                                        "id": "elec-meter",
                                        "serialNumber": "E123",
                                        "readings": {
                                            "edges": [
                                                {
                                                    "node": {
                                                        "readAt": "2026-04-28T12:00:00+01:00",
                                                        "registers": [
                                                            {
                                                                "id": "1",
                                                                "identifier": "Total",
                                                                "value": "1234.5",
                                                            }
                                                        ],
                                                    }
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        ],
                        "gasMeterPoints": [
                            {
                                "mprn": "98765",
                                "meters": [
                                    {
                                        "id": "gas-meter",
                                        "serialNumber": "G123",
                                        "readings": {
                                            "edges": [
                                                {
                                                    "node": {
                                                        "readAt": "2026-04-28T12:00:00+01:00",
                                                        "registers": [
                                                            {
                                                                "identifier": "Total",
                                                                "value": 456.7,
                                                            }
                                                        ],
                                                    }
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        "A-1",
    )

    assert data.account_number == "A-1"
    assert len(data.readings) == 2
    assert data.readings[0].fuel == "electricity"
    assert data.readings[0].value == 1234.5
    assert data.readings[0].unit == "kWh"
    assert data.readings[1].fuel == "gas"
    assert data.readings[1].value == 456.7
    assert data.readings[1].unit == "m3"


def test_parse_multi_register_electricity() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "120001",
                                "meters": [
                                    {
                                        "serialNumber": "E7",
                                        "readings": [
                                            {
                                                "reading": "100",
                                                "unit": "kWh",
                                                "registerId": "day",
                                                "registerLabel": "Day",
                                            },
                                            {
                                                "reading": "200",
                                                "unit": "kWh",
                                                "registerId": "night",
                                                "registerLabel": "Night",
                                            },
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        },
        "A-1",
    )

    assert len(data.readings) == 2
    assert {reading.register_id for reading in data.readings} == {"day", "night"}
    assert data.readings[0].unique_id != data.readings[1].unique_id


def test_parse_missing_consumption_is_not_required() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "120001",
                                "meters": [{"serialNumber": "E123", "readings": []}],
                            }
                        ],
                        "gasMeterPoints": [],
                    }
                ]
            }
        },
        "A-1",
    )

    assert data.readings == ()
