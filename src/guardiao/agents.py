"""Estruturas iniciais dos papéis de agentes do Sprint 2.

Estas classes tornam explícitas as ferramentas e a passagem de contexto, mas
não fazem orquestração autônoma nem chamada ao Ollama. A integração completa
fica para uma etapa posterior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from guardiao.agent_prompts import (
    PREVENTIVE_ADVISOR_SYSTEM_PROMPT,
    RISK_ANALYST_SYSTEM_PROMPT,
    RISK_ANALYST_TO_ADVISOR_TEMPLATE,
)
from guardiao.agent_tools import tool_predict_url_risk, tool_query_duckdb_stats
from guardiao.rag import retrieve_contexts


@dataclass(frozen=True)
class ToolDefinition:
    """Descrição serializável de uma ferramenta exposta a um agente."""

    name: str
    description: str
    callable: Callable[..., dict[str, Any]]


@dataclass
class RiskAnalyst:
    """Analista que reúne previsão local e uma estatística aprovada."""

    system_prompt: str = RISK_ANALYST_SYSTEM_PROMPT
    tools: tuple[ToolDefinition, ...] = field(
        default_factory=lambda: (
            ToolDefinition(
                "tool_predict_url_risk",
                "Prevê risco usando o bundle local, sem acessar a URL.",
                tool_predict_url_risk,
            ),
            ToolDefinition(
                "tool_query_duckdb_stats",
                "Consulta uma estatística previamente aprovada em modo read-only.",
                tool_query_duckdb_stats,
            ),
        )
    )

    def analyze(self, url: str, query_name: str) -> dict[str, Any]:
        """Chama as duas tools e devolve o pacote transferível ao orientador."""
        prediction = tool_predict_url_risk(url)
        statistics = tool_query_duckdb_stats(query_name)
        return {
            "agent": "Analista de Risco",
            "prediction": prediction,
            "statistics": statistics,
            "uncertainty": (
                "A previsão é um sinal estatístico da amostra e não confirma "
                "fraude ou legitimidade."
            ),
        }


@dataclass
class PreventiveAdvisor:
    """Estrutura inicial do orientador, sem geração autônoma de resposta."""

    system_prompt: str = PREVENTIVE_ADVISOR_SYSTEM_PROMPT
    retriever: Callable[..., list[dict[str, object]]] = retrieve_contexts

    def prepare_context(
        self,
        question: str,
        risk_analysis: dict[str, Any],
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Recupera contexto e passa explicitamente a análise anterior adiante."""
        if top_k <= 0:
            raise ValueError("top_k deve ser maior que zero.")
        contexts = self.retriever(question, top_k=top_k)
        risk_text = str(risk_analysis)
        retrieved_context = "\n\n---\n\n".join(
            str(context.get("document", "")) for context in contexts
        )
        prompt = RISK_ANALYST_TO_ADVISOR_TEMPLATE.format(
            risk_analysis=risk_text,
            question=question,
            retrieved_context=retrieved_context,
        )
        return {
            "agent": "Orientador Preventivo",
            "risk_analysis": risk_analysis,
            "contexts": contexts,
            "prompt": prompt,
            "llm_called": False,
        }
