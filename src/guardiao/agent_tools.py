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
from guardiao.observability import trace
from guardiao.rag import retrieve_contexts
from guardiao.url_model import (
    DEFAULT_MODEL_PATH,
    load_model_bundle,
    predict_url_risk,
)


@trace("tool_predict_url_risk", kind="tool")
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


@trace("tool_search_security_guidelines", kind="tool")
def tool_search_security_guidelines(
    question: str,
    top_k: int = 3,
) -> dict[str, Any]:
    """Busca orientações somente no índice ChromaDB local.

    A pergunta é enviada ao índice persistido; nenhum endereço recuperado ou
    informado pelo usuário é aberto, resolvido ou requisitado.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A pergunta deve ser um texto não vazio.")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 5:
        raise ValueError("top_k deve ser um inteiro entre 1 e 5.")

    contexts = retrieve_contexts(question, top_k=top_k)
    return {
        "tool": "tool_search_security_guidelines",
        "question": question,
        "top_k": top_k,
        "contexts": contexts,
        "sources": [context["metadata"] for context in contexts],
        "network_accessed": False,
    }


@trace("tool_query_duckdb_stats", kind="tool")
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
