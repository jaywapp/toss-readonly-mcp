import asyncio

import httpx
import pytest
import respx

from toss_mcp.auth import TokenProvider
from toss_mcp.config import Settings
from toss_mcp.errors import TossApiError
from toss_mcp.ratelimit import RateLimiter

BASE = "https://openapi.tossinvest.com"
TOKEN_URL = f"{BASE}/oauth2/token"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def token_body(token, expires_in=86400):
    return {"access_token": token, "token_type": "Bearer", "expires_in": expires_in}


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "c_abc")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "s_xyz")
    return Settings(_env_file=None)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
async def provider(settings, clock):
    limiter = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    async with httpx.AsyncClient() as http:
        yield TokenProvider(settings, http, limiter, time_fn=clock.time)


@respx.mock
async def test_issues_a_token(provider):
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-1")))

    assert await provider.get_token() == "tok-1"
    assert route.call_count == 1


@respx.mock
async def test_sends_client_credentials_as_form_data(provider):
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-1")))

    await provider.get_token()

    request = route.calls[0].request
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    body = request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=c_abc" in body
    assert "client_secret=s_xyz" in body


@respx.mock
async def test_reuses_an_unexpired_token(provider, clock):
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-1")))

    await provider.get_token()
    clock.now += 100
    assert await provider.get_token() == "tok-1"
    assert route.call_count == 1


@respx.mock
async def test_refreshes_within_the_60s_safety_margin(provider, clock):
    route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json=token_body("tok-1", expires_in=3600)),
            httpx.Response(200, json=token_body("tok-2", expires_in=3600)),
        ]
    )

    await provider.get_token()
    clock.now += 3600 - 59  # inside the margin, but not yet expired

    assert await provider.get_token() == "tok-2"
    assert route.call_count == 2


@respx.mock
async def test_does_not_refresh_just_outside_the_margin(provider, clock):
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-1", expires_in=3600)))

    await provider.get_token()
    clock.now += 3600 - 61

    assert await provider.get_token() == "tok-1"
    assert route.call_count == 1


@respx.mock
async def test_invalidate_forces_a_new_token(provider):
    route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json=token_body("tok-1")),
            httpx.Response(200, json=token_body("tok-2")),
        ]
    )

    await provider.get_token()
    provider.invalidate()

    assert await provider.get_token() == "tok-2"
    assert route.call_count == 2


@respx.mock
async def test_concurrent_callers_issue_only_one_token(provider):
    """Toss invalidates the previous token on re-issue, so a stampede would
    leave most callers holding a dead token."""
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-1")))

    tokens = await asyncio.gather(*(provider.get_token() for _ in range(10)))

    assert tokens == ["tok-1"] * 10
    assert route.call_count == 1


@respx.mock
async def test_rejected_credentials_raise_toss_api_error(provider):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": {"code": "invalid-token", "message": "bad client"}})
    )

    with pytest.raises(TossApiError) as excinfo:
        await provider.get_token()

    assert "TOSS_CLIENT_ID" in excinfo.value.user_message()


@respx.mock
async def test_oauth_standard_error_shape_is_handled(provider):
    """The token endpoint uses the OAuth2 error shape, not the BFF envelope."""
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": "invalid_client", "error_description": "nope"})
    )

    with pytest.raises(TossApiError):
        await provider.get_token()
