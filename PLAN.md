# EDF Kraken Home Assistant Integration: Current Handoff Plan

## Current Status
- Current branch: `main`.
- Latest completed Phase 2 implementation commit: `3bfc833 Add Phase 2 robustness handling`.
- Phase 1 MVP is implemented.
- Phase 2 robustness and account coverage work is implemented.
- Phase 3 initial usage and metadata work is merged to `main`.
- Phase 4 polish and installation documentation are merged to `main`.

## Implemented So Far
- Home Assistant custom integration domain: `edf_kraken`.
- Standard integration files exist under `custom_components/edf_kraken/`.
- UI config flow and reauth flow are implemented.
- EDF GraphQL authentication uses `obtainKrakenToken`.
- Config entries persist the EDF account number and refresh token only.
- Access tokens are runtime-only and refreshed as needed.
- Account discovery uses `viewer`.
- Account topology and meter readings are fetched through GraphQL.
- Sensors are coordinator-backed and avoid network I/O in entity properties.
- Default polling interval is 60 minutes, configurable through options.
- Cumulative electricity and gas reading sensors are implemented for Energy Dashboard compatibility.
- GraphQL `errors` payloads are handled even when HTTP status is 200.
- Token refresh failure raises Home Assistant reauth.
- Defensive parsing supports electricity-only, gas-only, dual-fuel, multi-property, multi-meter, and multi-register accounts.
- Stable sensor unique IDs are derived from account, fuel, meter point, meter, serial, and register identity.
- Duplicate readings for the same sensor are deduplicated, preferring the newest timestamp.
- Bounded retry/backoff is implemented for transient HTTP failures and 429 rate-limit responses.
- Diagnostics are implemented with token redaction.
- README documents current scope and install notes.
- Phase 3 initial implementation adds latest-reading timestamp sensors from existing cumulative readings.
- Phase 3 initial implementation adds opt-in daily usage sensors behind `enable_daily_usage`.
- Phase 3 initial implementation adds opt-in tariff/projected-balance metadata sensors behind `enable_account_metadata`.
- Phase 4 initial implementation adds Home Assistant repair issues for auth failure, rate limits, no readings, and unavailable optional data.
- Phase 4 initial implementation adds `docs/manual_validation.md` for real-account validation.
- Installation documentation is implemented in `docs/installation.md`.
- HACS repository metadata is implemented in `hacs.json`.
- GitHub Actions CI is implemented for linting, syntax checks, JSON validation, HACS metadata validation, and pytest.
- GitHub Actions release workflow is implemented for `v*.*.*` tags.
- Dependabot is configured for GitHub Actions updates.

## Verification State
- Syntax check passes:
  - `python -B -c "<ast parse check over all .py files>"`
- Standalone API parser/client tests pass when run directly:
  - `python -B -c "<load tests/test_api.py and execute test_* functions>"`
- Pytest suite passes:
  - `python -B -m pytest tests -o cache_dir=C:/tmp/pytest-cache/ha-edf`
  - Result: `13 passed`
- Ruff lint passes:
  - `python -B -m ruff check --no-cache custom_components tests scripts`
- HACS metadata validation passes:
  - `python -B scripts/validate_hacs.py`
- Manifest and translation JSON parse successfully.
- No real EDF account validation has been performed yet.
- No full Home Assistant runtime validation has been performed yet.

## Phase 3: Implemented Initial Work
- Added optional daily usage sensors where EDF GraphQL consumption data is available:
  - Daily electricity usage.
  - Daily gas usage.
- Added latest reading timestamp sensors for electricity and gas cumulative readings.
- Added optional account/tariff metadata sensors:
  - Active electricity product/tariff name.
  - Active gas product/tariff name.
  - Projected balance if the API exposes it reliably.
- Keep cumulative register sensors as the primary Energy Dashboard path.
- Keep daily usage and metadata sensors disabled by default behind the existing options:
  - `enable_daily_usage`
  - `enable_account_metadata`
- Current implementation keeps Phase 3 data in the topology query behind GraphQL directives so default behavior remains conservative.
- Split daily usage and metadata into separate GraphQL calls later if real-account validation shows complexity or field-protection issues.
- Do not add REST yet unless real-account testing proves a specific REST endpoint is needed.

## Remaining Phase 3 Work
- Validate the `consumption(grouping: DAY, startAt, timezone)` query with a real EDF account.
- Confirm EDF's `ConsumptionType` fields; current query uses documented EDF fields `consumption` and `isEstimate`.
- Confirm `SupplyProductType` product fields on active agreements for EDF accounts.
- Decide whether daily usage sensors need a separate coordinator if real-world update cadence differs from cumulative readings.
- Add Home Assistant entity tests once a Home Assistant test environment is available.
- Consider documenting the options flow once real-account validation confirms daily usage and metadata behavior.

## Phase 4: Current Work
- Add Home Assistant repair issues for common account states:
  - Authentication failure.
  - Rate limit, point allowance, or query complexity exhaustion.
  - No cumulative meter readings discovered.
  - Daily usage unavailable while daily usage sensors are enabled.
  - Metadata unavailable while account metadata sensors are enabled.
- Improve diagnostics with counts and booleans for readings, daily usage, and metadata.
- Add manual validation documentation for real EDF accounts.

## Remaining Phase 4 Work
- Validate repair issue translations in a running Home Assistant instance.
- Decide whether any repair issue should be fixable with a RepairsFlow after real-account testing.
- Improve device grouping if Home Assistant UI shows account, meter point, or meter devices poorly.
- Add Home Assistant runtime/entity tests when a test environment is available.

## Remaining Phase 2 Gaps To Validate
- Confirm the GraphQL topology query fields against a real EDF account.
- Confirm `meters(includeInactive: true)` is accepted by EDF's GraphQL schema; remove the argument if EDF rejects it.
- Confirm register reading units for gas are volume (`m3`) or energy (`kWh`) on real accounts.
- Confirm Home Assistant accepts the generated sensor device classes, units, and state classes in the Energy Dashboard.
- Confirm reauth flow works after an expired or invalid refresh token.

## Later Phases
- Phase 5 should remain optional:
  - REST investigation only for proven GraphQL gaps.
  - Smart meter consent/status sensors only after read-only behavior is confirmed.
  - Hourly usage sensors only if API limits and Home Assistant performance are acceptable.
  - Write services such as `requestConsumptionData` only if explicitly required later.

## Repository Automation
- CI workflow: `.github/workflows/ci.yml`.
- HACS metadata workflow: `.github/workflows/validate-hacs.yml`.
- Release workflow: `.github/workflows/release.yml`.
- Release instructions: `docs/releasing.md`.
- Dev dependencies: `requirements-dev.txt`.
- Local validation helper: `scripts/validate_hacs.py`.

## Assumptions
- The integration remains read-only.
- GraphQL remains the primary API.
- REST remains deferred.
- Cumulative register readings remain the primary Energy Dashboard integration path.
- Real EDF account validation is required before treating GraphQL field availability as stable.
- Polling remains conservative to reduce risk of EDF complexity and hourly point limits.
