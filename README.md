# metel

Monorepo for metel prototype.

- `frontend`: Next.js app (for Vercel)
- `backend`: FastAPI app (Notion OAuth, integrations)
- `docs`: planning and architecture docs

## Frontend Local Setup

1. `frontend/.env.example`를 참고해 `frontend/.env.local` 생성
2. 아래 값을 입력
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_BASE_URL` (백엔드 준비 후 입력)
3. `cd frontend && npm install && npm run dev`

## Backend Local Setup

1. `backend/.env.example`를 참고해 `backend/.env` 생성
2. 아래 값을 입력
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `NOTION_CLIENT_ID`
   - `NOTION_CLIENT_SECRET`
   - `NOTION_REDIRECT_URI` (예: `http://localhost:8000/api/oauth/notion/callback`)
   - `NOTION_STATE_SECRET` (랜덤 문자열)
   - `NOTION_TOKEN_ENCRYPTION_KEY` (Fernet key)
   - `TELEGRAM_BOT_TOKEN` (BotFather 발급)
   - `TELEGRAM_LINK_SECRET` (랜덤 문자열)
   - `TELEGRAM_WEBHOOK_SECRET` (선택, 랜덤 문자열)
   - `TELEGRAM_BOT_USERNAME` (선택, 예: `my_metel_bot`)
   - `OPENAI_API_KEY` (선택, LLM planner 사용 시)
   - `LLM_PLANNER_ENABLED` (기본 `false`, LLM planner 활성화 여부)
   - `LLM_PLANNER_MODEL` (기본 `gpt-4o-mini`)
   - `FRONTEND_URL` (예: `http://localhost:3000`)
3. `cd backend && python3 -m venv .venv && source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `uvicorn main:app --reload --port 8000`

## Google OAuth Redirect URL

- `http://localhost:3000/auth/callback`
- `https://<your-vercel-domain>/auth/callback`

## Notion OAuth Redirect URL

- `http://localhost:8000/api/oauth/notion/callback`
- `https://<your-backend-domain>/api/oauth/notion/callback`

## Notion Test Endpoint

- `GET /api/oauth/notion/pages?page_size=5`
- `Authorization: Bearer <Supabase access token>` 헤더가 필요합니다.
- Notion 연동 후 사용자 페이지 목록을 반환합니다.

## Telegram Integration Setup

1. BotFather에서 봇 생성 후 `TELEGRAM_BOT_TOKEN` 확보
2. 백엔드 공개 URL 기준으로 webhook 등록
   - `POST https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook`
   - body 예시:
     - `url=https://<your-backend-domain>/api/telegram/webhook`
     - `secret_token=<TELEGRAM_WEBHOOK_SECRET>` (설정한 경우)
3. 대시보드에서 `Telegram 연결하기` 클릭
4. 열린 `t.me` 링크에서 `/start ...` 실행 후 연결 상태 확인

## LLM Planner (Optional)

기본값은 규칙 기반 planner입니다. LLM planner를 켜면 요청 분석/서비스·tool 선택을 LLM이 우선 수행하고, 실패 시 규칙 기반으로 fallback 됩니다.

필수 설정:
- `OPENAI_API_KEY` (OpenAI 사용 시)
- `LLM_PLANNER_ENABLED=true`

선택 설정:
- `LLM_PLANNER_PROVIDER` (기본 `openai`)
- `LLM_PLANNER_MODEL` (기본 `gpt-4o-mini`)
- `LLM_PLANNER_FALLBACK_PROVIDER` (예: `gemini`)
- `LLM_PLANNER_FALLBACK_MODEL` (예: `gemini-2.5-flash-lite`)
- `GOOGLE_API_KEY` (Gemini 사용 시)

## Supabase SQL

Supabase SQL Editor에서 `docs/sql/001_create_users_table.sql` 실행:

- `users` 프로필 테이블 생성
- RLS 및 본인 데이터 접근 정책 생성

추가로 `docs/sql/002_create_oauth_tokens_table.sql` 실행:

- `oauth_tokens` 연동 토큰 저장 테이블 생성

추가로 `docs/sql/003_add_telegram_columns.sql` 실행:

- `users` 테이블에 텔레그램 연결 컬럼 추가

추가로 `docs/sql/004_create_command_logs_table.sql` 실행:

- 텔레그램 명령 감사 로그 테이블 생성

## Production Env Checklist

### Vercel (frontend)

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_BASE_URL` (예: `https://metel-production.up.railway.app`)

### Railway (backend)

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `NOTION_CLIENT_ID`
- `NOTION_CLIENT_SECRET`
- `NOTION_REDIRECT_URI` (예: `https://metel-production.up.railway.app/api/oauth/notion/callback`)
- `NOTION_STATE_SECRET`
- `NOTION_TOKEN_ENCRYPTION_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_LINK_SECRET`
- `TELEGRAM_WEBHOOK_SECRET` (선택)
- `TELEGRAM_BOT_USERNAME` (선택)
- `FRONTEND_URL` (예: `https://metel-frontend.vercel.app`)
- `ALLOWED_ORIGINS` (예: `https://metel-frontend.vercel.app,http://localhost:3000`)

## Deploy Verification

1. Backend health
   - `GET https://<railway-domain>/api/health` => `{"status":"ok"}`
2. Frontend dashboard open
   - 로그인 후 Notion/Telegram 섹션이 네트워크 오류 없이 로드
3. Notion flow
   - 대시보드 `Notion 연결하기` -> 연결 성공 -> 상태 `연결됨`
4. Telegram flow
   - 대시보드 `Telegram 연결하기` -> Telegram `/start ...` -> 상태 `연결됨`
5. Telegram commands
   - `/status`
   - `/notion_pages`
   - `/notion_create 테스트 페이지`
6. Command logs
   - 대시보드 `명령 로그` 최근 20건에 성공/실패 기록 표시

## Notion Live Integration Tests

실제 Notion API를 대상으로 통합 테스트를 실행할 수 있습니다.

1. 가상환경 활성화
   - `cd backend && source .venv/bin/activate`
2. 필수 환경변수 설정
   - `RUN_NOTION_LIVE_TESTS=true`
   - `NOTION_LIVE_TOKEN=<Internal Integration Token 또는 유효한 OAuth access token>`
   - `NOTION_LIVE_PAGE_ID=<접근 가능한 page/block id>`
   - `NOTION_LIVE_DATA_SOURCE_ID=<접근 가능한 data source id>`
3. 읽기 테스트 실행
   - `python -m pytest -q tests/integration/test_notion_live.py -k "search_pages or retrieve_block_children or query_data_source"`
4. 쓰기 테스트(주의: 실제 변경 발생) 실행
   - `RUN_NOTION_LIVE_WRITE_TESTS=true`
   - `NOTION_LIVE_BASE_TITLE="Metel Live Test"` (제목 변경 테스트용)
   - `python -m pytest -q tests/integration/test_notion_live.py -k "update_page_title_roundtrip or append_block_children"`

참고:
- 테스트 토큰은 먼저 검증됩니다. `401 unauthorized`가 나오면 토큰이 잘못된 것입니다.
- Integration 토큰을 쓸 경우 테스트할 페이지/데이터소스를 해당 Integration에 연결(Connections)해야 합니다.

## Troubleshooting

- CORS 오류 (`No 'Access-Control-Allow-Origin' header`)
  - Railway `ALLOWED_ORIGINS`에 현재 Vercel 도메인 포함
  - 저장 후 Railway 재배포
- Telegram webhook 무반응
  - `getWebhookInfo` 확인
  - `url`이 backend webhook 경로인지 확인
  - `secret_token`과 `TELEGRAM_WEBHOOK_SECRET` 일치 확인
- Telegram `/start` 연결 실패
  - 대시보드에서 받은 최신 링크 사용 (만료 30분)
  - 앱에서 반응 없으면 `/start <payload>` 직접 전송
