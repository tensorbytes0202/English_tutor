"""Settings from the environment. A local .env file (never committed) is read first; real environment variables win."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

MIN_SECRET_CHARS = 32


def jwt_secret():
    """The key that signs sign-in tokens. Refuses to run with a missing or weak one rather than quietly using a default."""
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < MIN_SECRET_CHARS:
        raise RuntimeError(f"JWT_SECRET must be set to at least {MIN_SECRET_CHARS} characters (see .env.example).")
    return secret


def cookie_secure():
    """Send the session cookie over HTTPS only. Turn on in production (COOKIE_SECURE=1); off for http://localhost."""
    return os.getenv("COOKIE_SECURE", "0") == "1"
