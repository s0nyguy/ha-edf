# EDF Kraken Home Assistant Integration Plan

## Feasibility Summary

Creating a Home Assistant integration for EDF electricity and gas usage appears possible using EDF's Kraken API.

The best route is GraphQL-first:

- GraphQL endpoint: `https://api.edfgb-kraken.energy/v1/graphql/`
- REST base URL: `https://api.edfgb-kraken.energy/v1/`
- Authentication is available through GraphQL `obtainKrakenToken`.
- The same token can authenticate both GraphQL and REST requests.
- Authenticated user discovery is available through `viewer`.
- Account and meter data are available through `account`, meter point, meter, reading, and consumption fields.

REST is documented, but the useful customer usage and meter surfaces are clearer in GraphQL. The integration should use GraphQL as the primary API and only add REST calls later if real-account testing shows a better protected REST endpoint.

## Relevant API Surfaces

Authentication and account discovery:

- `obtainKrakenToken`
- `viewer`
- `account`

Meter readings:

- `electricityMeterReadings`
- `gasMeterReadings`
- `ElectricityMeterType.readings`
- `GasMeterType.readings`

Smart meter consumption:

- `ElectricityMeterType.consumption(...)`
- `GasMeterType.consumption(...)`
- `smartMeterTelemetry(...)`
- `requestConsumptionData`

Preferences and consent:

- `smartMeterDataPreferences`
- `updateSmartMeterDataPreferences`

Important API constraints:

- GraphQL requests use HTTPS at `https://api.edfgb-kraken.energy/v1/graphql/`.
- GraphQL may return HTTP 200 even when the response contains errors.
- Queries have complexity limits.
- Authenticated users have hourly points allowances.
- Paginated fields require cursor pagination and `first` values under 100.
- Datetime parameters should use ISO 8601 with explicit timezone information.

## Home Assistant Integration Design

Create a custom integration with domain `edf_kraken`.

Suggested files:

- `custom_components/edf_kraken/manifest.json`
- `custom_components/edf_kraken/__init__.py`
- `custom_components/edf_kraken/config_flow.py`
- `custom_components/edf_kraken/api.py`
- `custom_components/edf_kraken/coordinator.py`
- `custom_components/edf_kraken/sensor.py`
- `custom_components/edf_kraken/const.py`
- `custom_components/edf_kraken/strings.json`

Authentication flow:

- Config flow asks for EDF email and password.
- Call GraphQL `obtainKrakenToken`.
- Store refresh token in the config entry.
- Keep the short-lived JWT in runtime memory.
- Refresh the token before expiry.
- Trigger Home Assistant reauth if refresh fails.

Discovery flow:

- Query `viewer { accounts { number } }`.
- For each account, query linked properties, electricity agreements, gas agreements, meter points, meters, registers, smart meter devices, and relevant identifiers.
- Create devices grouped by account, meter point, or meter depending on the available identifiers.

Polling strategy:

- Fetch topology on setup and occasional reload.
- Poll readings and usage on a conservative interval, initially 30-60 minutes.
- Keep GraphQL queries small to avoid complexity and hourly point issues.
- Do not perform network I/O in entity properties; use a Home Assistant `DataUpdateCoordinator`.

## Sensors

Primary sensors:

- Electricity import total
  - Home Assistant device class: `energy`
  - Unit: `kWh`
  - State class: `total_increasing` if based on cumulative meter register readings

- Gas total
  - Home Assistant device class: `gas` if EDF returns volume such as `m3`
  - Home Assistant device class: `energy` if EDF returns converted gas energy in `kWh`
  - State class: `total_increasing` if based on cumulative register readings

Optional sensors:

- Daily electricity usage
- Daily gas usage
- Latest electricity reading timestamp
- Latest gas reading timestamp
- Account balance
- Active tariff/product name
- Smart meter reading frequency/consent status

Prefer cumulative register readings for Home Assistant Energy Dashboard compatibility. Use grouped consumption data for daily/hourly usage sensors where supported.

## Error Handling

Handle these cases explicitly:

- Authentication failure.
- Token expiry and refresh failure.
- GraphQL `errors` field despite HTTP 200.
- Rate limiting and hourly points exhaustion.
- Disabled or protected GraphQL fields.
- Electricity-only or gas-only accounts.
- Non-smart meters with manual readings only.
- No consumption data available for a date range.
- Multi-register electricity meters such as Economy 7.
- Meter replacement causing a reset or a new cumulative register series.

## Testing Plan

Unit tests:

- Token parsing and refresh logic.
- GraphQL response parsing.
- GraphQL error handling.
- Viewer/account discovery parsing.
- Electricity-only, gas-only, and dual-fuel fixture accounts.
- Multi-register electricity meter fixture.
- Missing smart consumption fixture.
- Sensor classes, units, and state classes.

Manual validation:

- Authenticate with a real EDF account.
- Confirm account and meter discovery.
- Confirm latest electricity and gas readings match EDF portal/app values.
- Confirm Home Assistant Energy Dashboard accepts the created sensors.
- Confirm refresh token survives Home Assistant restart.
- Confirm reauth flow works after invalid credentials/token expiry.

## Assumptions

- EDF permits customer account access through the public Kraken API using normal account credentials.
- Protected endpoint behavior may differ from public documentation, so real-account validation is required.
- GraphQL field availability may vary by account type, fuel type, meter type, and smart meter consent.
- The initial integration should be read-only.
- REST should not be implemented until a specific REST endpoint proves useful during real-account testing.

## Source Links

- EDF API documentation: https://developer.edfgb-kraken.energy/
- EDF GraphQL basics: https://developer.edfgb-kraken.energy/graphql/guides/basics/
- EDF GraphQL queries: https://developer.edfgb-kraken.energy/graphql/reference/queries/
- EDF GraphQL mutations: https://developer.edfgb-kraken.energy/graphql/reference/mutations/
- EDF REST basics: https://developer.edfgb-kraken.energy/rest/guides/api-basics/
- Home Assistant sensor docs: https://developers.home-assistant.io/docs/core/entity/sensor/
