# metel

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](#)
[![Frontend](https://img.shields.io/badge/frontend-Next.js-000000?logo=nextdotjs&logoColor=white)](#)
[![Database](https://img.shields.io/badge/database-Supabase-3FCF8E?logo=supabase&logoColor=white)](#)
[![Deploy Backend](https://img.shields.io/badge/deploy-Railway-7B3FE4?logo=railway&logoColor=white)](#)
[![Deploy Frontend](https://img.shields.io/badge/deploy-Vercel-000000?logo=vercel&logoColor=white)](#)
[![Status](https://img.shields.io/badge/status-prototype-orange)](#)

대화형 자율 AI 비서 프로토타입.  
웹에서 한 번 연동하고, 이후에는 Telegram에서 자연어로 작업을 요청하면 LLM 에이전트가 계획/실행/결과 전달까지 수행합니다.

## Status

- Stage: Prototype (active development)
- Frontend: Next.js (Vercel)
- Backend: FastAPI (Railway)
- Data/Auth: Supabase
- Current primary integration: Notion
- Agent mode: LLM planner + autonomous loop + guarded fallback

## Why metel

기존 자동화 도구의 한계를 동시에 해결하는 것이 목표입니다.

- 단순 자동화(If-Then) 한계: 맥락 이해/복합 작업 불가
- 설치형 에이전트 한계: 운영 부담, 보안 책임 전가
- metel 방향: SaaS 기반 + 최소 권한 + 감사 로그 + 대화형 실행

## Core Flow

```text
User (Telegram)
  -> Request
  -> LLM Planner (task requirements, target service, tool candidates)
  -> Autonomous Loop (tool call / verify / replan)
  -> Tool Runner (Notion API, ...)
  -> Result + execution trace
  -> User (Telegram)
```

## Current Capabilities

- Notion OAuth 연동 및 상태 조회
- Telegram 계정 연결/해제
- 자연어 요청 기반 Notion 작업(조회/생성/수정/아카이브 일부)
- 실행 로그 저장(`command_logs`) 및 텔레메트리(`plan_source`, `execution_mode`, `autonomous_fallback_reason`, `verification_reason`)
- 자율 루프 보호 장치
  - turn/tool/replan/timeout budget
  - verification gate
  - duplicate mutation call block
  - optional rule fallback control

## Quick Start (Local)

### 1) Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

### 3) Check

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`

## Environment Variables

필수 키는 각 `.env.example`을 기준으로 설정합니다.

- Backend: `backend/.env.example`
- Frontend: `frontend/.env.example`

LLM planner/autonomous 관련 주요 변수:

- `LLM_PLANNER_ENABLED`
- `LLM_PLANNER_PROVIDER`
- `LLM_PLANNER_MODEL`
- `LLM_PLANNER_FALLBACK_PROVIDER`
- `LLM_PLANNER_FALLBACK_MODEL`
- `LLM_AUTONOMOUS_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_ENABLED`
- `LLM_AUTONOMOUS_RULE_FALLBACK_MUTATION_ENABLED`
- `TOOL_SPECS_VALIDATE_ON_STARTUP`

## Testing

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

Tool spec 검증:

```bash
cd backend
source .venv/bin/activate
python scripts/check_tool_specs.py --json
```

## Repository Structure

```text
frontend/                  Next.js dashboard
backend/                   FastAPI + agent runtime
backend/agent/             planner / autonomous / registry / tool_runner
backend/agent/tool_specs/  service tool specs (json)
backend/tests/             unit + integration tests
docs/                      plan, architecture, setup, SQL migrations
docs/sql/                  schema migration scripts
```

## Roadmap (High Level)

- [x] Notion + Telegram 기반 end-to-end 프로토타입
- [x] LLM planner + autonomous loop 기본 동작
- [x] 실행 로그/텔레메트리/검증 사유 추적
- [ ] rule fallback 비중 축소(autonomous success rate 지속 향상)
- [ ] Notion API coverage 확대 및 멀티서비스 확장(Spotify/Google/Slack)
- [ ] workflow mining -> skill candidate 자동화
- [ ] production hardening (rate limit, retries, ops playbook)

## Docs

- `docs/work_plan.md` - 구현 우선순위/진행 상태
- `docs/service_plan.md` - 제품 기획/아키텍처
- `docs/openclaw_analysis.md` - 비교 분석
- `docs/setup_guild.md` - 환경 구성 가이드

## Inspiration (README structure)

- FastAPI: https://github.com/fastapi/fastapi
- Supabase: https://github.com/supabase/supabase
- LangChain: https://github.com/langchain-ai/langchain

---

Promethium internal prototype.
