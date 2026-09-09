# 성능·회귀·오류 방어 작업

orchestrator: Codex

| 작업 | owner | model | effort | depends_on | parallel_group | files | verification | status |
|---|---|---|---|---|---|---|---|---|
| 캐시 연결·조회 개선 | Codex | gpt-6-astra | high | 분석·설계 | root-python | src/toss_mcp/symbols.py | SQLite 및 검색 회귀 | completed |
| 비정상 응답 방어·테스트 | Codex | gpt-6-astra | high | 분석·설계 | root-python | client.py, auth.py, tests/ | pytest mock 스위트 | completed |

같은 테스트 환경과 파일을 사용해 저장소 내부는 순차 진행한다. 다른 저장소는 별도 Codex 에이전트에서 병렬 수행한다.

검증: .venv/Scripts/python.exe -m pytest -m 'not smoke' -q --tb=short → 159 passed, 14 deselected. 추가 회귀 21개. 초기 sandbox 임시 폴더 권한 오류는 사용자 권한 재실행으로 해결. pytest 캐시 권한 경고 1건은 테스트 성공에 영향 없음. 실제 API smoke 미실행.
