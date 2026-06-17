"""Chain index: bridge module to select which domain chain to use.

Currently wired to d002 with unified database. To switch domain,
edit imports in this file only.
"""

import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# d002의 함수들을 import해서 사용
from src.chains.d002.rag_chain import run_rag, _format_docs
from src.utils.d002.loaders import load_llm

load_dotenv()


def load_unified_vector_db() -> Chroma:
    """통합 벡터 DB 로드 (unified_rag_collection 사용)."""
    db_path = os.getenv("CHROMA_DB_DIR", "./chroma_storage")
    collection_name = os.getenv("COLLECTION_NAME", "unified_rag_collection")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 필요합니다")

    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    embeddings = OpenAIEmbeddings(api_key=api_key, model=embedding_model)

    return Chroma(
        persist_directory=db_path,
        embedding_function=embeddings,
        collection_name=collection_name,
    )


def build_llm() -> ChatOpenAI:
    """OpenAI LLM 로드."""
    return load_llm()


def build_chain(k: int = 3, use_grade: bool = True):
    """RAG 체인 구성 요소 로드 (통합 DB 사용).

    통합 DB를 사용하여 retriever를 생성하고, LLM을 로드합니다.
    Grade 단계는 answer_question에서 직접 처리됩니다.
    """
    vectordb = load_unified_vector_db()
    llm = build_llm()

    retriever = vectordb.as_retriever(search_kwargs={"k": k})

    return retriever, llm, use_grade


def answer_question(
    question: str,
    k: int = 3,
    use_grade: bool = True,
    use_validation: bool = True,
    region: Optional[str] = None,
    housing_type: Optional[str] = None,
    lang: str = "ko",
    verbose: bool = False,
) -> Dict[str, Any]:
    """질문에 답변하고 문서 출처를 반환 (통합 DB 사용, d002의 run_rag 사용).

    d002의 run_rag 함수를 import해서 사용하되, 통합 DB를 사용하도록 수정합니다.
    검색된 파일명은 url_map.json에서 매핑하여 URL을 가져옵니다.

    Returns:
        {
            "answer": str,
            "sources": List[str],  # 파일명 리스트 (url_map.json에서 매핑 가능)
            "duration_ms": int,
            "num_docs": int,
            "clarification_needed": bool,
            "web_search_used": bool,
        }
    """
    # d002의 build_rag_chain을 임시로 통합 DB를 사용하도록 패치
    import src.chains.d002.rag_chain as rag_chain_module

    # 통합 DB를 사용하는 build_rag_chain 함수로 임시 교체
    original_build = rag_chain_module.build_rag_chain

    def unified_build_rag_chain(domain: str = "d002", use_grade: bool = True):
        """통합 DB를 사용하는 build_rag_chain"""
        vectordb = load_unified_vector_db()
        llm = build_llm()
        retriever = vectordb.as_retriever(
            search_kwargs={"k": k}
        )  # answer_question의 k 파라미터 사용
        return retriever, llm, use_grade

    # 임시로 함수 교체
    rag_chain_module.build_rag_chain = unified_build_rag_chain

    try:
        # d002의 run_rag 함수 호출 (통합 DB 사용)
        result = run_rag(
            query=question,
            domain="d002",  # domain 파라미터는 무시됨 (통합 DB 사용)
            verbose=verbose,
            use_grade=use_grade,
            use_validation=use_validation,
            region=region,
            housing_type=housing_type,
            lang=lang,
        )
        return result
    finally:
        # 원래 함수로 복원
        rag_chain_module.build_rag_chain = original_build


__all__ = [
    "build_chain",
    "answer_question",
    "build_llm",
    "load_unified_vector_db",
]
