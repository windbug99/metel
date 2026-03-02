# S9 Follow-up: `linear issue -> notion create` 간헐 `not_found`

> Legacy notice (2026-03-02):
> 이 문서는 Telegram/Stage6 운영 맥락의 이슈 추적 문서입니다.
> 현재 제품 실행 경로는 MCP Gateway 중심이며 기준 문서는 `docs/overhaul-20260302.md`입니다.

## 배경
- 시나리오: `linear OPT-47 이슈로 notion에 페이지 생성하세요`
- 현상: 간헐적으로 `error_code=not_found` 발생
- 현재 상태: `backend/agent/orchestrator_v2.py`에 fallback 반영 완료
  - Linear 이슈 조회 실패 시에도 참조 키를 본문에 포함해 Notion 페이지 생성을 계속 진행

## 재현/확인 절차
1. `python -u backend/scripts/run_stage6_telegram_e2e.py --chat-id <CHAT_ID> --poll-timeout-sec 45 --reset-pending --reset-between-chains`
2. `docs/reports/stage6_telegram_e2e_latest.json`에서 `S9` 결과 확인
3. `command_logs.detail`에서 `skill_v2_rollout`, `router_source`, `error_code` 확인

## 관찰 지표
- 목표: S9 `not_found` 0건 (N회 반복 기준)
- 권장 샘플: 최소 10회

## 후속 개선 후보
1. Linear 조회 쿼리 보강
- `OPT-47` 키 조회 실패 시 제목/최근 이슈 fallback 재시도 횟수 확장

2. 에러 가시성 강화
- `S9` 실패 시 `detail`에 `issue_ref`, 검색 쿼리, 후보 수를 명시

3. 테스트 보강
- `backend/tests/test_orchestrator_v2.py`의 fallback 케이스 유지
- 간헐 실패 패턴(검색 결과 0건/지연)을 모의하는 케이스 추가
