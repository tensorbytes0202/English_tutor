import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
from admin import db
from admin.api import router as admin_router

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    auth.reset_throttles()


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "school.db")
    db.init()
    return db


def make_app(tmp_path=None):
    app = FastAPI()
    auth.install(app)
    app.include_router(admin_router)
    return app


@pytest.fixture
def anonymous(database):
    """A browser that has not signed in."""
    return TestClient(make_app())


@pytest.fixture
def client(database, anonymous):
    """A browser signed in as an admin."""
    auth.create_user("asha", PASSWORD, "admin")
    assert anonymous.post("/api/auth/login", json={"username": "asha", "password": PASSWORD}).status_code == 200
    return anonymous
