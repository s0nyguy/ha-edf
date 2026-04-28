# EDF Kraken Home Assistant Integration

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=s0nyguy&repository=ha-edf&category=integration)

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
- Home Assistant repair issues for authentication failure, rate limits, no readings, and unavailable optional data.
- Manual validation checklist in `docs/manual_validation.md`.

Daily usage, tariff/account metadata, and REST-backed endpoints are intentionally disabled by default and should be added only after real-account validation.

## Install

### HACS

Open HACS repository on my Home Assistant:

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=s0nyguy&repository=ha-edf&category=integration)

Or add it manually:

1. Install [HACS](https://hacs.xyz/) if it is not already installed.
2. Open HACS in Home Assistant.
3. Open the three-dot menu and choose **Custom repositories**.
4. Add `https://github.com/s0nyguy/ha-edf` as an **Integration** repository.
5. Search for **EDF Kraken** in HACS.
6. Download the integration.
7. Restart Home Assistant.
8. Go to **Settings** -> **Devices & services** -> **Add integration**.
9. Search for **EDF Kraken** and sign in with your EDF credentials.

### Manual

Copy `custom_components/edf_kraken` into your Home Assistant `custom_components` directory, restart Home Assistant, then add **EDF Kraken** from the integrations UI.

Full setup instructions are in [docs/installation.md](docs/installation.md).
