# Declaração do desafio CBL — Guardião Anti-Golpes Digitais

**Estado:** versão final candidata, aguardando apenas a aprovação autoral do estudante. A justificativa pessoal foi escrita pelo estudante e revisada em três frases, com correções de ortografia, pontuação e estrutura gramatical.

## Grande ideia

Segurança digital e prevenção de fraudes no cotidiano. Pessoas precisam reconhecer sinais de manipulação e verificar informações antes de compartilhar dados ou realizar pagamentos.

## Pergunta essencial

Como podemos ajudar pessoas comuns a reconhecer possíveis golpes digitais e decidir com segurança o que fazer antes ou depois de uma interação suspeita?

## Desafio

Criar o **Guardião Anti-Golpes Digitais**, um assistente de triagem e orientação preventiva com interface de chat. O sistema deverá identificar sinais presentes em mensagens e endereços informados pelo usuário, consultar orientações confiáveis sobre golpes por meio de RAG, responder perguntas em linguagem natural sobre um conjunto estruturado de exemplos de phishing e explicar suas conclusões com evidências e incertezas. A análise de URLs será feita sem abrir os endereços; o assistente também deverá evitar expor dados pessoais e indicar ações seguras para a situação apresentada.

## Justificativa pessoal — autoria do estudante

Durante um período em que eu estava com um CNPJ ativo, recebi uma mensagem dizendo que meu boleto do MEI estava vencido; acabei clicando e pagando e, somente depois de conferir, descobri que era um golpe, o que me deixou frustrado, pois, mesmo após abrir um processo no meu banco para ter o valor restituído, não consegui. A ideia surgiu a partir de uma sugestão do meu assistente de projetos e despertou meu interesse pela proposta, por resolver um problema frequente no ambiente digital. Em 2025, o Brasil registrou mais de 346 mil casos de golpes digitais, um aumento de 20,6% em relação ao ano anterior, segundo o G1; assim, além de poder ajudar outras pessoas, a ferramenta também possui potencial econômico para mim como projeto de negócio.

**Fonte da estatística:** [G1 — Brasil registrou mais de quatro golpes por minuto em 2025](https://g1.globo.com/politica/noticia/2026/07/23/golpes-registrados-por-minuto-anuario-seguranca-publica.ghtml).

## Verificação da rubrica

| Critério | Situação | Evidência ou ajuste necessário |
|---|---|---|
| Grande ideia ampla e relevante | Atende | Segurança digital admite várias situações reais de fraude |
| Pergunta essencial aberta | Atende | Pergunta sobre reconhecimento e decisão segura, sem pressupor uma única solução |
| Desafio concreto e coerente | Atende | Define público, função, dados, RAG, interface e limites já implementados |
| Justificativa pessoal autêntica | Concluída | Experiência real descrita pelo estudante em três frases e apoiada por estatística referenciada |
| Domínio viável para as próximas etapas | Confirmado | CSV inspecionado e processado; DuckDB, RAG e triagem foram integrados e validados |
