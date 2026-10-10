"""Interface de chat do Guardião Anti-Golpes Digitais."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.agent_workflow import run_agent_workflow
from guardiao.message_analysis import analyze_message, extract_message_candidate
from guardiao.observability import initialize_observability, tracing_status
from guardiao.ollama_client import DEFAULT_MODEL
from guardiao.scope import OUT_OF_SCOPE_RESPONSE, is_in_scope
from guardiao.url_analysis import extract_url_candidate


initialize_observability()


def render_sources(
    sources: list[dict[str, object]], used_source_ids: set[str] | None = None
) -> None:
    """Exibe os trechos recuperados e quais sustentaram a resposta."""
    if used_source_ids is None:
        used_source_ids = {
            str(source["metadata"]["chunk_id"]) for source in sources
        }

    with st.expander("Fontes consultadas"):
        for index, source in enumerate(sources, start=1):
            metadata = source["metadata"]
            chunk_id = str(metadata["chunk_id"])
            status = (
                "Usado na resposta"
                if chunk_id in used_source_ids
                else "Não enviado ao modelo por baixa relevância"
            )
            st.markdown(
                f"**Fonte {index}: {metadata['titulo']}**  \n"
                f"Página {metadata['pagina']}"
            )
            st.caption(status)


st.set_page_config(
    page_title="Guardião Anti-Golpes",
    page_icon="🛡️",
    layout="centered",
)

st.title("🛡️ Guardião Anti-Golpes")
st.write(
    "Consulte orientações preventivas ou peça a triagem de uma mensagem ou URL. "
    "Não informe senhas, códigos, documentos ou dados bancários."
)

with st.sidebar:
    st.subheader("Como funciona")
    st.markdown(
        f"- **Modelo local:** `{DEFAULT_MODEL}`\n"
        "- **Fluxo:** Analista de Risco → Orientador Preventivo\n"
        "- **Fontes:** cartilhas locais do CERT.br\n"
        "- **Segurança:** mensagens e URLs são analisadas sem acesso à rede"
    )
    st.caption(tracing_status())
    st.caption(
        "Exemplos: “Analise esta mensagem: ...” ou “Analise esta URL: ...”."
    )
    if st.button("Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("sources"):
            render_sources(
                message["sources"],
                set(message.get("used_source_ids", [])) or None,
            )

question = st.chat_input("Faça uma pergunta ou peça a análise de uma mensagem ou URL")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        message_candidate = extract_message_candidate(question)
        url_candidate = extract_url_candidate(question)
        if not (url_candidate or message_candidate or is_in_scope(question)):
            response = OUT_OF_SCOPE_RESPONSE
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
        else:
            try:
                message_for_analysis = message_candidate
                if (
                    message_for_analysis is None
                    and url_candidate
                    and question.strip() != url_candidate.strip()
                ):
                    message_for_analysis = question
                message_analysis = (
                    analyze_message(message_for_analysis)
                    if message_for_analysis
                    else None
                )
                activity = "🔍 Analisando URL..." if url_candidate else "🔍 Preparando orientação..."
                with st.spinner(activity):
                    result = run_agent_workflow(
                        question,
                        url=url_candidate,
                        message_analysis=message_analysis,
                    )

                response = str(result["answer"])
                st.markdown(response)
                render_sources(
                    list(result["sources"]),
                    set(result["used_source_ids"]) or None,
                )
                if result["fallback_used"]:
                    st.info("A orientação foi gerada no modo local de contingência.")
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "sources": result["sources"],
                        "used_source_ids": result["used_source_ids"],
                    }
                )
            except Exception:
                response = (
                    "Não foi possível concluir a análise agora. Não abra links nem "
                    "compartilhe dados; confirme a solicitação por um canal oficial."
                )
                st.error(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
