# 성능·회귀·오류 방어 설계

SQLite 연결을 contextmanager로 관리해 commit/rollback 뒤 반드시 닫는다. UPPER(symbol) 표현식 인덱스로 기존 대소문자 조회 의미를 보존한다. 일괄 삽입 튜플은 generator로 전달한다. 공백 검색은 I/O 전에 빈 결과를 반환한다.

Retry-After는 유한한 0 이상 값만 사용하고 잘못된 값은 기존 지수 backoff로 처리한다. 만료시간 변환 OverflowError는 기존 기본값으로 처리한다. 로그는 잘못된 헤더 값 없이 고정 진단문만 남긴다.

전역 캐시/새 서비스/재시도 정책 확대는 도입하지 않는다. SQLite EXPLAIN QUERY PLAN, 추적 연결과 실패 트랜잭션 테스트, mock HTTP로 검증한다.
