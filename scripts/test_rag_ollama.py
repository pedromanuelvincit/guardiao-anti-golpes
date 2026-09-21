"""Testa recuperação, prompt e geração local antes da interface Streamlit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.ollama_client import DEFAULT_MODEL, stream_chat
from guardiao.formatting import extract_glossary, format_markdown_stream
from guardiao.prompts import SYSTEM_PROMPT, build_user_prompt
from guardiao.rag import retrieve_contexts, select_generation_contexts
from guardiao.scope import OUT_OF_SCOPE_RESPONSE, is_in_scope


DEFAULT_QUESTION = "Como conferir se um boleto é verdadeiro antes de pagar?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa uma pergunta completa no RAG com o Ollama local."
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_console()

    print(f"Pergunta: {args.question}\n")
    if not is_in_scope(args.question):
        print(f"Resposta de escopo:\n\n{OUT_OF_SCOPE_RESPONSE}\n")
        return

    print("Recuperando os três trechos mais relevantes...")
    contexts = retrieve_contexts(args.question, top_k=args.top_k)

    print("\nFontes recuperadas:")
    for index, context in enumerate(contexts, start=1):
        metadata = context["metadata"]
        print(
            f"{index}. {metadata['titulo']} — página {metadata['pagina']} "
            f"— distância {context['distance']:.4f} "
            f"— termos {context.get('lexical_coverage', 0):.0%}"
        )

    generation_contexts = select_generation_contexts(contexts)
    print("\nTrechos enviados ao modelo:")
    for context in generation_contexts:
        metadata = context["metadata"]
        print(f"- {metadata['titulo']} — página {metadata['pagina']}")

    user_prompt = build_user_prompt(args.question, generation_contexts)
    print(f"\nResposta do {args.model}:\n")
    fragments = stream_chat(SYSTEM_PROMPT, user_prompt, model=args.model)
    for fragment in format_markdown_stream(
        fragments, prefix=extract_glossary(generation_contexts)
    ):
        print(fragment, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    main()
