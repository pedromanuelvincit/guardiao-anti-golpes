"""Executa as duas consultas estruturadas oficiais diretamente no DuckDB."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.data_queries import QUERY_DEFINITIONS, run_named_query


def configure_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def print_table(columns: list[str], rows: list[tuple[object, ...]]) -> None:
    widths = [len(column) for column in columns]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(str(value)))

    def format_row(values: tuple[object, ...] | list[str]) -> str:
        return " | ".join(
            str(value).ljust(widths[index])
            for index, value in enumerate(values)
        )

    print(format_row(columns))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(format_row(row))


def main() -> None:
    configure_console()
    for number, (name, definition) in enumerate(
        QUERY_DEFINITIONS.items(), start=1
    ):
        print(f"\nConsulta {number}: {definition['question']}")
        print("SQL executado:")
        print(str(definition["sql"]).strip())
        print("\nResultado:")
        columns, rows = run_named_query(name)
        print_table(columns, rows)


if __name__ == "__main__":
    main()
