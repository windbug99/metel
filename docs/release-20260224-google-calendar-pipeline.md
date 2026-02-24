# Release Note - 2026-02-24

## 요약
- Google Calendar OAuth 연결(UI + API) 추가 및 운영 검증 완료
- Google Calendar 조회 기반 연속 파이프라인 구현 및 운영 검증 완료
  - `Google Calendar(오늘 일정)` -> `Notion 회의록 초안 생성(회의별)` -> `Linear 이슈 생성(회의별)`
- 실패 정책 적용/검증 완료
  - 하나라도 실패 시 전체 실패 처리
  - 생성된 결과에 대해 보상(롤백) 수행 후 실패 반환

## 반영 범위

### 1) Google OAuth / Dashboard
- Backend
  - `POST /api/oauth/google/start`
  - `GET /api/oauth/google/callback`
  - `GET /api/oauth/google/status`
  - `DELETE /api/oauth/google/disconnect`
- Frontend Dashboard
  - Service Connection에 Google Calendar 카드 추가
  - Connect / Disconnect / Connected 상태 표시

### 2) Google Calendar Tool 실행 안정화
- `google_calendar_list_events` 기본 파라미터 자동 주입
  - `calendar_id=primary`
  - 오늘 UTC 범위 `time_min/time_max`
  - `single_events=true`, `order_by=startTime`, `max_results` 기본값
- Google API query key 매핑
  - snake_case -> camelCase
  - 예: `time_min -> timeMin`, `max_results -> maxResults`

### 3) 계획/실행 보정
- 일정 조회 의도에서 `google_calendar_list_events` 우선 선택 보정
- `router_v2`가 `실시간 조회 불가`를 반환하는 경우 legacy 실행기로 폴백하도록 보정
- `google_oauth_status`에서 간헐 `NoneType` 예외 방어 처리

### 4) 연속 파이프라인(회의별 fan-out) 구현
- 요청 패턴:
  - "구글캘린더에서 오늘 회의일정 조회해서 각 회의마다 노션에 회의록 초안 생성하고 각 회의를 리니어 이슈로 등록"
- 동작:
  - 이벤트 목록 조회 -> 각 이벤트 순차 처리
  - Notion 페이지 생성 -> Linear 이슈 생성
- 실패 시:
  - 이미 생성된 Linear/Notion 항목 역순 보상(archive) 수행
  - 최종 실패 응답 반환

## 운영 설정

### 필수 환경변수
- Google OAuth
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REDIRECT_URI` (`https://metel-production.up.railway.app/api/oauth/google/callback`)
  - `GOOGLE_STATE_SECRET`

### 현재 권장 운영값 (2026-02-24 검증 기준)
- `SKILL_RUNNER_V2_ENABLED=false`
  - 이유: `router_v2`의 realtime guard가 일부 실행 가능한 요청을 조기 차단하는 케이스가 있었음
  - 이번 릴리즈에서는 deterministic 경로 신뢰성을 우선

## 검증 결과
- OAuth 검증
  - Google/Linear/Notion 상태 API 정상 응답 확인
  - OAuth callback 후 token upsert 정상 확인
- 기능 검증
  - Google Calendar 오늘 일정 조회 성공 (`200`)
  - Notion 페이지 생성 성공(회의별)
  - Linear 이슈 생성 성공(회의별)
  - Telegram 결과 메시지에 Notion/Linear 링크 다건 출력 확인
- 실패 검증
  - Linear 인증 실패(`401`) 시 전체 실패 + 보상(롤백) 메시지 확인
  - Linear 재연결 후 동일 시나리오 성공 확인

## 알려진 이슈 / 후속 작업
- `next lint` 스크립트는 현재 Next CLI 변경 영향으로 실행 오류가 있어, 프론트 검증은 `tsc --noEmit` 기준으로 수행
- 운영 신뢰성 기준선 유지 후, `router_v2` 재활성화는 별도 게이트로 진행 권장
  - 조건: realtime guard 완화/정교화 + 회귀 테스트 강화

## 변경 파일(주요)
- Backend
  - `backend/app/routes/google.py`
  - `backend/main.py`
  - `backend/agent/tool_specs/google.json`
  - `backend/agent/tool_runner.py`
  - `backend/agent/executor.py`
  - `backend/agent/planner.py`
  - `backend/agent/loop.py`
- Frontend
  - `frontend/app/dashboard/page.tsx`
  - `frontend/public/logos/google.svg`
- Tests
  - `backend/tests/test_agent_registry.py`
  - `backend/tests/test_tool_runner.py`
  - `backend/tests/test_agent_executor.py`
- `backend/tests/test_agent_task_decomposition.py`
- `backend/tests/test_agent_loop.py`

---

## 배포 체크리스트 (1페이지)

### 사전 체크 (Pre-Deploy)
- [ ] `SKILL_RUNNER_V2_ENABLED=false` 유지 확인
- [ ] Railway 환경변수 확인
  - [ ] `GOOGLE_CLIENT_ID`
  - [ ] `GOOGLE_CLIENT_SECRET`
  - [ ] `GOOGLE_REDIRECT_URI=https://metel-production.up.railway.app/api/oauth/google/callback`
  - [ ] `GOOGLE_STATE_SECRET`
- [ ] Google Cloud 설정 확인
  - [ ] OAuth 테스트 사용자에 운영 테스트 계정 포함
  - [ ] 승인된 리디렉션 URI가 Railway callback과 정확히 일치
  - [ ] Google Calendar API 활성화
- [ ] 대시보드 연결 UI 확인
  - [ ] Notion / Linear / Google Connect 버튼 노출
  - [ ] Google 상태 API(`/api/oauth/google/status`) 200 응답
- [ ] 백엔드 테스트 통과 확인
  - [ ] `backend/tests/test_agent_executor.py`
  - [ ] `backend/tests/test_agent_tool_runner.py` 또는 `backend/tests/test_tool_runner.py`
  - [ ] `backend/tests/test_agent_loop.py`
- [ ] 마이그레이션/DB 스키마 영향 없음 확인 (`oauth_tokens` 기존 upsert 경로 유지)

### 배포 직후 체크 (Post-Deploy)
- [ ] `/api/health` 200 확인
- [ ] 대시보드에서 Google Connect 수행
  - [ ] callback 후 `google=connected` 리다이렉트 확인
  - [ ] Google 카드 상태 `Connected` 확인
- [ ] Telegram 단건 조회 스모크 테스트
  - [ ] 요청: `구글캘린더에서 오늘 회의 일정 조회`
  - [ ] 로그: `GET /calendar/v3/calendars/primary/events ... 200`
- [ ] Telegram 연속 파이프라인 스모크 테스트
  - [ ] 요청: `구글캘린더에서 오늘 회의일정 조회해서 각 회의마다 노션에 회의록 초안 생성하고 각 회의를 리니어 이슈로 등록해줘`
  - [ ] 로그: `linear_list_teams` -> `notion_create_page` N회 -> `linear_create_issue` N회
  - [ ] 응답: 처리 건수 + Notion/Linear 링크 목록
- [ ] 실패 경로 스모크 테스트 (권장)
  - [ ] Linear 연결 해제 후 동일 요청
  - [ ] 기대 결과: 전체 실패 + 보상(롤백) 메시지
  - [ ] Linear 재연결 후 성공 재확인
- [ ] command_logs 검증
  - [ ] `agent_plan` 성공/실패 코드가 사용자 응답과 일치
  - [ ] `realtime_data_unavailable` 조기 종료가 재발하지 않는지 확인

### 롤백 기준
- [ ] 아래 중 하나 발생 시 즉시 롤백 또는 기능 플래그 차단
  - [ ] 정상 연결 상태인데도 `realtime_data_unavailable` 반복 발생
  - [ ] Notion/Linear 다건 생성 중 부분 생성 누락 + 보상 실패
  - [ ] OAuth status API 5xx 반복
