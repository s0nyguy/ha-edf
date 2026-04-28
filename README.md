# EDF Kraken Home Assistant Integration

Custom Home Assistant integration for read-only EDF Kraken account and meter readings.

## Current scope

- UI config flow using EDF email and password.
- GraphQL authentication and refresh-token persistence.
- Runtime access-token refresh.
- Account discovery through `viewer`.
- Conservative polling through `DataUpdateCoordinator`.
- Cumulative electricity and gas meter reading sensors for Energy Dashboard use.
- Defensive parsing for electricity-only, gas-only, dual-fuel, multi-meter, and multi-register accounts.

Daily usage, tariff/account metadata, and REST-backed endpoints are intentionally disabled by default and should be added only after real-account validation.

## Install

Copy `custom_components/edf_kraken` into a Home Assistant `custom_components` directory, restart Home Assistant, then add the integration from the UI.
