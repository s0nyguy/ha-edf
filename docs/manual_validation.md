# EDF Kraken Manual Validation Checklist

Use this checklist with a real EDF account before treating the integration as stable.

## Setup And Authentication

- Install `custom_components/edf_kraken` into a Home Assistant test instance.
- Add the integration through the UI using EDF credentials.
- Confirm the config entry title uses the EDF account number.
- Restart Home Assistant and confirm the integration reloads without asking for the password again.
- Force an invalid refresh token in a test copy of the config entry and confirm Home Assistant starts reauth.

## Cumulative Readings

- Confirm electricity and gas cumulative sensors match the EDF portal or app.
- Confirm electricity-only, gas-only, and dual-fuel accounts behave correctly where available.
- Confirm Economy 7 or other multi-register meters create separate stable sensors per register.
- Confirm Home Assistant Energy Dashboard accepts the cumulative electricity and gas sensors.
- Confirm a non-smart/manual-reading account does not create daily usage sensors unless data exists.

## Optional Phase 3 Sensors

- Enable daily usage sensors in options and reload the integration.
- Confirm grouped daily electricity and gas usage values match EDF where EDF exposes them.
- Confirm accounts without smart consumption create a repair issue instead of failing setup.
- Enable account metadata sensors and confirm tariff names and projected balance are correct.
- Disable optional sensors again and confirm related repair issues disappear after the next update.

## Repairs And Diagnostics

- Confirm a no-meter account shape creates the `No EDF meter readings found` repair issue.
- Confirm EDF rate/complexity errors create the `EDF API rate limit reached` repair issue.
- Confirm optional daily usage and metadata repair issues are only created when the corresponding option is enabled.
- Download diagnostics and verify tokens are redacted.
- Confirm diagnostics include reading, daily usage, and metadata counts.

## GraphQL Field Validation

- Confirm `meters(includeInactive: true)` is accepted by EDF.
- Confirm `consumption(grouping: DAY, startAt, timezone)` is accepted by EDF.
- Confirm EDF `ConsumptionType` returns the fields currently parsed by the integration.
- Confirm active agreement `product` fields expose usable product names.
- If a field is rejected or protected, adjust the GraphQL query before enabling the feature by default.
