"""d002 도메인 컨텍스트 추출 유틸리티."""
from typing import Optional


def extract_region_from_question(question: str) -> Optional[str]:
    """질문에서 지역 정보 추출.

    지역 키워드:
    - 서울, 부산, 대구, 인천, 광주, 대전, 울산, 세종
    - 경기, 강원, 충북, 충남, 전북, 전남, 경북, 경남, 제주
    - 수도권, 지방, 수도권외
    """
    region_keywords = [
        "서울",
        "부산",
        "대구",
        "인천",
        "광주",
        "대전",
        "울산",
        "세종",
        "경기",
        "강원",
        "충북",
        "충남",
        "전북",
        "전남",
        "경북",
        "경남",
        "제주",
        "수도권",
        "지방",
        "수도권외",
        "경기도",
        "인천광역시",
        "서울특별시",
    ]

    for keyword in region_keywords:
        if keyword in question:
            # 간단한 정리 (예: "경기도" -> "경기")
            if keyword == "경기도":
                return "경기"
            elif keyword == "인천광역시":
                return "인천"
            elif keyword == "서울특별시":
                return "서울"
            return keyword

    return None


def extract_housing_type_from_question(question: str) -> Optional[str]:
    """질문에서 주거형태 정보 추출.

    주거형태 키워드:
    - 전세, 월세, 반전세, 자가, 매매, 구매, 분양, 청약
    """
    housing_keywords = [
        "전세",
        "월세",
        "반전세",
        "자가",
        "매매",
        "구매",
        "분양",
        "청약",
    ]

    for keyword in housing_keywords:
        if keyword in question:
            return keyword

    return None


def apply_region_housing_priority(
    question: str,
    preset_region: Optional[str],
    preset_housing_type: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """지역/주거형태 우선순위 적용.

    우선순위: 질문 속 지역/주거형태 > 사전 선택 지역/주거형태

    Returns:
        (최종 지역, 최종 주거형태)
    """
    # 질문에서 추출
    question_region = extract_region_from_question(question)
    question_housing_type = extract_housing_type_from_question(question)

    # 우선순위 적용
    final_region = question_region if question_region else preset_region
    final_housing_type = (
        question_housing_type if question_housing_type else preset_housing_type
    )

    return final_region, final_housing_type


def build_user_context(
    region: Optional[str],
    housing_type: Optional[str],
    lang: str = "ko",
) -> Optional[str]:
    """지역/주거형태 컨텍스트 문자열 생성.

    Returns:
        컨텍스트 문자열 또는 None (정보가 없을 경우)
    """
    lang = (lang or "ko").lower()
    is_en = lang == "en"
    region_label = "Region" if is_en else "거주 지역"
    housing_label = "Housing type" if is_en else "주거형태"

    context_info = []
    if region:
        context_info.append(f"{region_label}: {region}")
    if housing_type:
        context_info.append(f"{housing_label}: {housing_type}")
    return "\n".join(context_info) if context_info else None

