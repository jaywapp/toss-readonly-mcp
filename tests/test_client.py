import httpx
import pytest
import respx

from toss_mcp.client import MAX_RATE_LIMIT_RETRIES, TossClient
from toss_mcp.config import Settings
from toss_mcp.errors import TossApiError, TossConnectionError

BASE = "https://openapi.tossinvest.com"
TOKEN_URL = f"{BASE}/oauth2/token"
PRICES_URL = f"{BASE}/api/v1/prices"


def token_body(token="tok-1"):
    return {"access_token": token, "token_type": "Bearer", "expires_in": 86400}


def error_body(code, message=""):
    return {"error": {"requestId": "01H", "code": code, "message": message}}


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "c_abc")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "s_xyz")
    return Settings(_env_file=None)


@pytest.fixture
async def client(settings):
    slept = []

    async def no_wait(seconds):
        slept.append(seconds)

    c = TossClient(settings, sleep_fn=no_wait)
    c.slept = slept  # exposed for assertions
    try:
        yield c
    finally:
        await c.aclose()


@respx.mock
async def test_unwraps_the_result_envelope(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    respx.get(PRICES_URL).mock(
        return_value=httpx.Response(200, json={"result": [{"symbol": "005930", "lastPrice": "72000"}]})
    )

    result = await client.get("/api/v1/prices", "MARKET_DATA", {"symbols": "005930"})

    assert result == [{"symbol": "005930", "lastPrice": "72000"}]


@respx.mock
async def test_sends_bearer_token(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body("tok-abc")))
    route = respx.get(PRICES_URL).mock(return_value=httpx.Response(200, json={"result": []}))

    await client.get("/api/v1/prices", "MARKET_DATA", {"symbols": "005930"})

    assert route.calls[0].request.headers["authorization"] == "Bearer tok-abc"


@respx.mock
async def test_drops_none_params(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    route = respx.get(PRICES_URL).mock(return_value=httpx.Response(200, json={"result": []}))

    await client.get("/api/v1/prices", "MARKET_DATA", {"symbols": "005930", "before": None})

    assert "before" not in route.calls[0].request.url.params
    assert route.calls[0].request.url.params["symbols"] == "005930"


@respx.mock
async def test_retries_once_after_401(client):
    token_route = respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json=token_body("stale")),
            httpx.Response(200, json=token_body("fresh")),
        ]
    )
    data_route = respx.get(PRICES_URL).mock(
        side_effect=[
            httpx.Response(401, json=error_body("expired-token")),
            httpx.Response(200, json={"result": ["ok"]}),
        ]
    )

    assert await client.get("/api/v1/prices", "MARKET_DATA") == ["ok"]
    assert token_route.call_count == 2
    assert data_route.calls[1].request.headers["authorization"] == "Bearer fresh"


@respx.mock
async def test_gives_up_after_a_second_401(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    data_route = respx.get(PRICES_URL).mock(
        return_value=httpx.Response(401, json=error_body("expired-token"))
    )

    with pytest.raises(TossApiError) as excinfo:
        await client.get("/api/v1/prices", "MARKET_DATA")

    assert excinfo.value.code == "expired-token"
    assert data_route.call_count == 2, "one retry only, then surface the error"


@respx.mock
async def test_honours_retry_after_on_429(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    respx.get(PRICES_URL).mock(
        side_effect=[
            httpx.Response(429, json=error_body("rate-limit-exceeded"), headers={"Retry-After": "3"}),
            httpx.Response(200, json={"result": ["ok"]}),
        ]
    )

    assert await client.get("/api/v1/prices", "MARKET_DATA") == ["ok"]
    assert client.slept == [3.0]


@respx.mock
async def test_backs_off_exponentially_without_retry_after(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    respx.get(PRICES_URL).mock(
        side_effect=[
            httpx.Response(429, json=error_body("rate-limit-exceeded")),
            httpx.Response(429, json=error_body("rate-limit-exceeded")),
            httpx.Response(200, json={"result": ["ok"]}),
        ]
    )

    assert await client.get("/api/v1/prices", "MARKET_DATA") == ["ok"]
    # delay = 2**attempt * (1 + random()), so attempt 0 -> [1,2), attempt 1 -> [2,4)
    assert len(client.slept) == 2
    assert 1.0 <= client.slept[0] < 2.0, "1s base plus jitter"
    assert 2.0 <= client.slept[1] < 4.0, "2s base plus jitter"
    assert client.slept[1] > client.slept[0], "backoff must grow"


@respx.mock
async def test_surfaces_rate_limit_error_after_retries_exhausted(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    route = respx.get(PRICES_URL).mock(
        return_value=httpx.Response(429, json=error_body("rate-limit-exceeded"))
    )

    with pytest.raises(TossApiError) as excinfo:
        await client.get("/api/v1/prices", "MARKET_DATA")

    assert excinfo.value.code == "rate-limit-exceeded"
    assert route.call_count == MAX_RATE_LIMIT_RETRIES + 1


@respx.mock
async def test_does_not_retry_a_404(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    route = respx.get(PRICES_URL).mock(return_value=httpx.Response(404, json=error_body("stock-not-found")))

    with pytest.raises(TossApiError) as excinfo:
        await client.get("/api/v1/prices", "MARKET_DATA")

    assert excinfo.value.code == "stock-not-found"
    assert route.call_count == 1


@respx.mock
async def test_connection_failure_becomes_toss_connection_error(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    respx.get(PRICES_URL).mock(side_effect=httpx.ConnectError("no route to host"))

    with pytest.raises(TossConnectionError):
        await client.get("/api/v1/prices", "MARKET_DATA")


@respx.mock
async def test_missing_result_key_is_reported_not_silently_none(client):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_body()))
    respx.get(PRICES_URL).mock(return_value=httpx.Response(200, json={"unexpected": 1}))

    with pytest.raises(TossApiError):
        await client.get("/api/v1/prices", "MARKET_DATA")
