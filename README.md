# EDF Kraken Home Assistant Integration

Custom Home Assistant integration for read-only EDF Kraken account and meter readings.

## Current scope

- UI config flow using EDF email and password.
- GraphQL authentication and refresh-token persistence.
- Runtime access-token refresh.
- Account discovery through `viewer`.
- Conservative polling through `DataUpdateCoordinator`.
- Cumulative electricity and gas meter reading sensors for Energy Dashboard use.
- Latest reading timestamp sensors for each cumulative reading sensor.
- Defensive parsing for electricity-only, gas-only, dual-fuel, multi-property, multi-meter, and multi-register accounts.
- Stable unique IDs derived from account, fuel, meter point, meter, serial, and register identifiers.
- Bounded retry/backoff handling for transient HTTP failures and rate-limit responses.
- Reauth signaling when token refresh fails.
- Optional daily usage sensors, disabled by default pending real-account validation.
- Optional tariff and projected-balance metadata sensors, disabled by default pending real-account validation.

Daily usage, tariff/account metadata, and REST-backed endpoints are intentionally disabled by default and should be added only after real-account validation.

## Install

Copy `custom_components/edf_kraken` into a Home Assistant `custom_components` directory, restart Home Assistant, then add the integration from the UI.
