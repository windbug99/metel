# V1 Removal Plan (Draft)

## 목표
- Skill V2 100% 운영 전환 이후 V1 라우팅/실행 경로를 제거해 코드 복잡도를 낮춘다.

## 전제 조건
- 운영 게이트 PASS 유지 (`v2_success_rate >= 0.85`, `v2_error_rate <= 0.15`)
- 최근 운영 E2E에서 핵심 시나리오 통과
- 롤백 경로(플래그 기반) 문서화

## 제거 범위(초안)
1. V1 실행 분기 정리
- `backend/agent/loop.py` 내 V1 우회/혼합 분기 정리
- V2 우선 경로만 남기고 dead path 제거

2. 레거시 에러/메시지 정리
- V1 전용 에러 코드와 변환 로직 제거
- 텔레그램 응답 헬퍼에서 미사용 분기 정리

3. 테스트 정리
- V1 전용 테스트 제거/대체
- V2 기준 회귀 테스트 유지/강화

4. 문서 정리
- 운영 runbook에서 V1 관련 플래그/절차 제거
- 마이그레이션 문서 완료 상태로 전환

## PR 구성 제안
1. PR-1: V1 분기 제거 + 테스트 갱신 (기능 변경 최소화)
2. PR-2: 텔레그램 응답/에러 코드 정리
3. PR-3: 문서/운영 가이드 정리

### PR-1 착수 기록 (2026-02-23)
- `backend/agent/executor.py` 미사용 레거시 실행기 함수 제거:
  - `_execute_linear_plan`
  - `_execute_notion_plan`
- `backend/agent/loop.py` shadow 모드 legacy 반환 제거:
  - V2 실행 성공 시 shadow 여부와 무관하게 V2 결과 반환
  - `test_agent_loop.py` shadow 관련 기대값을 V2 기준으로 갱신
- 회귀 확인:
  - `tests/test_agent_executor.py` 통과
  - `tests/test_agent_loop.py` 통과
  - `tests/test_orchestrator_v2.py` 주요 경로 통과

### PR-2 착수 기록 (2026-02-23)
- `backend/app/routes/telegram.py` 레거시 command log 컬럼 fallback 제거:
  - `command_logs` insert 실패 시 legacy payload 재시도 분기 삭제
  - 운영 스키마 기준 단일 payload 기록만 유지
- 회귀 확인:
  - `tests/test_telegram_route_helpers.py` 통과
  - `tests/test_telegram_command_mapping.py` 통과

### PR-3 착수 기록 (2026-02-23)
- 운영/마이그레이션 문서 정합화:
  - `docs/stage6_run_commands.md` 현재 운영 기준(100%) 반영
  - `docs/stage6_e2e_test_sheet.md` 삭제 정책(`delete_disabled`) 반영
  - `docs/skills_migration.md` shadow/V1 응답 관련 구문을 현재 동작 기준으로 갱신
  - `docs/intent_JSON_migration.md` PR-1/PR-2 진행 기록 추가

## 롤백 전략
- PR 머지 직후 24h 집중 모니터링
- 이탈 시 즉시 이전 커밋 롤백 또는 feature flag 복구

## 오너/체크리스트
- 오너: Backend Agent
- 체크:
  - [x] 운영 지표 재확인
  - [x] PR-1 생성 (초기 코드 정리 착수)
  - [x] PR-2 생성 (텔레그램 응답/에러코드 정리)
  - [x] PR-3 생성
