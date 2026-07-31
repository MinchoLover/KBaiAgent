# KBaiAgent 최종 기술 감사

## 1. 감사 범위와 방법

본 감사는 2026-07-29 KST에 저장소를 처음부터 다시 읽고 다음 증거를 교차 검증했다.

- Git branch·HEAD·최근 20개 commit·tracked/staged/unstaged/untracked 상태
- `app.py`, `src/`, `scripts/`, `tests/`, `dataset/`, `docs/`, 설정·환경 예시
- Stage 0~5 실행 경로, 거래·결제 위험, T4 국가환경, 상담·공식후보·보고서
- README, Architecture, AI Log, Decision Log, demo script, judge Q&A, 발표 자산
- Golden PDF·expected data·Baseline 산출물의 SHA-256
- compile, 456개 unittest, verify, regression, dependency, Streamlit AppTest
- secret pattern, `.env` 추적, Markdown 내부 링크, 공식상품 URL 도달성

기존 문서의 완료 주장을 판정 근거로 그대로 받아들이지 않았다. 코드 경로를 먼저
복원한 후 실제 테스트와 CLI 결과로 문서를 대조했다. 이번 감사에서는 OpenAI Live,
외부 유료 API, 실제 고객문서, Git push를 사용하지 않았다.

> **현재 로컬 제출 BLOCKER: 없음.** 과거 감사의 `amount_due` 의미 문제는 승인된
> “Stage 2 분석 대상 예정 결제 노출액 / 실제 현재 잔액 UNKNOWN” 계약으로
> 정리됐고, 수출 `LIQUIDITY_BUFFER_RISK`의 상담 mapping과 위험 기반 Top 3·handoff도
> 구현·회귀 검증됐다. 추적 secret 노출은 발견되지 않았다. 다만 auth·tenant·
> malware scan·보존/삭제·실제 RM 연동은 운영 전환 전 별도 blocker다.

## 2. 저장소 시작 상태

### 2.1 Git 무결성

| 항목 | 예상 | 실제 시작 | 판정 |
|---|---|---|---|
| branch | `feature/submission-benchmark-evidence` | 동일 | 일치 |
| HEAD | `6dd7608eab6bc1be6856e983e28c81e51684e620` | 동일 | 일치 |
| staged | 없음 | 없음 | 일치 |
| tracked unstaged | 없음 | 없음 | 일치 |
| 일반 untracked | 보호 파일 3개 | 보호 파일 3개 | 일치 |

시작 `git status --short`:

```text
?? PROJECT_DIRECTION.md
?? docs/FEATURE_MAPPING.md
?? docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md
```

보호 파일 시작 SHA-256:

| 파일 | SHA-256 |
|---|---|
| `PROJECT_DIRECTION.md` | `4739d0db7087cdd61e20f5c444114ba661f46972b655528bac5307bc042f8e63` |
| `docs/FEATURE_MAPPING.md` | `e0e6ae03a3d40614da8a739e6f641bcaaa0bd66a4f53808a0c71449986c33a08` |
| `docs/T4_COUNTRY_ENVIRONMENT_IMPLEMENTATION_PROMPT.md` | `40685eea8f4ee52fea69cb4229ead52edc29a76c66d34142eb93f988f571b0e9` |

### 2.2 최근 20개 commit

```text
6dd7608 docs: clarify scheduled exposure amount semantics
ec753d0 fix: recover source-grounded amount and date evidence
f7b9812 docs: finalize submission demo and judge qa
e466912 test: validate golden demo finance inputs
73e457f test: add text-layer golden trade demo
432678f docs: record country benchmark v2 evidence
9bdffd9 fix: canonicalize verified country aliases
97b1cd0 test: add guarded live benchmark evidence workflow
0a53847 feat: add versioned country environment review
6ad75ad test: add country trade document validation set
92c3adf feat: ground final report in consultation evidence
b6716e2 feat: shortlist grounded official candidates
795feaa feat: map trade risks to consultation actions
99a4dea feat: add deterministic trade settlement risk
3acdfa4 feat: simplify the financial decision UI
24e0f69 fix: verify source-grounded document evidence
091fb14 docs: align submission validation evidence
8e4de1e fix: enforce document evidence integrity
6b95edf docs: record document intake validation flow
22240ff feat: harden document intake normalization
```

감사 문서 초안 이후 상담 강화를 다음 논리 단위로 구현했다.

```text
7cf25f9 docs: add final technical and consultation audit
6580a50 fix: map export liquidity risk to consultation action
53a858a feat: prioritize grounded consultation actions
f317337 feat: add consultation handoff summary
bb00dc6 feat: preserve consultation priorities in reports
```

### 2.3 Golden과 Baseline 지문

Golden PDF SHA-256은
`5330a1a572488005f7b02cccfc7150fbaa8b38c84bb9290da1e0c6e1c3a0a91c`로
예상값과 일치했다.

Baseline은 “각 파일 SHA-256 출력 문자열을 경로순으로 다시 SHA-256”한 디렉터리
지문과 개별 root report SHA를 기록했다.

| 대상 | 시작 지문 |
|---|---|
| prediction v1 full | `5ecb950f6b3a05b69575508a52f060389d3f94cdd40291bb27602d2b271e2c36` |
| prediction v1 smoke | `3830001616ed2ae05c03c5bbbfa7acbb3aa7bd708d67bd1d7e3c2dc16872a649` |
| prediction v2 full | `a206fe474494845265c034b19d2f7a5109975de64bb1300616eca4013e0e45f9` |
| report v1 full | `97ed239027120a2a4fff98d18fe53590b57b8e99117f4c285b6eb44948338670` |
| report v1 smoke | `7966c6b8001c73d8cf310cf9b239845f85e4495f034d24bb43f8f9c2af6c3e4d` |
| report v2 full | `0d629162c305a4179ebabd8b64e7951c6c47b50429c854f9f1b07cec0b54ab03` |
| `reports/baseline_metrics.json` | `e839d8ecb8fa6203ef1204d313b839dae28358b34aec03c0e8d30b1328c451c0` |
| `reports/eval_summary.json` | `63652628e9ada3158a24764d00764ff1e97acb134c9ac645f2d5345cf6618ec4` |
| `reports/eval_report.md` | `8cc25dadd6fbd03687d1894f16d0d366e6a12edc9f3527ca69dfbeb2c0da638c` |
| `reports/failure_cases.jsonl` | `df5de1de3dd05bc137d7aab78ea9f85ff5687d6402c695f2ec0e02cfba0547af` |

전체 테스트와 보고서 작성 뒤, commit 직전 재계산에서도 위 Golden·Baseline 지문과
보호 파일 3개의 지문이 시작값과 모두 일치했다.

`scripts/run_regression.py:65-78`은 baseline update flag가 없어도 평가 report를
다시 쓰므로 원본에서 실행하지 않고 `git archive HEAD` 임시 사본에서 실행했다.

### 2.4 실행 환경·의존성

- OS: macOS 26.5.1 arm64
- Python: CPython 3.9.6, Clang 17
- pip: 26.0.1
- Git: 2.47.0
- direct dependencies: `requirements.txt:1-9`
- package conflict: 없음 (`pip check`)
- `.streamlit/config.toml`: light theme, headless, usage stats off
- canonical 환경 예시는 `env.template`; 빈 secret placeholder와 현재
  `Settings.from_env` 키를 제공
- 로컬 `.env`는 존재하지만 `.gitignore`에 의해 무시되고 추적되지 않으며, 감사
  출력에 내용이나 값은 노출하지 않음

설치된 53개 패키지는 부록 A에 기록한다. `requirements.txt`는 direct dependency를
모두 exact pin하지만 Python 자체와 transitive lockfile/hash lock은 없다.

### 2.5 저장소 구조

cache, `.venv`, `.git`, ignored live 결과를 제외한 논리 구조다.

```text
KBaiAgent/
├── app.py                         # 4,677줄 Streamlit UI
├── schemas.py / validators.py     # Stage 0 계약·검증·Stage 2 전달
├── src/
│   ├── application/               # UI-independent orchestration services
│   ├── consultation/              # risk, trade-risk mapping, packet
│   ├── country_environment/       # BR/US snapshot loader·assessment
│   ├── document_intake/           # extraction, evidence, confirmation
│   ├── domain/                    # strict Pydantic contracts
│   ├── integration_assets/        # Stage 1 fixture, country snapshot
│   ├── security/                  # upload guard, redaction
│   ├── stage1/ ... stage5/        # adapters, finance, retrieval, report
│   ├── ui/                        # state and labels
│   └── workflow/                  # state, gate, trace, orchestrator
├── scripts/                       # verify, eval, regression, generators, demo
├── tests/                         # 26 modules, 456 tests
├── dataset/                       # labels, fixtures, Golden, country set
├── reports/                       # tracked fixture baseline, ignored live runs
├── knowledge_base/                # 10 official candidate records
├── prompts/                       # Stage 0 prompt contract
├── samples/                       # Stage contracts and offline demos
├── docs/                          # architecture, logs, runbooks, reports
└── KB_AI_Codex_Autopilot_Prompt_Pack_v1/
```

추적 파일은 308개다. 추적된 Python 파일은 합계 41,252줄이며,
`app.py`가 4,677줄이라 UI 변경 회귀면이 크다.

## 3. 아키텍처 일치성

### 3.1 코드 기준 실제 경계

| 경계 | 코드 책임 | 감사 판정 |
|---|---|---|
| Stage 0 | AI 구조화 + evidence/confirmation | 작동, 예정 노출/실제 잔액 경계 명시 |
| Stage 1 | 외부 JSON/REST + spot + scenario | 계약 분리 작동 |
| Stage 2 | deterministic Decimal ledger | 작동 |
| Stage 3 | deterministic constraint grid | 작동, prototype |
| runtime Stage 4 | official retrieval | offline 작동, web 통합 결함 |
| auxiliary T4 | country environment | BR/US 제한 작동 |
| 상담 | topic merge + 결정론 Top 3 + canonical handoff | 공모전 MVP 범위 완료 |
| Stage 5 | LLM draft + deterministic critic/fallback | 작동 |
| workflow | gate, invalidation, trace | 작동 |

루트 `ARCHITECTURE.md`는 workflow·fallback을 가장 자세히 설명하지만 T4 국가환경과
공식 shortlist의 최신 경계를 반영하지 않는다. `docs/ARCHITECTURE.md`는 더 짧은
사용자 관점 문서다. 둘은 서로 모순되지는 않지만 어느 하나도 현재 전체 구조의
완전한 canonical 문서는 아니었다. 본 감사의
[`FINAL_PROJECT_REPORT.md`](FINAL_PROJECT_REPORT.md)가 최신 통합 구조를 제공한다.

### 3.2 AI와 결정론 경계

확인된 안전 경계:

- OpenAI structured output은 사용자 확인 전 Stage 2에 들어가지 않는다
  (`validators.py:1417`, `:1534-1558`).
- Stage 2·3, 거래위험, 국가환경, shortlist 제한은 LLM을 사용하지 않는다.
- Stage 5는 source bundle의 숫자를 재계산하지 않도록 지시하고 critic으로 재검사한다.
- OpenAI document/report/web request는 `store=False`다
  (`src/document_intake/openai_adapter.py:168`,
  `src/stage4/official_search.py:277`, `src/stage5/report_agent.py:142`).

한계:

- 사용자 override는 필드 단위로 안전하게 기록되지만, 운영 환경에서 누가 어떤
  권한으로 override했는지 인증·승인하는 계층은 없다.
- critic은 정규식·경로 검사이며 형식적으로 모든 자연어 함의를 증명하지 않는다.

## 4. 기능 완성도 전수검사

판정은 현재 코드와 실제 테스트 기준이다. `COMPLETE`는 공모전 MVP 명시 범위 안의
구현 완료이며 운영 상용화 완료를 뜻하지 않는다.

| 기능 | 판정 | 코드 근거 | 테스트 근거 | UI 노출 | 알려진 한계 | 제출 시 주장 가능 여부 |
|---|---|---|---|---|---|---|
| 1. 문서 업로드 | COMPLETE | `app.py:2090`, `upload_guard.py:107` | `UploadGuardTests` | 예 | PDF/PNG/JPEG만, AV 없음 | 제한 형식·크기 지원 |
| 2. 문서 유형 추출 | COMPLETE | `schemas.py`, OpenAI adapter | `SchemaTests`, Golden | 예 | 모델/fixture, UNKNOWN 가능 | 구조화 후보 추출 |
| 3. 회사 역할 | COMPLETE | `app.py:2080-2085` | trade direction tests | 예 | 사용자 선택 의존 | BUYER/SELLER 확인 |
| 4. 판매자·구매자 국가 | COMPLETE | normalization, validators | country canonicalization 8 | 예 | alias allowlist 밖 UNKNOWN | 결정론 canonicalization |
| 5. 수출입 방향 | COMPLETE | deterministic derivation | `TradeTypeDerivationTests` | 예 | 국가 충돌 시 UNKNOWN | 확인 전 계산 차단 |
| 6. 통화 | COMPLETE | schema/evidence validator | evidence tests | 예 | 복수통화 모호 시 null | 확인 통화만 계산 |
| 7. 계약 총액 | COMPLETE | `grand_total` | schema/Golden tests | 상세 | Stage 2 핵심값 아님 | 문서 명시 총액 |
| 8. 예정 결제 노출액 | COMPLETE | `amount_due` → Stage 2 | Golden/validator/critic | 예 | 실제 이행내역은 별도 UNKNOWN | 예정 노출로 제한 주장 |
| 9. 분할결제 | COMPLETE | `validators.py:1561-1583` | installment tests | 예 | Stage 1 첫 회차 target 문제 | 회차별 Stage 2 입력 |
| 10. 명시 지급일 | COMPLETE | date validator | Golden/source recovery | 예 | quote ambiguity 시 차단 | explicit due extraction |
| 11. 사건 기준 지급일 | PARTIAL | Net/event parser | date tests | 경고 | 사건 기준일 없으면 unresolved | 추측하지 않고 UNKNOWN |
| 12. evidence | PARTIAL | source evidence engine | 18 recovery + core tests | 예 | scan 독립 OCR 없음 | text-PDF source-grounded |
| 13. 사용자 confirmation | COMPLETE | confirmation record/gate | workflow tamper tests | 예 | 인증된 신원 아님 | 사람 확인 전 차단 |
| 14. explicit override | COMPLETE | override fields | explicit override tests | 예 | 운영 권한·2인 승인 없음 | 명시 override 기록 |
| 15. Stage 1 환율 시나리오 | COMPLETE | provider/scenario builder | Stage1 suites | 예 | 팀 모델 버전/가용성 외부 | JSON/REST adapter |
| 16. manual stress | COMPLETE | fixed 7 points | manual stress tests | 예 | 예측 아님 | ±3/5/10 조건 |
| 17. Stage 2 계산 | COMPLETE | `src/stage2/` | Stage2 37+ | 예 | 실제 계좌·입금이력 없음 | 결정론 계산 |
| 18. 현금 버퍼 | COMPLETE | cashflow ledger | shortfall tests | 예 | 사용자 입력값 | 목표 버퍼 부족 |
| 19. 신용한도 | COMPLETE | post-credit metric | stage2/consultation | 예 | 실제 가용한도 아님 | 사용자 입력 한도 반영 |
| 20. Stage 3 헤지안 | COMPLETE | grid optimizer | Stage3 tests | 예 | 실제 quote/자문 아님 | 계산상 후보 최대 3 |
| 21. 결제·회수 위험 | COMPLETE | trade risk rules | trade-risk suite | 예 | MVP 90일 기준 | 검토 우선도 |
| 22. 국가·무역환경 | PARTIAL | T4 snapshot/engine | T4 27 + critic | 예 | BR/US only, IMF 없음 | 3축 별도 문맥 |
| 23. 상담 행동 | COMPLETE | mapping + priority view | consultation priority suite | 예 | KB 공식 routing policy는 아님 | 결정론 검토 Top 3 |
| 24. 공식 후보 | PARTIAL | shortlist service | official candidate tests | 예 | web-result category 결함 | offline 후보 ≤3 |
| 25. 최종 보고서 | COMPLETE | deterministic/LLM report | Stage5 tests | 예 | 운영 PDF export 없음 | Markdown 통합 보고서 |
| 26. critic | COMPLETE | `critic.py` | 34+ policy tests | 상세 | regex 기반 | 정책 위반 차단 |
| 27. fallback | COMPLETE | orchestrator/report fallback | workflow/Stage5 tests | 경고 | 문서 extraction 자동대체 안 함 | API-free fallback |
| 28. audit trace | COMPLETE | `workflow/trace.py` | trace safety tests | 고급 | 영구 중앙 감사 아님 | payload-free trace |
| 29. 보안 | PARTIAL | upload/outbound/redaction | security tests | 일부 | auth/AV/rate limit 없음 | MVP 안전 기본값 |
| 30. 개인정보 보호 | PARTIAL | store false/no persistence | report/trace tests | 고지 | 동의·보존·삭제 체계 없음 | 자동 저장 안 함 |
| 31. Streamlit UI | PARTIAL | `app.py` | AppTest | 예 | 대형 단일 파일, 실사용성 연구 없음 | Top 3 로컬 데모 |
| 32. Golden demo | COMPLETE(제한) | assets/generator/tests | Golden + priority tests | 업로드 가능 | 합성 1건, 실제 고객 일반화 불가 | 제한 Golden demo |
| 33. 스캔문서 fail-closed | COMPLETE | evidence validator | scan baseline/tests | 예 | 독립 OCR 없음 | 미검증 시 계산 차단 |
| 34. Live 평가 | PARTIAL | guarded evaluator | live gate tests | CLI | 합성 8건 + Golden 1건, 일반화 불가 | 제한 합성 benchmark |
| 35. 제출 실행 방법 | PARTIAL | README/runbooks | command check/health | 문서 | 실제 slide/video 없음 | API-free 실행법 |

## 5. 코드 품질

### 5.1 긍정 판정

- domain model과 application service, workflow, UI가 논리적으로 분리되어 있다.
- Python 3.9 typing 규칙을 대체로 지키고 금융 core는 `Decimal`이다.
- 외부 Stage 1을 재구현하지 않고 계약 adapter를 유지한다.
- immutable/fingerprint 경계와 deterministic fixture가 광범위하다.
- 실패를 빈 결과·경고·fallback으로 구조화한다.

### 5.2 경고

| 항목 | 근거 | 영향 |
|---|---|---|
| 거대 `app.py` | 4,677줄 | UI 상태 무효화와 domain 호출 변경의 회귀면 증가 |
| 중복 파일 | `src/demo 2.py`, `src/stage5/* 2.py`, `docs/PROJECT_BRIEF 2.md` | canonical 파일 혼동 |
| 중복 파일 내용 불일치 | 네 쌍 모두 `cmp` 불일치 | 잘못 import/검토할 위험 |
| CI 설정 없음 | `.github/` 없음 | 로컬 456 PASS가 자동 release gate가 아님 |
| coverage/lint/type gate 없음 | unittest/compile만 | 미실행 branch 정량 확인 불가 |
| `verify.py` 범위 제한 secret scan | app/src/scripts/prompts/KB 일부 확장자 | docs·dataset 전체/high-entropy secret 보장 아님 |
| runtime Stage 4와 auxiliary T4 명칭 중복 | docs와 UI | 심사 설명 혼동 |

대규모 리팩터링은 제출 직전에 권장하지 않는다. 중복 파일 제거와 app 분리는 기능
동결 후 별도 commit·회귀로 처리해야 한다.

## 6. 금융 의미 감사

| 항목 | 판정 | 근거 |
|---|---|---|
| `Decimal` 금융 계산 | PASS | `src/stage2/metrics.py`, Stage2 tests |
| 원화 반올림 | PASS | 0.01, `ROUND_HALF_UP` |
| 수입/수출 불리 방향 | PASS | `test_import_rate_rise_is_adverse`, `test_export_rate_fall_is_adverse` |
| 보유외화·natural hedge 방향 | PASS | allocation/exposure tests |
| 버퍼·현금적자·신용 후 부족 | PASS | `test_buffer_cash_and_credit_shortfalls_are_distinct` |
| 실제 미수와 예정 노출 구분 | PASS | 제품 계약·UI·packet·critic에서 예정 노출/UNKNOWN 분리 |
| 분할합계 | PASS | validator·Golden 합계 |
| 분할결제 Stage 1 target | WARNING | 첫 회차 target, Golden test는 잔금일 단일노출 |
| q90 의미 | PASS | UI/report/critic tests |
| 방향 score 확률 오해 | PASS | `calibrated_probability=false` 정책 |
| fixed stress와 예측 구분 | PASS | scenario kind·report critic |
| 국가 snapshot을 공식 등급으로 오해 | PASS | disclaimer·critic |
| 국가 신호의 Stage2/3 변경 | PASS | country integration invariance |
| 상품 추천과 상담 후보 구분 | PASS | eligibility/approval contract |
| 승인·보험인수 단정 | PASS | model/critic/문구 |

### RESOLVED F-01 — 예정 노출과 실제 잔액 경계

승인된 현재 제품 계약은 다음과 같다
(`README.md:58-66`, `docs/DECISIONS.md:444-465`).

- `amount_due`: Stage 2 분석 대상 계약상 예정 결제 노출액
- Golden: 이행 여부가 확인되지 않은 USD 20,000 + USD 80,000 = USD 100,000
- 실제 현재 미수·미지급잔액: 입금·지급 이력을 반영해야 하는 별도 개념,
  Golden에서는 `UNKNOWN`

이번 상담 작업은 extraction prompt/schema·validator·Stage 2를 변경하지 않았다.
대신 선지급 실제 이행 상태를 별도 `InstallmentPaymentStatus`로 보존하고 packet의
첫 missing item으로 표시한다 (`src/domain/consultation_models.py:105-119`,
`src/consultation/prioritization.py:690-729`). Stage 5 critic은 예정 노출을 실제
현재 잔액으로 표현한 보고서를 거부한다
(`tests/test_stage5_decision_report.py::test_critic_rejects_scheduled_exposure_as_actual_receivable`).

## 7. AI 안전성

| 점검 | 판정 | 근거·한계 |
|---|---|---|
| structured output | PASS | Pydantic `responses.parse` |
| retry 상한 | PASS | document ≤3 attempts, SDK retry 0 |
| timeout | PASS | OpenAI 60초, Stage1 10초 default |
| API 실패 격리 | PASS | document 오류/market fallback/report fallback |
| raw response 저장 금지 | PASS | `store=False`, live artifact에도 raw response 없음 |
| hallucination 방지 | PASS | evidence/value gate, critic |
| abstention | PASS | UNKNOWN/null/OCR_REQUIRED |
| 사용자 확인 전 계산 차단 | PASS | gate + binding tests |
| source-grounded recovery | PASS(제한) | text-PDF unique candidate only |
| scan OCR 검증 | WARNING | 독립 verifier 없음, 대신 fail-closed |
| report 숫자 재계산 | PASS | source path critic |
| web search grounding | FAIL(통합) | official result category가 shortlist와 불일치 |
| Live 일반화 | WARNING | 합성 8건 + recovery 이후 Golden 1건, 실제 고객 일반화 불가 |

## 8. 보안·안전 감사

`PASS`는 현재 저장소 구현에 대한 판정이며 상용 운영 인증을 뜻하지 않는다.

| 항목 | 판정 | 근거 또는 위험 |
|---|---|---|
| API key 추적 노출 | PASS | 고신뢰 credential pattern 0, generic assignment 수동의심 0, `.env` ignored |
| `.env` 추적 | PASS | `git ls-files .env` 없음, `.gitignore:1` |
| settings repr secret | PASS | `src/config.py:59`, `:89-91` `repr=False` |
| raw model response 저장 | PASS | `store=False`, raw response artifact 없음 |
| 전체 prompt 자동 저장 | PASS | 저장 코드 없음; 요청 시 모델에는 전송됨 |
| 문서 bytes 자동 dataset/log 저장 | PASS | 메모리/요청 사용, trace 저장 안 함 |
| 고객문서 영구보존 통제 | WARNING | 앱 DB는 없지만 배포 정책·세션 삭제 SLA 없음 |
| path traversal | PASS | `Path(filename).name` + sanitize |
| 확장자/MIME/signature | PASS | 세 값 일치 검사 |
| 악성 PDF/이미지 | WARNING | strict parse·limit은 있으나 AV/sandbox 없음 |
| 파일 크기 제한 | PASS | 15MB default |
| PDF 페이지 제한 | PASS | 20쪽 default |
| 이미지 decompression bomb | PASS(제한) | 40M pixel + Pillow verify |
| timeout | PASS | OpenAI/Stage1 설정 |
| retry 폭주 | PASS | bounded document/Stage1/report |
| Stage1 SSRF | PASS | HTTPS, DNS/IP, host allowlist, no redirect |
| 공식 URL allowlist | PASS | exact/subdomain host, lookalike tests |
| 로그 개인정보 | PASS(로컬) | payload-free trace; 중앙 log 자체 없음 |
| Markdown injection | WARNING | `unsafe_allow_html`은 주로 hardcoded/escape; 완전 sanitizer 없음 |
| Streamlit unsafe HTML | WARNING | 다수 사용, 동적 값 escape 확인했으나 전체 taint proof 없음 |
| 사용자 confirmation 우회 | PASS | binding/tamper tests |
| evidence override 오용 | WARNING | 명시 기록되나 인증·2인 승인 없음 |
| 금융 core float | PASS | 금액·환율·비율은 Decimal; timeout/UI 비금융 float만 존재 |
| Decimal 변환 | PASS | finite/scientific notation 검증 |
| date/timezone | PASS | date 계산, audit datetime timezone 강제 |
| 실제 잔액/예정 노출 혼동 | PASS | UI·packet·critic에서 예정 노출/UNKNOWN 분리 |
| q90 확률 오해 | PASS | instructions·critic·tests |
| 국가 snapshot 공식등급 오해 | PASS | separate axes·critic |
| 상품 추천/후보 혼동 | PASS | candidate/disclaimer/eligibility unknown |
| 대출·보험·보증 승인 단정 | PASS | critic + official candidate contract |
| 인증·tenant·권한 | FAIL(운영) | 미구현, 로컬 공모전 범위 |
| rate limit·DLP·중앙 audit | FAIL(운영) | 미구현 |

현재 로컬 제출 blocker는 없다. 인증·tenant·AV·보존/삭제와 실제 RM 연동은
공모전 로컬 MVP의 운영 전환 blocker이며 제출 데모 자체의 코드 오류와는 구분한다.

## 9. 상담 심층 기술 판정

### RESOLVED C-01 — 수출 유동성 상담

`LIQUIDITY_BUFFER_RISK`는 수출에서 `EXPORT_LIQUIDITY_REVIEW`를 만든다
(`src/consultation/response_mapping.py:548-581`). 문구는 버퍼 부족만으로
지급불능·대출 필요성·필요 대출금·승인 가능성을 판단하지 않는다. Golden은
ending cash 8,000,000원, target 10,000,000원, buffer shortfall 2,000,000원,
cash deficit 0원, payment/post-credit deficit 0원을 함께 표시한다
(`src/consultation/prioritization.py:513-575`).

### RESOLVED C-02/C-03 — priority·숫자·handoff

- `ConsultationPriorityView`가 rank, reason, structured numeric rationale,
  missing information, expected decision, next action, 후보와 audit rule을 가진다
  (`src/domain/consultation_models.py:121-158`).
- `CATEGORY_PRIORITY_RULES`는 가중합·LLM 없이 명시적 사전식 순서를 만든다
  (`src/consultation/prioritization.py:31-137`, `:761-935`).
- Golden 순서는 회수 보호 → 환율 → 유동성이다.
- USD 20,000 선지급 실제 입금 여부와 입금일이 첫 missing item이고, 사용자
  확인 시 그 항목만 제거된다.
- UI, Markdown과 Stage 5는 동일 `ConsultationPacket` JSON을 사용한다.
- 실제 예약·RM 전송·신청·심사 연동은 없다.

상담 전체 점수는 **86/100**이며 세부는
`docs/CONSULTATION_STRENGTHENING_REPORT.md`에 있다.

## 10. UI·UX 감사

### 작동 확인

- 네 탭이 실제 렌더링된다 (`app.py:2031-2044`).
- API key를 모두 빈 값으로 둔 실제 Streamlit process에서
  `/_stcore/health`가 `ok`였다.
- AppTest가 수입·수출 demo, evidence 수정 무효화, 국가 정보부족을 실행한다
  (`tests/test_ui_evidence_state.py`).
- 상담 topic, 공식 후보, 준비 조건, Markdown/JSON 다운로드가 노출된다
  (`app.py:3894-3937`, `:4400-4483`, `:4505-4556`).

### 약점

- Top 3 카드와 첫 행동은 상단에 있으나 실제 사용자성 연구는 하지 않았다.
- 실제 KB 연락·예약·RM 전송 버튼은 없고 Markdown 다운로드까지만 제공한다.
- 입금상태 확인은 로컬 session이며 계좌·수납 시스템과 연결되지 않는다.
- `app.py`가 크고 session state invalidation이 여러 위치에 분산되어 변경 위험이 높다.

## 11. 문서·로그·발표자료 정합성

| 대상 | 판정 | 실제 확인 |
|---|---|---|
| README | PASS(현재) | 456 tests, 예정 노출/UNKNOWN, Top 3와 handoff 경계 반영 |
| root Architecture | PARTIAL | workflow 상세, 최신 T4/consultation priority gap 누락 |
| docs Architecture | PARTIAL | 짧고 유용하나 전체 최신 흐름 아님 |
| AI Log | PASS(이력) | 날짜별 당시 test count·변경 이유를 기록; 현재 count로 읽으면 안 됨 |
| Decision Log | PASS(현재) | 예정 노출 계약과 priority/packet source-of-truth 결정 기록 |
| Validation Report | PASS(기록) | 456 count, 과거/현재 Golden Live와 상담 검증 구분 |
| `env.template` | PASS | README가 가리키는 canonical 설정 예시이며 현재 `Settings.from_env`와 정렬 |
| prompt pack `.env.example` | PARTIAL(역사 자산) | `DELETE_TEMP_FILES`, `LOG_LEVEL`, `STAGE1_API_KEY`, `CACHE_TTL_SECONDS`는 현재 앱이 읽지 않음 |
| Submission Readiness | PASS(감사 중 정정) | Golden 상태는 정확; preflight 재생성 명령을 SHA 확인으로 교체 |
| Demo Script | PASS(감사 중 정정) | Golden 국가환경을 실제 `STANDARD_REVIEW`, 거래위험을 `ELEVATED_REVIEW`로 분리 |
| Judge Q&A | PASS(제한 고지) | 승인·등급·실고객 검증 한계를 방어 |
| 실제 발표자료 | NOT IMPLEMENTED | `.pptx`, `.ppt`, `.key`, slide deck 없음 |
| Markdown pitch source | DOCUMENTATION ONLY | prompt pack과 demo/Q&A만 존재 |

`docs/AI_LOG.md`의 219·240·274·383·394 같은 테스트 수는 각 변경 당시의 이력이라
현재 456과 모순이 아니다. 반면 `docs/repositioning/FINAL_REPORT.md`의 274개와
`docs/REPOSITORY_AUDIT.md`의 184개는 과거 snapshot이므로 제출시 최신 결과로 인용하면
안 된다. 현재 canonical 검증 문서는 `docs/VALIDATION_REPORT.md`와 본 감사다.

## 12. 테스트·정적 검증 결과

| 순서 | 명령/검사 | 결과 | 비고 |
|---:|---|---|---|
| 1 | `compileall` | PASS | app/src/scripts/tests |
| 2 | 전체 unittest | 456/456 PASS | 상담 구현 후 재실행 |
| 3 | `scripts/verify.py` | PASS | 내부 456/456 |
| 4 | `pip check` | 최종 gate에서 재확인 | dependency write 없음 |
| 5 | regression | PASS | immutable temp Git archive |
| 6 | Golden 집중 | 14/14 PASS | API-free |
| 7 | evidence+canonicalization | 26/26 PASS | API-free |
| 8 | Stage2·hedge·Stage4·Stage5 | 59/59 PASS | API-free |
| 9 | consultation·priority·Stage 5·UI 집중 | 67/67 PASS | API-free |
| 10 | T4 | 27/27 PASS | API-free |
| 11 | report/critic·UI | 38/38 PASS | API-free |
| 12 | import/export demo | PASS/PASS | mock Stage1, fixture spot |
| 13 | Streamlit health | `ok` | sandbox bind 실패 후 승인 local 실행 |
| 14 | `git diff --check` | PASS | 문서 작성 전 기준 |
| 15 | local Markdown links | 30 checked, 0 missing | 최종 보고서 포함 |
| 16 | secret pattern | 고신뢰 credential 0 | tracked+의도 문서; generic assignment 33건은 empty/test/source literal, 수동의심 0 |
| 17 | official product URLs | 10/10 HTTP 200 | response body 미저장 |

Streamlit 첫 시작은 sandbox port bind 제한으로 `PermissionError`가 났다. 동일 명령을
로컬 bind 승인 후 실행해 health를 확인하고 즉시 종료했다. 애플리케이션 결함이
아니다.

### 남은 미검증 경로

1. `OFFICIAL_WEB_SEARCH` 결과 → `shortlist_official_candidates` end-to-end
2. 실제 KB 예약·RM·고객 식별·심사 integration
3. 실제 고객문서·운영분포 benchmark와 독립 OCR 품질
4. production auth/tenant/malware/retention
5. 기업 담당자·RM 대상 usability test

## 13. 발견 문제 목록

| ID | 심각도 | 문제 | 파일·라인 | 재현 | 영향 | 권장 조치 |
|---|---|---|---|---|---|---|
| F-01 | RESOLVED | 예정 노출/실제 잔액 경계 | README, Decision 29, packet/critic | Golden packet | USD 100k/80k/UNKNOWN 구분 | 현재 계약 유지 |
| C-01 | RESOLVED | 수출 liquidity 상담 누락 | mapping `:548-581` | export mapping test | 2m/0/0 행동 결속 | 완료 |
| S4-01 | HIGH/P1 | web 후보 category 통합 불가 | official search `:292-323`, service `:154-164` | web candidate 1 → shortlist 0 | 최신검색 선택 시 빈 후보 | source category 보존/분류 adapter + integration test |
| G-01 | HIGH/P1 | Golden split target/test 불일치 | app `:2884`, orchestrator `:411`, Golden test `:300` | 현행 target 7/29 vs test 8/20 | horizon·일정 설명 불충분 | split end-to-end fixture와 target policy 결정 |
| C-02 | RESOLVED | 실제 결제이력 UNKNOWN | prioritization `:690-729` | Golden missing test | 준비사항 표시 | 완료 |
| C-03 | RESOLVED | rank·숫자·expected decision | priority model `:121-158` | priority/UI/Stage5 tests | 첫 행동 표시 | 완료 |
| D-01 | MEDIUM/RESOLVED | Demo T4 priority 오기 | `docs/DEMO_SCRIPT_KO.md:98` | Golden 22일 rule 실행 | 발표 수치 오류 | 감사 중 국가 `STANDARD_REVIEW`·거래 `ELEVATED_REVIEW`로 정정 |
| D-02 | MEDIUM/RESOLVED | Golden preflight가 재생성 지시 | README Golden 절, demo `:19`, readiness `:148` | 명령 확인 | 불변 PDF 오염 위험 | 감사 중 SHA check로 교체 |
| D-03 | LOW | prompt pack 환경 예시가 현재 설정과 어긋남 | prompt pack `.env.example:20-30`, `src/config.py:96-205` | 키 비교 | 운영자가 무효 변수를 설정할 수 있음 | `env.template`만 canonical로 명시하거나 역사 예시 동기화 |
| R-01 | MEDIUM | 다른 내용의 ` 2` 중복 파일 | 네 파일 | `cmp` exit 1 | 유지보수 혼동 | freeze 후 삭제 commit |
| U-01 | MEDIUM | 실제 slide deck 없음 | repo file scan | ppt/key 0 | 발표 완성도 저하 | 3분 deck+backup video |
| SEC-01 | MEDIUM/운영 | AV/auth/tenant/retention 없음 | architecture/limit docs | code scan | 실제 고객 운영 불가 | 운영 전 별도 보안 architecture |
| QA-01 | LOW | CI·coverage·lint 없음 | repo root | `.github` 없음 | 자동 gate 부족 | 제출 후 CI 추가 |

## 14. 프로젝트 냉정 평가

### 14.1 100점 평가

| 평가 영역 | 배점 | 현재 | 감점 근거 |
|---|---:|---:|---|
| 문제 정의와 고객가치 | 10 | 9 | 실제 상담 outcome은 회수하지 않음 |
| KB AI Challenge 주제 적합성 | 10 | 9 | KB 내부 workflow·예약 미연동 |
| 전체 아키텍처 | 10 | 8 | Stage4/T4 명칭, monolithic UI |
| AI 활용의 필요성과 적절성 | 10 | 8 | 제한 합성 성능, web 통합 결함 |
| 금융 계산과 도메인 정합성 | 10 | 8 | 실제 quote·계좌·입금연동 없음 |
| evidence·안전성 | 10 | 9 | scan OCR verifier 없음 |
| 테스트와 재현성 | 10 | 10 | 456 PASS·verify·regression, CI는 없음 |
| 상담·KB 업무 연결 | 15 | 12 | Top 3/handoff, 실제 RM 연동 없음 |
| UI·데모 전달력 | 10 | 7 | 카드 구현, usability/deck 증거 부족 |
| 제출 완성도 | 5 | 4 | 문서·대본 완료, 최종 영상/실제 deck 확인 필요 |
| **합계** | **100** | **84** |  |

### 14.2 수상 경쟁력

- 상담 P0/P1 구현 전 감사 기준: **74/100, 통과 가능 수준**
- 현재 코드 기준: **84/100**
- 과장 없는 현재 수상 경쟁력: **본상 경쟁력 있음**

“대상 경쟁력 있음”으로 단정하지 않는 이유는 실제 고객 검증, KB 예약·RM·심사
integration, 실시간 quote·eligibility와 최종 사용자성 증거가 없기 때문이다.
대상 가능성은 데모에서 handoff의 실무가치를 얼마나 설득하는지에 달렸으며
보장할 수 없다.

### 14.3 KB 심사기준·윤리 관점

KB국민은행의 2026-07-10 공식 보도자료에서 제8회 대회의 주제가 AI를 활용한 금융
서비스 구현이고 대상 1팀을 포함해 5팀을 시상한다는 점은 확인했다. 그러나 저장소와
공개 공식 페이지에서 정확한 최신 심사항목별 배점표는 확인하지 못했으므로
**UNKNOWN**이다. 본 평가는 사용자가 제시한 100점 기준을 canonical rubric으로
사용했다. 공식 대회 사실:
[KB국민은행 제8회 Future Finance AI Challenge 보도자료](https://omoney.kbstar.com/quics?articleId=145331&bbsMode=view&boardId=647&page=C017648).

공식 KB금융그룹 AI 윤리기준의 공정·포용, 참여·협력, 데이터·개인정보, 투명성,
통제가능성, 안전·책임 원칙과 대조하면 evidence gate·사람 확인·출처·fallback은
방향이 맞다. 다만 운영 개인정보 통제, 사용자 권한, 실제 상담 책임분계는 아직
구현되지 않았다. 공식 기준:
[KB금융그룹 AI 윤리기준](https://www.kbfg.com/kor/about/ethics/standard/ai-rule.htm).

## 15. 심사위원 관점 약점

1. “USD 100,000 예정 노출과 USD 80,000 잔금·실제 미수는 어떻게 다른가?”
2. “상담 1·2·3순위는 AI 추천인가, KB 공식 routing policy인가?”
3. “버퍼 2,000,000원 부족을 왜 대출 필요로 보지 않는가?”
4. “공식 web search를 켜면 왜 후보가 없어질 수 있나?”
5. “Golden Live 최초 실패와 recovery 이후 성공의 범위는 무엇인가?”
6. “두 회차인데 환율 target과 회차별 현금 timing은 어떻게 설명하는가?”
7. “KB가 이 packet을 실제로 받는가, 단순 Markdown 다운로드인가?”
8. “실제 고객문서와 스캔문서 정확도는 측정했나?”
9. “국가 raw 4가 신용등급인가?”
10. “헤지 후보와 공식 후보를 실제 추천·승인으로 오해하지 않게 어떻게 막는가?”

## 16. 경쟁작 대비 부족한 점

- 은행 상담 예약·RM CRM·고객 ID·내부 상품 API가 없어 business closure가 약하다.
- 실제 고객 문서·운영분포 benchmark가 없어 모델 성능 근거가 좁다.
- 상담 Top 3는 구현됐지만 실제 KB routing policy와 사용자성 연구가 없다.
- 실시간 상품조건·quote·적격성을 사용하지 않아 실제 실행성은 낮다.
- deck·영상·offline screenshot 등 발표 deliverable이 코드 수준만큼 준비되지 않았다.
- CI/CD, auth, tenant, retention, observability가 없어 production story가 약하다.

반대로 경쟁작과 차별화할 수 있는 사실은 “미검증 AI 값을 계산에 넘기지 않는 gate”,
“buffer/deficit 분리”, “국가 원자료 비합산”, “후보 자격 UNKNOWN”이다. 이 네 가지를
과장 없이 시연해야 한다.

## 17. 최종 판정

**제출 가능 — 현재 84/100, 본상 경쟁력 있음.**

과거 P0인 예정 노출 의미 경계, 수출 liquidity mapping, 상담 priority·숫자·
handoff는 해결됐다. 456개 API-free tests, verify와 regression이 이를 회귀
검증한다. 대상 경쟁력은 실제 고객·KB 내부연동과 사용자성 증거가 없어 확정할 수
없다. 운영 배포는 auth·tenant·동의·malware·RM 계약 전까지 금지해야 한다.

## 부록 A. 설치된 패키지

`pip freeze` 실제 출력:

```text
altair==5.5.0
annotated-types==0.7.0
anyio==4.12.1
attrs==26.1.0
blinker==1.9.0
cachetools==6.2.6
certifi==2026.7.22
charset-normalizer==3.4.9
click==8.1.8
distro==1.9.0
exceptiongroup==1.3.1
gitdb==4.0.12
GitPython==3.1.55
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.18
Jinja2==3.1.6
jiter==0.16.0
jsonschema==4.25.1
jsonschema-specifications==2025.9.1
MarkupSafe==3.0.3
narwhals==2.21.0
numpy==2.0.2
openai==2.47.0
packaging==25.0
pandas==2.3.3
pillow==11.3.0
protobuf==6.33.6
pyarrow==21.0.0
pydantic==2.13.4
pydantic_core==2.46.4
pydeck==0.9.3
pypdf==5.9.0
python-dateutil==2.9.0.post0
python-dotenv==1.2.1
pytz==2026.2
referencing==0.36.2
requests==2.32.5
rpds-py==0.27.1
six==1.17.0
smmap==5.0.3
sniffio==1.3.1
streamlit==1.50.0
streamlit-pdf==1.0.8
tenacity==9.1.2
toml==0.10.2
tornado==6.5.7
tqdm==4.69.0
typing-inspection==0.4.2
typing_extensions==4.16.0
tzdata==2026.3
urllib3==1.26.20
```

## 부록 B. 주장 경계 최종 검사

사용 가능:

- 제한된 합성문서 평가
- 결정론적 국가 canonicalization
- source-grounded evidence recovery
- 사용자 확인 전 금융계산 차단
- 예정 결제 노출액과 실제 현재 잔액 `UNKNOWN`의 분리
- 공식 상담 후보
- 결정론적 상담 검토 Top 3
- API-free 456개 테스트
- 과거 Golden Live evidence 차단과 recovery 이후 제한된 Golden Live 1건 성공

사용 금지:

- 모든 문서에서 정확함
- OCR 정확도 100%
- 금융상품 자동 추천
- 대출 승인 예측·보험 가입 보장
- 공식 국가신용등급
- 현재 실제 미수잔액 확정
- 수익·최적 헤지 보장
- 실제 고객환경 검증 완료
- 한 건의 Golden Live 성공을 전체 문서·실제 고객환경 성능으로 일반화
