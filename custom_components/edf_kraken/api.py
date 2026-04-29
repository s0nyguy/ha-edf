"""EDF Kraken GraphQL API client and response normalization."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import DEFAULT_API_RETRIES, DEFAULT_API_RETRY_BACKOFF_SECONDS, GRAPHQL_URL

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
class DailyUsage:
    """Latest grouped daily usage for a meter."""

    unique_id: str
    account_number: str
    fuel: str
    name: str
    value: float
    unit: str
    start_at: str | None
    end_at: str | None
    is_estimate: bool | None
    meter_point_id: str | None
    meter_id: str | None
    serial_number: str | None


@dataclass(frozen=True, slots=True)
class AccountMetadata:
    """Optional account metadata exposed as sensors."""

    unique_id: str
    account_number: str
    name: str
    value: str | float
    unit: str | None = None
    device_class: str | None = None


@dataclass(frozen=True, slots=True)
class AccountData:
    """Normalized account topology and latest readings."""

    account_number: str
    readings: tuple[MeterReading, ...]
    daily_usages: tuple[DailyUsage, ...] = ()
    metadata: tuple[AccountMetadata, ...] = ()
    topology_error: str | None = None


class EdfKrakenApiClient:
    """Small GraphQL-first EDF Kraken API client."""

    def __init__(
        self,
        session: ClientSession,
        *,
        graphql_url: str = GRAPHQL_URL,
        retries: int = DEFAULT_API_RETRIES,
        retry_backoff_seconds: int = DEFAULT_API_RETRY_BACKOFF_SECONDS,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._graphql_url = graphql_url
        self._token: KrakenToken | None = None
        self._retries = retries
        self._retry_backoff_seconds = retry_backoff_seconds

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

    async def get_account_data(
        self,
        account_number: str | None = None,
        *,
        include_daily_usage: bool = False,
        include_metadata: bool = False,
        timezone: str = "Europe/London",
    ) -> AccountData:
        """Fetch and normalize account topology plus latest readings."""
        await self._ensure_access_token()
        if account_number is None:
            account_number = await self.get_first_account_number()

        try:
            payload = await self._request(
                ACCOUNT_TOPOLOGY_QUERY,
                {"accountNumber": account_number},
                authenticated=True,
            )
            account_data = parse_account_data(
                payload,
                account_number,
            )
        except EdfKrakenGraphQLError as err:
            LOGGER.warning(
                "EDF account topology query failed; setting up without readings: %s",
                err,
            )
            account_data = AccountData(
                account_number=account_number,
                readings=(),
                topology_error=str(err),
            )

        daily_usages: tuple[DailyUsage, ...] = ()
        if include_daily_usage:
            try:
                daily_usages = await self.get_daily_usage(account_number, timezone=timezone)
            except EdfKrakenError as err:
                LOGGER.warning("EDF optional daily usage query failed: %s", err)

        metadata: tuple[AccountMetadata, ...] = ()
        if include_metadata:
            try:
                metadata = await self.get_account_metadata(account_number)
            except EdfKrakenError as err:
                LOGGER.warning("EDF optional metadata query failed: %s", err)

        return AccountData(
            account_number=account_data.account_number,
            readings=account_data.readings,
            daily_usages=daily_usages,
            metadata=metadata,
            topology_error=account_data.topology_error,
        )

    async def get_daily_usage(
        self,
        account_number: str,
        *,
        timezone: str = "Europe/London",
    ) -> tuple[DailyUsage, ...]:
        """Fetch optional grouped daily usage data."""
        await self._ensure_access_token()
        payload = await self._request(
            DAILY_USAGE_QUERY,
            {
                "accountNumber": account_number,
                "usageStartAt": _daily_usage_start_at(timezone),
                "usageTimezone": timezone,
            },
            authenticated=True,
        )
        data = parse_account_data(payload, account_number, include_daily_usage=True)
        return data.daily_usages

    async def get_account_metadata(self, account_number: str) -> tuple[AccountMetadata, ...]:
        """Fetch optional account metadata."""
        await self._ensure_access_token()
        payload = await self._request(
            ACCOUNT_METADATA_QUERY,
            {"accountNumber": account_number},
            authenticated=True,
        )
        data = parse_account_data(payload, account_number, include_metadata=True)
        return data.metadata

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

        payload: dict[str, Any] | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._session.post(
                    self._graphql_url,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                response.raise_for_status()
                response_payload = await response.json()
            except ClientResponseError as err:
                if err.status in (401, 403):
                    raise EdfKrakenAuthError("EDF authentication failed") from err
                if err.status == 429:
                    if attempt < self._retries:
                        await self._async_retry_sleep(attempt)
                        continue
                    raise EdfKrakenRateLimitError("EDF rate limit exceeded") from err
                if err.status == 400:
                    error_message = await _response_error_message(response)
                    raise EdfKrakenGraphQLError(
                        error_message or "EDF rejected the GraphQL request"
                    ) from err
                if 500 <= err.status < 600 and attempt < self._retries:
                    await self._async_retry_sleep(attempt)
                    continue
                raise EdfKrakenError(f"EDF request failed with HTTP {err.status}") from err
            except ClientError as err:
                if attempt < self._retries:
                    await self._async_retry_sleep(attempt)
                    continue
                raise EdfKrakenError("EDF request failed") from err

            if not isinstance(response_payload, dict):
                raise EdfKrakenError("EDF returned an invalid response")
            payload = response_payload
            break

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

    async def _async_retry_sleep(self, attempt: int) -> None:
        """Sleep before retrying a transient request failure."""
        await asyncio.sleep(self._retry_backoff_seconds * (2**attempt))


async def _response_error_message(response: Any) -> str | None:
    """Extract a useful error message from an HTTP error response."""
    message: str | None = None
    try:
        payload = await response.json()
    except (ClientError, ValueError, TypeError):
        payload = None
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            messages = [
                _coerce_str(error.get("message")) for error in errors if isinstance(error, dict)
            ]
            message = "; ".join(item for item in messages if item) or None
    if message:
        return message

    try:
        text = await response.text()
    except (ClientError, ValueError, TypeError, AttributeError):
        return None
    text = text.strip()
    return text[:500] or None


def parse_account_data(
    payload: dict[str, Any],
    account_number: str,
    *,
    include_daily_usage: bool = False,
    include_metadata: bool = False,
) -> AccountData:
    """Normalize latest cumulative readings from an EDF account payload."""
    account = payload.get("account")
    if not isinstance(account, dict):
        raise EdfKrakenError("EDF account payload is missing")

    readings: list[MeterReading] = []
    readings.extend(_extract_fuel_readings(account, account_number, "electricity"))
    readings.extend(_extract_fuel_readings(account, account_number, "gas"))

    daily_usages: list[DailyUsage] = []
    if include_daily_usage:
        daily_usages.extend(_extract_daily_usages(account, account_number, "electricity"))
        daily_usages.extend(_extract_daily_usages(account, account_number, "gas"))

    metadata: list[AccountMetadata] = []
    if include_metadata:
        metadata.extend(_extract_account_metadata(account, account_number))

    return AccountData(
        account_number=account_number,
        readings=tuple(_dedupe_readings(readings)),
        daily_usages=tuple(_dedupe_daily_usages(daily_usages)),
        metadata=tuple(_dedupe_metadata(metadata)),
    )


def _extract_fuel_readings(
    account: dict[str, Any],
    account_number: str,
    fuel: str,
) -> list[MeterReading]:
    meter_points = _find_all_lists_by_name(account, f"{fuel}MeterPoints")
    if not meter_points:
        meter_points = _find_all_lists_by_fragment(account, f"{fuel}meterpoint")

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
        meters = _find_all_lists_by_name(meter_point, "meters")
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
    candidates = _find_all_lists_by_name(meter, "readings")
    if not candidates:
        candidates = _find_all_lists_by_fragment(meter, "meterreading")
    candidates.extend(_find_all_lists_by_name(meter, "unbilledReadings"))

    readings: list[MeterReading] = []
    for reading in candidates:
        if not isinstance(reading, dict):
            continue
        registers = _find_all_lists_by_name(reading, "registers")
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


def _dedupe_readings(readings: list[MeterReading]) -> list[MeterReading]:
    """Return one reading per unique sensor, preferring the newest timestamp."""
    deduped: dict[str, MeterReading] = {}
    for reading in readings:
        existing = deduped.get(reading.unique_id)
        if existing is None or _read_at_sort_key(reading) >= _read_at_sort_key(existing):
            deduped[reading.unique_id] = reading
    return list(deduped.values())


def _read_at_sort_key(reading: MeterReading) -> datetime:
    if not reading.read_at:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(reading.read_at.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_daily_usages(
    account: dict[str, Any],
    account_number: str,
    fuel: str,
) -> list[DailyUsage]:
    meter_points = _find_all_lists_by_name(account, f"{fuel}MeterPoints")
    if not meter_points:
        meter_points = _find_all_lists_by_fragment(account, f"{fuel}meterpoint")

    daily_usages: list[DailyUsage] = []
    for meter_point in meter_points:
        if not isinstance(meter_point, dict):
            continue
        meter_point_id = _first_present_str(
            meter_point,
            "mpan" if fuel == "electricity" else "mprn",
            "meterPointId",
            "id",
        )
        meters = _find_all_lists_by_name(meter_point, "meters")
        if not meters:
            meters = [meter_point]
        for meter in meters:
            if isinstance(meter, dict):
                daily_usages.extend(
                    _extract_meter_daily_usages(
                        account_number,
                        fuel,
                        meter_point_id,
                        meter,
                    )
                )
    return daily_usages


def _extract_meter_daily_usages(
    account_number: str,
    fuel: str,
    meter_point_id: str | None,
    meter: dict[str, Any],
) -> list[DailyUsage]:
    meter_id = _first_present_str(meter, "id", "meterId")
    serial_number = _first_present_str(meter, "serialNumber", "meterSerialNumber")
    unit = _normalise_unit(_first_present_str(meter, "consumptionUnits", "unit"), fuel)
    candidates = _find_all_lists_by_name(meter, "consumption")

    daily_usages: list[DailyUsage] = []
    for node in candidates:
        if not isinstance(node, dict):
            continue
        value = _first_present_float(node, "value", "consumption", "quantity")
        if value is None:
            continue
        start_at = _first_present_str(node, "startAt", "startDate")
        end_at = _first_present_str(node, "endAt", "endDate")
        is_estimate = node.get("isEstimate")
        identity_parts = [account_number, fuel, meter_point_id, meter_id, serial_number, "daily_usage"]
        unique_id = "_".join(_slugify(part) for part in identity_parts if part)
        if not unique_id:
            continue
        daily_usages.append(
            DailyUsage(
                unique_id=unique_id,
                account_number=account_number,
                fuel=fuel,
                name=f"{fuel.title()} Daily Usage",
                value=value,
                unit=unit,
                start_at=start_at,
                end_at=end_at,
                is_estimate=is_estimate if isinstance(is_estimate, bool) else None,
                meter_point_id=meter_point_id,
                meter_id=meter_id,
                serial_number=serial_number,
            )
        )
    return daily_usages


def _dedupe_daily_usages(daily_usages: list[DailyUsage]) -> list[DailyUsage]:
    deduped: dict[str, DailyUsage] = {}
    for usage in daily_usages:
        existing = deduped.get(usage.unique_id)
        if existing is None or _usage_sort_key(usage) >= _usage_sort_key(existing):
            deduped[usage.unique_id] = usage
    return list(deduped.values())


def _usage_sort_key(usage: DailyUsage) -> datetime:
    for value in (usage.end_at, usage.start_at):
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return datetime.min.replace(tzinfo=UTC)


def _extract_account_metadata(
    account: dict[str, Any],
    account_number: str,
) -> list[AccountMetadata]:
    metadata: list[AccountMetadata] = []
    metadata.extend(_extract_agreement_metadata(account, account_number, "electricity"))
    metadata.extend(_extract_agreement_metadata(account, account_number, "gas"))

    projected_balance = _first_present_float(account, "projectedBalance")
    if projected_balance is not None:
        metadata.append(
            AccountMetadata(
                unique_id=_slugify(f"{account_number}_projected_balance"),
                account_number=account_number,
                name="Projected Balance",
                value=projected_balance / 100,
                unit="GBP",
                device_class="monetary",
            )
        )
    return metadata


def _extract_agreement_metadata(
    account: dict[str, Any],
    account_number: str,
    fuel: str,
) -> list[AccountMetadata]:
    agreements = _find_all_lists_by_name(account, f"{fuel}Agreements")
    metadata: list[AccountMetadata] = []
    for agreement in agreements:
        if not isinstance(agreement, dict):
            continue
        product = agreement.get("product")
        if not isinstance(product, dict):
            continue
        product_name = _first_present_str(product, "displayName", "fullName", "code")
        if not product_name:
            continue
        metadata.append(
            AccountMetadata(
                unique_id=_slugify(f"{account_number}_{fuel}_tariff"),
                account_number=account_number,
                name=f"{fuel.title()} Tariff",
                value=product_name,
            )
        )
        break
    return metadata


def _dedupe_metadata(metadata: list[AccountMetadata]) -> list[AccountMetadata]:
    deduped: dict[str, AccountMetadata] = {}
    for item in metadata:
        deduped[item.unique_id] = item
    return list(deduped.values())


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
    return _parse_datetime(value)


def _parse_datetime(value: str | None) -> datetime | None:
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
    return _find_all_lists_by_name(payload, key)


def _find_all_lists_by_name(payload: Any, key: str) -> list[Any]:
    found_lists: list[Any] = []
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list):
            found_lists.extend(value)
        if isinstance(value, dict):
            nodes = value.get("nodes")
            if isinstance(nodes, list):
                found_lists.extend(nodes)
            edges = value.get("edges")
            if isinstance(edges, list):
                found_lists.extend(
                    [
                        edge["node"]
                        for edge in edges
                        if isinstance(edge, dict) and "node" in edge
                    ]
                )
        for child in payload.values():
            found = _find_all_lists_by_name(child, key)
            if found:
                found_lists.extend(found)
    elif isinstance(payload, list):
        for child in payload:
            found = _find_all_lists_by_name(child, key)
            if found:
                found_lists.extend(found)
    return found_lists


def _find_lists_by_fragment(payload: Any, key_fragment: str) -> list[Any]:
    return _find_all_lists_by_fragment(payload, key_fragment)


def _find_all_lists_by_fragment(payload: Any, key_fragment: str) -> list[Any]:
    found_lists: list[Any] = []
    lowered_fragment = key_fragment.lower()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if lowered_fragment in key.lower():
                if isinstance(value, list):
                    found_lists.extend(value)
                if isinstance(value, dict):
                    nodes = value.get("nodes")
                    if isinstance(nodes, list):
                        found_lists.extend(nodes)
                    edges = value.get("edges")
                    if isinstance(edges, list):
                        found_lists.extend(
                            [
                                edge["node"]
                                for edge in edges
                                if isinstance(edge, dict) and "node" in edge
                            ]
                        )
            found = _find_all_lists_by_fragment(value, key_fragment)
            if found:
                found_lists.extend(found)
    elif isinstance(payload, list):
        for child in payload:
            found = _find_all_lists_by_fragment(child, key_fragment)
            if found:
                found_lists.extend(found)
    return found_lists


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


def _daily_usage_start_at(timezone: str) -> str:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = UTC
    today = datetime.now(zone).date()
    start_date = today - timedelta(days=3)
    return datetime.combine(start_date, time.min, tzinfo=zone).isoformat()


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
        id
        mpan
        meters(includeInactive: true) {
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
        id
        mprn
        meters(includeInactive: true) {
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

DAILY_USAGE_QUERY = """
query AccountDailyUsage(
  $accountNumber: String!
  $usageStartAt: DateTime!
  $usageTimezone: String!
) {
  account(accountNumber: $accountNumber) {
    number
    properties {
      id
      electricityMeterPoints {
        id
        mpan
        meters(includeInactive: true) {
          id
          serialNumber
          consumptionUnits
          consumption(first: 3, grouping: DAY, startAt: $usageStartAt, timezone: $usageTimezone) {
            edges {
              node {
                consumption
                isEstimate
              }
            }
          }
        }
      }
      gasMeterPoints {
        id
        mprn
        meters(includeInactive: true) {
          id
          serialNumber
          consumptionUnits
          consumption(first: 3, grouping: DAY, startAt: $usageStartAt, timezone: $usageTimezone) {
            edges {
              node {
                consumption
                isEstimate
              }
            }
          }
        }
      }
    }
  }
}
"""

ACCOUNT_METADATA_QUERY = """
query AccountMetadata($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    number
    projectedBalance
    properties {
      id
      electricityMeterPoints {
        id
        mpan
        electricityAgreements: agreements {
          id
          validFrom
          validTo
          product {
            code
            displayName
            fullName
          }
        }
      }
      gasMeterPoints {
        id
        mprn
        gasAgreements: agreements {
          id
          validFrom
          validTo
          product {
            code
            displayName
            fullName
          }
        }
      }
    }
  }
}
"""
