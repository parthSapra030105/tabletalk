"""Rate limits: wait out a per-minute limit, give up at once on a daily quota (so the caller can fall back)."""

import httpx
import pytest
from openai import RateLimitError

import llm


def _rate_limit(delay):
    body = [{"error": {"code": 429, "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                                   "retryDelay": delay}]}}]
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    return RateLimitError(f"Error code: 429 - {body}", response=response, body=body)


class FakeClient:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0
        self.chat = self
        self.completions = self

    def create(self, **_):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return "response"


@pytest.fixture
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    return slept


def test_a_per_minute_limit_is_waited_out(monkeypatch, waits):
    fake = FakeClient([_rate_limit("34s")])
    monkeypatch.setattr(llm, "client", lambda: fake)
    assert llm._create("m", {}) == "response"
    assert fake.calls == 2 and waits == [35.0]


def test_a_daily_quota_raises_at_once(monkeypatch, waits):
    fake = FakeClient([_rate_limit("83795s")])
    monkeypatch.setattr(llm, "client", lambda: fake)
    with pytest.raises(RateLimitError):
        llm._create("m", {})
    assert fake.calls == 1 and waits == []


def test_retries_are_capped(monkeypatch, waits):
    fake = FakeClient([_rate_limit("5s")] * 5)
    monkeypatch.setattr(llm, "client", lambda: fake)
    with pytest.raises(RateLimitError):
        llm._create("m", {})
    assert fake.calls == llm.RATE_LIMIT_RETRIES + 1
