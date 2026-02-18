# metel

Monorepo for metel prototype.

- `frontend`: Next.js app (for Vercel)
- `docs`: planning and architecture docs

## Frontend Local Setup

1. `frontend/.env.example`를 참고해 `frontend/.env.local` 생성
2. 아래 값을 입력
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_BASE_URL` (백엔드 준비 후 입력)
3. `cd frontend && npm install && npm run dev`

## Google OAuth Redirect URL

- `http://localhost:3000/auth/callback`
- `https://<your-vercel-domain>/auth/callback`

## Supabase SQL

Supabase SQL Editor에서 `docs/sql/001_create_users_table.sql` 실행:

- `users` 프로필 테이블 생성
- RLS 및 본인 데이터 접근 정책 생성
