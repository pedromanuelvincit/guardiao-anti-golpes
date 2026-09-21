# Validação humana do pipeline RAG

## Resultado

As três perguntas oficiais foram executadas na interface Streamlit com
recuperação no ChromaDB, geração pelo `llama3.2:3b` local e resposta em
streaming. As fontes foram exibidas com documento, página, chunk e distância
vetorial.

| Pergunta | Evidência principal | Avaliação humana |
|---|---|---|
| Como conferir se um boleto é verdadeiro antes de pagar? | *Golpes: Evite Fraudes*, página 13 | Aprovada. A resposta orientou conferir despesa, valor, destinatário, boleto registrado e canais oficiais. |
| Como verificar se um áudio ou vídeo conhecido pode ter sido falsificado com IA? | *Golpes: Não se Deixe Enganar*, página 12 | Aprovada. A resposta orientou confirmar por contato conhecido, buscar alterações e testar o conhecimento da pessoa. |
| O que fazer depois de transferir dinheiro por Pix para um golpista? | *Golpes: Caiu? Veja o que Fazer*, página 6 | Aprovada. A resposta orientou contestar pelos canais oficiais, acionar o MED e agir o quanto antes, sem garantir devolução. |

## Critérios verificados

- As três evidências esperadas apareceram entre os três primeiros resultados.
- As respostas permaneceram limitadas ao conteúdo recuperado.
- O sistema não garantiu recuperação de valores.
- A resposta foi exibida progressivamente.
- A interface preservou o histórico e permitiu limpar a conversa.
- As fontes permaneceram disponíveis abaixo de cada resposta.

**Conclusão:** pipeline RAG aprovado para a demonstração do projeto.

## Ajuste final de precisão

Durante a validação da escrita, o modelo local acrescentou exemplos que não
constavam nos documentos. O prompt foi alterado para um modo extrativo com um
exemplo fictício de resposta desejada. No teste final sobre falsificação de
áudio e vídeo, a resposta preservou as quatro orientações relevantes da página
12 sem criar exemplos adicionais.

Na pergunta sobre Pix, a ordenação passou a combinar distância vetorial e
palavras da pergunta. Isso colocou o trecho sobre dinheiro transferido ao
golpista antes do trecho sobre Pix recebido por engano. Definições explícitas
de siglas, como MED, são extraídas diretamente do trecho e exibidas antes dos
passos, evitando depender da geração do modelo.
