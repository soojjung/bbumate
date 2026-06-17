"""Ingestion index: bridge to d003 ingestion pipeline pieces.

Console-friendly `ingest` that mirrors src/ingestion/d003/pipeline.py
logging and behavior (load → split → embed → persist with timing).
Switch domain by editing imports here.

통합 Ingestion Index: 모든 도메인(d001~d005)의 ingestion 파이프라인 통합.
각 도메인의 기존 함수를 import하여 사용하고, domain 파라미터로 라우팅.
"""

import os
import time
import shutil
from typing import Optional, Literal
from pathlib import Path
from dotenv import load_dotenv

# 각 도메인의 기존 함수 import
from src.ingestion.d001.pipeline import main_pipeline as d001_main_pipeline
from src.ingestion.d001.pdf_loader import load_pdfs as d001_load_pdfs
from src.ingestion.d001.text_splitter import split_documents as d001_split_documents
from src.ingestion.d002.embed_store import embed_from_html, load_html_documents as d002_load_html_documents
from src.ingestion.d002.embed_store import extract_text_from_html
from src.ingestion.d003.loader import load_documents as d003_load_documents
from src.ingestion.d003.splitter import split_documents as d003_split_documents
from src.ingestion.d003.embedder import get_openai_embeddings
from src.ingestion.d003.vectorstore import persist_to_chroma as d003_persist_to_chroma
from src.ingestion.d004.batch_processor import process_pdf_directory as d004_process_pdf_directory
from src.ingestion.d004.vectorstore_manager import VectorStoreManager as d004_VectorStoreManager
from src.ingestion.d005.batch_processor import process_pdf_directory as d005_process_pdf_directory
from src.ingestion.d005.vectorstore_manager import VectorStoreManager as d005_VectorStoreManager

from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


def ingest(
    domain: str = "d003",
    data_dir: Optional[str] = None,
    mode: Literal["pdf", "html"] = "pdf",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    persist_dir: Optional[str] = None,
    force_recreate: bool = True,  # 기존 DB 재생성 여부 (기본값: True - 기존 동작 유지)
) -> None:
    """통합 ingestion 함수: 도메인별 적절한 파이프라인 실행.

    Args:
        domain: 도메인 이름 (d001, d002, d003, d004, d005, "all")
                "all"을 지정하면 모든 도메인을 순차적으로 처리
        data_dir: 데이터 디렉토리 경로 (None이면 도메인 기본값 사용)
        mode: 로드 모드 (pdf/html) - d003에서만 사용
        chunk_size: 청크 크기
        chunk_overlap: 청크 오버랩
        persist_dir: Chroma 저장 경로 (None이면 환경변수 또는 기본값 사용)

    Examples:
        >>> ingest("d001")  # d001 도메인 ingestion
        >>> ingest("d003", mode="html")  # d003 도메인 HTML 모드
        >>> ingest("all")  # 모든 도메인 순차 처리
        >>> ingest("d004", data_dir="data/d004")  # d004 도메인 커스텀 경로
    """
    load_dotenv()

    # "all" 옵션: 모든 도메인을 통합 벡터 DB에 저장
    if domain.lower() == "all":
        domains = ["d001", "d002", "d003", "d004", "d005"]
        print(f"\n{'='*60}")
        print(f"Starting UNIFIED ingestion for ALL domains: {domains}")
        print(f"All documents will be stored in a single unified vector database")
        print(f"{'='*60}\n")
        
        all_chunks = []
        
        # 각 도메인의 문서 로드 및 청킹
        for dom in domains:
            try:
                print(f"\n[Processing domain: {dom}]")
                default_dirs = {
                    "d001": "data/d001/housing",
                    "d002": "data/d002",
                    "d003": "data/d003",
                    "d004": "data/d004",
                    "d005": "data/d005",
                }
                data_dir = default_dirs.get(dom, "data")
                
                if not os.path.isdir(data_dir):
                    print(f"[WARN] Data directory not found: {data_dir}, skipping...")
                    continue
                
                # 도메인별 문서 로드 및 청킹
                if dom == "d001":
                    docs = d001_load_pdfs(Path(data_dir))
                    if docs:
                        chunks = d001_split_documents(docs)
                        for chunk in chunks:
                            chunk.metadata["domain"] = "d001"
                        all_chunks.extend(chunks)
                        print(f"[d001] Loaded {len(chunks)} chunks")
                
                elif dom == "d002":
                    base_dir = Path(data_dir)
                    input_dir = base_dir / "htmls"
                    if input_dir.exists():
                        docs = d002_load_html_documents(input_dir)
                        if docs:
                            splitter = RecursiveCharacterTextSplitter(
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                                length_function=len,
                                separators=["\n\n", "\n", " ", ""],
                            )
                            chunks = splitter.split_documents(docs)
                            for chunk in chunks:
                                chunk.metadata["domain"] = "d002"
                            all_chunks.extend(chunks)
                            print(f"[d002] Loaded {len(chunks)} chunks")
                
                elif dom == "d003":
                    docs = d003_load_documents(data_dir, mode=mode)
                    if docs:
                        chunks = d003_split_documents(
                            docs,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                            strip_html=(mode == "html"),
                        )
                        for chunk in chunks:
                            chunk.metadata["domain"] = "d003"
                        all_chunks.extend(chunks)
                        print(f"[d003] Loaded {len(chunks)} chunks")
                
                elif dom == "d004":
                    # d001 방식으로 PDF 로드 (PyPDFLoader 사용)
                    docs = d001_load_pdfs(Path(data_dir))
                    if docs:
                        chunks = d001_split_documents(docs)
                        for chunk in chunks:
                            chunk.metadata["domain"] = "d004"
                        all_chunks.extend(chunks)
                        print(f"[d004] Loaded {len(chunks)} chunks")
                
                elif dom == "d005":
                    # d001 방식으로 PDF 로드 (PyPDFLoader 사용 - 안정적)
                    docs = d001_load_pdfs(Path(data_dir))
                    if docs:
                        chunks = d001_split_documents(docs)
                        for chunk in chunks:
                            chunk.metadata["domain"] = "d005"
                        all_chunks.extend(chunks)
                        print(f"[d005] Loaded {len(chunks)} chunks")
                
            except Exception as e:
                print(f"[ERROR] Failed to process domain {dom}: {e}")
                print(f"Continuing with next domain...\n")
                continue
        
        if not all_chunks:
            print("[ERROR] No chunks loaded from any domain. Exiting.")
            return
        
        print(f"\n{'='*60}")
        print(f"Total chunks loaded: {len(all_chunks)}")
        print(f"Saving to unified vector database...")
        print(f"{'='*60}\n")
        
        # 통합 벡터 DB에 저장
        embeddings = get_openai_embeddings()
        db_path = persist_dir or os.getenv("CHROMA_DB_DIR", "./chroma_storage")
        collection_name = os.getenv("COLLECTION_NAME", "unified_rag_collection")
        
        print(f"[Unified DB] Collection: {collection_name}")
        print(f"[Unified DB] Path: {db_path}")
        
        start_time = time.perf_counter()
        
        # 기존 DB 처리
        if os.path.exists(db_path):
            if force_recreate:
                print(f"[Unified DB] Removing existing database...")
                shutil.rmtree(db_path)
            else:
                print(f"[WARN] 기존 DB가 존재합니다: {db_path}")
                print(f"[WARN] DB를 재생성하려면 force_recreate=True를 설정하세요.")
                print(f"[WARN] 기존 DB를 사용합니다.")
                return
        
        # 통합 벡터 DB 생성 및 저장
        # OpenAI 임베딩 API의 1회 요청 토큰 한도(300k)를 넘지 않도록 배치 처리.
        # 1,000+ 청크를 한 번에 from_documents에 넣으면 BadRequestError(400) 발생.
        BATCH_SIZE = 100
        total = len(all_chunks)

        vectorstore = Chroma.from_documents(
            documents=all_chunks[:BATCH_SIZE],
            embedding=embeddings,
            persist_directory=db_path,
            collection_name=collection_name,
        )
        done = min(BATCH_SIZE, total)
        print(f"[Unified DB] Embedded {done}/{total} chunks")
        for i in range(BATCH_SIZE, total, BATCH_SIZE):
            batch = all_chunks[i : i + BATCH_SIZE]
            vectorstore.add_documents(batch)
            done += len(batch)
            print(f"[Unified DB] Embedded {done}/{total} chunks")

        elapsed_s = time.perf_counter() - start_time
        print(f"\n{'='*60}")
        print(f"[DONE] Unified ingestion completed")
        print(f"Total chunks: {len(all_chunks)}")
        print(f"Time elapsed: {elapsed_s:.2f}s")
        print(f"Collection: {collection_name}")
        print(f"{'='*60}\n")
        return

    # 도메인별 기본 data_dir 설정
    if data_dir is None:
        default_dirs = {
            "d001": "data/d001/housing",
            "d002": "data/d002",
            "d003": "data/d003",
            "d004": "data/d004",
            "d005": "data/d005",
        }
        data_dir = default_dirs.get(domain, "data")

    if not os.path.isdir(data_dir):
        print(f"[ERROR] Data directory not found: {data_dir}")
        return

    print(f"\n{'='*60}")
    print(f"Starting ingestion for domain: {domain}")
    print(f"Data directory: {data_dir}")
    print(f"{'='*60}\n")

    # 도메인별 라우팅
    if domain == "d001":
        # d001: main_pipeline() 사용 (하드코딩된 경로 수정 필요 시 data_dir 활용)
        # 현재는 하드코딩된 경로를 사용하므로 경로가 맞으면 실행
        d001_main_pipeline()

    elif domain == "d002":
        # d002: embed_from_html() 사용
        base_dir = Path(data_dir)
        input_dir = base_dir / "htmls"
        persist_dir_path = Path(persist_dir) if persist_dir else (base_dir / "vector_store")
        collection_name = "d002"

        embed_from_html(
            input_dir=input_dir,
            persist_dir=persist_dir_path,
            collection_name=collection_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    elif domain == "d003":
        # d003: loader/splitter/embedder/vectorstore 조합
        print(f"[d003] Loading documents from {data_dir} (mode={mode}) ...")
        docs = d003_load_documents(data_dir, mode=mode)
        if not docs:
            print("[WARN] No documents found. Exiting.")
            return

        print(f"[d003] Splitting {len(docs)} documents ...")
        chunks = d003_split_documents(
            docs,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strip_html=(mode == "html"),
        )
        print(f"[d003] Created {len(chunks)} chunks.")

        print("[d003] Initializing embeddings ...")
        embeddings = get_openai_embeddings()

        print("[d003] Persisting to Chroma ...")
        start_time = time.perf_counter()
        d003_persist_to_chroma(chunks, embedding_function=embeddings)
        elapsed_s = time.perf_counter() - start_time
        print(f"[d003] Embedded and persisted {len(chunks)} chunks in {elapsed_s:.2f}s")

    elif domain == "d004":
        # d004: process_pdf_directory() + VectorStoreManager.save_documents()
        print(f"[d004] Processing PDF directory: {data_dir} ...")
        docs = d004_process_pdf_directory(data_dir)

        if not docs:
            print("[WARN] No documents found. Exiting.")
            return

        print(f"[d004] Created {len(docs)} chunks.")

        print("[d004] Saving to Chroma ...")
        start_time = time.perf_counter()

        collection_name = "d004"
        db_path = persist_dir or os.getenv("CHROMA_DB_DIR", "./chroma_storage")

        d004_VectorStoreManager.save_documents(
            documents=docs,
            collection_name=collection_name,
            db_path=db_path,
        )

        elapsed_s = time.perf_counter() - start_time
        print(f"[d004] Persisted {len(docs)} chunks in {elapsed_s:.2f}s")

    elif domain == "d005":
        # d005: process_pdf_directory() + VectorStoreManager.save_documents()
        print(f"[d005] Processing PDF directory: {data_dir} ...")
        docs = d005_process_pdf_directory(data_dir)

        if not docs:
            print("[WARN] No documents found. Exiting.")
            return

        print(f"[d005] Created {len(docs)} chunks.")

        print("[d005] Saving to Chroma ...")
        start_time = time.perf_counter()

        collection_name = "d005"
        db_path = persist_dir or os.getenv("CHROMA_DB_DIR", "./chroma_storage")

        d005_VectorStoreManager.save_documents(
            documents=docs,
            collection_name=collection_name,
            db_path=db_path,
        )

        elapsed_s = time.perf_counter() - start_time
        print(f"[d005] Persisted {len(docs)} chunks in {elapsed_s:.2f}s")

    else:
        raise ValueError(f"Unknown domain: {domain}. Available: d001, d002, d003, d004, d005, all")

    print(f"\n{'='*60}")
    print(f"[DONE] Ingestion completed for domain: {domain}")
    print(f"{'='*60}\n")


__all__ = ["ingest"]
