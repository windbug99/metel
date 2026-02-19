# Apple Music API Guide (metel)

## 목적
- Apple Music 연동 작업(사용자 청취 기록/플레이리스트/곡·아티스트 조회)을 안정적으로 수행하기 위한 운영 기준 문서다.
- 에이전트는 본 문서를 참고해 계획을 수립하되, 실제 실행 가능한 도구는 `backend/agent/tool_specs/apple_music.json`으로 제한한다.

## 인증
- Apple Music API는 `Developer Token` + `Music User Token` 조합을 사용한다.
- Developer Token: 서버에서 ES256 JWT로 생성한다.
- Music User Token: 대시보드에서 MusicKit JS 권한 승인 후 발급받아 저장한다.

## 권한
- 사용자 데이터 조회는 `Music-User-Token` 헤더가 필요하다.
- 카탈로그 검색/곡·아티스트 조회는 storefront 경로(`/v1/catalog/{storefront}/...`)를 사용한다.

## 핵심 엔드포인트
- `GET /v1/me/storefront`: 사용자 storefront 조회
- `GET /v1/me/recent/played/tracks`: 최근 청취 트랙 조회
- `GET /v1/me/library/playlists`: 사용자 라이브러리 플레이리스트 조회
- `GET /v1/catalog/{storefront}/search`: 카탈로그 검색
- `GET /v1/catalog/{storefront}/songs/{song_id}`: 곡 상세 조회
- `GET /v1/catalog/{storefront}/artists/{artist_id}`: 아티스트 상세 조회

## 제한 사항
- 인증 만료/권한 이슈 발생 시 401/403이 반환될 수 있다.
- 요청량이 많은 경우 429(rate limit)가 발생할 수 있다.

## 에러 처리
- 401/403: 사용자 연동 재승인 또는 토큰 재연결 안내
- 404: storefront/id 재확인
- 429: backoff 후 재시도

## 권장 워크플로우
1. `apple_music_get_storefront`로 사용자 storefront 확인
2. 조회 목적에 맞는 도구 선택
3. 실패 시 상태 코드 기반 재시도/가이드 응답

## 참고 문서
- https://developer.apple.com/documentation/musickitjs
- https://developer.apple.com/documentation/applemusicapi/get_a_catalog_song
- https://developer.apple.com/documentation/applemusicapi/get_a_catalog_artist
- https://developer.apple.com/documentation/applemusicapi/get_a_catalog_search
- https://developer.apple.com/documentation/applemusicapi/get_a_library_playlist

