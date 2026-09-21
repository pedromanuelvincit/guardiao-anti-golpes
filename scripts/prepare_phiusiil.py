"""Prepara duas tabelas seguras e relacionadas a partir do PhiUSIIL.

O script nunca acessa as URLs. Todos os atributos são calculados localmente a
partir do texto do endereço. As URLs exportadas são neutralizadas para reduzir
o risco de clique acidental.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pandas as pd


SOURCE_NAME = "UCI PhiUSIIL Phishing URL (Website)"
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


def parse_url_text(url: str) -> tuple[str, object]:
    """Extrai hostname e partes da URL sem realizar requisição de rede."""
    candidate = url.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    return (parsed.hostname or "").lower(), parsed


def is_ip_address(hostname: str) -> int:
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return 1
    except ValueError:
        return 0


def redact_url_details(value: str) -> str:
    """Remove valores de query e fragmento antes do armazenamento público."""
    without_fragment, separator, _ = value.partition("#")
    fragment_marker = "#[fragment-redacted]" if separator else ""
    without_query, separator, _ = without_fragment.partition("?")
    query_marker = "?[query-redacted]" if separator else ""
    return without_query + query_marker + fragment_marker


def neutralize(value: str) -> str:
    """Redige detalhes, impede cliques e evita fórmulas em planilhas."""
    safe = (
        redact_url_details(value)
        .replace("\r", r"\r")
        .replace("\n", r"\n")
        .replace("\t", r"\t")
        .replace("https://", "hxxps://")
        .replace("http://", "hxxp://")
        .replace(".", "[.]")
    )
    if safe.startswith(("=", "+", "-", "@")):
        safe = "'" + safe
    return safe


def extract_features(url: str) -> dict[str, int | float]:
    hostname, parsed = parse_url_text(url)
    length = len(url)
    letters = sum(char.isalpha() for char in url)
    digits = sum(char.isdigit() for char in url)
    special = sum(not char.isalnum() for char in url)
    encoded = len(PERCENT_ENCODED.findall(url))
    labels = [part for part in hostname.split(".") if part]
    tld = "" if is_ip_address(hostname) else (labels[-1] if labels else "")
    tokens = {token.lower() for token in WORD_TOKEN.findall(url)}

    return {
        "url_length": length,
        "hostname_length": len(hostname),
        "is_hostname_ip": is_ip_address(hostname),
        "tld_length": len(tld),
        "hostname_dot_count": hostname.count("."),
        "hyphen_count": url.count("-"),
        "at_count": url.count("@"),
        "equals_count": url.count("="),
        "question_mark_count": url.count("?"),
        "ampersand_count": url.count("&"),
        "letter_count": letters,
        "letter_ratio": round(letters / length, 6) if length else 0.0,
        "digit_count": digits,
        "digit_ratio": round(digits / length, 6) if length else 0.0,
        "special_char_count": special,
        "special_char_ratio": round(special / length, 6) if length else 0.0,
        "encoded_char_count": encoded,
        "has_obfuscation": int(encoded > 0),
        "uses_https": int(parsed.scheme.lower() == "https"),
        "path_length": len(parsed.path),
        "path_depth": len([part for part in parsed.path.split("/") if part]),
        "query_length": len(parsed.query),
        "query_param_count": len(parse_qsl(parsed.query, keep_blank_values=True)),
        "fragment_length": len(parsed.fragment),
        "suspicious_word_count": len(tokens & SUSPICIOUS_WORDS),
    }


def load_source(archive_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(archive_path) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Esperado um CSV no ZIP; encontrados: {csv_names}")
        with archive.open(csv_names[0]) as stream:
            frame = pd.read_csv(stream, usecols=["URL", "label"])

    if frame.isna().any().any():
        raise ValueError("O arquivo contém valores ausentes em URL ou label.")
    if not set(frame["label"].unique()).issubset({0, 1}):
        raise ValueError("Foram encontrados rótulos diferentes de 0 e 1.")
    return frame


def build_tables(source: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    conflicts = source.groupby("URL")["label"].nunique().gt(1)
    if conflicts.any():
        raise ValueError(f"Há {int(conflicts.sum())} URLs com rótulos conflitantes.")

    original_rows = len(source)
    deduplicated = source.drop_duplicates(subset=["URL"], keep="first").reset_index(drop=True)
    deduplicated.insert(0, "url_id", range(1, len(deduplicated) + 1))

    records: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    parse_failures = 0

    for row in deduplicated.itertuples(index=False):
        url = str(row.URL)
        hostname, _ = parse_url_text(url)
        if not hostname:
            parse_failures += 1
        host_labels = [part for part in hostname.split(".") if part]
        tld = "" if is_ip_address(hostname) else (host_labels[-1] if host_labels else "")

        records.append(
            {
                "url_id": row.url_id,
                "url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest(),
                "url_masked": neutralize(url),
                "domain_masked": neutralize(hostname),
                "tld": tld or "sem_tld",
                "label": int(row.label),
                "label_name": "legitima" if int(row.label) == 1 else "phishing",
                "source": SOURCE_NAME,
            }
        )
        features.append({"url_id": row.url_id, **extract_features(url)})

    stats = {
        "original_rows": original_rows,
        "deduplicated_rows": len(deduplicated),
        "duplicates_removed": original_rows - len(deduplicated),
        "parse_failures": parse_failures,
    }
    return pd.DataFrame(records), pd.DataFrame(features), stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="ZIP oficial da UCI")
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    source = load_source(args.input)
    urls, url_features, stats = build_tables(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    urls_path = args.output_dir / "urls.csv"
    features_path = args.output_dir / "url_features.csv"
    urls.to_csv(urls_path, index=False, encoding="utf-8")
    url_features.to_csv(features_path, index=False, encoding="utf-8")

    print(stats)
    print(f"urls={urls_path} rows={len(urls)}")
    print(f"url_features={features_path} rows={len(url_features)}")


if __name__ == "__main__":
    main()
