# Claude Desktop metel 커넥터 점검 체크리스트

목표:
- Claude Desktop에 `metel` 커넥터는 연결됐지만 도구가 보이지 않거나 호출이 실패할 때 원인을 빠르게 식별한다.

관련 문서:
- `docs/claude_desktop_mcp_connection.md`
- `docs/mcp_smoke_test_checklist.md`

## 0) 증상 분류

아래 증상 중 현재 상태를 먼저 확인한다.

- 증상 A: 커넥터는 보이는데 "이 커넥터에는 사용 가능한 도구가 없습니다"
- 증상 B: 도구는 보이지만 실행 시 `invalid_api_key`, `oauth_not_connected` 등 오류
- 증상 C: 로컬 스모크는 통과했는데 Claude Desktop에서만 실패

## 1) 필수 환경값 확인 (가장 흔한 원인)

Claude Desktop `metel` 커넥터 설정의 환경값을 확인한다.

- `API_BASE_URL`
  - 예: `https://metel-production.up.railway.app`
  - `/mcp`를 붙이든 안 붙이든 브리지 코드 기준으로 일관되게 설정
- `API_KEY`
  - 반드시 `metel_` prefix 키
  - 운영 URL이면 운영에서 발급한 키 사용

체크 포인트:
- 키 앞뒤 공백/개행 없음
- 오래된/폐기된 키 아님
- 다른 환경(staging/local) 키를 운영 URL에 넣지 않음

## 2) API Key 유효성 단독 확인

Claude Desktop 이전에 API 자체를 먼저 검증한다.

```bash
export API_BASE_URL="https://metel-production.up.railway.app"
export API_KEY="metel_xxx"

curl -s -X POST "$API_BASE_URL/mcp/list_tools" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"list_tools"}'
```

정상 기준:
- `result.tools` 배열이 비어있지 않음

오류 기준:
- `error.message=invalid_api_key`면 키 문제

## 3) OAuth 연결 상태 확인

`list_tools` 결과가 빈 배열이면 OAuth 미연결 가능성이 높다.

- 대시보드에서 Notion/Linear 연결 상태 확인
- 필요 시 재연결 후 다시 `list_tools` 호출

## 4) allowed_tools 제한 확인

API Key가 특정 tool만 허용하도록 설정되면 나머지는 숨겨질 수 있다.

- `/api/api-keys`에서 `allowed_tools` 확인
- 테스트 키는 우선 `allowed_tools = null`(전체 허용)로 검증 권장

## 5) Risk Gate/Quota/정책에 의한 차단 구분

도구가 보여도 실행이 막히는 경우는 정책 차단일 수 있다.

- `policy_blocked`: 위험 작업 차단 (정상 동작)
- `quota_exceeded`: 일일 쿼터 초과
- `upstream_temporary_failure`: 외부 API 일시 장애

즉, "도구 없음" 문제와 "도구 실행 차단" 문제를 분리해서 본다.

## 6) 자동 스모크로 서버 상태 먼저 고정

```bash
cd backend
API_BASE_URL="https://metel-production.up.railway.app" \
API_KEY="metel_xxx" \
./scripts/run_mcp_smoke.sh
```

정상 기준:
- `pass=8 fail=0`

의미:
- 서버/MCP/API Key/OAuth 경로가 정상임을 먼저 확정 가능

## 7) Claude Desktop 전용 점검

먼저 브리지 단독 진단을 수행한다.

```bash
cd backend
API_BASE_URL="https://metel-production.up.railway.app" \
API_KEY="metel_xxx" \
python scripts/check_claude_bridge_tools.py
```

- `OK tools_count=N`이면 브리지/백엔드는 정상
- 이 상태에서 Desktop에 도구가 안 보이면 Desktop 설정 반영 이슈 가능성이 높다

그 다음 Desktop 순서:
- Claude Desktop 재시작 (설정 반영)
- 커넥터 `metel` 제거 후 재등록
- 같은 키/URL로 다시 연결
- 여전히 도구 0개면 `BRIDGE_DEBUG=1`로 브리지 stderr 로그 확인

## 8) 빠른 진단 매트릭스

- `invalid_api_key`: 키 값/환경 불일치
- `list_tools` 빈 배열 + API는 정상: OAuth 미연결 또는 `allowed_tools` 제한
- curl/스크립트는 정상 + Claude만 실패: Desktop 설정/재시작/브리지 환경 전달 문제

## 9) 운영 권장 절차

- 배포 후 순서 고정:
  1. `run_mcp_smoke.sh` 통과
  2. 테스트 API Key로 Claude Desktop 연결 검증
  3. 테스트 키 revoke
  4. 운영 키 재발급
