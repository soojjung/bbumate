"""d002 도메인 답변 생성 모듈."""
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.utils.d002.context_extraction import build_user_context


# 모델이 한국어 문서를 보더라도 사용자에게는 영어로 답하도록 시키는 지시문.
_ENGLISH_DIRECTIVE = (
    "\n\nIMPORTANT LANGUAGE INSTRUCTION:\n"
    "- The retrieved source documents are written in Korean.\n"
    "- Read and understand them, but ALWAYS respond entirely in English.\n"
    "- Keep proper nouns (program names, agency names) in their original form, "
    "and add a brief English gloss in parentheses on first mention if helpful.\n"
    "- Preserve numeric values exactly; convert currency labels to English "
    "(예: '100만원' → '1,000,000 KRW' or 'KRW 1,000,000').\n"
    "- Bold Korean phrases like '제공된 문서에는' must NOT appear; if you must "
    "indicate missing info, write: 'The provided documents do not contain this information.'"
)


def _system_prompt_with_lang(system_prompt: str, lang: str) -> str:
    """lang=en이면 영어 출력 지시를 시스템 프롬프트 끝에 덧붙임."""
    if (lang or "ko").lower() == "en":
        return system_prompt + _ENGLISH_DIRECTIVE
    return system_prompt


def generate_with_web_context(
    question: str,
    web_results: str,
    llm_model,
    region: Optional[str] = None,
    housing_type: Optional[str] = None,
    lang: str = "ko",
) -> str:
    """웹 검색 결과를 컨텍스트로 사용하여 답변 생성."""
    # 지역/주거형태 컨텍스트 정보 생성
    user_context = build_user_context(region, housing_type, lang=lang)

    # 프롬프트 템플릿 구성 (컨텍스트 유무에 따라 다르게)
    if user_context:
        system_prompt = (
            "당신은 신혼부부 지원정책 도메인 전문가입니다. "
            "웹 검색 결과를 참고하여 질문에 답변하세요. "
            "정보가 충분하지 않으면 모른다고 답하세요.\n\n"
            "사용자 컨텍스트:\n{user_context}\n\n"
            "답변은 마크다운 형식으로 작성하세요:\n"
            "- 금액(예: 100만원, 3억원)과 비율(예: 50%, 3.5%)은 **굵게** 처리\n"
            "- 문장 단위로 줄바꿈 (마침표, 느낌표, 물음표 뒤)\n"
            "- 사용자 컨텍스트 정보(지역, 주거형태)가 제공되면 해당 정보를 고려하여 답변하세요."
        )
    else:
        system_prompt = (
            "당신은 신혼부부 지원정책 도메인 전문가입니다. "
            "웹 검색 결과를 참고하여 질문에 답변하세요. "
            "정보가 충분하지 않으면 모른다고 답하세요.\n\n"
            "답변은 마크다운 형식으로 작성하세요:\n"
            "- 금액(예: 100만원, 3억원)과 비율(예: 50%, 3.5%)은 **굵게** 처리\n"
            "- 문장 단위로 줄바꿈 (마침표, 느낌표, 물음표 뒤)"
        )

    system_prompt = _system_prompt_with_lang(system_prompt, lang)

    web_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "질문: {question}\n\n웹 검색 결과:\n{web_results}"),
        ]
    )
    web_chain = web_prompt | llm_model | StrOutputParser()

    try:
        invoke_params = {
            "question": question,
            "web_results": web_results,
        }
        if user_context:
            invoke_params["user_context"] = user_context

        answer = web_chain.invoke(invoke_params)
        return answer.strip()
    except Exception:
        if (lang or "ko").lower() == "en":
            return "Sorry, I couldn't generate an answer from the web search results."
        return "죄송합니다. 웹 검색 결과를 기반으로 답변을 생성할 수 없습니다."


def generate_with_docs_context(
    question: str,
    context: str,
    llm_model,
    region: Optional[str] = None,
    housing_type: Optional[str] = None,
    lang: str = "ko",
) -> str:
    """문서 컨텍스트를 사용하여 답변 생성."""
    # 지역/주거형태 컨텍스트 정보 생성
    user_context = build_user_context(region, housing_type, lang=lang)

    # 기본 프롬프트 구성
    base_prompt = """당신은 신혼부부 지원정책 및 가족/복지 정책 도메인 전문가입니다.

규칙:
1. 컨텍스트에 명확하게 나와있는 정보만 답변하세요. 컨텍스트에 없는 내용은 절대 추가하지 마세요.
2. 질문이 컨텍스트의 내용과 정확히 일치하지 않으면, "제공된 문서에는 해당 정보가 없습니다"라고 답하세요.
3. 답변은 자연스럽고 읽기 쉽게 작성하세요. "제공된 문서에는...", "○○ 문서에 따르면..." 같은 표현을 사용하지 마세요.
4. 문서명이나 파일명을 직접 언급하지 마세요.
5. 컨텍스트에 나와있는 정보를 연결하거나 확장하지 마세요. 정확히 명시된 내용만 답변하세요.
6. 답변은 마크다운 형식으로 작성하세요:
   - 금액(예: 100만원, 3억원)과 비율(예: 50%, 3.5%)은 **굵게** 처리
   - 문장 단위로 줄바꿈 (마침표, 느낌표, 물음표 뒤)"""

    # 사용자 컨텍스트가 있으면 추가
    if user_context:
        user_context_section = f"""
7. 사용자 컨텍스트 정보(지역, 주거형태)가 제공되면 해당 정보를 고려하여 답변하세요.

사용자 컨텍스트:
{user_context}

예시:
- 질문: "재테크 방법 알려줘" → 답변: "제공된 문서에는 재테크 방법에 대한 정보가 없습니다. 신혼부부 지원정책 및 가족/복지 정책 관련 질문만 답변드릴 수 있습니다."
- 질문: "전세자금대출 조건 알려줘" → 답변: 컨텍스트에 나와있는 조건을 정확히 답변 (금액/비율은 **굵게**, 문장 단위 줄바꿈)
- 사용자 컨텍스트가 "{user_context}"인 경우: 해당 지역/주거형태의 정보를 우선적으로 답변"""
    else:
        user_context_section = """

예시:
- 질문: "재테크 방법 알려줘" → 답변: "제공된 문서에는 재테크 방법에 대한 정보가 없습니다. 신혼부부 지원정책 및 가족/복지 정책 관련 질문만 답변드릴 수 있습니다."
- 질문: "전세자금대출 조건 알려줘" → 답변: 컨텍스트에 나와있는 조건을 정확히 답변 (금액/비율은 **굵게**, 문장 단위 줄바꿈)"""

    system_prompt = (
        f"{base_prompt}{user_context_section}\n\n컨텍스트:\n{{context}}".strip()
    )

    system_prompt = _system_prompt_with_lang(system_prompt, lang)

    # RAG 체인 구성: Context + Question → Generate
    rag_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "질문: {question}"),
        ]
    )

    # RAG 체인: 질문 + 컨텍스트 → LLM → 답변
    rag_chain = rag_prompt | llm_model | StrOutputParser()
    answer = rag_chain.invoke({"question": question, "context": context})

    return answer.strip()
