"""d002 도메인 웹 검색 모듈."""
import os
from typing import List, Dict, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def rewrite_query(question: str, llm_model) -> str:
    """웹 검색에 적합하도록 쿼리를 재작성 (Re-write query)."""
    rewrite_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 웹 검색 쿼리 전문가입니다. "
                "사용자의 질문을 웹 검색에 최적화된 검색 쿼리로 재작성하세요. "
                "핵심 키워드를 포함하고, 자연어 질문을 검색 친화적인 형태로 변환하세요.",
            ),
            ("human", "원래 질문: {question}\n\n웹 검색 쿼리로 재작성:"),
        ]
    )
    rewrite_chain = rewrite_prompt | llm_model | StrOutputParser()

    try:
        rewritten = rewrite_chain.invoke({"question": question})
        return rewritten.strip()
    except Exception:
        return question


def web_search(query: str) -> tuple[str, List[Dict[str, str]]]:
    """웹 검색 실행 (Tavily API 사용).

    Returns:
        (검색 결과 텍스트, 검색 결과 리스트) 튜플 반환.
        검색 결과 리스트는 {"title": str, "url": str} 딕셔너리 리스트.
        API 호출 실패 시 더미 응답과 빈 리스트 반환.
    """
    try:
        from tavily import TavilyClient

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            # API 키가 없으면 더미 응답 반환 (개발/테스트 환경)
            return (
                f"[웹 검색 결과] '{query}'에 대한 최신 정보를 찾을 수 없습니다. TAVILY_API_KEY가 설정되지 않았습니다.",
                [],
            )

        client = TavilyClient(api_key=api_key)

        # Tavily API 호출
        # search_depth: "basic" (빠름) 또는 "advanced" (더 상세)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=3,  # 상위 3개 결과만 사용
        )

        # 검색 결과 포맷팅 및 메타데이터 추출
        if response.get("results"):
            results_text = []
            web_results = []
            for i, result in enumerate(response["results"], 1):
                title = result.get("title", "")
                content = result.get("content", "")
                url = result.get("url", "")

                if url:
                    web_results.append({"title": title, "url": url})

                results_text.append(f"[결과 {i}] {title}\n{content}\n출처: {url}")

            return "\n\n---\n\n".join(results_text), web_results
        else:
            return (
                f"[웹 검색 결과] '{query}'에 대한 검색 결과를 찾을 수 없습니다.",
                [],
            )

    except ImportError:
        # tavily-python 패키지가 설치되지 않은 경우
        return (
            f"[웹 검색 결과] '{query}'에 대한 최신 정보를 찾을 수 없습니다. tavily-python 패키지가 설치되지 않았습니다.",
            [],
        )
    except Exception as e:
        # API 호출 실패 시 더미 응답 반환
        return (
            f"[웹 검색 결과] '{query}'에 대한 최신 정보를 찾을 수 없습니다. 검색 중 오류 발생: {str(e)}",
            [],
        )


def execute_web_search_path(
    query: str,
    llm,
    final_region: Optional[str],
    final_housing_type: Optional[str],
    verbose: bool = False,
    lang: str = "ko",
) -> tuple[str, List[Dict[str, str]]]:
    """웹 검색 경로 실행 (Re-write query → Web Search → Generate).

    Returns:
        (답변, sources 메타데이터)
    """
    from src.generation.d002.generator import generate_with_web_context

    if verbose:
        print("[웹 검색 경로 실행]")

    # Re-write query
    rewritten_query = rewrite_query(query, llm)

    if verbose:
        print(f"[쿼리 재작성]: {rewritten_query}")

    # Web Search
    web_results, web_metadata = web_search(rewritten_query)

    if verbose:
        print("[웹 검색 완료]")

    # Generate with Web Search results
    answer = generate_with_web_context(
        query, web_results, llm, final_region, final_housing_type, lang=lang
    )

    # 웹 검색 메타데이터를 sources 형태로 변환
    fallback_label = "Web search" if (lang or "ko").lower() == "en" else "웹 검색"
    sources = (
        [{"title": item["title"], "url": item["url"]} for item in web_metadata]
        if web_metadata
        else [fallback_label]
    )

    return answer, sources

