"""Valida o fluxo local RiskAnalyst -> PreventiveAdvisor.

O script chama as tools locais, tenta tool calling no Ollama local e usa um
fallback determinístico baseado somente no RAG quando o Ollama não está
acessível. Nenhuma URL é aberta ou resolvida.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.agent_tools import (
    tool_predict_url_risk,
    tool_query_duckdb_stats,
    tool_search_security_guidelines,
)
from guardiao.agents import PreventiveAdvisor, RiskAnalyst
from guardiao.ollama_client import chat_with_tools

MAX_TOOL_ROUNDS = 3
TEST_URL = "hxxps://198[.]51[.]100[.]42/login?account=teste"
QUESTION = "O que devo fazer antes de pagar uma cobrança suspeita?"

RAG_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "tool_search_security_guidelines",
        "description": "Busca trechos das cartilhas no ChromaDB local, sem rede.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["question"],
        },
    },
}


def _arguments(call: dict[str, Any]) -> dict[str, Any]:
    raw = call.get("function", {}).get("arguments", {})
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        raise ValueError("Argumentos da tool não são um objeto JSON.")
    # Alguns modelos locais serializam inteiros do schema como 2.0 ou "2".
    # Normalizamos somente esse campo antes da validação estrita da tool.
    top_k = parsed.get("top_k")
    if isinstance(top_k, float) and top_k.is_integer():
        parsed["top_k"] = int(top_k)
    elif isinstance(top_k, str):
        try:
            numeric_top_k = float(top_k)
        except ValueError:
            numeric_top_k = None
        if numeric_top_k is not None and numeric_top_k.is_integer():
            parsed["top_k"] = int(numeric_top_k)
    if isinstance(parsed.get("top_k"), int) and not isinstance(parsed["top_k"], bool):
        parsed["top_k"] = max(1, min(parsed["top_k"], 5))
    return parsed


def _fallback_answer(search_result: dict[str, Any]) -> str:
    lines = [
        "**Resposta final (fallback local; Ollama indisponível)**",
        "",
        "A orientação abaixo reproduz somente os trechos recuperados das "
        "cartilhas. O contexto recuperado é a única base deste fallback; se ele "
        "for insuficiente, a resposta deve permanecer inconclusiva.",
        "",
    ]
    for context in search_result["contexts"]:
        metadata = context["metadata"]
        lines.extend(
            [
                f"**Fonte:** {metadata.get('titulo')} — página {metadata.get('pagina')} "
                f"(chunk {metadata.get('chunk_id')})",
                str(context.get("document", "")),
                "",
            ]
        )
    return "\n".join(lines).strip()


def _try_advisor_with_ollama(
    advisor: PreventiveAdvisor,
    risk: dict[str, Any],
    question: str,
) -> tuple[str, list[str]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": advisor.system_prompt},
        {
            "role": "user",
            "content": (
                "Use a análise recebida do Analista de Risco e responda à pergunta. "
                "Chame tool_search_security_guidelines antes de responder. "
                "Não invente fontes ou recomendações.\n\n"
                f"PARECER BRUTO:\n{json.dumps(risk, ensure_ascii=False, default=str)}\n\n"
                f"PERGUNTA: {question}"
            ),
        },
    ]
    calls_seen: list[str] = []
    for _ in range(MAX_TOOL_ROUNDS):
        response = chat_with_tools(messages, [RAG_TOOL_SCHEMA])
        message = response.get("message") or {}
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = str(message.get("content") or "").strip()
            if not content:
                raise RuntimeError("Ollama não retornou resposta final.")
            return content, calls_seen
        for call in tool_calls:
            name = (call.get("function") or {}).get("name")
            if name != "tool_search_security_guidelines":
                raise ValueError(f"Tool não permitida ao orientador: {name!r}")
            search_tool = next(
                tool.callable for tool in advisor.tools if tool.name == name
            )
            arguments = _arguments(call)
            try:
                result = search_tool(**arguments)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Falha na tool {name} com argumentos {arguments!r}: {error}"
                ) from error
            calls_seen.append(name)
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    raise RuntimeError("Ollama excedeu o limite de rodadas de tool calling.")


def main() -> int:
    analyst = RiskAnalyst()
    advisor = PreventiveAdvisor()

    # Validação explícita das três tools locais antes do fluxo entre papéis.
    prediction = tool_predict_url_risk(TEST_URL)
    statistics = tool_query_duckdb_stats("class_distribution")
    search = tool_search_security_guidelines(QUESTION, top_k=2)
    assert prediction["network_accessed"] is False
    assert statistics["read_only"] is True
    assert search["network_accessed"] is False
    assert {tool.name for tool in advisor.tools} == {"tool_search_security_guidelines"}

    risk = analyst.analyze(TEST_URL, "class_distribution")
    print("PARECER BRUTO DO RISKANALYST:")
    print(json.dumps(risk, ensure_ascii=False, default=str))
    print("\nBUSCA RAG LOCAL:")
    print(json.dumps(search, ensure_ascii=False, default=str))

    try:
        final, calls = _try_advisor_with_ollama(advisor, risk, QUESTION)
        print("\nRESPOSTA FINAL AO USUÁRIO (OLLAMA):")
        print(final)
        print(f"Tools do Orientador chamadas: {', '.join(calls)}")
    except (OSError, RuntimeError, ValueError) as error:
        print(f"\nFALLBACK CLARO: Ollama indisponível ou inválido: {error}")
        print(_fallback_answer(search))

    print("\nWorkflow Sprint 2 validado: tools locais, passagem RiskAnalyst -> PreventiveAdvisor e RAG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
