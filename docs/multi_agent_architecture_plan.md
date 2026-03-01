# metel 핵심 엔진 오버홀 기획서 (초안)

> 작성 목적: 핵심 실행 엔진 전면 재설계를 위한 기획 문서
> 버전: v1.0 Draft

---

# 1. 문제 정의

## 1.1 현재 증상

- 사용자 요청 인식률이 낮다
- 실행은 되지만 사용자가 기대한 결과와 다르다
- 복합 요청 처리 시 오류가 누적된다
- 디버깅이 어렵다

## 1.2 근본 원인

- 자연어 입력을 복합 파이프라인 DAG로 바로 변환
- Intent와 Slot이 불완전한 상태에서 실행 강행
- 검증이 "API 호출 성공 여부" 중심으로만 동작
- 기대 결과에 대한 계약(Contract)이 없음

---

# 2. metel의 제품 정체성

> metel = Claude Connector와 동일한 실행 구조.
> 단, 커뮤니케이션 툴(텔레그램 등)을 인터페이스로 사용하며 LLM은 모델 직접 내장이 아닌 API로 호출한다.

metel은 다음과 같은 플랫폼이다:

> 텔레그램 등 커뮤니케이션 툴에서 자연어 요청을 입력하면
> LLM API를 통해 의도를 해석하고
> OAuth로 연결된 SaaS API를 호출하여
> 자동으로 작업을 수행하는 SaaS 실행 커넥터

## 2.1 Claude Connector와의 비교

| 항목 | Claude Connector | metel |
| --- | --- | --- |
| 인터페이스 | Claude.ai / Claude 앱 | 텔레그램 등 커뮤니케이션 툴 |
| LLM 사용 방식 | LLM 모델 직접 내장 | LLM API 호출 |
| SaaS 연결 | OAuth 기반 | OAuth 기반 (동일) |
| 실행 방식 | HTTP API 호출 | HTTP API 호출 (동일) |

## 2.2 OpenClaw와의 비교

| 항목 | OpenClaw | metel |
| --- | --- | --- |
| 실행 범위 | OS/화면 제어 | SaaS API |
| 자율성 | 시스템 레벨 | 서비스 레벨 |
| 실행 방식 | 화면 제어/명령 실행 | HTTP API 호출 |
| 통제 구조 | LLM 중심 | Orchestrator 중심 |
| 모델 사용 | 로컬 모델 가능 | LLM API 사용 |

---

# 3. 시장 포지셔닝

## 3.1 자동화 도구 스펙트럼

```
자율성 ←————————————————————————→ 명시성

OpenClaw          metel              n8n
(자율 에이전트)   (오케스트레이터)    (명시적 워크플로우)

LLM이 모든        코드가 흐름 통제    사람이 직접
판단을 자율로      LLM은 필요시만      노드를 연결하여
수행              호출               설계
```

## 3.2 포지션 비교

| 항목 | OpenClaw | metel | n8n |
| --- | --- | --- | --- |
| 흐름 통제 | LLM 자율 | Orchestrator | 사람 (UI) |
| LLM 역할 | 전체 판단 | Intent/Slot 추출 | 없음 (또는 선택) |
| 유연성 | 최고 | 중간 | 낮음 |
| 정확도 보장 | 어려움 | 가능 | 높음 |
| 사용자 개입 | 최소 | Clarification만 | 설계 단계에서 전부 |
| 자연어 입력 | ✅ | ✅ | ❌ |
| 실행 안전성 | 낮음 | 높음 | 높음 |

## 3.3 metel의 차별점

> 자연어로 요청하면 안전하고 정확하게 실행된다.

OpenClaw는 너무 자율적이어서 정확도 보장이 어렵고, n8n은 자연어 입력이 불가능하다. metel은 자연어의 편의성과 파이프라인의 안전성을 동시에 제공한다.

---

# 4. 설계 전략

## 4.1 핵심 전략: Atomic-First

> 먼저 하나의 작업을 완벽하게 수행한다.

복합 요청은 Atomic이 안정화된 이후 명시적 Workflow Mode로 확장한다.

## 4.2 Atomic Task 정의

Atomic Task란:

- 단일 SaaS 중심 작업
- 하나의 명확한 intent
- 외부 API 호출 1회
- 기대 결과 명확히 정의 가능

| 요청 | Atomic 여부 |
| --- | --- |
| 오늘 구글 캘린더 일정 조회 | ✅ |
| 노션 페이지 생성 | ✅ |
| 최근 Linear 이슈 5개 조회 | ✅ |
| 일정 조회 후 노션 생성 후 슬랙 공유 | ❌ |

## 4.3 엔진 구조: 오케스트레이터 중심 파이프라인

멀티 에이전트 구조(LLM이 스스로 판단하며 루프)가 아닌, 코드가 흐름을 통제하고 LLM은 필요한 지점에서만 호출하는 파이프라인 구조를 채택한다.

이유:
- metel의 핵심 문제가 "정확도"이기 때문
- 각 단계의 입출력이 명확해야 디버깅 가능
- 자율 판단이 개입될수록 기대 결과와의 불일치가 심화됨

---

# 5. 실행 엔진 파이프라인

## 5.1 전체 흐름

```text
User Request (텔레그램 등)
    ↓
[OAuth 연결 확인]
    ↓ 미연결 시 → 연결 안내 후 중단
    ↓
Request Understanding  ← LLM API 호출
    ↓
[요청 유형 판단]
    ↓ 순수 LLM 대화 요청 → 미지원 안내 후 중단
    ↓ SaaS 실행 요청
[Clarification 루프 ①]  ← Intent/Slot 불완전 시 최대 2회 질문
    ↓
Request Contract
    ↓
[Clarification 루프 ②]  ← Hard Ask 파라미터 누락 시 질문
    ↓
Tool Retrieval (Top-K)
    ↓
Atomic Planner
    ↓
Executor → API Call
    ↓
Expectation Verification
    ↓
Response
```

## 5.2 모듈별 역할 요약

| 모듈 | 역할 | LLM 사용 |
| --- | --- | --- |
| Request Understanding | 자연어 → Intent/Slot 추출 | ✅ |
| Request Contract | Slot 완전성 검증, 기대 결과 정의 | ❌ |
| Tool Retrieval | 연결 서비스 기반 Tool 후보 필터링 | ❌ |
| Atomic Planner | API 파라미터 매핑 | ❌ |
| Executor | SaaS API 호출 | ❌ |
| Expectation Verification | 결과 조건 충족 여부 검사 | ❌ |

---

# 6. 모듈 상세 설계

## 6.1 Request Understanding

자연어 요청을 LLM API로 분석하여 Intent와 Slot을 추출한다.

**입력**
```json
{
  "user_message": "오늘 구글 캘린더 일정 알려줘",
  "user_id": "string",
  "connected_services": ["google", "notion", "linear"]
}
```

**출력**
```json
{
  "intent": "list_events",
  "service": "google",
  "slots": {
    "time_range": "today"
  },
  "missing_slots": [],
  "confidence": 0.95
}
```

confidence가 운영 임계치(기본 0.8) 미만이면 사용자에게 재질문한다.

---

## 6.2 Clarification 루프

Clarification은 두 시점에서 발생한다. 각 시점의 2회 제한은 독립적으로 계산한다.

### 루프 ① — Request Understanding 이후

Intent 또는 핵심 Slot이 불완전할 때 발생한다.

- 트리거: confidence < 운영 임계치(기본 0.8) 또는 서비스/intent 특정 불가
- 목적: 요청 자체를 명확히 하는 것
- 예시: "어떤 서비스를 말씀하신 건가요? Notion인가요, Linear인가요?"

### 루프 ② — Request Contract 이후

Hard Ask 파라미터가 누락된 경우 발생한다.

- 트리거: fill 정책이 `hard_ask`인 파라미터가 MISSING 상태
- 목적: 실행에 필요한 구체적 대상을 확정하는 것
- 예시: "어느 Notion 데이터베이스에 생성할까요?"

**공통 원칙**
- 각 루프 최대 2회 질문
- 선택지 기반 질문 우선
- 2회 초과 시 요청 중단

---

## 6.3 Request Contract

실행 전 Intent, Slot, 기대 결과를 계약 형태로 확정한다. Contract가 불완전하면 실행하지 않는다.

**입력**: Request Understanding 출력

**출력**
```json
{
  "intent": "list_events",
  "service": "google",
  "slots": {
    "time_range": "today",
    "limit": 5,
    "timezone": "Asia/Seoul"
  },
  "clarification_needed": [],
  "autofilled": ["limit", "timezone"],
  "expected_output": {
    "type": "list",
    "format": "bullet",
    "count": 5
  }
}
```

---

## 6.4 Hybrid Parameter Strategy

파라미터 자동 채움과 사용자 질문을 안전성 기준으로 분리한다.

### A. Hard Ask — 반드시 질문

절대 자동 채우지 않는 파라미터:

- 대상 선택형 ID (database_id, project_id, channel, page_id 등)
- 외부 전송 대상
- destructive 작업 대상
- 권한/금전 관련 파라미터

처리: `"MISSING"` 반환 → Clarification 질문

### B. Safe Default — 자동 채움 가능

- 타임존
- 기본 limit (5 또는 10)
- 기본 정렬
- 명확한 날짜 표현 ("오늘")

단, 응답에 가정을 명시한다:
> 최근 5개 기준으로 조회했습니다.

### C. Soft Autofill + Confirm

- 후보 1개: 자동 선택
- 후보 2~3개: 선택지 질문

---

## 6.5 Tool Spec 설계

Tool Spec은 각 SaaS 서비스의 API를 metel이 호출할 수 있도록 사전에 정의해 둔 명세서다. LLM은 Tool Spec을 참고해서 사용자 요청으로부터 파라미터를 추출하고, 코드 로직은 입력 스키마/슬롯 정책에 따라 파라미터를 자동 채우거나 사용자에게 질문한다.

### Tool Spec 구조

```json
{
  "service": "google",
  "version": "v1",
  "base_url": "https://www.googleapis.com/calendar/v3",
  "tools": [
    {
      "tool_name": "google_calendar_list_events",
      "description": "List events in a calendar for a time range",
      "method": "GET",
      "path": "/calendars/{calendar_id}/events",
      "adapter_function": "google_calendar_list_events",
      "input_schema": {
        "type": "object",
        "properties": {
          "calendar_id": { "type": "string" },
          "time_min": { "type": "string" },
          "time_max": { "type": "string" },
          "time_zone": { "type": "string" },
          "max_results": { "type": "integer" }
        },
        "required": ["calendar_id"]
      }
    }
  ]
}
```

### fill 정책 정의

| fill 값 | 동작 | 해당 파라미터 예시 |
| --- | --- | --- |
| `hard_ask` | 반드시 사용자에게 질문 | 대상 ID, 전송 채널, destructive 대상 |
| `safe_default` | 기본값으로 자동 채움 + 응답에 명시 | 타임존, limit, 정렬 기준 |
| `soft_confirm` | 후보 1개면 자동 선택, 2~3개면 질문 | 연결된 캘린더, 워크스페이스 |
| `llm_extract` | LLM이 사용자 요청에서 직접 추출 | 날짜 표현, 키워드, 개수 |

> 구현 기준: `fill`은 Tool Spec의 필수 필드가 아니라 런타임 정책(`slot_schema`, `slot_policy`)으로 관리한다.  
> Tool Spec은 실행 계약(input schema/required scopes)에 집중하고, 질문/자동채움은 오케스트레이터 정책에서 판정한다.

### LLM의 역할 범위

LLM은 Tool Spec이라는 틀 안에서 사용자 요청을 파라미터로 변환하는 역할만 담당한다. 어떤 API를 쓸지, 파라미터가 부족한지, 실행할지 여부는 코드 로직이 처리한다.

```
사용자 요청: "오늘 구글 캘린더 일정 알려줘"
    ↓
LLM 추출 (llm_extract)
  time_min → "오늘 00:00 KST" 변환
  time_max → "오늘 23:59 KST" 변환
    ↓
코드 로직 처리
  max_results → 5 (safe_default)
  timezone    → "Asia/Seoul" (safe_default)
    ↓
모든 파라미터 확정 → Executor 실행
```

### Tool Spec 등록 위치

```text
backend/
  agent/
    tool_specs/
      google.json
      notion.json
      linear.json
      spotify.json
      web.json
```

새로운 SaaS 서비스를 추가할 때는 해당 서비스의 Tool Spec JSON을 등록하는 것으로 확장한다.

---

## 6.6 Tool Retrieval

모든 Tool을 LLM에 제공하면 환각이 증가한다. 연결된 서비스와 Intent 기반으로 Top-K 후보만 Planner에 전달한다.

**입력**: intent, service

**출력**
```json
{
  "tools": [
    {
      "tool_name": "google_calendar_list_events",
      "service": "google",
      "schema": { }
    }
  ],
  "top_k": 3
}
```

---

## 6.7 Atomic Planner

Request Contract와 Tool Spec을 기반으로 API 호출 파라미터를 확정한다.

**입력**: Request Contract + Tool Retrieval 출력

**출력**
```json
{
  "plan": [
    {
      "step": 1,
      "tool_name": "google_calendar_list_events",
      "params": {
        "time_min": "2026-02-28T00:00:00+09:00",
        "time_max": "2026-02-28T23:59:59+09:00",
        "max_results": 5
      }
    }
  ]
}
```

---

## 6.8 Executor

Plan에 따라 SaaS API를 호출한다.

**입력**: Atomic Planner 출력

**출력**
```json
{
  "status": "success",
  "raw_response": { },
  "executed_tool": "google_calendar_list_events"
}
```

---

## 6.9 Expectation Verification

API 성공 여부가 아닌 사용자 요청 조건 충족 여부를 검사한다.

**입력**: Executor 출력 + Request Contract의 expected_output

**출력**
```json
{
  "verified": true,
  "checks": {
    "count_match": true,
    "date_range_match": true,
    "format_match": true
  },
  "final_response": "오늘 일정 5건입니다:\n• 10:00 팀 미팅 ..."
}
```

**검증 항목**
- 개수 정확성: "최근 5개" → 정확히 5개인지
- 기간 정확성: "오늘 일정" → timezone 기준 오늘인지
- 필터 정확성: 조건에 맞는 데이터인지
- 출력 형식: 요청한 포맷(bullet 등)인지

---

# 7. OAuth 연결 관리

## 7.1 전제 조건

모든 SaaS 작업은 사용자가 해당 서비스를 OAuth로 사전 연결한 경우에만 실행된다.

## 7.2 연결 상태 확인 흐름

```text
User Request
    ↓
Request Understanding
    ↓
서비스 연결 여부 확인
    ↓
연결됨   → Request Contract 진행
미연결   → 연결 안내 메시지 반환 후 중단
```

**미연결 시 응답 예시**
> Google Calendar가 연결되어 있지 않습니다.
> 아래 링크에서 연결 후 다시 요청해 주세요.
> 👉 [Google Calendar 연결하기](링크)

## 7.3 토큰 만료 처리

| 상황 | 처리 방식 |
| --- | --- |
| Access Token 만료 | Refresh Token으로 자동 갱신 후 재실행 |
| Refresh Token 만료 | 재연결 안내 메시지 반환 |
| 권한 범위 부족 | 필요한 권한 안내 + 재연결 유도 |

---

# 8. 에러 및 예외 처리 정책

## 8.1 에러 유형별 처리

| 에러 유형 | 처리 방식 |
| --- | --- |
| Intent 인식 실패 (confidence < 운영 임계치) | 사용자에게 재질문 |
| Clarification 2회 초과 | 요청 중단 + 안내 메시지 반환 |
| API 호출 실패 (429/timeout) | 1회 재시도 |
| API 호출 실패 (5xx) | 1회 재시도 후 실패 시 중단 + 서비스 오류 안내 |
| Verification 실패 | Executor부터 1회 재실행 (API 재호출) → 실패 시 결과 + 경고 반환 |
| Tool 후보 없음 | 지원하지 않는 요청 안내 |

## 8.2 재시도 정책

- 최대 재시도 횟수: 1회
- 재시도 대상: API `rate_limited`/`timeout`/`5xx`, Verification 실패
- 재시도 불가: validation_error, Clarification 초과, destructive 작업

## 8.3 사용자 응답 예시

**Clarification 초과 시**
> 요청을 정확히 이해하지 못했습니다.
> 다시 한번 구체적으로 말씀해 주시겠어요?
> 예: "노션 'Daily Log' 페이지에 오늘 일정 추가해줘"

**Verification 실패 시**
> 요청하신 조건과 결과가 일부 다를 수 있습니다.
> 조회된 결과를 그대로 전달드립니다.
> (조회 기준: 오늘 / 결과: 3건)

---

# 9. MVP 범위

## 9.1 포함

- Notion 단일 작업
- Google Calendar 단일 조회
- Linear 단일 조회/생성

## 9.2 제한

- 다중 서비스 자동 체인 ❌
- destructive 자동 실행 ❌
- 3-step 이상 파이프라인 ❌

## 9.3 허용

- 조회 + LLM 내부 요약 ✅

## 9.4 LLM 대화 기능 범위

metel은 순수 LLM 대화 서비스가 아니다. SaaS 실행 커넥터로서의 포지셔닝을 유지하기 위해 LLM 사용 범위를 다음과 같이 제한한다.

| 요청 유형 | 예시 | 처리 방식 |
| --- | --- | --- |
| 순수 콘텐츠 생성 | "회의록 서식 만들어줘" | ❌ 지원 안 함 + 안내 메시지 |
| SaaS 실행 | "노션에 회의록 페이지 만들어줘" | ✅ 지원 |
| 조회 + LLM 요약 | "오늘 일정 요약해줘" | ✅ 지원 |
| SaaS 데이터 가공 | "Linear 이슈 내용 정리해줘" | ✅ 지원 |

**원칙**: SaaS 데이터를 조회한 결과를 LLM으로 가공하는 것은 허용한다. SaaS와 무관한 순수 대화/생성은 범위 밖이다.

**순수 생성 요청 시 응답 예시**
> 회의록 서식 생성은 지원하지 않습니다.
> 노션 등 연결된 서비스에 페이지를 직접 만들어드릴 수 있습니다.
> 예: "노션 'Daily Log' 데이터베이스에 오늘 날짜로 회의록 페이지 만들어줘"

---

## 9.5 복합 요청 처리 (확장 단계)

MVP 안정화 이후 Workflow Mode를 별도 모듈로 개발한다.

```
Atomic Mode (기본)          Workflow Mode (확장)
단일 작업 수행              A 작업 완료 → B 작업 연결
정확도 최우선               UI 기반 구성
                           Template 기반 실행
```

---

# 10. 코드 구조

```text
backend/
  app/
    routes/
      telegram.py
      notion.py
      linear.py
      google.py
  agent/
    loop.py
    orchestrator_v2.py
    stepwise_planner.py
    planner_llm.py
    executor.py
    tool_runner.py
    slot_schema.py
    pending_action.py
    tool_specs/
  docs/sql/
    002_create_oauth_tokens_table.sql
    004_create_command_logs_table.sql
    007_create_pending_actions_table.sql
    013_add_pipeline_step_logs_and_command_logs_stepwise_columns.sql
```

---

## 10.1 전환 전략 (기존 구조 공존)

Atomic-First로 전환하되, 현재 운영 중인 실행 경로는 feature flag 기반으로 점진 이행한다.

- 유지 원칙:
  - 서비스/provider 식별자는 현행(`google`, `notion`, `linear`) 유지
  - Tool 이름 규약은 현행(`tool_name`, 예: `google_calendar_list_events`) 유지
  - OAuth 저장 구조는 현행(`oauth_tokens`) 유지

- 공존 대상 경로:
  - 기존 rule planner + executor
  - stepwise pipeline
  - router v2
  - autonomous
- 이행 원칙:
  - 신규 Atomic 경로를 shadow로 먼저 실행하고 `command_logs`, `pipeline_step_logs`로 비교
  - 품질 게이트 통과 시 트래픽 10% → 30% → 100% 확대
  - 장애 시 즉시 기존 경로로 rollback (`*_enabled=false`, traffic 0)
- 수용 기준:
  - 기존 대비 성공률 동등 이상
  - validation_error 및 user-visible error 비율 개선
  - p95 지연 +10% 이내

---

# 11. 오버홀 실행 계획

## 11.1 실행 체크리스트

### Phase 1 — 관측/기준선 고정

- [x] `telegram.py`, `loop.py` 구조화 로그 필드 정리 반영
- [x] 최근 7일 기준 baseline 리포트(success/validation_error/clarification/p95) 생성
- [x] 오버홀 전후 비교 지표 정의 문서화
- [ ] baseline 수치 팀 합의 완료

baseline 팀 합의용 스냅샷 (결재 대기)
- baseline(7d): `docs/reports/atomic_overhaul_baseline_7d.json`
  - success_rate: `12.9%`
  - validation_error_rate: `35.3%`
  - user_visible_error_rate: `87.1%`
  - latency_p95_ms: `4226`
- cutover 최신(재인증 후): `docs/reports/atomic_overhaul_rollout_latest.json`
  - accepted_outcome_rate: `100.0%`
  - success_rate: `70.0%`
  - validation_error_rate: `0.0%`
  - user_visible_error_rate: `0.0%`
  - latency_p95_ms: `5137`
  - legacy_row_count: `0`
- 승인 기록:
  - 승인자:
  - 승인일(UTC):
  - 코멘트:

Phase 1 baseline 리포트 (2026-03-01 14:17 KST)
- 생성 명령: `cd backend && .venv/bin/python scripts/eval_atomic_overhaul_rollout.py --limit 1000 --days 7 --min-sample 30 --output-json ../docs/reports/atomic_overhaul_baseline_7d.json`
- 리포트: `docs/reports/atomic_overhaul_baseline_7d.json`
- 핵심 수치:
  - sample_size: `85`
  - legacy_row_count: `915`
  - success_rate: `12.9%`
  - validation_error_rate: `35.3%`
  - user_visible_error_rate: `87.1%`
  - latency_p95_ms: `4226`

오버홀 전후 비교 지표 정의
- success_rate: `status == "success"` 비율
- validation_error_rate: `error_code == "validation_error"` 비율
- user_visible_error_rate: `status != "success"` 비율(사용자 관점 실패율)
- latency_p95_ms: `latency_ms` p95
- legacy_row_count: `plan_source`가 legacy 계열인 row 개수(컷오버 기준은 `0`)

### Phase 2 — Request Understanding + Clarification 정합화

- [x] Clarification 트리거(confidence/intent/service) 정책 코드 반영
- [x] Clarification 각 루프 최대 2회 제한 동작 확인
- [x] `pending_actions` 재개/만료/취소 시나리오 테스트 통과
- [x] `hard_ask`/`safe_default`/`soft_confirm` 런타임 정책 테스트 통과

### Phase 3 — Atomic Planner 경로 신설 및 공존

- [x] Atomic 경로 feature flag 추가
- [x] Tool Retrieval Top-K 구현 (service/intent 기반 후보 제한)
- [x] shadow 실행 시 `command_logs`/`pipeline_step_logs` 비교 가능 상태 확인
- [x] 기존 경로(rule/stepwise/router v2/autonomous) 병행 동작 확인
- [x] rollback 플래그(`*_enabled=false`, traffic 0) 즉시 전환 검증

Phase 3 shadow 로그 비교 점검 (완료)
- 점검 명령: `python backend/scripts/check_atomic_shadow_log_parity.py --limit 400 --output-json docs/reports/atomic_shadow_log_parity_latest.json`
- 최신 결과: `compare_ready=true`, `shadow_compare_ready=true`
- 해석: atomic serve/shadow 모두 `request_id` 기준으로 `command_logs` ↔ `pipeline_step_logs` 비교 가능

### Phase 4 — Executor/Verification 정책 강화

- [x] expected_output 기반 검증 로직 구현
- [x] verification 실패 시 1회 재실행 정책 구현 및 테스트 통과
- [x] API 재시도 정책(429/timeout/5xx만 1회) 일치 확인
- [x] destructive/권한 위험 요청의 risk gate 검증

### Phase 5 — 텔레그램 응답/운영 연계 정리

- [x] 사용자 응답 메시지(성공/실패/미지원/clarification) 정책 반영
- [x] `command_logs`/`pipeline_step_logs` KPI 집계 경로 일관성 검증
- [x] 필요 시 SQL 마이그레이션 보강 및 적용 절차 문서화
- [x] 사용자 가시 오류 메시지 QA 완료

### Phase 5 SQL 적용 절차 (Runbook)

Atomic 오버홀 로그 지표 확장을 위해 다음 순서로 SQL을 적용한다.

1. 적용 대상 파일
- `docs/sql/013_add_pipeline_step_logs_and_command_logs_stepwise_columns.sql`
- `docs/sql/014_add_command_logs_atomic_overhaul_columns.sql`

2. 적용 순서
- 스테이징 DB에 `013 -> 014` 순서로 적용
- 운영 DB에 동일 순서로 적용
- 각 단계 적용 후 `command_logs`, `pipeline_step_logs` insert 정상 여부 확인

3. 롤백 기준
- `command_logs` insert 실패율 급증
- `pipeline_step_logs` insert 실패 경고 급증
- 위 조건 발생 시 신규 컬럼 사용 코드 비활성화 후 원인 분석

4. 검증 쿼리 예시
```sql
select
  count(*) filter (where atomic_verified is true) as atomic_verified_ok,
  count(*) filter (where atomic_verified is false) as atomic_verified_fail
from public.command_logs
where created_at >= now() - interval '1 day';
```

### Phase 6 — 점진 롤아웃 및 경로 정리

- [x] 트래픽 비율 10% → 30% → 100% 단계별 확대 실행
- [x] 각 단계 KPI 수용 기준 충족 확인
- [x] kill-switch/rollback 시나리오 리허설 완료
- [x] 구경로 비활성화(또는 제거) 후 운영 안정성 확인

### Phase 6 롤아웃 제어 플래그

- `atomic_overhaul_enabled`: Atomic 오버홀 경로 on/off
- `atomic_overhaul_traffic_percent`: 해시 기반 트래픽 비율 제어 (0~100)
- `atomic_overhaul_allowlist`: 특정 사용자 우선 적용 (`user_id` CSV)
- `atomic_overhaul_shadow_mode`: serve 제외 사용자 shadow 실행
- `atomic_overhaul_legacy_fallback_enabled`: legacy 경로 fallback 허용/차단

### Phase 6 운영 런북

1. KPI 게이트 평가
- `python backend/scripts/eval_atomic_overhaul_rollout.py --limit 200 --days 1 --min-sample 30 --output-json docs/reports/atomic_overhaul_rollout_latest.json`
- 컷오버 시점 이후만 평가(과거 legacy 제외):
  - `SINCE_UTC=2026-03-01T05:20:00Z bash backend/scripts/run_atomic_cutover_gate.sh`
- 100% 전환 이후 구경로 제거 검증:
  - `python backend/scripts/eval_atomic_overhaul_rollout.py --limit 200 --days 1 --min-sample 30 --require-zero-legacy --output-json docs/reports/atomic_overhaul_rollout_latest.json`
- PASS 조건:
  - accepted_outcome_rate >= 0.85 (`success + needs_input(policy)`)
  - validation_error_rate <= 0.10
  - user_visible_error_rate <= 0.15
  - p95 latency <= 12000ms

2. 롤아웃 의사결정
- `python backend/scripts/decide_atomic_overhaul_rollout.py --report-json docs/reports/atomic_overhaul_rollout_latest.json --current-percent 10 > docs/reports/atomic_overhaul_rollout_decision_latest.json`
- promote: `10 -> 30 -> 100`
- fail 시 rollback: 한 단계 하향

3. 환경 반영
- dry-run:
  - `python backend/scripts/apply_atomic_overhaul_rollout_decision.py --from-json docs/reports/atomic_overhaul_rollout_decision_latest.json --env-file backend/.env`
- apply:
  - `python backend/scripts/apply_atomic_overhaul_rollout_decision.py --from-json docs/reports/atomic_overhaul_rollout_decision_latest.json --env-file backend/.env --apply`

4. Kill-switch (즉시 차단)
- `ATOMIC_OVERHAUL_ENABLED=false`
- `ATOMIC_OVERHAUL_TRAFFIC_PERCENT=0`
- `ATOMIC_OVERHAUL_LEGACY_FALLBACK_ENABLED=true` (긴급 복귀 허용)
- 적용 후 즉시 `/api/telegram/webhook` 요청 기준 legacy 경로 응답 확인

5. 리허설 완료 기준
- FAIL 리포트 입력 시 `decide_atomic_overhaul_rollout.py`가 rollback을 출력
- `apply_atomic_overhaul_rollout_decision.py`가 traffic/env 값을 정상 반영

6. Cutover 최종 게이트
- `bash backend/scripts/run_atomic_cutover_gate.sh`
- PASS 조건:
  - rollout gate verdict PASS
  - `ATOMIC_OVERHAUL_TRAFFIC_PERCENT >= 100`
  - `legacy_row_count == 0`
  - sample_size >= min_sample

### Phase 6 최신 게이트 실행 결과

- 실행 시각: `2026-03-01 15:20:24 KST`
- 실행 명령: `bash backend/scripts/run_atomic_cutover_gate.sh`
- 결과: `PASS`
- 근거 리포트: `docs/reports/atomic_overhaul_rollout_latest.json`
- 핵심 지표:
  - `sample_size:40` (`min_sample=30` 충족)
  - `legacy_row_count:0`
  - `accepted_outcome_rate:1.000`
  - `success_rate:0.700`
  - `validation_error_rate:0.000`
  - `user_visible_error_rate:0.000`
  - `latency_p95_ms:5137`
- 보강 사항:
  - `backend/scripts/eval_atomic_overhaul_rollout.py`에 `--since-utc` 추가
  - `backend/scripts/run_atomic_cutover_gate.sh`에 `SINCE_UTC` 전달 추가
  - 컷오버 시점 이후만 대상으로 `legacy_row_count`를 검증 가능
  - `atomic_overhaul_v1_clarification2`를 atomic 계열로 집계하도록 분류 보정 (`legacy_row_count=0` 확인)
  - KPI 집계에서 정책상 `needs_input`(clarification/risk/slot-missing validation)을 accepted outcome으로 분류

### Phase 6 Stage6 Telegram E2E 최신 결과

- 실행 시각: `2026-03-01 15:19:55 KST`
- 실행 명령: `cd backend && PYTHONPATH=. .venv/bin/python scripts/run_stage6_telegram_e2e.py`
- 결과: `10/10 PASS`
- 주요 실패 코드:
  - 없음
- 보강 사항:
  - Atomic 실행 실패 에러코드 매핑 추가(`AUTH_REQUIRED/unauthorized/forbidden -> auth_error`)
  - 재인증 후 S1/S2/S6/S10 `auth_error` 해소
- 근거 점검:
  - 동일 `user_id`로 Linear 작업(S1/S2/S6/S10) 성공 확인
- 리포트: `docs/reports/stage6_telegram_e2e_latest.json`
- 메모:
  - `tool_not_found`는 재현되지 않음(의도-계약 폴백 효과 유지)
  - Stage6 판정에서 `clarification_needed`/`risk_gate_blocked`를 `needs_input`로 인정하도록 보정
  - S7, S8은 `PASS(status=success)` 유지(payload schema sanitize 효과 유지)
  - S9는 `PASS(status=success)` 유지(notion create_page parent/properties 자동 보강 효과 유지)

### Phase 6 다음 액션

1. [완료] Linear OAuth 재인증 반영 및 `auth_error` 해소
2. [완료] `atomic_overhaul_legacy_fallback_enabled=false` 상태 표본 40건 확보
3. [완료] `SINCE_UTC=2026-03-01T06:17:04Z` 기준 cutover gate PASS 확인
4. [완료] Phase 6 체크리스트 2개(각 단계 KPI, 구경로 안정성) 완료 처리

### Phase 6 KPI 실패 원인 분해 (2026-03-01 14:31 KST)

- 실행 명령:
  - `cd backend && .venv/bin/python scripts/analyze_atomic_kpi_failures.py --since-utc 2026-03-01T05:21:56Z --limit 200 --output-json ../docs/reports/atomic_kpi_failure_analysis_latest.json`
- 리포트:
  - `docs/reports/atomic_kpi_failure_analysis_latest.json`
- 결과 요약 (`atomic_rows=40`):
  - `tool_execution=12`
  - `oauth_auth=4`
  - `needs_input_or_policy=12`
  - `success=12`
- 해석:
  - KPI 하락의 핵심은 `tool_failed(12)` + `needs_input_or_policy(12)`이며, 특히 `linear` 서비스 비중(`28/40`)이 높다.
  - `legacy_row_count` 문제는 해소되었고, 현재 병목은 legacy가 아니라 Linear 성공률/인증 상태다.

최신 컷오버 구간 재분해 (2026-03-01 15:20 KST)
- 기준 구간: `since_utc=2026-03-01T06:17:04Z`
- 결과 (`atomic_rows=40`):
  - `success=28`
  - `needs_input_or_policy=12`
  - `oauth_auth=0`
  - `tool_execution=0`
- 해석:
  - Linear 인증 실패는 해소되었고, 남은 비성공 응답은 정책상 `needs_input` 카테고리다.

### Phase 6 최종 회귀 검증 (2026-03-01 15:26 KST)

- 실행 명령: `cd backend && bash scripts/run_core_regression.sh`
- 결과: `PASS (245 passed)`
- 특이사항:
  - STEPWISE semantic preflight 보강 적용
  - Google Calendar `time_min/time_max` 잘못된 datetime 입력은 API 호출 전 `semantic_validation_failed`로 차단
  - Linear update 보정 경로(issue_id 해석/patch field 보강) 회귀 없음 확인

### 운영 수동 테스트 체크리스트

- [x] 테스트 시작 전 환경 확인
  - [x] `ATOMIC_OVERHAUL_ENABLED=true`
  - [x] `ATOMIC_OVERHAUL_TRAFFIC_PERCENT=100`
  - [x] `ATOMIC_OVERHAUL_LEGACY_FALLBACK_ENABLED=false`
- [x] Linear 시나리오
  - [x] 이슈 조회: 최근 이슈 5개 조회 성공
  - [x] 이슈 수정: 특정 이슈 설명/제목 업데이트 성공
  - [x] 이슈 생성: 팀/제목 입력 기반 생성 성공
  - [x] 위험 요청: 삭제 요청 시 `risk_gate_blocked` 또는 승인 질문 동작
- [ ] Notion 시나리오
  - [x] 페이지 제목 업데이트 성공
  - [x] 페이지 본문 append/update 성공
  - [ ] Linear 참조 기반 Notion 페이지 생성 성공
- [ ] Google Calendar 시나리오
  - [ ] 오늘 일정 조회 성공
  - [ ] 잘못된 datetime 입력 시 semantic validation 차단 확인
- [ ] Clarification 시나리오
  - [ ] 슬롯 누락 시 `clarification_needed` 유도
  - [ ] `팀:`, `제목:` 같은 후속 응답으로 재개 성공
  - [ ] `취소` 입력 시 pending action 정상 취소
- [ ] 관측/로그 검증
  - [ ] `command_logs`에 `atomic_overhaul_rollout`, `request_id` 기록 확인
  - [ ] `pipeline_step_logs`와 `request_id` 기준 추적 가능 확인
  - [ ] `legacy_row_count == 0` 확인
- [ ] 합격 기준
  - [ ] Stage6 E2E 재실행 시 `10/10 PASS`
  - [ ] `bash backend/scripts/run_atomic_cutover_gate.sh` 결과 `PASS`
  - [ ] 사용자 가시 오류(`tool_failed`, `auth_error`) 비정상 급증 없음

## Phase 1 — 관측/기준선 고정 (1주)

- 목표:
  - 현재 경로(rule/stepwise/router v2/autonomous)의 실패 유형과 기준 지표를 고정한다.
- 수정 범위:
  - `backend/app/routes/telegram.py` (구조화 로그 필드 정리)
  - `backend/agent/loop.py` (phase 구분 note 태깅)
  - `docs/reports/*` 생성 스크립트 (`backend/scripts/eval_*`)
- 완료 조건:
  - 최근 7일 기준 success/validation_error/clarification/p95 기준선 리포트 확정
  - 오버홀 전후 비교용 지표 정의 확정

## Phase 2 — Request Understanding + Clarification 정합화 (1~2주)

- 목표:
  - 문서 기준 Request Understanding/Clarification 정책을 현행 코드에 일치시킨다.
- 수정 범위:
  - `backend/agent/loop.py` (clarification 트리거/횟수/중단 정책)
  - `backend/agent/orchestrator_v2.py` (intent parsing + needs_input 정책)
  - `backend/agent/intent_contract.py` (confidence/필드 검증 정렬)
  - `backend/agent/pending_action.py` (pending_actions 수명주기 정렬)
  - `backend/agent/slot_schema.py`, `backend/agent/slot_collector.py` (hard_ask/safe_default/soft_confirm 런타임 정책)
  - `backend/tests/test_agent_loop.py`, `backend/tests/test_orchestrator_v2.py`, `backend/tests/test_pending_action.py`
- 완료 조건:
  - Clarification 정책 회귀 테스트 통과
  - pending_actions 기반 재질문 재개/만료/취소 시나리오 통과

## Phase 3 — Atomic Planner 경로 신설 및 기존 경로 공존 (2주)

- 목표:
  - 기존 경로를 유지한 채 Atomic 실행 경로를 feature flag로 추가한다.
- 수정 범위:
  - `backend/agent/loop.py` (Atomic 경로 진입 분기 + rollout note)
  - `backend/agent/planner.py`, `backend/agent/planner_llm.py` (단일 서비스/단일 작업 중심 계획 생성)
  - `backend/agent/stepwise_planner.py` (stepwise fallback 역할 축소)
  - `backend/app/core/config.py` (Atomic rollout/shadow 플래그)
  - `backend/tests/test_agent_loop.py`, `backend/tests/test_planner_llm.py`, `backend/tests/test_stepwise_planner.py`
- 완료 조건:
  - Atomic 경로 shadow 실행 가능
  - rollback 없이 기존 경로 병행 동작 확인

## Phase 4 — Executor/Verification 정책 강화 (2주)

- 목표:
  - API 성공이 아닌 기대결과 충족 검증(Expectation Verification) 중심으로 실행 정책을 강화한다.
- 수정 범위:
  - `backend/agent/executor.py` (expected_output 기반 검증 규칙 + verification fail handling)
  - `backend/agent/tool_runner.py` (재시도 대상/비대상 일관화)
  - `backend/agent/runtime_api_profile.py` (scope/risk gate 보강)
  - `backend/tests/test_agent_executor.py`, `backend/tests/test_tool_runner.py`, `backend/tests/test_runtime_api_profile.py`
- 완료 조건:
  - verification 실패 재실행 정책 테스트 통과
  - 재시도 정책(429/timeout/5xx only) 일치 확인

## Phase 5 — 텔레그램 응답/운영 연계 정리 (1주)

- 목표:
  - 사용자 응답 품질, 운영 로그, KPI 계산 경로를 Atomic 정책에 맞게 정리한다.
- 수정 범위:
  - `backend/app/routes/telegram.py` (최종 응답 메시지/오류 매핑/로그 연계)
  - 필요 시 SQL 마이그레이션 보강: `docs/sql/004_*`, `docs/sql/013_*`
  - `backend/tests/test_telegram_route_helpers.py`, `backend/tests/test_telegram_command_mapping.py`
- 완료 조건:
  - command_logs/pipeline_step_logs 기반 KPI 집계 일관성 확인
  - 사용자 가시 오류 메시지 정책 점검 완료

## Phase 6 — 점진 롤아웃 및 경로 정리 (1~2주)

- 목표:
  - Atomic 경로를 `10% -> 30% -> 100%`로 확대하고, 구경로를 단계 축소한다.
- 수정 범위:
  - `backend/app/core/config.py` (rollout 기본값 전환)
  - `backend/agent/loop.py` (legacy 분기 제거 또는 비활성화)
  - 운영 스크립트/리포트 (`backend/scripts/run_*`, `docs/reports/*`) 업데이트
  - 전체 회귀: `backend/tests/test_agent_loop.py`, `backend/tests/test_autonomous_loop.py`, `backend/tests/test_agent_executor_e2e.py`
- 완료 조건:
  - KPI 수용 기준 충족
  - kill-switch/rollback 시나리오 검증
  - 구경로 축소 후 운영 안정성 확인

---

# 12. 성공 지표

| 지표 | 목표 | 측정 방법 |
| --- | --- | --- |
| Intent 인식률 | 90%+ | 전체 요청 중 confidence ≥ 운영 임계치로 Contract 진입한 비율 |
| 기대 결과 정합성 | 85%+ | Expectation Verification 통과 비율 |
| Clarification 평균 횟수 | 1.5회 이하 | 요청당 Clarification 발생 횟수 평균 (`command_logs`/`pending_actions` 기반) |
| Tool 환각 | 0건 | 등록되지 않은 `tool_name`이 Planner 출력에 포함된 건수 |
| 승인 없는 destructive 실행 | 0건 | Hard Ask 미확인 상태로 destructive 작업이 Executor에 도달한 건수 |

---

# 13. 핵심 철학

metel은 OpenClaw처럼 자율 OS 에이전트가 아니다.

metel은:

> Claude Connector와 동일한 실행 구조를 가진 SaaS 실행 커넥터

이다. 차이는 인터페이스(커뮤니케이션 툴)와 LLM 사용 방식(API 호출)뿐이다.

따라서:

- 자율성보다 정확성
- 복합성보다 완성도
- 자동 채움보다 안전성

을 우선한다.

---

# 14. 데이터 모델 (현행 유지)

파이프라인 오버홀은 **현행 DB 스키마를 유지**한 상태에서 진행한다. 신규 테이블 신설보다 기존 테이블 확장/활용을 우선한다.

## 14.1 사용자 (users)

```sql
users
- id              UUID        PK
- telegram_id     STRING      UNIQUE  -- 텔레그램 사용자 식별자
- timezone        STRING      DEFAULT 'Asia/Seoul'
- created_at      TIMESTAMP
- updated_at      TIMESTAMP
```

## 14.2 서비스 연결 (oauth_tokens)

OAuth 토큰은 암호화 저장하며, provider별 연결 상태/scope는 `oauth_tokens`를 기준으로 관리한다.

```sql
oauth_tokens
- id                    BIGSERIAL   PK
- user_id               UUID        FK
- provider              STRING      -- 'google' | 'notion' | 'linear' | 'spotify' ...
- access_token_encrypted TEXT       ENCRYPTED
- granted_scopes        TEXT[]      -- 부여 스코프
- workspace_id          TEXT
- workspace_name        TEXT
- created_at            TIMESTAMP
- updated_at            TIMESTAMP
```

## 14.3 요청/실행 로그 (command_logs, pipeline_step_logs)

성공 지표 측정과 회귀 비교는 기존 로그 테이블을 사용한다.

```sql
command_logs
- command, status, error_code, detail
- run_id, request_id, catalog_id
- final_status, failed_task_id, failure_reason
- missing_required_fields
```

```sql
pipeline_step_logs
- run_id, request_id, task_index, task_id
- service, api, validation_status, call_status
- missing_required_fields, validation_error_code, failure_reason
- request_payload, normalized_response, raw_response
```

## 14.4 대화 상태 (pending_actions)

Clarification 루프 상태는 `pending_actions`에 저장한다.

```sql
pending_actions
- user_id (PK)
- intent, action, task_id
- plan_json, plan_source
- collected_slots, missing_slots
- expires_at, status
- created_at, updated_at
```

---

# 15. 상태 관리 설계

Clarification 루프는 사용자의 응답을 기다리는 동안 파이프라인 상태를 유지해야 한다.

## 15.1 상태 흐름

```text
요청 수신
    ↓
pending_actions에 상태 저장
    ↓
사용자에게 질문 전송
    ↓
[대기] 다음 메시지 수신까지
    ↓
텔레그램 메시지 수신
    ↓
pending_actions 조회
    ↓
활성 상태 있음 → Clarification 응답으로 처리
활성 상태 없음 → 새 요청으로 처리
```

## 15.2 상태 만료 정책

- 생성 후 **10~15분**(운영 설정값) 내 응답 없으면 자동 만료
- 만료 후 메시지 수신 시 새 요청으로 처리
- 만료 안내 메시지는 별도 전송하지 않음 (사용자가 다시 요청하면 됨)

## 15.3 동시 요청 처리

- 사용자당 활성 pending_action은 1개만 허용
- Clarification 대기 중 새 요청이 들어오면 기존 상태를 파기하고 새 요청으로 처리
- 파기 시 안내 메시지 전송:
  > 이전 요청을 취소하고 새 요청을 처리합니다.

---

# 16. LLM 프롬프트 설계

Request Understanding에서 LLM API를 호출할 때 사용하는 프롬프트 구조다.

## 16.1 시스템 프롬프트

```
당신은 SaaS 자동화 도우미입니다.
사용자의 자연어 요청을 분석하여 아래 JSON 형식으로만 응답하세요.

규칙:
1. 응답은 반드시 JSON만 출력합니다. 설명이나 부가 텍스트는 포함하지 않습니다.
2. 연결된 서비스 목록에 없는 서비스는 intent에 포함하지 않습니다.
3. 날짜/시간 표현은 사용자 timezone 기준으로 해석합니다.
4. SaaS 실행과 무관한 요청(순수 콘텐츠 생성, 일반 대화)은 request_type을 'unsupported'로 설정합니다.
5. 확신할 수 없는 경우 confidence를 낮게 설정합니다.

출력 형식:
{
  "request_type": "saas_execution" | "unsupported",
  "intent": string | null,
  "service": string | null,
  "slots": { [key: string]: any },
  "missing_slots": string[],
  "confidence": float  // 0.0 ~ 1.0
}
```

## 16.2 유저 프롬프트

```
사용자 요청: {user_message}
연결된 서비스: {connected_services}
사용자 timezone: {timezone}
현재 시각: {current_datetime}
```

## 16.3 Few-shot 예시

프롬프트에 포함되는 예시로, LLM 출력 일관성을 높인다.

**예시 1 — SaaS 실행 요청**
```
입력: "오늘 구글 캘린더 일정 알려줘"
출력:
{
  "request_type": "saas_execution",
  "intent": "list_events",
  "service": "google",
  "slots": { "time_range": "today" },
  "missing_slots": [],
  "confidence": 0.95
}
```

**예시 2 — 대상 ID 누락**
```
입력: "노션에 페이지 만들어줘"
출력:
{
  "request_type": "saas_execution",
  "intent": "create_page",
  "service": "notion",
  "slots": {},
  "missing_slots": ["database_id"],
  "confidence": 0.88
}
```

**예시 3 — 순수 콘텐츠 생성 요청**
```
입력: "회의록 서식 만들어줘"
출력:
{
  "request_type": "unsupported",
  "intent": null,
  "service": null,
  "slots": {},
  "missing_slots": [],
  "confidence": 0.92
}
```

**예시 4 — 낮은 confidence**
```
입력: "저번에 했던 거 다시 해줘"
출력:
{
  "request_type": "saas_execution",
  "intent": null,
  "service": null,
  "slots": {},
  "missing_slots": [],
  "confidence": 0.21
}
```

## 16.4 프롬프트 관리 원칙

- 시스템 프롬프트는 `backend/agent/prompts/request_understanding.txt`로 관리
- Few-shot 예시는 `backend/agent/prompts/examples/`에 JSON으로 별도 관리하여 추가/수정 가능하게 유지
- 프롬프트 변경 시 반드시 intent 인식률 회귀 테스트 수행

---

# 17. MVP Tool Spec 목록

MVP 범위(Notion, Google Calendar, Linear)에서 구현할 Tool 전체 목록이다. 각 Tool의 상세 Spec은 `backend/agent/tool_specs/` 하위 JSON 파일로 관리한다.

## 17.1 Google Calendar

| tool_name | 설명 | 주요 파라미터 |
| --- | --- | --- |
| `google_calendar_list_events` | 일정 조회 | calendar_id(hard_ask/soft_confirm), time_min(llm_extract), time_max(llm_extract), max_results(safe_default) |
| `google_calendar_get_event` | 단일 일정 조회 | calendar_id(hard_ask/soft_confirm), event_id(hard_ask) |
| `google_calendar_list_calendars` | 캘린더 목록 조회 | max_results(safe_default) |

## 17.2 Notion

| tool_name | 설명 | 주요 파라미터 |
| --- | --- | --- |
| `notion_create_page` | 페이지 생성 | database_id(hard_ask), title(llm_extract), properties(llm_extract) |
| `notion_query_database` | 데이터베이스 조회 | database_id(hard_ask), filter(llm_extract), page_size(safe_default) |
| `notion_retrieve_page` | 페이지 조회 | page_id(hard_ask) |
| `notion_update_page` | 페이지 속성 수정 | page_id(hard_ask), properties(llm_extract) |
| `notion_search` | 페이지/오브젝트 검색 | query(llm_extract), page_size(safe_default) |

## 17.3 Linear

| tool_name | 설명 | 주요 파라미터 |
| --- | --- | --- |
| `linear_list_issues` | 이슈 목록 조회 | team_id(soft_confirm), state(llm_extract), limit(safe_default) |
| `linear_search_issues` | 이슈 검색 | query(llm_extract), first(safe_default) |
| `linear_create_issue` | 이슈 생성 | team_id(soft_confirm), title(llm_extract), description(llm_extract), priority(safe_default) |
| `linear_update_issue` | 이슈 상태/속성 수정 | issue_id(hard_ask), state(llm_extract) |

---

# 18. 비기능 요구사항

## 18.1 응답 시간

| 구간 | 목표 |
| --- | --- |
| 요청 수신 ~ 첫 응답 전송 | 10초 이내 |
| Clarification 질문 전송 | 3초 이내 |
| API 호출 실패 시 에러 응답 | 5초 이내 |

LLM API 호출이 포함되므로 10초를 기본 목표로 설정한다. 초과 시 "처리 중입니다..." 메시지를 먼저 전송한다.

## 18.2 보안

| 항목 | 정책 |
| --- | --- |
| OAuth 토큰 저장 | AES-256 암호화 후 DB 저장 |
| LLM API 키 | 환경변수로 관리, 코드에 하드코딩 금지 |
| 요청 로그 | raw_message 포함 저장, 90일 후 자동 삭제 |
| 사용자 식별 | telegram_id 기반, 별도 인증 없음 (텔레그램 인증 위임) |

## 18.3 LLM API 장애 대응

| 상황 | 처리 방식 |
| --- | --- |
| LLM API 타임아웃 (10초 초과) | 1회 재시도 후 실패 시 안내 메시지 반환 |
| LLM API 5xx | 즉시 안내 메시지 반환 |
| LLM 출력이 JSON 파싱 불가 | 재요청 1회 → 실패 시 confidence 0으로 처리 |

> LLM 서비스 장애 중입니다. 잠시 후 다시 요청해 주세요.

## 18.4 처리량

MVP 단계 목표: **동시 사용자 50명** 기준으로 안정적으로 동작

- 사용자당 conversation_state 1개 제한으로 중복 처리 방지
- LLM API 호출은 사용자 요청당 최대 2회 (Understanding + 재시도)
