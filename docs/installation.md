# EDF Kraken Installation Guide

This guide covers installing and configuring the EDF Kraken custom integration in Home Assistant.

## Before You Start

- You need a working Home Assistant instance.
- You need an EDF online account email and password.
- If you want the easiest install path, install HACS first: <https://hacs.xyz/>.
- The integration is read-only. It stores the EDF account number and refresh token in the Home Assistant config entry. It does not store your EDF password.

## Install With HACS

Open HACS repository on my Home Assistant:

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=s0nyguy&repository=ha-edf&category=integration)

If the button does not work, add the repository manually:

1. Open Home Assistant.
2. Open **HACS**.
3. Open the three-dot menu.
4. Select **Custom repositories**.
5. Enter this repository URL:

   ```text
   https://github.com/s0nyguy/ha-edf
   ```

6. Set the category to **Integration**.
7. Select **Add**.
8. Search HACS for **EDF Kraken**.
9. Select **Download**.
10. Restart Home Assistant.

## Manual Install

Use this path if you do not use HACS.

1. Download or clone this repository.
2. In your Home Assistant config directory, create `custom_components` if it does not already exist.
3. Copy this directory from the repository:

   ```text
   custom_components/edf_kraken
   ```

4. Paste it into your Home Assistant config directory so the final path is:

   ```text
   config/custom_components/edf_kraken
   ```

5. Restart Home Assistant.

## Add The Integration In Home Assistant

1. Open Home Assistant.
2. Go to **Settings**.
3. Open **Devices & services**.
4. Select **Add integration**.
5. Search for **EDF Kraken**.
6. Enter your EDF account email and password.
7. Submit the form.

After setup, the integration discovers the EDF account and creates sensors for available electricity and gas meter readings.

## Configure Options

1. Go to **Settings** -> **Devices & services**.
2. Open the **EDF Kraken** integration.
3. Select **Configure**.
4. Adjust the polling interval if needed. The default is 60 minutes.
5. Optional sensors are disabled by default:
   - Enable daily usage sensors only after confirming EDF exposes smart consumption data for your account.
   - Enable account metadata sensors only after confirming EDF exposes tariff and balance metadata for your account.

## Energy Dashboard Setup

The primary sensors are cumulative meter readings.

1. Go to **Settings** -> **Dashboards** -> **Energy**.
2. Add the EDF electricity cumulative energy sensor to electricity consumption.
3. Add the EDF gas cumulative sensor if Home Assistant accepts the exposed unit and device class.
4. Compare Home Assistant values with the EDF app or portal before relying on long-term statistics.

## Troubleshooting

### EDF Kraken Does Not Appear In Add Integration

- Confirm the folder path is `config/custom_components/edf_kraken`.
- Confirm `manifest.json` exists inside that folder.
- Restart Home Assistant after installing the files.
- Clear the browser cache or reload the Home Assistant frontend.

### Authentication Fails

- Confirm the same EDF email and password work in the EDF app or portal.
- Remove and re-add the integration if the stored refresh token is no longer valid.
- Check Home Assistant logs for `edf_kraken` messages.

### No Meter Sensors Are Created

- Confirm the EDF account has active electricity or gas supply points.
- Download diagnostics from the integration page and check reading counts.
- Some account, meter, or smart-meter fields may be unavailable until tested against a real EDF account.

### Daily Usage Or Metadata Sensors Are Missing

- Confirm the corresponding option is enabled.
- Wait for the next scheduled update or reload the integration.
- If a repair issue appears, EDF did not return that optional data for the account.

## Validation

Before treating the integration as stable for your account, run through the manual checklist in [manual_validation.md](manual_validation.md).
