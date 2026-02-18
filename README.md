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

## Supabase SQL

Supabase SQL Editor에서 `docs/sql/001_create_users_table.sql` 실행:

- `users` 프로필 테이블 생성
- RLS 및 본인 데이터 접근 정책 생성

추가로 `docs/sql/002_create_oauth_tokens_table.sql` 실행:

- `oauth_tokens` 연동 토큰 저장 테이블 생성
