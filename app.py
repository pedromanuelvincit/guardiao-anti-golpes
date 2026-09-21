"""Interface de chat do Guardião Anti-Golpes Digitais."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from guardiao.data_queries import (
    QUERY_DEFINITIONS,
    detect_data_intent,
    format_query_answer,
    run_named_query,
)
from guardiao.message_analysis import (
    analyze_message,
    extract_message_candidate,
    format_message_analysis,
)
from guardiao.ollama_client import DEFAULT_MODEL, stream_chat
from guardiao.formatting import extract_glossary, format_markdown_stream
from guardiao.prompts import SYSTEM_PROMPT, build_user_prompt
from guardiao.rag import retrieve_contexts, select_generation_contexts
from guardiao.scope import OUT_OF_SCOPE_RESPONSE, is_in_scope
from guardiao.url_analysis import (
    analyze_url,
    extract_url_candidate,
    format_url_analysis,
)


TOP_K = int(os.getenv("RAG_TOP_K", "3"))


def render_sources(
    sources: list[dict[str, object]], used_source_ids: set[str] | None = None
) -> None:
    """Exibe os trechos recuperados e quais sustentaram a resposta."""
    if used_source_ids is None:
        used_source_ids = {
            str(source["metadata"]["chunk_id"]) for source in sources
        }

    with st.expander("Trechos recuperados"):
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
                f"Página {metadata['pagina']} · "
                f"[Abrir documento]({metadata['url_documento']})"
            )
            st.caption(
                f"{status} · Chunk {chunk_id} · "
                f"distância vetorial {source['distance']:.4f} · "
                f"termos da pergunta {source.get('lexical_coverage', 0):.0%}"
            )


def render_sql(query_name: str) -> None:
    """Mostra a consulta controlada usada para produzir a resposta."""
    with st.expander("Consulta executada no DuckDB"):
        st.code(str(QUERY_DEFINITIONS[query_name]["sql"]).strip(), language="sql")


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
        f"- **Busca:** {TOP_K} trechos no ChromaDB\n"
        "- **Dados:** consultas controladas no DuckDB\n"
        "- **Triagem:** mensagens e URLs sem acesso à rede"
    )
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
        if message["role"] == "assistant" and message.get("data_query_name"):
            render_sql(str(message["data_query_name"]))

question = st.chat_input("Faça uma pergunta ou peça a análise de uma mensagem ou URL")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        data_intent = detect_data_intent(question)
        message_candidate = extract_message_candidate(question)
        url_candidate = extract_url_candidate(question)
        if data_intent:
            try:
                _, rows = run_named_query(data_intent)
                response = format_query_answer(data_intent, rows)
                st.markdown(response)
                render_sql(data_intent)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "data_query_name": data_intent,
                    }
                )
            except Exception as error:
                st.error(f"Não foi possível consultar o DuckDB: {error}")
        elif message_candidate:
            try:
                message_result = analyze_message(message_candidate)
                response = format_message_analysis(message_result)
                embedded_url = message_result.get("url")
                if embedded_url:
                    response += "\n\n---\n\n" + format_url_analysis(
                        analyze_url(str(embedded_url))
                    )
                st.markdown(response)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "analysis_type": "message",
                    }
                )
            except Exception as error:
                st.error(f"Não foi possível analisar a mensagem: {error}")
        elif url_candidate:
            try:
                response = format_url_analysis(analyze_url(url_candidate))
                st.markdown(response)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "analysis_type": "url",
                    }
                )
            except Exception as error:
                st.error(f"Não foi possível analisar a URL: {error}")
        elif not is_in_scope(question):
            st.markdown(OUT_OF_SCOPE_RESPONSE)
            st.session_state.messages.append(
                {"role": "assistant", "content": OUT_OF_SCOPE_RESPONSE}
            )
        else:
            try:
                with st.spinner("Consultando as cartilhas..."):
                    contexts = retrieve_contexts(question, top_k=TOP_K)
                    generation_contexts = select_generation_contexts(contexts)
                    user_prompt = build_user_prompt(question, generation_contexts)

                response = st.write_stream(
                    format_markdown_stream(
                        stream_chat(
                            SYSTEM_PROMPT, user_prompt, model=DEFAULT_MODEL
                        ),
                        prefix=extract_glossary(generation_contexts),
                    )
                )
                used_source_ids = {
                    str(context["metadata"]["chunk_id"])
                    for context in generation_contexts
                }
                render_sources(contexts, used_source_ids)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response,
                        "sources": contexts,
                        "used_source_ids": sorted(used_source_ids),
                    }
                )
            except Exception as error:
                st.error(f"Não foi possível gerar a resposta: {error}")
