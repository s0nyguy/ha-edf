# EDF Kraken Home Assistant Integration: Current Handoff Plan

## Current Status
- Current local branch: `fallback-meter-reading-queries`.
- Open PR: https://github.com/s0nyguy/ha-edf/pull/10
- Latest released version installed/tested in Home Assistant: `v0.1.3`.
- PR #10 targets `v0.1.4` and is intended to fix the current no-entities/no-sensors issue.
- Home Assistant runtime validation has started with a real EDF dual-fuel smart-meter account.
- User account shape confirmed:
  - EDF account number is discovered successfully.
  - Account has both electricity and gas.
  - EDF portal shows smart meter readings.
  - Home Assistant integration loads but has no entities on `v0.1.3`.

## Important Recent Findings
- `v0.1.3` authenticates and discovers the account number, but creates no sensors.
- `v0.1.3` diagnostics show:
  - `reading_count: 0`
  - `last_errors.topology: "EDF rejected the GraphQL request"`
  - Repair issue: `no_meters`
- Home Assistant debug logging was enabled after adding `loggers` in `manifest.json`, but EDF still returns a generic HTTP 400 body for the topology query.
- Live local probe was added at `scripts/live_probe.py`.
- User ran the live probe and got:
  - `meter_topology: ok - 2 meters`
  - Electricity meter ID: `4833853`
  - Gas meter ID: `5472027`
  - `electricity_meter_readings: error - 4833853: EDF rejected the GraphQL request`
  - `gas_meter_readings: error - 5472027: EDF rejected the GraphQL request`
- This proves:
  - Authentication works.
  - Account discovery works.
  - Basic meter topology works.
  - Current problem is specifically the meter readings query shape or selected fields.

## Current PR #10 Work
- Adds fallback GraphQL behaviour:
  - Try embedded account topology/readings.
  - If rejected, fetch meter topology only.
  - Then query electricity/gas readings per meter.
- Adds `query_diagnostics` to diagnostics so future no-entity states show per-stage failures.
- Adds `scripts/live_probe.py` for direct live EDF API testing outside Home Assistant.
- Bumps manifest version to `0.1.4`.
- Latest local patch after the user’s first live-probe run:
  - Changed root meter readings query variable type from `String!` to `ID!` for `meterId`.
  - Added live probe variants:
    - `count_only`
    - `basic_node`
- PR #10 CI was green before the latest push:
  - Lint and test passed.
  - HACS metadata passed.
- Recheck PR #10 checks in the next session.

## Next Session Immediate Steps
1. Ensure the local branch is `fallback-meter-reading-queries`.
2. Ensure working tree is clean.
3. Confirm latest PR #10 checks:
   - `gh pr checks 10`
4. Because the next session should inherit the user’s EDF env vars, run:
   - `python -B scripts\live_probe.py`
5. Inspect the new `Reading query variants:` output.
6. If `count_only` works but `basic_node` fails:
   - The connection/query is valid, but a selected field is invalid/protected.
   - Remove or adjust fields inside `edges.node`.
7. If both `count_only` and `basic_node` fail:
   - The issue is likely one of:
     - EDF does not expose `electricityMeterReadings` / `gasMeterReadings`.
     - `meterId` should be a different identifier from topology.
     - EDF uses another root query or meter field for readings.
8. If the `ID!` change makes main fallback readings work:
   - Keep PR #10 as the fix.
   - Merge PR #10.
   - Confirm release workflow creates `v0.1.4`.
   - User should update HACS to `v0.1.4` and re-test in Home Assistant.

## Local Live Testing
- Script: `scripts/live_probe.py`
- Required env vars:
  - `EDF_KRAKEN_EMAIL`
  - `EDF_KRAKEN_PASSWORD`
- Optional env var:
  - `EDF_KRAKEN_ACCOUNT_NUMBER=A-965CADEE`
- The script prints sanitized output only:
  - account number
  - reading counts
  - topology error
  - query diagnostics
  - reading summaries if found
  - reading query variant results
- Do not print tokens, refresh tokens, email, or password.
- When live testing is complete, the user intends to change EDF credentials.

## Implemented So Far
- Home Assistant custom integration domain: `edf_kraken`.
- UI config flow, options flow, and reauth flow are implemented.
- EDF GraphQL authentication uses `obtainKrakenToken`.
- Config entries persist only EDF account number and refresh token.
- Access tokens are runtime-only and refreshed as needed.
- Account discovery uses `viewer`.
- Coordinator-backed polling uses `DataUpdateCoordinator`.
- Default polling interval is 60 minutes and configurable through options.
- Cumulative electricity/gas reading sensors are implemented for Energy Dashboard compatibility when readings are discovered.
- Latest-reading timestamp sensors are implemented from cumulative readings.
- Optional daily usage and account metadata sensors exist behind options.
- Repairs are implemented for auth failure, rate limits, no readings, and unavailable optional data.
- Diagnostics are implemented with token redaction.
- Diagnostics now include last topology error and query diagnostics.
- HACS metadata and installation docs are implemented.
- CI, HACS validation, Dependabot, and release automation are implemented.
- Release workflow now creates releases from merges to `main` by reading `manifest.json` version.

## Verification State
- Local tests on PR #10 branch passed:
  - `python -B -m pytest tests -p no:cacheprovider`
  - Result after latest fallback changes: `18 passed`
- Ruff passed:
  - `python -B -m ruff check --no-cache custom_components tests scripts`
- HACS metadata validation passed:
  - `python -B scripts/validate_hacs.py`
- JSON validation passed.
- Real EDF account validation is in progress and currently blocked on finding the correct readings query.

## Known Risks / Unknowns
- EDF’s GraphQL schema appears compatible enough for account/meter topology but rejects the current meter readings query with a generic HTTP 400.
- Public Kraken/Octopus docs show `electricityMeterReadings` and `gasMeterReadings` using `meterId: ID!`; PR #10 now matches that, but this has not yet been re-run with live credentials after the patch.
- EDF may have disabled root meter reading fields or may require different arguments such as reading origin/type filters.
- The `meters(includeInactive: true)` argument is accepted in the live account topology query.
- Gas units still need real validation once readings are returned.

## Later Work
- Once readings work:
  - Validate Home Assistant entities and Energy Dashboard compatibility.
  - Confirm reauth flow with an invalid/expired refresh token.
  - Validate daily usage and metadata optional sensors.
  - Improve docs with real-account validation notes.
- Phase 5 remains optional:
  - REST only for proven GraphQL gaps.
  - Smart meter consent/status sensors only after read-only behaviour is stable.
  - Hourly usage only if API limits and HA performance allow it.
  - Write operations only if explicitly required later.
