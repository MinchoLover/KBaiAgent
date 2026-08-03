from src.domain.trade_statistics_interpretation_models import (
    TradeExportChangeDirection,
    TradeStatisticsInterpretationDraft,
)


SUMMARY_BY_DIRECTION = {
    "INCREASED": (
        "최근 양국 교역 자료에서 한국의 상대국 수출은 이전 비교기간보다 증가했습니다."
    ),
    "DECREASED": (
        "최근 양국 교역 자료에서 한국의 상대국 수출은 이전 비교기간보다 감소했습니다."
    ),
    "UNCHANGED": (
        "최근 양국 교역 자료에서 한국의 상대국 수출은 이전 비교기간과 유사한 흐름을 보였습니다."
    ),
    "UNAVAILABLE": (
        "비교 가능한 공식 자료가 충분하지 않아 수출 흐름의 변화를 설명하기 어렵습니다."
    ),
}
COMMON_LIMITATION = (
    "이 정보는 양국 전체 교역 흐름에 관한 참고자료이며 개별 거래처의 "
    "신용도나 대금 회수 가능성을 의미하지 않습니다."
)


def build_trade_statistics_fallback(
    direction: TradeExportChangeDirection,
) -> TradeStatisticsInterpretationDraft:
    return TradeStatisticsInterpretationDraft(
        summary=SUMMARY_BY_DIRECTION[direction],
        limitation=COMMON_LIMITATION,
    )
