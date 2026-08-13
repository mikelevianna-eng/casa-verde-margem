# Casa Verde Distribuidora — Análise de Margem de Contribuição

![testes](https://github.com/mikelevianna-eng/casa-verde-margem/actions/workflows/testes.yml/badge.svg)

Pipeline completo de dados que identifica onde uma distribuidora de pequeno porte perde margem, partindo de exportações brutas de ERP e chegando a um relatório executivo pronto para a tomada de decisão.

> Projeto de portfólio construído com dados sintéticos. A metodologia, o código e os cálculos são reais. Os dados foram gerados por script para permitir a publicação, já que bases de clientes não podem ser divulgadas.

---

## O problema

A Casa Verde é uma distribuidora de material de limpeza e descartáveis com 5 funcionários e faturamento aproximado de R$ 90 mil por mês. O dono chegou com uma queixa comum.

> "Vendo mais todo ano e não sobra dinheiro no caixa. Não sei quais produtos e quais clientes dão lucro de verdade."

O sistema da empresa mostra a margem por produto, mas calcula apenas o preço de venda menos custo de compra. Ficam de fora o desconto concedido, o custo real da entrega e a comissão do vendedor. É nessa diferença que o resultado desaparece.

---

## Principais achados

| Indicador | Valor |
|---|---|
| Receita analisada | R$ 972.782 |
| Margem de contribuição real | R$ 123.015 (12,6%) |
| Frete absorvido pela empresa em um ano | R$ 62.998 |
| Categoria operando no vermelho | Descartáveis, R$ 19.326 de prejuízo |
| Produtos com margem negativa | 40, somando R$ 227.036 de receita |

**A política de frete grátis custa metade do lucro anual.** A empresa oferece entrega gratuita acima de R$ 600 e absorve o custo integral. Isso consome R$ 62.998 por ano, o equivalente a 51% de toda a margem gerada no período. Sem esse subsídio, Descartáveis sairia do prejuízo e passaria a contribuir positivamente.

**O desconto tem um ponto de virada exato em 10%.**

| Faixa de desconto | Receita | Margem |
|---|---|---|
| 0 a 5% | R$ 612.087 | 17,6% |
| 5 a 10% | R$ 229.987 | 10,6% |
| 10 a 15% | R$ 76.823 | **−1,3%** |
| 15 a 20% | R$ 36.275 | **−6,7%** |
| Acima de 20% | R$ 17.612 | **−31,7%** |

Toda venda com desconto acima de 10% destrói o resultado. Esse achado vira uma regra comercial aplicável de imediato, sem investimento e sem mudança de sistema.

**Os maiores clientes são os menos rentáveis.** A margem média da carteira é 12,6%. Os três maiores clientes rendem entre 4,2% e 6,2%, menos da metade. São contas antigas com condições comerciais negociadas há anos e nunca revisadas, concentradas justamente na categoria de menor margem.

---

## O que o pipeline faz

Os dados chegam como três exportações de ERP com os defeitos típicos desse tipo de arquivo. Valores monetários aparecem como `1.234,56`, `89.90` e `R$ 12,30` na mesma coluna. Datas alternam entre três formatos. O CNPJ vem mascarado em alguns registros e limpo em outros. Há linhas duplicadas, devoluções lançadas como quantidade negativa sem sinalização e pedidos apontando para clientes que não existem no cadastro.

O tratamento resolve tudo isso e registra cada correção aplicada.

| Etapa | Problema encontrado | Registros | Ação |
|---|---|---|---|
| Vendas | Chave pedido mais item repetida na exportação | 76 | Removidas, mantida a primeira ocorrência |
| Vendas | Pedidos com status cancelado | 403 | Excluídos da análise de margem |
| Vendas | Quantidade negativa sem sinalização de devolução | 85 | Marcadas como devolução em coluna própria |
| Integridade | Pedidos com cliente ausente no cadastro | 44 | Reclassificados como não identificado |
| Produtos | Produtos sem custo de compra cadastrado | 378 | Receita mantida, margem sinalizada como indisponível |

Nenhum registro é alterado em silêncio. Esse relatório de auditoria acompanha o entregável final, porque a primeira pergunta do cliente sempre é se os números conferem com o sistema dele.

### A conta que o ERP não faz

```
Receita       = preço praticado × quantidade + frete cobrado do cliente
Custo produto = custo de compra × quantidade
Custo entrega = custo real da entrega, mesmo quando o frete foi grátis
Comissão      = percentual sobre o valor da mercadoria

Margem de contribuição = Receita − Custo produto − Custo entrega − Comissão
```

Um pedido pode ter margem bruta positiva e margem de contribuição negativa. Só o segundo número paga as contas.

---

## Entregáveis

- **Relatório executivo em Excel** com nove abas, disponível em [`data/output/`](data/output/). Os indicadores da capa são fórmulas vivas, então a planilha recalcula quando o cliente filtra ou corrige um valor.
- **Dashboard no Looker Studio** para acompanhamento contínuo.
- **Base tratada em parquet** pronta para consumo por outras ferramentas.

---

## Stack

Python com pandas para o tratamento e a análise. openpyxl para a geração do relatório formatado. pytest para os testes. GitHub Actions para execução automática a cada alteração. Looker Studio para a camada de visualização.

Todo o projeto roda no Google Colab, sem necessidade de instalação local.

---

## Estrutura

```
casa-verde-margem/
├── src/
│   ├── gerar_dados.py        Gerador da base sintética
│   ├── limpeza.py            Tratamento, padronização e cálculo de margem
│   ├── analise.py            Rankings, curva ABC e análise de frete
│   ├── relatorio_excel.py    Geração do relatório executivo
│   └── exportar_sheets.py    Envio das tabelas para o Looker Studio
├── tests/                    53 testes automatizados
├── data/output/              Relatório entregue ao cliente
├── .github/workflows/        Execução automática dos testes
├── requirements.txt
└── pytest.ini
```

---

## Como executar

```bash
git clone https://github.com/SEU_USUARIO/casa-verde-margem.git
cd casa-verde-margem
pip install -r requirements.txt

python src/gerar_dados.py       # gera a base bruta
python src/limpeza.py           # trata e calcula margem
python src/relatorio_excel.py   # produz o relatório
pytest                          # roda os testes
```

A geração usa semente fixa, então qualquer execução reproduz exatamente os mesmos números apresentados aqui.

---

## Testes

São 53 testes que validam regras de negócio, não apenas execução de código. Um pipeline pode rodar sem erro e entregar número errado, e é esse o defeito que chega ao cliente.

Alguns exemplos do que está coberto.

O valor `1.234,56` precisa virar 1234,56 e não 1,23, porque a confusão entre separador de milhar e decimal produz erro de mil vezes sem lançar exceção. A data `03/05/2025` precisa ser lida como 3 de maio pelo padrão brasileiro, já que a inferência automática interpretaria como 5 de março e distorceria toda a análise mensal. A curva ABC precisa cortar por receita acumulada e não por contagem de itens, que é o erro mais frequente nessa técnica. E um pedido com margem bruta positiva e margem de contribuição negativa precisa continuar sendo detectado, porque essa é a tese central do trabalho.

---

## Limitações

O custo de entrega usado no cálculo é uma estimativa por peso volumétrico, não o valor real cobrado pela transportadora em cada rota. Num projeto com dados verdadeiros, esse número viria da fatura do frete.

A comissão é tratada como percentual fixo por vendedor. Estruturas escalonadas por meta exigiriam regra adicional.

Produtos sem custo cadastrado ficam fora do cálculo de margem, embora permaneçam no faturamento. São 378 registros, e a correção depende do cliente completar o cadastro no ERP.

---

## Sobre os dados

A base foi gerada pelo script [`src/gerar_dados.py`](src/gerar_dados.py), que replica a estrutura de uma exportação real de ERP e injeta deliberadamente os problemas de qualidade descritos acima. O gerador é parte do projeto e demonstra o entendimento sobre como esses dados se comportam na prática.

O caso reproduz um padrão que se repete em distribuidoras de pequeno porte, no qual a categoria de maior giro é também a de menor margem, e a combinação de desconto por volume com frete subsidiado transforma o produto campeão de vendas em gerador de prejuízo.
