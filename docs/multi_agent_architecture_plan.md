아래는 **metel 멀티에이전트 아키텍처 설계 + 구현 계획 + 예시 시나리오 포함 MD 문서**입니다.
그대로 `.md` 파일로 저장해서 사용하셔도 됩니다.

---

# metel 멀티에이전트 아키텍처 설계 문서

*(Planner / Executor / Verifier / Policy 구조 기반)*

---

# 1. 목표

metel을 다음과 같은 구조로 고도화한다.

* 자연어 요청 기반 자율 실행
* n8n 수준의 결정적 워크플로우 안정성
* Manus/OpenClaw 수준의 계획/추론 능력 일부 보유
* LLM은 "의사결정", 시스템은 "강제 실행"

---

# 2. 전체 아키텍처

```
User Request
    ↓
Planner Agent
    ↓
Policy Agent
    ↓
Orchestrator (Execution Runtime)
    ↓
Executor Agent (action별)
    ↓
API Call
    ↓
Verifier Agent
    ↓
State Update
    ↓
Next Action
    ↓
Final Composer
```

---

# 3. 핵심 구성요소

---

## 3.1 Tool Registry (Contract 기반 설계)

모든 서비스 API는 다음 정보를 포함해야 한다.

```json
{
  "tool": "notion.create_page",
  "service": "notion",
  "risk_level": "write",
  "scopes_required": ["pages:write"],
  "input_schema": {
    "type": "object",
    "required": ["title", "parent_id"],
    "properties": {
      "title": { "type": "string" },
      "parent_id": { "type": "string" },
      "content": { "type": "string" }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["id", "url"]
  },
  "produces_map": {
    "page_id": "$.id",
    "page_url": "$.url"
  }
}
```

---

## 3.2 Execution State

```json
{
  "memory": {},
  "history": [],
  "errors": []
}
```

* memory: produces 필드 저장
* history: 실행 기록
* errors: 실패 정보

---

# 4. Agent 역할 정의

---

## 4.1 Planner Agent

### 역할

* 사용자 요청 → Action Plan(JSON) 생성
* 의존성 명시 (requires / produces)

### 출력 형식

```json
{
  "goal": "...",
  "timezone": "Asia/Seoul",
  "actions": [
    {
      "id": "a1",
      "tool": "notion.create_page",
      "requires": [],
      "produces": ["page_url"]
    },
    {
      "id": "a2",
      "tool": "slack.post_message",
      "requires": ["page_url"],
      "produces": []
    }
  ]
}
```

---

## 4.2 Policy Agent

### 역할

* 위험도 검사
* 권한 확인
* 외부 전송 차단
* 승인 필요 여부 판단

### 출력

```json
{
  "a1": "allow",
  "a2": "require_confirm"
}
```

---

## 4.3 Executor Agent

### 역할

* 특정 action의 input_schema 기반으로 payload 생성
* 필수값이 없으면 `"MISSING"` 반환

### 출력

```json
{
  "title": "회의 기록",
  "parent_id": "abc123",
  "content": "회의 내용..."
}
```

---

## 4.4 Verifier Agent

### 역할

* output_schema 충족 여부 확인
* success_criteria 검사
* 다음 action requires 충족 여부 확인

### 출력

```json
{
  "status": "pass"
}
```

또는

```json
{
  "status": "fail",
  "reason": "page_url not found"
}
```

---

# 5. 실행 흐름 (Orchestrator)

1. Planner 호출 → Action Plan 생성
2. Policy 검사
3. Action 반복 실행:

   * Executor → payload 생성
   * JSON Schema 검증
   * API 호출
   * produces_map 기반 state 저장
   * Verifier 검사
4. 모든 action 완료 후 Final Composer 호출

---

# 6. 예시 시나리오

---

# 시나리오 1

## 요청

> "내일 오후 3시에 노션에 회의 기록을 만들고 슬랙에 공유해줘"

---

## Step 1 — Planner 출력

```json
{
  "goal": "회의 기록 생성 후 슬랙 공유",
  "timezone": "Asia/Seoul",
  "actions": [
    {
      "id": "a1",
      "tool": "notion.create_page",
      "requires": [],
      "produces": ["page_url"]
    },
    {
      "id": "a2",
      "tool": "slack.post_message",
      "requires": ["page_url"],
      "produces": ["message_ts"]
    }
  ]
}
```

---

## Step 2 — Policy 검사

* notion.create_page → allow
* slack.post_message → allow

---

## Step 3 — a1 실행

Executor 출력:

```json
{
  "title": "회의 기록 - 2026-02-28 15:00",
  "parent_id": "database_id",
  "content": "회의 준비 문서"
}
```

API 호출 → 결과:

```json
{
  "id": "page_123",
  "url": "https://notion.so/page_123"
}
```

State 업데이트:

```json
{
  "page_id": "page_123",
  "page_url": "https://notion.so/page_123"
}
```

---

## Step 4 — a2 실행

Executor 입력에 page_url 포함

```json
{
  "channel": "#general",
  "text": "회의 기록이 생성되었습니다: https://notion.so/page_123"
}
```

API 호출 → 성공

---

## Step 5 — Final Response

> 노션에 회의 기록을 생성했고 슬랙에 공유했습니다.
> 링크: [https://notion.so/page_123](https://notion.so/page_123)

---

# 시나리오 2 (의존성 실패 케이스)

## 요청

> "지난주 매출을 구글 시트에서 가져와서 슬랙에 요약해줘"

---

### Planner

* a1: google.sheets.get_range
* a2: slack.post_message (requires summary)

---

### 실행

* a1 성공 → 데이터 획득
* Verifier: summary 필드 없음
* Verifier → Planner 재요청: "요약 단계 누락"

---

### 재계획

* a1: sheets.get_range
* a2: summarize_data (LLM 내부 작업)
* a3: slack.post_message

---

이렇게 멀티에이전트 구조는
**재플래닝이 가능**해야 진짜 자율 구조가 된다.

---

# 7. 단계별 구현 계획

---

## Phase 0 — 기반 구축

* Tool Registry 설계
* JSON Schema Validator 구현
* produces_map 추출기
* Execution State 구조화
* 로그/리플레이 시스템

---

## Phase 1 — 단일 에이전트 → 멀티 구조 준비

* Planner → Action Plan JSON 강제
* Executor → schema-locked 출력
* Policy → 규칙 기반 위험 통제
* Verifier → 코드 중심

---

## Phase 2 — 멀티 에이전트 분리

* Planner Agent 독립
* Policy Agent 독립
* Verifier Agent 독립
* 재플래닝 루프 구현

---

## Phase 3 — n8n 포지션 강화

* 조건 분기
* 병렬 실행
* 사용자 승인 노드
* 워크플로우 저장 기능

---

# 8. 핵심 설계 원칙

1. LLM은 제안만 한다
2. 실행은 항상 코드가 한다
3. 스키마 밖 필드는 허용하지 않는다
4. 위험 작업은 정책이 최종 권한을 가진다
5. requires / produces는 반드시 명시한다
6. 실패는 재계획 가능해야 한다

---

# 9. 결론

이 구조는:

* n8n처럼 안정적이고
* Manus/OpenClaw처럼 자율적이며
* SaaS 환경에서 안전하게 운영 가능한

**중간 포지션 최적 아키텍처**다.

---

아래에 요청하신 4가지를 **각각 독립적으로 바로 붙여 넣어 쓸 수 있는 형태**로 정리했습니다.

---

# 1) Action Plan JSON Schema 정식 정의 (Draft 2020-12)

> 목적: Planner Agent의 출력(= Action Plan)을 **항상 동일한 구조로 강제**하고, Orchestrator/Validator가 기계적으로 검증할 수 있게 함.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://metel.ai/schemas/action-plan.schema.json",
  "title": "Metel Action Plan",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "goal", "timezone", "actions"],
  "properties": {
    "version": {
      "type": "string",
      "const": "1.0"
    },
    "goal": {
      "type": "string",
      "minLength": 1
    },
    "timezone": {
      "type": "string",
      "minLength": 1,
      "description": "IANA timezone (e.g., Asia/Seoul)"
    },
    "locale": {
      "type": "string",
      "default": "ko-KR"
    },
    "context": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "user_text": { "type": "string" },
        "connected_services": {
          "type": "array",
          "items": { "type": "string" }
        },
        "tool_candidates": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Planner에 제공된 Top-K tool ids (optional)"
        }
      }
    },
    "actions": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/action" }
    },
    "final_response": {
      "$ref": "#/$defs/final_response"
    },
    "constraints": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "max_actions": { "type": "integer", "minimum": 1, "default": 12 },
        "allow_parallel": { "type": "boolean", "default": false }
      }
    }
  },
  "$defs": {
    "action": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "tool", "intent", "requires", "produces"],
      "properties": {
        "id": {
          "type": "string",
          "pattern": "^[a-zA-Z][a-zA-Z0-9_\\-]{0,63}$"
        },
        "tool": {
          "type": "string",
          "minLength": 1,
          "description": "Tool ID from Tool Registry (e.g., notion.create_page)"
        },
        "intent": {
          "type": "string",
          "enum": ["read", "write", "notify", "summarize", "transform", "search", "other"]
        },
        "summary": {
          "type": "string",
          "description": "Human-readable one-liner for logs/UX"
        },
        "requires": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "description": "State keys required before executing this action"
        },
        "produces": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "description": "State keys expected to be produced by this action"
        },
        "success_criteria": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "description": "Verifier input - simple criteria list"
        },
        "risk": {
          "$ref": "#/$defs/risk"
        },
        "policy_hints": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "needs_user_confirmation": { "type": "boolean" },
            "contains_pii": { "type": "boolean" },
            "external_send": { "type": "boolean" }
          }
        },
        "depends_on": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Explicit dependency edges (optional). Usually redundant with requires."
        },
        "input_bindings": {
          "type": "object",
          "additionalProperties": { "type": "string" },
          "description": "Optional mapping: payload_field -> state_key (executor can also infer)."
        },
        "retries": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "max_attempts": { "type": "integer", "minimum": 1, "maximum": 10, "default": 3 },
            "backoff_ms": { "type": "integer", "minimum": 0, "default": 500 }
          }
        },
        "timeout_ms": {
          "type": "integer",
          "minimum": 1000,
          "default": 20000
        }
      }
    },
    "risk": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "level": {
          "type": "string",
          "enum": ["read", "write", "destructive"]
        },
        "tags": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": ["pii", "external_send", "financial", "admin", "delete", "share_public"]
          }
        }
      }
    },
    "final_response": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "style": { "type": "string", "enum": ["concise", "detailed"], "default": "concise" },
        "include_links": { "type": "boolean", "default": true },
        "include_step_results": { "type": "boolean", "default": false }
      }
    }
  }
}
```

---

# 2) Notion Action Plan JSON Schema 정식 정의

> 목적: “Notion 전용 플로우”를 만들 때 Planner가 **notion.* tool만** 사용하고, produces/requires 관례도 Notion 관점으로 정해 **일관성**을 확보.

아래 스키마는 “Notion-only Plan”을 강제합니다. (tool prefix 제한)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://metel.ai/schemas/action-plan.notion.schema.json",
  "title": "Metel Notion Action Plan",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "goal", "timezone", "actions"],
  "properties": {
    "version": { "type": "string", "const": "1.0" },
    "goal": { "type": "string", "minLength": 1 },
    "timezone": { "type": "string", "minLength": 1 },
    "notion_context": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "workspace_id": { "type": "string" },
        "default_parent_type": { "type": "string", "enum": ["page", "database"] },
        "default_parent_id": { "type": "string" }
      }
    },
    "actions": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/notion_action" }
    }
  },
  "$defs": {
    "notion_action": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "tool", "intent", "requires", "produces"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_\\-]{0,63}$" },
        "tool": {
          "type": "string",
          "pattern": "^notion\\.[a-zA-Z0-9_\\-]+$",
          "description": "Only notion.* tools are allowed"
        },
        "intent": {
          "type": "string",
          "enum": ["read", "write", "search", "transform"]
        },
        "summary": { "type": "string" },
        "requires": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 }
        },
        "produces": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 }
        },
        "notion_produces_convention": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "page_id": { "type": "boolean" },
            "page_url": { "type": "boolean" },
            "database_id": { "type": "boolean" },
            "block_ids": { "type": "boolean" }
          },
          "description": "Optional hint to standardize state keys"
        },
        "success_criteria": {
          "type": "array",
          "items": { "type": "string" },
          "default": []
        },
        "risk": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "level": { "type": "string", "enum": ["read", "write", "destructive"] },
            "tags": {
              "type": "array",
              "items": { "type": "string", "enum": ["pii", "share_public", "delete"] }
            }
          }
        },
        "timeout_ms": { "type": "integer", "minimum": 1000, "default": 20000 }
      },
      "allOf": [
        {
          "if": {
            "properties": { "tool": { "const": "notion.create_page" } }
          },
          "then": {
            "properties": {
              "intent": { "const": "write" },
              "produces": {
                "contains": { "const": "page_url" }
              }
            }
          }
        },
        {
          "if": {
            "properties": { "tool": { "const": "notion.query_database" } }
          },
          "then": {
            "properties": {
              "intent": { "const": "read" },
              "produces": {
                "contains": { "const": "records" }
              }
            }
          }
        }
      ]
    }
  }
}
```

### Notion에서 추천하는 state key 표준(관례)

* `page_id`, `page_url`
* `database_id`
* `records` (query 결과)
* `block_ids` (블록 추가/수정 결과)
* `notion_object` (raw 응답 저장 시)

이 관례를 고정하면 “다음 step requires”를 Planner/Verifier가 훨씬 잘 맞춥니다.

---

# 3) Orchestrator 의사코드 (Python 버전)

> 목표: **멀티 에이전트라도 실행은 Orchestrator가 “단일 루프”로 통제**
> (LLM이 API를 직접 호출하지 않음)

아래는 구현 가능한 수준의 의사코드입니다.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import time
import json

# -------------------------
# Data models
# -------------------------

@dataclass
class ToolContract:
    tool_id: str
    risk_level: str  # read|write|destructive
    scopes_required: List[str]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    produces_map: Dict[str, str]  # state_key -> jsonpath (or extractor key)

@dataclass
class Action:
    id: str
    tool: str
    intent: str
    requires: List[str]
    produces: List[str]
    success_criteria: List[str] = field(default_factory=list)
    timeout_ms: int = 20000
    retries_max_attempts: int = 3
    retries_backoff_ms: int = 500

@dataclass
class ActionPlan:
    version: str
    goal: str
    timezone: str
    actions: List[Action]
    final_response: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecRecord:
    action_id: str
    tool: str
    status: str  # success|failed|skipped
    attempts: int
    started_at: float
    ended_at: float
    error: Optional[str] = None

@dataclass
class ExecutionState:
    memory: Dict[str, Any] = field(default_factory=dict)
    history: List[ExecRecord] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

# -------------------------
# Interfaces (you will implement)
# -------------------------

class ToolRegistry:
    def get_contract(self, tool_id: str) -> ToolContract:
        raise NotImplementedError

class PolicyEngine:
    def check_action(self, action: Action, contract: ToolContract, state: ExecutionState) -> Tuple[str, str]:
        """
        Returns (decision, reason)
        decision: allow | deny | require_confirm
        """
        raise NotImplementedError

class LLMPlanner:
    def plan(self, user_request: str, tool_candidates: List[str], timezone: str) -> Dict[str, Any]:
        raise NotImplementedError

class LLMExecutor:
    def fill_params(self, action: Action, contract: ToolContract, state: ExecutionState, timezone: str) -> Dict[str, Any]:
        raise NotImplementedError

class LLMVerifier:
    def verify(self, action: Action, contract: ToolContract, payload: Dict[str, Any], result: Dict[str, Any], state: ExecutionState) -> Dict[str, Any]:
        """
        Returns:
          {"status": "pass"} or
          {"status": "fail", "reason": "...", "next": "retry|ask_user|replan", "patch": {...optional...}}
        """
        raise NotImplementedError

class ToolCaller:
    def call(self, tool_id: str, payload: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
        raise NotImplementedError

class SchemaValidator:
    def validate(self, schema: Dict[str, Any], data: Dict[str, Any]) -> None:
        """Raise exception if invalid."""
        raise NotImplementedError

class ResultExtractor:
    def extract(self, produces_map: Dict[str, str], result: Dict[str, Any]) -> Dict[str, Any]:
        """Map tool result to state keys. (Implement JSONPath or simple dotted paths)"""
        raise NotImplementedError

# -------------------------
# Orchestrator
# -------------------------

class Orchestrator:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        policy: PolicyEngine,
        planner: LLMPlanner,
        executor: LLMExecutor,
        verifier: LLMVerifier,
        caller: ToolCaller,
        validator: SchemaValidator,
        extractor: ResultExtractor,
    ):
        self.tool_registry = tool_registry
        self.policy = policy
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.caller = caller
        self.validator = validator
        self.extractor = extractor

    def run(self, user_request: str, tool_candidates: List[str], timezone: str = "Asia/Seoul") -> Dict[str, Any]:
        state = ExecutionState()

        # 1) Plan
        plan_dict = self.planner.plan(user_request, tool_candidates, timezone)
        plan = self._parse_plan(plan_dict)

        # 2) Execute actions sequentially (MVP). Parallel/branch can be added later.
        for action in plan.actions:
            # 2.1 dependency check
            if not self._requires_satisfied(action, state):
                # Missing dependencies => fail fast or replan
                state.errors.append({
                    "action_id": action.id,
                    "type": "missing_requires",
                    "missing": [k for k in action.requires if k not in state.memory]
                })
                # In MVP: ask user or replan; here we choose replan
                return self._finalize_with_replan(user_request, tool_candidates, timezone, state, reason="missing_requires")

            contract = self.tool_registry.get_contract(action.tool)

            # 2.2 Policy gate
            decision, reason = self.policy.check_action(action, contract, state)
            if decision == "deny":
                state.history.append(ExecRecord(
                    action_id=action.id, tool=action.tool, status="skipped",
                    attempts=0, started_at=time.time(), ended_at=time.time(),
                    error=f"Denied by policy: {reason}"
                ))
                return self._finalize(plan, state, user_message=f"정책상 실행할 수 없는 작업이 포함되어 중단했습니다: {reason}")

            if decision == "require_confirm":
                # In product: trigger approval UI. Here: stop and ask.
                return self._finalize(plan, state, user_message=f"다음 작업은 승인 후 진행 가능합니다: {action.tool} / 사유: {reason}")

            # 2.3 Execute with retry loop
            started = time.time()
            attempts = 0
            last_error = None

            while attempts < action.retries_max_attempts:
                attempts += 1
                try:
                    payload = self.executor.fill_params(action, contract, state, plan.timezone)
                    # Validate payload schema
                    self.validator.validate(contract.input_schema, payload)

                    # If payload contains "MISSING" => ask user
                    missing_fields = self._find_missing(payload)
                    if missing_fields:
                        return self._finalize(plan, state, user_message=f"추가 정보가 필요합니다: {', '.join(missing_fields)}")

                    # Call tool
                    result = self.caller.call(action.tool, payload, action.timeout_ms)

                    # Validate output
                    self.validator.validate(contract.output_schema, result)

                    # Extract produces -> state
                    produced = self.extractor.extract(contract.produces_map, result)
                    state.memory.update(produced)

                    # Verify
                    verdict = self.verifier.verify(action, contract, payload, result, state)
                    if verdict.get("status") == "pass":
                        state.history.append(ExecRecord(
                            action_id=action.id, tool=action.tool, status="success",
                            attempts=attempts, started_at=started, ended_at=time.time()
                        ))
                        break

                    # Fail verdict
                    next_step = verdict.get("next", "retry")
                    if next_step == "retry":
                        last_error = verdict.get("reason", "verifier_fail")
                        time.sleep(action.retries_backoff_ms / 1000)
                        continue
                    if next_step == "ask_user":
                        return self._finalize(plan, state, user_message=f"확인이 필요합니다: {verdict.get('reason','')}")
                    if next_step == "replan":
                        return self._finalize_with_replan(user_request, tool_candidates, timezone, state, reason=verdict.get("reason","replan"))

                    # default => retry
                    last_error = verdict.get("reason", "verifier_fail")
                    time.sleep(action.retries_backoff_ms / 1000)

                except Exception as e:
                    last_error = str(e)
                    time.sleep(action.retries_backoff_ms / 1000)

            if attempts >= action.retries_max_attempts and last_error:
                state.history.append(ExecRecord(
                    action_id=action.id, tool=action.tool, status="failed",
                    attempts=attempts, started_at=started, ended_at=time.time(),
                    error=last_error
                ))
                return self._finalize(plan, state, user_message=f"작업 실행에 실패했습니다: {action.tool} / {last_error}")

        # 3) Compose final response
        return self._finalize(plan, state)

    # -------------------------
    # helpers
    # -------------------------

    def _parse_plan(self, plan_dict: Dict[str, Any]) -> ActionPlan:
        actions = []
        for a in plan_dict["actions"]:
            r = a.get("retries", {})
            actions.append(Action(
                id=a["id"],
                tool=a["tool"],
                intent=a["intent"],
                requires=a.get("requires", []),
                produces=a.get("produces", []),
                success_criteria=a.get("success_criteria", []),
                timeout_ms=a.get("timeout_ms", 20000),
                retries_max_attempts=r.get("max_attempts", 3),
                retries_backoff_ms=r.get("backoff_ms", 500),
            ))
        return ActionPlan(
            version=plan_dict["version"],
            goal=plan_dict["goal"],
            timezone=plan_dict["timezone"],
            actions=actions,
            final_response=plan_dict.get("final_response", {})
        )

    def _requires_satisfied(self, action: Action, state: ExecutionState) -> bool:
        return all(k in state.memory for k in action.requires)

    def _find_missing(self, payload: Any, path: str = "") -> List[str]:
        missing = []
        if isinstance(payload, dict):
            for k, v in payload.items():
                missing += self._find_missing(v, f"{path}.{k}" if path else k)
        elif isinstance(payload, list):
            for i, v in enumerate(payload):
                missing += self._find_missing(v, f"{path}[{i}]")
        else:
            if payload == "MISSING":
                missing.append(path or "unknown")
        return missing

    def _finalize_with_replan(self, user_request: str, tool_candidates: List[str], timezone: str, state: ExecutionState, reason: str) -> Dict[str, Any]:
        # In product: feed failure + state summary back to planner
        return {
            "status": "need_replan",
            "reason": reason,
            "state": {"memory": state.memory, "history": [r.__dict__ for r in state.history], "errors": state.errors}
        }

    def _finalize(self, plan: ActionPlan, state: ExecutionState, user_message: Optional[str] = None) -> Dict[str, Any]:
        # In product: call a Composer LLM. Here we return structured.
        return {
            "status": "ok" if user_message is None else "interrupted",
            "message": user_message,
            "goal": plan.goal,
            "memory": state.memory,
            "history": [r.__dict__ for r in state.history],
            "errors": state.errors
        }
```

### 구현 팁 (중요)

* **Verifier/Policy는 “코드 우선 + LLM 보조”**로 설계하면 비용/리스크가 크게 줄어듭니다.
* **Executor만 LLM이 payload 생성**을 담당하고, API 호출은 절대 LLM에게 맡기지 마세요.

---

# 4) Agent별 실제 프롬프트 설계

아래 프롬프트는 “출력 포맷 강제 + 환각 방지”에 최적화했습니다.
(운영에서는 `SYSTEM` + `DEVELOPER` + `USER` 역할로 분리 추천)

## 4.1 Planner Agent Prompt

**SYSTEM**

* 너는 워크플로우 플래너다.
* 너의 임무는 사용자 요청을 실행 가능한 Action Plan(JSON)으로 변환하는 것이다.
* 툴은 반드시 제공된 후보(tool_candidates) 중에서만 선택한다.
* 의존성은 `requires/produces`로 반드시 명시한다.
* 출력은 JSON만. 다른 텍스트 금지.

**DEVELOPER**

* 출력은 Action Plan JSON Schema(version=1.0)를 따라야 한다.
* 각 action은 단일 tool 호출만 포함해야 한다.
* `requires`는 state key 목록이다. 이전 action의 `produces`를 참조하라.
* 불명확한 정보가 있어도 계획은 만들되, 해당 정보는 Executor가 `"MISSING"`으로 표기하도록 유도하라(즉, Planner 단계에서는 질문을 만들지 말고 plan을 만든다).
* 위험한 tool(삭제/외부 공유/결제)이 포함될 것 같으면 action.risk.tags에 해당 태그를 추가하라.

**USER 입력 템플릿**

```json
{
  "user_request": "내일 오후 3시에 노션에 회의 기록 만들고 슬랙에 공유해줘",
  "timezone": "Asia/Seoul",
  "tool_candidates": [
    "notion.create_page",
    "notion.query_database",
    "slack.post_message",
    "slack.find_channel"
  ],
  "connected_services": ["notion", "slack"]
}
```

**Planner 기대 출력 예**

```json
{
  "version": "1.0",
  "goal": "회의 기록 생성 후 슬랙 공유",
  "timezone": "Asia/Seoul",
  "actions": [
    {
      "id": "a1",
      "tool": "notion.create_page",
      "intent": "write",
      "summary": "노션에 회의 기록 페이지 생성",
      "requires": [],
      "produces": ["page_url", "page_id"],
      "success_criteria": ["page_url exists"],
      "risk": { "level": "write", "tags": [] },
      "retries": { "max_attempts": 3, "backoff_ms": 500 },
      "timeout_ms": 20000
    },
    {
      "id": "a2",
      "tool": "slack.post_message",
      "intent": "notify",
      "summary": "슬랙 채널에 노션 링크 공유",
      "requires": ["page_url"],
      "produces": ["message_ts"],
      "success_criteria": ["message_ts exists"],
      "risk": { "level": "write", "tags": ["external_send"] },
      "retries": { "max_attempts": 3, "backoff_ms": 500 },
      "timeout_ms": 20000
    }
  ],
  "final_response": { "style": "concise", "include_links": true }
}
```

---

## 4.2 Policy Agent Prompt

**SYSTEM**

* 너는 정책 심사관이다.
* 주어진 Action Plan의 각 action에 대해 allow/deny/require_confirm 중 하나를 결정한다.
* 출력은 JSON만.

**DEVELOPER**

* 입력으로 `tenant_policy`, `user_scopes`, `actions`, `tool_contracts`가 주어진다.
* 규칙:

  * risk.level=destructive 또는 risk.tags에 delete/financial/share_public 포함 → 기본 require_confirm(또는 tenant_policy에 따라 deny)
  * external_send 태그는 기본 allow지만 PII가 의심되면 require_confirm
  * 필요한 OAuth scope가 user_scopes에 없으면 deny
* 출력 포맷:

```json
{
  "decisions": {
    "a1": { "decision": "allow", "reason": "" },
    "a2": { "decision": "require_confirm", "reason": "external_send" }
  }
}
```

**USER 입력 템플릿**

```json
{
  "tenant_policy": {
    "allow_external_send": true,
    "allow_destructive": false
  },
  "user_scopes": ["pages:write", "chat:write"],
  "actions": [ ... ],
  "tool_contracts": {
    "notion.create_page": { "risk_level": "write", "scopes_required": ["pages:write"] },
    "slack.post_message": { "risk_level": "write", "scopes_required": ["chat:write"] }
  }
}
```

---

## 4.3 Executor Agent Prompt

**SYSTEM**

* 너는 API 파라미터 생성기다.
* 반드시 제공된 `input_schema`에 맞춰 payload JSON만 출력한다.
* 모르는 필수값은 `"MISSING"`으로 채운다.
* 입력에 없는 사실을 지어내지 않는다(특히 id, 채널명, 사용자 정보).

**DEVELOPER**

* 네가 사용할 수 있는 정보는:

  * action(요청 의도)
  * tool input_schema
  * state.memory (이전 결과)
  * timezone
  * user_request 일부(필요한 경우)
* 금지:

  * schema에 없는 필드 추가
  * tool 변경 제안
  * 설명 텍스트 출력

**USER 입력 템플릿**

```json
{
  "action": {
    "id": "a2",
    "tool": "slack.post_message",
    "intent": "notify",
    "summary": "슬랙 채널에 노션 링크 공유",
    "requires": ["page_url"]
  },
  "input_schema": {
    "type": "object",
    "required": ["channel", "text"],
    "properties": {
      "channel": { "type": "string" },
      "text": { "type": "string" }
    }
  },
  "state_memory": {
    "page_url": "https://notion.so/page_123"
  },
  "timezone": "Asia/Seoul",
  "user_request": "내일 오후 3시에 노션에 회의 기록 만들고 슬랙에 공유해줘"
}
```

**Executor 기대 출력 예**

```json
{
  "channel": "MISSING",
  "text": "회의 기록이 생성되었습니다: https://notion.so/page_123"
}
```

(→ Orchestrator는 `"channel"`이 MISSING이므로 사용자에게 “어느 채널에 공유할까요?”만 물어봄)

---

## 4.4 Verifier Agent Prompt

**SYSTEM**

* 너는 실행 검증자다.
* action 실행 결과가 성공인지 판단하고 다음 행동(retry/ask_user/replan)을 결정한다.
* 출력은 JSON만.

**DEVELOPER**

* 가능한 한 “명확한 기준”으로 판단한다:

  * output_schema 충족 여부
  * action.success_criteria 충족 여부(예: page_url exists)
  * 다음 액션의 requires가 state에 생겼는지
* 출력 포맷:

```json
{
  "status": "pass"
}
```

또는

```json
{
  "status": "fail",
  "reason": "...",
  "next": "retry|ask_user|replan",
  "patch": { "suggested_payload_overrides": { } }
}
```

* retry는 동일 tool 재호출이 의미 있을 때만.
* ask_user는 필수 정보 누락/승인 필요일 때.
* replan은 step 누락/도구 선택 오류/의존성 설계 오류일 때.

**USER 입력 템플릿**

```json
{
  "action": { ... },
  "success_criteria": ["page_url exists"],
  "output_schema": { ... },
  "result": { "id": "page_123", "url": "https://notion.so/page_123" },
  "state_memory": { "page_url": "https://notion.so/page_123" }
}
```

**Verifier 기대 출력 예**

```json
{ "status": "pass" }
```

---

## 4.5 (선택) Final Composer Prompt

> 운영에서 응답 품질을 일정하게 만들고 싶으면 Composer를 분리하는 게 좋습니다.

**SYSTEM**

* 너는 결과 요약자다. 사용자가 이해하기 쉽게 최종 답변을 작성한다.

**DEVELOPER**

* 입력: goal, state.memory, history
* 출력: 한국어, 간결, 링크 포함, 불필요한 내부정보(스키마/도구id) 노출 금지

---

## 다음 작업 제안 (바로 구현 가능한 “세트”)

원하시면 제가 위 설계에 맞춰서:

1. **Action Plan JSON Schema 파일 2개**를 실제 파일로 만들어 드리고
2. Notion/Slack Tool Registry 샘플(contracts)도 함께
3. Orchestrator에 들어갈 **ResultExtractor(JSONPath-lite)**, **SchemaValidator(jsonschema)** 예시 코드

까지 한 번에 정리해드릴 수 있어요.

