# metel 프로토타입 개발 계획

## 1. 개요

본 문서는 **Promethium**의 AI 비서 SaaS 서비스인 **metel**의 핵심 플로우(웹사이트 사용자 계정 생성 및 로그인, 외부 서비스 OAuth 연동, 텔레그램 연결, 텔레그램 작업 요청 및 AI 답변)를 구현하기 위한 프로토타입 개발 계획을 상세히 기술합니다. 기획서 및 OpenClaw 분석 문서를 기반으로 기술 스택(Next.js, FastAPI, Supabase, python-telegram-bot, 사용자가 웹사이트 대시보드에서 선택 가능한 LLM API (Gemini-2.5-flash-lite, GPT-4o mini))을 활용하여 각 단계별 구현 내용, 진행 순서, 예상 소요 시간, 필요한 외부 서비스 설정, 그리고 완료 기준을 명시합니다.

## 2. 프로토타입 목표 플로우

1.  **웹사이트에서 구글 로그인으로 사용자 계정 생성**
2.  **로그인**
3.  **테스트용 Notion API 연결을 위한 OAuth 로그인**
4.  **Telegram 연결 기능**
5.  **텔레그램에서 작업 요청 및 AI 답변**

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

## 4. 결론

본 개발 계획은 **Promethium**의 **metel** 프로토타입을 구축하기 위한 구체적인 로드맵을 제시합니다. 각 단계별로 명확한 목표와 완료 기준을 설정함으로써 효율적인 개발 진행을 도모하고, 기획서 및 OpenClaw 분석 문서에서 도출된 핵심 기술 스택과 아키텍처를 충실히 반영하였습니다. 이 계획을 통해 안정적이고 확장 가능한 프로토타입을 성공적으로 개발할 수 있을 것으로 기대합니다.

## 5. References

[1] 서비스 기획서: `service_plan.md`
[2] OpenClaw 분석 문서: `openclaw_analysis.md`
