"""Exceptions and the mapping from Toss API error codes to user-facing text.

Tool results are read by an LLM, so every message says what went wrong *and*
what to do next. Credentials never appear in these strings.
"""

from __future__ import annotations

from typing import Any


class ConfigError(Exception):
    """Required configuration is missing or unusable."""


class TossConnectionError(Exception):
    """The Toss API was unreachable (DNS, TCP, TLS, or timeout)."""

    def user_message(self) -> str:
        return "토스증권 API에 연결하지 못했습니다. 네트워크 상태를 확인하고 잠시 후 다시 시도하세요."


# code -> message. Anything not listed falls back to "{code}: {message}".
_MESSAGES: dict[str, str] = {
    "stock-not-found": "해당 종목을 찾을 수 없습니다. search_symbol로 심볼을 확인하세요.",
    "exchange-rate-not-found": "해당 시각의 환율 정보가 없습니다.",
    "invalid-token": "인증에 실패했습니다. TOSS_CLIENT_ID/TOSS_CLIENT_SECRET를 확인하세요.",
    "expired-token": "인증에 실패했습니다. TOSS_CLIENT_ID/TOSS_CLIENT_SECRET를 확인하세요.",
    "login-user-not-found": "인증에 실패했습니다. TOSS_CLIENT_ID/TOSS_CLIENT_SECRET를 확인하세요.",
    "edge-blocked": "허용되지 않은 요청입니다. 요청 경로와 인증 정보를 확인하세요.",
    "forbidden": "이 요청에 필요한 권한이 없습니다. Open API 이용 신청 상태를 확인하세요.",
    "rate-limit-exceeded": "요청이 몰려 조회에 실패했습니다. 잠시 후 다시 시도하세요.",
    "edge-rate-limit-exceeded": "요청이 몰려 조회에 실패했습니다. 잠시 후 다시 시도하세요.",
    "internal-error": "토스증권 서버 일시 장애입니다. 잠시 후 다시 시도하세요.",
    "maintenance": "토스증권 시스템 점검 중입니다. 잠시 후 다시 시도하세요.",
}


class TossApiError(Exception):
    """A structured error returned by the Toss API."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        status: int | None = None,
        request_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        self.data = data

    @classmethod
    def from_response(cls, status: int, body: Any) -> TossApiError:
        """Parse the Toss error envelope, tolerating malformed bodies."""
        error: dict[str, Any] = {}
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            error = body["error"]

        code = error.get("code") or f"http-{status}"
        data = error.get("data") if isinstance(error.get("data"), dict) else None
        return cls(
            code=str(code),
            message=str(error.get("message") or ""),
            status=status,
            request_id=error.get("requestId"),
            data=data,
        )

    def user_message(self) -> str:
        text = _MESSAGES.get(self.code)
        if text is None:
            text = f"{self.code}: {self.message}" if self.message else self.code

        hint = self._hint()
        return f"{text} ({hint})" if hint else text

    def _hint(self) -> str:
        """Surface the API's own resolution hint for invalid requests."""
        if self.code != "invalid-request" or not self.data:
            return ""

        parts = []
        field = self.data.get("field")
        if field:
            parts.append(f"문제 필드: {field}")
        allowed = self.data.get("allowedValues")
        if isinstance(allowed, list) and allowed:
            parts.append("허용값: " + ", ".join(str(v) for v in allowed))
        return " / ".join(parts)
