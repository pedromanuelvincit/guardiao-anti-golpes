"""Cria e valida o banco DuckDB a partir dos dois CSVs processados."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URLS = PROJECT_ROOT / "data" / "processed" / "urls.csv"
DEFAULT_FEATURES = PROJECT_ROOT / "data" / "processed" / "url_features.csv"
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "guardiao.duckdb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria o DuckDB do Guardião a partir dos CSVs processados."
    )
    parser.add_argument("--urls", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def validate_input(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {resolved}")
    return resolved


def build_database(urls_path: Path, features_path: Path, database_path: Path) -> dict:
    urls_path = validate_input(urls_path)
    features_path = validate_input(features_path)
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(database_path)) as connection:
        connection.execute(
            "CREATE OR REPLACE TABLE urls AS "
            "SELECT * FROM read_csv_auto(?, header=true)",
            [str(urls_path)],
        )
        connection.execute(
            "CREATE OR REPLACE TABLE url_features AS "
            "SELECT * FROM read_csv_auto(?, header=true)",
            [str(features_path)],
        )

        stats = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM urls) AS urls_count,
                (SELECT COUNT(*) FROM url_features) AS features_count,
                (SELECT COUNT(DISTINCT url_id) FROM urls) AS unique_urls,
                (SELECT COUNT(DISTINCT url_id) FROM url_features) AS unique_features,
                (SELECT COUNT(*) FROM urls AS u
                 LEFT JOIN url_features AS f USING (url_id)
                 WHERE f.url_id IS NULL) AS urls_without_features,
                (SELECT COUNT(*) FROM url_features AS f
                 LEFT JOIN urls AS u USING (url_id)
                 WHERE u.url_id IS NULL) AS features_without_urls
            """
        ).fetchone()

        if not stats:
            raise RuntimeError("Não foi possível validar as tabelas carregadas.")
        urls_count, features_count, unique_urls, unique_features, left_gap, right_gap = stats
        if (
            urls_count == 0
            or urls_count != features_count
            or urls_count != unique_urls
            or features_count != unique_features
            or left_gap != 0
            or right_gap != 0
        ):
            raise ValueError(
                "A relação um para um por url_id não foi confirmada: "
                f"urls={urls_count}, features={features_count}, "
                f"urls_sem_features={left_gap}, features_sem_urls={right_gap}."
            )

        connection.execute(
            """
            CREATE OR REPLACE VIEW urls_com_features AS
            SELECT u.*, f.* EXCLUDE (url_id)
            FROM urls AS u
            INNER JOIN url_features AS f USING (url_id)
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_urls_id ON urls(url_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_url_features_id "
            "ON url_features(url_id)"
        )
        classes = connection.execute(
            "SELECT label_name, COUNT(*) FROM urls "
            "GROUP BY label_name ORDER BY label_name"
        ).fetchall()

    return {
        "database": str(database_path),
        "rows_per_table": int(urls_count),
        "classes": classes,
    }


def main() -> None:
    args = parse_args()
    result = build_database(args.urls, args.features, args.database)
    print(f"Banco criado: {result['database']}")
    print(f"Linhas por tabela: {result['rows_per_table']}")
    print(f"Classes: {result['classes']}")
    print("Relação por url_id: um para um")


if __name__ == "__main__":
    main()
