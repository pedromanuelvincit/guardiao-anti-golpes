# Validação das consultas ao DuckDB

## Resultado

As duas consultas oficiais foram executadas pela interface a partir de
perguntas em linguagem natural. O sistema identificou a intenção, executou uma
consulta SQL previamente aprovada em modo somente leitura e exibiu o SQL para
auditoria.

## Consulta 1 — distribuição das classes

**Pergunta:** Quantas URLs são phishing e quantas são legítimas?

| Classe | Quantidade | Percentual |
|---|---:|---:|
| Legítima | 134.850 | 57,29% |
| Phishing | 100.520 | 42,71% |

**Tabelas usadas:** `urls`.

## Consulta 2 — comparação de características

**Pergunta:** Qual é o comprimento médio das URLs e qual percentual usa HTTPS
em cada classe?

| Classe | Quantidade | Comprimento médio | HTTPS |
|---|---:|---:|---:|
| Legítima | 134.850 | 27,23 | 100,00% |
| Phishing | 100.520 | 46,22 | 48,63% |

**Tabelas usadas:** `urls` e `url_features`, relacionadas por `url_id` com
`INNER JOIN`.

## Critérios verificados

- As perguntas foram feitas em linguagem natural.
- Os resultados correspondem ao perfil documentado da base processada.
- A segunda consulta demonstra a relação entre as duas tabelas.
- O banco foi aberto em modo somente leitura.
- Somente consultas previamente aprovadas podem ser executadas.
- A interface preserva a consulta e o SQL no histórico da sessão.

**Conclusão:** integração com dados estruturados aprovada para a demonstração
do projeto.
