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
