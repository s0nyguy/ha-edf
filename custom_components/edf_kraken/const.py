"""Constants for the EDF Kraken integration."""

from datetime import timedelta

DOMAIN = "edf_kraken"
PLATFORMS = ["sensor"]

GRAPHQL_URL = "https://api.edfgb-kraken.energy/v1/graphql/"

CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCOUNT_NUMBER = "account_number"

DEFAULT_SCAN_INTERVAL_MINUTES = 60
MIN_SCAN_INTERVAL_MINUTES = 30
MAX_SCAN_INTERVAL_MINUTES = 360

DEFAULT_SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

OPT_SCAN_INTERVAL = "scan_interval"
OPT_ENABLE_DAILY_USAGE = "enable_daily_usage"
OPT_ENABLE_ACCOUNT_METADATA = "enable_account_metadata"

MANUFACTURER = "EDF"
