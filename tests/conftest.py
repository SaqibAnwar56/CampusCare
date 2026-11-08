"""Shared fixtures. Each test gets a fresh in-memory database.

A small plugin records the genuine outcome of every test (pass/fail plus the 'observed' text that
the test passes to record()) in test-results/results.json. The project report is generated from
that file, so no result in the report is typed in by hand.
"""
import io
import json
import os

import pytest
from flask import g
from flask.testing import FlaskClient

from campuscare import create_app
from campuscare.extensions import db
from campuscare.services import create_user
from config import TestConfig

_OBSERVED = {}
_OUTCOMES = {}


class Cfg(TestConfig):
    pass


class IsolatedClient(FlaskClient):
    """The `app` fixture keeps ONE app context open for direct DB access, so flask.g would otherwise be
    shared by every request and Flask-Login would cache the first user across clients. Dropping the cached
    user before each request makes every client behave like a separate browser."""
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


@pytest.fixture()
def app(tmp_path):
    Cfg.UPLOAD_FOLDER = str(tmp_path / "uploads")
    app = create_app(Cfg)
    app.test_client_class = IsolatedClient
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def users(app):
    out = {}
    for key, name, role, spec in [("admin", "Test Admin", "admin", None), ("staff", "Test Electrician", "staff", "Electrical"),
                                  ("staff2", "Test Plumber", "staff", "Plumbing & Water"),
                                  ("student", "Test Student", "requester", None), ("student2", "Other Student", "requester", None)]:
        out[key] = create_user(name, f"{key}@t.test", "Passw0rd!", role, "Testing", spec).id
    db.session.commit()
    return out


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, key, password="Passw0rd!"):
    return client.post("/login", data={"email": f"{key}@t.test", "password": password})


@pytest.fixture()
def as_user(app, users):
    def _make(key):
        c = app.test_client()
        r = login(c, key)
        assert r.status_code == 302, f"login failed for {key}"
        return c
    return _make


VALID_FORM = dict(title="Projector not working", description="The projector in the lab does not switch on at all.",
                  category="IT & Network", building="Computer Lab Complex", location="Lab 3", priority="Medium")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def png_file(name="photo.png", data=PNG):
    return (io.BytesIO(data), name)


@pytest.fixture()
def record(request):
    """record(tc_id, requirement_ids, observed_text) — stores what the test actually saw."""
    def _rec(tc, observed):
        _OBSERVED[request.node.nodeid] = (tc, observed)
    return _rec


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.failed):
        _OUTCOMES[report.nodeid] = {"outcome": report.outcome, "duration": round(report.duration, 3),
                                    "longrepr": str(report.longrepr)[-600:] if report.failed else ""}


def pytest_sessionfinish(session, exitstatus):
    rows = []
    for nodeid, res in _OUTCOMES.items():
        tc, observed = _OBSERVED.get(nodeid, (None, ""))
        rows.append({"nodeid": nodeid, "tc": tc, "observed": observed, **res})
    os.makedirs("test-results", exist_ok=True)
    with open("test-results/results.json", "w") as fh:
        json.dump({"exit_status": int(exitstatus), "tests": rows}, fh, indent=2)
