"""Ajustes mínimos de apresentação aplicados durante o streaming."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator


def extract_glossary(contexts: list[dict[str, object]]) -> str:
    """Extrai definições explícitas de siglas presentes nos trechos."""
    entries: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"(?m)^([^\n()]{3,80}) \(([A-Z]{2,})\)\s*\n\s*é\s+(.+?)\.",
        flags=re.DOTALL,
    )

    for context in contexts:
        for full_name, acronym, definition in pattern.findall(
            str(context["document"])
        ):
            if acronym in seen:
                continue
            seen.add(acronym)
            clean_name = " ".join(full_name.split())
            clean_definition = " ".join(definition.split())
            entries.append(
                f"**O que é {acronym}:** {clean_name} é {clean_definition}."
            )

    return "\n\n".join(entries)


def format_markdown_stream(
    fragments: Iterable[str], prefix: str = ""
) -> Iterator[str]:
    """Garante que marcadores redondos apareçam em linhas separadas."""
    if prefix:
        yield f"{prefix}\n\n"
    for fragment in fragments:
        yield fragment.replace("•", "\n\n-")
