"""EDF Kraken GraphQL API client and response normalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import GRAPHQL_URL

LOGGER = logging.getLogger(__name__)


class EdfKrakenError(Exception):
    """Base EDF Kraken error."""


class EdfKrakenAuthError(EdfKrakenError):
    """Raised when authentication or token refresh fails."""


class EdfKrakenGraphQLError(EdfKrakenError):
    """Raised when GraphQL returns an errors payload."""


class EdfKrakenRateLimitError(EdfKrakenError):
    """Raised when the API rate limits or exhausts the point allowance."""


@dataclass(slots=True)
class KrakenToken:
    """Runtime token bundle."""

    access_token: str
    refresh_token: str
    expires_at: datetime | None = None

    @property
    def needs_refresh(self) -> bool:
        """Return true when the access token should be refreshed."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) + timedelta(minutes=5) >= self.expires_at


@dataclass(frozen=True, slots=True)
class MeterReading:
    """Latest cumulative meter register reading."""

    unique_id: str
    account_number: str
    fuel: str
    name: str
    value: float
    unit: str
    read_at: str | None
    meter_point_id: str | None
    meter_id: str | None
    register_id: str | None
    serial_number: str | None


@dataclass(frozen=True, slots=True)
class AccountData:
    """Normalized account topology and latest readings."""

    account_number: str
    readings: tuple[MeterReading, ...]


class EdfKrakenApiClient:
    """Small GraphQL-first EDF Kraken API client."""

    def __init__(
        self,
        session: ClientSession,
        *,
        graphql_url: str = GRAPHQL_URL,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._graphql_url = graphql_url
        self._token: KrakenToken | None = None

    @property
    def refresh_token(self) -> str | None:
        """Return the latest refresh token."""
        return self._token.refresh_token if self._token else None

    def set_refresh_token(self, refresh_token: str) -> None:
        """Seed the client with a persisted refresh token."""
        self._token = KrakenToken(access_token="", refresh_token=refresh_token)

    async def authenticate(self, email: str, password: str) -> KrakenToken:
        """Authenticate with EDF credentials."""
        payload = await self._request(
            OBTAIN_TOKEN_MUTATION,
            {"input": {"email": email, "password": password}},
            authenticated=False,
        )
        token_payload = _find_first_mapping(payload, "obtainKrakenToken")
        if not token_payload:
            raise EdfKrakenAuthError("EDF did not return a token payload")

        token = _parse_token_payload(token_payload)
        if not token.access_token or not token.refresh_token:
            raise EdfKrakenAuthError("EDF returned an incomplete token payload")

        self._token = token
        return token

    async def refresh_access_token(self) -> KrakenToken:
        """Refresh the short-lived access token."""
        if self._token is None or not self._token.refresh_token:
            raise EdfKrakenAuthError("No refresh token is available")

        payload = await self._request(
            OBTAIN_TOKEN_MUTATION,
            {"input": {"refreshToken": self._token.refresh_token}},
            authenticated=False,
        )
        token_payload = _find_first_mapping(payload, "obtainKrakenToken")
        if not token_payload:
            raise EdfKrakenAuthError("EDF did not return a refreshed token")

        token = _parse_token_payload(token_payload)
        if not token.refresh_token:
            token = KrakenToken(
                access_token=token.access_token,
                refresh_token=self._token.refresh_token,
                expires_at=token.expires_at,
            )
        if not token.access_token:
            raise EdfKrakenAuthError("EDF returned an incomplete refreshed token")

        self._token = token
        return token

    async def get_account_data(self, account_number: str | None = None) -> AccountData:
        """Fetch and normalize account topology plus latest readings."""
        await self._ensure_access_token()
        if account_number is None:
            account_number = await self.get_first_account_number()

        payload = await self._request(
            ACCOUNT_TOPOLOGY_QUERY,
            {"accountNumber": account_number},
            authenticated=True,
        )
        return parse_account_data(payload, account_number)

    async def get_first_account_number(self) -> str:
        """Return the first account number visible to the authenticated user."""
        await self._ensure_access_token()
        payload = await self._request(VIEWER_QUERY, {}, authenticated=True)
        accounts = _extract_viewer_accounts(payload)
        if not accounts:
            raise EdfKrakenError("No EDF accounts were found for this user")
        account_number = _coerce_str(accounts[0].get("number"))
        if not account_number:
            raise EdfKrakenError("EDF account is missing an account number")
        return account_number

    async def _ensure_access_token(self) -> None:
        """Refresh the token when needed."""
        if self._token is None:
            raise EdfKrakenAuthError("No token is available")
        if not self._token.access_token or self._token.needs_refresh:
            await self.refresh_access_token()

    async def _request(
        self,
        query: str,
        variables: dict[str, Any],
        *,
        authenticated: bool,
    ) -> dict[str, Any]:
        """Execute a GraphQL request and validate the response envelope."""
        headers = {"Content-Type": "application/json"}
        if authenticated:
            if self._token is None or not self._token.access_token:
                raise EdfKrakenAuthError("No access token is available")
            headers["Authorization"] = f"JWT {self._token.access_token}"

        try:
            response = await self._session.post(
                self._graphql_url,
                json={"query": query, "variables": variables},
                headers=headers,
            )
            response.raise_for_status()
            payload = await response.json()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise EdfKrakenAuthError("EDF authentication failed") from err
            if err.status == 429:
                raise EdfKrakenRateLimitError("EDF rate limit exceeded") from err
            raise EdfKrakenError(f"EDF request failed with HTTP {err.status}") from err
        except ClientError as err:
            raise EdfKrakenError("EDF request failed") from err

        if not isinstance(payload, dict):
            raise EdfKrakenError("EDF returned an invalid response")

        errors = payload.get("errors")
        if errors:
            messages = [_coerce_str(error.get("message")) for error in errors if isinstance(error, dict)]
            joined = "; ".join(message for message in messages if message)
            lowered = joined.lower()
            if "rate" in lowered or "point" in lowered or "complexity" in lowered:
                raise EdfKrakenRateLimitError(joined or "EDF GraphQL allowance exceeded")
            if "auth" in lowered or "permission" in lowered or "credential" in lowered:
                raise EdfKrakenAuthError(joined or "EDF authentication failed")
            raise EdfKrakenGraphQLError(joined or "EDF returned GraphQL errors")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise EdfKrakenError("EDF returned no GraphQL data")
        return data


def parse_account_data(payload: dict[str, Any], account_number: str) -> AccountData:
    """Normalize latest cumulative readings from an EDF account payload."""
    account = payload.get("account")
    if not isinstance(account, dict):
        raise EdfKrakenError("EDF account payload is missing")

    readings: list[MeterReading] = []
    readings.extend(_extract_fuel_readings(account, account_number, "electricity"))
    readings.extend(_extract_fuel_readings(account, account_number, "gas"))
    return AccountData(account_number=account_number, readings=tuple(readings))


def _extract_fuel_readings(
    account: dict[str, Any],
    account_number: str,
    fuel: str,
) -> list[MeterReading]:
    meter_points = _find_lists_by_name(account, f"{fuel}MeterPoints")
    if not meter_points:
        meter_points = _find_lists_by_fragment(account, f"{fuel}meterpoint")

    readings: list[MeterReading] = []
    for meter_point in meter_points:
        if not isinstance(meter_point, dict):
            continue
        meter_point_id = _first_present_str(
            meter_point,
            "mpan" if fuel == "electricity" else "mprn",
            "meterPointId",
            "id",
        )
        meters = _find_lists_by_name(meter_point, "meters")
        if not meters:
            meters = [meter_point]
        for meter in meters:
            if isinstance(meter, dict):
                readings.extend(
                    _extract_meter_readings(
                        account_number,
                        fuel,
                        meter_point_id,
                        meter,
                    )
                )
    return readings


def _extract_meter_readings(
    account_number: str,
    fuel: str,
    meter_point_id: str | None,
    meter: dict[str, Any],
) -> list[MeterReading]:
    meter_id = _first_present_str(meter, "id", "meterId")
    serial_number = _first_present_str(meter, "serialNumber", "meterSerialNumber")
    candidates = _find_lists_by_name(meter, "readings")
    if not candidates:
        candidates = _find_lists_by_fragment(meter, "meterreading")

    readings: list[MeterReading] = []
    for reading in candidates:
        if not isinstance(reading, dict):
            continue
        registers = _find_lists_by_name(reading, "registers")
        if registers:
            for register in registers:
                if not isinstance(register, dict):
                    continue
                readings.extend(
                    _build_meter_reading(
                        account_number,
                        fuel,
                        meter_point_id,
                        meter_id,
                        serial_number,
                        {**reading, **register},
                    )
                )
            continue
        readings.extend(
            _build_meter_reading(
                account_number,
                fuel,
                meter_point_id,
                meter_id,
                serial_number,
                reading,
            )
        )
    return readings


def _build_meter_reading(
    account_number: str,
    fuel: str,
    meter_point_id: str | None,
    meter_id: str | None,
    serial_number: str | None,
    reading: dict[str, Any],
) -> list[MeterReading]:
    """Build a normalized reading from either a reading node or register node."""
    readings: list[MeterReading] = []
    value = _first_present_float(
        reading,
        "value",
        "reading",
        "cumulative",
        "cumulativeConsumption",
        "decimalValue",
    )
    if value is None:
        return readings
    unit = _normalise_unit(_first_present_str(reading, "unit", "units", "readingUnit"), fuel)
    read_at = _first_present_str(reading, "readAt", "readOn", "createdAt", "timestamp")
    register_id = _first_present_str(
        reading,
        "registerId",
        "registerIdentifier",
        "identifier",
        "register",
        "id",
    )
    label = _first_present_str(reading, "registerLabel", "label", "name", "identifier") or "Total"

    identity_parts = [
        account_number,
        fuel,
        meter_point_id,
        meter_id,
        serial_number,
        register_id,
        label,
    ]
    unique_id = "_".join(_slugify(part) for part in identity_parts if part)
    if not unique_id:
        return readings

    readings.append(
        MeterReading(
            unique_id=unique_id,
            account_number=account_number,
            fuel=fuel,
            name=f"{fuel.title()} {label}",
            value=value,
            unit=unit,
            read_at=read_at,
            meter_point_id=meter_point_id,
            meter_id=meter_id,
            register_id=register_id,
            serial_number=serial_number,
        )
    )
    return readings


def _parse_token_payload(payload: dict[str, Any]) -> KrakenToken:
    access_token = _first_present_str(payload, "token", "accessToken", "access_token", "jwt") or ""
    refresh_token = _first_present_str(payload, "refreshToken", "refresh_token") or ""
    expires_in = _first_present_float(payload, "expiresIn", "expires_in")
    expires_at_raw = _first_present_str(payload, "expiresAt", "expires_at", "expiry")
    expires_at = _parse_expires_at(expires_at_raw)
    jwt_payload = payload.get("payload")
    if expires_at is None and isinstance(jwt_payload, dict):
        exp = _first_present_float(jwt_payload, "exp")
        if exp is not None:
            expires_at = datetime.fromtimestamp(exp, UTC)
    if expires_at is None and expires_in:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    return KrakenToken(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)


def _parse_expires_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_viewer_accounts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    viewer = payload.get("viewer")
    if not isinstance(viewer, dict):
        return []
    accounts = viewer.get("accounts")
    if isinstance(accounts, list):
        return [account for account in accounts if isinstance(account, dict)]
    if isinstance(accounts, dict):
        nodes = accounts.get("nodes")
        if isinstance(nodes, list):
            return [account for account in nodes if isinstance(account, dict)]
        edges = accounts.get("edges")
        if isinstance(edges, list):
            return [
                edge["node"]
                for edge in edges
                if isinstance(edge, dict) and isinstance(edge.get("node"), dict)
            ]
    return []


def _find_first_mapping(payload: Any, key: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
        for child in payload.values():
            found = _find_first_mapping(child, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = _find_first_mapping(child, key)
            if found is not None:
                return found
    return None


def _find_lists_by_name(payload: Any, key: str) -> list[Any]:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nodes = value.get("nodes")
            if isinstance(nodes, list):
                return nodes
            edges = value.get("edges")
            if isinstance(edges, list):
                return [
                    edge["node"]
                    for edge in edges
                    if isinstance(edge, dict) and "node" in edge
                ]
        for child in payload.values():
            found = _find_lists_by_name(child, key)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = _find_lists_by_name(child, key)
            if found:
                return found
    return []


def _find_lists_by_fragment(payload: Any, key_fragment: str) -> list[Any]:
    lowered_fragment = key_fragment.lower()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if lowered_fragment in key.lower():
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    nodes = value.get("nodes")
                    if isinstance(nodes, list):
                        return nodes
            found = _find_lists_by_fragment(value, key_fragment)
            if found:
                return found
    elif isinstance(payload, list):
        for child in payload:
            found = _find_lists_by_fragment(child, key_fragment)
            if found:
                return found
    return []


def _first_present_str(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        text = _coerce_str(value)
        if text:
            return text
    return None


def _first_present_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _first_present_float(value, "value", "amount")
            if nested is not None:
                return nested
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise_unit(unit: str | None, fuel: str) -> str:
    if not unit:
        return "kWh" if fuel == "electricity" else "m3"
    lowered = unit.lower()
    if lowered in {"kwh", "kilowatt_hour", "kilowatt-hours", "kilowatt hours"}:
        return "kWh"
    if lowered in {"m3", "m^3", "cubic_metres", "cubic meters", "cubic metres"}:
        return "m3"
    return unit


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


OBTAIN_TOKEN_MUTATION = """
mutation ObtainKrakenToken($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    token
    payload
    refreshToken
    refreshExpiresIn
  }
}
"""

VIEWER_QUERY = """
query ViewerAccounts {
  viewer {
    accounts {
      number
    }
  }
}
"""

ACCOUNT_TOPOLOGY_QUERY = """
query AccountTopology($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    properties {
      id
      electricityMeterPoints {
        mpan
        meters {
          id
          serialNumber
          readings(first: 10) {
            edges {
              node {
                id
                readAt
                readingSource
                readingType
                registers {
                  id
                  identifier
                  value
                }
              }
            }
          }
        }
      }
      gasMeterPoints {
        mprn
        meters {
          id
          serialNumber
          readings(first: 10) {
            edges {
              node {
                id
                readAt
                readingSource
                readingType
                registers {
                  id
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
"""
