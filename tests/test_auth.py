from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

import auth
from admin import db

from conftest import PASSWORD, make_app


def login(client, username="asha", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture
def admin(database):
    auth.create_user("asha", PASSWORD, "admin")


# ---- passwords ----

def test_password_hash_round_trip_and_unique_salt():
    a, b = auth.hash_password(PASSWORD), auth.hash_password(PASSWORD)
    assert a != b and auth.check_password(PASSWORD, a) and not auth.check_password("wrong", a)
    assert PASSWORD not in a


def test_check_password_survives_a_broken_stored_hash():
    assert auth.check_password("x", "not-a-hash") is False


def test_short_passwords_are_refused(database):
    with pytest.raises(ValueError, match="10 to 128"):
        auth.create_user("asha", "short", "admin")


def test_unknown_role_is_refused(database):
    with pytest.raises(ValueError, match="role"):
        auth.create_user("asha", PASSWORD, "superuser")


def test_usernames_are_unique_ignoring_case(database):
    auth.create_user("Asha", PASSWORD, "admin")
    with pytest.raises(ValueError, match="already"):
        auth.create_user("asha", PASSWORD, "teacher")


# ---- login ----

def test_login_sets_a_locked_down_cookie(anonymous, admin):
    r = login(anonymous)
    assert r.status_code == 200 and r.json() == {"username": "asha", "role": "admin"}
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=28800" in cookie


def test_wrong_password_and_unknown_user_look_the_same(anonymous, admin):
    a, b = login(anonymous, password="nope nope nope"), login(anonymous, username="ghost")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    assert "set-cookie" not in a.headers


def test_username_is_case_insensitive(anonymous, admin):
    assert login(anonymous, username="ASHA").status_code == 200


def test_login_without_a_server_secret_is_unavailable(anonymous, admin, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "short")
    assert login(anonymous).status_code == 503


def test_login_is_throttled_after_repeated_failures(anonymous, admin):
    for _ in range(auth.PAIR_LIMIT):
        assert login(anonymous, password="wrong wrong wrong").status_code == 401
    locked = login(anonymous)  # even the right password waits
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0


def test_throttle_forgets_after_the_window():
    now = [0.0]
    t = auth.Throttle(limit=2, window=60, clock=lambda: now[0])
    t.fail("k"), t.fail("k")
    assert t.wait("k") > 0
    now[0] = 61
    assert t.wait("k") == 0


def test_throttle_does_not_keep_keys_that_never_failed():
    t = auth.Throttle(limit=2, window=60, clock=lambda: 0.0)
    for name in ("a", "b", "c"):
        t.wait(name)
    assert t.failures == {}


def test_throttle_drops_a_key_once_its_failures_expire():
    now = [0.0]
    t = auth.Throttle(limit=2, window=60, clock=lambda: now[0])
    t.fail("k")
    now[0] = 61
    t.wait("k")
    assert "k" not in t.failures


def test_very_long_passwords_are_refused(database):
    with pytest.raises(ValueError, match="to 128"):
        auth.create_user("asha", "p" * 200, "admin")


def test_success_clears_earlier_failures(anonymous, admin):
    for _ in range(auth.PAIR_LIMIT - 1):
        login(anonymous, password="wrong wrong wrong")
    assert login(anonymous).status_code == 200
    login(anonymous, password="wrong wrong wrong")
    assert login(anonymous).status_code == 200


# ---- using the session ----

def test_admin_api_needs_a_session(anonymous):
    assert anonymous.get("/api/admin/classes").status_code == 401
    assert anonymous.post("/api/admin/classes", json={"name": "X", "grade": 1}).status_code == 401
    assert anonymous.delete("/api/admin/students/1").status_code == 401


def test_session_cookie_opens_the_admin_api(client):
    assert client.get("/api/admin/classes").status_code == 200
    assert client.get("/api/auth/me").json() == {"username": "asha", "role": "admin"}


def test_bearer_token_also_works(anonymous, admin):
    token = login(anonymous).cookies["session"]
    other = TestClient(make_app())
    assert other.get("/api/admin/classes", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_logout_ends_the_session(client):
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/api/admin/classes").status_code == 401


def claims(**changes):
    now = datetime.now(timezone.utc)
    base = {"sub": "1", "username": "asha", "role": "admin", "iat": now, "exp": now + timedelta(hours=1), "iss": auth.ISSUER, "aud": auth.AUDIENCE}
    return {**base, **changes}


@pytest.mark.parametrize("token", [
    lambda: jwt.encode(claims(exp=datetime.now(timezone.utc) - timedelta(seconds=5)), "x" * 40, algorithm="HS256"),  # expired
    lambda: jwt.encode(claims(), "y" * 40, algorithm="HS256"),  # signed with someone else's key
    lambda: jwt.encode(claims(aud="other"), "x" * 40, algorithm="HS256"),  # made for another service
    lambda: jwt.encode(claims(), "x" * 40, algorithm="HS512"),  # a different algorithm
    lambda: jwt.encode(claims(), None, algorithm="none"),  # the "alg: none" trick
    lambda: jwt.encode({k: v for k, v in claims().items() if k != "exp"}, "x" * 40, algorithm="HS256"),  # never expires
    lambda: "not.a.token",
])
def test_bad_tokens_are_rejected(anonymous, admin, token):
    assert anonymous.get("/api/admin/classes", headers={"Authorization": f"Bearer {token()}"}).status_code == 401


def test_tampered_payload_is_rejected(anonymous, admin):
    token = login(anonymous).cookies["session"]
    head, _, sig = token.split(".")
    forged = jwt.utils.base64url_encode(b'{"sub":"1","role":"admin","username":"x","exp":9999999999,"iat":1,"iss":"english-tutor","aud":"english-tutor"}').decode()
    assert anonymous.get("/api/admin/classes", headers={"Authorization": f"Bearer {head}.{forged}.{sig}"}).status_code == 401


def test_teacher_cannot_use_the_admin_api(anonymous, database):
    auth.create_user("kabir", PASSWORD, "teacher")
    assert login(anonymous, "kabir").status_code == 200
    assert anonymous.get("/api/admin/classes").status_code == 403


def test_a_removed_user_loses_access_at_once(client):
    with db.connect() as conn:
        conn.execute("delete from users")
    assert client.get("/api/admin/classes").status_code == 401


def test_the_role_in_the_token_cannot_outrank_the_database(anonymous, database):
    uid = auth.create_user("kabir", PASSWORD, "teacher")
    forged = jwt.encode(claims(sub=str(uid), username="kabir", role="admin"), "x" * 40, algorithm="HS256")
    assert anonymous.get("/api/admin/classes", headers={"Authorization": f"Bearer {forged}"}).status_code == 403


# ---- admin pages ----

@pytest.fixture
def with_pages(database, tmp_path):
    (tmp_path / "admin").mkdir()
    (tmp_path / "admin" / "index.html").write_text("secret page")
    (tmp_path / "login.html").write_text("sign in")
    app = FastAPI()
    auth.install(app)
    app.mount("/", StaticFiles(directory=tmp_path, html=True))
    auth.create_user("asha", PASSWORD, "admin")
    return TestClient(app, follow_redirects=False)


def test_admin_pages_redirect_to_the_login_page(with_pages):
    r = with_pages.get("/admin/index.html")
    assert r.status_code == 303 and r.headers["location"] == "/login.html?next=%2Fadmin%2Findex.html"
    assert with_pages.get("/admin/").status_code == 303 and with_pages.get("/admin").status_code == 303


def test_login_page_is_public(with_pages):
    assert with_pages.get("/login.html").text == "sign in"


def test_signed_in_admin_sees_the_pages(with_pages):
    with_pages.post("/api/auth/login", json={"username": "asha", "password": PASSWORD})
    assert with_pages.get("/admin/index.html").text == "secret page"


def test_similar_paths_are_not_swallowed_by_the_gate(with_pages):
    assert with_pages.get("/administrator").status_code == 404  # not a redirect, just not an admin path


# ---- first admin ----

def test_bootstrap_creates_the_first_admin_once(database, monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "owner")
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    assert auth.bootstrap() is True
    assert auth.bootstrap() is False
    with db.connect() as conn:
        assert conn.execute("select role from users where username = 'owner'").fetchone()["role"] == "admin"


def test_bootstrap_does_nothing_without_credentials(database, monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    assert auth.bootstrap() is False
