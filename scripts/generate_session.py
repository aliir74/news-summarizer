#!/usr/bin/env python3
"""One-time script to generate Pyrogram session string.

Run this script locally to authenticate your Telegram account and generate
a session string that can be used in environment variables for deployment.

Usage:
    uv run python scripts/generate_session.py

You will be prompted for:
1. Your API ID and API Hash (from https://my.telegram.org)
2. Your phone number
3. The verification code sent to your Telegram app
4. Your 2FA password (if enabled)

The script will output a session string that you should:
1. Copy and save securely
2. Add to your deployment environment as TELEGRAM_SESSION_STRING
3. Never commit to git or share publicly
"""

import asyncio
import os
import sys

# Add the project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pyrogram import Client


async def main() -> None:
    """Generate and display the session string."""
    load_dotenv()

    print("=" * 60)
    print("Telegram Session String Generator")
    print("=" * 60)
    print()

    # Get API credentials
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not api_id:
        api_id = input("Enter your API ID (from https://my.telegram.org): ").strip()

    if not api_hash:
        api_hash = input("Enter your API Hash: ").strip()

    if not api_id or not api_hash:
        print("Error: API ID and API Hash are required")
        sys.exit(1)

    print()
    print("Starting authentication...")
    print("You will be prompted for your phone number and verification code.")
    print()

    # Create client and authenticate
    async with Client(
        name="session_generator",
        api_id=int(api_id),
        api_hash=api_hash,
        in_memory=True,
    ) as app:
        # Export the session string
        session_string = await app.export_session_string()

        print()
        print("=" * 60)
        print("SUCCESS! Your session string is below.")
        print("=" * 60)
        print()
        print("Add this to your environment variables as TELEGRAM_SESSION_STRING:")
        print()
        print("-" * 60)
        print(session_string)
        print("-" * 60)
        print()
        print("IMPORTANT SECURITY NOTES:")
        print("1. Never share this string - it grants access to your account")
        print("2. Never commit this to git")
        print("3. Store securely in your deployment environment (e.g., Railway)")
        print("4. If compromised, terminate all sessions in Telegram settings")
        print()


if __name__ == "__main__":
    asyncio.run(main())
