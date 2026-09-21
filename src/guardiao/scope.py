"""Delimitação determinística do escopo documental do Guardião."""

from __future__ import annotations

import re
import unicodedata


DOMAIN_TERMS = {
    "aplicativo",
    "audio",
    "banco",
    "boleto",
    "cartao",
    "conta",
    "deepfake",
    "dinheiro",
    "emprestimo",
    "fraude",
    "fraudador",
    "golpe",
    "golpista",
    "inteligencia artificial",
    "link",
    "malware",
    "mensagem",
    "pagamento",
    "perfil falso",
    "pix",
    "qr code",
    "senha",
    "site falso",
    "transferencia",
    "video",
    "whatsapp",
}

OUT_OF_SCOPE_RESPONSE = (
    "Não consigo responder a essa pergunta com base nas cartilhas consultadas. "
    "Elas tratam de prevenção e reação a golpes digitais, mas não contêm a "
    "informação solicitada. Consulte uma fonte oficial relacionada ao assunto."
)


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(re.findall(r"[a-z0-9]+", normalized))


def is_in_scope(question: str) -> bool:
    """Confirma se a pergunta contém ao menos um conceito do domínio."""
    normalized_question = f" {_normalize(question)} "
    return any(
        f" {_normalize(term)} " in normalized_question
        for term in DOMAIN_TERMS
    )
