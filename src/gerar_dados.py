"""
Gerador de dados sintéticos - Casa Verde Distribuidora

Simula exportacoes de ERP de uma distribuidora de material de limpeza
e descartaveis, com faturamento aproximado de R$ 90 mil por mes.

Os dados sao gerados com defeitos propositais que replicam problemas
reais de exportacao de ERP brasileiro. O tratamento desses defeitos e
o proposito do pipeline.

Defeitos injetados:
  - CNPJ em tres formatos diferentes
  - Datas em tres formatos diferentes
  - Valores com virgula, ponto e prefixo R$
  - Nomes com espacos extras e caixa inconsistente
  - Linhas duplicadas
  - Custo ausente em parte dos produtos
  - Pedidos com cliente inexistente no cadastro
  - Devolucoes lancadas como quantidade negativa sem sinalizacao
  - Um arquivo em encoding latin-1 e separador ponto e virgula

Uso:
    python gerar_dados.py
"""

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42
PASTA_SAIDA = Path("data/raw")

ANO = 2025
N_PRODUTOS = 180
N_CLIENTES = 90
FATURAMENTO_MENSAL_ALVO = 90_000

random.seed(SEED)

# ---------------------------------------------------------------------
# Catalogos base
# ---------------------------------------------------------------------

CATEGORIAS = {
    # categoria: (margem_tabela, peso_no_mix, desconto_maximo, custo_min, custo_max)
    "Quimicos":     (0.34, 0.30, 0.10,  8.0, 42.0),
    "Papel":        (0.28, 0.22, 0.12, 12.0, 68.0),
    "Descartaveis": (0.12, 0.28, 0.25,  5.0, 38.0),   # <- o vilao do caso
    "Acessorios":   (0.41, 0.12, 0.08,  4.0, 29.0),
    "EPI":          (0.38, 0.08, 0.06,  3.0, 24.0),
}

PRODUTOS_POR_CATEGORIA = {
    "Quimicos": [
        "Detergente Neutro 5L", "Desinfetante Lavanda 5L", "Alvejante 5L",
        "Limpador Multiuso 5L", "Desengordurante 5L", "Sabao Liquido 5L",
        "Cera Liquida Incolor 5L", "Removedor 1L", "Alcool 70 1L",
        "Limpa Vidros 500ml",
    ],
    "Papel": [
        "Papel Higienico Rolao 300m", "Papel Toalha Interfolha 1000f",
        "Papel Higienico Folha Dupla 30m", "Guardanapo 24x24",
        "Bobina Papel Toalha 200m", "Papel Toalha Rolo 100f",
    ],
    "Descartaveis": [
        "Copo Descartavel 200ml", "Copo Descartavel 50ml",
        "Prato Descartavel 15cm", "Talher Descartavel Misto",
        "Saco Lixo 100L", "Saco Lixo 60L", "Saco Lixo 30L",
        "Marmitex Aluminio 800ml", "Embalagem Delivery 750ml",
        "Luva Plastica Descartavel",
    ],
    "Acessorios": [
        "Vassoura Nylon", "Rodo 40cm", "Balde 20L", "Pano Multiuso",
        "Esponja Dupla Face", "Mop Umido", "Escova Sanitaria",
        "Borrifador 500ml",
    ],
    "EPI": [
        "Luva Latex", "Bota PVC", "Oculos Protecao", "Mascara Descartavel",
        "Avental PVC",
    ],
}

UNIDADES = ["UN", "CX", "FD", "PCT", "GL"]

VENDEDORES = [
    ("V01", "Rogerio Antunes", 0.030),
    ("V02", "Simone Klein", 0.035),
    ("V03", "Tarcisio Bueno", 0.028),
]

REGIOES = ["Regiao Metropolitana", "Interior Norte", "Interior Sul", "Litoral"]

SEGMENTOS = [
    "Restaurante", "Padaria", "Mercado", "Escola",
    "Condominio", "Industria", "Clinica", "Hotel",
]

PRIMEIROS_NOMES = [
    "Alvorada", "Bandeirante", "Central", "Diamante", "Estrela", "Fenix",
    "Guarani", "Horizonte", "Imperial", "Jangada", "Luminar", "Missoes",
    "Nortao", "Oriente", "Pampa", "Querencia", "Rio Claro", "Serrano",
    "Trevo", "Uniao", "Vitoria", "Xavante", "Zenite", "Aurora", "Boreal",
]

SEGUNDOS_NOMES = [
    "Comercio", "Distribuidora", "Servicos", "Alimentos", "Empreendimentos",
    "Industria", "Participacoes", "Negocios",
]

SUFIXOS = ["LTDA", "ME", "EIRELI", "S/A", "LTDA ME"]


# ---------------------------------------------------------------------
# Utilitarios de sujeira
# ---------------------------------------------------------------------

def gerar_cnpj():
    """CNPJ aleatorio sem validacao de digito verificador."""
    return "".join(str(random.randint(0, 9)) for _ in range(14))


def sujar_cnpj(cnpj):
    """Aplica um dos tres formatos encontrados em exportacoes de ERP."""
    formato = random.choices(["mascarado", "limpo", "espacado"], [0.55, 0.35, 0.10])[0]
    if formato == "mascarado":
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    if formato == "espacado":
        return f" {cnpj} "
    return cnpj


def sujar_data(d):
    """Datas em tres formatos, como acontece quando o ERP mistura origens."""
    formato = random.choices(["br", "iso", "curto"], [0.60, 0.30, 0.10])[0]
    if formato == "br":
        return d.strftime("%d/%m/%Y")
    if formato == "iso":
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d-%m-%y")


def sujar_valor(v):
    """Valores com virgula, ponto e prefixo de moeda."""
    formato = random.choices(["virgula", "ponto", "moeda"], [0.60, 0.30, 0.10])[0]
    if formato == "virgula":
        return f"{v:.2f}".replace(".", ",")
    if formato == "moeda":
        return f"R$ {v:.2f}".replace(".", ",")
    return f"{v:.2f}"


def sujar_texto(t):
    """Espacos extras e caixa inconsistente."""
    escolha = random.random()
    if escolha < 0.12:
        return f"  {t.upper()}  "
    if escolha < 0.20:
        return t.lower()
    if escolha < 0.26:
        return f"{t} "
    return t


# ---------------------------------------------------------------------
# Geracao das entidades
# ---------------------------------------------------------------------

def gerar_produtos():
    produtos = []
    codigo = 1000

    for categoria, nomes in PRODUTOS_POR_CATEGORIA.items():
        margem, _, _, custo_min, custo_max = CATEGORIAS[categoria]
        # replica cada nome em variacoes de embalagem para chegar ao volume
        variacoes = max(1, N_PRODUTOS // sum(len(v) for v in PRODUTOS_POR_CATEGORIA.values()))
        for nome in nomes:
            for i in range(variacoes + random.randint(0, 1)):
                codigo += 1
                unidade = random.choice(UNIDADES)
                custo = round(random.uniform(custo_min, custo_max), 2)
                preco_tabela = round(custo / (1 - margem), 2)

                sufixo_variacao = "" if i == 0 else f" - {random.choice(['Fardo 6', 'Fardo 12', 'Caixa 24', 'Pacote 100'])}"

                produtos.append({
                    "codigo_produto": f"P{codigo}",
                    "descricao": sujar_texto(nome + sufixo_variacao),
                    "categoria": categoria,
                    "unidade": unidade,
                    "custo_unitario": sujar_valor(custo),
                    "preco_tabela": sujar_valor(preco_tabela),
                    "ativo": random.choices(["S", "N"], [0.92, 0.08])[0],
                })

    produtos = produtos[:N_PRODUTOS]

    # defeito: custo ausente em parte do cadastro
    for p in random.sample(produtos, k=int(len(produtos) * 0.06)):
        p["custo_unitario"] = ""

    return pd.DataFrame(produtos)


def gerar_clientes():
    clientes = []
    usados = set()

    for i in range(N_CLIENTES):
        while True:
            nome = f"{random.choice(PRIMEIROS_NOMES)} {random.choice(SEGUNDOS_NOMES)} {random.choice(SUFIXOS)}"
            if nome not in usados:
                usados.add(nome)
                break

        abertura = date(ANO - random.randint(1, 12), random.randint(1, 12), random.randint(1, 28))

        clientes.append({
            "codigo_cliente": f"C{2000 + i}",
            "razao_social": sujar_texto(nome),
            "cnpj": sujar_cnpj(gerar_cnpj()),
            "segmento": random.choice(SEGMENTOS),
            "regiao": random.choice(REGIOES),
            "vendedor": random.choice(VENDEDORES)[0],
            "data_cadastro": sujar_data(abertura),
            "limite_credito": sujar_valor(round(random.uniform(2000, 40000), 2)),
        })

    return pd.DataFrame(clientes)


def _sortear_produto(df_produtos):
    """Sorteia produto respeitando o peso de cada categoria no mix."""
    categoria = random.choices(
        list(CATEGORIAS.keys()),
        [c[1] for c in CATEGORIAS.values()],
    )[0]
    candidatos = df_produtos[df_produtos["categoria"] == categoria]
    if candidatos.empty:
        candidatos = df_produtos
    return candidatos.sample(1).iloc[0]


def gerar_vendas(df_produtos, df_clientes):
    linhas = []
    numero_pedido = 50000

    # curva ABC de clientes: poucos concentram o volume
    pesos_clientes = [random.paretovariate(1.4) for _ in range(len(df_clientes))]

    dia = date(ANO, 1, 1)
    fim = date(ANO, 12, 31)

    while dia <= fim:
        # sem venda em domingo, volume menor no sabado
        if dia.weekday() == 6:
            dia += timedelta(days=1)
            continue

        pedidos_do_dia = random.randint(3, 10) if dia.weekday() < 5 else random.randint(1, 3)

        # sazonalidade: dezembro e marco mais fortes
        if dia.month in (3, 12):
            pedidos_do_dia += 2

        for _ in range(pedidos_do_dia):
            numero_pedido += 1
            cliente = df_clientes.sample(1, weights=pesos_clientes).iloc[0]
            n_itens = random.choices([1, 2, 3, 4, 5, 6, 7], [16, 24, 23, 17, 11, 6, 3])[0]

            valor_pedido = 0
            itens_pedido = []

            for seq in range(1, n_itens + 1):
                produto = _sortear_produto(df_produtos)
                categoria = produto["categoria"]
                _, _, desconto_max, _, _ = CATEGORIAS[categoria]

                preco_tabela = float(
                    str(produto["preco_tabela"]).replace("R$", "").replace(" ", "").replace(",", ".")
                )

                quantidade = random.choices([1, 2, 3, 5, 10, 20, 50], [26, 24, 19, 14, 10, 5, 2])[0]

                # desconto cresce com a quantidade e com o teto da categoria
                fator_volume = min(quantidade / 50, 1.0)
                desconto = round(random.uniform(0, desconto_max) * (0.4 + 0.6 * fator_volume), 4)

                preco_praticado = round(preco_tabela * (1 - desconto), 2)
                valor_item = round(preco_praticado * quantidade, 2)
                valor_pedido += valor_item

                itens_pedido.append({
                    "numero_pedido": numero_pedido,
                    "sequencia_item": seq,
                    "data_pedido": dia,
                    "codigo_cliente": cliente["codigo_cliente"],
                    "codigo_produto": produto["codigo_produto"],
                    "quantidade": quantidade,
                    "preco_unitario": preco_praticado,
                    "desconto_pct": round(desconto * 100, 2),
                    "categoria_ref": categoria,
                })

            # regra de frete: gratis acima de 800, e o custo fica com a empresa.
            # itens volumosos custam mais para entregar.
            peso_volumetrico = sum(
                2.5 if i["categoria_ref"] in ("Descartaveis", "Papel") else 1.0
                for i in itens_pedido
            )
            custo_frete = round(28 + peso_volumetrico * random.uniform(4, 9), 2)
            frete_gratis = valor_pedido >= 600
            frete_cobrado = 0.0 if frete_gratis else round(custo_frete * 0.7, 2)

            for item in itens_pedido:
                proporcao = (item["preco_unitario"] * item["quantidade"]) / valor_pedido
                linhas.append({
                    "numero_pedido": item["numero_pedido"],
                    "sequencia_item": item["sequencia_item"],
                    "data_pedido": sujar_data(item["data_pedido"]),
                    "codigo_cliente": item["codigo_cliente"],
                    "codigo_produto": item["codigo_produto"],
                    "quantidade": item["quantidade"],
                    "preco_unitario": sujar_valor(item["preco_unitario"]),
                    "desconto_pct": sujar_valor(item["desconto_pct"]),
                    "frete_cobrado": sujar_valor(round(frete_cobrado * proporcao, 2)),
                    "custo_frete_real": sujar_valor(round(custo_frete * proporcao, 2)),
                    "vendedor": cliente["vendedor"],
                    "status": random.choices(
                        ["FATURADO", "faturado", "Faturado", "CANCELADO"],
                        [0.70, 0.12, 0.12, 0.06],
                    )[0],
                })

        dia += timedelta(days=1)

    df = pd.DataFrame(linhas)

    # defeito: duplicacao de exportacao, a mesma chave pedido+item repetida
    duplicatas = df.sample(frac=0.012, random_state=SEED)
    df = pd.concat([df, duplicatas], ignore_index=True)

    # defeito: devolucoes lancadas como quantidade negativa sem sinalizacao
    indices = random.sample(range(len(df)), k=int(len(df) * 0.015))
    df.loc[indices, "quantidade"] = df.loc[indices, "quantidade"] * -1

    # defeito: pedidos apontando para cliente inexistente
    indices = random.sample(range(len(df)), k=int(len(df) * 0.008))
    df.loc[indices, "codigo_cliente"] = "C9999"

    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


# ---------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------

def main():
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)

    print("Gerando produtos...")
    df_produtos = gerar_produtos()

    print("Gerando clientes...")
    df_clientes = gerar_clientes()

    print("Gerando vendas...")
    df_vendas = gerar_vendas(df_produtos, df_clientes)

    # vendas: padrao brasileiro de ERP, ponto e virgula e latin-1
    df_vendas.to_csv(
        PASTA_SAIDA / "vendas.csv",
        sep=";", index=False, encoding="latin-1", errors="replace",
    )

    df_produtos.to_csv(
        PASTA_SAIDA / "produtos.csv",
        sep=";", index=False, encoding="utf-8",
    )

    # clientes: exportado de outro modulo, por isso o separador muda
    df_clientes.to_csv(
        PASTA_SAIDA / "clientes.csv",
        sep=",", index=False, encoding="utf-8",
    )

    print()
    print(f"produtos.csv  {len(df_produtos):>6} linhas")
    print(f"clientes.csv  {len(df_clientes):>6} linhas")
    print(f"vendas.csv    {len(df_vendas):>6} linhas")
    print()
    print(f"Arquivos gravados em {PASTA_SAIDA.resolve()}")


if __name__ == "__main__":
    main()
