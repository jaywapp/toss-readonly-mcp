# toss-mcp

토스증권 Open API 를 MCP 도구로 노출하는 **읽기 전용** 서버입니다.
LLM 이 국내·미국 주식의 시세, 종목 정보, 환율·장 운영 시간, 랭킹을 조회할 수 있습니다.

계좌 조회와 주문(생성·정정·취소)은 **구현하지 않았습니다**. 이 서버는 어떤 부수효과도 일으키지 않습니다.

## 설치

```powershell
git clone <repo> toss-mcp
cd toss-mcp
uv sync
```

`uv` 가 없으면 `python -m pip install uv` 로 설치합니다.

## 설정

`.env.example` 을 `.env` 로 복사하고 자격증명을 채웁니다.
`client_id` / `client_secret` 은 토스증권 WTS 로그인 후 **설정 > Open API** 에서 발급합니다.

| 변수 | 필수 | 기본값 | 용도 |
|------|------|--------|------|
| `TOSS_CLIENT_ID` | ✅ | — | OAuth client_id |
| `TOSS_CLIENT_SECRET` | ✅ | — | OAuth client_secret |
| `TOSS_API_BASE_URL` | | `https://openapi.tossinvest.com` | 엔드포인트 |
| `TOSS_HTTP_TIMEOUT` | | `10` | 요청 타임아웃(초) |
| `TOSS_CACHE_DIR` | | `~/.cache/toss-mcp` | 종목 마스터 SQLite 위치 |
| `TOSS_SYMBOL_TTL_DAYS` | | `7` | 종목 마스터 자동 갱신 주기 |
| `TOSS_SYMBOL_MARKETS` | | `KRX,NASDAQ,NYSE,AMEX` | 종목 마스터 수집 대상 |
| `TOSS_LOG_LEVEL` | | `INFO` | 로그 레벨 |

`.env` 는 커밋하지 마세요. 자격증명은 MCP 설정의 `env` 블록에 넣어도 됩니다.

## 등록

```powershell
claude mcp add --scope user toss -- uv --directory D:\workspace\repositories\toss-mcp run toss-mcp
```

## 도구

### 종목 검색

토스 API 에는 종목명 검색 엔드포인트가 없어서, 상장 종목 목록을 로컬 SQLite 에 캐시해 직접 제공합니다.
첫 검색 시 수집하며 이후 `TOSS_SYMBOL_TTL_DAYS` 마다 자동 갱신됩니다.

| 도구 | 설명 |
|------|------|
| `search_symbol` | 종목명으로 심볼 검색 (`삼성전자` → `005930`) |
| `refresh_symbols` | 종목 마스터 강제 갱신 |

### 시세

| 도구 | 설명 |
|------|------|
| `get_price` | 현재가 (최대 200종목). `include_change=True` 면 전일 대비 등락률 포함 |
| `get_orderbook` | 매수/매도 호가 및 잔량 |
| `get_trades` | 당일 최근 체결 내역 (최대 50건) |
| `get_price_limits` | 당일 상한가·하한가 |
| `get_candles` | 캔들 OHLCV (`1m` / `1d`, 최대 200봉) |

`get_price` 응답에는 로컬 종목 마스터에서 찾은 종목명이 API 추가 호출 없이 붙습니다.

`include_change` 는 기본값이 `False` 입니다. 토스의 현재가 응답에 등락률이 없어서,
켜면 종목마다 일봉을 추가로 조회합니다 (차트 API 는 초당 5회 제한이라 종목이 많으면 느려집니다).

### 종목 정보

| 도구 | 설명 |
|------|------|
| `get_stock_info` | 종목명·시장·통화·상장상태·발행주식수 (최대 200종목) |
| `get_stock_warnings` | 정리매매·단기과열·투자경고/위험·VI 발동 |

### 시장 정보

| 도구 | 설명 |
|------|------|
| `get_exchange_rate` | KRW↔USD 환율 |
| `get_market_calendar` | 국내(`KR`)·미국(`US`) 장 운영 시간, 전일·당일·익일 |

### 랭킹·지표

| 도구 | 설명 |
|------|------|
| `get_rankings` | 상승률·하락률·거래대금·거래량 상위 |
| `get_market_indicators` | 코스피·코스닥 등 시장 지표 현재가 |

## 개발

```powershell
uv run pytest              # 네트워크를 타지 않는 전체 스위트
uv run pytest -m smoke     # 실제 API 호출 (자격증명 필요)
```

## 문서

- 설계: `docs/superpowers/specs/2026-08-04-toss-mcp-design.md`
- 구현 계획: `docs/superpowers/plans/2026-08-04-toss-mcp.md`
- 토스 OpenAPI 스펙: <https://openapi.tossinvest.com/openapi-docs/latest/openapi.json> (v1.2.9 기준)
