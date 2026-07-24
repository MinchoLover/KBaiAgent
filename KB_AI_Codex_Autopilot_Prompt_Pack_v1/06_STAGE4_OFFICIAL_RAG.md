# Stage 4 공식 금융상품 RAG 프롬프트

공식 출처만을 사용해 Stage 3 전략을 실행할 수 있는 상품·제도 후보를 검색하는 모듈을 구현하라.

모드:

1. `OFFLINE_KB`: local Markdown/JSON knowledge base + lexical search
2. `OFFICIAL_WEB_SEARCH`: OpenAI Responses API web search tool, allowed domains only

기본 공식 도메인 allowlist:

- kbstar.com
- kbfg.com
- ksure.or.kr
- kosmes.or.kr
- bizinfo.go.kr
- kodit.co.kr
- kibo.or.kr

검색 대상:

- 선물환
- 환변동보험
- 외화예금
- 수출입 대출
- 정책자금
- 보증상품

각 후보 스키마:

- product_name
- institution
- category
- target_users
- relevant_reason
- eligibility_summary
- required_documents
- application_path
- source_title
- source_url
- checked_at
- evidence_excerpt paraphrase
- unknown_fields
- human_review_required

규칙:

- 공식 도메인 외 결과 제외
- 현재 운영 여부와 기준일 표시
- 금리·한도·승인 가능성 추정 금지
- 출처 없는 주장 금지
- eligibility가 불분명하면 상담 질문으로 변환
- 결과 캐시와 만료시간
- web search 비활성/API 오류 시 offline KB fallback
- 출처를 최종 보고서까지 유지

검색 프롬프트와 ranking 규칙을 파일로 분리하고, unrelated/expired/unofficial fixture를 거르는 테스트를 작성하라.
