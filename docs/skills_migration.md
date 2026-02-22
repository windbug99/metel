# Skills 기반 단계적 마이그레이션 계획

## 1) 목적과 원칙

### 목적
- 기존 "LLM 즉흥 라우팅 + 즉흥 파라미터 구성" 구조에서 발생하는 실패율을 낮춘다.
- 외부 서비스 호출을 스킬 계약(contract) 기반으로 제한해 실행 안정성을 높인다.
- 레거시와 꼬이지 않도록 빅뱅 교체가 아닌 단계적 교체로 운영 리스크를 관리한다.

### 핵심 원칙
- LLM은 **결정(router)** 만 담당하고, 실행은 **코드(skill runner)** 가 담당한다.
- 스킬은 문서가 아니라 **스키마 + 에러 규약 + 입력 수집 규약**을 가진 계약이다.
- 필수 파라미터는 최소화하고, 자동채움(autofill)을 기본 전략으로 한다.
- 부족한 값은 자연어 재추론이 아닌 `needs_input.missing_fields` 로 수집한다.
- 실패 원인은 구조화 로그로 남겨 재시도 정책과 프롬프트를 개선한다.
- 기본 응답 엔진은 LLM API이며, 서비스 지칭이 있으면 오케스트레이터가 스킬 단계를 추가한다.
- 실행 순서는 고정하지 않고 요청 의도에 따라 동적으로 결정한다.
  - `LLM_ONLY`: LLM만 수행
  - `LLM_THEN_SKILL`: LLM 결과를 스킬 입력으로 전달해 외부 서비스 반영
  - `SKILL_THEN_LLM`: 스킬로 외부 데이터 수집 후 LLM이 최종 답변 생성

## 2) 대상 범위와 비범위

### 범위
- Telegram 요청 처리 경로
- LLM Router V2
- Skill Runner V2
- Notion/Linear 핵심 기능 스킬(8개)
- V1/V2 병행 실행용 feature flag

### 비범위
- Notion/Linear 전체 API 표면적 지원
- 기타 서비스(예: Google, GitHub 등) 동시 전환
- 프론트엔드 대시보드 대규모 개편
- 기존 스키마 전체 재설계

## 2.1) 1차 지원 스킬 목록

### Notion (Page)
- `notion.page_create`
- `notion.page_search`
- `notion.page_update`
- `notion.page_delete`

### Linear (Issue)
- `linear.issue_create`
- `linear.issue_search`
- `linear.issue_update`
- `linear.issue_delete`

## 3) 목표 아키텍처

```text
[Telegram User Message]
        |
        v
[Orchestrator]
  1) Context Load (chat/user/project/oauth)
  2) Router V2 (LLM -> strict JSON)
        |
        +-- mode=LLM_ONLY --------> [LLM response] ---------------------------> Telegram
        |
        +-- mode=LLM_THEN_SKILL --> [LLM result] -> [Skill Runner V2] -------> Telegram
        |
        +-- mode=SKILL_THEN_LLM --> [Skill Runner V2 result] -> [LLM answer] -> Telegram
```

### 3.1) 기본 실행 정책
- 사용자가 서비스명을 지칭하지 않으면 `LLM_ONLY`를 기본으로 처리한다.
  - 예: "오늘 서울 날씨 알려줘" -> LLM API 응답
- 서비스 지칭 + 외부 반영 요청이면 `LLM_THEN_SKILL`로 처리한다.
  - 예: "오늘 서울 날씨를 notion에 페이지로 생성해줘"
  - 순서: LLM으로 날씨 결과 생성 -> `notion.page_create`로 반영
- 서비스 지칭 + 외부 데이터 참조 후 해석 요청이면 `SKILL_THEN_LLM`로 처리한다.
  - 예: "linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘"
  - 순서: `linear.issue_search`로 OPT-35 설명 조회 -> LLM으로 해결방법 정리

## 4) 단계적 교체(컷오버) 전략

### 단계 0. 계측 고정 (즉시)
- 현재 경로(V1)의 실패 사유를 최소 1주간 축적
- 최소 수집 항목
  - `request_id`, `chat_id`, `user_id`
  - `selected_service`, `selected_api`
  - `validation_failure`, `auth_failure`, `not_found`, `ambiguous`, `rate_limit`
  - `latency_ms`, `retry_count`

### 단계 1. V2 뼈대 도입 (병행, 기본 OFF)
- `router_v2`, `skill_runner_v2` 모듈 추가
- feature flag 추가
  - `SKILL_ROUTER_V2_ENABLED=false`
  - `SKILL_RUNNER_V2_ENABLED=false`
  - `SKILL_V2_SHADOW_MODE=true` (응답은 V1, 로그만 V2)

### 단계 2. 파일럿 스킬 2개 전환
- 대상
  - `notion.page_update`
  - `linear.issue_update`
- shadow mode에서 V1과 V2 결과 비교
  - 라우팅 일치율
  - 스키마 검증 실패율
  - needs_input 전환율
  - 최종 성공률

### 단계 3. 부분 트래픽 전환
- 기준 충족 시 점진 전환
  - 10% -> 30% -> 60% -> 100%
- 단계별 승격 조건 예시
  - 성공률 85% 이상
  - 치명 오류(auth/server) 증가 없음
  - 평균 latency 20% 이내 증가

### 단계 4. 레거시 제거
- V2 100% 전환 1~2주 안정화 후 V1 제거
- 제거 순서
  1. 라우터 V1 분기 삭제
  2. 즉흥 파라미터 수집 로직 삭제
  3. 미사용 텔레메트리 키 정리
  4. 운영 문서/런북 업데이트

## 5) 저장소 구조 제안

```text
backend/
  agent/
    router_v2.py
    orchestrator_v2.py
    skills/
      registry.py
      runner_v2.py
      contracts/
        notion.page_create.yaml
        notion.page_search.yaml
        notion.page_update.yaml
        notion.page_delete.yaml
        linear.issue_create.yaml
        linear.issue_search.yaml
        linear.issue_update.yaml
        linear.issue_delete.yaml
      providers/
        notion_client.py
        linear_client.py
      resolvers/
        notion_page_resolver.py
        linear_issue_resolver.py
      normalizers/
        notion_properties.py
        linear_fields.py
  app/
    routes/
      telegram.py
  tests/
    skills/
      test_notion_page_update_contract.py
      test_linear_issue_update_contract.py
      test_skill_runner_v2.py
      test_router_v2_json_output.py
```

## 6) 스킬 계약 파일 포맷

스킬 정의는 YAML 1개 파일로 관리한다. 내부에 JSON Schema를 포함한다.

```yaml
name: notion.page_update
version: 1.0.0
summary: Update a Notion page properties and optional comment

provider:
  service: notion
  auth: oauth
  scopes:
    - pages:write
    - databases:read

autofill:
  sources:
    - chat_context.project_id_to_notion_database_id
    - chat_context.last_active_page_id
  rules:
    - "if database_id is null, use mapped database"
    - "if target.page_id is null and target.title exists, resolve by title search"

input_schema:
  type: object
  additionalProperties: false
  required: [target, patch]
  properties:
    database_id:
      type: [string, 'null']
    target:
      type: object
      additionalProperties: false
      properties:
        page_id: { type: [string, 'null'] }
        title: { type: [string, 'null'] }
    patch:
      type: object
      additionalProperties: false
      required: [properties]
      properties:
        properties:
          type: object
          additionalProperties: true
        comment:
          type: [string, 'null']
    options:
      type: object
      additionalProperties: false
      properties:
        search_limit: { type: integer, minimum: 1, maximum: 20, default: 5 }
        allow_ambiguous_target: { type: boolean, default: false }
        dry_run: { type: boolean, default: false }

output_schema:
  type: object
  additionalProperties: false
  required: [status]
  properties:
    status:
      type: string
      enum: [success, needs_input, error]
    result:
      type: [object, 'null']
      additionalProperties: false
      properties:
        page_id: { type: string }
        url: { type: string }
        updated_fields:
          type: array
          items: { type: string }
        summary: { type: string }
    needs_input:
      type: [object, 'null']
      additionalProperties: false
      properties:
        missing_fields:
          type: array
          items: { type: string }
        questions:
          type: array
          items: { type: string }
        choices:
          type: [object, 'null']
          additionalProperties: true
    error:
      type: [object, 'null']
      additionalProperties: false
      properties:
        error_type:
          type: string
          enum: [auth, validation, not_found, ambiguous, rate_limit, server, network, unknown]
        message: { type: string }
        recoverable: { type: boolean }
        suggested_next_action: { type: string }

examples:
  - name: update_by_page_title
    input:
      database_id: null
      target:
        page_id: null
        title: 스프린트 회고
      patch:
        properties:
          Status: Done
        comment: null
      options:
        dry_run: false
```

### 6.1) 서비스별 스킬 계약 파일 규칙
- Notion 페이지 스킬: `notion.page_<action>.yaml`
- Linear 이슈 스킬: `linear.issue_<action>.yaml`
- 각 스킬은 공통 섹션을 포함한다.
  - `provider`, `autofill`, `input_schema`, `output_schema`, `examples`
- 식별자 필드는 가능하면 공통 키로 통일한다.
  - 권장: `result.resource_id` (Notion page_id, Linear issue_id를 공통 표현)
- 각 스킬은 단일 책임으로 유지한다.
  - 생성/검색/수정/삭제를 하나의 스킬로 합치지 않는다.

## 7) Router V2 계약

Router V2는 반드시 JSON만 반환해야 한다.

### Router 출력 스키마

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["mode", "confidence", "reason", "arguments"],
  "properties": {
    "mode": { "type": "string", "enum": ["LLM_ONLY", "LLM_THEN_SKILL", "SKILL_THEN_LLM"] },
    "skill_name": { "type": ["string", "null"] },
    "skill_chain": {
      "type": ["array", "null"],
      "items": { "type": "string" },
      "description": "순차 실행이 필요한 스킬 목록(최대 2개 권장)"
    },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "reason": { "type": "string" },
    "arguments": { "type": "object" },
    "llm_task": {
      "type": ["object", "null"],
      "description": "LLM이 수행해야 할 작업 정의(요약/생성/정리 등)"
    }
  }
}
```

### Router 규칙
- `mode=LLM_THEN_SKILL` 또는 `mode=SKILL_THEN_LLM`인 경우 `skill_name` 또는 `skill_chain`이 registry에 존재해야 한다.
- registry에 없는 스킬이면 실행 금지, `LLM_ONLY`로 강등하거나 안전 에러 반환.
- confidence 임계치 예시
  - `< 0.45`: LLM_ONLY
  - `>= 0.45`: Skill 연계 모드 후보

## 8) Skill Runner V2 의사코드

```python
# backend/agent/skills/runner_v2.py

def run_skill_v2(request_ctx, skill_name, arguments):
    request_id = request_ctx.request_id
    contract = registry.get(skill_name)
    if not contract:
        return error("validation", "unknown skill", recoverable=False)

    # 1) autofill
    enriched_args = autofill_args(contract.autofill, request_ctx, arguments)

    # 2) schema validate
    valid, issues = validate_json_schema(contract.input_schema, enriched_args)
    if not valid:
        return {
            "status": "needs_input",
            "needs_input": {
                "missing_fields": to_missing_fields(issues),
                "questions": build_questions(issues, request_ctx.locale),
                "choices": build_choices_if_possible(issues, request_ctx)
            }
        }

    # 3) resolve target
    resolved = resolve_target_for_skill(skill_name, request_ctx, enriched_args)
    if resolved.kind == "ambiguous":
        return {
            "status": "needs_input",
            "needs_input": {
                "missing_fields": ["target.page_id"],
                "questions": ["대상 페이지/이슈를 선택해 주세요."],
                "choices": {"candidates": resolved.candidates}
            }
        }
    if resolved.kind == "not_found":
        return error("not_found", "target not found", recoverable=True)

    # 4) provider payload normalize
    normalized_payload = normalize_properties_for_provider(
        skill_name=skill_name,
        database_schema=resolved.database_schema,
        args=enriched_args,
    )

    # 5) dry run
    if enriched_args.get("options", {}).get("dry_run") is True:
        return {
            "status": "success",
            "result": {
                "page_id": resolved.page_id,
                "url": resolved.url,
                "updated_fields": normalized_payload.preview_fields,
                "summary": "dry_run preview"
            }
        }

    # 6) execute API
    try:
        provider_result = provider_client.update(
            target_id=resolved.target_id,
            payload=normalized_payload,
        )
    except ProviderAuthError as e:
        return error("auth", str(e), recoverable=True)
    except ProviderRateLimitError as e:
        return error("rate_limit", str(e), recoverable=True)
    except ProviderValidationError as e:
        return error("validation", str(e), recoverable=True)
    except Exception as e:
        return error("unknown", str(e), recoverable=False)

    # 7) output normalize + validate
    output = {
        "status": "success",
        "result": {
            "page_id": provider_result.target_id,
            "url": provider_result.url,
            "updated_fields": provider_result.updated_fields,
            "summary": provider_result.summary,
        }
    }
    assert validate_json_schema(contract.output_schema, output)[0]
    return output
```

## 9) Telegram 질의 플로우 (동적 순서 + needs_input)

### 9.1 LLM_ONLY (기본)
1. 사용자: "오늘 서울 날씨 알려줘"
2. Router V2: `LLM_ONLY`
3. LLM 실행: 모델(`gpt-4o-mini` 또는 `gemini-2.5-flash-lite`)로 답변 생성
4. 텔레그램 응답: 날씨 답변 전달

### 9.2 LLM_THEN_SKILL (생성 후 반영)
1. 사용자: "오늘 서울 날씨를 notion에 페이지로 생성해줘"
2. Router V2: `LLM_THEN_SKILL` + `skill_name=notion.page_create`
3. LLM 실행: 날씨 결과/요약 생성
4. Runner 실행: LLM 결과를 page title/body로 매핑해 Notion 페이지 생성
5. 텔레그램 응답: 요약 + 생성된 Notion 링크 전달

### 9.3 SKILL_THEN_LLM (조회 후 해석)
1. 사용자: "linear의 OPT-35 이슈 설명을 해결하는 방법을 정리해줘"
2. Router V2: `SKILL_THEN_LLM` + `skill_name=linear.issue_search`
3. Runner 실행: OPT-35 이슈 설명 조회
4. LLM 실행: 조회된 설명을 기반으로 해결 방법 정리
5. 텔레그램 응답: 해결 가이드 전달

### 9.4 후보 충돌(ambiguous)
1. 사용자: "로그인 버그 상태 진행중으로"
2. Runner: title 검색 결과 3건
3. Runner 반환: `status=needs_input`, `choices.candidates[]`
4. Telegram: inline keyboard로 후보 출력
5. 사용자 선택: page_id 전달
6. 동일 skill 재호출 -> 성공

### 9.5 누락값 수집
1. 사용자: "페이지 상태 바꿔줘"
2. Runner: target 불충분 (`target.page_id|title` 없음)
3. Runner 반환: `missing_fields=[target.title]` + 질문
4. Telegram 질문: "어떤 페이지를 수정할까요? (예: 스프린트 회고)"
5. 사용자 답변 수집 후 재호출

### 9.6 텔레그램 상태 머신 제안

```text
IDLE
 -> ROUTE
 -> (LLM_ONLY -> REPLY -> IDLE)
 -> (LLM_THEN_SKILL -> RUN_LLM -> RUN_SKILL)
 -> (SKILL_THEN_LLM -> RUN_SKILL -> RUN_LLM)
RUN_SKILL
 -> SUCCESS -> REPLY -> IDLE
 -> NEEDS_INPUT -> ASK_USER -> WAITING_INPUT
WAITING_INPUT
 -> USER_REPLY -> MERGE_ARGS -> RUN_SKILL
 -> TIMEOUT -> CANCELLED_REPLY -> IDLE
 -> USER_CANCEL -> CANCELLED_REPLY -> IDLE
ERROR
 -> REPLY_ERROR -> IDLE
```

## 10) 서비스별 정규화 규칙

### 10.1) Notion 페이지 업데이트 정규화

#### 표준 키 -> Notion 속성명 매핑
- 내부 표준 키 권장: `status`, `priority`, `assignee`, `due`, `tags`
- 프로젝트별 매핑 테이블 예시
  - `status -> "Status"`
  - `priority -> "Priority"`
  - `assignee -> "Assignee"`
  - `due -> "Due"`

#### 타입별 정규화
- Select/Status: 대소문자/동의어 매핑 (`높음`, `high`, `High` -> `High`)
- People: `@me` -> 현재 사용자 notion id
- Date: `YYYY-MM-DD` 강제 변환
- Multi-select(tags): 문자열/배열 모두 허용 후 배열로 통일

### 10.2) Linear 이슈 업데이트 정규화
- 표준 키 권장: `title`, `description`, `state`, `priority`, `assignee`, `label`
- 매핑 예시
  - `state` -> Linear workflow state id/name
  - `assignee` -> Linear user id/email
  - `priority` -> Linear priority enum
- 타입별 규칙
  - `priority`: 자연어(`높음`, `긴급`) -> enum 정규화
  - `state`: 이름 입력 시 워크플로우 상태 조회 후 id 변환
  - `assignee`: `@me` 또는 이름 -> 사용자 id resolve

## 11) Feature Flag 설계

- `SKILL_ROUTER_V2_ENABLED`
  - Router V2 사용 여부
- `SKILL_RUNNER_V2_ENABLED`
  - Skill Runner V2 사용 여부
- `SKILL_V2_SHADOW_MODE`
  - 사용자 응답은 V1, 내부적으로 V2 병렬 실행/로그만 수집
- `SKILL_V2_TRAFFIC_PERCENT`
  - V2 대상 트래픽 샘플링 (0~100)
- `SKILL_V2_ALLOWLIST`
  - `chat_id` 또는 `user_id` 기반 우선 전환

## 12) 로깅/관측 스키마

### 필수 로그 필드
- 요청 공통
  - `request_id`, `chat_id`, `user_id`, `message_id`, `timestamp`
- 라우터
  - `router_version`, `mode`, `skill_name`, `confidence`, `reason`
- 검증
  - `input_validation_ok`, `missing_fields[]`, `invalid_fields[]`
- 실행
  - `provider`, `api_name`, `latency_ms`, `retry_count`, `provider_request_id`
- 결과
  - `status`, `error_type`, `recoverable`, `suggested_next_action`

### 대시보드 KPI
- skill별 성공률
- `needs_input` 전환율
- 에러 타입 분포(auth/validation/rate_limit)
- 평균 응답 시간 p50/p95
- V1 vs V2 성공률 비교

## 13) 테스트 전략

### 단위 테스트
- Router JSON schema 강제 검증
- `notion.page_update` 입력/출력 schema 검증
- `linear.issue_update` 입력/출력 schema 검증
- autofill 우선순위 검증
- ambiguous/not_found/validation 에러 분류 검증

### 통합 테스트
- Telegram 메시지 -> needs_input -> 버튼 선택 -> 성공까지 E2E
- dry_run true 경로 검증
- rate_limit 시 재시도/오류 메시지 검증

### 회귀 테스트
- V1 경로와 공존 시 기존 기능 불변 확인
- feature flag on/off 조합 테스트

## 14) 운영 런북

### 장애 대응 우선순위
1. auth 오류 급증: OAuth 토큰 만료/권한 스코프 확인
2. validation 급증: DB 속성명 변경 여부 확인
3. ambiguous 급증: title 기반 검색 비중 감소, page_id/issue_id 선택 유도
4. rate_limit 급증: 재시도 정책/쿨다운 적용

### 즉시 롤백 조건
- V2 전환 후 30분 기준
  - 성공률이 V1 대비 10%p 이상 하락
  - auth/server 에러가 2배 이상 증가
- 조치
  - `SKILL_RUNNER_V2_ENABLED=false`
  - 필요시 `SKILL_ROUTER_V2_ENABLED=false`

## 15) 마이그레이션 체크리스트

### 구현 전
- [x] V2 모듈 경로 생성
- [x] feature flag 정의
- [x] 공통 로그 필드 확정

### 파일럿(`notion.page_update`, `linear.issue_update`)
- [x] 계약 YAML 작성
- [x] input/output schema validator 연결
- [x] resolver/normalizer 구현
- [x] Telegram needs_input UI 연결(inline keyboard)
- [x] 단위/통합 테스트 통과

### 컷오버
- [ ] shadow mode 3일 이상
- [ ] 트래픽 10/30/60/100 단계 전환
- [ ] 레거시 제거 PR 분리
- [x] 운영 문서 업데이트

### 운영 전환 상세 체크(현재)
- [ ] 운영 환경에서 V2 Shadow mode 지표 수집(최소 3일)
  - 현재 상태: `대기(운영 네트워크/DNS 확인 필요)`
  - 완료 조건: `DAYS=3` 기준 gate report `PASS` + `shadow_count >= min_sample` + `shadow_ok_rate >= 0.85`
- [ ] 운영 환경에서 10% 트래픽 전환 검증(성공률/에러율/latency 기준)
  - 현재 상태: `대기(Shadow 3일 PASS 이후 진행)`
  - 완료 조건: `CURRENT_PERCENT=10` 기준 gate report `PASS` + canary 구간 `v2_selected_count > 0`

## 16) 구현 시작 순서 (권장 1주)

### Day 1-2
- Router V2 strict JSON 출력 고정
- Skill Registry/Contract Loader 구현
- Orchestrator에 실행 모드 3종(`LLM_ONLY`, `LLM_THEN_SKILL`, `SKILL_THEN_LLM`) 분기 추가

### Day 3-4
- `notion.page_update` / `linear.issue_update` runner 구현
- target resolve + needs_input + inline keyboard 연결
- `linear.issue_search -> LLM 정리` 체인 시나리오 구현

### Day 5
- shadow mode 운영, 로그 비교 리포트 생성

### Day 6-7
- 10% 트래픽 전환
- KPI 확인 후 다음 단계 결정

## 17) 진행 상태 (2026-02-22)

### 완료
- [x] V2 오케스트레이터 파일 추가 (`backend/agent/orchestrator_v2.py`)
- [x] `run_agent_analysis`에 V2 진입 플래그 분기 추가
- [x] 설정 플래그 추가
  - `skill_router_v2_enabled`
  - `skill_runner_v2_enabled`
- [x] `LLM_ONLY` 경로 구현
  - 예: "오늘 서울 날씨 알려줘"
- [x] `LLM_THEN_SKILL` 경로 1차 구현
  - `notion.page_create` 대응 (`notion_create_page`)
  - `notion.page_update` 대응 (`notion_append_block_children`)
  - `notion.page_delete` 대응 (`notion_update_page` with `in_trash=true`)
  - `linear.issue_create` 대응 (`linear_create_issue`)
  - `linear.issue_update` 대응 (`linear_update_issue`)
  - `linear.issue_delete` 대응 (`linear_update_issue` with `archived=true`)
- [x] `SKILL_THEN_LLM` 경로 1차 구현
  - `linear.issue_search -> LLM 정리`
  - `notion.page_search(+본문 조회) -> LLM 정리`
- [x] V2 `needs_input` 표준 응답 통합
  - 모호/누락 입력 시 `missing_fields/questions/choices` 구조화 반환
  - 예: Notion 페이지 후보 다중 매칭 시 선택지 반환
- [x] Router V2 LLM 라우팅(스키마 검증 + fallback) 1차 적용
  - `skill_router_v2_llm_enabled=true` 시 LLM JSON 라우팅 시도
  - JSON 파싱/검증 실패 시 규칙 라우터로 자동 fallback
  - 허용 스킬 allowlist 검증으로 임의 tool 발명 방지
- [x] V2 Shadow mode / 점진 전환 게이트 구현
  - `skill_v2_shadow_mode` (그림자 실행 후 legacy 응답 유지)
  - `skill_v2_traffic_percent` (0~100% 트래픽 샘플링)
  - `skill_v2_allowlist` (user_id allowlist 우선 전환)
  - plan notes에 rollout/shadow 실행 메타 기록
- [x] V2 전환 검증 리포트 스크립트 추가
  - `backend/scripts/eval_skill_v2_rollout.py`
  - `command_logs.detail`의 `skill_v2_*`/`router_source`를 집계
  - PASS/FAIL 기준: `v2_success_rate`, `v2_error_rate`, `v2_p95_latency_ms`, `min_sample`
- [x] V2 전환 게이트 실행 스크립트 추가
  - `backend/scripts/run_skill_v2_rollout_gate.sh`
  - 운영 시 `LIMIT/MIN_SAMPLE/TARGET_V2_SUCCESS/MAX_V2_ERROR_RATE/MAX_V2_P95_LATENCY_MS` 환경변수로 조정 가능
- [x] V2 전환 단계 결정 스크립트 추가
  - `backend/scripts/decide_skill_v2_rollout.py`
  - 게이트 JSON 결과를 바탕으로 `promote/hold/rollback` 및 다음 퍼센트 제안
- [x] V2 운영 사이클 스크립트 추가
  - `backend/scripts/run_skill_v2_rollout_cycle.sh`
  - gate + decision을 연속 실행하고 리포트/결정 JSON을 `docs/reports/`에 저장
- [x] V2 전환 결정 적용 스크립트 추가
  - `backend/scripts/apply_skill_v2_rollout_decision.py`
  - decision JSON의 `suggested_env`를 `.env`에 안전하게 반영(dry-run 기본)
- [x] Shadow 기간 기반(최근 N일) 게이트 평가 지원
  - `eval_skill_v2_rollout.py --days N` 추가(UTC 기준)
  - gate/cycle 스크립트에서 `DAYS` 환경변수로 동일 제어
  - 0% -> 10% 승격 시 `shadow_ok_rate`뿐 아니라 `shadow_count >= min_sample` 조건 추가
- [x] V2 단위 테스트 추가/통과
  - `backend/tests/test_orchestrator_v2.py`
  - `backend/tests/test_agent_loop.py`의 V2 우선 경로 테스트

### 진행 중
- [x] Notion/Linear 핵심 8개 스킬 계약 파일 초안 추가
  - 위치: `backend/agent/skills/contracts/*.json`
  - 대상: `notion.page_{create,search,update,delete}`, `linear.issue_{create,search,update,delete}`
  - 계약 검사기: `backend/scripts/check_skill_contracts.py`
  - 계약 테스트: `backend/tests/test_skill_contracts.py`
- [x] URL 본문 수집용 최소 스킬 계약 추가
  - `web.url_fetch_text` (`backend/agent/skills/contracts/web_url_fetch_text.json`)
  - 현재 단계는 계약 추가까지이며, 런타임 도구(`http_fetch_url_text`) 연결은 다음 단계에서 진행
- [x] 계약 파일을 런타임(오케스트레이터/runner)에서 직접 로드/검증하는 경로 연결
  - 오케스트레이터 allowlist를 계약 기반 `runtime_tools`로 전환
  - V2 실행 전 계약 검증(`validate_all_contracts`) 실패 시 fail-closed 처리
- [x] Router payload에 `skill_name` 계약 경로 연결
  - LLM 라우터가 `skill_name`만 반환해도 계약(`runtime_tools`)에서 실행 도구 유도
  - 규칙 라우터도 `skill_name`을 함께 기록해 계약 중심 메타 정합성 확보
- [x] 오케스트레이터 실행 분기의 `selected_tools` 하드코딩 역매핑 제거
  - 계약 기반 `infer_skill_name_from_runtime_tools`로 `skill_name` 추론
  - `target_services`도 계약의 provider 정보 우선 사용
  - `MODE_SKILL_THEN_LLM` 분기에서 `skill_name` 우선 매칭으로 실행 안정성 개선

### 다음 단계
- [ ] 운영 환경에서 V2 Shadow mode 지표 수집(최소 3일)
- [ ] 운영 환경에서 10% 트래픽 전환 검증(성공률/에러율/latency 기준)

### 운영 실행 명령 예시
- Shadow mode 지표 리포트(JSON 출력):
  - `cd backend && . .venv/bin/activate && python scripts/eval_skill_v2_rollout.py --limit 200 --min-sample 30 --max-v2-p95-latency-ms 12000 --output-json ../docs/reports/skill_v2_rollout_latest.json`
- Shadow/rollout 게이트 실행:
  - `cd backend && DAYS=3 ./scripts/run_skill_v2_rollout_gate.sh`
- 전환 단계 결정(예: 현재 10%):
  - `cd backend && . .venv/bin/activate && python scripts/decide_skill_v2_rollout.py --report-json ../docs/reports/skill_v2_rollout_latest.json --current-percent 10`
- 게이트 + 결정 일괄 실행(예: 현재 10%):
  - `cd backend && DAYS=3 CURRENT_PERCENT=10 ./scripts/run_skill_v2_rollout_cycle.sh`
- 게이트 + 결정 + .env 적용(예: 현재 10%):
  - `cd backend && DAYS=3 CURRENT_PERCENT=10 APPLY_DECISION=true ENV_FILE=.env ./scripts/run_skill_v2_rollout_cycle.sh`
- 사전점검만 실행:
  - `cd backend && . .venv/bin/activate && python scripts/check_skill_v2_rollout_prereqs.py --check-dns`
- 10% 전환 운영 플래그 예시:
  - `SKILL_ROUTER_V2_ENABLED=true`
  - `SKILL_RUNNER_V2_ENABLED=true`
  - `SKILL_V2_SHADOW_MODE=false`
  - `SKILL_V2_TRAFFIC_PERCENT=10`
- Shadow 3일 수집 운영 플래그 예시:
  - `SKILL_ROUTER_V2_ENABLED=true`
  - `SKILL_RUNNER_V2_ENABLED=true`
  - `SKILL_V2_SHADOW_MODE=true`
  - `SKILL_V2_TRAFFIC_PERCENT=0`
- 계약 검사:
  - `cd backend && . .venv/bin/activate && python scripts/check_skill_contracts.py`
- 주의:
  - rollout/shadow 평가 스크립트는 `command_logs` 조회를 위해 Supabase 연결이 필요하다.
  - 네트워크 또는 `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`가 없으면 report 생성 없이 cycle이 실패 종료된다.
  - `run_skill_v2_rollout_gate.sh`, `run_skill_v2_rollout_cycle.sh`는 기본적으로 preflight를 먼저 수행한다.
  - 특수 상황에서 preflight를 건너뛰려면 `SKIP_PREFLIGHT=true`를 명시한다.

### 운영 사이클 환경변수
- `CURRENT_PERCENT`: 현재 canary 퍼센트(0/10/30/60/100)
- `REQUIRE_SHADOW_OK_FOR_PROMOTE`: `true`면 0%->10% 승격 시 shadow_ok_rate 기준 적용
- `APPLY_DECISION`: `true`면 decision 결과를 `.env`에 자동 반영
- `ENV_FILE`: 자동 반영 대상 env 파일 경로(기본 `.env`)
- `LIMIT`, `MIN_SAMPLE`, `TARGET_V2_SUCCESS`, `MAX_V2_ERROR_RATE`, `MAX_V2_P95_LATENCY_MS`: 게이트 임계값/샘플 설정

---

## 부록 A) Router 프롬프트 최소 규약

```text
You are a router. Output JSON only.
Allowed modes: LLM_ONLY, LLM_THEN_SKILL, SKILL_THEN_LLM.
If mode includes skill execution, select skill from registry list exactly.
Do not invent skills. Do not add extra keys.
```

## 부록 B) needs_input 응답 템플릿(텔레그램)

```text
입력값이 더 필요합니다.
- 필요한 값: {missing_fields}
- 질문: {question}
선택 가능한 항목을 아래 버튼에서 골라주세요.
```

## 부록 C) 성공 응답 템플릿(텔레그램)

```text
완료했습니다.
- 대상: {page_title_or_issue_id}
- 변경: {updated_fields}
- 링크: {url}
```
