# <Service> API Guide (metel)

## 1. 목적

- 이 문서는 `<service>` 연동 시 개발/운영 기준을 고정하기 위한 사람용 가이드다.
- 에이전트가 실제 호출할 도구는 `backend/agent/tool_specs/<service>.json`에서 제한한다.

## 2. 인증

- OAuth 버전:
- Access token 위치:
- Refresh token 갱신 정책:
- 필수 환경변수:

## 3. 권한(Scope/Capability)

- 최소 권한:
- 권장 권한:
- 쓰기 권한 주의사항:

## 4. 핵심 엔드포인트

### 4.1 Read

- `<name>`: `<METHOD> <PATH>`
  - 목적:
  - 주요 입력:
  - 주요 출력:
  - 비고:

### 4.2 Write

- `<name>`: `<METHOD> <PATH>`
  - 목적:
  - 주요 입력:
  - 주요 출력:
  - 비고:

## 5. 제한 사항

- Rate limit:
- Pagination:
- Idempotency:
- Payload size:

## 6. 에러 처리

- 인증 실패:
- 권한 부족:
- 레이트리밋:
- 서버 오류:
- 재시도 가능/불가 기준:

## 7. 권장 워크플로우

1. `<workflow-1>`
2. `<workflow-2>`
3. `<workflow-3>`

## 8. 테스트 체크리스트

- [ ] OAuth 토큰 발급/갱신 확인
- [ ] Read endpoint 1건 이상 성공
- [ ] Write endpoint 1건 이상 성공
- [ ] 실패 케이스(401/403/429) 확인

## 9. 참고 문서

- 공식 문서:
- 내부 문서:
