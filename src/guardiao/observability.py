"""Observabilidade opcional e local do fluxo de agentes.

O módulo é deliberadamente tolerante: sem as duas chaves do Langfuse, ou sem
o pacote instalado, todas as operações viram no-op e o fluxo mantém o mesmo
comportamento. Nenhuma chave é registrada ou impressa.
"""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


class _NoopObservation:
    def __enter__(self) -> "_NoopObservation":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def update(self, **_kwargs: Any) -> None:
        return None

    def end(self, **_kwargs: Any) -> None:
        return None


class _ObservationAdapter:
    """Adapta objetos de trace antigos que não implementam context manager."""

    def __init__(self, raw: Any) -> None:
        self.raw = raw

    def __enter__(self) -> "_ObservationAdapter":
        return self

    def __exit__(self, *_exc: object) -> None:
        try:
            self.raw.end()
        except Exception:
            pass

    def update(self, **kwargs: Any) -> None:
        try:
            self.raw.update(**kwargs)
        except Exception:
            pass


class LocalObservability:
    """Fachada segura para o cliente opcional do Langfuse."""

    def __init__(self) -> None:
        self.client: Any | None = None
        self.active = False
        self.reason = "credenciais ausentes"
        secret = os.getenv("LANGFUSE_SECRET_KEY")
        public = os.getenv("LANGFUSE_PUBLIC_KEY")
        if not (secret and public):
            return
        try:
            from langfuse import Langfuse

            host = os.getenv("LANGFUSE_HOST", "cloud.langfuse.com")
            if not host.startswith(("http://", "https://")):
                host = f"https://{host}"
            self.client = Langfuse(
                public_key=public,
                secret_key=secret,
                host=host,
            )
            self.active = True
            self.reason = "Langfuse configurado"
        except (ImportError, TypeError, RuntimeError, OSError) as error:
            self.reason = f"Langfuse indisponível: {type(error).__name__}"

    def observation(
        self,
        name: str,
        *,
        kind: str = "span",
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Abre uma observação compatível com versões do SDK 2 e 3."""
        if not self.active or self.client is None:
            return _NoopObservation()
        try:
            starter = getattr(self.client, "start_as_current_observation", None)
            if starter is not None:
                raw = starter(
                    as_type=kind,
                    name=name,
                    input=input_data,
                    metadata=metadata or {},
                )
                return raw if hasattr(raw, "__enter__") else _ObservationAdapter(raw)
            trace_method = getattr(self.client, "trace", None)
            if trace_method is not None:
                raw = trace_method(
                    name=name, input=input_data, metadata=metadata or {}
                )
                return raw if hasattr(raw, "__enter__") else _ObservationAdapter(raw)
        except Exception:  # observabilidade nunca pode derrubar o produto
            return _NoopObservation()
        return _NoopObservation()

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:
                pass

    def shutdown(self) -> None:
        if self.client is not None:
            try:
                shutdown = getattr(self.client, "shutdown", None)
                if shutdown is not None:
                    shutdown()
            except Exception:
                pass


_INSTANCE: LocalObservability | None = None


def get_observability() -> LocalObservability:
    """Retorna a instância lazy; útil também em testes sem credenciais."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = LocalObservability()
    return _INSTANCE


def initialize_observability() -> LocalObservability:
    """Inicializa (lazy) o tracing e retorna a fachada usada pelo workflow."""
    return get_observability()


def reset_observability() -> None:
    """Limpa a instância para testes que alteram variáveis de ambiente."""
    global _INSTANCE
    _INSTANCE = None


def tracing_status() -> str:
    observability = get_observability()
    return f"Tracing Langfuse: {'ativo' if observability.active else 'inativo'} ({observability.reason})"


def trace(name: str, *, kind: str = "span") -> Callable[[F], F]:
    """Decora uma função sem alterar seu fallback nem sua assinatura pública."""
    def decorator(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            observation = get_observability().observation(
                name,
                kind=kind,
                input_data={"args": repr(args), "kwargs": repr(kwargs)},
            )
            with observation:
                try:
                    result = function(*args, **kwargs)
                except Exception as error:
                    try:
                        observation.update(level="ERROR", status_message=str(error))
                    except Exception:
                        pass
                    raise
                try:
                    observation.update(output=result)
                except Exception:
                    pass
                return result

        return cast(F, wrapped)

    return decorator


def flush_and_shutdown() -> None:
    """Envia eventos pendentes e encerra o cliente, se houver tracing ativo."""
    observability = get_observability()
    observability.flush()
    observability.shutdown()
