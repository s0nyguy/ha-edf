"""Tests for EDF Kraken API normalization."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

from aiohttp import ClientResponseError, RequestInfo
from yarl import URL


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
EdfKrakenRateLimitError = api.EdfKrakenRateLimitError
parse_account_data = api.parse_account_data


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


def test_parse_multiple_properties_and_meters() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "mpan-1",
                                "meters": [
                                    {
                                        "id": "meter-1",
                                        "serialNumber": "E1",
                                        "readings": [
                                            {"value": "1", "registerId": "total"}
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "mpan-2",
                                "meters": [
                                    {
                                        "id": "meter-2",
                                        "serialNumber": "E2",
                                        "readings": [
                                            {"value": "2", "registerId": "total"}
                                        ],
                                    },
                                    {
                                        "id": "meter-3",
                                        "serialNumber": "E3",
                                        "readings": [
                                            {"value": "3", "registerId": "total"}
                                        ],
                                    },
                                ],
                            }
                        ]
                    },
                ]
            }
        },
        "A-1",
    )

    assert len(data.readings) == 3
    assert {reading.serial_number for reading in data.readings} == {"E1", "E2", "E3"}


def test_parse_deduplicates_to_latest_reading() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "gasMeterPoints": [
                            {
                                "mprn": "mprn-1",
                                "meters": [
                                    {
                                        "id": "gas-1",
                                        "serialNumber": "G1",
                                        "readings": [
                                            {
                                                "value": "10",
                                                "readAt": "2026-04-27T12:00:00+01:00",
                                                "registerId": "total",
                                            },
                                            {
                                                "value": "11",
                                                "readAt": "2026-04-28T12:00:00+01:00",
                                                "registerId": "total",
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

    assert len(data.readings) == 1
    assert data.readings[0].value == 11


def test_parse_daily_usage_when_enabled() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "mpan-1",
                                "meters": [
                                    {
                                        "id": "meter-1",
                                        "serialNumber": "E1",
                                        "consumptionUnits": "kWh",
                                        "consumption": {
                                            "edges": [
                                                {
                                                    "node": {
                                                        "consumption": 1100,
                                                        "isEstimate": False,
                                                    }
                                                },
                                                {
                                                    "node": {
                                                        "consumption": 1200,
                                                        "isEstimate": True,
                                                    }
                                                },
                                            ]
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        },
        "A-1",
        include_daily_usage=True,
    )

    assert len(data.daily_usages) == 1
    assert data.daily_usages[0].fuel == "electricity"
    assert data.daily_usages[0].value == 1200
    assert data.daily_usages[0].unit == "kWh"
    assert data.daily_usages[0].is_estimate is True


def test_parse_daily_usage_supports_period_fields() -> None:
    data = parse_account_data(
        {
            "account": {
                "properties": [
                    {
                        "gasMeterPoints": [
                            {
                                "mprn": "mprn-1",
                                "meters": [
                                    {
                                        "id": "gas-1",
                                        "serialNumber": "G1",
                                        "consumptionUnits": "m3",
                                        "consumption": {
                                            "edges": [
                                                {
                                                    "node": {
                                                        "value": "1.1",
                                                        "startAt": "2026-04-27T00:00:00+01:00",
                                                        "endAt": "2026-04-28T00:00:00+01:00",
                                                    }
                                                },
                                                {
                                                    "node": {
                                                        "value": "1.2",
                                                        "startAt": "2026-04-28T00:00:00+01:00",
                                                        "endAt": "2026-04-29T00:00:00+01:00",
                                                    }
                                                },
                                            ]
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ]
            }
        },
        "A-1",
        include_daily_usage=True,
    )

    assert len(data.daily_usages) == 1
    assert data.daily_usages[0].value == 1.2
    assert data.daily_usages[0].start_at == "2026-04-28T00:00:00+01:00"
    assert data.daily_usages[0].end_at == "2026-04-29T00:00:00+01:00"


def test_parse_metadata_when_enabled() -> None:
    data = parse_account_data(
        {
            "account": {
                "projectedBalance": 12345,
                "electricityAgreements": [
                    {
                        "id": "agreement-1",
                        "product": {
                            "displayName": "Electricity Fixed",
                            "code": "ELEC-FIXED",
                        },
                    }
                ],
                "gasAgreements": [
                    {
                        "id": "agreement-2",
                        "product": {
                            "fullName": "Gas Variable",
                            "code": "GAS-VAR",
                        },
                    }
                ],
            }
        },
        "A-1",
        include_metadata=True,
    )

    assert {item.name: item.value for item in data.metadata} == {
        "Electricity Tariff": "Electricity Fixed",
        "Gas Tariff": "Gas Variable",
        "Projected Balance": 123.45,
    }


def test_optional_phase_3_data_is_not_parsed_by_default() -> None:
    data = parse_account_data(
        {
            "account": {
                "projectedBalance": 12345,
                "electricityAgreements": [
                    {"product": {"displayName": "Electricity Fixed"}}
                ],
                "properties": [
                    {
                        "electricityMeterPoints": [
                            {
                                "mpan": "mpan-1",
                                "meters": [
                                    {
                                        "serialNumber": "E1",
                                        "consumption": {
                                            "edges": [
                                                {"node": {"consumption": 1200}}
                                            ]
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                ],
            }
        },
        "A-1",
    )

    assert data.daily_usages == ()
    assert data.metadata == ()


def test_token_payload_expiry_is_parsed() -> None:
    token = api._parse_token_payload(
        {
            "token": "access",
            "refreshToken": "refresh",
            "payload": {"exp": 1777392000},
        }
    )

    assert token.access_token == "access"
    assert token.refresh_token == "refresh"
    assert token.expires_at is not None
    assert token.expires_at.isoformat() == "2026-04-28T16:00:00+00:00"


def test_graphql_rate_limit_errors_are_classified() -> None:
    session = _FakeSession([{"errors": [{"message": "Query complexity limit exceeded"}]}])
    client = EdfKrakenApiClient(session, retries=0)

    try:
        asyncio.run(client._request("query", {}, authenticated=False))
    except EdfKrakenRateLimitError:
        pass
    else:
        raise AssertionError("Expected rate limit error")


def test_http_500_is_retried() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                status=500,
                payload={"errors": [{"message": "temporary"}]},
            ),
            {"data": {"viewer": {"accounts": [{"number": "A-1"}]}}},
        ]
    )
    client = EdfKrakenApiClient(session, retries=1, retry_backoff_seconds=0)

    result = asyncio.run(client._request("query", {}, authenticated=False))

    assert result["viewer"]["accounts"][0]["number"] == "A-1"
    assert session.calls == 2


def test_refresh_keeps_existing_refresh_token_when_not_returned() -> None:
    session = _FakeSession(
        [
            {
                "data": {
                    "obtainKrakenToken": {
                        "token": "new-access",
                        "payload": {"exp": 1777392000},
                    }
                }
            }
        ]
    )
    client = EdfKrakenApiClient(session, retries=0)
    client.set_refresh_token("old-refresh")

    token = asyncio.run(client.refresh_access_token())

    assert token.access_token == "new-access"
    assert token.refresh_token == "old-refresh"


class _FakeSession:
    def __init__(self, responses: list[dict | "_FakeResponse"]) -> None:
        self._responses = responses
        self.calls = 0

    async def post(self, *args, **kwargs) -> "_FakeResponse":
        response = self._responses[self.calls]
        self.calls += 1
        if isinstance(response, _FakeResponse):
            return response
        return _FakeResponse(status=200, payload=response)


class _FakeResponse:
    def __init__(self, *, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status >= 400:
            request_info = RequestInfo(
                url=URL("https://api.edfgb-kraken.energy/v1/graphql/"),
                method="POST",
                headers={},
                real_url=URL("https://api.edfgb-kraken.energy/v1/graphql/"),
            )
            raise ClientResponseError(
                request_info=request_info,
                history=(),
                status=self.status,
                message="error",
            )

    async def json(self) -> dict:
        return self._payload
