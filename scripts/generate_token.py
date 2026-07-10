#!/usr/bin/env python3
"""Generate a time-limited access token for the PHI pipeline batch demo.

Usage:
    python scripts/generate_token.py              # 48-hour token (default)
    python scripts/generate_token.py --hours 24   # 24-hour token
    python scripts/generate_token.py --hours 168  # 1-week token

Reads PIPELINE_ACCESS_TOKEN from .env.cloud (or shell env).
"""
import argparse
import hashlib
import hmac
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ENV_CLOUD  = SCRIPT_DIR.parent / ".env.cloud"


def load_secret() -> str:
    secret = os.environ.get("PIPELINE_ACCESS_TOKEN", "")
    if not secret and ENV_CLOUD.exists():
        for line in ENV_CLOUD.read_text().splitlines():
            if line.startswith("PIPELINE_ACCESS_TOKEN="):
                secret = line.split("=", 1)[1].strip()
                break
    if not secret:
        sys.exit("Error: PIPELINE_ACCESS_TOKEN not found in env or .env.cloud")
    return secret


def generate(secret: str, hours: int) -> str:
    expiry = str(int(time.time()) + hours * 3600)
    sig = hmac.new(secret.encode(), expiry.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}:{sig}"


def main():
    parser = argparse.ArgumentParser(description="Generate a time-limited pipeline access token")
    parser.add_argument("--hours", type=int, default=48, help="Token lifetime in hours (default: 48)")
    args = parser.parse_args()

    secret = load_secret()
    token  = generate(secret, args.hours)
    expiry_dt = datetime.fromtimestamp(int(token.split(":")[0]), tz=timezone.utc)

    print(f"\nToken (valid for {args.hours}h, expires {expiry_dt:%Y-%m-%d %H:%M UTC}):\n")
    print(f"  {token}\n")
    print("Share this token with anyone who needs batch demo access.")


if __name__ == "__main__":
    main()
