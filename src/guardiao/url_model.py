"""Inferência local do modelo de risco de URLs, sem acesso à rede."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import joblib
import numpy as np
import pandas as pd

from guardiao.url_analysis import normalize_for_parsing


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "data" / "models" / "url_risk_model.joblib"

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


def _is_ip_address(hostname: str) -> int:
    try:
        ipaddress.ip_address(hostname.strip("[]"))
        return 1
    except ValueError:
        return 0


def extract_model_features(url: str) -> dict[str, int | float]:
    """Extrai as mesmas 25 features usadas no treinamento."""
    normalized = normalize_for_parsing(url)
    parsed = urlsplit(normalized if "://" in normalized else f"//{normalized}")
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Não foi possível identificar o domínio da URL.")

    length = len(normalized)
    letters = sum(char.isalpha() for char in normalized)
    digits = sum(char.isdigit() for char in normalized)
    special = sum(not char.isalnum() for char in normalized)
    encoded = len(PERCENT_ENCODED.findall(normalized))
    labels = [part for part in hostname.split(".") if part]
    tld = "" if _is_ip_address(hostname) else (labels[-1] if labels else "")
    tokens = {token.lower() for token in WORD_TOKEN.findall(normalized)}

    return {
        "url_length": length,
        "hostname_length": len(hostname),
        "is_hostname_ip": _is_ip_address(hostname),
        "tld_length": len(tld),
        "hostname_dot_count": hostname.count("."),
        "hyphen_count": normalized.count("-"),
        "at_count": normalized.count("@"),
        "equals_count": normalized.count("="),
        "question_mark_count": normalized.count("?"),
        "ampersand_count": normalized.count("&"),
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


def load_model_bundle(model_path: Path = DEFAULT_MODEL_PATH) -> dict[str, object]:
    """Carrega um bundle produzido por scripts/train_model.py."""
    if not model_path.is_file():
        raise FileNotFoundError(f"Modelo não encontrado: {model_path}")
    bundle = joblib.load(model_path)
    required = {"model", "model_name", "feature_columns", "input_adapter"}
    missing = required - bundle.keys()
    if missing:
        raise ValueError(f"Bundle do modelo incompleto; faltam: {sorted(missing)}")
    return bundle


def _model_input(features: dict[str, int | float], bundle: dict[str, object]) -> object:
    columns = [str(column) for column in bundle["feature_columns"]]
    frame = pd.DataFrame([[features[column] for column in columns]], columns=columns)
    if bundle["input_adapter"] == "for_flaml":
        return pd.DataFrame(
            frame.to_numpy(dtype=np.float64),
            columns=pd.Index(columns, dtype=object),
            index=frame.index,
        )
    return frame


def predict_url_risk(url: str, bundle: dict[str, object]) -> dict[str, object]:
    """Prediz o risco para uma URL sem abrir o endereço."""
    features = extract_model_features(url)
    model = bundle["model"]
    model_input = _model_input(features, bundle)
    prediction = int(model.predict(model_input)[0])
    probability = None
    if hasattr(model, "predict_proba"):
        probability = float(model.predict_proba(model_input)[0, 1])

    return {
        "is_phishing": prediction,
        "phishing_probability": probability,
        "model_name": bundle["model_name"],
    }


def format_model_prediction(
    result: dict[str, object], textual_signal_count: int = 0
) -> str:
    """Formata a previsão como estimativa, sem afirmar certeza."""
    score = result["phishing_probability"]
    score_text = f"{float(score):.1%}" if score is not None else "indisponível"
    if result["is_phishing"] == 1 and textual_signal_count == 0:
        conclusion = (
            "alerta estatístico inconclusivo: o modelo sinalizou risco, "
            "mas a triagem textual não encontrou sinais"
        )
    elif result["is_phishing"] == 1:
        conclusion = "sinal estatístico compatível com phishing"
    else:
        conclusion = "baixo sinal estatístico de phishing"

    return (
        "**Estimativa do modelo local**\n\n"
        f"- Resultado: **{conclusion}**\n"
        f"- Score estatístico de phishing: **{score_text}**\n"
        f"- Modelo: `{result['model_name']}`\n\n"
        "Esse score não é uma probabilidade calibrada e não representa reputação "
        "do domínio. O modelo foi treinado em uma amostra específica e pode errar "
        "em URLs legítimas, como sites conhecidos. Não confirma que a URL seja "
        "fraudulenta ou segura; confirme qualquer solicitação por um canal oficial."
    )
