"""Recuperação de trechos dos documentos indexados no ChromaDB."""

from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "guardiao_antigolpes"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
STOPWORDS = {
    "a", "ao", "as", "com", "como", "da", "de", "depois", "do", "dos",
    "e", "em", "eu", "o", "os", "para", "por", "que", "se", "um", "uma",
}


def _search_terms(text: str) -> set[str]:
    """Cria radicais simples para complementar a similaridade semântica."""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    words = re.findall(r"[a-z0-9]+", normalized)
    return {
        word[:8]
        for word in words
        if len(word) >= 4 and word not in STOPWORDS
    }


@lru_cache(maxsize=2)
def _get_collection(chroma_path: str):
    """Mantém o modelo de embeddings carregado entre perguntas."""
    embedding_function = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        device="cpu",
        normalize_embeddings=True,
    )
    client = chromadb.PersistentClient(path=chroma_path)
    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )


def retrieve_contexts(
    question: str,
    top_k: int = 3,
    chroma_dir: Path = DEFAULT_CHROMA_DIR,
) -> list[dict[str, object]]:
    """Retorna os trechos mais próximos da pergunta e seus metadados."""
    if not question.strip():
        raise ValueError("A pergunta não pode estar vazia.")
    if top_k <= 0:
        raise ValueError("top_k deve ser maior que zero.")
    if not chroma_dir.exists():
        raise FileNotFoundError(
            f"Índice não encontrado em {chroma_dir}. Execute prepare_rag.py primeiro."
        )

    collection = _get_collection(str(chroma_dir.resolve()))
    candidate_count = min(max(top_k * 2, top_k), collection.count())
    result = collection.query(
        query_texts=[question],
        n_results=candidate_count,
        include=["documents", "metadatas", "distances"],
    )

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    question_terms = _search_terms(question)
    contexts = [
        {
            "document": document,
            "metadata": metadata,
            "distance": float(distance),
            "lexical_coverage": (
                len(question_terms & _search_terms(str(document)))
                / max(len(question_terms), 1)
            ),
        }
        for document, metadata, distance in zip(
            documents, metadatas, distances, strict=True
        )
    ]
    for context in contexts:
        context["hybrid_score"] = (
            context["distance"] - 0.35 * context["lexical_coverage"]
        )
    contexts.sort(
        key=lambda context: context["hybrid_score"]
    )
    return contexts[:top_k]


def select_generation_contexts(
    contexts: list[dict[str, object]], max_score_gap: float = 0.10
) -> list[dict[str, object]]:
    """Remove resultados muito abaixo do melhor antes de chamar o LLM."""
    if not contexts:
        return []
    best_score = float(contexts[0]["hybrid_score"])
    return [
        context
        for context in contexts
        if float(context["hybrid_score"]) <= best_score + max_score_gap
    ]
