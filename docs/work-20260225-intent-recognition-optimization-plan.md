# 문장 인식률(의도/슬롯) 향상 최적화 계획 (2026-02-25)

## 1) 문서 목적
- 서비스 실패율 감소와 별도로, 사용자 문장의 의도/슬롯 인식 정확도를 지속적으로 향상하기 위한 실행 계획을 정의한다.
- 본 문서는 차후 구현 시 데이터 수집, 평가, 모델/정책 개선, 배포/롤백 기준으로 사용한다.

## 2) 목표와 비목표
### 목표
- `intent accuracy`, `skill selection accuracy`, `slot fill F1`를 지속 개선한다.
- 1턴 성공률(First-turn success rate)을 높이고, 불필요한 재질문 횟수를 줄인다.
- 실제 운영 로그를 학습 가능한 데이터셋으로 전환하는 루프를 내장한다.

### 비목표
- 초기 단계에서 온라인 자동 파인튜닝 도입
- 근거 없는 모델 교체
- 안전장치 없는 자동 정책 반영

## 3) 핵심 지표(KPI)
- `Intent Accuracy`
  - 정의: 정답 intent와 예측 intent 일치 비율
- `Skill Selection Accuracy`
  - 정의: 정답 skill_name(또는 skill_chain) 일치 비율
- `Slot Fill F1`
  - 정의: 필수 슬롯 추출 정밀도/재현율의 조화평균
- `First-turn Success Rate`
  - 정의: 추가 질문 없이 첫 시도에 실행 성공한 비율
- `Needs-input Rate`
  - 정의: `needs_input`으로 전환된 요청 비율
- `Wrong-tool Rate`
  - 정의: 실행은 되었지만 잘못된 도구/서비스가 선택된 비율

## 4) 데이터 플라이휠 설계
## 4.1 수집 대상
- 고가치 오류 케이스:
  - `validation_error`
  - `needs_input` 반복
  - `wrong_tool` / `cross_service_blocks`
  - `verification_failed`
- 성공 케이스:
  - 1턴 성공 요청(정답 샘플로 활용)

## 4.2 데이터셋 스키마(권장)
- `id`, `created_at`, `request_text`, `locale`
- `pred_intent`, `pred_skill`, `pred_slots`
- `gold_intent`, `gold_skill`, `gold_slots`
- `error_code`, `verification_reason`, `final_status`
- `source` (`prod_log`, `synthetic`, `manual_label`)

## 4.3 데이터 품질 규칙
- PII/민감정보 마스킹 후 저장
- 라벨 없는 데이터는 학습셋에 직접 투입 금지
- gold 라벨 변경은 리뷰 이력 남김

## 5) 인식 파이프라인 개선 전략
## 5.1 2단계 해석 구조
1. 문장 정규화 단계
- 오탈자/동의어/서비스 별칭/도메인 키워드 정규화
- 예: `리니어`, `linear`, `이슈트래커` -> `linear`

2. 구조화 추출 단계
- Router/Parser가 strict JSON으로 `intent + skill + slots` 출력
- 스키마 불일치 시 보정 프롬프트로 최대 N회 재시도

## 5.2 동적 Few-shot 주입
- 현재 요청과 유사한 과거 성공 예시 3~5개 주입
- 도메인별(Linear/Notion/Google) 예시 풀 분리
- 장문 예시는 요약 후 삽입해 토큰 비용 통제

## 5.3 모호성 해소 정책
- confidence 하한 미달 시 강제 실행 금지
- 1슬롯씩 확인 질문
- 후보가 있으면 선택형 질문(최대 3개) 우선

## 5.4 슬롯 자동보완 강화
- `@me`, 날짜 표현, 이슈키/페이지명 패턴 우선 해석
- 컨텍스트 기반 자동보완 후 검증 실패 시에만 질문

## 6) 학습/최적화 방식 선택 기준
## 6.1 1차(권장): 정책/프롬프트 튜닝
- 대상:
  - 라우터 프롬프트
  - 스키마 보정 프롬프트
  - fallback 조건/순서
- 장점:
  - 빠른 반영, 낮은 리스크, 즉시 롤백 가능

## 6.2 2차(조건부): 모델 미세조정(LoRA/FT)
- 착수 조건:
  - 라벨 데이터 충분(도메인별 샘플 확보)
  - 고정 평가셋에서 프롬프트 튜닝 한계 확인
  - 배포/롤백 체계 준비 완료
- 원칙:
  - Offline 평가 PASS 전에는 운영 반영 금지
  - Canary로 제한 반영

## 7) 평가 체계
## 7.1 고정 평가셋 운영
- 유형별 세트 구성:
  - 오탈자/축약어
  - 혼합 명령(조회+생성)
  - 다건 fan-out 요청
  - 모호 대상(동일 제목 다수)
- 최소 주 1회 회귀 평가 실행

## 7.2 온라인 A/B 또는 Shadow 평가
- 기준 모델/정책 vs 개선안 비교
- 핵심 비교 지표:
  - intent accuracy
  - first-turn success
  - needs_input rate
  - wrong-tool rate

## 8) 운영 루프(주간)
1. 로그 수집/정제
2. 오분류 샘플 라벨링
3. 프롬프트/정책 개선안 생성
4. 오프라인 평가(고정셋)
5. Shadow 또는 10% canary 적용
6. KPI 확인 후 승격/보류/롤백

## 9) 안전장치
- 승인 없는 자동 100% 반영 금지
- 임계치 이탈 시 즉시 롤백
  - intent accuracy 하락
  - wrong-tool rate 급증
  - first-turn success 급락
- 모델/프롬프트 버전과 평가 결과를 함께 기록

## 10) 단계별 구현 로드맵
## Phase A (1주): 측정 기반 구축
- 인식 전용 지표 집계 스크립트 추가
- 고정 평가셋 v1 구성
- DoD:
  - 지표 대시보드/리포트 자동 생성

## Phase B (1~2주): 정책/프롬프트 최적화
- 정규화 사전 + few-shot 리트리버 + 보정 프롬프트 개선
- DoD:
  - 오프라인 평가셋에서 주요 지표 개선

## Phase C (1주): 온라인 검증
- Shadow 또는 10% canary
- DoD:
  - 운영 KPI 저하 없이 first-turn success 개선

## Phase D (선택): 미세조정 PoC
- LoRA/FT 후보 모델로 제한 실험
- DoD:
  - 정책 튜닝 대비 추가 개선이 통계적으로 유의미

## 11) 구현 백로그 (우선순위)
1. `eval_intent_recognition_quality.py` 추가
- intent/skill/slot 정확도 집계

2. `build_intent_goldset.py` 추가
- 로그에서 라벨링 후보 추출

3. `run_intent_quality_gate.sh` 추가
- 기준 미달 시 FAIL 반환

4. Router 프롬프트 입력에 few-shot retrieval 연결

5. 정규화 사전(`synonyms/aliases`) 외부 파일화

## 12) Definition of Done
- 인식 품질 리포트가 주기적으로 생성된다.
- 개선안 반영 전/후를 동일 평가셋으로 비교 가능하다.
- 2주 연속으로 아래 중 2개 이상 개선:
  - intent accuracy
  - slot fill F1
  - first-turn success rate
- 운영 안정성 지표(실패율/오류율) 악화 없이 유지된다.

## 13) 다음 액션
1. 고정 평가셋 항목(도메인별 30~50문장) 확정
2. 인식 품질 리포트 스크립트 초안 구현
3. 주간 운영 루프 소유자(Backend/Product) 지정
