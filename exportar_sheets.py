"""
Exportacao para o Google Sheets - Casa Verde Distribuidora

Escreve as tabelas analiticas em uma planilha do Google, que serve de
fonte para o dashboard no Looker Studio.

Projetado para rodar no Google Colab, onde a autenticacao ja e nativa.

Uso no Colab:
    from src.exportar_sheets import exportar
    url = exportar("Casa Verde - Base Dashboard")
"""

import pandas as pd


def _autenticar():
    """
    Autentica no Google usando a sessao do Colab.

    Fora do Colab, seria necessario um arquivo de credencial de conta de
    servico, que nao entra no repositorio por ser informacao sensivel.
    """
    try:
        from google.colab import auth
        from google.auth import default
        import gspread
    except ImportError as erro:
        raise RuntimeError(
            "Este modulo foi feito para rodar no Google Colab. "
            "Instale gspread e configure credenciais para uso local."
        ) from erro

    auth.authenticate_user()
    credenciais, _ = default()
    return gspread.authorize(credenciais)


def _preparar_para_sheets(df):
    """
    Ajusta os tipos para gravacao.

    O Sheets nao aceita nulo do pandas nem tipo Period, e datas precisam
    virar texto em formato reconhecivel pelo Looker Studio.
    """
    df = df.copy()

    for coluna in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[coluna]):
            df[coluna] = df[coluna].dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_period_dtype(df[coluna]):
            df[coluna] = df[coluna].astype(str)
        elif df[coluna].dtype.name in ("category", "object"):
            df[coluna] = df[coluna].astype(str)

    return df.where(pd.notna(df), "")


def _gravar_aba(planilha, nome, df):
    df = _preparar_para_sheets(df)

    try:
        aba = planilha.worksheet(nome)
        aba.clear()
    except Exception:
        aba = planilha.add_worksheet(
            title=nome, rows=max(len(df) + 10, 100), cols=max(len(df.columns) + 2, 20)
        )

    valores = [list(df.columns)] + df.values.tolist()
    aba.update(values=valores, range_name="A1")
    aba.freeze(rows=1)
    return len(df)


def exportar(nome_planilha="Casa Verde - Base Dashboard", df=None):
    """
    Grava a base detalhada e as tabelas agregadas no Google Sheets.

    A base detalhada e a fonte principal do dashboard, porque permite ao
    Looker Studio aplicar filtros por categoria, cliente e periodo. As
    agregadas ficam disponiveis para conferencia rapida.
    """
    from limpeza import executar_limpeza
    from analise import gerar_analises

    if df is None:
        df, _ = executar_limpeza(salvar=False)

    analises = gerar_analises(df)

    # Colunas enviadas ao dashboard. Enviar a base inteira deixaria a
    # planilha lenta sem acrescentar nada ao painel.
    colunas_base = [
        "data_pedido", "ano_mes", "numero_pedido", "codigo_cliente",
        "razao_social", "segmento", "regiao", "vendedor", "codigo_produto",
        "descricao", "categoria", "quantidade", "desconto_pct",
        "receita_total", "custo_produto", "custo_entrega", "custo_comissao",
        "margem_contribuicao", "margem_pct", "frete_subsidiado",
        "tipo_operacao", "custo_confiavel",
    ]

    base = df[[c for c in colunas_base if c in df.columns]]
    base = base[base["custo_confiavel"]]

    conexao = _autenticar()

    try:
        planilha = conexao.open(nome_planilha)
    except Exception:
        planilha = conexao.create(nome_planilha)

    abas = {
        "base_detalhada": base,
        "por_categoria": analises["resumo_categoria"],
        "por_mes": analises["evolucao_mensal"],
        "por_desconto": analises["impacto_desconto"],
        "clientes": analises["ranking_clientes"],
        "produtos": analises["ranking_produtos"],
    }

    for nome, dados in abas.items():
        linhas = _gravar_aba(planilha, nome, dados)
        print(f"{nome:<16} {linhas:>6} linhas")

    # remove a aba vazia criada junto com a planilha
    try:
        planilha.del_worksheet(planilha.worksheet("Sheet1"))
    except Exception:
        pass

    print()
    print(f"Planilha disponivel em {planilha.url}")
    return planilha.url


if __name__ == "__main__":
    exportar()
