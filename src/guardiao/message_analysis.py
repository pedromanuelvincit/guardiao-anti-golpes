"""Triagem local de sinais observáveis em mensagens suspeitas."""

from __future__ import annotations

import re
import unicodedata

from guardiao.url_analysis import extract_url_candidate


MESSAGE_REQUEST_PATTERNS = [
    re.compile(
        r"(?:analise|analisa|avalie|verifique|recebi)\s+"
        r"(?:esta|essa|a)?\s*mensagem\s*[:\-]\s*(.+)",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"mensagem\s+(?:suspeita\s+)?(?:para\s+analisar)?\s*[:\-]\s*(.+)",
        flags=re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(.+?)\s+(?:analise|analisa|avalie|verifique)\s+"
        r"(?:esta|essa|a)?\s*mensagem\s*[.!?]*\s*$",
        flags=re.IGNORECASE | re.DOTALL,
    ),
]

SIGNAL_RULES = [
    (
        "Pressa ou urgência",
        r"\b(urgente|agora|imediatamente|hoje|ultima chance|prazo|vence)\b",
        "A mensagem tenta acelerar uma decisão.",
    ),
    (
        "Ameaça ou consequência negativa",
        r"\b(bloquead\w*|bloqueio|suspend\w*|cancelad\w*|multa|penalidade|"
        r"negativad\w*|pendencia)\b",
        "A mensagem usa medo de bloqueio, perda ou punição.",
    ),
    (
        "Pedido de pagamento",
        r"\b(pix|boleto|pague|pagar|pagando|pagamento|taxa|cobranca|"
        r"transfer\w*|deposit\w*)\b",
        "A mensagem solicita dinheiro ou uma ação financeira.",
    ),
    (
        "Pedido de dado sensível",
        r"\b(senha|codigo|token|cpf|cartao|dados bancarios|chave pix)\b",
        "A mensagem menciona credenciais ou dados pessoais e financeiros.",
    ),
    (
        "Uso de autoridade",
        r"\b(banco|receita federal|mei|governo|policia|suporte|seguranca)\b",
        "A mensagem usa o nome de uma instituição ou função de autoridade.",
    ),
    (
        "Vantagem ou recompensa",
        r"\b(premio|ganhou|brinde|oportunidade exclusiva|dinheiro facil)\b",
        "A mensagem promete uma vantagem para estimular uma ação.",
    ),
    (
        "Pedido de segredo",
        r"\b(nao conte|segredo|sigilo|confidencial)\b",
        "A mensagem tenta impedir que a situação seja confirmada com outras pessoas.",
    ),
    (
        "Link ou chamada para clicar",
        r"\b(clique|acesse|link|site)\b|(?:hxxps?://|https?://|www\.)",
        "A mensagem direciona o usuário para um endereço externo.",
    ),
]


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    )


def extract_message_candidate(text: str) -> str | None:
    """Extrai o conteúdo após um pedido explícito de análise de mensagem."""
    for pattern in MESSAGE_REQUEST_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip().strip('"“”')
            return candidate or None
    return None


def analyze_message(message: str) -> dict[str, object]:
    """Identifica padrões observáveis sem afirmar que a mensagem é um golpe."""
    if not message.strip():
        raise ValueError("A mensagem para análise está vazia.")
    if len(message) > 5000:
        raise ValueError("A mensagem ultrapassa o limite de 5.000 caracteres.")

    normalized = _normalize(message)
    signals = [
        {"name": name, "description": description}
        for name, pattern, description in SIGNAL_RULES
        if re.search(pattern, normalized, flags=re.IGNORECASE)
    ]
    return {
        "character_count": len(message),
        "signals": signals,
        "url": extract_url_candidate(message),
    }


def format_message_analysis(result: dict[str, object]) -> str:
    """Formata a triagem e orienta uma verificação segura."""
    signals = list(result["signals"])
    lines = ["**Triagem da mensagem**", ""]

    if signals:
        lines.append("**Sinais que merecem verificação:**")
        lines.append("")
        for index, signal in enumerate(signals, start=1):
            lines.append(
                f"{index}. **{signal['name']}:** {signal['description']}"
            )
        next_action = (
            "**Antes de agir:** não use os contatos ou links fornecidos na própria "
            "mensagem. Confirme a situação por um canal oficial ou por um contato "
            "que você já conheça."
        )
    else:
        lines.append(
            "Nenhum dos padrões textuais verificados foi encontrado. Isso não "
            "comprova que a mensagem seja legítima."
        )
        next_action = (
            "Se você não reconhecer o remetente ou o motivo da mensagem, confirme "
            "a situação por um canal conhecido antes de agir."
        )

    lines.extend(
        [
            "",
            next_action,
            "",
            "A triagem identifica sinais observáveis e não confirma, isoladamente, "
            "se a mensagem é verdadeira ou fraudulenta.",
        ]
    )
    return "\n".join(lines)
