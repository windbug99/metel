# metel 프로젝트 초기 세팅 가이드

본 문서는 AI 비서 SaaS 서비스 "metel" 프로젝트를 시작하기 위한 초기 개발 환경 설정 및 가이드를 제공합니다. 실무에서 바로 적용할 수 있는 수준으로 작성되었습니다.

## 1. GitHub 레포지토리 초기 설정

### 1.1. 모노레포 vs 멀티레포

**metel** 프로젝트는 **모노레포(Monorepo)** 구조를 추천합니다. Next.js 기반의 프론트엔드와 FastAPI 기반의 백엔드가 긴밀하게 연동되어 개발될 예정이며, 모노레포는 이러한 환경에서 다음과 같은 이점을 제공합니다.

*   **코드 공유 용이성**: 프론트엔드와 백엔드 간에 공유되는 타입 정의, 유틸리티 함수 등을 쉽게 관리하고 재사용할 수 있습니다.
*   **원자적 커밋(Atomic Commits)**: 프론트엔드와 백엔드 변경 사항을 하나의 커밋으로 묶어 관리할 수 있어, 기능 개발 시 일관성을 유지하기 용이합니다.
*   **통합된 의존성 관리**: 루트 `package.json` 등을 활용하여 프로젝트 전체의 의존성을 한곳에서 관리할 수 있습니다.
*   **단순화된 CI/CD**: 하나의 레포지토리에서 전체 프로젝트의 빌드, 테스트, 배포 파이프라인을 구성하기 용이합니다.

### 1.2. 레포지토리 구조 (디렉토리 트리)

다음은 `service_plan.md` 및 `work_plan.md`를 기반으로 제안하는 프로젝트 디렉토리 구조입니다.

```
metel/
├── frontend/                    # Next.js 프론트엔드 애플리케이션
│   ├── app/                     # Next.js App Router 구조
│   │   ├── page.tsx             # 랜딩 페이지
│   │   ├── dashboard/           # 사용자 대시보드 및 설정 페이지
│   │   │   ├── page.tsx
│   │   │   └── skills/          # Skill 관리 페이지
│   │   │       └── [skill_id]/  # 개별 Skill 상세 페이지
│   │   │           └── page.tsx
│   │   └── api/                 # Next.js API Routes (NextAuth, Webhook 등)
│   │       ├── auth/            # NextAuth OAuth 처리
│   │       └── webhook/         # 텔레그램 Webhook 수신 엔드포인트
│   ├── components/              # 재사용 가능한 UI 컴포넌트
│   ├── lib/                     # 클라이언트 측 유틸리티 및 라이브러리
│   │   └── supabase.ts          # Supabase 클라이언트 설정
│   ├── public/                  # 정적 파일
│   ├── styles/                  # 전역 스타일
│   ├── .env.local               # 로컬 환경 변수 (Next.js)
│   ├── package.json             # 프론트엔드 의존성 및 스크립트
│   ├── tsconfig.json            # TypeScript 설정
│   └── next.config.js
│
├── backend/                     # FastAPI 백엔드 애플리케이션
│   ├── main.py                  # FastAPI 앱 진입점
│   ├── bot/                     # 텔레그램/슬랙 봇 관련 로직
│   │   ├── telegram_bot.py      # 텔레그램 봇 핸들러
│   │   └── slack_bot.py         # 슬랙 봇 핸들러
│   ├── agent/                   # AI 에이전트 핵심 로직
│   │   ├── agent.py             # 에이전트 루프 구현
│   │   ├── tools.py             # LLM Tool 정의 및 실행
│   │   └── memory.py            # 대화 기록 및 메모리 관리
│   ├── skills/                  # 개별 Skill 구현 모듈
│   │   ├── scheduler.py         # 스케줄러 관리
│   │   ├── news.py              # 뉴스 모니터링 Skill 예시
│   │   ├── portfolio.py         # 포트폴리오 Skill 예시
│   │   └── spotify.py           # Spotify Skill 예시
│   ├── integrations/            # 외부 서비스 API 클라이언트
│   │   ├── spotify.py           # Spotify API 클라이언트
│   │   ├── google.py            # Google API 클라이언트
│   │   └── notion.py            # Notion API 클라이언트
│   ├── config/                  # 백엔드 설정 파일
│   ├── models/                  # Pydantic 모델 정의
│   ├── schemas/                 # 데이터베이스 스키마 정의 (SQLAlchemy 등)
│   ├── tests/                   # 백엔드 테스트 코드
│   ├── .env                     # 로컬 환경 변수 (FastAPI)
│   ├── requirements.txt         # 백엔드 Python 의존성
│   └── Dockerfile               # Dockerfile (배포용)
│
├── .github/                     # GitHub Actions CI/CD 설정
│   └── workflows/
│       └── main.yml             # CI/CD 워크플로우 정의
├── .gitignore                   # Git 추적 제외 파일 설정
├── README.md                    # 프로젝트 개요 및 시작 가이드
├── package.json                 # 모노레포 루트 의존성 및 스크립트 (선택 사항)
├── tsconfig.json                # 모노레포 루트 TypeScript 설정 (선택 사항)
└── Dockerfile                   # (선택 사항) 전체 모노레포를 위한 Dockerfile
```

### 1.3. `.gitignore` 설정

프로젝트 루트에 `.gitignore` 파일을 생성하고 다음 내용을 추가하여 불필요한 파일이나 민감한 정보가 Git에 커밋되지 않도록 합니다.

```gitignore
# Node.js
node_modules
.next/
.vercel/

# Python
__pycache__/
.venv/
venv/
*.pyc
*.log

# Environment variables
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# IDE
.vscode/
.idea/

# OS generated files
.DS_Store
Thumbs.db

# Docker
*.dockerignore

# Logs
logs/
*.log

# Misc
*.sqlite3
```

### 1.4. `README.md` 초안

프로젝트 루트에 `README.md` 파일을 생성하고 다음 내용을 초안으로 작성합니다. 프로젝트의 목적, 기술 스택, 시작 방법 등을 간략하게 설명하여 새로운 팀원이 빠르게 프로젝트를 이해하고 시작할 수 있도록 돕습니다.

```markdown
# metel: 내 모든 서비스를 아는 AI 비서

"설치 없이, 대화로" - 웹에서 한 번 설정하고, 텔레그램·슬랙으로 AI 비서와 대화하며 업무를 자동화하는 SaaS 서비스, metel.

## 🚀 프로젝트 개요

metel은 OpenClaw와 같은 자체 설치형 AI 도구의 기술적 장벽과 보안 문제를 해결하고, IFTTT/Zapier와 같은 단순 자동화 도구의 한계를 넘어 LLM 기반의 지능적인 대화형 AI 비서 서비스를 제공합니다. 사용자는 웹에서 간편하게 서비스를 연동하고 Skills를 설정한 후, 텔레그램이나 슬랙을 통해 AI 비서와 대화하며 업무를 자동화할 수 있습니다.

## ✨ 주요 기능

*   **웹 기반 설정**: 회원가입, 외부 서비스(Spotify, Google, Notion 등) OAuth 연동, Skills 선택 및 설정
*   **메신저 기반 대화**: 텔레그램/슬랙을 통한 AI 비서와의 대화, 정기 알림 수신, 추가 작업 요청
*   **LLM 기반 지능**: 멀티 소스 통합 분석, 대화형 후속 작업, 개인화된 응답, 맥락 유지
*   **강력한 보안**: API 키 중앙 관리 및 암호화, 최소 권한 원칙, 사용자 간 완전 격리

## 🛠️ 기술 스택

*   **프론트엔드**: Next.js (React, TypeScript, TailwindCSS)
*   **백엔드**: FastAPI (Python)
*   **데이터베이스**: Supabase (PostgreSQL)
*   **인증**: Supabase Auth, NextAuth
*   **캐시/세션**: Upstash (Redis)
*   **메신저 봇**: `python-telegram-bot`, `slack_bolt`
*   **LLM**: Gemini-2.5-flash-lite 또는 GPT-4o mini (사용자 선택)
*   **배포**: Vercel (프론트엔드), Railway (백엔드)

## 📦 프로젝트 구조

본 프로젝트는 모노레포 구조로 구성되어 있으며, `frontend`와 `backend` 두 개의 주요 디렉토리로 나뉩니다. 자세한 내용은 [1.2. 레포지토리 구조](#12-레포지토리-구조-디렉토리-트리)를 참조하십시오.

## 🏁 시작하기

프로젝트를 로컬에서 실행하기 위한 자세한 지침은 [로컬 개발 환경 실행 방법](#5-로컬-개발-환경-실행-방법) 섹션을 참조하십시오.

## 🤝 기여

기여 가이드는 추후 추가될 예정입니다.

## 📄 라이선스

MIT License
```

### 1.5. 브랜치 전략

**Git Flow** 또는 **GitHub Flow** 전략을 기반으로 한 브랜치 전략을 제안합니다. 프로젝트의 규모와 팀의 선호도에 따라 선택할 수 있으나, 초기 단계에서는 단순한 **GitHub Flow**를 따르되, 필요에 따라 `release` 브랜치를 추가하는 방식으로 확장하는 것을 권장합니다.

**GitHub Flow 기반 브랜치 전략:**

1.  **`main` 브랜치**: 항상 배포 가능한(deployable) 상태를 유지합니다. 모든 개발은 `main` 브랜치에서 시작됩니다.
2.  **`feature` 브랜치**: 새로운 기능 개발, 버그 수정, 개선 사항 등 모든 작업은 `main` 브랜치에서 분기된 `feature/<기능-이름>` 또는 `bugfix/<이슈-번호>` 형태의 브랜치에서 진행합니다.
    *   예시: `feature/google-oauth-integration`, `bugfix/telegram-bot-error`
3.  **Pull Request (PR)**: 작업이 완료되면 `main` 브랜치로 병합하기 위해 Pull Request를 생성합니다. PR은 코드 리뷰를 거쳐야 하며, 모든 테스트를 통과해야 합니다.
4.  **코드 리뷰**: 최소 한 명 이상의 팀원이 코드를 리뷰하고 승인해야 합니다.
5.  **병합**: 승인된 PR은 `main` 브랜치로 병합됩니다. 병합 후 `feature` 브랜치는 삭제합니다.
6.  **배포**: `main` 브랜치에 병합될 때마다 자동 배포(CI/CD)가 트리거되도록 설정합니다.

**추가 고려 사항:**

*   **`develop` 브랜치 (선택 사항)**: 만약 `main` 브랜치를 항상 프로덕션 배포용으로 유지하고, 개발 진행 상황을 통합하는 별도의 브랜치가 필요하다면 `develop` 브랜치를 사용할 수 있습니다. 이 경우 `feature` 브랜치는 `develop`에서 분기되고 `develop`으로 병합됩니다. `develop` 브랜치는 주기적으로 `main`으로 병합되어 릴리즈됩니다.
*   **커밋 메시지**: 명확하고 일관된 커밋 메시지 컨벤션을 따릅니다 (예: Conventional Commits).

## 2. 프로젝트 초기화 순서

### 2.1. Next.js 프로젝트 생성 및 기본 설정

`metel/frontend` 디렉토리에서 Next.js 프로젝트를 생성합니다.

1.  **디렉토리 이동:**
    ```bash
    mkdir metel
    cd metel
    ```
2.  **Next.js 프로젝트 생성:**
    ```bash
    npx create-next-app@latest frontend --typescript --tailwind --eslint
    # 또는 npm create next-app@latest frontend --typescript --tailwind --eslint
    ```
    *   `--typescript`: TypeScript 사용
    *   `--tailwind`: Tailwind CSS 사용
    *   `--eslint`: ESLint 설정
3.  **기본 설정 확인:**
    *   `frontend/package.json` 파일에서 `scripts` 섹션에 `dev`, `build`, `start`, `lint` 스크립트가 있는지 확인합니다.
    *   `frontend/tailwind.config.ts` 및 `frontend/postcss.config.js` 파일이 올바르게 생성되었는지 확인합니다.
4.  **개발 서버 실행 (선택 사항):**
    ```bash
    cd frontend
    npm run dev
    # 또는 yarn dev
    ```
    브라우저에서 `http://localhost:3000`에 접속하여 기본 Next.js 페이지가 뜨는지 확인합니다.

### 2.2. FastAPI 프로젝트 생성 및 기본 설정

`metel/backend` 디렉토리에서 FastAPI 프로젝트를 생성합니다.

1.  **디렉토리 이동:**
    ```bash
    cd metel
    mkdir backend
    cd backend
    ```
2.  **Python 가상 환경 생성 및 활성화:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
3.  **FastAPI 및 uvicorn 설치:**
    ```bash
    pip install fastapi uvicorn[standard]
    ```
4.  **`main.py` 파일 생성:**
    `backend/main.py` 파일을 생성하고 다음 내용을 추가합니다.
    ```python
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()

    # CORS 설정
    origins = [
        "http://localhost:3000",  # Next.js 개발 서버 주소
        # 여기에 배포된 프론트엔드 주소를 추가하세요
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def read_root():
        return {"message": "Welcome to metel backend!"}

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok"}
    ```
5.  **`requirements.txt` 생성:**
    ```bash
    pip freeze > requirements.txt
    ```
6.  **개발 서버 실행 (선택 사항):**
    ```bash
    uvicorn main:app --reload
    ```
    브라우저에서 `http://localhost:8000`에 접속하여 `{"message": "Welcome to metel backend!"}` 메시지가 뜨는지 확인합니다.

### 2.3. 환경 변수 관리 (`.env` 구조)

민감한 정보(API 키, 데이터베이스 URL 등)는 코드에 직접 포함하지 않고 환경 변수로 관리해야 합니다. `frontend`와 `backend` 각각의 디렉토리에 `.env` 파일을 생성하여 관리합니다.

**`metel/frontend/.env.local` 예시:**

```env
NEXT_PUBLIC_SUPABASE_URL="YOUR_SUPABASE_URL"
NEXT_PUBLIC_SUPABASE_ANON_KEY="YOUR_SUPABASE_ANON_KEY"
NEXT_PUBLIC_GOOGLE_CLIENT_ID="YOUR_GOOGLE_CLIENT_ID"
NEXT_PUBLIC_API_BASE_URL="http://localhost:8000" # 백엔드 개발 서버 주소
```

**`metel/backend/.env` 예시:**

```env
SUPABASE_URL="YOUR_SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY="YOUR_SUPABASE_SERVICE_ROLE_KEY"
GOOGLE_CLIENT_ID="YOUR_GOOGLE_CLIENT_ID"
GOOGLE_CLIENT_SECRET="YOUR_GOOGLE_CLIENT_SECRET"
NOTION_CLIENT_ID="YOUR_NOTION_CLIENT_ID"
NOTION_CLIENT_SECRET="YOUR_NOTION_CLIENT_SECRET"
TELEGRAM_BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
OPENAI_API_KEY="YOUR_OPENAI_API_KEY" # GPT-4o mini
GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY" # Gemini-2.5-flash-lite
```

**주의사항:**
*   `.env` 파일은 `.gitignore`에 추가하여 Git 추적에서 제외해야 합니다.
*   각 환경(개발, 스테이징, 프로덕션)에 맞는 `.env` 파일을 사용하거나, 배포 환경에서는 시스템 환경 변수를 설정해야 합니다.

### 2.4. 의존성 관리 (`package.json`, `requirements.txt`)

*   **프론트엔드 (Next.js):**
    `frontend/package.json` 파일에 모든 JavaScript/TypeScript 의존성이 관리됩니다. `npm install` 또는 `yarn install` 명령어로 의존성을 설치합니다.
    ```json
    // frontend/package.json 예시
    {
      "name": "frontend",
      "version": "0.1.0",
      "private": true,
      "scripts": {
        "dev": "next dev",
        "build": "next build",
        "start": "next start",
        "lint": "next lint"
      },
      "dependencies": {
        "next": "^14.0.4",
        "react": "^18",
        "react-dom": "^18",
        "@supabase/auth-helpers-nextjs": "^0.8.7",
        "@supabase/supabase-js": "^2.39.3"
      },
      "devDependencies": {
        "typescript": "^5",
        "@types/node": "^20",
        "@types/react": "^18",
        "@types/react-dom": "^18",
        "autoprefixer": "^10.0.1",
        "postcss": "^8",
        "tailwindcss": "^3.3.0",
        "eslint": "^8",
        "eslint-config-next": "next"
      }
    }
    ```
*   **백엔드 (FastAPI):**
    `backend/requirements.txt` 파일에 모든 Python 의존성이 관리됩니다. 가상 환경을 활성화한 후 `pip install -r requirements.txt` 명령어로 의존성을 설치합니다.
    ```txt
    # backend/requirements.txt 예시
    fastapi==0.104.1
    uvicorn[standard]==0.24.0.post1
    python-telegram-bot==20.8
    supabase-py==2.4.1
    python-dotenv==1.0.0
    # LLM 라이브러리 (선택)
    openai==1.3.7
    google-generativeai==0.3.0
    # 기타 필요한 라이브러리
    cryptography==41.0.7
    APScheduler==3.10.4
    ```

## 3. Antigravity(AI IDE)에서의 효율적인 개발 워크플로우

Antigravity(Cursor와 유사한 AI 기반 코드 에디터/IDE)를 활용하여 **metel** 프로젝트를 효율적으로 개발하기 위한 팁입니다.

### 3.1. 프로젝트 열기 및 설정

1.  **프로젝트 루트 열기**: Antigravity에서 `metel/` 디렉토리 전체를 워크스페이스로 엽니다. 이렇게 하면 IDE가 `frontend`와 `backend` 양쪽의 컨텍스트를 모두 인식할 수 있습니다.
2.  **가상 환경 설정**: 백엔드 개발을 위해 `backend/.venv` 가상 환경을 IDE에 설정합니다. Python 인터프리터를 해당 가상 환경으로 지정하여 올바른 의존성을 사용하도록 합니다.
3.  **ESLint/Prettier 설정**: `frontend` 디렉토리의 `.eslintrc.json` 및 `prettier.config.js` 설정을 IDE가 인식하도록 합니다. 코드 포맷팅 및 린팅 규칙을 자동으로 적용하여 코드 품질을 유지합니다.

### 3.2. AI 어시스턴트 활용 팁

Antigravity의 AI 어시스턴트를 최대한 활용하여 개발 생산성을 높입니다.

1.  **컨텍스트 파일 지정**: AI에게 특정 코드에 대한 질문이나 작업을 요청할 때, 관련 파일들을 명시적으로 지정(`@filename`)하여 AI가 정확한 컨텍스트를 기반으로 응답하도록 유도합니다.
    *   예시: "`@frontend/app/dashboard/page.tsx` 파일에 Notion 연동 버튼을 추가하는 코드를 작성해줘. `@frontend/lib/supabase.ts`를 참고해서 Supabase 클라이언트를 사용해야 해."
2.  **명확한 지시**: AI에게 모호한 지시 대신 구체적이고 명확한 목표를 제시합니다. 필요한 경우 예상되는 출력 형식이나 제약 조건을 함께 제공합니다.
    *   예시: "`backend/agent/agent.py`에서 `run_agent_turn` 함수를 구현해야 해. `service_plan.md`의 에이전트 루프 다이어그램을 참고하고, `tool_use`를 처리하는 로직을 포함해줘."
3.  **점진적 개발**: 복잡한 기능은 한 번에 구현하기보다 작은 단위로 나누어 AI에게 요청합니다. 각 단계별로 AI의 도움을 받아 코드를 작성하고 검토하는 과정을 반복합니다.
4.  **코드 스캐폴딩**: 새로운 파일이나 함수를 생성할 때 AI에게 초기 스캐폴딩 코드를 요청하여 시작 시간을 단축합니다.
    *   예시: "`backend/integrations/notion.py` 파일에 Notion API 클라이언트 클래스의 기본 구조를 작성해줘. `async` 함수로 구성하고, `AIOHTTP`를 사용하도록 해."
5.  **리팩토링 및 최적화**: 기존 코드의 리팩토링이나 성능 최적화가 필요할 때 AI에게 개선 방안을 문의하고 코드를 수정하도록 요청합니다.
    *   예시: "`backend/agent/memory.py`의 `load_session` 함수를 더 효율적으로 리팩토링해줘. Supabase에서 데이터를 가져올 때 쿼리 최적화를 고려해줘."

### 3.3. 추천 확장 기능/설정

Antigravity의 기본 AI 기능 외에, 개발 생산성을 더욱 높일 수 있는 확장 기능이나 설정을 고려해볼 수 있습니다.

*   **Git Graph**: Git 브랜치 및 커밋 히스토리를 시각적으로 보여주어 브랜치 전략을 이해하고 관리하는 데 도움을 줍니다.
*   **Docker**: `Dockerfile` 작성 및 Docker 이미지 빌드, 컨테이너 관리를 IDE 내에서 편리하게 수행할 수 있도록 돕습니다.
*   **REST Client**: 백엔드 API 엔드포인트를 IDE 내에서 직접 테스트할 수 있게 해줍니다. `backend/tests/api.http`와 같은 파일을 생성하여 API 요청을 관리할 수 있습니다.
*   **TODO Highlight**: 코드 내 `TODO`, `FIXME` 등의 주석을 강조하여 놓치지 않고 관리할 수 있도록 돕습니다.
*   **Path Intellisense**: 파일 경로 자동 완성을 제공하여 오타를 줄이고 개발 속도를 높입니다.

## 4. 외부 서비스 사전 준비 체크리스트

**metel** 프로젝트 개발을 시작하기 전에 필요한 외부 서비스 설정 및 API 키 발급 체크리스트입니다.

| 서비스 | 준비 항목 | 상세 내용 | 참고 자료 |
| :--- | :--- | :--- | :--- |
| **Supabase** | 프로젝트 생성 | Supabase 웹사이트에서 새 프로젝트 생성. PostgreSQL 데이터베이스 및 인증 기능 활용. | [Supabase 공식 문서](https://supabase.com/docs) |
| | API Key 및 URL 확보 | `Project URL`과 `anon public key`, `service role key`를 확보하여 `.env` 파일에 설정. | Supabase 프로젝트 설정 페이지 |
| **Google Cloud Console** | OAuth 클라이언트 ID 발급 | Google 로그인 및 Google API 연동을 위해 OAuth 2.0 클라이언트 ID (웹 애플리케이션 타입) 생성. | [Google Cloud Console](https://console.cloud.google.com/) |
| | 리디렉션 URI 설정 | `http://localhost:3000/auth/callback` (Next.js 개발용) 및 배포 환경 URI를 `승인된 리디렉션 URI`에 추가. | Google Cloud Console OAuth 동의 화면 설정 |
| **Notion** | Integration 생성 | Notion Developer 사이트에서 새 Integration 생성. `Internal Integration` 또는 `Public Integration` 선택. | [Notion Developers](https://developers.notion.com/) |
| | Internal Integration Secret 발급 | 생성된 Integration의 `Internal Integration Secret`을 확보하여 `.env` 파일에 설정. | Notion Integration 설정 페이지 |
| | 리디렉션 URI 설정 | Notion OAuth 연동을 위해 `Redirect URI` 설정 (FastAPI 백엔드 콜백 URL). | Notion Integration 설정 페이지 |
| **Telegram BotFather** | 봇 생성 및 토큰 발급 | 텔레그램 앱에서 `@BotFather`에게 `/newbot` 명령어를 보내 새 봇을 생성하고 `HTTP API Token`을 발급받아 `.env` 파일에 설정. | [Telegram BotFather](https://t.me/BotFather) |
| **LLM API** | Google AI Studio API 키 발급 | Gemini-2.5-flash-lite 사용을 위해 Google AI Studio에서 API 키 발급. | [Google AI Studio](https://aistudio.google.com/) |
| | OpenAI API 키 발급 | GPT-4o mini 사용을 위해 OpenAI 플랫폼에서 API 키 발급. | [OpenAI Platform](https://platform.openai.com/) |

## 5. 로컬 개발 환경 실행 방법

프론트엔드와 백엔드를 동시에 로컬에서 실행하고 기본 동작을 확인하는 방법입니다.

### 5.1. 사전 준비

1.  **프로젝트 클론:**
    ```bash
    git clone <YOUR_REPOSITORY_URL>
    cd metel
    ```
2.  **환경 변수 설정:**
    *   `frontend/.env.local` 파일을 생성하고 [2.3. 환경 변수 관리](#23-환경-변수-관리-env-구조) 섹션의 예시를 참고하여 필요한 환경 변수를 설정합니다.
    *   `backend/.env` 파일을 생성하고 [2.3. 환경 변수 관리](#23-환경 변수-관리-env-구조) 섹션의 예시를 참고하여 필요한 환경 변수를 설정합니다.
3.  **프론트엔드 의존성 설치:**
    ```bash
    cd frontend
    npm install # 또는 yarn install
    cd ..
    ```
4.  **백엔드 의존성 설치:**
    ```bash
    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cd ..
    ```

### 5.2. 프론트엔드/백엔드 동시 실행

두 개의 터미널을 열어 각각 프론트엔드와 백엔드 개발 서버를 실행합니다.

**터미널 1 (프론트엔드):**

```bash
cd metel/frontend
npm run dev
```

**터미널 2 (백엔드):**

```bash
cd metel/backend
source .venv/bin/activate
uvicorn main:app --reload
```

*   프론트엔드는 `http://localhost:3000`에서 실행됩니다.
*   백엔드는 `http://localhost:8000`에서 실행됩니다.

### 5.3. 기본 동작 확인 방법

1.  **프론트엔드 접속:**
    웹 브라우저에서 `http://localhost:3000`에 접속하여 Next.js 랜딩 페이지가 정상적으로 표시되는지 확인합니다.
2.  **백엔드 API 테스트:**
    웹 브라우저에서 `http://localhost:8000/api/health`에 접속하여 `{"status": "ok"}` 응답이 오는지 확인합니다. 이는 백엔드 서버가 정상적으로 동작하고 있음을 나타냅니다.
3.  **프론트엔드-백엔드 통신 테스트 (선택 사항):**
    `frontend` 코드에서 `backend`의 `/api/health` 엔드포인트를 호출하는 간단한 버튼이나 로직을 추가하여 프론트엔드와 백엔드 간의 통신이 원활한지 확인합니다.

이 가이드를 통해 **metel** 프로젝트의 초기 세팅을 성공적으로 완료하고 개발을 시작할 수 있습니다. 추가적인 기능 구현은 `work_plan.md`를 참조하여 진행하십시오.

## References

[1] 서비스 기획서: `service_plan.md`
[2] 프로토타입 개발 계획: `work_plan.md`
