# OpenClaw 소스코드 분석 — 텔레그램 연동 & 에이전트 구현

> Legacy notice (2026-03-02):
> 본 문서는 Telegram/에이전트 구조 분석 기록입니다.
> 현재 제품 실행 경로는 MCP Gateway 기반이며 기준 문서는 `docs/overhaul-20260302.md`입니다.

> OpenClaw GitHub(https://github.com/openclaw/openclaw) 소스코드 및 공식 문서 분석 기반
> 우리 서비스 구현에 필요한 부분만 추출·정리

> 상태 주의 (2026-02-19): 본 문서는 OpenClaw 패턴 분석 문서입니다.  
> metel의 현재 구현 기준 모델/실행 경로는 `OpenAI(gpt-4o-mini) 우선 + Gemini 폴백`,  
> 그리고 `planner_llm + loop + executor + tool_specs` 조합입니다.  
> 아래 Anthropic 예시는 OpenClaw 구조 이해를 위한 참고 코드로 간주합니다.

---

## 목차

1. [OpenClaw 전체 아키텍처 요약](#1-openclaw-전체-아키텍처-요약)
2. [텔레그램 연동 방식](#2-텔레그램-연동-방식)
3. [메시지 수신 → 에이전트 도달까지 흐름](#3-메시지-수신--에이전트-도달까지-흐름)
4. [에이전트 루프 구현](#4-에이전트-루프-구현)
5. [세션·메모리 관리](#5-세션메모리-관리)
6. [우리 서비스에 적용할 핵심 패턴](#6-우리-서비스에-적용할-핵심-패턴)
7. [OpenClaw와 우리 서비스의 구현 차이](#7-openclaw와-우리-서비스의-구현-차이)

---

## 1. OpenClaw 전체 아키텍처 요약

OpenClaw의 핵심은 **Gateway** 패턴이다. 모든 채널(텔레그램, 슬랙, 디스코드 등)은 Gateway라는 단일 컨트롤 플레인에 연결되고, Gateway는 에이전트와 통신한다.

```
WhatsApp / Telegram / Slack / Discord / Signal
              │
              ▼
  ┌─────────────────────┐
  │      Gateway        │  ← 단일 컨트롤 플레인
  │  ws://127.0.0.1:    │    (모든 채널의 허브)
  │       18789         │
  └──────────┬──────────┘
             │
     ┌───────┴────────┐
     │                │
  Pi Agent          CLI / WebChat UI
  (RPC)             (부가 인터페이스)
```

**핵심 철학:**
- 에이전트 로직은 채널을 모른다
- 채널 어댑터가 각 플랫폼 메시지를 표준 Envelope 형식으로 변환
- 표준 Envelope이 에이전트에 전달됨
- **채널과 에이전트가 완전히 분리되어 있다**

우리 서비스에서 차용할 핵심 원칙이다.

---

## 2. 텔레그램 연동 방식

### 2-1. 라이브러리 선택: grammY

OpenClaw는 텔레그램 봇 구현에 **grammY** (TypeScript) 를 사용한다.
우리는 Python 스택이므로 **python-telegram-bot v20+** 을 사용하지만, 구조는 동일하다.

```
OpenClaw (TypeScript):  grammY
우리 서비스 (Python):   python-telegram-bot v20+

차이: 언어만 다르고, 패턴은 동일
```

### 2-2. 봇 초기화 미들웨어 체인

OpenClaw의 `src/telegram/bot.ts`는 다음 순서로 미들웨어를 적용한다.

```
[미들웨어 체인 순서]

1. API Throttler      ← 텔레그램 rate limit 자동 처리
2. Sequentialize      ← 같은 채팅의 메시지를 순서대로 처리 (race condition 방지)
3. Error handler      ← 모든 에러 포착 (봇 크래시 방지)
4. Update logger      ← verbose 모드에서 raw update 로깅
5. Update recorder    ← update_id 추적 (중복 방지)
6. Message handler    ← 실제 메시지 처리 진입점
```

**Sequential 처리가 핵심이다.** 같은 사용자의 메시지가 동시에 두 개 오더라도, 첫 번째가 완료된 후 두 번째가 처리된다.

```python
# python-telegram-bot에서 동일 효과 구현
# 같은 user_id의 요청을 순서대로 처리하는 Lock 사용

from asyncio import Lock
from collections import defaultdict

session_locks = defaultdict(Lock)

async def handle_message(update, context):
    user_id = str(update.effective_user.id)
    
    async with session_locks[user_id]:  # 같은 유저는 순서대로
        await process_message(update, context)
```

### 2-3. Sequential Key 설계

OpenClaw는 메시지 타입에 따라 다른 sequential key를 사용한다. (`src/telegram/bot.ts:67-110`)

```
DM 메시지:        telegram:<chatId>
그룹 메시지:      telegram:<chatId>
포럼 토픽:        telegram:<chatId>:topic:<threadId>
컨트롤 커맨드:    telegram:<chatId>:control  ← 우선순위 높음
```

우리 서비스에서 적용:
```python
def get_session_key(update) -> str:
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == "private":
        return f"user:{user.id}"              # DM
    elif chat.type in ["group", "supergroup"]:
        return f"group:{chat.id}:user:{user.id}"  # 그룹
    else:
        return f"user:{user.id}"
```

### 2-4. 텔레그램 설정 (openclaw.json 참조)

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "123:abc",
      "dmPolicy": "pairing",
      "allowFrom": [123456789],
      "groups": {
        "*": { "requireMention": true }
      }
    }
  },
  "routing": {
    "rules": [
      { "channel": "telegram", "session": "main" }
    ]
  }
}
```

**주의:** routing rules 없으면 텔레그램 메시지가 webchat 세션으로 라우팅되는 버그가 있다.
우리 서비스에서는 user_id 기반으로 직접 라우팅하므로 해당 없음.

### 2-5. Polling vs Webhook

```
Polling 모드 (기본, 우리 서비스 MVP에 적합):
  - 서버가 주기적으로 텔레그램에 새 메시지 요청
  - 공개 URL 불필요 (Railway 내부에서 동작)
  - 약간의 지연 있음 (~1초)
  - 개발/테스트에 편리

Webhook 모드 (운영 환경 추천):
  - 텔레그램이 우리 서버로 즉시 Push
  - HTTPS 공개 URL 필요
  - 즉각 응답
  - Railway 배포 시 자동 HTTPS URL 제공 → 쉽게 전환 가능
```

---

## 3. 메시지 수신 → 에이전트 도달까지 흐름

OpenClaw의 `src/telegram/bot-message.ts`와 `src/auto-reply/reply.ts`를 분석한 메시지 파이프라인이다.

```
[전체 파이프라인]

텔레그램 Update 수신
        │
        ▼
① 중복 제거 (Deduplication)
   update_id 기반 캐시 확인
        │
        ▼
② 표준 Envelope 변환 (Normalization)
   텔레그램 형식 → 내부 표준 형식
        │
        ▼
③ 보안 정책 확인 (Security Policy)
   allowFrom 확인, pairing 확인
        │
        ▼
④ 세션 라우팅 (Session Routing)
   어느 에이전트 세션으로 보낼지 결정
        │
        ▼
⑤ 에이전트 처리 (Agent Processing)
   LLM 호출, Tool Use, 응답 생성
        │
        ▼
⑥ 응답 포맷팅 (Response Formatting)
   내부 형식 → 텔레그램 메시지 형식
        │
        ▼
텔레그램 메시지 발송
```

### 3-1. Envelope 형식

OpenClaw가 내부적으로 사용하는 표준 메시지 형식이다.

```
[Telegram <ChatName> (@<username>) id:<chatId> (<relative-time>) <timestamp>]
<SenderName> (@<senderUsername>): <message text>
```

실제 예시:
```
[Telegram My Chat (@myusername) id:123456789 (2 minutes ago) 2026-02-17T09:00:00Z]
John Doe (@johndoe): 오늘 날씨 어때?
```

우리 서비스에서 LLM 시스템 프롬프트에 컨텍스트로 활용할 수 있다:
```python
def build_context_header(update) -> str:
    user = update.effective_user
    chat = update.effective_chat
    return (
        f"[Telegram {chat.title or 'DM'} "
        f"(@{user.username}) "
        f"id:{chat.id} "
        f"{datetime.now().isoformat()}]\n"
        f"{user.full_name} (@{user.username}): "
    )
```

### 3-2. 접근 제어 흐름

```
DM 메시지 수신
     │
     ▼
dmPolicy == "open"?  → 즉시 허용
     │
dmPolicy == "allowlist"? → allowFrom 목록 확인
     │
dmPolicy == "pairing"? → 페어링 코드 발송, 승인 대기
     │
dmPolicy == "disabled"? → 거부
```

우리 서비스는 **가입된 사용자만 이용** 구조이므로:
```python
async def check_access(update) -> bool:
    telegram_id = update.effective_user.id
    user = await db.get_user_by_telegram_id(telegram_id)
    
    if not user:
        await update.message.reply_text(
            "가입 후 이용 가능합니다.\n"
            "👉 https://yourapp.com/start"
        )
        return False
    return True
```

---

## 4. 에이전트 루프 구현

OpenClaw의 "You Could've Invented OpenClaw" 공식 문서와 `src/auto-reply/reply.ts` 분석 결과다.

### 4-1. 에이전트 루프 핵심 원리

```
[에이전트 루프 = 단순 반복]

while True:
    LLM에게 메시지 전송
    
    if 응답이 "end_turn":
        → 최종 텍스트 반환, 루프 종료
    
    if 응답이 "tool_use":
        → 도구 실행
        → 결과를 다시 LLM에게 전송
        → 루프 계속
```

### 4-2. OpenClaw의 실제 구현 패턴 (Python으로 번역)

OpenClaw의 `run_agent_turn` 함수를 Python으로 번역한 것이다.

```python
# agent/agent.py

import anthropic
import json
from typing import Optional

client = anthropic.Anthropic()

def serialize_content(content_blocks: list) -> list:
    """
    Anthropic API 응답의 content blocks를 JSON 직렬화 가능한 형태로 변환.
    세션 파일(JSONL)에 저장하기 위해 필요.
    
    OpenClaw 참조: src/auto-reply/reply.ts의 직렬화 로직
    """
    serialized = []
    for block in content_blocks:
        if hasattr(block, "text"):
            serialized.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            serialized.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input
            })
    return serialized


async def run_agent_turn(
    session_key: str,
    user_message: str,
    system_prompt: str,
    tools: list,
    execute_tool_fn,
    max_turns: int = 20
) -> str:
    """
    에이전트 루프 핵심 함수.
    
    OpenClaw 구조:
    - session_key: 사용자별 격리된 세션 식별자
    - 세션은 JSONL 파일로 영속 저장
    - tool_use가 end_turn이 될 때까지 반복
    
    반환: LLM의 최종 텍스트 응답
    """
    # 세션에서 대화 기록 로드
    messages = await load_session(session_key)
    
    # 컨텍스트 오버플로우 방지 (OpenClaw의 compaction)
    messages = await compact_if_needed(session_key, messages)
    
    # 사용자 메시지 추가
    user_msg = {"role": "user", "content": user_message}
    messages.append(user_msg)
    await append_to_session(session_key, user_msg)
    
    # 에이전트 루프 (최대 max_turns 회)
    for turn in range(max_turns):
        
        # LLM 호출
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        
        # 응답 직렬화 (세션 저장용)
        serialized_content = serialize_content(response.content)
        assistant_msg = {"role": "assistant", "content": serialized_content}
        messages.append(assistant_msg)
        await append_to_session(session_key, assistant_msg)
        
        # 종료 조건: 최종 응답
        if response.stop_reason == "end_turn":
            final_text = "".join(
                block.text
                for block in response.content
                if hasattr(block, "text")
            )
            return final_text
        
        # 도구 사용
        elif response.stop_reason == "tool_use":
            tool_results = []
            
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  🔧 Tool: {block.name}({json.dumps(block.input)[:80]})")
                    
                    # 실제 도구 실행
                    result = await execute_tool_fn(
                        tool_name=block.name,
                        tool_input=block.input
                    )
                    
                    print(f"     → {str(result)[:100]}")
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            
            # 도구 결과를 다음 턴에 전달
            results_msg = {"role": "user", "content": tool_results}
            messages.append(results_msg)
            await append_to_session(session_key, results_msg)
            
            # 루프 계속
        
        else:
            # 예상치 못한 stop_reason
            break
    
    return "(최대 처리 횟수 초과)"
```

### 4-3. 컨텍스트 오버플로우 방지 (Compaction)

OpenClaw의 핵심 기능 중 하나. 대화가 길어지면 오래된 부분을 요약해서 토큰 절약.

```python
# agent/memory.py

def estimate_tokens(messages: list) -> int:
    """대략적인 토큰 수 추정 (문자 수 / 4)"""
    return sum(len(json.dumps(m)) for m in messages) // 4


async def compact_if_needed(session_key: str, messages: list) -> list:
    """
    OpenClaw의 Context Compaction 로직.
    
    임계값(기본 100k 토큰) 초과 시:
    - 앞 절반을 LLM으로 요약
    - 요약 + 뒷 절반으로 교체
    
    OpenClaw 참조: src/auto-reply/reply/compact.ts
    """
    TOKEN_THRESHOLD = 80_000  # 128k 컨텍스트의 약 60%
    
    if estimate_tokens(messages) < TOKEN_THRESHOLD:
        return messages  # 오버플로우 아님, 그대로 반환
    
    split = len(messages) // 2
    old_messages = messages[:split]
    recent_messages = messages[split:]
    
    print(f"  📦 세션 압축 중... ({len(old_messages)}개 메시지 → 요약)")
    
    # 오래된 메시지를 LLM으로 요약
    summary_response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # 저렴한 모델로 요약
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": (
                "다음 대화를 간결하게 요약해주세요.\n"
                "보존해야 할 내용:\n"
                "- 사용자에 대한 핵심 정보 (이름, 선호도)\n"
                "- 완료된 주요 작업\n"
                "- 미완료 Task\n\n"
                f"{json.dumps(old_messages, ensure_ascii=False, indent=2)}"
            )
        }]
    )
    
    summary_text = summary_response.content[0].text
    
    # 요약 + 최근 메시지로 교체
    compacted = [
        {
            "role": "user",
            "content": f"[이전 대화 요약]\n{summary_text}"
        }
    ] + recent_messages
    
    # 압축된 버전으로 세션 덮어쓰기
    await save_session(session_key, compacted)
    
    return compacted
```

### 4-4. 시스템 프롬프트 설계 (SOUL.md)

OpenClaw의 가장 독특한 패턴. `SOUL.md` 파일로 에이전트의 정체성 정의.

```python
# agent/soul.py

def build_system_prompt(user_id: str, connected_services: list) -> str:
    """
    OpenClaw의 SOUL.md 패턴을 우리 서비스에 적용.
    
    사용자별로 동적으로 생성:
    - 연동된 서비스 목록
    - 사용자 맞춤 지시
    - 사용 가능한 도구 설명
    """
    services_str = ", ".join(connected_services) if connected_services else "없음"
    
    return f"""당신은 사용자의 개인 AI 비서입니다.

## 당신의 역할
사용자가 연결한 서비스들을 통해 실제 작업을 수행합니다.
단순히 정보를 제공하는 것이 아니라, 직접 행동합니다.

## 연결된 서비스
{services_str}

## 행동 원칙
- 요청을 받으면 즉시 적절한 도구를 사용하세요
- 도구 사용 전에 "무엇을 하겠다"고 설명하지 마세요. 그냥 하세요
- 작업 완료 후 결과를 친근하고 간결하게 설명하세요
- 항상 한국어로 응답하세요

## 도구 사용 기준
- Spotify 관련 요청 → create_spotify_playlist, get_spotify_recommendations
- 일정 관련 요청 → get_calendar_events, create_calendar_event
- 뉴스/정보 요청 → search_news
- Notion 관련 요청 → read_notion_page, create_notion_page
- GitHub 관련 요청 → get_github_prs, get_github_issues

연결되지 않은 서비스 요청 시, 연결 방법을 안내하세요:
"해당 기능은 [서비스명] 연동이 필요합니다. 웹에서 연결해주세요: https://yourapp.com/dashboard"
"""
```

---

## 5. 세션·메모리 관리

### 5-1. JSONL 세션 파일 (OpenClaw 핵심 패턴)

OpenClaw는 세션을 `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl` 에 저장한다.
각 줄이 하나의 메시지. Append-only로 충돌 안전.

```
장점:
- 서버 재시작해도 대화 기록 유지
- 한 줄씩 append하므로 도중 크래시해도 데이터 안전
- 사람이 읽을 수 있음

우리 서비스 적용:
- JSONL 대신 Supabase(PostgreSQL) conversation_history 테이블 사용
- 동일한 append-only 원칙 적용
```

```python
# db/session.py

async def append_to_session(session_key: str, message: dict):
    """
    OpenClaw의 append_to_session과 동일한 역할.
    JSONL 파일 대신 Supabase에 저장.
    """
    await supabase.table("conversation_history").insert({
        "session_key": session_key,
        "role": message["role"],
        "content": message["content"],  # JSON
    }).execute()


async def load_session(session_key: str, limit: int = 40) -> list:
    """최근 40개 메시지 로드 (토큰 절약)"""
    result = await supabase.table("conversation_history") \
        .select("role, content") \
        .eq("session_key", session_key) \
        .order("created_at", desc=True) \
        .limit(limit) \
        .execute()
    
    # 시간 역순이므로 뒤집기
    messages = list(reversed(result.data))
    return [{"role": m["role"], "content": m["content"]} for m in messages]
```

### 5-2. 세션 키 설계

OpenClaw의 세션 네이밍 컨벤션을 우리 서비스에 맞게 적용.

```python
# OpenClaw 패턴:
# agent:<agentId>:telegram:<accountId>:<peerId>

# 우리 서비스 적용:
SESSION_KEY_PATTERNS = {
    # 사용자 DM 대화 (실시간 대화)
    "dm":       "user:{user_id}:dm",
    
    # Skills 자동 실행 (별도 컨텍스트)
    "skill":    "user:{user_id}:skill:{skill_id}",
    
    # 크론 작업 (독립 세션)
    "cron":     "cron:{skill_type}:{user_id}",
}

def get_session_key(user_id: str, context: str = "dm", **kwargs) -> str:
    pattern = SESSION_KEY_PATTERNS.get(context, SESSION_KEY_PATTERNS["dm"])
    return pattern.format(user_id=user_id, **kwargs)
```

### 5-3. 장기 메모리 (Memory System)

OpenClaw는 파일 기반 + 벡터 검색으로 세션 간 메모리를 유지한다.
우리 서비스 MVP에서는 단순화된 버전을 사용한다.

```python
# OpenClaw 프로덕션: SQLite + 벡터 임베딩 (semantic search)
# 우리 서비스 MVP: Supabase + 키워드 검색

# 에이전트에 제공할 메모리 도구
MEMORY_TOOLS = [
    {
        "name": "save_memory",
        "description": "중요한 정보를 장기 메모리에 저장합니다. 사용자 선호도, 핵심 사실 등",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "메모리 식별자 (예: user-preferences)"},
                "content": {"type": "string", "description": "저장할 내용"}
            },
            "required": ["key", "content"]
        }
    },
    {
        "name": "recall_memory",
        "description": "장기 메모리에서 관련 정보를 검색합니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 내용"}
            },
            "required": ["query"]
        }
    }
]
```

---

## 6. 우리 서비스에 적용할 핵심 패턴

OpenClaw 분석을 바탕으로 우리 서비스에서 그대로 가져올 패턴들이다.

### 패턴 1: Sequential Processing (필수)

```python
# 같은 사용자의 메시지는 순서대로 처리
# OpenClaw: grammY의 sequentialize 미들웨어
# 우리 서비스: asyncio Lock

from asyncio import Lock
from collections import defaultdict

_locks: dict[str, Lock] = defaultdict(Lock)

async def handle_message(update, context):
    user_id = str(update.effective_user.id)
    
    async with _locks[user_id]:  # ← 이 한 줄이 핵심
        await _process_message(update, context)
```

### 패턴 2: Channel-Agent Decoupling (필수)

```python
# 채널(텔레그램)과 에이전트 로직을 분리
# → 슬랙 추가 시 agent.py 건드리지 않아도 됨

# bot/telegram_bot.py (채널 레이어)
async def handle_message(update, context):
    user_id = str(update.effective_user.id)
    message_text = update.message.text
    
    # 채널을 모르는 에이전트 함수 호출
    response = await run_agent_turn(
        session_key=f"user:{user_id}:dm",
        user_message=message_text,
        ...
    )
    
    await update.message.reply_text(response)

# agent/agent.py (에이전트 레이어)
# 텔레그램을 전혀 모름. 그냥 텍스트 받고 텍스트 반환
async def run_agent_turn(session_key, user_message, ...):
    ...
    return final_text
```

### 패턴 3: Streaming 응답 (UX 개선)

OpenClaw는 응답이 생성되는 동안 텔레그램 메시지를 계속 수정하며 스트리밍을 구현한다.

```python
# OpenClaw: streamMode = "partial" (기본값)
# 처리 방식: 임시 메시지 발송 → 응답 완성되면 수정

async def handle_with_streaming(update, context):
    # 1. 즉시 "생각 중..." 메시지 발송
    thinking_msg = await update.message.reply_text("💭")
    
    # 2. 에이전트 실행 (스트리밍)
    full_response = ""
    async for chunk in run_agent_stream(...):
        full_response += chunk
        # 일정 간격으로 메시지 업데이트
        if len(full_response) % 100 == 0:
            await thinking_msg.edit_text(full_response + "▌")
    
    # 3. 최종 응답으로 마무리
    await thinking_msg.edit_text(full_response)
```

### 패턴 4: Cron/Skills 스케줄러 (핵심 차별점)

```python
# OpenClaw의 Heartbeat = 우리의 Skills 자동 실행
# 핵심: 스케줄 실행도 동일한 에이전트 루프 사용

async def run_scheduled_skill(user_id: str, skill: dict):
    # Skills 전용 세션 (DM 대화와 분리)
    session_key = f"user:{user_id}:skill:{skill['id']}"
    
    prompt = generate_skill_prompt(skill)
    
    # 동일한 에이전트 루프 사용
    result = await run_agent_turn(
        session_key=session_key,
        user_message=prompt,
        system_prompt=build_system_prompt(user_id, ...),
        tools=get_user_tools(user_id),
        execute_tool_fn=execute_tool
    )
    
    # 텔레그램으로 결과 전송
    telegram_id = await db.get_telegram_chat_id(user_id)
    await bot.send_message(
        chat_id=telegram_id,
        text=f"📬 정기 브리핑\n\n{result}"
    )
```

### 패턴 5: 접근 제어 (보안)

```python
# OpenClaw의 dmPolicy/allowFrom을 우리 서비스에 맞게 단순화

ALLOWED_COMMANDS_WITHOUT_AUTH = ["/start", "/help"]

async def access_control_middleware(update, context, next_handler):
    """모든 메시지에 적용되는 접근 제어"""
    
    # 가입 관련 커맨드는 항상 허용
    if update.message.text in ALLOWED_COMMANDS_WITHOUT_AUTH:
        return await next_handler(update, context)
    
    telegram_id = update.effective_user.id
    user = await db.get_user_by_telegram_id(telegram_id)
    
    if not user:
        await update.message.reply_text(
            "⚠️ 먼저 웹에서 가입해주세요:\n"
            "👉 https://yourapp.com"
        )
        return
    
    # 가입된 사용자면 다음 핸들러 실행
    context.user_data["user"] = user
    await next_handler(update, context)
```

---

## 7. OpenClaw와 우리 서비스의 구현 차이

### 구조적 차이

| 항목 | OpenClaw | 우리 서비스 |
|------|----------|-------------|
| 실행 위치 | 사용자 로컬 PC | 중앙 서버 (Railway) |
| 언어 | TypeScript (Node.js) | Python (FastAPI) |
| 텔레그램 라이브러리 | grammY | python-telegram-bot v20+ |
| 세션 저장 | JSONL 파일 (로컬) | Supabase PostgreSQL |
| 사용자 수 | 1인 (자신만) | 다수 사용자 (SaaS) |
| 보안 모델 | 로컬이라 신뢰 | 멀티테넌트 격리 필수 |
| 브라우저 제어 | 가능 (Playwright) | 불가 (서버 환경) |
| API 키 관리 | 사용자 PC에 저장 | 서버 암호화 저장 (KMS) |

### 우리가 가져오는 것

```
✅ 에이전트 루프 패턴 (Tool Use 반복)
✅ Sequential Processing (동시성 제어)
✅ Channel-Agent 분리 아키텍처
✅ Session JSONL → PostgreSQL로 변환
✅ Context Compaction (세션 압축)
✅ SOUL.md → 사용자별 시스템 프롬프트
✅ Cron/Heartbeat → Skills 스케줄러
✅ Streaming 응답 (UX)
```

### 우리가 버리는 것

```
❌ 브라우저 자동화 (Playwright) → 서버에서 불가
❌ 로컬 파일 시스템 접근 → 보안상 불필요
❌ 쉘 명령 실행 → 보안상 금지
❌ 단일 사용자 구조 → 멀티테넌트로 재설계
❌ 로컬 메모리 파일 → Supabase로 대체
```

### 우리가 추가하는 것

```
✅ OAuth 토큰 관리 (Spotify, Google 등)
✅ 멀티테넌트 사용자 격리
✅ 암호화된 토큰 저장 (Envelope Encryption)
✅ 감사 로그 (모든 API 접근 기록)
✅ 웹 설정 대시보드 (Next.js)
✅ 결제/구독 시스템
```

---

## 부록: 최소 구현 코드 (Mini OpenClaw for Our Service)

OpenClaw의 "mini-openclaw.py" 패턴을 우리 서비스용으로 재작성한 핵심 코드다.

```python
#!/usr/bin/env python3
"""
our_agent.py - OpenClaw 패턴 기반의 우리 서비스 에이전트 최소 구현
"""

import anthropic
import json
from asyncio import Lock
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters

client = anthropic.Anthropic()
_locks: dict[str, Lock] = defaultdict(Lock)

# ── 도구 정의 ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_news",
        "description": "최신 뉴스를 검색하고 요약합니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string"},
                "count": {"type": "integer"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "create_spotify_playlist",
        "description": "Spotify 플레이리스트를 생성합니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "mood": {"type": "string", "enum": ["집중", "운동", "휴식", "감성"]}
            },
            "required": ["name", "mood"]
        }
    },
    {
        "name": "get_calendar_events",
        "description": "Google Calendar 일정을 가져옵니다",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer"}
            },
            "required": ["days"]
        }
    }
]

# ── 에이전트 루프 (핵심) ───────────────────────────────────

async def run_agent(user_id: str, user_message: str) -> str:
    """
    OpenClaw의 run_agent_turn 패턴.
    Tool Use가 end_turn이 될 때까지 반복.
    """
    session_key = f"user:{user_id}:dm"
    messages = await load_session(session_key)
    messages = await compact_if_needed(messages)
    
    user_msg = {"role": "user", "content": user_message}
    messages.append(user_msg)
    await append_session(session_key, user_msg)
    
    connected = await get_connected_services(user_id)
    available_tools = filter_tools(TOOLS, connected)
    
    for _ in range(20):
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=2048,
            system=build_system_prompt(user_id, connected),
            tools=available_tools,
            messages=messages
        )
        
        content = serialize_content(response.content)
        asst_msg = {"role": "assistant", "content": content}
        messages.append(asst_msg)
        await append_session(session_key, asst_msg)
        
        if response.stop_reason == "end_turn":
            return "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
        
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(user_id, block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            
            results_msg = {"role": "user", "content": tool_results}
            messages.append(results_msg)
            await append_session(session_key, results_msg)
    
    return "(처리 한도 초과)"

# ── 텔레그램 핸들러 ────────────────────────────────────────

async def handle_message(update: Update, context):
    user_id = str(update.effective_user.id)
    
    # Sequential 처리 (OpenClaw의 sequentialize)
    async with _locks[user_id]:
        
        # 접근 제어
        user = await get_user_by_telegram_id(int(user_id))
        if not user:
            await update.message.reply_text(
                "먼저 가입해주세요 👉 https://yourapp.com"
            )
            return
        
        # 처리 중 표시
        thinking = await update.message.reply_text("💭")
        
        # 에이전트 실행
        response = await run_agent(user_id, update.message.text)
        
        # 응답 전송
        await thinking.delete()
        await update.message.reply_text(response)


def main():
    app = Application.builder().token("YOUR_TOKEN").build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
```

---

*분석 기준: OpenClaw v2026.2.x, DeepWiki 문서, "You Could've Invented OpenClaw" 공식 가이드*
