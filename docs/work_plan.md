# metel 프로토타입 개발 계획

## 1. 개요

본 문서는 **Promethium**의 AI 비서 SaaS 서비스인 **metel**의 핵심 플로우(웹사이트 사용자 계정 생성 및 로그인, 외부 서비스 OAuth 연동, 텔레그램 연결, 텔레그램 작업 요청 및 AI 답변)를 구현하기 위한 프로토타입 개발 계획을 상세히 기술합니다. 기획서 및 OpenClaw 분석 문서를 기반으로 기술 스택(Next.js, FastAPI, Supabase, python-telegram-bot, 사용자가 웹사이트 대시보드에서 선택 가능한 LLM API (Gemini-2.5-flash-lite, GPT-4o mini))을 활용하여 각 단계별 구현 내용, 진행 순서, 예상 소요 시간, 필요한 외부 서비스 설정, 그리고 완료 기준을 명시합니다.

## 2. 프로토타입 목표 플로우

1.  **웹사이트에서 구글 로그인으로 사용자 계정 생성**
2.  **로그인**
3.  **테스트용 Notion API 연결을 위한 OAuth 로그인**
4.  **Telegram 연결 기능**
5.  **텔레그램에서 작업 요청 및 AI 답변**

### 2.1 텔레그램 요청 처리 표준 7단계 (작업 기준선)

향후 구현/검증은 아래 7단계를 기준으로 진행한다.

1. **텔레그램에서 사용자가 작업 요청문 작성**
2. **에이전트가 요청문에서 작업 요구사항 도출**
3. **작업 요구사항 기반으로 타겟 서비스/필요 API 선정**
4. **워크플로우 생성**
5. **워크플로우 기반 작업 진행**
6. **결과 정리**
7. **텔레그램으로 사용자에게 결과 전달**

현재 구현 상태(2026-02-19 기준):
- **1~3단계 구현 완료**: `backend/app/routes/telegram.py`에서 자연어 메시지를 `run_agent_analysis`로 전달하고, 요구사항/서비스/API를 도출.
- **4~7단계 구현 진행 중(하이브리드)**:
  - 워크플로우 생성: `backend/agent/planner.py` + `backend/agent/planner_llm.py` (LLM planner + rule fallback)
  - 자율 실행 루프: `backend/agent/autonomous.py` (action/tool_call/final/replan, verifier, turn/tool/timeout budget)
  - 규칙 실행기: `backend/agent/executor.py` (Notion 특화 안정 실행 경로)
  - 결과 정리/전달: `backend/app/routes/telegram.py`
- **실제 동작 정리**:
  - LLM planner가 계획을 만들고 자율 루프를 우선 시도
  - 자율 루프 실패(`turn_limit`, `replan_limit` 등) 시 rule executor로 fallback
  - 따라서 현재는 **완전 자율 only가 아니라 자율+규칙 하이브리드**
- **최우선 남은 작업**: fallback 빈도 감소(자율 성공률 향상), rule 경로 축소, plan-step 실행 일관성 강화.

### 2.2 향후 구현 단계 (최우선: 자율 LLM 에이전트 루프 완성)

1. **자율 루프 엔진 완성**
   - 목표: Planner 출력 plan을 step 단위로 실행하고 Verifier로 완료 검증
   - 필수: `max_turns`, `max_tool_calls`, `timeout`, `replan(1회)` 강제
2. **Notion 복합 워크플로우의 분기 제거**
   - 목표: 조회 → 요약 → 생성 → 본문추가를 고정 분기 없이 plan-driven 실행
3. **실패 원인 가시화/복구**
   - "문장 이해 실패" vs "페이지 미존재" vs "권한/API 실패"를 분리해 사용자 메시지 제공
4. **관측/회귀 방지**
   - 단계별 로그 고도화 + Notion E2E 테스트 시나리오 확장
5. **그 다음 멀티서비스 확장**
   - Spotify는 Notion 에이전트 완성 후 동일 패턴으로 추가

진행 메모(2026-02-19):
- `tool_runner`에 schema 기반 입력 검증(`required/type/min/max/enum`) 추가
- `executor`가 `plan.selected_tools` 우선 순서를 반영해 tool 선택
- 서비스 분기 실행기 추가(Notion/Spotify 경로; Spotify는 토큰/실행기 확장 준비 단계)
- Notion 특정 페이지 대상 시나리오 확장:
  - `"노션에서 <페이지명>의 내용 중 상위 N줄 출력"`
  - `"노션에서 <페이지명> 요약해줘"`
  - `"노션에서 <페이지명>에 <내용> 추가해줘"` (append block children)
  - `"노션에서 <페이지명> 페이지 제목을 <새 제목>으로 변경"` (update page properties)
  - `"노션 데이터소스 <id> 최근 N개 조회"` (query data source)
  - `"노션에서 <페이지명> 페이지 삭제해줘"` (archive page)
- E2E 성격 테스트(모킹 기반) 추가:
  - 제목 변경/데이터소스 조회/페이지 아카이브 실행 경로 검증
  - 실행 오류 표준화 메시지(`auth_error` 등) 검증
- 실패 메시지 표준화:
  - `execute_agent_plan`에서 HTTPException detail 코드를 사용자 친화 메시지/요약/표준 오류코드로 매핑
  - 표준 코드 예: `notion_not_connected`, `auth_error`, `rate_limited`, `validation_error`, `upstream_error`
- 텔레그램 응답 가이드 강화:
  - `backend/app/routes/telegram.py`에서 `analysis.execution.artifacts.error_code`를 읽어 오류 가이드 문구를 사용자 응답에 자동 첨부
  - command log `error_code`도 표준 코드 우선 기록
- 실행 모드 가시성 강화:
  - 텔레그램 응답에 `plan_source` + `execution_mode` + `autonomous_fallback_reason` 표시
- 자율 루프 수렴 개선(2026-02-19):
  - `autonomous.py`에서 요청 의도 기반 도구 우선순위 정렬 적용
  - 자율 루프 도구 후보를 최대 8개로 축소(Planner가 선택한 도구 우선 고정)
  - 자율 액션 프롬프트에 `workflow_steps` 주입 및 "필요 tool_call 완료 전 final 금지" 원칙 추가
- 자율 실행 정책 강화(2026-02-19):
  - `loop.py`에서 **plan_source와 무관하게** `LLM_AUTONOMOUS_ENABLED=true`이면 자율 루프를 우선 실행
  - 즉, `rule planner`로 계획이 만들어진 경우에도 자율 실행을 먼저 시도하고 실패 시에만 rule executor로 fallback
  - 관련 단위 테스트 추가: `test_run_agent_analysis_prefers_autonomous_even_with_rule_plan`
- Planner-Execution 정합성 보강(2026-02-19):
  - `loop.py`에서 LLM planner 결과의 필수 도구 누락을 사전 검증
  - 삭제/데이터소스/추가/생성/요약/조회 의도별 최소 도구 조건 검사
  - 불일치 시 자동으로 rule planner로 재계획(`plan_realign_from_llm:*`) 후 실행
- 텔레메트리 활용 UI 보강(2026-02-19):
  - 대시보드 명령 로그 영역에 Agent 실행 지표 카드 추가
  - `execution_mode(auto/rule)`, `plan_source(llm/rule)`, `success/error`, `fallback 상위 사유`를 시각화
  - fallback 원인(top 3) 기반으로 다음 프롬프트/도구 정책 튜닝 근거 확보
- 텔레그램 오류/폴백 가이드 강화(2026-02-19):
  - `verification_failed`에 대해 세부 원인(`move_requires_update_page` 등)을 사용자 메시지에 노출
  - `autonomous_fallback_reason`별 `fallback_hint`를 응답에 추가해 재시도 방법 안내
  - command log에는 세부 사유를 `autonomous_fallback_reason`/`verification_reason` 필드로 일관 기록
- 자율 재시도 프롬프트 강화(2026-02-19):
  - `loop.py`에서 자율 1차 실패 원인(`turn_limit` 등)에 따라 재시도 가이드를 생성
  - 재시도 호출(`run_autonomous_loop`)에 `extra_guidance`를 주입해 동일 실패 반복 가능성을 감소
  - 관련 테스트: `test_run_agent_analysis_autonomous_retry_then_success`에서 guidance 전달 검증
- 삭제/생성 품질 보강:
  - 삭제 의도 판별 정규식 개선(예: "삭제 테스트 페이지"를 삭제 요청으로 오인하지 않음)
  - 다중 제목 지정 요약 생성 지원(예: `"더 코어 3", "사이먼 블로그"` 지정 조회)
  - 상위 페이지 하위 생성 지원(예: `"일일 회의록 페이지 아래 나의 일기 페이지 생성"`)
- Notion 제약 대응:
  - workspace 최상위 페이지 API 아카이브 불가(`Archiving workspace level pages via API not supported`)를 명시적으로 사용자 안내
  - 생성 기본 parent를 제어하는 `NOTION_DEFAULT_PARENT_PAGE_ID` 도입
- 실제 Notion 통합 테스트 골격 추가:
  - `backend/tests/integration/test_notion_live.py`
  - 기본은 skip, 환경변수로 선택 실행:
    - `RUN_NOTION_LIVE_TESTS=true`
    - (쓰기 테스트) `RUN_NOTION_LIVE_WRITE_TESTS=true`
    - `NOTION_LIVE_TOKEN`, `NOTION_LIVE_PAGE_ID` 등
- 라이브 테스트 범위 확장:
  - 읽기: `search_pages`, `retrieve_block_children`, `query_data_source`
  - 쓰기: `update_page_title_roundtrip`, `append_block_children`
  - 토큰 사전검증: `users/me` 호출로 invalid token 조기 진단
- 테스트 상태:
  - 단위/시나리오 테스트 통과(최근 수정 기준 `backend/tests/test_agent_executor_e2e.py`, `test_agent_loop.py`, `test_telegram_command_mapping.py`)
- LLM 자율 에이전트 1차 착수:
  - `backend/agent/planner_llm.py` 추가 (OpenAI chat completions 기반 planner)
  - `loop`에서 `LLM planner -> 실패 시 rule planner fallback` 적용
  - 실행 결과에 `plan_source`(`llm`/`rule`) 추가
  - 관련 env: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `LLM_PLANNER_ENABLED`,
    `LLM_PLANNER_PROVIDER`, `LLM_PLANNER_MODEL`,
    `LLM_PLANNER_FALLBACK_PROVIDER`, `LLM_PLANNER_FALLBACK_MODEL`

### 2.3 상태 체크리스트 (코드 기준)

- 완료:
  - service resolver / guide retriever / tool_specs registry
  - LLM planner + rule fallback 경로
  - Notion 핵심 read/write tool 호출과 에러 표준화
  - Telegram 응답에 실행 단계/오류 가이드 출력
- 완료(최근 보강):
  - 자율 루프 엔진(`autonomous.py`)과 fallback reason 노출
  - 다중 제목 지정 생성/요약, 하위 페이지 생성, append/rename/archive 핵심 케이스
  - Notion workspace-level archive 제약 감지 및 안내
- 부분 완료:
  - planner 출력 기반 자율 실행이 동작하지만 실패 시 rule fallback 비중이 아직 높음
  - 완전한 plan-step 범용 실행기보다 Notion 도메인 분기 코드가 여전히 존재
- 미완:
  - 자율 루프 성공률 목표치 달성(현재 일부 요청에서 `turn_limit`/`replan_limit`)
  - 멀티서비스(Spotify 등)에 Notion 수준의 실행 완성도 확장
  - 자율 루프와 rule executor의 단일 실행 추상화(중복 분기 제거)

### 2.4 텔레그램 실사용 QA 현황 (2026-02-19)

- 통과:
  - `"더 코어 3", "사이먼 블로그" 요약 -> "삭제 테스트 페이지 1" 생성`
  - `"일일 회의록 페이지 아래 나의 일기 페이지 생성"`
  - `"나의 일기 페이지 삭제해줘"` (하위 페이지 기준)
  - `"노션 데이터소스 invalid-id 조회"` 입력 검증/가이드 출력
- 제약:
  - Notion API 정책상 **workspace 최상위 페이지 아카이브 불가**
  - 해결: 하위 페이지로 생성/이동 후 삭제하거나 Notion UI에서 직접 삭제
- 운영 설정 권장:
  - `NOTION_DEFAULT_PARENT_PAGE_ID` 설정으로 생성 페이지를 기본적으로 삭제 가능한 하위 경로에 배치

## 3. 개발 단계별 상세 계획

### 3.1. Phase 1: 초기 환경 설정 및 기본 웹 서비스 구축

#### 3.1.1. 프로젝트 초기화 (Next.js, FastAPI)

*   **구현 내용:**
    *   `frontend` 디렉토리에 Next.js 프로젝트 생성 및 기본 설정.
    *   `backend` 디렉토리에 FastAPI 프로젝트 생성 및 기본 설정.
    *   Next.js와 FastAPI 간의 기본적인 통신 테스트 (예: 간단한 API 엔드포인트).
*   **진행 순서:**
    1.  Next.js 프로젝트 생성 (`npx create-next-app@latest frontend`).
    2.  FastAPI 프로젝트 생성 및 `main.py` 파일 작성.
    3.  CORS 설정 등 기본 백엔드 설정.
    4.  프론트엔드에서 백엔드 호출 테스트.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** Next.js 개발 서버와 FastAPI 개발 서버가 정상적으로 실행되고, 프론트엔드에서 백엔드 API를 성공적으로 호출할 수 있음.

#### 3.1.2. Supabase 설정 및 연동 (DB, Auth)

*   **구현 내용:**
    *   Supabase 프로젝트 생성 및 PostgreSQL 데이터베이스 초기 설정.
    *   사용자 관리 테이블 (`users`) 스키마 정의.
    *   Supabase Auth를 Next.js 프로젝트에 연동하여 사용자 인증 기능 구현.
    *   FastAPI에서 Supabase 클라이언트를 사용하여 데이터베이스 접근 설정.
*   **진행 순서:**
    1.  Supabase 웹사이트에서 새 프로젝트 생성.
    2.  `users` 테이블 스키마 정의 (id, email, created_at 등).
    3.  Next.js에 `@supabase/auth-helpers-nextjs` 또는 유사 라이브러리 설치 및 설정.
    4.  FastAPI에 `supabase-py` 설치 및 클라이언트 초기화.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** Supabase 프로젝트 생성, API Key 및 URL 확보.
*   **완료 기준:** 웹사이트에서 Supabase를 통해 사용자 회원가입 및 로그인이 가능하며, FastAPI에서 Supabase DB에 데이터를 읽고 쓸 수 있음.

#### 3.1.3. Google OAuth 연동 (웹사이트 로그인)

*   **구현 내용:**
    *   Supabase Auth의 Google OAuth 공급자 설정.
    *   Google Cloud Console에서 OAuth 클라이언트 ID 및 Secret 발급.
    *   Next.js 웹사이트에서 Google 로그인 버튼 구현 및 연동.
*   **진행 순서:**
    1.  Google Cloud Console에서 새 프로젝트 생성 및 OAuth 동의 화면 설정.
    2.  OAuth 2.0 클라이언트 ID 생성 (웹 애플리케이션 타입).
    3.  Supabase Auth 설정에서 Google 공급자 활성화 및 클라이언트 ID/Secret 입력.
    4.  Next.js 로그인 페이지에 Google 로그인 버튼 추가.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** Google Cloud Console에서 OAuth 클라이언트 ID 및 Secret 발급, 리디렉션 URI 설정.
*   **완료 기준:** 웹사이트에서 Google 계정을 통해 회원가입 및 로그인이 성공적으로 이루어짐.

### 3.2. Phase 2: 외부 서비스 OAuth 연동 (웹사이트)

#### 3.2.1. Notion OAuth 연동

Notion은 생산성 도구로서 다양한 API를 제공하며, OAuth 연동이 비교적 용이하여 **metel**의 다양한 기능을 테스트하기에 적합합니다. (예: 페이지 생성, 데이터베이스 관리, 콘텐츠 검색 등)

*   **구현 내용:**
    *   Notion Integration 생성 및 OAuth 설정.
    *   FastAPI 백엔드에 Notion OAuth 콜백 엔드포인트 구현.
    *   사용자별 Notion Access Token을 Supabase에 저장.
    *   웹사이트 대시보드에서 Notion 연결 버튼 및 연결 상태 표시.
*   **진행 순서:**
    1.  Notion Developer 사이트에서 새 Integration 생성 및 Redirect URI 설정.
    2.  FastAPI에 Notion OAuth 흐름 처리 로직 구현.
    3.  Supabase `user_tokens` 테이블에 Notion 토큰 저장 로직 추가.
    4.  Next.js 대시보드에 Notion 연결 UI 구현.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** Notion Integration Secret 발급, Redirect URI 설정.
*   **완료 기준:** 웹사이트에서 Notion 계정을 성공적으로 연결하고, FastAPI 백엔드에서 해당 사용자의 Notion API 토큰을 저장할 수 있음.

### 3.3. Phase 3: 텔레그램 봇 서비스 구축

#### 3.3.1. Telegram Bot API 설정 및 `python-telegram-bot` 연동

*   **구현 내용:**
    *   BotFather를 통해 텔레그램 봇 생성 및 API 토큰 발급.
    *   FastAPI 백엔드에 `python-telegram-bot` 라이브러리 설치 및 봇 인스턴스 초기화.
    *   기본 `/start`, `/help` 명령어 처리 및 간단한 메시지 에코 기능 구현.
    *   Webhook 또는 Polling 방식 설정 (MVP는 Polling으로 시작, 이후 Webhook 전환 고려).
*   **진행 순서:**
    1.  텔레그램 BotFather를 통해 새 봇 생성 및 토큰 발급.
    2.  FastAPI `backend/bot/telegram_bot.py` 파일 생성 및 `Application` 객체 초기화.
    3.  `CommandHandler`를 사용하여 `/start`, `/help` 명령어 핸들러 등록.
    4.  `MessageHandler`를 사용하여 일반 텍스트 메시지 에코 핸들러 등록.
    5.  Polling 방식으로 봇 실행 테스트.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 텔레그램 BotFather에서 봇 토큰 발급.
*   **완료 기준:** 텔레그램 봇이 정상적으로 동작하며, 사용자 메시지에 응답할 수 있음.

#### 3.3.2. 사용자-텔레그램 봇 연결 기능 (웹사이트)

*   **구현 내용:**
    *   웹사이트 대시보드에 텔레그램 봇 연결을 위한 UI 구현.
    *   사용자별 텔레그램 `chat_id`를 Supabase에 저장하는 기능 구현.
    *   텔레그램 봇이 특정 사용자에게 메시지를 보낼 수 있도록 `chat_id`를 활용.
*   **진행 순서:**
    1.  웹사이트 대시보드에 텔레그램 연결 안내 및 버튼 추가 (예: "봇에게 /start 메시지 보내기").
    2.  텔레그램 봇의 `/start` 명령어 핸들러에서 사용자 `chat_id`를 추출하여 Supabase `users` 테이블에 저장 (기존 사용자 레코드에 업데이트).
    3.  봇이 사용자에게 연결 성공 메시지를 보낼 수 있는지 테스트.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 웹사이트에서 텔레그램 봇 연결 안내를 제공하고, 사용자가 봇에게 `/start` 메시지를 보내면 해당 사용자의 `chat_id`가 Supabase에 저장되며, 봇이 사용자에게 성공적으로 메시지를 보낼 수 있음.

### 3.4. Phase 4: AI 에이전트 핵심 로직 구현

#### 3.4.1. LLM API 연동 (Gemini-2.5-flash-lite, GPT-4o mini)

*   **구현 내용:**
    *   선택된 LLM API (Gemini-2.5-flash-lite 또는 GPT-4o mini)에 대한 API 키 발급 및 FastAPI 백엔드에 설정.
    *   선택된 LLM에 맞는 Python 클라이언트 라이브러리 설치 (예: `google-generativeai` 또는 `openai`).
    *   간단한 LLM API 호출 테스트 (예: 특정 프롬프트에 대한 응답).
    *   **웹사이트 대시보드에 LLM 모델 선택 UI/기능 추가.**
*   **진행 순서:**
    1.  각 LLM 제공자 웹사이트에서 API 키 발급 (Google Cloud Console, OpenAI).
    2.  FastAPI 프로젝트에 `google-generativeai` 또는 `openai` 라이브러리 설치.
    3.  `backend/agent/agent.py` 파일에 선택된 LLM 클라이언트 초기화 및 간단한 API 호출 함수 작성.
    4.  Next.js 웹사이트 대시보드에 사용자가 LLM 모델을 선택할 수 있는 UI 컴포넌트 구현 및 선택 정보 저장 로직 추가.
*   **예상 소요 시간:** 0.5일
*   **외부 서비스 설정:** 각 LLM API 키 발급.
*   **완료 기준:** FastAPI 백엔드에서 선택된 LLM API를 성공적으로 호출하고 응답을 받을 수 있으며, 웹사이트 대시보드에서 LLM 모델 선택 기능이 정상 작동함.

#### 3.4.2. 에이전트 루프 구현 (OpenClaw 분석 기반)

*   **구현 내용:**
    *   OpenClaw 분석 문서에서 제시된 에이전트 루프 패턴을 `backend/agent/agent.py`에 구현.
    *   **사용자가 선택한 LLM 모델에 따라 동적으로 LLM 호출, `tool_use` 처리, `end_turn` 조건에 따른 루프 종료 로직 포함.**
    *   세션 키 기반의 대화 기록 로드 및 저장 기능 (Supabase 또는 Redis 연동).
*   **진행 순서:**
    1.  `run_agent_turn` 함수 구조화 (LLM 호출, 응답 파싱, `stop_reason` 처리).
    2.  `serialize_content` 함수 구현.
    3.  대화 기록을 저장하고 로드하는 `load_session`, `append_to_session` 함수 (초기에는 파일 시스템, 이후 Supabase 또는 Redis로 전환).
*   **예상 소요 시간:** 3일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 에이전트 루프가 기본적으로 동작하며, LLM과 상호작용하여 `tool_use` 또는 `end_turn` 응답을 처리할 수 있음.

#### 3.4.3. Tool Use 기능 구현 (기본 Tool 정의)

*   **구현 내용:**
    *   `backend/agent/tools.py`에 Notion API를 호출하는 더미 Tool 함수 정의.
    *   `execute_tool_fn` 함수를 구현하여 LLM이 요청한 Tool을 실행하고 결과를 반환.
    *   **선택된 LLM API의 `tools` 또는 `functions` 파라미터에 Tool 정의를 전달.**
*   **진행 순서:**
    1.  `tools.py`에 `create_notion_page`, `get_notion_database_items` 등 Notion 관련 더미 Tool 함수 정의.
    2.  `execute_tool_fn` 함수에서 Tool 이름에 따라 적절한 더미 Tool 함수를 호출하도록 구현.
    3.  `run_agent_turn` 함수에서 선택된 LLM API 호출 시 `tools` 또는 `functions` 파라미터에 Tool 정의 전달.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** 없음 (실제 API 호출은 다음 단계에서 구현).
*   **완료 기준:** 에이전트가 `tool_use`를 요청하면 `execute_tool_fn`이 호출되어 더미 Tool이 실행되고, 그 결과가 다시 LLM에게 전달될 수 있음.

#### 3.4.4. 세션/메모리 관리 (Supabase 연동)

*   **구현 내용:**
    *   OpenClaw 분석 문서의 컨텍스트 오버플로우 방지 (Compaction) 로직을 `backend/agent/memory.py`에 구현.
    *   대화 기록을 Supabase 데이터베이스에 저장하고 로드하는 기능 구현.
    *   `Upstash (Redis)`를 활용하여 세션 캐싱 또는 임시 데이터 저장 고려 (MVP에서는 Supabase로 시작).
*   **진행 순서:**
    1.  Supabase에 `sessions` 테이블 생성 (session_key, messages_json, last_updated 등).
    2.  `load_session`, `append_to_session`, `save_session` 함수를 Supabase 연동으로 변경.
    3.  `compact_if_needed` 함수 구현 및 `run_agent_turn`에 통합.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** Upstash (Redis) 계정 생성 및 API Key 확보 (선택 사항).
*   **완료 기준:** 사용자별 대화 세션이 Supabase에 저장되고 로드되며, 컨텍스트 오버플로우 방지 로직이 동작하여 대화가 길어져도 안정적으로 처리됨.

### 3.5. Phase 5: 웹사이트 - 텔레그램 - AI 연동 및 테스트

#### 3.5.1. 웹사이트에서 텔레그램 봇으로 작업 요청 전달

*   **구현 내용:**
    *   웹사이트 대시보드에 AI 비서에게 작업을 요청할 수 있는 입력 필드 및 버튼 구현.
    *   웹사이트에서 입력된 작업 요청을 FastAPI 백엔드로 전송하는 API 엔드포인트 구현.
    *   FastAPI 백엔드에서 해당 요청을 텔레그램 봇을 통해 사용자에게 전달 (또는 직접 AI 에이전트 호출).
*   **진행 순서:**
    1.  Next.js 대시보드에 작업 요청 입력 폼 추가.
    2.  FastAPI에 `POST /api/request_task` 엔드포인트 구현.
    3.  이 엔드포인트에서 사용자 ID를 기반으로 텔레그램 `chat_id`를 조회하고, 텔레그램 봇을 통해 사용자에게 메시지 전송 (예: "웹사이트에서 '[요청 내용]' 작업이 접수되었습니다.").
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 웹사이트에서 작업 요청을 제출하면, 해당 내용이 텔레그램 봇을 통해 사용자에게 전달됨.

#### 3.5.2. 텔레그램 봇에서 AI 에이전트 호출 및 응답 처리

*   **구현 내용:**
    *   텔레그램 봇이 사용자 메시지를 수신하면, AI 에이전트의 `run_agent_turn` 함수를 호출하도록 연동.
    *   AI 에이전트의 최종 응답을 텔레그램 봇을 통해 사용자에게 다시 전달.
    *   OpenClaw 분석 문서의 `build_context_header` 및 `check_access` 로직을 텔레그램 봇에 적용.
*   **진행 순서:**
    1.  텔레그램 봇의 메시지 핸들러에서 `check_access`를 통해 사용자 인증 확인.
    2.  인증된 사용자의 메시지를 `run_agent_turn` 함수에 전달.
    3.  `run_agent_turn`의 최종 응답을 텔레그램 `update.message.reply_text`를 통해 사용자에게 전송.
    4.  `build_context_header`를 사용하여 시스템 프롬프트에 컨텍스트 추가.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 텔레그램에서 사용자 메시지를 보내면 AI 에이전트가 이를 처리하고, 그 응답이 텔레그램을 통해 사용자에게 전달됨.

#### 3.5.3. 종합 테스트 및 디버깅

*   **구현 내용:**
    *   프로토타입의 전체 플로우 (웹사이트 로그인 → 외부 서비스 연동 → 텔레그램 연결 → 텔레그램 작업 요청 → AI 답변)에 대한 통합 테스트.
    *   발견된 버그 수정 및 안정성 확보.
    *   로그 시스템을 활용한 문제 진단.
*   **진행 순서:**
    1.  각 단계별로 구현된 기능을 통합하여 시나리오 기반 테스트 수행.
    2.  테스트 케이스 작성 (예: Notion 페이지 생성 요청 등).
    3.  FastAPI 및 Next.js 로그를 모니터링하며 문제점 파악 및 수정.
*   **예상 소요 시간:** 3일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 프로토타입의 핵심 플로우가 오류 없이 정상적으로 동작하며, 사용자 경험이 매끄러움.

### 3.6. Phase 6: 규칙 매핑 → LLM 자율 에이전트 전환

#### 3.6.1. 에이전트 실행 계약(Contract) 정의

*   **구현 내용:**
    *   `backend/agent/`에 Planner/Executor/Verifier 역할을 분리.
    *   if-else 규칙 분기가 아니라 `tool_use` 루프를 표준 실행 경로로 고정.
    *   실행 제한(`max_turns`, `max_tool_calls`, `timeout`)을 공통 적용.
*   **진행 순서:**
    1.  에이전트 상태 모델(`goal`, `plan`, `step_results`, `final_answer`) 정의.
    2.  Executor를 `plan.steps` 기반 실행기로 전환(의도별 분기 최소화).
    3.  Verifier에서 `success_criteria` 충족 여부 검사.
    4.  실패 시 재계획(replan) 정책 1회 적용 후 재실행.
    5.  budget 초과/치명 오류 시 안전 종료 및 사용자 안내.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 복합 요청이 고정 분기 없이 루프 내에서 단계적으로 처리됨.

#### 3.6.2. Notion Tool 카탈로그 정식화

*   **구현 내용:**
    *   Notion 공식 레퍼런스 기반 도구를 사전 등록하고 JSON Schema를 고정.
    *   읽기/쓰기 도구를 분리하고 권한 범위를 명시.
*   **진행 순서:**
    1.  Core Read: `search`, `retrieve page`, `retrieve block children`, `query data source` 구현.
    2.  Core Write: `create page`, `update page`, `append block children`, `delete block` 구현.
    3.  Tool 에러 표준 응답 형식(`ok/data/error/request_id`) 통일.
*   **예상 소요 시간:** 2일
*   **외부 서비스 설정:** Notion Integration 권한(scope/capability) 점검.
*   **완료 기준:** 에이전트가 복합 Notion 작업에서 필요한 도구를 동적으로 선택/호출할 수 있음.

#### 3.6.3. 복합 시나리오 E2E 검증

*   **구현 내용:**
    *   사용자 핵심 시나리오를 통합 테스트로 고정.
    *   결과물 URL/ID를 검증하는 종료 조건 테스트 추가.
*   **진행 순서:**
    1.  "최근 3개 페이지 요약 후 새 페이지 생성" 시나리오 테스트 작성.
    2.  실패 케이스(권한 부족, 429, 빈 검색결과) 테스트 작성.
    3.  텔레그램 응답 메시지 품질(완료/실패 안내) 점검.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 위 시나리오가 자동/수동 테스트에서 반복 통과.

#### 3.6.4. 관측 가능성 및 운영 가드레일 강화

*   **구현 내용:**
    *   `command_logs`/`access_logs`에 계획 단계, 도구 호출, 실패 원인을 구조적으로 기록.
    *   사용자 메시지는 친화적으로, 운영 로그는 디버깅 가능하게 이중화.
*   **진행 순서:**
    1.  요청 단위 `request_id` 전파.
    2.  단계별 로그(`plan_generated`, `tool_called`, `tool_failed`, `finalized`) 추가.
    3.  대시보드 "최근 명령 20건"에 실행 상태 및 요약 표시.
*   **예상 소요 시간:** 1일
*   **외부 서비스 설정:** 없음
*   **완료 기준:** 장애 발생 시 로그만으로 실패 단계를 역추적할 수 있음.

### 3.7. Phase 7: 실제 구현 참조용 파일 단위 실행 계획

아래 순서대로 구현하면 다음 스프린트에서 바로 개발을 시작할 수 있다.

#### 3.7.1. 서비스별 API 가이드/툴 스펙 체계 구축

*   **구현 내용:**
    *   사람용 API 가이드와 에이전트용 기계 스펙을 분리 관리.
*   **생성/수정 파일:**
    *   `docs/api_guides/notion.md`
    *   `docs/api_guides/spotify.md` (후속 서비스 추가 시)
    *   `backend/agent/tool_specs/notion.json`
    *   `backend/agent/tool_specs/spotify.json` (후속 서비스 추가 시)
*   **진행 순서:**
    1.  `docs/api_guides/notion.md`에 인증, 엔드포인트, 제약사항, 예외 케이스 정리.
    2.  `backend/agent/tool_specs/notion.json`에 tool name / input schema / required scopes 정의.
    3.  신규 서비스는 동일 패턴으로 가이드+스펙 동시 추가.
*   **완료 기준:** 에이전트가 서비스 문서가 아니라 `tool_specs`를 기준으로 호출 가능한 도구를 판단할 수 있음.

#### 3.7.2. Planner/Registry/Loop 코드 골격 구현

*   **구현 내용:**
    *   LLM 자율 실행을 위한 핵심 모듈 생성.
*   **생성/수정 파일:**
    *   `backend/agent/planner.py`
    *   `backend/agent/registry.py`
    *   `backend/agent/loop.py`
    *   `backend/agent/types.py`
*   **진행 순서:**
    1.  `planner.py`: `goal`, `constraints`, `success_criteria`, `steps` 생성.
    2.  `registry.py`: `tool_specs/*.json` 로드 및 실행 라우팅.
    3.  `loop.py`: plan→tool_call→verify 반복 루프 구현.
    4.  `types.py`: `AgentPlan`, `AgentStepResult`, `AgentFinalResult` 타입 고정.
*   **완료 기준:** 단일 요청에 대해 최소 1회 이상 동적 계획 + 도구 실행 + 결과 검증이 동작.
*   **상태:** 부분 완료 (요구사항 도출/서비스/API 선정까지 연결됨, 실행 루프는 진행 중).

#### 3.7.3. Notion Adapter 확장 (실행 가능한 Tool)

*   **구현 내용:**
    *   Notion Core Read/Write 도구를 실제 API 호출로 제공.
*   **생성/수정 파일:**
    *   `backend/integrations/notion.py`
    *   `backend/agent/tools.py` (또는 `registry.py`에서 직접 어댑터 연결)
*   **진행 순서:**
    1.  `search`, `retrieve page`, `retrieve block children` 구현.
    2.  `create page`, `append block children`, `update page` 구현.
    3.  응답 정규화(`ok`, `data`, `error`, `request_id`) 적용.
*   **완료 기준:** "최근 3개 페이지 요약 후 회의록 생성"에서 필요한 Notion API 호출이 모두 가능.

#### 3.7.4. Safety/Observability 모듈 고도화

*   **구현 내용:**
    *   실행 제한, 오류 표준화, 로그 추적성 강화.
*   **생성/수정 파일:**
    *   `backend/agent/safety.py`
    *   `backend/agent/observability.py`
    *   `backend/app/routes/telegram.py`
    *   `backend/app/routes/notion.py` (존재 시)
*   **진행 순서:**
    1.  `max_turns`, `max_tool_calls`, `timeout` 강제.
    2.  오류 코드 표준화(`AUTH_REQUIRED`, `RATE_LIMITED`, `TOOL_FAILED`).
    3.  단계 로그(`plan_generated`, `tool_called`, `tool_failed`, `finalized`) 저장.
*   **완료 기준:** CORS/인증/권한/레이트리밋 실패가 사용자 메시지와 운영 로그에서 동시에 식별 가능.

#### 3.7.5. E2E 테스트 및 회귀 방지

*   **구현 내용:**
    *   핵심 복합 시나리오를 자동화 테스트로 고정.
*   **생성/수정 파일:**
    *   `backend/tests/test_agent_notion_workflow.py`
    *   `backend/tests/test_tool_registry.py`
*   **진행 순서:**
    1.  복합 시나리오 성공 테스트.
    2.  실패 시나리오(권한 없음/빈 결과/429) 테스트.
    3.  텔레그램 응답 포맷(완료 URL 포함) 검증.
*   **완료 기준:** 배포 전 테스트에서 핵심 시나리오가 반복 통과하고 회귀가 차단됨.

### 3.8. Phase 8: 가이드 참조형 멀티서비스 에이전트 고도화

#### 3.8.1. API 가이드 표준 템플릿 도입

*   **구현 내용:**
    *   서비스별 API 가이드 문서 템플릿을 고정하여 신규 서비스 추가 비용을 최소화.
*   **생성/수정 파일:**
    *   `docs/api_guides/_template.md`
    *   `docs/api_guides/spotify.md`
    *   `docs/api_guides/notion.md` (보강)
*   **진행 순서:**
    1.  템플릿에 인증/scope/endpoint/error/rate-limit/workflow 섹션 고정.
    2.  Spotify/Notion 가이드를 템플릿 기준으로 정리.
    3.  문서 변경 시 스펙 동기화 체크리스트 추가.
*   **완료 기준:** 신규 서비스 문서를 같은 형식으로 작성 가능하고, 누락 필드 없이 검수 가능.

#### 3.8.2. Guide Retriever + Service Resolver 구현

*   **구현 내용:**
    *   사용자 요청에서 대상 서비스를 추론하고 해당 가이드를 참조 컨텍스트로 로드.
*   **생성/수정 파일:**
    *   `backend/agent/service_resolver.py`
    *   `backend/agent/guide_retriever.py`
    *   `backend/agent/planner.py`
*   **진행 순서:**
    1.  요청 텍스트/연결 상태 기반 서비스 추론 로직 구현.
    2.  추론된 서비스의 가이드 핵심 섹션만 추출.
    3.  Planner 입력 컨텍스트에 가이드 요약 포함.
*   **완료 기준:** 요청별로 서비스 추론 결과와 참조된 가이드 섹션이 로그에 남음.

#### 3.8.3. Tool Spec 컴파일/검증 파이프라인

*   **구현 내용:**
    *   `tool_specs`의 스키마 유효성 검증과 런타임 로딩 안정화.
*   **생성/수정 파일:**
    *   `backend/agent/tool_specs/schema.json`
    *   `backend/agent/registry.py`
    *   `backend/tests/test_tool_spec_schema.py`
*   **진행 순서:**
    1.  tool spec JSON Schema 정의.
    2.  서버 시작 시 전체 스펙 검증/로드.
    3.  invalid spec 발견 시 부팅 실패 또는 경고 정책 적용.
*   **완료 기준:** 잘못된 tool spec이 런타임까지 유입되지 않음.

#### 3.8.4. Spotify 실행 도구 세트 추가

*   **구현 내용:**
    *   Spotify 요청을 실제로 수행하는 최소 도구 세트 구현.
*   **생성/수정 파일:**
    *   `backend/agent/tool_specs/spotify.json`
    *   `backend/integrations/spotify.py`
    *   `backend/agent/tools.py` 또는 `backend/agent/registry.py`
*   **진행 순서:**
    1.  `spotify_get_top_tracks`
    2.  `spotify_create_playlist`
    3.  `spotify_add_tracks`
*   **완료 기준:** "출근용 잔잔한 플레이리스트 만들어줘"를 에이전트 루프가 자동 수행.

#### 3.8.5. Workflow Mining → Skill Candidate 자동화

*   **구현 내용:**
    *   자주 반복되는 성공 실행을 Skill 후보로 자동 추출.
*   **생성/수정 파일:**
    *   `backend/agent/workflow_mining.py`
    *   `backend/app/routes/skills.py` (존재 시)
    *   `frontend/app/dashboard/skills/page.tsx` (추천 Skill 노출)
*   **진행 순서:**
    1.  `command_logs`/`access_logs`에서 의도+도구시퀀스 군집화.
    2.  성공률/지연시간/재시도율 기준으로 후보 필터링.
    3.  후보를 사용자 대시보드에 추천 카드로 노출.
*   **완료 기준:** 최소 1개 이상의 추천 Skill 후보가 자동 생성/노출됨.

#### 3.8.6. 운영 수용 테스트 (서비스 추가 가능성 검증)

*   **구현 내용:**
    *   "신규 서비스 추가시 코드 영향 범위 최소화"를 검증하는 운영 테스트.
*   **진행 순서:**
    1.  가상 서비스(모의 API) 하나를 `guide + spec + adapter`로만 추가.
    2.  에이전트가 해당 서비스 요청을 인식/계획/실행하는지 검증.
    3.  실패 시 어떤 단계에서 막혔는지 로그로 추적 확인.
*   **완료 기준:** 핵심 라우터 수정 없이 신규 서비스가 동작.

## 4. 결론

본 개발 계획은 **Promethium**의 **metel** 프로토타입을 구축하기 위한 구체적인 로드맵을 제시합니다. 각 단계별로 명확한 목표와 완료 기준을 설정함으로써 효율적인 개발 진행을 도모하고, 기획서 및 OpenClaw 분석 문서에서 도출된 핵심 기술 스택과 아키텍처를 충실히 반영하였습니다. 이 계획을 통해 안정적이고 확장 가능한 프로토타입을 성공적으로 개발할 수 있을 것으로 기대합니다.

## 5. References

[1] 서비스 기획서: `service_plan.md`
[2] OpenClaw 분석 문서: `openclaw_analysis.md`
