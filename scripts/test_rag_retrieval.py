"""Valida a recuperacao dos documentos indexados no ChromaDB.

O teste confirma se cada pergunta encontra o documento esperado entre os tres
primeiros resultados. A relevancia do texto recuperado ainda deve ser avaliada
por uma pessoa no relatorio gerado.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# O modelo ja foi baixado na criacao do indice. Estes modos evitam chamadas
# externas desnecessarias durante os testes e a demonstracao local.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from prepare_rag import COLLECTION_NAME, DEFAULT_CHROMA_DIR, DEFAULT_MODEL


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "data" / "processed" / "rag" / "retrieval_validation.md"
VALIDATION_QUESTIONS = [
    {
        "question": (
            "Como verificar se um audio ou video de alguem conhecido pode ter "
            "sido falsificado com inteligencia artificial?"
        ),
        "expected_file": "01_golpes_nao_se_deixe_enganar.pdf",
        "expected_page": 12,
    },
    {
        "question": (
            "Como conferir se um boleto e verdadeiro antes de fazer o pagamento?"
        ),
        "expected_file": "02_golpes_evite_fraudes.pdf",
        "expected_page": 13,
    },
    {
        "question": (
            "O que devo fazer depois de transferir dinheiro por Pix para um golpista?"
        ),
        "expected_file": "03_golpes_caiu_o_que_fazer.pdf",
        "expected_page": 6,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa as tres perguntas de validacao da recuperacao RAG."
    )
    parser.add_argument("--chroma-dir", type=Path, default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_console()

    if not args.chroma_dir.exists():
        raise FileNotFoundError(
            f"Indice nao encontrado em {args.chroma_dir}. Execute prepare_rag.py primeiro."
        )
    if args.top_k <= 0:
        raise ValueError("--top-k deve ser maior que zero.")

    embedding_function = SentenceTransformerEmbeddingFunction(
        model_name=args.model,
        device="cpu",
        normalize_embeddings=True,
    )
    client = chromadb.PersistentClient(path=str(args.chroma_dir))
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )

    lines = [
        "# Validacao da recuperacao RAG",
        "",
        f"- Colecao: `{COLLECTION_NAME}`",
        f"- Chunks indexados: {collection.count()}",
        f"- Resultados por pergunta: {args.top_k}",
        "",
        "Quanto menor a distancia, maior a similaridade. A verificacao automatica ",
        "confirma a origem; a relevancia do trecho deve ser avaliada manualmente.",
        "",
    ]
    matched_questions = 0

    for question_number, item in enumerate(VALIDATION_QUESTIONS, start=1):
        question = item["question"]
        expected_file = item["expected_file"]
        expected_page = item["expected_page"]
        result = collection.query(
            query_texts=[question],
            n_results=args.top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        found_expected = any(
            metadata.get("arquivo") == expected_file
            and metadata.get("pagina") == expected_page
            for metadata in metadatas
        )
        matched_questions += int(found_expected)

        lines.extend(
            [
                f"## Pergunta {question_number}",
                "",
                question,
                "",
                f"- Evidencia esperada: `{expected_file}`, pagina {expected_page}",
                f"- Encontrado no top {args.top_k}: "
                + ("SIM" if found_expected else "NAO"),
                "",
            ]
        )

        for rank, (document, metadata, distance) in enumerate(
            zip(documents, metadatas, distances), start=1
        ):
            lines.extend(
                [
                    f"### Resultado {rank}",
                    "",
                    f"- Documento: {metadata.get('titulo')}",
                    f"- Pagina: {metadata.get('pagina')}",
                    f"- Chunk: `{metadata.get('chunk_id')}`",
                    f"- Distancia: {float(distance):.4f}",
                    "",
                    str(document),
                    "",
                ]
            )

    lines.extend(
        [
            "## Resumo automatico",
            "",
            f"Perguntas que encontraram o documento esperado: "
            f"{matched_questions}/{len(VALIDATION_QUESTIONS)}.",
            "",
            "Aprovacao humana: PENDENTE.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8")

    print(f"Colecao: {COLLECTION_NAME}")
    print(f"Chunks indexados: {collection.count()}")
    print(
        "Perguntas com documento esperado no top "
        f"{args.top_k}: {matched_questions}/{len(VALIDATION_QUESTIONS)}"
    )
    print(f"Relatorio para avaliacao: {args.report}")


if __name__ == "__main__":
    main()
