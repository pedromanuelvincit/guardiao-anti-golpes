"""Ferramentas locais e controladas preparadas para o Sprint 2.

As funções deste módulo são adaptadores finos sobre componentes da Etapa 1.
Nenhuma delas abre URLs, executa SQL recebido do modelo ou acessa serviços
externos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from guardiao.data_queries import QUERY_DEFINITIONS, format_query_answer, run_named_query
from guardiao.url_model import (
    DEFAULT_MODEL_PATH,
    load_model_bundle,
    predict_url_risk,
)


def tool_predict_url_risk(
    url: str,
    model_path: Path | None = None,
) -> dict[str, Any]:
    """Executa a inferência local do bundle do Sprint 1.

    ``url`` é usado somente como texto para extração de features. O modelo
    nunca faz requisição, resolve DNS ou abre o endereço.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A URL deve ser um texto não vazio.")

    selected_path = model_path or Path(
        os.getenv("GUARDIAO_MODEL_PATH", str(DEFAULT_MODEL_PATH))
    )
    if not selected_path.is_absolute():
        selected_path = (Path.cwd() / selected_path).resolve()

    bundle = load_model_bundle(selected_path)
    prediction = predict_url_risk(url, bundle)
    return {
        "tool": "tool_predict_url_risk",
        "url": url,
        "prediction": prediction,
        "model_path": str(selected_path),
        "network_accessed": False,
    }


def tool_query_duckdb_stats(query_name: str) -> dict[str, Any]:
    """Executa apenas uma das consultas nomeadas e aprovadas do DuckDB.

    O agente fornece um identificador presente em ``QUERY_DEFINITIONS``; ele
    nunca fornece SQL. A conexão usada por ``run_named_query`` é read-only.
    """
    if query_name not in QUERY_DEFINITIONS:
        allowed = ", ".join(sorted(QUERY_DEFINITIONS))
        raise ValueError(f"Consulta não permitida: {query_name!r}. Use: {allowed}")

    columns, rows = run_named_query(query_name)
    return {
        "tool": "tool_query_duckdb_stats",
        "query_name": query_name,
        "question": QUERY_DEFINITIONS[query_name]["question"],
        "columns": columns,
        "rows": rows,
        "formatted_answer": format_query_answer(query_name, rows),
        "read_only": True,
    }
