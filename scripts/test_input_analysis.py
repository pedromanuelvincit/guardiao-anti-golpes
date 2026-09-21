"""Valida as rotas locais de análise de mensagem e URL."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.message_analysis import analyze_message, format_message_analysis
from guardiao.url_analysis import analyze_url, format_url_analysis


SUSPICIOUS_EXAMPLE = (
    "URGENTE: seu boleto do MEI vence hoje. Faça o pagamento agora em "
    "hxxp://192[.]0[.]2[.]10/login?account=teste&confirm=1"
)
NEUTRAL_EXAMPLE = "A reunião foi remarcada para terça-feira às 14 horas."
BANK_EXAMPLE = (
    "ATENÇÃO: Sua conta no Banco Nubank possui uma pendência cadastral. "
    "Evite o bloqueio pagando a taxa até hoje em "
    "hxxp://198[.]51[.]100[.]45/verify?user=admin&status=pending"
)
MARKDOWN_EXAMPLE = (
    "INFORMAÇÃO: Para entender o passo a passo de como emitir a guia do MEI, "
    "assista ao tutorial em "
    "[https://www.youtube.com/watch?v=abcdef12345]"
    "(https://www.youtube.com/watch?v=abcdef12345) Analise esta mensagem"
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=== MENSAGEM COM SINAIS ===")
    suspicious = analyze_message(SUSPICIOUS_EXAMPLE)
    print(format_message_analysis(suspicious))

    print("\n=== URL ENCONTRADA NA MENSAGEM ===")
    print(format_url_analysis(analyze_url(str(suspicious["url"]))))

    print("\n=== MENSAGEM SEM SINAIS DETECTADOS ===")
    print(format_message_analysis(analyze_message(NEUTRAL_EXAMPLE)))

    print("\n=== AMEACA DE BLOQUEIO E PAGAMENTO ===")
    bank_result = analyze_message(BANK_EXAMPLE)
    if bank_result["url"] != (
        "hxxp://198[.]51[.]100[.]45/verify?user=admin&status=pending"
    ):
        raise AssertionError(
            f"URL neutralizada extraída incorretamente: {bank_result['url']}"
        )
    bank_labels = {signal["name"] for signal in bank_result["signals"]}
    expected_labels = {
        "Pressa ou urgência",
        "Ameaça ou consequência negativa",
        "Pedido de pagamento",
        "Uso de autoridade",
        "Link ou chamada para clicar",
    }
    if not expected_labels.issubset(bank_labels):
        raise AssertionError(
            "Sinais esperados ausentes: "
            + ", ".join(sorted(expected_labels - bank_labels))
        )
    print(format_message_analysis(bank_result))
    print(format_url_analysis(analyze_url(str(bank_result["url"]))))

    from guardiao.message_analysis import extract_message_candidate

    markdown_message = extract_message_candidate(MARKDOWN_EXAMPLE)
    if not markdown_message:
        raise AssertionError("Mensagem com instrução no final não foi reconhecida.")
    markdown_result = analyze_message(markdown_message)
    if markdown_result["url"] != "https://www.youtube.com/watch?v=abcdef12345":
        raise AssertionError(
            f"URL em Markdown extraída incorretamente: {markdown_result['url']}"
        )
    print("\n=== PEDIDO DE ANALISE NO FINAL E URL EM MARKDOWN ===")
    print(format_message_analysis(markdown_result))
    print(format_url_analysis(analyze_url(str(markdown_result["url"]))))


if __name__ == "__main__":
    main()
