"""Valida a extração de features e a inferência local do modelo salvo."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.url_model import (
    DEFAULT_MODEL_PATH,
    extract_model_features,
    load_model_bundle,
    predict_url_risk,
)


def main() -> None:
    url = "hxxp://192[.]0[.]2[.]10/login?account=teste&confirm=1"
    features = extract_model_features(url)
    assert len(features) == 25
    assert features["is_hostname_ip"] == 1
    assert features["uses_https"] == 0

    bundle = load_model_bundle(DEFAULT_MODEL_PATH)
    result = predict_url_risk(url, bundle)
    assert result["is_phishing"] in {0, 1}
    assert result["model_name"]
    print("Inferência local validada: 25 features e previsão sem acesso à rede.")


if __name__ == "__main__":
    main()
