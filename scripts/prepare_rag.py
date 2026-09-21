"""Extrai, divide e indexa os fasciculos do CERT.br usados pelo Guardiao.

O modo ``--skip-index`` prepara os chunks e uma previa sem baixar o modelo de
embeddings. Depois da validacao humana, execute novamente sem essa opcao para
criar o indice persistente do ChromaDB.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "documents" / "raw"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "rag"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "guardiao_antigolpes"
SOURCE_NAME = "Cartilha de Segurança para Internet - CERT.br/NIC.br"
SOURCE_HOME = "https://cartilha.cert.br/fasciculos/"
LICENSE_NAME = "CC BY-NC-ND 4.0"
LICENSE_URL = "https://cartilha.cert.br/cc/"
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

DOCUMENT_INFO = {
    "01_golpes_nao_se_deixe_enganar.pdf": {
        "titulo": "Golpes: Não se Deixe Enganar",
        "url": "https://cartilha.cert.br/fasciculos/golpes/fasciculo-golpes.pdf",
    },
    "02_golpes_evite_fraudes.pdf": {
        "titulo": "Golpes: Evite Fraudes",
        "url": (
            "https://cartilha.cert.br/fasciculos/golpes-evite-fraudes/"
            "fasciculo-golpes-evite-fraudes.pdf"
        ),
    },
    "03_golpes_caiu_o_que_fazer.pdf": {
        "titulo": "Golpes: Caiu? Veja o que Fazer",
        "url": (
            "https://cartilha.cert.br/fasciculos/golpes-o-que-fazer/"
            "fasciculo-golpes-o-que-fazer.pdf"
        ),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepara os documentos do CERT.br para o pipeline RAG."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--chroma-dir", type=Path, default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--chunk-overlap", type=int, default=150)
    parser.add_argument("--preview-per-document", type=int, default=2)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Gera os chunks e a previa, mas nao cria o indice vetorial.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> list[Path]:
    if args.chunk_size <= 0:
        raise ValueError("--chunk-size deve ser maior que zero.")
    if not 0 <= args.chunk_overlap < args.chunk_size:
        raise ValueError("--chunk-overlap deve ser menor que --chunk-size.")

    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if len(pdfs) < 3:
        raise FileNotFoundError(
            f"Esperados pelo menos 3 PDFs em {args.input_dir}; encontrados {len(pdfs)}."
        )

    unknown = [pdf.name for pdf in pdfs if pdf.name not in DOCUMENT_INFO]
    if unknown:
        raise ValueError(
            "Foram encontrados PDFs nao registrados: " + ", ".join(unknown)
        )
    return pdfs


def normalize_text(raw_text: str) -> str:
    """Normaliza espacos e recompõe palavras quebradas no fim de linhas."""
    text = unicodedata.normalize("NFC", raw_text).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_page_text(page: pdfplumber.page.Page) -> str:
    """Extrai texto e recompõe letras capitulares usadas no layout."""
    raw_text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
    words = page.extract_words(
        x_tolerance=2,
        y_tolerance=3,
        use_text_flow=True,
        extra_attrs=["fontname", "size"],
    )

    # Os fasciculos usam uma letra inicial grande (capitular). No PDF ela e
    # armazenada separadamente do restante da palavra, por exemplo "G olpistas".
    # O tamanho da fonte permite diferencia-la de artigos normais como "A conta".
    for current, following in zip(words, words[1:]):
        current_text = str(current["text"])
        following_text = str(following["text"])
        current_size = float(current["size"])
        following_size = float(following["size"])
        if (
            len(current_text) == 1
            and current_text.isalpha()
            and following_text
            and following_text[0].islower()
            and current_size >= following_size * 1.8
        ):
            separated = rf"\b{re.escape(current_text)}\s+{re.escape(following_text)}\b"
            raw_text = re.sub(
                separated,
                current_text + following_text,
                raw_text,
                count=1,
            )

    return normalize_text(raw_text)


def extract_pages(pdf_path: Path) -> list[dict[str, object]]:
    """Extrai apenas as paginas de conteudo e preserva a pagina de origem."""
    info = DOCUMENT_INFO[pdf_path.name]
    pages: list[dict[str, object]] = []

    with pdfplumber.open(pdf_path) as document:
        total_pages = len(document.pages)
        # Os tres fasciculos usam: capa na primeira pagina e material auxiliar
        # (divulgacao, saiba mais e creditos) nas tres paginas finais.
        first_content_index = 1
        last_content_index = max(first_content_index, total_pages - 3)

        for page_index in range(first_content_index, last_content_index):
            page_number = page_index + 1
            text = extract_page_text(document.pages[page_index])
            if not text:
                continue
            if "\ufffd" in text:
                raise ValueError(
                    f"Caractere corrompido em {pdf_path.name}, pagina {page_number}."
                )

            pages.append(
                {
                    "text": text,
                    "metadata": {
                        "arquivo": pdf_path.name,
                        "titulo": info["titulo"],
                        "pagina": page_number,
                        "total_paginas": total_pages,
                        "fonte": SOURCE_NAME,
                        "url_documento": info["url"],
                        "url_fonte": SOURCE_HOME,
                        "licenca": LICENSE_NAME,
                        "url_licenca": LICENSE_URL,
                    },
                }
            )
    return pages


def create_chunks(
    pages: list[dict[str, object]], chunk_size: int, chunk_overlap: int
) -> list[dict[str, object]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""],
    )
    counters: defaultdict[tuple[str, int], int] = defaultdict(int)
    chunks: list[dict[str, object]] = []

    for page in pages:
        metadata = dict(page["metadata"])
        page_chunks = splitter.split_text(str(page["text"]))
        key = (str(metadata["arquivo"]), int(metadata["pagina"]))

        for text in page_chunks:
            counters[key] += 1
            document_number = str(metadata["arquivo"])[:2]
            chunk_id = (
                f"certbr_{document_number}_p{int(metadata['pagina']):03d}_"
                f"c{counters[key]:02d}"
            )
            embedding_text = (
                f"Documento: {metadata['titulo']}\n"
                f"Pagina: {metadata['pagina']}\n\n"
                f"{text}"
            )
            chunks.append(
                {
                    "id": chunk_id,
                    "text": text,
                    "embedding_text": embedding_text,
                    "metadata": {
                        **metadata,
                        "chunk_id": chunk_id,
                        "caracteres": len(text),
                    },
                }
            )

    return chunks


def write_jsonl(chunks: list[dict[str, object]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as stream:
        for chunk in chunks:
            stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def choose_preview(
    chunks: list[dict[str, object]], per_document: int
) -> list[dict[str, object]]:
    grouped: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for chunk in chunks:
        grouped[str(chunk["metadata"]["arquivo"])].append(chunk)

    selected: list[dict[str, object]] = []
    for filename in sorted(grouped):
        group = grouped[filename]
        if per_document <= 1:
            positions = [len(group) // 2]
        else:
            positions = [
                round(index * (len(group) - 1) / (per_document - 1))
                for index in range(per_document)
            ]
        selected.extend(group[position] for position in sorted(set(positions)))
    return selected


def write_preview(
    chunks: list[dict[str, object]], output_path: Path, per_document: int
) -> None:
    selected = choose_preview(chunks, per_document)
    lines = [
        "# Previa de chunks do RAG",
        "",
        "Verifique se cada trecho pode ser entendido sozinho, se nao ha frases cortadas ",
        "e se documento e pagina estao corretos.",
        "",
    ]
    for chunk in selected:
        metadata = chunk["metadata"]
        lines.extend(
            [
                f"## {metadata['chunk_id']}",
                "",
                f"- Documento: {metadata['titulo']}",
                f"- Pagina: {metadata['pagina']}",
                f"- Caracteres: {metadata['caracteres']}",
                "",
                str(chunk["text"]),
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def index_chunks(
    chunks: list[dict[str, object]], chroma_dir: Path, model_name: str
) -> int:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception as error:  # Chroma varia a excecao entre versoes.
        if "does not exist" not in str(error).lower():
            raise

    embedding_function = SentenceTransformerEmbeddingFunction(
        model_name=model_name,
        device="cpu",
        normalize_embeddings=True,
    )
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 64
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        collection.add(
            ids=[str(chunk["id"]) for chunk in batch],
            documents=[str(chunk["embedding_text"]) for chunk in batch],
            metadatas=[dict(chunk["metadata"]) for chunk in batch],
        )
    return collection.count()


def main() -> None:
    args = parse_args()
    pdfs = validate_args(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, object]] = []
    for pdf_path in pdfs:
        pages.extend(extract_pages(pdf_path))

    chunks = create_chunks(pages, args.chunk_size, args.chunk_overlap)
    if not chunks:
        raise RuntimeError("Nenhum chunk foi gerado.")

    chunks_path = args.output_dir / "chunks.jsonl"
    preview_path = args.output_dir / "chunks_preview.md"
    write_jsonl(chunks, chunks_path)
    write_preview(chunks, preview_path, args.preview_per_document)

    print(f"PDFs processados: {len(pdfs)}")
    print(f"Paginas de conteudo: {len(pages)}")
    print(f"Chunks gerados: {len(chunks)}")
    print(f"Previa para validacao: {preview_path}")

    if args.skip_index:
        print("Indice vetorial: ignorado nesta execucao (--skip-index).")
        return

    indexed = index_chunks(chunks, args.chroma_dir, args.model)
    print(f"Chunks indexados no ChromaDB: {indexed}")
    print(f"Indice persistente: {args.chroma_dir}")


if __name__ == "__main__":
    main()
