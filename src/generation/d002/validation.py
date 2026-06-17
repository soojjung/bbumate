"""d002 도메인 질문 검증 모듈."""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# 영어 도메인 키워드 (lang=en 또는 영문 질문 감지용)
_EN_DOMAIN_KEYWORDS = [
    "newlywed",
    "marriage",
    "married",
    "wedding",
    "jeonse",
    "wolse",
    "lease",
    "rent",
    "rental",
    "deposit",
    "loan",
    "mortgage",
    "housing",
    "house",
    "apartment",
    "subscription",  # 주택청약
    "tax",
    "deduction",
    "credit",
    "subsidy",
    "subsidies",
    "benefit",
    "welfare",
    "single mother",
    "single parent",
    "childbirth",
    "child",
    "maternity",
    "parental",
    "support",
    "policy",
    "policies",
    "discount",
]

_EN_QUESTION_PATTERNS = [
    "how",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "eligibility",
    "amount",
    "limit",
    "rate",
    "interest",
    "qualify",
    "apply",
    "process",
    "condition",
    "requirement",
]


def is_question_clear(question: str, lang: str = "ko") -> bool:
    """규칙 기반으로 질문이 명확한지 빠르게 판단 (LLM 호출 없이).

    명확한 질문의 특징:
    - 구체적인 키워드 포함 (전세자금, 대출, 세금, 주택 등; 영문도 마찬가지)
    - 길이가 적절함 (5자 이상)
    - 단일 단어나 매우 짧은 질문 아님

    Returns:
        명확하면 True, 모호하면 False
    """
    question = question.strip()
    lang = (lang or "ko").lower()

    # 너무 짧으면 모호함
    if len(question) < 5:
        return False

    # 단일 단어만 있으면 모호함
    if len(question.split()) < 2:
        return False

    # 신혼부부 지원정책 관련 키워드 체크
    domain_keywords = [
        "신혼부부",
        "전세",
        "자금",
        "대출",
        "주택",
        "구입",
        "매매",
        "세금",
        "세액",
        "공제",
        "혜택",
        "청약",
        "공급",
        "전세자금",
        "구입자금",
        "주택청약",
        "특별공급",
        "버팀목",
        "디딤돌",
        # 가족/복지 정책 관련 키워드 추가 (미혼모, 한부모 등)
        "미혼모",
        "한부모",
        "모자",
        "부자",
        "지원",
        "정책",
        "복지",
    ]

    if any(keyword in question for keyword in domain_keywords):
        return True

    # 기본 질문 패턴 체크 (한국어)
    question_patterns = [
        "조건",
        "한도",
        "금리",
        "혜택",
        "신청",
        "방법",
        "절차",
        "요건",
        "자격",
        "대상",
        "기간",
        "금액",
        "율",
    ]

    if any(pattern in question for pattern in question_patterns):
        return True

    # 영문 질문이면 영어 키워드도 함께 검사 (lang=en이거나 영문 문자가 많을 때)
    looks_english = (
        lang == "en"
        or sum(1 for ch in question if ch.isascii() and ch.isalpha())
        > len(question) // 2
    )
    if looks_english:
        lower_q = question.lower()
        if any(kw in lower_q for kw in _EN_DOMAIN_KEYWORDS):
            return True
        if any(p in lower_q for p in _EN_QUESTION_PATTERNS):
            return True

    # 기본적으로는 모호함으로 판단
    return False


def validate_question(
    question: str, llm_model, lang: str = "ko"
) -> tuple[bool, str, str]:
    """질문 검증: 도메인 관련성 + 명확성 동시 체크.

    Returns:
        (is_valid, reason, clarification_question)
        - is_valid: 질문이 유효하면 True, 아니면 False
        - reason: 실패 이유 ('domain' 또는 'ambiguity')
        - clarification_question: 모호한 경우 명확화 질문 (도메인 외면 빈 문자열)
    """
    validation_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 질문 평가 전문가입니다. 사용자의 질문은 한국어 또는 영어일 수 있습니다.\n"
                "다음 두 가지를 동시에 판단하세요:\n\n"
                "1. **도메인 관련성**: 질문이 신혼부부 지원정책(주거, 대출, 전세자금, 구매자금, 신혼부부 혜택 등) "
                "또는 가족/복지 정책(미혼모, 한부모, 모자/부자 가정 지원 등)과 관련이 있으면 'DOMAIN_OK', "
                "날씨, 요리, 일반 뉴스 등 무관한 주제면 'DOMAIN_OUT'으로 답하세요.\n"
                "(영어 예: 'newlywed loan', 'jeonse deposit support', 'single mother benefits' 등은 DOMAIN_OK)\n\n"
                "2. **질문 명확성**: 질문이 매우 모호하거나 거의 아무 정보도 없는 경우에만 'AMBIGUOUS', "
                "명확한 질문이면 'CLEAR'로 답하세요.\n\n"
                "예시 - 명확한 질문 (DOMAIN_OK, CLEAR): '신혼부부 전세자금대출 조건', '전세자금 대출 한도', "
                "'미혼모가 받을 수 있는 지원', 'What support is available for single mothers?', "
                "'newlywed jeonse loan conditions' 등\n"
                "예시 - 모호한 질문 (DOMAIN_OK, AMBIGUOUS): '대출', '조건 알려줘', 'loan', 'help' 등\n"
                "예시 - 도메인 외 (DOMAIN_OUT): '오늘 날씨는?', 'pasta recipe', 'news today' 등\n\n"
                "일반적인 조건/정보 문의는 명확한 것으로 판단하세요. 개인 맞춤형 답변을 위해 지역/소득 정보가 필요한 경우에만 모호하다고 판단하세요.\n\n"
                "답변 형식: '도메인: [DOMAIN_OK/DOMAIN_OUT], 명확성: [CLEAR/AMBIGUOUS]'",
            ),
            ("human", "질문: {question}"),
        ]
    )
    validation_chain = validation_prompt | llm_model | StrOutputParser()

    try:
        result = validation_chain.invoke({"question": question}).upper()

        # 도메인 체크
        is_domain_ok = "DOMAIN_OK" in result
        if not is_domain_ok:
            return (False, "domain", "")

        # 명확성 체크
        is_ambiguous = "AMBIGUOUS" in result
        if is_ambiguous:
            clarification_question = clarify_question(question, llm_model, lang=lang)
            return (False, "ambiguity", clarification_question)

        # 통과
        return (True, "", "")

    except Exception:
        # 평가 실패 시 유효하다고 가정 (안전장치)
        return (True, "", "")


def clarify_question(question: str, llm_model, lang: str = "ko") -> str:
    """모호한 질문을 명확화하기 위한 질문을 생성 (Re-ask)."""
    lang = (lang or "ko").lower()

    if lang == "en":
        system_msg = (
            "You are a newlywed-policy counselor. When the user's question is vague, "
            "ask for the 1-2 most essential pieces of context you need to answer. "
            "Keep it concise (one sentence) and ask for at most two items. "
            "Respond entirely in English. "
            "Example: 'Could you tell me your residence region (Seoul / metro area / other) "
            "and housing type (jeonse / monthly rent / homeowner)?' "
            "Do not list many questions or get too specific."
        )
        human_msg = "Vague question: {question}\n\nConcise clarification question (1-2 key items only):"
        fallback = "Could you share the key context I need (region, housing type, etc.)?"
    else:
        system_msg = (
            "당신은 신혼부부 지원정책 상담사입니다. "
            "사용자의 모호한 질문에 대해, 답변에 꼭 필요한 핵심 정보 1-2가지만 간결하게 물어보세요. "
            "가능하면 한 문장으로, 최대 2개의 핵심 정보만 요청하세요. "
            "예: '거주 지역(서울/수도권/지방)과 주거형태(전세/매매)를 알려주세요.' "
            "너무 구체적이거나 여러 질문을 나열하지 마세요."
        )
        human_msg = "모호한 질문: {question}\n\n간결한 명확화 질문(1-2개 핵심 정보만):"
        fallback = "답변에 필요한 핵심 정보(지역, 주거형태 등)를 알려주세요."

    clarify_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_msg),
            ("human", human_msg),
        ]
    )
    clarify_chain = clarify_prompt | llm_model | StrOutputParser()

    try:
        clarified = clarify_chain.invoke({"question": question})
        return clarified.strip()
    except Exception:
        return fallback
