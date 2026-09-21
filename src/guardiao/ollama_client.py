"""Cliente mínimo para respostas em streaming pela API local do Ollama."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def stream_chat(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_OLLAMA_URL,
) -> Iterator[str]:
    """Produz os fragmentos da resposta enviados pela API do Ollama."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "options": {"temperature": 0.0, "num_predict": 180},
    }
    request = Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=300) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                event = json.loads(raw_line.decode("utf-8"))
                if event.get("error"):
                    raise RuntimeError(f"Ollama retornou um erro: {event['error']}")
                content = event.get("message", {}).get("content", "")
                if content:
                    yield content
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"A API do Ollama respondeu com HTTP {error.code}: {details}"
        ) from error
    except URLError as error:
        raise RuntimeError(
            "Não foi possível acessar o Ollama em "
            f"{base_url}. Confirme se o aplicativo está aberto."
        ) from error
