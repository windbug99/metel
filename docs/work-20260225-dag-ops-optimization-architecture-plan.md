# DAG 운영 최적화 루프 내장 아키텍처 계획 (2026-02-25)

## 1) 문서 목적
- DAG 실행 안정화 이후 실패율을 지속적으로 낮추기 위해, 로그 기반 정책 최적화 루프를 기본 서비스 구조에 내장한다.
- 본 문서는 차후 구현을 위한 기준 아키텍처, 운영 절차, 단계별 도입 순서를 정의한다.

## 2) 목표와 비목표
### 목표
- 실행 실패 원인을 구조화 로그로 수집하고 주기적으로 평가한다.
- 평가 결과를 정책 추천으로 변환하고, 승인 기반으로 안전하게 반영한다.
- canary 승격/보류/롤백을 표준화하여 운영 리스크를 통제한다.
- 모델 재학습 없이도 정책 튜닝으로 성공률과 재현성을 개선한다.

### 비목표
- 온라인 자동 파인튜닝 자동화
- 무승인 정책 즉시 반영
- 전 서비스 동시 빅뱅 전환

## 3) 기본 서비스 구조에 포함할 컴포넌트
## 3.1 Runtime Plane (요청 처리)
- `Orchestrator (DAG Executor)`:
  - plan 검증, 노드 실행, 보상, 최종 응답 생성
- `Tool/Skill Runner`:
  - 계약 기반 입력/출력 검증, provider 호출, 오류 코드 표준화
- `Verifier`:
  - fan-in 정합성, 완료 조건 검증

## 3.2 Observability Plane (수집/집계)
- `Structured Log Writer`:
  - `command_logs` + pipeline artifact 기록
- `Metrics Aggregator`:
  - 최근 윈도우(예: 1일/3일) 기준 KPI 집계
- `Quality Report Generator`:
  - 게이트 결과 JSON/Markdown 생성

## 3.3 Policy Plane (평가/결정/적용)
- `Gate Evaluator`:
  - 성공률/오류율/지연/검증 실패율 기준 PASS/FAIL
- `Decision Engine`:
  - `promote | hold | rollback` 결정 + 권장 정책 산출
- `Policy Applier`:
  - allowlist 키만 env 반영, 기본 dry-run

## 3.4 Control Plane (운영)
- `Ops Runner (cron/manual)`:
  - 평가 -> 결정 -> 반영 체인 실행
- `Approval Step`:
  - 운영자 승인 후 apply
- `Rollback Trigger`:
  - 임계치 이탈 시 즉시 이전 정책 복귀

## 4) 데이터 계약 (필수)
## 4.1 실행 로그 필드
- 공통:
  - `request_id`, `user_id`, `created_at`, `status`, `error_code`
- DAG:
  - `pipeline_run_id`, `node_id`, `node_type`, `attempt`, `duration_ms`
  - `verification_reason`, `fallback_reason`, `execution_mode`, `plan_source`
- 품질:
  - `idempotency_key`, `compensation_status`, `fanout_total`, `fanout_failed`

## 4.2 KPI 정의
- `pipeline_success_rate = succeeded_runs / total_runs`
- `verification_failed_rate = verification_failed / total_runs`
- `fallback_rate = fallback_runs / total_runs`
- `p95_latency = p95(duration_ms)`
- `compensation_failed_rate = compensation_failed / compensation_attempts`

## 5) 운영 사이클 표준
1. 평가
- 스크립트 실행으로 품질 리포트 생성
- 예: `run_autonomous_gate.sh`, `run_skill_v2_rollout_gate.sh`

2. 결정
- 리포트 기반으로 승격/보류/롤백 판단
- 예: `decide_skill_v2_rollout.py`

3. 반영
- 추천 정책 dry-run 확인 후 승인 적용
- 예: `apply_agent_policy_recommendations.py`, `apply_skill_v2_rollout_decision.py`

4. 검증
- 반영 후 동일 KPI로 재평가
- 기준 미충족 시 자동 롤백

## 6) 안전장치 (필수)
- 정책 변경 allowlist:
  - 허용된 env 키만 수정
- 승인 절차:
  - 자동 추천 가능, 무승인 자동 반영 금지
- 점진 배포:
  - `0 -> 10 -> 30 -> 60 -> 100`
- 롤백 기준:
  - 성공률 10%p 이상 급락
  - auth/server 오류 2배 이상 급증
  - p95 임계치 초과
- 보안:
  - 민감정보 마스킹 기본
  - 사용자 원문 최소 수집

## 7) 단계별 도입 로드맵
## Phase A: 관측 고정 (1주)
- 로그 스키마 확정 및 누락 필드 보강
- DAG 품질 리포트 초안(`dag_quality_latest.json`) 생성
- 완료 기준:
  - 최소 샘플 기준 리포트 자동 생성 가능

## Phase B: 게이트/결정 자동화 (1주)
- DAG 전용 게이트 스크립트 추가
- 승격/보류/롤백 결정 로직 추가
- 완료 기준:
  - PASS/FAIL + action 제안 자동 산출

## Phase C: 승인 반영 + 롤백 자동화 (1주)
- 정책 반영 dry-run/apply 경로 분리
- 임계치 이탈 시 롤백 스위치 자동 수행
- 완료 기준:
  - 운영자 승인 후 5분 내 정책 반영/복귀 가능

## Phase D: 운영 내재화 (지속)
- 일간/주간 운영 루틴 고정
- 장애 회고를 지표/규칙에 재반영
- 완료 기준:
  - 월 단위로 실패율/검증 실패율 감소 추세 확인

## 8) 구현 작업 백로그 (우선순위)
1. `eval_dag_quality.py` 추가
- DAG 오류코드/정합성/보상 지표 집계

2. `run_dag_quality_gate.sh` 추가
- 리포트 생성 + PASS/FAIL 반환

3. `decide_dag_policy.py` 추가
- gate 결과를 `promote|hold|rollback`으로 변환

4. `apply_dag_policy_recommendations.py` 추가
- allowlist env 반영(dry-run 기본)

5. 운영 사이클 스크립트 추가
- `run_dag_optimization_cycle.sh` (gate -> decide -> apply)

## 9) 책임 분리 (RACI-lite)
- Backend:
  - 로그 스키마, 게이트/결정/적용 스크립트 구현
- SRE/운영:
  - 승인/롤백, 임계치 관리, 스케줄 운영
- Product:
  - KPI 목표치 설정, 승격 기준 승인

## 10) 구현 시 주의사항
- 기존 `skills_migration`/`hybrid learning loop`와 중복 구현하지 않고 재사용 우선
- DAG 경로와 비-DAG 경로의 지표를 혼합 집계하지 않는다(리포트 분리)
- 운영 환경에서 preflight(환경변수/Supabase 연결) 실패 시 fail-closed

## 11) Definition of Done
- DAG 품질 게이트 리포트가 일 단위로 자동 생성된다.
- 권장 정책이 dry-run으로 자동 산출되고 승인 후 반영된다.
- 롤백 트리거 동작이 검증된다.
- 2주 연속으로 핵심 KPI 중 최소 2개 이상 개선 추세를 보인다.

## 12) 다음 액션 (실행 제안)
1. `Phase A` 착수: DAG 리포트 스키마/집계 항목 확정
2. `eval_dag_quality.py` 프로토타입 구현
3. 운영 임계치 초안(`success/p95/fallback/verification`) 합의
