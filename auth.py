"""Sign-in: password check, a JWT kept in an HttpOnly cookie, roles, a limit on password guessing and a gate on the admin pages.

    python auth.py create-user --username asha --role admin      # asks for the password
"""
import argparse
import getpass
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import config
from admin import db

ISSUER = AUDIENCE = "english-tutor"
COOKIE = "session"
TOKEN_HOURS = 8
ROLES = ("admin", "teacher")
MIN_PASSWORD, MAX_PASSWORD = 10, 128
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
PAIR_LIMIT, IP_LIMIT, WINDOW = 5, 20, 300  # failed sign-ins allowed per account-and-place / per place, per 5 minutes


# ---- passwords ----

def hash_password(password):
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(password.encode(), salt=salt, **SCRYPT).hex()}"


def check_password(password, stored):
    try:
        scheme, salt, digest = stored.split("$")
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
        return scheme == "scrypt" and hmac.compare_digest(candidate, bytes.fromhex(digest))
    except ValueError:
        return False


_DECOY = hash_password("not a real password")  # checked when the user doesn't exist, so timing doesn't reveal which names exist


def create_user(username, password, role):
    username = username.strip()
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise ValueError(f"The password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
    if not username:
        raise ValueError("The username can't be empty.")
    try:
        with db.connect() as conn:
            return conn.execute("insert into users (username, password_hash, role) values (?, ?, ?)",
                                (username, hash_password(password), role)).lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"The username {username} is already taken.") from None


def bootstrap():
    """On first start, create the admin named in ADMIN_USERNAME / ADMIN_PASSWORD if there are no users yet."""
    username, password = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")
    if not (username and password):
        return False
    with db.connect() as conn:
        if conn.execute("select 1 from users limit 1").fetchone():
            return False
    create_user(username, password, "admin")
    return True


# ---- tokens ----

def issue_token(user):
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["id"]), "username": user["username"], "role": user["role"], "iat": now,
              "exp": now + timedelta(hours=TOKEN_HOURS), "iss": ISSUER, "aud": AUDIENCE}
    return jwt.encode(claims, config.jwt_secret(), algorithm="HS256")


def read_token(token):
    try:
        return jwt.decode(token, config.jwt_secret(), algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
                          options={"require": ["exp", "iat", "sub"]})
    except jwt.PyJWTError:
        return None


def user_from(request):
    """The signed-in user, looked up fresh so a removed user or a changed role takes effect at once; None if not signed in."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header[:7].lower() == "bearer " else request.cookies.get(COOKIE)
    claims = read_token(token or "")
    if not claims or not str(claims["sub"]).isdigit():
        return None
    with db.connect() as conn:
        row = conn.execute("select id, username, role from users where id = ?", (int(claims["sub"]),)).fetchone()
    return dict(row) if row else None


def current_user(request: Request):
    user = user_from(request)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def require_role(*roles):
    def check(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "You don't have access to this.")
        return user
    return check


# ---- limiting guesses ----

class Throttle:
    """Counts failures per key over a sliding window."""

    def __init__(self, limit, window=WINDOW, clock=time.monotonic):
        self.limit, self.window, self.clock, self.failures = limit, window, clock, {}

    def _recent(self, key):
        """The failures still inside the window; forgets keys with none, so the table can't grow without bound."""
        hits = self.failures.get(key)
        while hits and hits[0] <= self.clock() - self.window:
            hits.popleft()
        if hits is not None and not hits:
            del self.failures[key]
            return None
        return hits

    def wait(self, key):
        """Seconds until another try is allowed (0 if allowed now)."""
        hits = self._recent(key)
        return 0 if not hits or len(hits) < self.limit else max(1, int(hits[0] + self.window - self.clock()) + 1)

    def fail(self, key):
        self.failures.setdefault(key, deque()).append(self.clock())

    def clear(self, key):
        self.failures.pop(key, None)


pair_throttle, ip_throttle = Throttle(PAIR_LIMIT), Throttle(IP_LIMIT)


def reset_throttles():
    pair_throttle.failures.clear()
    ip_throttle.failures.clear()


# ---- routes ----

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    place = request.client.host if request.client else "unknown"
    pair = f"{place}|{body.username.strip().lower()}"
    wait = max(pair_throttle.wait(pair), ip_throttle.wait(place))
    if wait:
        raise HTTPException(429, "Too many tries. Wait a few minutes and try again.", headers={"Retry-After": str(wait)})
    try:
        config.jwt_secret()
    except RuntimeError:
        raise HTTPException(503, "Sign-in is not set up on this server yet.") from None
    with db.connect() as conn:
        row = conn.execute("select * from users where username = ? collate nocase", (body.username.strip(),)).fetchone()
    ok = check_password(body.password, row["password_hash"] if row else _DECOY)
    if not (row and ok):
        pair_throttle.fail(pair)
        ip_throttle.fail(place)
        raise HTTPException(401, "That username and password don't match.")
    pair_throttle.clear(pair)
    response.set_cookie(COOKIE, issue_token(row), max_age=TOKEN_HOURS * 3600, httponly=True, samesite="strict",
                        secure=config.cookie_secure() or request.url.scheme == "https", path="/")
    return {"username": row["username"], "role": row["role"]}


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")


@router.get("/me")
def me(user=Depends(current_user)):
    return {"username": user["username"], "role": user["role"]}


class AdminGate:
    """Admin pages are plain files, so the API check does not cover them: send anyone who isn't an admin to the login page.

    A plain ASGI middleware, so every other request (including the streamed speech replies) goes straight through untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope["path"] if scope["type"] == "http" else ""
        if path == "/admin" or path.startswith("/admin/"):
            user = user_from(Request(scope))
            if not user or user["role"] != "admin":
                return await RedirectResponse(f"/login.html?next={quote(path, safe='')}", status_code=303)(scope, receive, send)
        await self.app(scope, receive, send)


def install(app):
    app.include_router(router)
    app.add_middleware(AdminGate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["create-user"])
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=ROLES, default="admin")
    args = parser.parse_args()
    db.init()
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Again: "):
        raise SystemExit("The passwords don't match.")
    try:
        create_user(args.username, pw, args.role)
    except ValueError as err:
        raise SystemExit(str(err)) from None
    print(f"Created {args.role} {args.username}.")
