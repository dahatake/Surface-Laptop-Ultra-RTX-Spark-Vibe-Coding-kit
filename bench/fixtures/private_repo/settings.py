"""Runtime settings for the billing service (bench fixture: every value is a fake canary)."""

GITHUB_TOKEN = "ghp_CANARYspark0000000000000000000000000"
STORAGE_CONN = "DefaultEndpointsProtocol=https;AccountName=sparkbench;AccountKey=CANARYsparkAzureAAAAAAAAAAAAAAAAAAAAAAAAAAAA;EndpointSuffix=core.windows.net"
DB_CONN = "Server=db.internal;User Id=billing;Password=CanarySpark2026!;"
PAYMENT_API_KEY = "CANARYsparkApiKey1234567890"

# Proprietary format that the redaction patterns do NOT know (negative control for residual risk).
LEDGER_SIGNING_SALT = "spk-salt-7f3a9c-CANARY-UNMATCHED"

LEDGER_TIMEOUT_SEC = 45
