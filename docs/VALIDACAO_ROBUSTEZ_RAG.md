# Validação de robustez do RAG

## Objetivo

Verificar o comportamento com linguagem informal, cenários semelhantes e uma
pergunta fora do escopo documental.

| Caso | Resultado final | Situação |
|---|---|---|
| “Mandei um Pix e depois descobri que era golpe...” | Recuperou a página 6, explicou MED e orientou contestar pelos canais oficiais o quanto antes. | Aprovado |
| “Caiu um Pix que eu não conheço...” | Diferenciou Pix recebido de Pix enviado e orientou devolver pela função do banco para a conta de origem. | Aprovado após filtro de relevância |
| “Recebi um áudio do meu irmão pedindo dinheiro...” | Recuperou a página 12 e apresentou verificações previstas na cartilha, sem criar exemplos. | Aprovado |
| “Qual é o telefone da delegacia mais próxima...” | Respondeu que as cartilhas não contêm a informação e indicou consultar uma fonte oficial. O LLM não foi chamado. | Aprovado após barreira de escopo |

## Problemas encontrados e correções

1. O modelo inventou uma resposta para uma pergunta sem evidência documental.
   Foi criada uma barreira determinística de escopo antes da recuperação.
2. Um dos três resultados vetoriais descrevia outro tipo de golpe com Pix e
   contaminou a resposta. O sistema passou a recuperar três candidatos, mas
   enviar ao modelo apenas os suficientemente próximos do melhor resultado.
3. A interface identifica quais trechos foram usados e quais foram descartados
   por baixa relevância.

**Conclusão:** o RAG respondeu às variações informais, diferenciou cenários
parecidos e recusou uma pergunta fora do conteúdo disponível.
