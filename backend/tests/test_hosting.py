"""
A hosted copy: the shared sign-in, and Django serving the built UI. No database connection is made.
"""

import base64
import os

import django
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tabletalk.settings")
django.setup()
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from tabletalk.auth import BasicAuth


def _app(monkeypatch, user="demo", password="s3cret"):
    monkeypatch.setenv("APP_USER", user)
    monkeypatch.setenv("APP_PASSWORD", password)
    return BasicAuth(lambda request: HttpResponse("ok"))


def _header(credentials):
    return "Basic " + base64.b64encode(credentials.encode()).decode()


def test_sign_in_is_off_without_credentials(monkeypatch):
    monkeypatch.delenv("APP_USER", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    app = BasicAuth(lambda request: HttpResponse("ok"))
    assert app(RequestFactory().get("/api/datasets/")).status_code == 200


@pytest.mark.parametrize("header", [None, _header("demo:wrong"), _header("other:s3cret"), "Basic not-base64!",
                                    "Bearer abc"])
def test_wrong_or_missing_credentials_get_the_prompt(monkeypatch, header):
    extra = {"HTTP_AUTHORIZATION": header} if header else {}
    response = _app(monkeypatch)(RequestFactory().get("/api/datasets/", **extra))
    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Basic ")


def test_right_credentials_pass(monkeypatch):
    request = RequestFactory().get("/", HTTP_AUTHORIZATION=_header("demo:s3cret"))
    assert _app(monkeypatch)(request).status_code == 200


def test_health_check_needs_no_sign_in(monkeypatch):
    assert _app(monkeypatch)(RequestFactory().get("/healthz")).status_code == 200
    assert _app(monkeypatch)(RequestFactory().get("/healthz/")).status_code == 401


def test_password_may_contain_a_colon(monkeypatch):
    request = RequestFactory().get("/", HTTP_AUTHORIZATION=_header("demo:a:b"))
    assert _app(monkeypatch, password="a:b")(request).status_code == 200


def test_any_page_path_gets_the_ui(tmp_path, monkeypatch):
    from tabletalk.urls import frontend
    (tmp_path / "index.html").write_text("<div id=root></div>")
    monkeypatch.setattr(settings, "FRONTEND_DIR", tmp_path)
    response = frontend(RequestFactory().get("/datasets/3"))
    assert response.status_code == 200
    assert b"root" in b"".join(response.streaming_content)


def test_api_paths_are_not_sent_to_the_ui():
    from django.urls import resolve
    from tabletalk.urls import frontend
    assert resolve("/api/datasets/").func is not frontend
    assert resolve("/datasets/3").func is frontend
    assert resolve("/healthz").func is not frontend
