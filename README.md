# toss-mcp

토스증권 Open API 를 MCP 도구로 노출하는 **읽기 전용** Claude Code 플러그인입니다.
LLM 이 국내·미국 주식의 시세, 종목 정보, 환율·장 운영 시간, 랭킹을 조회할 수 있습니다.

계좌 조회와 주문(생성·정정·취소)은 **구현하지 않았습니다**. 이 서버는 어떤 부수효과도 일으키지 않습니다.

---

## 1. 토스증권 Open API 신청

플러그인을 설치하기 전에 API 자격증명부터 발급받아야 합니다.

| 단계 | 내용 |
|------|------|
| 1 | **토스증권 계좌**가 있어야 합니다. 없으면 토스 앱에서 먼저 개설합니다. |
| 2 | [토스증권 WTS](https://tossinvest.com) 에 로그인 → **설정 > Open API** 에서 `client_id` / `client_secret` 을 발급받습니다. |
| 3 | 같은 화면 하단 **허용 IP 관리**에서 API 를 호출할 IP 를 등록합니다. |
| 4 | 로컬에 [`uv`](https://docs.astral.sh/uv/) 가 설치되어 있어야 합니다 (`python -m pip install uv`). |

> **3번을 건너뛰면 모든 호출이 403 으로 차단됩니다.** 등록된 허용 IP 목록에 없는 IP 에서의 요청은
> 토스 측에서 거부합니다. 집·회사 등 실행할 환경의 공인 IP 를 등록하세요.
> ISP 가 IP 를 바꾸면 다시 등록해야 합니다.

별도의 심사나 승인 대기는 없습니다. 발급 즉시 사용할 수 있습니다.
`client_secret` 은 발급 화면을 벗어나면 다시 볼 수 없으니 그 자리에서 보관하세요.

---

## 2. 설치

Claude Code 와 Codex 양쪽에서 같은 저장소를 플러그인으로 설치할 수 있습니다.
자격증명을 받는 방식만 다릅니다.

### Claude Code

```
/plugin marketplace add jaywapp/toss-readonly-mcp
/plugin install toss-mcp@toss-readonly-mcp
```

플러그인을 활성화하면 `client_id` / `client_secret` 을 묻는 입력창이 뜹니다.
두 값 모두 민감 정보로 처리되어 `settings.json` 이 아닌 보안 저장소
(macOS Keychain, 그 외 플랫폼은 `~/.claude/.credentials.json`)에 저장됩니다.

가상환경은 `${CLAUDE_PLUGIN_DATA}/venv` 에 만들어져 플러그인을 업데이트해도 재사용됩니다.

설정을 바꾸려면 `/plugin` → toss-mcp → Configure 를 사용합니다.

### Codex

Codex 에는 플러그인 설정값을 묻는 절차가 없습니다. **자격증명을 먼저 환경변수로 등록**한 뒤 설치합니다.

```powershell
[Environment]::SetEnvironmentVariable('TOSS_CLIENT_ID', '<client_id>', 'User')
[Environment]::SetEnvironmentVariable('TOSS_CLIENT_SECRET', '<client_secret>', 'User')
# 새 터미널을 열어 반영

codex plugin marketplace add jaywapp/toss-readonly-mcp
codex plugin add toss-mcp@toss-readonly-mcp
```

`.codex.mcp.json` 의 `env_vars` 가 위 두 변수를 서버 프로세스로 전달합니다.
등록됐는지는 `codex mcp list` 의 `toss` 행에서 확인할 수 있습니다.

Codex 는 플러그인을 `~/.codex/plugins/cache/` 로 복사해 실행하며, 여기에 가상환경이 생깁니다.
Claude Code 와 달리 업데이트하면 다시 만들어집니다.

### 첫 실행

두 플랫폼 모두 첫 호출 때 `uv` 가 의존성을 설치하느라 십여 초 걸립니다.

새 세션에서 "삼성전자 주가 알려줘" 라고 물어보세요.
`search_symbol` → `get_price` 순으로 호출되면 정상입니다.

`TOSS_CLIENT_ID가 설정되지 않았습니다` 가 뜨면 자격증명이 비어 있는 것이고,
403 이 뜨면 허용 IP 등록(1번 3단계)이 안 된 것입니다.

---

## 3. 도구

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

---

## 4. 설정값

플러그인 설정으로 노출되는 것은 자격증명 두 개뿐입니다. 나머지는 환경변수로 조정합니다
(기본값 그대로 두어도 동작합니다).

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `TOSS_CLIENT_ID` | — | OAuth client_id (Claude Code 는 플러그인 설정, Codex 는 환경변수) |
| `TOSS_CLIENT_SECRET` | — | OAuth client_secret (동일) |
| `TOSS_API_BASE_URL` | `https://openapi.tossinvest.com` | 엔드포인트 |
| `TOSS_HTTP_TIMEOUT` | `10` | 요청 타임아웃(초) |
| `TOSS_CACHE_DIR` | `~/.cache/toss-mcp` | 종목 마스터 SQLite 위치 |
| `TOSS_SYMBOL_TTL_DAYS` | `7` | 종목 마스터 자동 갱신 주기 |
| `TOSS_SYMBOL_MARKETS` | `KRX,NASDAQ,NYSE,AMEX` | 종목 마스터 수집 대상 |
| `TOSS_LOG_LEVEL` | `INFO` | 로그 레벨 |

호출량은 토스가 공개한 그룹별 초당 한도(시세 10회, 차트 5회, 종목 5회, 시장정보 3회)에 맞춰
클라이언트에서 미리 조절합니다. 429 를 받아 재시도하는 것보다 싸기 때문입니다.

---

## 5. 플러그인 없이 쓰기

MCP 서버 단독으로도 등록할 수 있습니다. 소스를 직접 고칠 때 이 방식이 편합니다.

```powershell
git clone https://github.com/jaywapp/toss-readonly-mcp.git toss-mcp
cd toss-mcp
uv sync
copy .env.example .env    # client_id / client_secret 채우기

claude mcp add --scope user toss -- uv --directory <절대경로>\toss-mcp run toss-mcp
```

이때는 자격증명을 `.env` 에서 읽습니다. 환경변수가 있으면 그쪽이 우선합니다.
`.env` 는 `.gitignore` 에 있으니 커밋되지 않습니다.

### 개발

```powershell
uv run pytest              # 네트워크를 타지 않는 전체 스위트
uv run pytest -m smoke     # 실제 API 호출 (자격증명 + 허용 IP 등록 필요)
```

---

## 문서

- 설계: `docs/superpowers/specs/2026-08-04-toss-mcp-design.md`
- 구현 계획: `docs/superpowers/plans/2026-08-04-toss-mcp.md`
- 토스 Open API 개요: <https://openapi.tossinvest.com/openapi-docs/overview.md>
- 토스 OpenAPI 스펙: <https://openapi.tossinvest.com/openapi-docs/latest/openapi.json> (v1.2.9 기준)

## 라이선스

MIT
