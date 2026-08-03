from decimal import Decimal, InvalidOperation
from typing import Dict, List

from src.domain.country_economic_interpretation_models import (
    CountryEconomicIndicatorInput,
    CountryEconomicInterpretationDraft,
    CountryEconomicInterpretationSection,
)


def _decimal_direction(indicator: CountryEconomicIndicatorInput) -> str:
    if indicator.deterministic_value is None:
        return "MISSING"
    try:
        value = Decimal(indicator.deterministic_value)
    except InvalidOperation:
        return "MISSING"
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "ZERO"


def _gdp(indicator: CountryEconomicIndicatorInput) -> CountryEconomicInterpretationSection:
    observation_by_direction: Dict[str, str] = {
        "POSITIVE": "최근 공식 관측에서는 경제활동이 전년보다 증가했습니다.",
        "NEGATIVE": "최근 공식 관측에서는 경제활동이 전년보다 감소했습니다.",
        "ZERO": "최근 공식 관측에서는 경제활동의 큰 변화가 나타나지 않았습니다.",
        "MISSING": "검증된 경제 성장 지표를 확인하지 못했습니다.",
    }
    return CountryEconomicInterpretationSection(
        indicator_id="GDP_GROWTH",
        observation=observation_by_direction[_decimal_direction(indicator)],
        transaction_check=(
            "이 관측만으로 현재 거래의 안전성을 판단하지 말고 계약 조건을 별도로 확인하세요."
        ),
    )


def _inflation(indicator: CountryEconomicIndicatorInput) -> CountryEconomicInterpretationSection:
    observation = (
        "최근 공식 관측에서 소비자물가 변동이 확인됐습니다."
        if indicator.deterministic_value is not None
        else "검증된 소비자물가 지표를 확인하지 못했습니다."
    )
    return CountryEconomicInterpretationSection(
        indicator_id="INFLATION",
        observation=observation,
        transaction_check="계약가격과 현지 비용 조건의 실제 변화를 별도로 확인하세요.",
    )


def _current_account(indicator: CountryEconomicIndicatorInput) -> CountryEconomicInterpretationSection:
    observation_by_direction: Dict[str, str] = {
        "POSITIVE": "최근 공식 관측에서 대외수지 흑자가 나타났습니다.",
        "NEGATIVE": "최근 공식 관측에서 대외수지 적자가 나타났습니다.",
        "ZERO": "최근 공식 관측에서 대외수지가 균형에 가깝게 나타났습니다.",
        "MISSING": "검증된 대외수지 지표를 확인하지 못했습니다.",
    }
    return CountryEconomicInterpretationSection(
        indicator_id="CURRENT_ACCOUNT",
        observation=observation_by_direction[_decimal_direction(indicator)],
        transaction_check=(
            "국가의 외화 지급능력이나 거래처 신용도를 뜻하지 않으므로 결제와 송금 조건을 별도로 확인하세요."
        ),
    )


def _oecd(indicator: CountryEconomicIndicatorInput) -> CountryEconomicInterpretationSection:
    observation = (
        "공식 결제와 송금 참고 분류가 확인됐습니다."
        if indicator.deterministic_status != "DATA_UNAVAILABLE"
        else "검증된 결제와 송금 참고 분류를 확인하지 못했습니다."
    )
    return CountryEconomicInterpretationSection(
        indicator_id="OECD_CLASSIFICATION",
        observation=observation,
        transaction_check=(
            "국가 신용등급이나 개별 기업 평가가 아니므로 회수 보호수단 적용 범위와 결제 및 송금 조건을 확인하세요."
        ),
    )


def build_deterministic_interpretation(
    indicators: List[CountryEconomicIndicatorInput],
) -> CountryEconomicInterpretationDraft:
    builders = {
        "GDP_GROWTH": _gdp,
        "INFLATION": _inflation,
        "CURRENT_ACCOUNT": _current_account,
        "OECD_CLASSIFICATION": _oecd,
    }
    sections = [builders[item.indicator_id](item) for item in indicators]
    return CountryEconomicInterpretationDraft(
        overall_summary=(
            "검증된 공식 관측을 바탕으로 거래국 경제환경에서 확인할 사항을 정리했습니다. "
            "이 설명은 개별 거래의 안전성이나 금융 승인 여부를 판단하지 않습니다."
        ),
        sections=sections,
        limitations=[
            "이 설명은 공식 관측값의 이해를 돕는 참고 정보이며 개별 거래처 신용도를 평가하지 않습니다.",
            "환율 방향이나 손실 규모를 예측하지 않습니다.",
            "금융상품 가입 여부나 승인 결과를 확정하지 않습니다.",
        ],
    )
