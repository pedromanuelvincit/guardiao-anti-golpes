"""Treina e avalia um classificador local de risco de phishing (Sprint 1).

O script não abre URLs, não faz requisições de rede, não consulta DNS,
certificado ou conteúdo HTML. A saída é uma estimativa de risco, nunca uma
confirmação de fraude ou legitimidade.

Falsos negativos: classificar uma URL de phishing (is_phishing=1) como
legítima. Recall alto da classe positiva reduz esses erros. Um score alto
neste dataset não prova segurança em URLs reais. Padrões como HTTPS e
domínio em formato IP podem refletir viés de coleta do PhiUSIIL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flaml import AutoML
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URLS = PROJECT_ROOT / "data" / "processed" / "urls.csv"
DEFAULT_FEATURES = PROJECT_ROOT / "data" / "processed" / "url_features.csv"

URL_REQUIRED = ("url_id", "label", "domain_masked")
FORBIDDEN_FEATURES = {
    "url_id",
    "label",
    "label_name",
    "url_masked",
    "domain_masked",
    "url_sha256",
    "source",
    "tld",
    "is_phishing",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Treina um classificador local de risco de phishing."
    )
    parser.add_argument("--urls-path", type=Path, default=DEFAULT_URLS)
    parser.add_argument("--features-path", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--time-budget", type=int, default=60)
    parser.add_argument("--test-size", type=float, default=0.20)
    parser.add_argument("--validation-size", type=float, default=0.20)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--model-output",
        type=Path,
        default=None,
        help="Caminho opcional para salvar o modelo escolhido e seus metadados.",
    )
    return parser.parse_args()


def resolve_csv(path: Path) -> Path:
    resolved = path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"CSV não encontrado: {resolved}")
    return resolved


def load_joined_dataset(urls_path: Path, features_path: Path) -> pd.DataFrame:
    urls = pd.read_csv(urls_path)
    features = pd.read_csv(features_path)

    missing_urls = [column for column in URL_REQUIRED if column not in urls.columns]
    if missing_urls:
        raise ValueError(f"Colunas obrigatórias ausentes em urls.csv: {missing_urls}")
    if "url_id" not in features.columns:
        raise ValueError("url_features.csv precisa da coluna url_id.")

    if urls["url_id"].duplicated().any():
        raise ValueError("Há url_id duplicado em urls.csv.")
    if features["url_id"].duplicated().any():
        raise ValueError("Há url_id duplicado em url_features.csv.")

    dataset = urls.merge(features, on="url_id", how="inner", validate="one_to_one")
    if len(dataset) != len(urls) or len(dataset) != len(features):
        raise ValueError("O join por url_id não preservou a relação um para um.")

    # 0 = phishing no rótulo original; a classe positiva passa a ser 1.
    dataset["is_phishing"] = (dataset["label"] == 0).astype(int)
    return dataset


def select_numeric_features(dataset: pd.DataFrame, features_path: Path) -> list[str]:
    feature_header = pd.read_csv(features_path, nrows=0)
    candidates = [
        column
        for column in feature_header.columns
        if column not in FORBIDDEN_FEATURES and pd.api.types.is_numeric_dtype(dataset[column])
    ]
    if not candidates:
        raise ValueError("Nenhuma feature numérica permitida foi encontrada.")
    return candidates


def split_by_domain(
    X: pd.DataFrame,
    y: pd.Series,
    groups: pd.Series,
    test_size: float,
    validation_size: float,
    random_state: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    outer = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_val_idx, test_idx = next(outer.split(X, y, groups=groups))

    X_train_val = X.iloc[train_val_idx]
    y_train_val = y.iloc[train_val_idx]
    groups_train_val = groups.iloc[train_val_idx]

    inner = GroupShuffleSplit(
        n_splits=1, test_size=validation_size, random_state=random_state
    )
    train_rel, val_rel = next(inner.split(X_train_val, y_train_val, groups=groups_train_val))

    X_train = X_train_val.iloc[train_rel]
    y_train = y_train_val.iloc[train_rel]
    groups_train = groups_train_val.iloc[train_rel]
    X_val = X_train_val.iloc[val_rel]
    y_val = y_train_val.iloc[val_rel]
    groups_val = groups_train_val.iloc[val_rel]
    X_test = X.iloc[test_idx]
    y_test = y.iloc[test_idx]
    groups_test = groups.iloc[test_idx]
    return X_train, X_val, X_test, y_train, y_val, y_test, groups_train, groups_val, groups_test


def report_splits(
    y_train: pd.Series,
    y_val: pd.Series,
    y_test: pd.Series,
    groups_train: pd.Series,
    groups_val: pd.Series,
    groups_test: pd.Series,
) -> None:
    train_domains = set(groups_train)
    val_domains = set(groups_val)
    test_domains = set(groups_test)

    print("Divisão por domínio (GroupShuffleSplit)")
    print(f"  treino:      {len(y_train)} registros, {len(train_domains)} domínios")
    print(f"  validação:   {len(y_val)} registros, {len(val_domains)} domínios")
    print(f"  teste:       {len(y_test)} registros, {len(test_domains)} domínios")

    overlaps = [
        ("treino e validação", train_domains & val_domains),
        ("treino e teste", train_domains & test_domains),
        ("validação e teste", val_domains & test_domains),
    ]
    leaked = False
    for label, overlap in overlaps:
        if overlap:
            leaked = True
            print(f"  SOBREPOSIÇÃO em {label}: {len(overlap)} domínios")
    if not leaked:
        print("  confirmação: não há sobreposição de domínios entre os conjuntos.")


def classification_metrics(y_true, y_pred, y_score) -> dict[str, object]:
    metrics = {
        "matriz_confusao": confusion_matrix(y_true, y_pred, labels=[0, 1]),
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_phishing": precision_score(y_true, y_pred, pos_label=1, zero_division=0),
        "recall_phishing": recall_score(y_true, y_pred, pos_label=1, zero_division=0),
        "f1_phishing": f1_score(y_true, y_pred, pos_label=1, zero_division=0),
        "roc_auc": float("nan"),
    }
    if y_score is not None:
        metrics["roc_auc"] = roc_auc_score(y_true, y_score)
    return metrics


def predict_with_scores(model, X) -> tuple[object, object]:
    y_pred = model.predict(X)
    y_score = None
    if hasattr(model, "predict_proba"):
        y_score = model.predict_proba(X)[:, 1]
    return y_pred, y_score


def save_model_bundle(
    output_path: Path,
    model: object,
    model_name: str,
    feature_columns: list[str],
) -> Path:
    """Salva o modelo escolhido junto com o contrato mínimo de entrada."""
    resolved = output_path if output_path.is_absolute() else (PROJECT_ROOT / output_path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "model_name": model_name,
        "feature_columns": feature_columns,
        "positive_label": "is_phishing=1",
        "input_adapter": "for_flaml" if model_name == "FLAML" else "pandas",
    }
    joblib.dump(bundle, resolved)
    return resolved


def report_thresholds(y_true: pd.Series, y_score: object) -> None:
    """Compara limites de decisão apenas na validação."""
    if y_score is None:
        print("\nAnálise de limites: indisponível sem score probabilístico.")
        return

    print("\nAnálise de limites na validação (teste ainda não usado):")
    print("  limite | precision | recall | f1 | falsos negativos")
    for threshold in (0.30, 0.50, 0.70):
        predictions = (np.asarray(y_score) >= threshold).astype(int)
        metrics = classification_metrics(y_true, predictions, None)
        matrix = metrics["matriz_confusao"]
        print(
            f"  {threshold:.2f}   | "
            f"{metrics['precision_phishing']:.4f}   | "
            f"{metrics['recall_phishing']:.4f} | "
            f"{metrics['f1_phishing']:.4f} | {int(matrix[1, 0])}"
        )


def print_metrics(title: str, metrics: dict[str, object]) -> None:
    matrix = metrics["matriz_confusao"]
    print(title)
    print("  matriz de confusão [[TN FP] [FN TP]]:")
    print(f"    {matrix[0].tolist()}")
    print(f"    {matrix[1].tolist()}")
    print(f"  accuracy:            {metrics['accuracy']:.4f}")
    print(f"  precision phishing:  {metrics['precision_phishing']:.4f}")
    print(f"  recall phishing:     {metrics['recall_phishing']:.4f}")
    print(f"  f1 phishing:         {metrics['f1_phishing']:.4f}")
    print(f"  roc-auc:             {metrics['roc_auc']:.4f}")
    print(
        "  nota: FN (matriz[1,0]) são URLs de phishing classificadas como "
        "legítimas; recall alto reduz esses erros."
    )


def train_baseline(
    X_train: pd.DataFrame, y_train: pd.Series, random_state: int
) -> Pipeline:
    # Referência simples e explicável, treinada só no conjunto de treino.
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=random_state,
                ),
            ),
        ]
    )
    model.fit(X_train, y_train)
    return model


def for_flaml(frame: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói o DataFrame com colunas object; o pandas 3 usa StringDtype."""
    return pd.DataFrame(
        frame.to_numpy(dtype=np.float64),
        columns=pd.Index([str(name) for name in frame.columns], dtype=object),
        index=frame.index,
    )


def train_flaml(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    time_budget: int,
    random_state: int,
) -> AutoML:
    automl = AutoML()
    automl.fit(
        for_flaml(X_train),
        y_train.to_numpy(),
        task="classification",
        metric="f1",
        time_budget=time_budget,
        seed=random_state,
        X_val=for_flaml(X_val),
        y_val=y_val.to_numpy(),
        verbose=1,
    )
    return automl


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = parse_args()
    urls_path = resolve_csv(args.urls_path)
    features_path = resolve_csv(args.features_path)

    dataset = load_joined_dataset(urls_path, features_path)
    feature_cols = select_numeric_features(dataset, features_path)

    X = dataset[feature_cols]
    y = dataset["is_phishing"]
    groups = dataset["domain_masked"]

    print(f"Registros unidos: {len(dataset)}")
    print(f"Features numéricas ({len(feature_cols)}): {', '.join(feature_cols)}")
    print(
        "A saída do modelo é estimativa de risco. HTTPS, IP no host e scores "
        "altos neste conjunto podem refletir viés do dataset, não segurança real."
    )

    (
        X_train,
        X_val,
        X_test,
        y_train,
        y_val,
        y_test,
        groups_train,
        groups_val,
        groups_test,
    ) = split_by_domain(
        X,
        y,
        groups,
        test_size=args.test_size,
        validation_size=args.validation_size,
        random_state=args.random_state,
    )
    report_splits(y_train, y_val, y_test, groups_train, groups_val, groups_test)

    print("\nTreinando referência (LogisticRegression)...")
    baseline = train_baseline(X_train, y_train, args.random_state)
    baseline_pred, baseline_score = predict_with_scores(baseline, X_val)
    baseline_val = classification_metrics(y_val, baseline_pred, baseline_score)
    print_metrics("Validação — referência", baseline_val)

    print(f"\nTreinando FLAML (time_budget={args.time_budget}s, metric=f1)...")
    automl = train_flaml(
        X_train,
        y_train,
        X_val,
        y_val,
        time_budget=args.time_budget,
        random_state=args.random_state,
    )
    flaml_pred, flaml_score = predict_with_scores(automl, for_flaml(X_val))
    flaml_val = classification_metrics(y_val, flaml_pred, flaml_score)
    print_metrics("Validação — FLAML", flaml_val)
    print(f"  melhor estimador FLAML: {automl.best_estimator}")

    chosen_name = "FLAML"
    chosen_model = automl
    if baseline_val["f1_phishing"] > flaml_val["f1_phishing"]:
        chosen_name = "referência LogisticRegression"
        chosen_model = baseline
    print(f"\nModelo escolhido pela F1 de phishing na validação: {chosen_name}")
    print("O conjunto de teste não foi usado no ajuste.")
    chosen_val_score = flaml_score if chosen_name == "FLAML" else baseline_score
    report_thresholds(y_val, chosen_val_score)

    test_input = for_flaml(X_test) if chosen_name == "FLAML" else X_test
    test_pred, test_score = predict_with_scores(chosen_model, test_input)
    test_metrics = classification_metrics(y_test, test_pred, test_score)
    print_metrics("Teste — avaliação final (uma única vez)", test_metrics)

    if args.model_output is not None:
        saved_path = save_model_bundle(
            args.model_output,
            chosen_model,
            chosen_name,
            feature_cols,
        )
        print(f"\nModelo e metadados salvos em: {saved_path}")


if __name__ == "__main__":
    main()
