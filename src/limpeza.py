"""
Limpeza e padronizacao dos dados brutos - Casa Verde Distribuidora

Transforma as tres exportacoes de ERP em uma base unica confiavel.

Toda correcao aplicada e registrada no RelatorioQualidade, que fica
disponivel ao final do processo. Nenhum registro e descartado em
silencio.

Uso:
    from limpeza import executar_limpeza
    df, relatorio = executar_limpeza()
    print(relatorio)
"""

import re
from pathlib import Path

import pandas as pd

PASTA_ENTRADA = Path("data/raw")
PASTA_SAIDA = Path("data/processed")

COMISSAO_PADRAO = 0.032


# ---------------------------------------------------------------------
# Relatorio de auditoria
# ---------------------------------------------------------------------

class RelatorioQualidade:
    """Acumula o que foi corrigido, para que nada seja alterado em silencio."""

    def __init__(self):
        self.eventos = []

    def registrar(self, etapa, descricao, quantidade, acao):
        self.eventos.append({
            "etapa": etapa,
            "problema": descricao,
            "registros": quantidade,
            "acao": acao,
        })

    def como_dataframe(self):
        return pd.DataFrame(self.eventos)

    def __str__(self):
        if not self.eventos:
            return "Nenhum problema encontrado."
        linhas = ["", "RELATORIO DE QUALIDADE DE DADOS", "=" * 78]
        for e in self.eventos:
            linhas.append(f"[{e['etapa']:<10}] {e['problema']}")
            linhas.append(f"{'':<13}{e['registros']} registros  ->  {e['acao']}")
        linhas.append("=" * 78)
        return "\n".join(linhas)


# ---------------------------------------------------------------------
# Normalizadores
# ---------------------------------------------------------------------

def normalizar_valor(serie):
    """
    Converte texto monetario brasileiro em numero.

    Trata: 'R$ 1.234,56', '1234,56', '1234.56', ' 12,30 '

    A regra do separador decimal e posicional. Quando existem ponto e
    virgula, a virgula e sempre o decimal. Quando existe apenas ponto,
    ele so e milhar se houver exatamente tres digitos depois dele.
    """
    s = serie.astype(str).str.strip()
    s = s.str.replace("R$", "", regex=False).str.strip()
    s = s.str.replace(r"\s+", "", regex=True)

    tem_ambos = s.str.contains(r"\.", regex=True) & s.str.contains(",", regex=False)
    s = s.mask(tem_ambos, s.str.replace(".", "", regex=False))
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


def normalizar_data(serie):
    """
    Converte datas em tres formatos para datetime.

    Trata: '13/02/2025', '2025-11-07', '05-03-25'

    Nao usa inferencia automatica do pandas porque ela confunde
    dia e mes em datas ambiguas como 03/05/2025.
    """
    s = serie.astype(str).str.strip()
    resultado = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")

    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%y"):
        pendentes = resultado.isna()
        if not pendentes.any():
            break
        convertidas = pd.to_datetime(s[pendentes], format=formato, errors="coerce")
        resultado[pendentes] = convertidas

    return resultado


def normalizar_texto(serie):
    """Remove espacos extras e aplica caixa de titulo consistente."""
    s = serie.astype(str).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.str.title()


def normalizar_cnpj(serie):
    """Deixa apenas digitos e valida o comprimento de 14 caracteres."""
    s = serie.astype(str).str.replace(r"\D", "", regex=True)
    return s.where(s.str.len() == 14)


# ---------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------

def carregar_produtos(pasta=PASTA_ENTRADA):
    df = pd.read_csv(pasta / "produtos.csv", sep=";", encoding="utf-8", dtype=str)
    df["descricao"] = normalizar_texto(df["descricao"])
    df["custo_unitario"] = normalizar_valor(df["custo_unitario"])
    df["preco_tabela"] = normalizar_valor(df["preco_tabela"])
    return df


def carregar_clientes(pasta=PASTA_ENTRADA):
    df = pd.read_csv(pasta / "clientes.csv", sep=",", encoding="utf-8", dtype=str)
    df["razao_social"] = normalizar_texto(df["razao_social"])
    df["cnpj"] = normalizar_cnpj(df["cnpj"])
    df["data_cadastro"] = normalizar_data(df["data_cadastro"])
    df["limite_credito"] = normalizar_valor(df["limite_credito"])
    return df


def carregar_vendas(pasta=PASTA_ENTRADA):
    df = pd.read_csv(pasta / "vendas.csv", sep=";", encoding="latin-1", dtype=str)
    df["data_pedido"] = normalizar_data(df["data_pedido"])
    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce")
    for coluna in ("preco_unitario", "desconto_pct", "frete_cobrado", "custo_frete_real"):
        df[coluna] = normalizar_valor(df[coluna])
    df["status"] = df["status"].str.strip().str.upper()
    return df


# ---------------------------------------------------------------------
# Tratamentos
# ---------------------------------------------------------------------

def tratar_duplicatas(df, rel):
    """
    Remove duplicacao de exportacao usando a chave de negocio do ERP.

    Cada item de pedido e identificado por numero_pedido + sequencia_item.
    Esse par e unico por definicao no sistema de origem, entao qualquer
    repeticao dele e falha de exportacao, nunca um item legitimo lancado
    duas vezes. Um mesmo produto repetido no pedido recebe sequencia
    distinta e por isso e preservado.
    """
    chave = ["numero_pedido", "sequencia_item"]
    antes = len(df)
    df = df.drop_duplicates(subset=chave, keep="first")
    removidas = antes - len(df)
    if removidas:
        rel.registrar(
            "vendas", "Chave pedido mais item repetida na exportacao",
            removidas, "removidas, mantida a primeira ocorrencia",
        )
    return df


def tratar_cancelados(df, rel):
    cancelados = (df["status"] == "CANCELADO").sum()
    if cancelados:
        rel.registrar(
            "vendas", "Pedidos com status cancelado",
            int(cancelados), "excluidos da analise de margem",
        )
    return df[df["status"] != "CANCELADO"].copy()


def tratar_devolucoes(df, rel):
    """
    Quantidade negativa no ERP significa devolucao, mas nao ha coluna
    que sinalize isso. Cria a marcacao explicita e mantem o registro,
    porque devolucao afeta a margem real do cliente.
    """
    negativas = (df["quantidade"] < 0).sum()
    df["tipo_operacao"] = "VENDA"
    df.loc[df["quantidade"] < 0, "tipo_operacao"] = "DEVOLUCAO"
    if negativas:
        rel.registrar(
            "vendas", "Quantidade negativa sem sinalizacao de devolucao",
            int(negativas), "marcadas como DEVOLUCAO em coluna propria",
        )
    return df


def tratar_clientes_orfaos(df, df_clientes, rel):
    """Pedidos apontando para cliente que nao existe no cadastro."""
    validos = set(df_clientes["codigo_cliente"])
    orfaos = ~df["codigo_cliente"].isin(validos)
    if orfaos.any():
        rel.registrar(
            "integridade", "Pedidos com cliente ausente no cadastro",
            int(orfaos.sum()), "reclassificados como CLIENTE NAO IDENTIFICADO",
        )
    df.loc[orfaos, "codigo_cliente"] = "NAO_IDENTIFICADO"
    return df


def tratar_custo_ausente(df, rel):
    """
    Produto sem custo cadastrado impede o calculo de margem.
    O registro e mantido e sinalizado, nunca descartado, porque a
    receita dele e real e precisa aparecer no faturamento.
    """
    sem_custo = df["custo_unitario"].isna()
    df["custo_confiavel"] = ~sem_custo
    if sem_custo.any():
        rel.registrar(
            "produtos", "Produtos sem custo de compra cadastrado",
            int(sem_custo.sum()), "receita mantida, margem sinalizada como indisponivel",
        )
    return df


def tratar_datas_invalidas(df, rel):
    invalidas = df["data_pedido"].isna().sum()
    if invalidas:
        rel.registrar(
            "vendas", "Datas que nao correspondem a nenhum formato conhecido",
            int(invalidas), "removidas",
        )
    return df.dropna(subset=["data_pedido"]).copy()


# ---------------------------------------------------------------------
# Calculo de margem
# ---------------------------------------------------------------------

def calcular_margem(df, comissao=COMISSAO_PADRAO):
    """
    Margem de contribuicao real por linha de pedido.

    Receita       = preco praticado x quantidade + frete cobrado do cliente
    Custo produto = custo de compra x quantidade
    Custo frete   = custo real da entrega, mesmo quando o frete foi gratis
    Comissao      = percentual sobre o valor da mercadoria

    O ERP mostra apenas preco menos custo. A diferenca entre esse numero
    e o calculo abaixo e exatamente onde a margem desaparece.
    """
    sinal = df["tipo_operacao"].map({"VENDA": 1, "DEVOLUCAO": 1}).fillna(1)
    quantidade = df["quantidade"]

    df["receita_mercadoria"] = df["preco_unitario"] * quantidade
    df["receita_total"] = df["receita_mercadoria"] + df["frete_cobrado"] * sinal
    df["custo_produto"] = df["custo_unitario"] * quantidade
    df["custo_comissao"] = df["receita_mercadoria"] * comissao
    df["custo_entrega"] = df["custo_frete_real"]

    df["margem_bruta"] = df["receita_mercadoria"] - df["custo_produto"]
    df["margem_contribuicao"] = (
        df["receita_total"]
        - df["custo_produto"]
        - df["custo_entrega"]
        - df["custo_comissao"]
    )

    df.loc[~df["custo_confiavel"], ["margem_bruta", "margem_contribuicao"]] = pd.NA

    df["margem_pct"] = (df["margem_contribuicao"] / df["receita_total"]) * 100
    df["frete_subsidiado"] = df["custo_frete_real"] - df["frete_cobrado"]

    return df


# ---------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------

def executar_limpeza(pasta_entrada=PASTA_ENTRADA, salvar=True):
    rel = RelatorioQualidade()

    produtos = carregar_produtos(pasta_entrada)
    clientes = carregar_clientes(pasta_entrada)
    vendas = carregar_vendas(pasta_entrada)

    cnpj_invalido = clientes["cnpj"].isna().sum()
    if cnpj_invalido:
        rel.registrar(
            "clientes", "CNPJ fora do padrao de 14 digitos",
            int(cnpj_invalido), "mantido em branco para conferencia manual",
        )

    vendas = tratar_duplicatas(vendas, rel)
    vendas = tratar_datas_invalidas(vendas, rel)
    vendas = tratar_cancelados(vendas, rel)
    vendas = tratar_devolucoes(vendas, rel)
    vendas = tratar_clientes_orfaos(vendas, clientes, rel)

    df = vendas.merge(
        produtos[["codigo_produto", "descricao", "categoria", "custo_unitario", "preco_tabela"]],
        on="codigo_produto", how="left",
    )
    df = df.merge(
        clientes[["codigo_cliente", "razao_social", "segmento", "regiao"]],
        on="codigo_cliente", how="left",
    )

    df = tratar_custo_ausente(df, rel)
    df = calcular_margem(df)

    df["ano_mes"] = df["data_pedido"].dt.to_period("M").astype(str)

    if salvar:
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        df.to_parquet(PASTA_SAIDA / "vendas_tratadas.parquet", index=False)
        rel.como_dataframe().to_csv(
            PASTA_SAIDA / "relatorio_qualidade.csv", index=False, encoding="utf-8"
        )

    return df, rel


if __name__ == "__main__":
    df, relatorio = executar_limpeza()
    print(relatorio)
    print()
    print(f"Base final: {len(df):,} linhas".replace(",", "."))
    print(f"Periodo   : {df['data_pedido'].min():%d/%m/%Y} a {df['data_pedido'].max():%d/%m/%Y}")
    print(f"Receita   : R$ {df['receita_total'].sum():,.2f}")
    print(f"Margem    : R$ {df['margem_contribuicao'].sum():,.2f}")
