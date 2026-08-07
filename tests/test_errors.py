import pytest

from toss_mcp.errors import TossApiError, TossConnectionError


def envelope(code, message="", data=None):
    error = {"requestId": "01HXYZ", "code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"error": error}


def test_parses_envelope():
    err = TossApiError.from_response(404, envelope("stock-not-found", "없는 종목"))

    assert err.code == "stock-not-found"
    assert err.message == "없는 종목"
    assert err.status == 404
    assert err.request_id == "01HXYZ"


@pytest.mark.parametrize(
    "code,expected_fragment",
    [
        ("stock-not-found", "search_symbol"),
        ("rate-limit-exceeded", "잠시 후 다시 시도"),
        ("edge-rate-limit-exceeded", "잠시 후 다시 시도"),
        ("expired-token", "TOSS_CLIENT_ID"),
        ("invalid-token", "TOSS_CLIENT_ID"),
        ("maintenance", "점검"),
        ("internal-error", "일시 장애"),
        ("exchange-rate-not-found", "환율"),
    ],
)
def test_known_codes_get_actionable_messages(code, expected_fragment):
    err = TossApiError.from_response(400, envelope(code))

    assert expected_fragment in err.user_message()


def test_unknown_code_falls_back_to_code_and_message():
    err = TossApiError.from_response(400, envelope("brand-new-code", "무슨 일이 생김"))

    assert err.user_message() == "brand-new-code: 무슨 일이 생김"


def test_invalid_request_surfaces_the_api_hint():
    err = TossApiError.from_response(
        400,
        envelope("invalid-request", "값이 올바르지 않습니다.", {"field": "interval", "allowedValues": ["1m", "1d"]}),
    )

    text = err.user_message()
    assert "interval" in text
    assert "1m" in text and "1d" in text


def test_invalid_request_without_data_still_works():
    err = TossApiError.from_response(400, envelope("invalid-request", "값이 올바르지 않습니다."))

    assert "invalid-request" in err.user_message()


@pytest.mark.parametrize("body", [None, {}, {"error": "not-a-dict"}, "plain text", []])
def test_malformed_bodies_do_not_raise(body):
    err = TossApiError.from_response(500, body)

    assert err.code == "http-500"
    assert err.user_message()


def test_connection_error_has_its_own_message():
    assert "연결하지 못했습니다" in TossConnectionError().user_message()
