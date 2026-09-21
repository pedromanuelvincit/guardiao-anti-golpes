# Validação técnica da triagem de mensagens e URLs

## Objetivo

Permitir que o usuário forneça uma mensagem ou URL para uma triagem inicial
de sinais observáveis.

## Comportamento implementado

- A análise ocorre localmente e não abre URLs.
- Endereços são neutralizados antes de serem exibidos.
- Mensagens são verificadas quanto a pressa, ameaça, pagamento, dados
  sensíveis, autoridade, vantagem, segredo e links.
- URLs são verificadas quanto a IP no domínio, ausência de HTTPS, `@`,
  codificação, termos sensíveis, subdomínios e comprimento elevado.
- A saída não classifica definitivamente uma mensagem ou URL como segura ou
  fraudulenta.
- Quando uma mensagem contém URL, as duas triagens aparecem na mesma resposta.

## Testes executados

1. Mensagem fictícia com urgência, boleto de MEI, pagamento e URL neutralizada:
   os sinais correspondentes foram identificados.
2. URL com IP reservado para documentação, HTTP e termos de autenticação:
   os sinais foram identificados sem acesso à rede.
3. Mensagem neutra: nenhum padrão foi encontrado e o sistema informou que isso
   não comprova legitimidade.
4. URL simples com HTTPS: nenhum dos sinais textuais verificados foi encontrado
   e o sistema manteve o aviso de incerteza.
5. Inicialização completa do Streamlit: endpoint de saúde respondeu `200 ok`.
6. Mensagem de falsa pendência no Nubank: foram identificados urgência, ameaça
   de bloqueio, pedido de pagamento, uso de autoridade e presença de link.
7. URL neutralizada com endereço IP: o endereço completo foi preservado e os
   sinais de IP, ausência de HTTPS e termo de autenticação foram identificados.
8. Pedido `Analise esta mensagem` escrito depois do conteúdo: a mensagem passou
   a ser reconhecida corretamente.
9. Link em formato Markdown: somente a URL foi extraída, sem incorporar os
   colchetes, parênteses ou a repetição do endereço.

**Conclusão:** as rotas estão integradas, os dois casos avaliados na interface
foram corrigidos e os testes de regressão passaram.
