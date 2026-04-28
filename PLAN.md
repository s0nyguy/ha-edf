# EDF Kraken Home Assistant Integration: Phased Plan

## Summary
Build the integration in phases, starting with a read-only MVP that proves EDF login, account discovery, and Energy Dashboard-compatible cumulative sensors. Later phases add richer usage data, account/tariff metadata, resilience, diagnostics, and optional REST-backed features only if real-account testing shows value.

## Phase 1: MVP Read-Only Integration
- Create a Home Assistant custom integration with domain `edf_kraken`.
- Add the standard integration structure:
  - `manifest.json`
  - `__init__.py`
  - `const.py`
  - `config_flow.py`
  - `api.py`
  - `coordinator.py`
  - `sensor.py`
  - `strings.json`
- Implement config flow using EDF email/password.
- Authenticate via GraphQL `obtainKrakenToken`.
- Store only the refresh token in the config entry.
- Keep short-lived access tokens in memory and refresh them as needed.
- Query `viewer` to discover the customer account number.
- Discover basic electricity and gas meter topology for the account.
- Add cumulative sensors only:
  - Electricity import total in `kWh`, `device_class=energy`, `state_class=total_increasing`.
  - Gas total using EDF’s returned unit, preferring `kWh` if available, otherwise volume such as `m3`.
- Use `DataUpdateCoordinator` for all polling.
- Poll conservatively, defaulting to 60 minutes.
- Handle GraphQL `errors` responses even when HTTP status is 200.
- Support electricity-only, gas-only, and dual-fuel accounts.
- MVP success criteria:
  - User can add the integration from the UI.
  - Integration survives Home Assistant restart.
  - Latest cumulative readings match EDF portal/app values.
  - Created energy sensors are accepted by the Home Assistant Energy Dashboard.

## Phase 2: Robustness And Account Coverage
- Add full token refresh handling with Home Assistant reauth when refresh fails.
- Improve meter discovery for:
  - Multiple meters.
  - Multi-register electricity meters such as Economy 7.
  - Meter replacements or changed register identifiers.
  - Non-smart meters with only manual readings.
- Add stable unique IDs based on account, meter point, meter, and register identifiers.
- Add defensive parsing for missing fields, protected fields, disabled fields, and unavailable consumption data.
- Add retry/backoff behavior for rate limits, hourly point exhaustion, and transient API failures.
- Add unit tests using fixtures for:
  - Auth success/failure.
  - Refresh success/failure.
  - GraphQL errors.
  - Electricity-only account.
  - Gas-only account.
  - Dual-fuel account.
  - Multi-register electricity meter.
  - Missing smart consumption data.

## Phase 3: Usage And Metadata Sensors
- Add optional daily usage sensors where EDF GraphQL consumption data is available:
  - Daily electricity usage.
  - Daily gas usage.
- Add latest reading timestamp sensors for electricity and gas.
- Add account/tariff metadata sensors:
  - Active electricity product/tariff name.
  - Active gas product/tariff name.
  - Account balance if the API exposes it reliably.
- Keep cumulative register sensors as the primary Energy Dashboard path.
- Avoid high-complexity GraphQL queries by splitting topology, readings, and usage polling.
- Add options flow controls for:
  - Polling interval.
  - Enable/disable daily usage sensors.
  - Enable/disable account metadata sensors.

## Phase 4: Diagnostics, Repairs, And UX Polish
- Add Home Assistant diagnostics with sensitive values redacted.
- Add integration repairs for common account states:
  - Authentication expired.
  - No meters discovered.
  - Smart consumption unavailable.
  - Rate limit or hourly point exhaustion.
- Improve config-flow and reauth messages in `strings.json`.
- Add clear device grouping:
  - Account-level device for account metadata.
  - Meter-point or meter-level devices for electricity and gas sensors.
- Add manual validation checklist documentation for real EDF accounts.
- Confirm behavior across Home Assistant restart, reload, and reauth.

## Phase 5: Optional Advanced Features
- Investigate REST only after GraphQL MVP validation.
- Add REST calls only for specific proven gaps, not as a parallel API layer.
- Consider smart meter consent/status sensors using:
  - `smartMeterDataPreferences`
  - `updateSmartMeterDataPreferences` only if write behavior is explicitly desired later.
- Consider hourly usage sensors if API limits and Home Assistant performance are acceptable.
- Consider services for manually requesting consumption refresh via `requestConsumptionData`, but keep the default integration read-only unless a later requirement changes that.

## Public Interfaces And Data Model
- Public integration domain: `edf_kraken`.
- Config entry data:
  - EDF account identifier.
  - Refresh token.
- Runtime-only data:
  - Access token.
  - Token expiry.
  - Discovered account/meter topology.
- Entity identity:
  - Unique IDs should be stable and derived from EDF account number plus meter point, meter, register, or fuel identifiers.
- No YAML configuration for the initial version; UI config flow only.
- No write operations in MVP.

## Test Plan
- Unit tests for API client auth, token refresh, GraphQL error parsing, pagination helpers, and response normalization.
- Unit tests for coordinator behavior when partial account data is missing.
- Entity tests for names, unique IDs, units, device classes, and state classes.
- Fixture-based tests for electricity-only, gas-only, dual-fuel, multi-register, no-consumption, and meter-replacement scenarios.
- Manual tests with a real EDF account to verify readings, restart persistence, reauth, Energy Dashboard compatibility, and API limit behavior.

## Assumptions
- The initial integration is read-only.
- GraphQL is the primary API.
- REST is deferred until a specific REST endpoint is proven useful.
- The MVP prioritizes cumulative register readings over daily/hourly consumption.
- Real-account validation is required before treating field availability as stable.
- Polling starts at 60 minutes to reduce risk of complexity and hourly point limits.
