# toss-mcp 설계

- 작성일: 2026-08-04
- 상태: 승인됨
- 저장소: `D:\workspace\repositories\toss-mcp`

## 목적

토스증권 Open API 를 MCP 도구로 노출해, LLM 이 국내·미국 주식의 시세와 종목 정보를 조회할 수 있게 한다.
"삼성전자 주가 얼마야" 같은 자연어 질문에 답하는 것이 주 용도다.

## 범위

포함:

- 시세 — 현재가, 호가, 체결, 상/하한가, 캔들(OHLCV)
- 종목 정보 — 종목 기본 정보, 매수 유의사항
- 시장 정보 — KRW↔USD 환율, 국내·미국 장 운영 시간
- 종목 검색 — 종목명 → 심볼 변환 (토스 API 에 없는 기능이라 자체 구현)

제외:

- 계좌·자산 조회 (계좌 목록, 보유 주식, 매수가능금액)
- 주문 (생성·정정·취소)

제외 이유: `X-Tossinvest-Account` 헤더가 필요하고 자산 정보가 LLM 컨텍스트에 유입된다.
주문은 AI 가 실제 매매를 실행할 수 있게 되어 사고 위험이 크다.
전 도구가 읽기 전용이므로 이 서버는 부수효과를 일으키지 않는다.

## 참조

- API 문서: `D:\workspace\repositories\toss\` (비공식 한국어 레퍼런스, 스펙 `v1.1.5`)
- 라이브 OpenAPI 스펙: <https://openapi.tossinvest.com/openapi-docs/latest/openapi.json>
- Base URL: `https://openapi.tossinvest.com`

## 스택

- Python 3.11+
- `uv` — 의존성·실행
- `fastmcp` — MCP 서버
- `httpx` — HTTP 클라이언트
- `pydantic` / `pydantic-settings` — 응답 모델 및 설정
- `finance-datareader` — 종목 마스터 수집
- `pytest` + `respx` — 테스트

## 아키텍처

### 디렉터리 구조

```
toss-mcp/
├── pyproject.toml            # uv 프로젝트, entry point: toss-mcp
├── .env.example
├── .gitignore                # .env, __pycache__, .venv, *.db
├── README.md
├── docs/superpowers/specs/   # 설계 문서
├── src/toss_mcp/
│   ├── __init__.py
│   ├── config.py             # 환경변수 → Settings
│   ├── server.py             # FastMCP 인스턴스, 도구 등록
│   ├── auth.py               # 토큰 발급·캐시·자동 갱신
│   ├── ratelimit.py          # API 그룹별 토큰 버킷
│   ├── client.py             # 토스 API HTTP 클라이언트
│   ├── errors.py             # 토스 에러 → LLM 친화 메시지
│   ├── models.py             # 응답 스키마 (pydantic)
│   ├── symbols.py            # 종목 마스터 수집·캐시·검색
│   └── tools/
│       ├── symbols.py        # search_symbol, refresh_symbols
│       ├── market_data.py    # 시세 도구
│       ├── stock_info.py     # 종목 정보 도구
│       └── market_info.py    # 환율·장 운영 도구
└── tests/
```

### 모듈 경계

각 모듈은 하나의 책임만 가진다.

| 모듈 | 하는 일 | 의존 |
|------|---------|------|
| `config.py` | 환경변수를 읽어 `Settings` 로 노출 | 없음 |
| `auth.py` | access token 확보 (`get_token()` 하나) | `config` |
| `ratelimit.py` | API 그룹별 요청 허가 (`acquire(group)`) | `config` |
| `client.py` | 인증·레이트리밋·재시도를 적용한 HTTP 호출 | `auth`, `ratelimit`, `errors` |
| `symbols.py` | 종목명↔심볼 조회 | `config` (토스 API 와 무관) |
| `tools/*` | MCP 도구 정의, 입력 검증, 응답 정리 | `client`, `symbols`, `models` |

`client.py` 는 도구를 모르고, `tools/` 는 HTTP 를 모른다.
`symbols.py` 는 토스 API 와 완전히 독립적이라 단독으로 테스트할 수 있다.

## 설정 (환경변수)

`pydantic-settings` 로 `config.py` 한 곳에서 읽는다.
조회 순서: 프로세스 환경변수 → `.env` 파일.
MCP 서버는 셸 환경을 상속받지 못하는 경우가 있어 `.env` 폴백이 필요하다.

| 변수 | 필수 | 기본값 | 용도 |
|------|------|--------|------|
| `TOSS_CLIENT_ID` | ✅ | — | OAuth client_id |
| `TOSS_CLIENT_SECRET` | ✅ | — | OAuth client_secret |
| `TOSS_API_BASE_URL` | | `https://openapi.tossinvest.com` | 엔드포인트 |
| `TOSS_HTTP_TIMEOUT` | | `10` | 요청 타임아웃 (초) |
| `TOSS_CACHE_DIR` | | `~/.cache/toss-mcp` | 종목 마스터 SQLite 위치 |
| `TOSS_SYMBOL_TTL_DAYS` | | `7` | 마스터 자동 갱신 주기 |
| `TOSS_SYMBOL_MARKETS` | | `KRX,NASDAQ,NYSE,AMEX` | 수집 대상 시장 |
| `TOSS_LOG_LEVEL` | | `INFO` | 로그 레벨 |

필수값 누락 시 프로세스를 종료하지 않는다. 기동 로그에 경고를 남기고, 도구 호출 시
`TOSS_CLIENT_ID 가 설정되지 않았습니다. .env 또는 MCP 설정의 env 블록에 추가하세요.`
같은 실행 가능한 메시지를 반환한다. 프로세스가 죽으면 MCP 클라이언트에 원인 불명으로 보인다.

시크릿은 로그·에러 메시지·도구 응답 어디에도 출력하지 않는다.

## 인증

`POST /oauth2/token`, `grant_type=client_credentials`, `application/x-www-form-urlencoded`.

- 발급받은 토큰과 만료 시각을 프로세스 메모리에 보관한다. 디스크에 쓰지 않는다.
- 만료 **60초 전**에 선제 재발급한다.
- 클라이언트당 유효 토큰이 1개뿐이고 **재발급 시 이전 토큰이 즉시 무효화**되므로,
  동시 요청이 각자 재발급하지 않도록 `asyncio.Lock` 으로 직렬화한다.
- 401 `expired-token` / `invalid-token` 수신 시 **1회 한정** 재발급 후 재시도한다.
  두 번째도 401 이면 자격증명 문제로 보고 에러를 올린다.

## Rate limit

API 그룹별 토큰 버킷을 클라이언트 측에 두고 선제 제어한다.

| 그룹 | 한도 | 해당 도구 |
|------|------|-----------|
| `AUTH` | 5/s | 토큰 발급 |
| `MARKET_DATA` | 10/s | 현재가·호가·체결·상하한가 |
| `MARKET_DATA_CHART` | 5/s | 캔들 |
| `STOCK` | 5/s | 종목 정보·유의사항 |
| `MARKET_INFO` | 3/s | 환율·장 운영 |

429 수신 시: `Retry-After` 헤더 값을 우선 존중하고, 없으면 지수 백오프(1→2→4초)에 jitter 를 더해
**최대 3회** 재시도한다. 3회 실패 시 "요청이 몰려 조회에 실패했습니다. 잠시 후 다시 시도하세요."로 반환한다.

응답 헤더 `X-RateLimit-Remaining` 은 로그에만 남긴다 (도구 응답에 포함하지 않는다 — LLM 컨텍스트 낭비).

## 종목 마스터 (`symbols.py`)

토스 API 에는 종목명 검색 엔드포인트가 없다. `/api/v1/stocks` 도 심볼을 넣어야 이름이 나온다.
따라서 종목명 → 심볼 변환을 자체적으로 해결한다.

**수집** — `FinanceDataReader` 로 `TOSS_SYMBOL_MARKETS` 의 각 시장 목록을 받는다
(`fdr.StockListing('KRX')`, `('NASDAQ')`, `('NYSE')`, `('AMEX')`).
FDR 의 반환 컬럼명은 버전에 따라 다르므로 구현 시 실제 컬럼을 확인해 매핑한다.

**저장** — `{TOSS_CACHE_DIR}/symbols.db` (SQLite).
스키마: `symbol`, `name`, `english_name`, `market`, `updated_at`.
`name` 과 `symbol` 에 인덱스를 건다.

**갱신** — 캐시가 `TOSS_SYMBOL_TTL_DAYS` 보다 오래되면 다음 검색 시 자동 갱신.
`refresh_symbols` 도구로 수동 갱신도 가능.

**lazy 로딩** — FDR 수집은 수십 초가 걸릴 수 있다. 서버 기동을 막지 않도록
**첫 검색 요청 때** 수집한다. 수집 중 다른 요청이 들어오면 기다린다 (락으로 중복 수집 방지).

**검색 랭킹** — 다음 순서로 후보를 모으고, 앞 단계에서 채워지면 뒤는 보지 않는다.

1. 심볼 정확 일치 (`005930`, `AAPL`)
2. 종목명 정확 일치 (`삼성전자`)
3. 종목명 접두 일치 (`삼성` → `삼성전자`, `삼성물산`, …)
4. 종목명 부분 일치

동일 단계 내에서는 보통주 우선, 그다음 종목명 길이 오름차순으로 정렬한다
(`삼성전자` 가 `삼성전자우` 보다 먼저).
후보가 여러 개면 그대로 반환하고, 어느 것인지는 LLM 이 사용자에게 되묻게 한다.

## 도구

### 종목 검색

| 도구 | 파라미터 | 반환 |
|------|----------|------|
| `search_symbol` | `query`, `market?`, `limit=10` | `[{symbol, name, market}]` |
| `refresh_symbols` | — | `{markets, count, updated_at}` |

### 시세

| 도구 | 파라미터 | Rate limit 그룹 |
|------|----------|-----------------|
| `get_price` | `symbols` (최대 200), `include_change=False` | `MARKET_DATA` |
| `get_orderbook` | `symbol` | `MARKET_DATA` |
| `get_trades` | `symbol`, `count?` (최대 50) | `MARKET_DATA` |
| `get_price_limits` | `symbol` | `MARKET_DATA` |
| `get_candles` | `symbol`, `interval`, `count?` (최대 200), `before?`, `adjusted?` | `MARKET_DATA_CHART` |

`get_price` 응답에는 로컬 종목 마스터에서 찾은 **종목명을 붙여** 반환한다 (API 추가 호출 없음).
마스터에 없는 심볼이면 이름 없이 반환하고 실패로 처리하지 않는다.

**`include_change`** — `PriceResponse` 에는 등락률도 전일 종가도 없다 (`symbol`, `timestamp`,
`lastPrice`, `currency` 뿐). `include_change=True` 일 때만 종목별로 일봉 2개를 추가 조회해
전일 종가 대비 등락액·등락률을 계산한다. 기본값이 `False` 인 이유는 이 옵션이
종목 수만큼 `MARKET_DATA_CHART`(5/s) 호출을 발생시켜 응답이 느려지기 때문이다.

### 종목 정보

| 도구 | 파라미터 | Rate limit 그룹 |
|------|----------|-----------------|
| `get_stock_info` | `symbols` (최대 200) | `STOCK` |
| `get_stock_warnings` | `symbol` | `STOCK` |

### 시장 정보

| 도구 | 파라미터 | Rate limit 그룹 |
|------|----------|-----------------|
| `get_exchange_rate` | `base='USD'`, `quote='KRW'`, `date_time?` | `MARKET_INFO` |
| `get_market_calendar` | `country` (`KR`/`US`), `date?` | `MARKET_INFO` |

### 응답 크기

도구 응답은 전부 LLM 컨텍스트에 들어간다. 이 서버에서 실제로 돈이 드는 유일한 부분이다
(토스 API 호출 자체는 무료). 따라서 호가 10단계, 체결 50건, 캔들 200봉 같은 큰 응답은
스펙의 모든 필드를 그대로 흘리지 않고 필요한 필드만 추려 반환한다.
`decimal` 문자열은 그대로 유지한다 (부동소수점 변환으로 정밀도를 잃지 않기 위해).

## 에러 처리

토스는 모든 에러를 `{"error": {requestId, code, message, data}}` envelope 으로 내려준다.
`errors.py` 가 이를 LLM 이 읽고 다음 행동을 결정할 수 있는 문장으로 변환한다.

| 상황 | 반환 메시지 |
|------|-------------|
| `stock-not-found` | 해당 종목을 찾을 수 없습니다. `search_symbol` 로 심볼을 확인하세요. |
| `invalid-request` | 요청이 올바르지 않습니다: {message} (+ `data` 의 힌트) |
| `expired-token` (재시도 후) | 인증에 실패했습니다. `TOSS_CLIENT_ID`/`TOSS_CLIENT_SECRET` 를 확인하세요. |
| `rate-limit-exceeded` (재시도 소진) | 요청이 몰려 조회에 실패했습니다. 잠시 후 다시 시도하세요. |
| `exchange-rate-not-found` | 해당 시각의 환율 정보가 없습니다. |
| `maintenance` / `internal-error` | 토스증권 서버 일시 장애입니다. 잠시 후 다시 시도하세요. |
| 그 외 | {code}: {message} |

`requestId` 는 로그에 남기고 도구 응답에는 포함하지 않는다.
네트워크 타임아웃·연결 실패는 토스 에러가 아니므로 별도로 "토스증권 API 에 연결하지 못했습니다"로 처리한다.

## 테스트

`pytest` + `respx` 로 HTTP 를 목킹한다. 기본 테스트 스위트는 네트워크를 타지 않는다.

커버 대상:

- `auth` — 최초 발급, 만료 전 재사용, 만료 60초 전 선제 갱신, 401 후 1회 재시도, 동시 요청 직렬화
- `ratelimit` — 그룹별 버킷 독립성, 429 시 `Retry-After` 존중, 백오프 3회 후 포기
- `symbols` — 검색 랭킹 4단계 순서, 보통주 우선, TTL 만료 시 갱신, lazy 로딩 중복 수집 방지
- `errors` — 각 에러 코드 → 메시지 매핑
- `tools` — 파라미터 검증(심볼 200개 초과, 체결 50건 초과 등), `get_price` 종목명 부착,
  `include_change` 계산, 마스터에 없는 심볼 처리

실제 API 를 호출하는 스모크 테스트는 `@pytest.mark.smoke` 로 분리하고 자격증명이 있을 때만 실행한다.

## 등록

```
claude mcp add --scope user toss -- uv --directory D:\workspace\repositories\toss-mcp run toss-mcp
```

자격증명은 `toss-mcp/.env` 에 두거나 MCP 설정의 `env` 블록에 넣는다. `.env` 는 커밋하지 않는다.

## 구현 시 확인할 항목

- `get_candles` 의 `interval` enum 값 — 로컬 문서에 누락. 라이브 OpenAPI 스펙에서 확인한다.
- `FinanceDataReader` 각 시장의 반환 컬럼명 — 버전에 따라 다르므로 실제 값을 보고 매핑한다.
- 기존 `D:\workspace\repositories\toss\.env` 의 `API_KEY`/`SECRET_KEY` 를 재사용할지,
  이 레포에 별도 `.env` 를 둘지 사용자에게 확인한다.
