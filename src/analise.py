"""
Analise de margem - Casa Verde Distribuidora

Responde as tres perguntas que o dono da empresa faz na reuniao:

  1. Quais produtos vendem bem e dao prejuizo
  2. Quais clientes consomem margem em vez de gerar
  3. Quanto a politica de frete gratis custa por ano

Cada funcao devolve um DataFrame pronto para ir ao Excel ou ao
dashboard. Nenhuma delas imprime nada, para que possam ser testadas.

Uso:
    from analise import gerar_analises
    resultados = gerar_analises(df)
"""

import pandas as pd

# Limiares usados na classificacao. Ficam aqui, e nao espalhados pelo
# codigo, porque sao parametros de negocio que o cliente pode discutir.
MARGEM_SAUDAVEL = 20.0     # percentual considerado adequado pela empresa
MARGEM_ATENCAO = 10.0      # abaixo disso, revisar politica comercial
CORTE_ABC_A = 0.80         # 80 por cento da receita acumulada
CORTE_ABC_B = 0.95


# ---------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------

def _somente_confiaveis(df):
    """Restringe a analise de margem aos registros com custo cadastrado."""
    return df[df["custo_confiavel"]].copy()


def _classificar_margem(pct):
    if pd.isna(pct):
        return "SEM CUSTO"
    if pct < 0:
        return "PREJUIZO"
    if pct < MARGEM_ATENCAO:
        return "CRITICA"
    if pct < MARGEM_SAUDAVEL:
        return "ATENCAO"
    return "SAUDAVEL"


def _curva_abc(df, coluna_valor):
    """
    Classifica em A, B e C pelo criterio de Pareto sobre a receita.

    A ordenacao e decrescente e o corte usa a receita acumulada, nao a
    contagem de itens, que e o erro comum nessa analise.
    """
    df = df.sort_values(coluna_valor, ascending=False).copy()
    total = df[coluna_valor].sum()
    df["receita_acumulada_pct"] = df[coluna_valor].cumsum() / total

    def faixa(acumulado):
        if acumulado <= CORTE_ABC_A:
            return "A"
        if acumulado <= CORTE_ABC_B:
            return "B"
        return "C"

    df["classe_abc"] = df["receita_acumulada_pct"].apply(faixa)
    df["receita_acumulada_pct"] = (df["receita_acumulada_pct"] * 100).round(1)
    return df


# ---------------------------------------------------------------------
# Analises
# ---------------------------------------------------------------------

def resumo_categoria(df):
    """Visao de topo. E o slide que abre a apresentacao ao cliente."""
    base = _somente_confiaveis(df)

    r = base.groupby("categoria").agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        custo_frete=("custo_entrega", "sum"),
        frete_subsidiado=("frete_subsidiado", "sum"),
        pedidos=("numero_pedido", "nunique"),
    )

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    r["participacao_receita_pct"] = (r["receita"] / r["receita"].sum() * 100).round(1)
    r["situacao"] = r["margem_pct"].apply(_classificar_margem)

    return r.sort_values("margem").reset_index().round(2)


def produtos_prejuizo(df, minimo_receita=1000):
    """
    Produtos que geram receita relevante e margem negativa.

    O filtro de receita minima evita que item vendido uma vez apareca
    no topo do relatorio e desvie a atencao do que importa.
    """
    base = _somente_confiaveis(df)

    r = base.groupby(["codigo_produto", "descricao", "categoria"]).agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        quantidade=("quantidade", "sum"),
        desconto_medio=("desconto_pct", "mean"),
        pedidos=("numero_pedido", "nunique"),
    ).reset_index()

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    r["desconto_medio"] = r["desconto_medio"].round(1)
    r["situacao"] = r["margem_pct"].apply(_classificar_margem)

    r = r[(r["receita"] >= minimo_receita) & (r["margem"] < 0)]
    return r.sort_values("margem").reset_index(drop=True).round(2)


def ranking_produtos(df):
    """Todos os produtos com curva ABC, para o Excel do cliente."""
    base = _somente_confiaveis(df)

    r = base.groupby(["codigo_produto", "descricao", "categoria"]).agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        quantidade=("quantidade", "sum"),
        desconto_medio=("desconto_pct", "mean"),
    ).reset_index()

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    r["desconto_medio"] = r["desconto_medio"].round(1)
    r = _curva_abc(r, "receita")
    r["situacao"] = r["margem_pct"].apply(_classificar_margem)

    return r.reset_index(drop=True).round(2)


def ranking_clientes(df):
    """
    Curva ABC de clientes cruzada com margem.

    O cruzamento e o ponto da analise. Cliente classe A com margem
    negativa e o caso mais grave da carteira, porque concentra volume
    e consome resultado ao mesmo tempo.
    """
    base = _somente_confiaveis(df)
    base = base[base["codigo_cliente"] != "NAO_IDENTIFICADO"]

    r = base.groupby(["codigo_cliente", "razao_social", "segmento", "regiao"]).agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        frete_subsidiado=("frete_subsidiado", "sum"),
        desconto_medio=("desconto_pct", "mean"),
        pedidos=("numero_pedido", "nunique"),
    ).reset_index()

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    r["ticket_medio"] = (r["receita"] / r["pedidos"]).round(2)
    r["desconto_medio"] = r["desconto_medio"].round(1)
    r = _curva_abc(r, "receita")
    r["situacao"] = r["margem_pct"].apply(_classificar_margem)

    return r.reset_index(drop=True).round(2)


def custo_frete_gratis(df):
    """
    Quanto a politica de frete gratis custa e quem se beneficia dela.

    Frete subsidiado e a diferenca entre o custo real da entrega e o
    valor cobrado do cliente. Quando o pedido passa do limite da
    promocao, o subsidio e igual ao custo integral.
    """
    base = _somente_confiaveis(df)

    por_categoria = base.groupby("categoria").agg(
        receita=("receita_total", "sum"),
        custo_entrega=("custo_entrega", "sum"),
        frete_cobrado=("frete_cobrado", "sum"),
        subsidio=("frete_subsidiado", "sum"),
        margem=("margem_contribuicao", "sum"),
    ).reset_index()

    por_categoria["subsidio_sobre_receita_pct"] = (
        por_categoria["subsidio"] / por_categoria["receita"] * 100
    ).round(1)

    por_categoria["margem_sem_subsidio"] = (
        por_categoria["margem"] + por_categoria["subsidio"]
    )

    return por_categoria.sort_values("subsidio", ascending=False).round(2)


def evolucao_mensal(df):
    """Serie mensal de receita e margem, base do grafico do dashboard."""
    base = _somente_confiaveis(df)

    r = base.groupby("ano_mes").agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        pedidos=("numero_pedido", "nunique"),
    ).reset_index()

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    r["ticket_medio"] = (r["receita"] / r["pedidos"]).round(2)

    return r.round(2)


def impacto_desconto(df, faixas=(0, 5, 10, 15, 20, 100)):
    """
    Margem por faixa de desconto concedido.

    Serve para mostrar ao cliente em que ponto o desconto deixa de ser
    ferramenta comercial e passa a ser destruicao de resultado.
    """
    base = _somente_confiaveis(df)

    rotulos = [f"{faixas[i]} a {faixas[i+1]}%" for i in range(len(faixas) - 1)]
    base["faixa_desconto"] = pd.cut(
        base["desconto_pct"], bins=faixas, labels=rotulos, include_lowest=True
    )

    r = base.groupby("faixa_desconto", observed=True).agg(
        receita=("receita_total", "sum"),
        margem=("margem_contribuicao", "sum"),
        linhas=("numero_pedido", "count"),
    ).reset_index()

    r["margem_pct"] = (r["margem"] / r["receita"] * 100).round(1)
    return r.round(2)


# ---------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------

def gerar_analises(df):
    """Executa todas as analises e devolve um dicionario nomeado."""
    return {
        "resumo_categoria": resumo_categoria(df),
        "produtos_prejuizo": produtos_prejuizo(df),
        "ranking_produtos": ranking_produtos(df),
        "ranking_clientes": ranking_clientes(df),
        "custo_frete_gratis": custo_frete_gratis(df),
        "evolucao_mensal": evolucao_mensal(df),
        "impacto_desconto": impacto_desconto(df),
    }


def principais_achados(df):
    """
    Numeros de destaque, os que vao para a primeira pagina do relatorio
    e para o README do repositorio.
    """
    base = _somente_confiaveis(df)
    cat = resumo_categoria(df)
    prod = produtos_prejuizo(df)
    cli = ranking_clientes(df)

    negativas = cat[cat["margem"] < 0]
    clientes_a_negativos = cli[(cli["classe_abc"] == "A") & (cli["margem"] < 0)]

    return {
        "receita_total": base["receita_total"].sum(),
        "margem_total": base["margem_contribuicao"].sum(),
        "margem_pct": base["margem_contribuicao"].sum() / base["receita_total"].sum() * 100,
        "categorias_no_prejuizo": list(negativas["categoria"]),
        "prejuizo_categorias": negativas["margem"].sum(),
        "produtos_no_prejuizo": len(prod),
        "receita_produtos_prejuizo": prod["receita"].sum(),
        "frete_subsidiado_ano": base["frete_subsidiado"].sum(),
        "clientes_classe_a_negativos": len(clientes_a_negativos),
    }


if __name__ == "__main__":
    from limpeza import executar_limpeza

    df, _ = executar_limpeza(salvar=False)
    achados = principais_achados(df)

    print()
    print("PRINCIPAIS ACHADOS".center(70))
    print("=" * 70)
    print(f"Receita no periodo          R$ {achados['receita_total']:>14,.2f}")
    print(f"Margem de contribuicao      R$ {achados['margem_total']:>14,.2f}"
          f"   ({achados['margem_pct']:.1f}%)")
    print("-" * 70)
    print(f"Categorias no prejuizo      {', '.join(achados['categorias_no_prejuizo']) or 'nenhuma'}")
    print(f"Prejuizo dessas categorias  R$ {achados['prejuizo_categorias']:>14,.2f}")
    print(f"Produtos com margem negativa {achados['produtos_no_prejuizo']:>13}")
    print(f"Receita desses produtos     R$ {achados['receita_produtos_prejuizo']:>14,.2f}")
    print(f"Frete subsidiado no ano     R$ {achados['frete_subsidiado_ano']:>14,.2f}")
    print(f"Clientes classe A negativos {achados['clientes_classe_a_negativos']:>14}")
    print("=" * 70)
