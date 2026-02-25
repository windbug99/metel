# work-20260225-llm-route-hardening-plan

## 1) 배경
- 현재 일부 복합 요청(예: "오늘 일정 중 회의만 Linear 이슈 생성")이 `LLM 분석 -> autonomous 실행` 경로에서 `replan_limit`로 실패한다.
- 단기적으로는 deterministic 템플릿 라우팅으로 보완했지만, 중장기적으로는 LLM 경로 자체의 복원력/정확도를 높여야 한다.

## 2) 목표
- 전용 하드코딩 규칙 없이도 LLM 경로에서 복합 요청을 안정적으로 처리한다.
- `autonomous` 실패의 주 원인(`replan_limit`, tool selection drift, incomplete intent slots)을 구조적으로 줄인다.

## 3) 성공 기준 (Gate/SLO)
- Autonomous gate
  - `autonomous_attempt_rate >= 90%`
  - `autonomous_success_rate >= 90%`
  - `autonomous_success_over_attempt >= 85%`
  - `fallback_rate <= 10%` (stretch: `<= 5%`)
- 회귀 없음
  - DAG quality gate PASS 유지
  - 기존 Notion/Linear/Google 핵심 시나리오 회귀 테스트 PASS

## 4) 문제 분해
- Intent/slot 표현력 부족
  - "회의만", "A만", "제외", "조건" 같은 필터 조건이 명시적 슬롯으로 유지되지 않음.
- Planner -> Autonomous 인수 불일치
  - Planner 결과가 실행 가능한 tool payload로 충분히 수렴하지 못하면 autonomous가 재계획을 반복.
- Replan 정책 과민
  - 동일 실패 유형에서 재시도/재계획이 반복되어 `replan_limit` 도달.
- 검증 피드백 루프 약함
  - 실패 원인이 구조화된 slot/action 단위로 다시 planner에 반영되지 않음.

## 5) 개선 설계

### 5.1 Intent schema 확장 (필터/범위/대상 명시)
- `intent_contract` 확장 필드 추가:
  - `time_scope`: `today | date_range | explicit_date`
  - `event_filter`: `{ keyword_include: [], keyword_exclude: [] }`
  - `target_scope`: `linear_only | notion_only | notion_and_linear`
  - `result_limit`: 정수
- 예시: "오늘 일정 중 회의만 리니어 이슈 생성"
  - `time_scope=today`
  - `event_filter.keyword_include=["회의"]`
  - `target_scope=linear_only`

### 5.2 Planner 출력 제약 강화
- Planner 출력 검증:
  - tool set이 intent target_scope와 불일치하면 즉시 보정
  - 필수 슬롯 누락 시 실행 진입 금지(clarification or autofill)
- Calendar tool payload 규칙:
  - `today`면 실행 직전 `time_min/time_max/single_events/order_by` 강제 표준화

### 5.3 Autonomous 정책 튜닝
- `replan` 전 가드:
  - 같은 실패 코드/같은 payload 반복 시 재계획 대신 slot 재질문 또는 deterministic fallback
- `replan_limit` 소진 방지:
  - 실패 유형별 분기(`validation`, `auth`, `not_found`)를 독립 처리
- Tool ranking 개선:
  - intent의 `target_scope`/`event_filter`를 ranking prompt에 명시 주입

### 5.4 Verifier 강화
- 완료 조건을 intent 기반으로 명시:
  - `linear_only`인데 notion 생성이 있으면 실패
  - `keyword_include` 조건 미충족 결과가 생성되면 실패
- verifier 실패 시 단순 "다시 시도" 대신 구조화된 remediation 힌트 반환

### 5.5 관측/로그 개선
- `command_logs.detail`에 아래 필드 추가 기록:
  - `intent_time_scope`, `intent_target_scope`, `intent_filter_include`, `autonomous_replan_reason_histogram`
- 대시보드/리포트에 실패 원인 top-N과 슬롯 누락 빈도 노출

## 6) 단계별 실행 계획 (Checklist)

### Phase A: 스키마/검증 기초
- [ ] `intent_contract` 확장 필드 추가
- [ ] planner 출력 검증기(필수 슬롯/타겟 범위) 추가
- [ ] 관련 단위 테스트 추가

### Phase B: 실행 경로 수렴
- [ ] autonomous 입력 정규화 레이어 추가(시간/필터/타겟)
- [ ] 반복 실패 차단 로직 추가(동일 payload + 동일 에러)
- [ ] replan 정책 분기 튜닝

### Phase C: verifier/관측
- [ ] intent-aware verifier 규칙 추가
- [ ] 실패 remediation 힌트 구조화
- [ ] command_logs 스키마/리포트 반영

### Phase D: 롤아웃
- [ ] shadow mode(기존 경로와 병행)
- [ ] canary 10% -> 30% -> 100%
- [ ] gate 기준 충족 시 기본 경로 전환

## 7) 테스트 전략
- 단위 테스트
  - intent parsing/validation (필터/범위/타겟)
  - planner output guard
  - autonomous duplicate-failure blocking
  - verifier intent-rule validation
- 통합 테스트
  - "오늘 일정 중 회의만 리니어 이슈 생성"
  - "오늘 일정 중 회의만 노션 페이지 생성"
  - "오늘 일정 조회"(읽기 전용)
- 실운영 스모크
  - `run_autonomous_gate.sh`, `run_dag_quality_gate.sh`, `check_dag_smoke_result.py`

## 8) 리스크 및 대응
- 리스크: 과도한 제약으로 유연성 저하
  - 대응: strict 모드 플래그화 + 단계적 rollout
- 리스크: verifier false negative 증가
  - 대응: fail-open/closed 정책 분리, shadow 지표 먼저 확인
- 리스크: 로그 필드 확장으로 분석 복잡도 증가
  - 대응: 보고서 템플릿 고정화(top-N 중심)

## 9) 운영 파라미터(초기 제안)
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`
- `LLM_AUTONOMOUS_LIMIT_RETRY_ONCE=true`
- `LLM_AUTONOMOUS_STRICT_TOOL_SCOPE=true`
- `LLM_HYBRID_EXECUTOR_FIRST=true` (롤아웃 초기)
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`

## 10) 완료 정의 (Definition of Done)
- [ ] Autonomous gate 3회 연속 PASS
- [ ] fallback_rate 10% 이하 3일 연속 유지
- [ ] 대표 시나리오(회의만/오늘 조회/복합 생성) 회귀 0건
- [ ] 문서/운영 가이드 업데이트 완료
