"""Triagem local de sinais textuais em URLs, sem acesso à rede."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


SUSPICIOUS_WORDS = {
    "account",
    "atualizacao",
    "bank",
    "banking",
    "boleto",
    "confirm",
    "credential",
    "invoice",
    "login",
    "mei",
    "password",
    "payment",
    "pix",
    "secure",
    "security",
    "signin",
    "update",
    "verification",
    "verify",
}
PERCENT_ENCODED = re.compile(r"%[0-9a-fA-F]{2}")
WORD_TOKEN = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")
URL_BODY = r"(?:\[\.\]|[^\s<>\"'\[\]\(\)])+"
URL_PATTERN = re.compile(
    rf"(?:hxxps?://|https?://|www\.){URL_BODY}|"
    r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}"
    r"(?:/[^\s<>\"'\[\]\(\)]*)?"
)


def extract_url_candidate(text: str) -> str | None:
    """Localiza uma URL em uma pergunta sem abrir o endereço."""
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?)]}")


def normalize_for_parsing(url: str) -> str:
    """Restaura neutralizações apenas em memória para analisar a estrutura."""
    return (
        url.strip()
        .replace("hxxps://", "https://")
        .replace("hxxp://", "http://")
        .replace("[.]", ".")
    )


def neutralize(url: str) -> str:
    """Evita que o endereço apresentado se torne clicável."""
    return (
        url.replace("https://", "hxxps://")
        .replace("http://", "hxxp://")
        .replace(".", "[.]")
    )


def _is_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return True
    except ValueError:
        return False


def analyze_url(url: str) -> dict[str, object]:
    """Retorna sinais observáveis no texto da URL sem classificá-la."""
    normalized = normalize_for_parsing(url)
    parsed = urlsplit(normalized if "://" in normalized else f"//{normalized}")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Não foi possível identificar o domínio da URL.")

    tokens = {token.lower() for token in WORD_TOKEN.findall(normalized)}
    suspicious_terms = sorted(tokens & SUSPICIOUS_WORDS)
    signals: list[str] = []

    hostname_is_ip = _is_ip_address(hostname)
    if hostname_is_ip:
        signals.append("O domínio está representado por um endereço IP.")
    if parsed.scheme.lower() != "https":
        signals.append("A URL não informa o uso de HTTPS.")
    if "@" in normalized:
        signals.append("A URL contém o caractere @, que pode ocultar o destino real.")
    if PERCENT_ENCODED.search(normalized):
        signals.append("A URL contém caracteres codificados, o que dificulta a leitura.")
    if suspicious_terms:
        signals.append(
            "Foram encontrados termos frequentemente usados em páginas de "
            "autenticação ou pagamento: " + ", ".join(suspicious_terms) + "."
        )
    if not hostname_is_ip and hostname.count(".") >= 3:
        signals.append("O domínio contém vários níveis de subdomínio.")
    if len(normalized) >= 100:
        signals.append("A URL é longa e merece conferência cuidadosa.")

    return {
        "url_neutralized": neutralize(normalized),
        "hostname_neutralized": neutralize(hostname),
        "length": len(normalized),
        "uses_https": parsed.scheme.lower() == "https",
        "signals": signals,
    }


def format_url_analysis(result: dict[str, object]) -> str:
    """Apresenta a triagem sem afirmar que a URL é segura ou maliciosa."""
    signals = list(result["signals"])
    lines = [
        "**Triagem local da URL**",
        "",
        f"- URL neutralizada: `{result['url_neutralized']}`",
        f"- Domínio: `{result['hostname_neutralized']}`",
        f"- Comprimento: {result['length']} caracteres",
        "",
    ]

    if signals:
        lines.append("**Sinais que merecem verificação:**")
        lines.append("")
        lines.extend(
            f"{index}. {signal}" for index, signal in enumerate(signals, start=1)
        )
    else:
        lines.append(
            "Nenhum dos sinais textuais verificados foi encontrado. Isso não "
            "comprova que o endereço seja seguro."
        )

    lines.extend(
        [
            "",
            "A análise usa somente o texto informado e não abre o endereço. "
            "Confirme o domínio por um canal oficial antes de acessar ou inserir dados.",
        ]
    )
    return "\n".join(lines)
