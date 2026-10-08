"""Teste focado da estrutura de ferramentas e papéis do Sprint 2."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.agent_tools import tool_predict_url_risk, tool_query_duckdb_stats
from guardiao.agents import PreventiveAdvisor, RiskAnalyst


def main() -> None:
    prediction = tool_predict_url_risk(
        "hxxp://192[.]0[.]2[.]10/login?account=teste"
    )
    assert prediction["tool"] == "tool_predict_url_risk"
    assert prediction["network_accessed"] is False
    assert prediction["prediction"]["is_phishing"] in {0, 1}

    statistics = tool_query_duckdb_stats("class_distribution")
    assert statistics["read_only"] is True
    assert statistics["query_name"] == "class_distribution"
    assert statistics["rows"]

    analyst = RiskAnalyst()
    assert {tool.name for tool in analyst.tools} == {
        "tool_predict_url_risk",
        "tool_query_duckdb_stats",
    }
    risk = analyst.analyze(
        "hxxp://192[.]0[.]2[.]10/login?account=teste",
        "class_distribution",
    )
    assert risk["agent"] == "Analista de Risco"
    assert risk["prediction"]["tool"] == "tool_predict_url_risk"
    assert risk["statistics"]["read_only"] is True

    seen: dict[str, object] = {}

    def fake_retriever(question: str, top_k: int) -> list[dict[str, object]]:
        seen.update(question=question, top_k=top_k)
        return [{"document": "Confirme a solicitação por canal oficial."}]

    prepared = PreventiveAdvisor(retriever=fake_retriever).prepare_context(
        "O que devo fazer antes de pagar?", risk, top_k=1
    )
    assert prepared["risk_analysis"] is risk
    assert "Confirme a solicitação por canal oficial." in prepared["prompt"]
    assert seen == {"question": "O que devo fazer antes de pagar?", "top_k": 1}
    print("Estrutura Sprint 2 validada: tools locais, DuckDB controlado e passagem de contexto.")


if __name__ == "__main__":
    main()
