"""d002 도메인 RAG 체인 정의."""
import time
from typing import List, Dict, Any, Optional

from langchain_core.output_parsers import StrOutputParser

from src.utils.d002.loaders import load_vector_db, load_llm
from src.utils.d002.context_extraction import (
    apply_region_housing_priority,
    build_user_context,
)
from src.retrieval.d002.grader import grade_docs
from src.generation.d002.validation import is_question_clear, validate_question
from src.generation.d002.generator import generate_with_docs_context, generate_with_web_context
from src.generation.d002.web_search import execute_web_search_path


def _format_docs(docs: List[Any]) -> str:
    """문서들을 컨텍스트 형식으로 포맷팅 (출처 정보 제거하여 자연스러운 답변 유도)."""
    lines = []
    for i, d in enumerate(docs, 1):
        content = (d.page_content or "").strip()

        # 성능 개선: 문서 길이 제한 (요약형)
        if len(content) > 1500:
            content = content[:1500] + "..."

        lines.append(f"[문서 {i}]\n{content}")

    return "\n\n---\n\n".join(lines) if lines else "제공된 문서 없음"


def build_rag_chain(domain: str = "d002", use_grade: bool = True):
    """RAG 체인 구성 요소 로드 (Grade 단계는 run_rag에서 직접 처리).

    Note: Grade 단계가 있어서 체인을 완전히 구성하기 어려움.
    대신 필요한 컴포넌트(vectordb, retriever, llm)만 반환하고,
    실제 RAG 체인은 run_rag에서 Grade 포함하여 구성함.
    """
    vectordb = load_vector_db(domain)
    llm = load_llm()

    # 성능 개선: k 값 줄이기 (5 → 3)
    retriever = vectordb.as_retriever(search_kwargs={"k": 3})

    return retriever, llm, use_grade


def run_rag(
    query: str,
    domain: str = "d002",
    verbose: bool = False,
    use_grade: bool = True,
    use_validation: bool = True,
    region: Optional[str] = None,
    housing_type: Optional[str] = None,
    lang: str = "ko",
) -> Dict[str, Any]:
    """RAG 파이프라인 실행 (Question Validation → Retrieve → Grade → Generate).

    플로우:
    1. Question Validation: 도메인 관련성 + 명확성 동시 체크
       - 통과 못하면 → Re-ask/Clarification 또는 도메인 외 에러
    2. Retrieve: 문서 검색
    3. Grade: 관련성 높은 문서만 필터링
       - 문서 있으면(Yes) → Generate (RAG 체인 사용)
       - 문서 없으면(No) → Re-write query → Web search → Generate
    """
    start = time.perf_counter()
    retriever, llm, grade_enabled = build_rag_chain(domain, use_grade=use_grade)

    lang = (lang or "ko").lower()

    # 지역/주거형태 우선순위 적용
    final_region, final_housing_type = apply_region_housing_priority(
        query, region, housing_type
    )

    if verbose:
        if final_region or final_housing_type:
            print(
                f"[컨텍스트] 지역: {final_region or '미지정'}, 주거형태: {final_housing_type or '미지정'}"
            )

    # Question Validation: 도메인 관련성 + 명확성 동시 체크 (선택적 스킵)
    if use_validation:
        # 명확한 질문이면 validation 스킵하여 성능 향상
        if is_question_clear(query, lang=lang):
            if verbose:
                print("[Validation 스킵: 명확한 질문]")
            # validation 통과로 간주
        else:
            # 모호한 질문이면 LLM으로 validation 실행
            is_valid, reason, clarification_question = validate_question(
                query, llm, lang=lang
            )

            if not is_valid:
                if reason == "domain":
                    if verbose:
                        print("[도메인 관련성 없음]")

                    domain_msg = (
                        "Sorry, I can only answer questions about newlywed support policies "
                        "(housing, loans, jeonse/purchase funds, etc.) and family/welfare policies "
                        "(single mothers, single parents, etc.). I can't help with other topics."
                        if lang == "en"
                        else "죄송합니다. 신혼부부 지원정책(주거, 대출, 전세자금, 구매자금 등) 및 가족/복지 정책(미혼모, 한부모 지원 등) 관련 질문만 답변드릴 수 있습니다. 다른 주제의 질문은 처리할 수 없습니다."
                    )
                    return {
                        "answer": domain_msg,
                        "sources": [],
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "num_docs": 0,
                        "clarification_needed": False,
                        "web_search_used": False,
                    }

                elif reason == "ambiguity":
                    if verbose:
                        print("[질문 모호성 감지]")
                        print(f"[명확화 요청]: {clarification_question}")

                    ambiguity_prefix = (
                        "Could you clarify your question?"
                        if lang == "en"
                        else "질문을 더 명확히 해주세요."
                    )
                    return {
                        "answer": f"{ambiguity_prefix}\n\n{clarification_question}",
                        "sources": [],
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "num_docs": 0,
                        "clarification_needed": True,
                        "web_search_used": False,
                    }

    # Retrieve: 문서 검색
    initial_docs = retriever.invoke(query)
    
    # 검색된 문서 내용 출력 (디버깅용)
    if verbose and initial_docs:
        print(f"[검색된 문서 (Grade 전)] {len(initial_docs)}개")
        for i, doc in enumerate(initial_docs[:3], 1):  # 최대 3개만 출력
            content_preview = (doc.page_content or "")[:200]
            source = doc.metadata.get("source", "unknown")
            print(f"  [{i}] {source}: {content_preview}...")

    # Grade: 관련성 높은 문서만 필터링
    if grade_enabled and initial_docs:
        graded_docs = grade_docs(query, initial_docs, llm)
        if verbose:
            print(f"[Grade 결과] {len(initial_docs)}개 → {len(graded_docs)}개")
    else:
        graded_docs = initial_docs

    # Grade 결과로 바로 결정
    use_web_search = False
    if graded_docs:
        # Grade Yes: 관련 문서가 있음 → RAG 체인으로 Generate
        context = _format_docs(graded_docs)

        # Generate with documents
        answer = generate_with_docs_context(
            query, context, llm, final_region, final_housing_type, lang=lang
        )

        # 답변에서 "정보가 없습니다" 패턴 감지 → Web Search 경로로 전환
        # Korean LLM 답변 또는 English LLM 답변 두 경우 모두 잡기 위해 영문 패턴도 포함
        no_info_patterns = [
            "제공된 문서에는 해당 정보가 없습니다",
            "제공된 문서에는",
            "해당 정보가 없습니다",
            "정보가 없습니다",
            "찾을 수 없습니다",
            "the provided documents do not contain",
            "no information is available",
            "no information about",
            "i cannot find",
            "could not find",
        ]
        # 패턴이 답변의 시작 부분에 나타나는 경우만 감지 (일부 내용만 언급하는 경우 제외)
        answer_lower = answer.lower()
        if any(pattern in answer_lower for pattern in no_info_patterns):
            # 문서로 답변 불가능 → Web Search 경로로 전환
            use_web_search = True

            if verbose:
                print("[Generate 결과: 정보 없음 → Web Search 경로로 전환]")

            answer, sources = execute_web_search_path(
                query, llm, final_region, final_housing_type, verbose, lang=lang
            )
        else:
            # 답변 성공
            # 문서 출처 파일명 반환 (URL 매핑은 API에서 처리)
            source_set = {d.metadata.get("source", "unknown") for d in graded_docs}
            sources = list(source_set)
    else:
        # Grade No: 관련 문서가 없음 → Re-write query → Web Search → Generate
        use_web_search = True

        if verbose:
            print("[Grade 결과: 관련 문서 없음]")

        answer, sources = execute_web_search_path(
            query, llm, final_region, final_housing_type, verbose, lang=lang
        )

    # sources는 위에서 이미 설정됨 (웹 검색 경로 또는 문서 경로)
    duration_ms = int((time.perf_counter() - start) * 1000)

    if verbose:
        print("[질문]", query)
        print(f"[검색 문서] {len(initial_docs)}개 → {len(graded_docs)}개 (Grade)")
        if graded_docs and not use_web_search:
            # 검색된 문서 내용 일부 출력 (디버깅용)
            print(f"[검색된 문서 내용 샘플]")
            for i, doc in enumerate(graded_docs[:2], 1):  # 최대 2개만 출력
                content_preview = (doc.page_content or "")[:200]
                source = doc.metadata.get("source", "unknown")
                print(f"  [{i}] {source}: {content_preview}...")
        if use_web_search:
            print("[웹 검색 경로 사용]")
        print(f"[소요(ms)]", duration_ms)
        print("[답변]", answer)
        print("[출처]", sources)

    return {
        "answer": answer,
        "sources": sources,
        "duration_ms": duration_ms,
        "num_docs": len(graded_docs) if not use_web_search else 0,
        "clarification_needed": False,
        "web_search_used": use_web_search,
    }

