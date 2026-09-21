"""Consultas controladas aos dados estruturados do Guardião."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "guardiao.duckdb"
DATABASE_PATH = Path(os.getenv("DUCKDB_PATH", str(DEFAULT_DATABASE_PATH)))

CLASS_DISTRIBUTION_SQL = """
SELECT
    label_name AS classe,
    COUNT(*) AS quantidade,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentual
FROM urls
GROUP BY label_name
ORDER BY label_name
"""

CLASS_PROFILE_SQL = """
SELECT
    u.label_name AS classe,
    COUNT(*) AS quantidade,
    ROUND(AVG(f.url_length), 2) AS comprimento_medio,
    ROUND(100.0 * AVG(f.uses_https), 2) AS percentual_https
FROM urls AS u
INNER JOIN url_features AS f USING (url_id)
GROUP BY u.label_name
ORDER BY u.label_name
"""

QUERY_DEFINITIONS = {
    "class_distribution": {
        "question": "Quantas URLs são phishing e quantas são legítimas?",
        "sql": CLASS_DISTRIBUTION_SQL,
    },
    "class_profile": {
        "question": (
            "Qual é o comprimento médio das URLs e qual percentual usa HTTPS "
            "em cada classe?"
        ),
        "sql": CLASS_PROFILE_SQL,
    },
}


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def detect_data_intent(question: str) -> str | None:
    """Reconhece variações naturais das duas consultas oficiais."""
    words = set(_normalize(question).split())

    entity_terms = {"url", "urls", "link", "links", "site", "sites", "endereco"}
    profile_terms = {
        "comprimento", "tamanho", "media", "medio", "https", "percentual",
        "protocolo",
    }
    distribution_terms = {
        "quantas", "quantos", "quantidade", "total", "distribuicao",
        "proporcao",
    }
    class_terms = {
        "phishing", "legitima", "legitimas", "legitimo", "legitimos",
        "golpe", "golpes", "maliciosa", "maliciosas", "segura", "seguras",
    }

    mentions_entity = bool(words & entity_terms)
    if mentions_entity and words & profile_terms:
        return "class_profile"
    if mentions_entity and words & distribution_terms and words & class_terms:
        return "class_distribution"
    return None


def run_named_query(name: str) -> tuple[list[str], list[tuple[object, ...]]]:
    """Executa somente uma consulta previamente aprovada em modo somente leitura."""
    if name not in QUERY_DEFINITIONS:
        raise ValueError(f"Consulta não permitida: {name}")
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Banco DuckDB não encontrado em {DATABASE_PATH}")

    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        result = connection.execute(str(QUERY_DEFINITIONS[name]["sql"]))
        columns = [description[0] for description in result.description]
        rows = result.fetchall()
    return columns, rows


def _format_integer(value: object) -> str:
    return f"{int(value):,}".replace(",", ".")


def _format_decimal(value: object) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def format_query_answer(name: str, rows: list[tuple[object, ...]]) -> str:
    """Transforma os resultados aprovados em uma resposta legível."""
    by_class = {str(row[0]): row for row in rows}
    legitimate = by_class["legitima"]
    phishing = by_class["phishing"]

    if name == "class_distribution":
        return (
            "Na base analisada existem:\n\n"
            f"- **{_format_integer(legitimate[1])} URLs legítimas** "
            f"({_format_decimal(legitimate[2])}%);\n"
            f"- **{_format_integer(phishing[1])} URLs de phishing** "
            f"({_format_decimal(phishing[2])}%).\n\n"
            "Os valores consideram as URLs únicas após a remoção de duplicatas."
        )

    if name == "class_profile":
        return (
            "Comparação das características na base analisada:\n\n"
            "| Classe | URLs | Comprimento médio | Usa HTTPS |\n"
            "|---|---:|---:|---:|\n"
            f"| Legítima | {_format_integer(legitimate[1])} | "
            f"{_format_decimal(legitimate[2])} | "
            f"{_format_decimal(legitimate[3])}% |\n"
            f"| Phishing | {_format_integer(phishing[1])} | "
            f"{_format_decimal(phishing[2])} | "
            f"{_format_decimal(phishing[3])}% |\n\n"
            "Esses padrões descrevem somente esta amostra. O uso de HTTPS, "
            "isoladamente, não garante que uma URL seja legítima."
        )

    raise ValueError(f"Não existe formatador para a consulta: {name}")
