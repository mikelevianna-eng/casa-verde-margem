"""
Testes do modulo de analise.

As regras testadas aqui sao regras de negocio, nao de codigo. Se uma
delas quebrar, o relatorio entregue ao cliente estara errado mesmo que
o programa rode sem erro. Esse e o tipo de falha que passa despercebida
sem teste.

Execucao:
    pytest -v
"""

import pandas as pd
import pytest

from src.analise import (
    _classificar_margem,
    _curva_abc,
    resumo_categoria,
    produtos_prejuizo,
    ranking_clientes,
    custo_frete_gratis,
    impacto_desconto,
    evolucao_mensal,
)


# ---------------------------------------------------------------------
# Base de apoio
# ---------------------------------------------------------------------

def base_exemplo():
    """
    Base minima e controlada, com um caso de cada situacao.

    Descartaveis entra no vermelho, Quimicos fica saudavel, e ha um
    registro sem custo confiavel que precisa ser ignorado na margem.
    """
    linhas = [
        # categoria, receita, margem, frete_sub, custo_entrega, desconto, confiavel
        ("Descartaveis", 5000.0, -400.0, 600.0, 700.0, 18.0, True),
        ("Descartaveis", 3000.0, -100.0, 350.0, 400.0, 12.0, True),
        ("Quimicos",     8000.0, 2000.0, 300.0, 380.0,  3.0, True),
        ("Quimicos",     4000.0, 1000.0, 150.0, 190.0,  2.0, True),
        ("Papel",        2000.0,  100.0, 200.0, 260.0,  8.0, True),
        ("Papel",        9999.0, 9999.0,   0.0,   0.0,  0.0, False),
    ]

    registros = []
    for i, (cat, rec, mar, sub, ent, desc, conf) in enumerate(linhas):
        registros.append({
            "numero_pedido": 100 + i,
            "sequencia_item": 1,
            "codigo_produto": f"P{i}",
            "descricao": f"Produto {i}",
            "categoria": cat,
            "codigo_cliente": f"C{i % 3}",
            "razao_social": f"Cliente {i % 3}",
            "segmento": "Mercado",
            "regiao": "Interior Sul",
            "quantidade": 10,
            "desconto_pct": desc,
            "receita_total": rec,
            "margem_contribuicao": mar if conf else pd.NA,
            "custo_entrega": ent,
            "frete_cobrado": ent - sub,
            "frete_subsidiado": sub,
            "custo_confiavel": conf,
            "ano_mes": "2025-01" if i < 3 else "2025-02",
        })

    return pd.DataFrame(registros)


# ---------------------------------------------------------------------
# Classificacao
# ---------------------------------------------------------------------

class TestClassificarMargem:

    def test_margem_negativa_e_prejuizo(self):
        assert _classificar_margem(-3.0) == "PREJUIZO"

    def test_zero_nao_e_prejuizo(self):
        """Margem zero nao da lucro, mas tambem nao destroi resultado."""
        assert _classificar_margem(0.0) == "CRITICA"

    def test_abaixo_do_limite_de_atencao_e_critica(self):
        assert _classificar_margem(6.0) == "CRITICA"

    def test_entre_os_limites_e_atencao(self):
        assert _classificar_margem(15.0) == "ATENCAO"

    def test_acima_do_saudavel(self):
        assert _classificar_margem(25.0) == "SAUDAVEL"

    def test_nulo_vira_sem_custo(self):
        assert _classificar_margem(pd.NA) == "SEM CUSTO"


# ---------------------------------------------------------------------
# Curva ABC
# ---------------------------------------------------------------------

class TestCurvaAbc:

    def test_corte_usa_receita_acumulada_e_nao_contagem(self):
        """
        Erro classico: dividir a lista em 20, 30 e 50 por cento dos
        itens. O criterio correto e a receita acumulada.
        """
        df = pd.DataFrame({
            "item": ["a", "b", "c", "d"],
            "receita": [800.0, 150.0, 30.0, 20.0],
        })
        r = _curva_abc(df, "receita")
        classes = dict(zip(r["item"], r["classe_abc"]))
        assert classes["a"] == "A"
        assert classes["b"] == "B"
        assert classes["d"] == "C"

    def test_ordenacao_decrescente(self):
        df = pd.DataFrame({"item": ["x", "y"], "receita": [10.0, 90.0]})
        r = _curva_abc(df, "receita")
        assert r.iloc[0]["item"] == "y"

    def test_acumulado_termina_em_cem(self):
        df = pd.DataFrame({"item": ["x", "y"], "receita": [40.0, 60.0]})
        r = _curva_abc(df, "receita")
        assert r["receita_acumulada_pct"].iloc[-1] == pytest.approx(100.0)


# ---------------------------------------------------------------------
# Analises
# ---------------------------------------------------------------------

class TestResumoCategoria:

    def test_ignora_registros_sem_custo_confiavel(self):
        r = resumo_categoria(base_exemplo())
        papel = r[r["categoria"] == "Papel"].iloc[0]
        assert papel["receita"] == pytest.approx(2000.0)

    def test_identifica_categoria_no_prejuizo(self):
        r = resumo_categoria(base_exemplo())
        desc = r[r["categoria"] == "Descartaveis"].iloc[0]
        assert desc["margem"] < 0
        assert desc["situacao"] == "PREJUIZO"

    def test_participacao_soma_cem_por_cento(self):
        r = resumo_categoria(base_exemplo())
        assert r["participacao_receita_pct"].sum() == pytest.approx(100.0, abs=0.2)

    def test_ordenado_da_pior_margem_para_a_melhor(self):
        r = resumo_categoria(base_exemplo())
        assert r.iloc[0]["categoria"] == "Descartaveis"


class TestProdutosPrejuizo:

    def test_traz_apenas_margem_negativa(self):
        r = produtos_prejuizo(base_exemplo(), minimo_receita=0)
        assert (r["margem"] < 0).all()

    def test_filtro_de_receita_minima_exclui_itens_irrelevantes(self):
        r = produtos_prejuizo(base_exemplo(), minimo_receita=4000)
        assert len(r) == 1
        assert r.iloc[0]["receita"] >= 4000


class TestRankingClientes:

    def test_exclui_cliente_nao_identificado(self):
        df = base_exemplo()
        df.loc[0, "codigo_cliente"] = "NAO_IDENTIFICADO"
        r = ranking_clientes(df)
        assert "NAO_IDENTIFICADO" not in r["codigo_cliente"].values

    def test_ticket_medio_e_receita_sobre_pedidos(self):
        r = ranking_clientes(base_exemplo())
        linha = r.iloc[0]
        assert linha["ticket_medio"] == pytest.approx(
            linha["receita"] / linha["pedidos"], rel=0.01
        )


class TestCustoFreteGratis:

    def test_margem_sem_subsidio_e_sempre_maior(self):
        r = custo_frete_gratis(base_exemplo())
        assert (r["margem_sem_subsidio"] >= r["margem"]).all()

    def test_subsidio_reverte_o_prejuizo_de_descartaveis(self):
        """A afirmacao central do relatorio precisa estar sustentada."""
        r = custo_frete_gratis(base_exemplo())
        desc = r[r["categoria"] == "Descartaveis"].iloc[0]
        assert desc["margem"] < 0
        assert desc["margem_sem_subsidio"] > 0


class TestImpactoDesconto:

    def test_todas_as_linhas_caem_em_alguma_faixa(self):
        df = base_exemplo()
        r = impacto_desconto(df)
        confiaveis = df["custo_confiavel"].sum()
        assert r["linhas"].sum() == confiaveis

    def test_desconto_zero_entra_na_primeira_faixa(self):
        df = base_exemplo()
        df.loc[:, "desconto_pct"] = 0.0
        r = impacto_desconto(df)
        assert r["linhas"].iloc[0] == df["custo_confiavel"].sum()


class TestEvolucaoMensal:

    def test_um_registro_por_mes(self):
        r = evolucao_mensal(base_exemplo())
        assert len(r) == r["ano_mes"].nunique()

    def test_receita_total_bate_com_a_base(self):
        df = base_exemplo()
        r = evolucao_mensal(df)
        esperado = df[df["custo_confiavel"]]["receita_total"].sum()
        assert r["receita"].sum() == pytest.approx(esperado)
