"""Valida o workflow do Sprint 2 com tracing Langfuse opcional.

Sem LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY, a execução é explicitamente
no-op e não requer rede. Quando configurado, o cliente recebe os spans dos
agentes, tools e chamadas ao Ollama e é finalizado no bloco ``finally``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.observability import (
    flush_and_shutdown,
    get_observability,
    reset_observability,
    tracing_status,
)
from test_sprint2_workflow import main as run_workflow


def main() -> int:
    reset_observability()
    observability = get_observability()
    print(tracing_status())
    # O contrato de no-op é verificável sem rede e sem expor credenciais.
    if not observability.active:
        with observability.observation("observability_noop_check"):
            pass
    try:
        with observability.observation(
            "sprint3_workflow",
            kind="trace",
            input_data={"question": "O que devo fazer antes de pagar uma cobrança suspeita?"},
            metadata={"workflow": "RiskAnalyst -> PreventiveAdvisor", "network": False},
        ):
            result = run_workflow()
        return result
    finally:
        flush_and_shutdown()
        print("Langfuse flush/encerramento concluído (sem chaves exibidas).")


if __name__ == "__main__":
    raise SystemExit(main())
