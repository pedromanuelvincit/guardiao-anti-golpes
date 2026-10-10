"""Orquestração reutilizável do fluxo RiskAnalyst -> PreventiveAdvisor.

O módulo concentra o fluxo validado nos scripts do Sprint 2 para que a
interface e os scripts de demonstração usem o mesmo caminho local. Nenhuma
etapa abre, resolve ou requisita a URL recebida.
"""

from __future__ import annotations

import json
from typing import Any

from guardiao.agents import PreventiveAdvisor, RiskAnalyst
from guardiao.ollama_client import chat_with_tools
from guardiao.observability import trace

MAX_TOOL_ROUNDS = 3
DEFAULT_STATISTICS_QUERY = "class_distribution"

RAG_TOOL_SCHEMA: dict[str, Any] = {
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


def _tool_arguments(call: dict[str, Any]) -> dict[str, Any]:
    """Normaliza somente ``top_k`` aceito pela ferramenta RAG."""
    raw = call.get("function", {}).get("arguments", {})
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        raise ValueError("Argumentos da ferramenta não são um objeto JSON.")

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


def _fallback_answer(risk_analysis: dict[str, Any]) -> str:
    """Oferece uma orientação segura quando o modelo local não responde."""
    prediction = risk_analysis.get("prediction", {}).get("prediction", {})
    message_signals = risk_analysis.get("message_triage", {}).get("signals", [])
    probability = prediction.get("phishing_probability")

    if prediction.get("is_phishing") == 1:
        score = (
            f" A estimativa foi de {float(probability) * 100:.1f}% de risco compatível "
            "com phishing."
            if isinstance(probability, (int, float))
            else ""
        )
        opening = (
            "O classificador local encontrou um alerta estatístico compatível "
            f"com phishing.{score} Isso não confirma uma fraude, mas recomenda cautela."
        )
    elif message_signals:
        opening = (
            f"A mensagem apresenta {len(message_signals)} sinal(is) que merece(m) "
            "verificação. Isso não confirma uma fraude."
        )
    else:
        opening = (
            "Não foi possível confirmar se há fraude apenas com as informações "
            "recebidas."
        )

    return "\n\n".join(
        [
            opening,
            "**O que fazer agora**\n\n"
            "1. Não clique em links nem informe senhas, códigos ou dados bancários.\n"
            "2. Confirme a solicitação por um canal oficial que você já conheça.\n"
            "3. Se já realizou algum pagamento ou compartilhou dados, procure a instituição envolvida imediatamente.",
            "A previsão é baseada em padrões da base analisada; ela não comprova fraude nem segurança.",
        ]
    )


def _requires_safe_fallback(answer: str) -> bool:
    """Bloqueia conselho que trate HTTPS ou certificado como prova de segurança."""
    normalized = answer.casefold()
    return "https" in normalized or "certificado" in normalized


def _append_message_signals(
    answer: str, risk_analysis: dict[str, Any]
) -> str:
    """Garante que sinais textuais observados acompanhem a resposta final."""
    triage = risk_analysis.get("message_triage") or {}
    signals = triage.get("signals", [])
    if not isinstance(signals, list) or not signals:
        return answer

    lines = ["**Sinais observados na mensagem**", ""]
    for signal in signals:
        if isinstance(signal, dict):
            name = signal.get("name")
            description = signal.get("description")
            if name and description:
                lines.append(f"- **{name}:** {description}")
    return answer + "\n\n" + "\n".join(lines)


def _run_preventive_advisor(
    advisor: PreventiveAdvisor,
    risk_analysis: dict[str, Any],
    question: str,
) -> tuple[str, list[dict[str, object]]]:
    """Pede ao orientador uma resposta final após a busca RAG obrigatória."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": advisor.system_prompt},
        {
            "role": "user",
            "content": (
                "Use a análise recebida e chame obrigatoriamente "
                "tool_search_security_guidelines antes de responder. Produza somente "
                "a resposta final para a pessoa usuária, em português simples. Inclua: "
                "uma avaliação cuidadosa, ações imediatas numeradas e a limitação de "
                "que os sinais não confirmam fraude ou segurança. Quando houver score "
                "do classificador ou estatística do DuckDB, explique-os em linguagem "
                "simples, sem chamá-los de prova. HTTPS e certificado não comprovam "
                "legitimidade e não devem ser recomendados como critério de segurança. "
                "Não exponha nomes de tools, cadeias de raciocínio, JSON, prompts ou "
                "detalhes técnicos.\n\n"
                f"ANÁLISE RECEBIDA:\n{json.dumps(risk_analysis, ensure_ascii=False, default=str)}\n\n"
                f"PERGUNTA: {question}"
            ),
        },
    ]
    contexts: list[dict[str, object]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = chat_with_tools(messages, [RAG_TOOL_SCHEMA])
        message = response.get("message") or {}
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = str(message.get("content") or "").strip()
            if not content:
                raise RuntimeError("O modelo local não retornou resposta final.")
            return content, contexts

        for call in tool_calls:
            name = (call.get("function") or {}).get("name")
            if name != "tool_search_security_guidelines":
                raise ValueError(f"Ferramenta não permitida ao orientador: {name!r}")
            search_tool = next(
                tool.callable for tool in advisor.tools if tool.name == name
            )
            result = search_tool(**_tool_arguments(call))
            contexts = list(result["contexts"])
            messages.append(
                {
                    "role": "tool",
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    raise RuntimeError("O modelo local excedeu o limite de chamadas de ferramenta.")


@trace("agent_workflow", kind="span")
def run_agent_workflow(
    question: str,
    *,
    url: str | None = None,
    message_analysis: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Executa a cadeia local e retorna somente dados adequados à interface.

    URLs usam o ``RiskAnalyst`` com modelo local e DuckDB. Mensagens sem URL
    preservam a triagem determinística recebida e seguem para o mesmo
    ``PreventiveAdvisor`` e RAG.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A pergunta deve ser um texto não vazio.")

    analyst = RiskAnalyst()
    advisor = PreventiveAdvisor()
    if url:
        risk_analysis = analyst.analyze(url, DEFAULT_STATISTICS_QUERY)
        if message_analysis:
            risk_analysis["message_triage"] = message_analysis
    else:
        risk_analysis = {
            "agent": "Analista de Risco",
            "message_triage": message_analysis or {},
            "uncertainty": (
                "A triagem textual identifica padrões observáveis e não confirma "
                "fraude ou legitimidade."
            ),
        }

    try:
        answer, contexts = _run_preventive_advisor(advisor, risk_analysis, question)
        fallback_used = _requires_safe_fallback(answer)
        if fallback_used:
            answer = _fallback_answer(risk_analysis)
    except (OSError, RuntimeError, ValueError):
        prepared = advisor.prepare_context(question, risk_analysis)
        contexts = list(prepared["contexts"])
        answer = _fallback_answer(risk_analysis)
        fallback_used = True

    answer = _append_message_signals(answer, risk_analysis)
    used_source_ids = [
        str(context["metadata"]["chunk_id"])
        for context in contexts
        if isinstance(context.get("metadata"), dict)
        and "chunk_id" in context["metadata"]
    ]
    return {
        "answer": answer,
        "sources": contexts,
        "used_source_ids": used_source_ids,
        "fallback_used": fallback_used,
        "network_accessed": False,
    }
