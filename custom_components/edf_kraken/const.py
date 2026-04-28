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

DEFAULT_API_RETRIES = 2
DEFAULT_API_RETRY_BACKOFF_SECONDS = 2

OPT_SCAN_INTERVAL = "scan_interval"
OPT_ENABLE_DAILY_USAGE = "enable_daily_usage"
OPT_ENABLE_ACCOUNT_METADATA = "enable_account_metadata"

MANUFACTURER = "EDF"

ISSUE_AUTH_FAILED = "auth_failed"
ISSUE_RATE_LIMITED = "rate_limited"
ISSUE_NO_METERS = "no_meters"
ISSUE_DAILY_USAGE_UNAVAILABLE = "daily_usage_unavailable"
ISSUE_METADATA_UNAVAILABLE = "metadata_unavailable"
