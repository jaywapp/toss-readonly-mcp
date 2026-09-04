# toss-readonly-mcp — Claude Code 지침

공통 프로젝트 규칙은 `AGENTS.md`에 한 곳에서 관리한다. Claude Code는 아래 import를 통해 Codex와 동일한 공통 규칙을 읽는다.

@AGENTS.md

<!-- WORKSPACE-CLAUDE:BEGIN v2 -->

## Claude 전용 협업 메모

- 이 파일은 `orchestrator=Claude`인 작업 트리에서 사용하는 지침이다. 이 세션은 현재 저장소의 Project Agent이며, 워크스페이스 루트 요청의 조정은 루트 `CLAUDE.md`를 따르는 Main 세션에 맡긴다.
- 설계 선택이나 모호한 요구사항은 결론·근거·대안을 짧게 정리한 뒤 구현한다.
- 하위 에이전트·리뷰·구현 위임도 Claude 세션으로 유지하고, 작업 ID·상태·결과를 확인한다. 같은 작업 트리에서 Codex 세션을 함께 사용하지 않는다.
- 다른 도구가 필요한 경우 현재 변경 내용·검증 결과·남은 작업을 핸드오프 문서로 남기고 별도 작업 트리에서 시작한다.
- 웹 페이지 또는 주요 UX/UI 작업이면 운영 구현 전에 서로 다른 콘셉트의 샘플 페이지 3종을 만들고 사용자 선택을 받는다. 선택 전에는 구현을 시작하지 않으며, 샘플은 `docs/ux-concepts/<slug>/`에 기록한다.
- UX/UI 작업에서는 `impeccable`과 `design-taste-frontend` 스킬을 사용하고, 각 스킬의 `SKILL.md`와 pre-flight 지침을 따른다.
- 프로젝트 고유 규칙은 이 파일의 `프로젝트별 메모`에만 추가하고 공통 규칙을 복제하지 않는다.
- 구현 요청을 받으면 먼저 `docs\<slug>-analysis.md`, `docs\<slug>-design.md`, `docs\<slug>-tasks.md` 세 문서를 준비한다. 부족한 정보는 구현 전에 사용자에게 일괄 질문한다.
- `*-tasks.md`의 각 작업에 `owner`, `model`, `effort`, `depends_on`, `parallel_group`을 채우고, 독립 작업은 Claude 서브에이전트로 병렬 위임한다.
- 핵심 요구사항이 답변되지 않았으면 `blocked`로 기록하고 임의 구현하지 않는다.

<!-- WORKSPACE-CLAUDE:END -->

## 프로젝트별 메모

- Claude가 반드시 먼저 읽을 문서:
- 도메인 용어·사용자 역할:
- 리뷰 시 중점 항목:
- 프로젝트 고유 금지 사항:
