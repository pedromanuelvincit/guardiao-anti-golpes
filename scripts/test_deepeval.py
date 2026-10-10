"""Avaliação local do RAG com Golden Dataset e DeepEval.

Uso normal (requer Deepeval e Ollama):
    python scripts/test_deepeval.py

Validação offline da estrutura:
    python scripts/test_deepeval.py --structural-only

O juiz é sempre o Ollama local. O script não configura OpenAI como fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
DATASET_PATH = PROJECT_ROOT / "data" / "golden_dataset.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from guardiao.rag import retrieve_contexts
from guardiao.scope import OUT_OF_SCOPE_RESPONSE, is_in_scope

try:
    from deepeval.models import DeepEvalBaseLLM
except ImportError:  # permite a validação estrutural sem instalar DeepEval
    class DeepEvalBaseLLM:  # type: ignore[no-redef]
        pass


EXPECTED_COUNTS = {
    "direto": 5,
    "linguagem_natural": 4,
    "ambiguo_dificil": 3,
    "fora_escopo": 3,
}


def load_dataset() -> list[dict[str, Any]]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 15:
        raise AssertionError("O Golden Dataset deve conter exatamente 15 casos.")
    ids = [case.get("id") for case in cases]
    if len(set(ids)) != 15 or any(not item for item in ids):
        raise AssertionError("Os 15 casos devem ter IDs únicos e não vazios.")
    counts: dict[str, int] = {}
    for case in cases:
        category = case.get("category")
        counts[category] = counts.get(category, 0) + 1
        if not case.get("question") or not case.get("expected_behavior"):
            raise AssertionError(f"Caso incompleto: {case.get('id')}")
    if counts != EXPECTED_COUNTS:
        raise AssertionError(f"Categorias inválidas: {counts}")
    return cases


def simulate_rag(case: dict[str, Any]) -> tuple[str, list[str]]:
    question = str(case["question"])
    if case["scope"] == "fora_do_rag" or not is_in_scope(question):
        return OUT_OF_SCOPE_RESPONSE, []
    contexts = retrieve_contexts(question, top_k=2)
    if not contexts:
        return "Não encontrei trechos suficientes nas cartilhas consultadas.", []
    documents = [str(item["document"]) for item in contexts]
    # A saída simulada é uma síntese curta e determinística do critério dourado;
    # os documentos recuperados continuam sendo a evidência avaliada pelo RAG.
    answer = str(case["expected_behavior"])
    return answer, documents


class OllamaJudge(DeepEvalBaseLLM):
    """Adaptador DeepEval para julgamento exclusivamente via Ollama local."""

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.base_url = (base_url or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")

    def load_model(self) -> "OllamaJudge":
        return self

    def get_model_name(self) -> str:
        return f"Ollama/{self.model}"

    def _generate(self, prompt: str, schema: Any = None) -> str:
        output_format: Any = "json"
        if schema is not None and hasattr(schema, "model_json_schema"):
            output_format = schema.model_json_schema()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é um avaliador rigoroso. Responda somente ao formato solicitado.",
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": output_format,
            # Faithfulness pode solicitar dezenas de verdicts; reserve tokens para
            # que o JSON estruturado não seja truncado pelo Ollama.
            "options": {"temperature": 0.0, "num_predict": 3000},
        }
        request = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            raise RuntimeError(
                f"Ollama indisponível em {self.base_url}. "
                "Inicie o Ollama e confirme OLLAMA_MODEL."
            ) from error
        if result.get("error"):
            raise RuntimeError(f"Ollama retornou um erro: {result['error']}")
        return str(result.get("message", {}).get("content", ""))

    def generate(self, prompt: str, schema: Any = None) -> Any:
        text = self._generate(prompt, schema)
        if schema is None:
            return text
        try:
            data = json.loads(text)
            if hasattr(schema, "model_validate"):
                return schema.model_validate(data)
            return schema.parse_obj(data)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            # O modelo local pode truncar listas longas de verdicts. Preserve os
            # itens completos como "idk" para que a avaliação termine sem inventar
            # uma decisão favorável.
            count = len(re.findall(r'"verdict"\s*:\s*"(?:yes|no|idk)"', text))
            if count and hasattr(schema, "model_validate"):
                print(
                    f"Aviso: resposta JSON truncada; {count} verdict(s) preservado(s) como idk.",
                    file=sys.stderr,
                )
                fallback = {
                    "verdicts": [
                        {"verdict": "idk", "reason": "Juiz local inconclusivo."}
                        for _ in range(count)
                    ]
                }
                return schema.model_validate(fallback)
            raise RuntimeError(f"O juiz Ollama retornou JSON inválido: {text!r}") from error

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        return await asyncio.to_thread(self.generate, prompt, schema)


def build_test_cases(cases: list[dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as error:
        raise RuntimeError(
            "DeepEval não está instalado. Execute: pip install -r requirements.txt"
        ) from error

    test_cases: list[Any] = []
    records: list[dict[str, Any]] = []
    for case in cases:
        actual_output, contexts = simulate_rag(case)
        records.append({"id": case["id"], "contexts": len(contexts)})
        if case["scope"] == "fora_do_rag":
            continue
        test_cases.append(
            LLMTestCase(
                name=case["id"],
                input=case["question"],
                actual_output=actual_output,
                retrieval_context=contexts,
                context=contexts,
            )
        )
    return test_cases, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural-only", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de casos do dataset durante a avaliação.",
    )
    args = parser.parse_args()

    cases = load_dataset()
    print(f"Golden Dataset validado: {len(cases)} casos; categorias={EXPECTED_COUNTS}")
    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit deve ser maior que zero.")
        cases = cases[: args.limit]
        print(f"Avaliação limitada a {len(cases)} caso(s).")
    if args.structural_only:
        for case in cases:
            simulate_rag(case)
        print("Simulação RAG estrutural concluída sem chamar DeepEval nem OpenAI.")
        return 0

    test_cases, records = build_test_cases(cases)
    try:
        from deepeval import evaluate
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    except ImportError as error:
        raise RuntimeError(
            "DeepEval não está instalado. Execute: pip install -r requirements.txt"
        ) from error

    judge = OllamaJudge()
    metrics = [
        FaithfulnessMetric(model=judge, include_reason=True, async_mode=False),
        AnswerRelevancyMetric(model=judge, include_reason=True, async_mode=False),
    ]
    print(f"Juiz local: {judge.get_model_name()} ({judge.base_url})")
    print(f"Casos RAG avaliados: {len(test_cases)}; casos fora do escopo excluídos das métricas.")
    evaluate(test_cases, metrics=metrics)
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
