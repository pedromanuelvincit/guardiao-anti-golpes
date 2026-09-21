"""Demonstra a triagem local de uma URL sem realizar acesso à rede."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.url_analysis import analyze_url, format_url_analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="hxxp://192[.]0[.]2[.]10/login?account=teste&confirm=1",
        help="URL a analisar somente como texto.",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print(format_url_analysis(analyze_url(args.url)))


if __name__ == "__main__":
    main()
