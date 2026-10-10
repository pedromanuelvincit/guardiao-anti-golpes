"""Teste funcional do RiskAnalyst com tool calling no Ollama local.

Este script não abre a URL de teste. Ela é neutralizada e enviada apenas ao
extrator de features local. A execução é limitada a três rodadas de tools.
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

from guardiao.agent_tools import tool_predict_url_risk, tool_query_duckdb_stats
from guardiao.agents import RiskAnalyst
from guardiao.ollama_client import DEFAULT_MODEL, chat_with_tools

MAX_TOOL_ROUNDS = 3
TEST_URL = "hxxps://198[.]51[.]100[.]42/login?account=teste"

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "tool_predict_url_risk",
            "description": (
                "Classifica localmente o risco de phishing da URL fornecida "
                "sem abrir, resolver ou requisitar o endereço."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL neutralizada."}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_query_duckdb_stats",
            "description": "Consulta uma estatística aprovada no DuckDB read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_name": {
                        "type": "string",
                        "enum": ["class_distribution", "class_profile"],
                    }
                },
                "required": ["query_name"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "tool_predict_url_risk": tool_predict_url_risk,
    "tool_query_duckdb_stats": tool_query_duckdb_stats,
}


def _arguments(call: dict[str, Any]) -> dict[str, Any]:
    raw = call.get("function", {}).get("arguments", {})
    if isinstance(raw, str):
        parsed = json.loads(raw)
    else:
        parsed = raw
    if not isinstance(parsed, dict):
        raise ValueError("Os argumentos da tool não são um objeto JSON.")
    return parsed


def main() -> int:
    analyst = RiskAnalyst()
    user_prompt = (
        "Analise a URL neutralizada abaixo. Chame obrigatoriamente as duas "
        "tools disponíveis: faça a previsão local e consulte class_distribution "
        "ou class_profile no DuckDB. Depois entregue um parecer bruto, curto, "
        "com evidências, incertezas e ações seguras. Não abra a URL.\n\n"
        f"URL de teste: {TEST_URL}"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": analyst.system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    calls_seen: list[str] = []

    print(f"Modelo Ollama: {DEFAULT_MODEL}")
    print(f"URL neutralizada enviada ao RiskAnalyst: {TEST_URL}")

    try:
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            response = chat_with_tools(messages, TOOL_SCHEMAS)
            message = response.get("message") or {}
            messages.append(message)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                print("\nPARECER BRUTO DO RISKANALYST:")
                print(message.get("content") or "(Ollama não retornou conteúdo.)")
                print(f"\nRodadas de tool calling: {round_number}")
                print(f"Tools chamadas: {', '.join(calls_seen) or 'nenhuma'}")
                return 0

            for call in tool_calls:
                function = call.get("function") or {}
                name = function.get("name")
                print(f"\nCHAMADA DE TOOL (rodada {round_number}): {name}")
                try:
                    arguments = _arguments(call)
                    print(f"Argumentos: {json.dumps(arguments, ensure_ascii=False)}")
                    if name not in TOOL_FUNCTIONS:
                        raise ValueError(f"Tool não permitida: {name!r}")
                    result = TOOL_FUNCTIONS[name](**arguments)
                    calls_seen.append(str(name))
                    print(f"Resultado: {json.dumps(result, ensure_ascii=False, default=str)}")
                except Exception as error:  # envia erro controlado para o parecer
                    result = {"error": f"Falha controlada na tool {name}: {error}"}
                    print(f"ERRO CONTROLADO: {result['error']}")

                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        print("\nERRO: o Ollama excedeu o limite de rodadas de tool calling.")
        return 1
    except RuntimeError as error:
        print(f"\nFALLBACK: Ollama indisponível ou sem resposta válida: {error}")
        print("Execute `ollama serve` e confirme que o modelo local está instalado.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
