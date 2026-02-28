# metel Multi-Agent Architecture Plan (v3)

## SaaS 통합 자율 LLM 자동화 플랫폼 구현 전략

---

# 1. 문서 목적

본 문서는 metel을 **SaaS 통합 자율 LLM 자동화 플랫폼**으로 구현하기 위한:

* 제품 기획 명확화
* OpenClaw 구조적 장점 분석 및 수용 전략
* 멀티 에이전트 아키텍처 설계
* 실행 런타임 설계
* 보안 모델
* 실제 구현 단계별 로드맵

을 통합 정의한다.

---

# 2. metel의 제품 정체성 재정의

---

## 2.1 metel은 무엇인가?

metel은 다음과 같은 플랫폼이다:

> 여러 SaaS를 연결하고
> LLM이 자율적으로 작업을 계획하지만
> 실행 통제권은 항상 플랫폼이 소유하는 자동화 시스템

---

## 2.2 OpenClaw와의 전략적 관계

OpenClaw는 범용 OS 자율 에이전트다.
metel은 SaaS 통합 자동화 플랫폼이다.

### 비교

| 항목    | OpenClaw      | metel                 |
| ----- | ------------- | --------------------- |
| 실행 범위 | OS/로컬 시스템     | SaaS API              |
| 명령 실행 | system.run 가능 | HTTP API 호출만          |
| 메모리   | 파일 기반         | 구조화 DB                |
| 통제 구조 | LLM 중심        | Orchestrator 중심       |
| 위험 모델 | OS 권한         | OAuth + Policy Engine |

---

## 2.3 metel의 목표 모델

metel은 다음을 결합한다:

* n8n의 안정성
* OpenClaw의 자율 계획 능력
* SaaS 보안 요구사항

---

# 3. OpenClaw에서 전략적으로 수용할 요소

---

## 3.1 Gateway 중심 통합 구조

OpenClaw의 장점:

* 모든 채널을 단일 Gateway로 통합
* Runtime은 Gateway 뒤에 위치

### metel 설계 적용

```text
User / Web / API
        ↓
Metel Gateway
        ↓
Orchestrator
        ↓
Multi-Agent Runtime
```

### 목적

* 모든 SaaS 호출은 Orchestrator 통과
* 실행 로그 중앙 통합
* 승인/정책 통제 일원화

---

## 3.2 System Prompt 동적 구성

OpenClaw는 매 실행마다:

* Tool 목록
* Safety 규칙
* Memory 정보
* Skill 목록

을 동적으로 삽입한다.

### metel 적용 전략

Planner/Executor 호출 시:

* 연결된 서비스만 노출
* Top-K Tool만 제공
* tenant policy 요약 포함
* 위험도 태그 포함

> Tool 전체 노출 금지 → Tool Retrieval 도입

---

## 3.3 Memory 분리 전략

OpenClaw:

* 파일 기반 기억

metel:

* 구조화 상태 기반

### 3계층 Memory 구조

1️⃣ Execution State

* action produces 저장
* 세션 단위

2️⃣ Audit Log

* append-only
* 리플레이 가능

3️⃣ Long-term Memory

* 요약 기반 저장
* tenant 격리
* PII 필터링

---

## 3.4 Skill → Workflow Template로 재해석

OpenClaw의 Markdown Skill 개념을 다음으로 전환:

> Workflow Template

구성:

* Action Graph
* 기본 Tool 조합
* 정책 힌트
* 성공 기준

예:

```yaml
skill: notion_meeting_workflow
description: 노션 회의 생성 및 슬랙 공유
actions:
  - notion.create_page
  - slack.post_message
```

---

## 3.5 Approval Gate (Policy 중심)

OpenClaw의 실행 승인 개념을 SaaS 정책 모델로 변환

| Risk                | 처리    |
| ------------------- | ----- |
| read                | 자동 허용 |
| write               | 허용    |
| destructive         | 승인 필요 |
| financial           | 승인 필요 |
| external_send + PII | 승인 필요 |

---

# 4. SaaS 자율 LLM 에이전트 아키텍처

---

## 4.1 전체 구조

```text
Gateway
    ↓
Orchestrator (State Machine)
    ↓
Planner Agent
Policy Agent
Executor Agent
Verifier Agent
```

---

## 4.2 책임 분리

### Planner Agent

* 사용자 요청 → Action Plan JSON
* requires / produces 명시
* Tool 후보 제한

### Policy Agent

* 위험도 판단
* OAuth scope 검증
* 승인 요구

### Executor Agent

* input_schema 기반 payload 생성
* MISSING 규칙

### Verifier Agent

* output_schema 검증
* success_criteria 확인
* retry / replan 결정

### Orchestrator

* 실행 루프
* JSON Schema 강제
* retry/backoff
* 상태 저장
* 승인 UX 연결

---

# 5. 실행 런타임 설계

---

## 5.1 Action Plan 기반 실행

```text
User Request
    ↓
Planner
    ↓
Policy Check
    ↓
for action:
    Executor → Payload
    ↓
    Schema Validation
    ↓
    API Call
    ↓
    produces_map 추출
    ↓
    Verifier
    ↓
    State Update
```

---

## 5.2 재플래닝 구조

실패 조건:

* requires 미충족
* output_schema 실패
* success_criteria 미충족

→ Planner 재호출

---

# 6. 실제 구현 계획

---

# Phase 1 — Core Infrastructure (3주)

### 1. Tool Registry 구현

* JSON Schema 기반 정의
* produces_map 추출기
* OAuth scope 모델

### 2. Orchestrator 구현

* 실행 루프
* retry/backoff
* timeout
* JSON Schema Validator
* Result Extractor

### 3. Execution State 저장

* Redis (세션 상태)
* PostgreSQL (audit log)

---

# Phase 2 — LLM 기반 Action 실행 (2주)

### 4. Planner 구현

* Action Plan JSON Schema 강제
* Tool Retrieval 적용

### 5. Executor 구현

* schema-locked payload
* MISSING 규칙

### 6. Verifier 구현

* 코드 중심 검증
* LLM 보조

---

# Phase 3 — Policy 및 승인 시스템 (2주)

### 7. Policy Engine

* risk_level 기반 제어
* scope 확인

### 8. 승인 UX

* destructive 승인
* external_send 승인

---

# Phase 4 — 멀티 에이전트 분리 (3주)

### 9. Planner/Policy/Verifier 독립

### 10. 재플래닝 루프 완성

---

# Phase 5 — Workflow Template (Skill) 도입 (2주)

### 11. Template Registry

### 12. 자동 추천

---

# 7. 보안 설계 원칙

1. LLM은 직접 API 호출하지 않는다
2. 모든 Tool은 Contract 기반
3. 스키마 밖 필드 차단
4. 승인 없는 destructive 실행 0%
5. OAuth scope 검증 필수
6. PII 외부 전송 시 승인

---

# 8. 성공 지표

* 3-step 의존성 자동 처리 성공률 80%+
* Tool 환각률 < 1%
* 승인 없는 destructive 실행 0건
* 실패 시 재플래닝 성공률 70%+
* 완전 리플레이 가능

---

# 9. 최종 설계 철학

metel은 OpenClaw를 모방하지 않는다.

대신 다음을 흡수한다:

* Gateway 중심 구조
* 동적 System Prompt 구성
* Skill 개념
* Approval Gate
* Agent Loop 구조

그러나:

* OS 실행은 배제
* LLM 중심 실행 통제는 배제
* SaaS API 중심으로 재설계

---

# 최종 정의

metel은:

> SaaS 통합 자율 LLM 자동화 플랫폼

* 자율적이지만 통제 가능하고
* 확장 가능하지만 안전하며
* 지능적이지만 예측 가능한 시스템

아래는 기존 문서 에 **“실제 코드 디렉토리 구조 설계”**와 **“MVP 범위 재정의”**를 목적(= OpenClaw 장점 흡수 + SaaS 통합 자율 LLM 에이전트) 관점으로 **통합 반영한 업데이트 본문**입니다.
(그대로 `docs/multi_agent_architecture_plan.md`에 추가/교체해서 사용하시면 됩니다.)

---

# 10. MVP 범위 재정의 (SaaS 통합 자율 LLM 에이전트)

## 10.1 MVP 목표

MVP는 “완전 자율”이 아니라, **안전하고 예측 가능한 자율 실행 루프**를 최소 기능으로 제공한다.

MVP에서 반드시 달성할 것:

* 자연어 요청 → **Action Plan(JSON)** 생성
* **Policy Gate**로 위험 작업 통제(승인/차단)
* **Schema-locked Executor**로 payload 생성 (필수값은 `MISSING`)
* Orchestrator가 **결정적으로 실행**(retry/timeout/state)
* 실행 결과를 **State + Audit Log**로 남기고 리플레이 가능

OpenClaw에서 MVP에 가져올 핵심:

* **Gateway 중심 단일 진입점**
* **런타임에서 동적 System Prompt 조립**
* **Skill(= Workflow Template) 목록 기반 확장**
* **Approval Gate(승인/정책)**
* **Agent Loop(스트리밍/툴 이벤트/재시도/압축) 사고방식**

## 10.2 MVP에서 “하지 않을 것”

* OS/로컬 명령 실행 (OpenClaw의 system.run 류) ❌
* 임의 HTTP 호출(LLM이 URL을 만들어 호출) ❌
* 무제한 도구 노출(전체 도구 목록을 LLM에 제공) ❌
* destructive/financial 자동 실행 ❌ (항상 승인)
* 병렬/분기/조인 등 고급 워크플로우 엔진 (Phase 3+) ❌

## 10.3 MVP 기능 범위

### A. 채널/진입점(Gateway)

* Web API(HTTP)로 요청 수신 (추후 Slack/Telegram 확장)
* 실행 요청/상태 조회 엔드포인트
* (선택) WebSocket 스트리밍: tool event / agent event / final

### B. 지원 SaaS (최소 2~3개)

* Notion: create_page / query_database (read+write)
* Slack: post_message (notify)
* (선택) Google Sheets: get_range (read)

> MVP에서 중요한 건 “서비스 숫자”가 아니라 **requires/produces 의존성 연결이 안정적으로 동작**하는지다.

### C. Tool Registry(Contract)

* tool_id, risk_level, scopes_required
* input_schema/output_schema(JSON Schema)
* produces_map(state key 표준화)

### D. Multi-Agent (초기 4개 유지)

* Planner: Action Plan 생성
* Policy: allow/deny/require_confirm
* Executor: schema-locked payload 생성
* Verifier: pass/fail + retry/ask_user/replan

### E. Orchestrator(Runtime)

* sequential action 실행 루프
* retries/backoff/timeout
* schema validation (input/output)
* produces extraction → state update
* 승인 요청 시 “중단 + 승인 대기” 상태 반환
* audit log 저장(append-only) + replay key

### F. 최소 승인 UX

* require_confirm 상태 반환 시, 프론트/클라이언트에서 “승인/거절” 호출
* 승인 후 동일 run을 이어서 실행

## 10.4 MVP 성공 조건(명확한 테스트 기준)

* 2-step 의존성 플로우 성공률 90%+ (Notion 생성 → Slack 공유)
* `MISSING` 발생 시 “필요 정보만” 질문하고 재개 가능
* 승인 없는 destructive 실행 0건
* 모든 run은 audit log로 재현 가능(replay)
* Tool 환각(등록되지 않은 tool 호출) 0건

---

# 11. 실제 코드 디렉토리 구조 설계 (Python 중심)

> 원칙: OpenClaw처럼 “런타임이 조립하고(Gateway/Prompt/Skill), 실행은 통제된 Runtime(Orchestrator)이 한다”를 코드 구조로 강제한다.

## 11.1 리포지토리 구조(권장)

아래는 **Python + FastAPI** 기준의 현실적인 구조입니다. (단일 repo)

```text
metel/
  apps/
    api/                          # Gateway(API Hub): FastAPI, WebSocket streaming
      main.py
      routers/
        runs.py                   # /runs (create, status, approve, replay)
        tools.py                  # (optional) tool registry introspection
      middleware/
        auth.py                   # tenant/user auth, rate limit
      deps.py
      settings.py
    worker/                       # background workers (Celery/RQ/Arq)
      main.py
      tasks/
        run_execute.py            # execute run loop
        tool_call.py              # tool call wrapper jobs (optional)
  packages/
    core/
      __init__.py
      orchestrator/
        orchestrator.py           # main runtime loop
        models.py                 # ActionPlan, Action, ExecutionState, ExecRecord
        validator.py              # jsonschema validation
        extractor.py              # produces_map extraction (jsonpath-lite)
        replay.py                 # replay serializer & deterministic re-run helper
        prompt_builder.py         # dynamic system prompt assembly (OpenClaw-like)
        tool_retrieval.py         # top-k tools selection (RAG/embedding or rules)
      agents/
        planner.py                # LLM client wrapper + planner prompt
        executor.py               # schema-locked payload generator
        verifier.py               # verifier logic (code-first + LLM fallback)
        policy.py                 # policy logic (rule engine + LLM fallback)
        composer.py               # final response generator (optional)
      registry/
        tool_registry.py          # contract store interface
        contracts/                # tool definitions (yaml/json)
          notion.create_page.json
          slack.post_message.json
        skills/                   # workflow templates (OpenClaw skill-like)
          notion_meeting_workflow.yaml
      policy/
        rules.py                  # allow/deny/require_confirm rules
        pii.py                    # pii detectors/redactors
        scopes.py                 # oauth scope checks
      integrations/
        notion/
          client.py               # Notion API client wrapper (requests/httpx)
          adapters.py             # tool_id -> actual endpoint mapping
        slack/
          client.py
          adapters.py
        google_sheets/
          client.py
          adapters.py
      storage/
        state_store.py            # Redis: session state
        audit_log.py              # Postgres: append-only log
        secrets.py                # token vault interface
      observability/
        tracing.py                # request/run correlation ids
        logging.py                # structured logs
        metrics.py                # counters (tool success rate, retry count)
  docs/
    multi_agent_architecture_plan.md
    schemas/
      action-plan.schema.json
      action-plan.notion.schema.json
    api/
      openapi.md
  scripts/
    dev_run.sh
    seed_contracts.py
  tests/
    unit/
      test_schema_validation.py
      test_produces_extractor.py
      test_policy_rules.py
    integration/
      test_notion_to_slack_flow.py
  pyproject.toml
  README.md
```

## 11.2 디렉토리 설계의 핵심 의도

### A. `apps/api` = Gateway

OpenClaw의 Gateway 장점(단일 진입점)을 metel에서도 강제합니다.

* 인증/요금/레이트리밋
* run 생성/조회/승인/리플레이 API
* (선택) WebSocket 스트리밍으로 “에이전트 이벤트” 제공

### B. `packages/core/orchestrator` = 실행 통제의 단일 소유자

* LLM이 아닌 코드가 실행을 통제(필수)
* schema validation / retry / timeout / state update / audit log
* 승인 대기 상태로 전환(Policy 결과에 따라)

### C. `packages/core/agents` = “제안자” 모듈

* Planner/Executor/Verifier/Policy는 **출력 포맷 강제(JSON only)** 를 전제로 구현
* 모델 교체가 쉬워야 하므로 “LLM client wrapper + prompt template”로 분리

### D. `packages/core/registry/contracts` = Tool Contract 단일 진실

* Tool 환각 방지의 핵심
* 입력/출력 스키마, risk_level, produces_map 고정

### E. `packages/core/registry/skills` = Workflow Template

OpenClaw의 Skill 아이디어를 metel에서는 “템플릿 워크플로우”로 활용:

* Planner 안정성 상승
* 자주 쓰는 플로우를 표준화
* 운영/디버깅 용이

## 11.3 MVP에서 반드시 만들어야 하는 파일/모듈 (체크리스트)

* [ ] `docs/schemas/action-plan.schema.json` (Planner 출력 검증)
* [ ] `packages/core/orchestrator/orchestrator.py` (실행 루프)
* [ ] `packages/core/registry/tool_registry.py` + `contracts/*`
* [ ] `packages/core/agents/planner.py` + prompt
* [ ] `packages/core/agents/executor.py` + schema-locked prompt
* [ ] `packages/core/policy/rules.py` (최소 규칙 엔진)
* [ ] `packages/core/storage/state_store.py` (Redis)
* [ ] `packages/core/storage/audit_log.py` (Postgres)
* [ ] `apps/api/routers/runs.py` (create/status/approve)

---

## 11.4 MVP 권장 API(최소)

* `POST /runs` : run 생성(요청 + 연결된 서비스 + tool 후보)
* `GET /runs/{run_id}` : 상태 조회(state, history 요약)
* `POST /runs/{run_id}/approve` : 승인(특정 action 또는 전체)
* `POST /runs/{run_id}/replay` : 리플레이 실행(디버깅/감사)
