# Dados do Guardião Anti-Golpes

## Fonte

**Dataset:** PhiUSIIL Phishing URL (Website)

**Origem:** UCI Machine Learning Repository
https://archive.ics.uci.edu/dataset/967/phiusiil%2Bphishing%2Burl%2Bwebsite%2Bdataset

**Autores:** Arvind Prasad e Shalini Chandra

**Licença:** CC BY 4.0. A reutilização exige atribuição.

**SHA-256 do ZIP inspecionado:** `0A639FD03AEA6308C5B1C10C92AA23C2CE1505447A9137271865CD0BADC9A59A`

**Rótulos da fonte:** `0` significa phishing; `1` significa URL legítima.

## Arquivos processados

- `processed/urls.csv`: identificação, versão neutralizada da URL, domínio neutralizado, TLD, rótulo e fonte.
- `processed/url_features.csv`: atributos calculados localmente a partir do texto da URL.

As tabelas possuem relação de um para um pela chave `url_id`.

## Segurança e transformação

O projeto não abre nem visita URLs do dataset. O script `scripts/prepare_phiusiil.py`:

1. lê somente `URL` e `label` do ZIP oficial;
2. verifica se há rótulos conflitantes;
3. remove URLs duplicadas;
4. recalcula atributos determinísticos com operações locais de texto;
5. remove valores de query e fragmento dos campos publicados;
6. converte `http` para `hxxp` e pontos para `[.]` nos campos exibíveis;
7. grava um hash SHA-256 para rastreabilidade sem depender da URL original.

O ZIP bruto é mantido fora do Git. Para reproduzir os CSVs, baixe a fonte oficial para `data/raw/phiusiil.zip` e execute:

```powershell
python scripts/prepare_phiusiil.py --input data/raw/phiusiil.zip --output-dir data/processed
```

## Limitações conhecidas

- O dataset original mistura atributos da URL e do conteúdo da página.
- Algumas colunas fornecidas pela fonte variam entre linhas com a mesma URL.
- O conjunto apresenta padrões fortes de coleta: todos os exemplos legítimos usam HTTPS e todos os domínios representados como IP estão rotulados como phishing.
- Para o modelo futuro, a divisão de treino e teste deverá ser agrupada por domínio, evitando que endereços do mesmo domínio apareçam nos dois conjuntos.
- A previsão será uma estimativa de risco, não uma garantia de que o endereço é seguro ou malicioso.
