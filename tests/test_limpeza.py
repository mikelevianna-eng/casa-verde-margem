"""
Testes do modulo de limpeza.

Cada teste cobre um defeito real encontrado em exportacao de ERP.
Os casos sao escritos a mao, nao gerados, para que a falha aponte
exatamente qual regra quebrou.

Execucao:
    pytest -v
"""

import pandas as pd
import pytest

from src.limpeza import (
    normalizar_valor,
    normalizar_data,
    normalizar_texto,
    normalizar_cnpj,
    tratar_duplicatas,
    tratar_devolucoes,
    tratar_custo_ausente,
    calcular_margem,
    RelatorioQualidade,
)


# ---------------------------------------------------------------------
# normalizar_valor
# ---------------------------------------------------------------------

class TestNormalizarValor:

    def test_virgula_como_decimal(self):
        r = normalizar_valor(pd.Series(["1234,56"]))
        assert r.iloc[0] == pytest.approx(1234.56)

    def test_ponto_como_decimal(self):
        r = normalizar_valor(pd.Series(["1234.56"]))
        assert r.iloc[0] == pytest.approx(1234.56)

    def test_ponto_milhar_com_virgula_decimal(self):
        """O erro mais caro da conversao: 1.234,56 virando 1,23."""
        r = normalizar_valor(pd.Series(["1.234,56"]))
        assert r.iloc[0] == pytest.approx(1234.56)

    def test_prefixo_moeda(self):
        r = normalizar_valor(pd.Series(["R$ 89,90"]))
        assert r.iloc[0] == pytest.approx(89.90)

    def test_espacos_ao_redor(self):
        r = normalizar_valor(pd.Series(["  42,00  "]))
        assert r.iloc[0] == pytest.approx(42.00)

    def test_valor_vazio_vira_nulo(self):
        r = normalizar_valor(pd.Series([""]))
        assert pd.isna(r.iloc[0])

    def test_texto_invalido_vira_nulo(self):
        r = normalizar_valor(pd.Series(["consultar"]))
        assert pd.isna(r.iloc[0])

    def test_formatos_misturados_na_mesma_coluna(self):
        entrada = pd.Series(["1.234,56", "89.90", "R$ 12,30", "  7,00 "])
        r = normalizar_valor(entrada)
        assert r.tolist() == pytest.approx([1234.56, 89.90, 12.30, 7.00])


# ---------------------------------------------------------------------
# normalizar_data
# ---------------------------------------------------------------------

class TestNormalizarData:

    def test_formato_brasileiro(self):
        r = normalizar_data(pd.Series(["13/02/2025"]))
        assert r.iloc[0] == pd.Timestamp("2025-02-13")

    def test_formato_iso(self):
        r = normalizar_data(pd.Series(["2025-11-07"]))
        assert r.iloc[0] == pd.Timestamp("2025-11-07")

    def test_formato_curto_com_hifen(self):
        r = normalizar_data(pd.Series(["05-03-25"]))
        assert r.iloc[0] == pd.Timestamp("2025-03-05")

    def test_data_ambigua_respeita_padrao_brasileiro(self):
        """
        03/05/2025 e 5 de marco no Brasil.
        A inferencia automatica do pandas leria como 3 de maio.
        """
        r = normalizar_data(pd.Series(["03/05/2025"]))
        assert r.iloc[0].month == 5
        assert r.iloc[0].day == 3

    def test_formatos_misturados_na_mesma_coluna(self):
        entrada = pd.Series(["13/02/2025", "2025-11-07", "05-03-25"])
        r = normalizar_data(entrada)
        assert r.notna().all()

    def test_data_invalida_vira_nulo(self):
        r = normalizar_data(pd.Series(["sem data"]))
        assert pd.isna(r.iloc[0])


# ---------------------------------------------------------------------
# normalizar_texto e cnpj
# ---------------------------------------------------------------------

class TestNormalizarTexto:

    def test_mesma_entidade_com_grafias_diferentes_converge(self):
        entrada = pd.Series(["  DETERGENTE NEUTRO 5L  ", "detergente neutro 5l"])
        r = normalizar_texto(entrada)
        assert r.nunique() == 1

    def test_espacos_internos_multiplos(self):
        r = normalizar_texto(pd.Series(["Copo    Descartavel"]))
        assert r.iloc[0] == "Copo Descartavel"


class TestNormalizarCnpj:

    def test_mascarado_e_limpo_convergem(self):
        entrada = pd.Series(["54.629.148/6528-16", "54629148652816"])
        r = normalizar_cnpj(entrada)
        assert r.nunique() == 1

    def test_comprimento_invalido_vira_nulo(self):
        r = normalizar_cnpj(pd.Series(["123"]))
        assert pd.isna(r.iloc[0])


# ---------------------------------------------------------------------
# Tratamentos
# ---------------------------------------------------------------------

class TestTratarDuplicatas:

    def test_remove_chave_repetida(self):
        df = pd.DataFrame({
            "numero_pedido": [1, 1, 1],
            "sequencia_item": [1, 2, 2],
            "valor": [10, 20, 20],
        })
        r = tratar_duplicatas(df, RelatorioQualidade())
        assert len(r) == 2

    def test_preserva_produto_repetido_com_sequencia_distinta(self):
        """
        O mesmo produto pode ser lancado duas vezes no pedido de forma
        legitima. A sequencia diferencia, e a linha nao pode sumir.
        """
        df = pd.DataFrame({
            "numero_pedido": [1, 1],
            "sequencia_item": [1, 2],
            "codigo_produto": ["P1", "P1"],
            "quantidade": [5, 5],
        })
        r = tratar_duplicatas(df, RelatorioQualidade())
        assert len(r) == 2

    def test_registra_no_relatorio(self):
        df = pd.DataFrame({"numero_pedido": [1, 1], "sequencia_item": [1, 1]})
        rel = RelatorioQualidade()
        tratar_duplicatas(df, rel)
        assert len(rel.eventos) == 1
        assert rel.eventos[0]["registros"] == 1


class TestTratarDevolucoes:

    def test_marca_negativa_como_devolucao(self):
        df = pd.DataFrame({"quantidade": [10, -3, 5]})
        r = tratar_devolucoes(df, RelatorioQualidade())
        assert r["tipo_operacao"].tolist() == ["VENDA", "DEVOLUCAO", "VENDA"]

    def test_nao_descarta_a_devolucao(self):
        df = pd.DataFrame({"quantidade": [10, -3]})
        r = tratar_devolucoes(df, RelatorioQualidade())
        assert len(r) == 2


class TestTratarCustoAusente:

    def test_sinaliza_sem_remover_a_linha(self):
        df = pd.DataFrame({"custo_unitario": [10.0, None, 5.0]})
        r = tratar_custo_ausente(df, RelatorioQualidade())
        assert len(r) == 3
        assert r["custo_confiavel"].tolist() == [True, False, True]


# ---------------------------------------------------------------------
# calcular_margem
# ---------------------------------------------------------------------

def _linha_base(**kwargs):
    """Monta uma linha de pedido com valores controlados."""
    dados = {
        "quantidade": 10,
        "preco_unitario": 20.0,
        "custo_unitario": 12.0,
        "frete_cobrado": 0.0,
        "custo_frete_real": 50.0,
        "tipo_operacao": "VENDA",
        "custo_confiavel": True,
    }
    dados.update(kwargs)
    return pd.DataFrame([dados])


class TestCalcularMargem:

    def test_margem_bruta_ignora_frete_e_comissao(self):
        r = calcular_margem(_linha_base(), comissao=0.0)
        # 10 x 20 menos 10 x 12
        assert r["margem_bruta"].iloc[0] == pytest.approx(80.0)

    def test_margem_contribuicao_desconta_frete_e_comissao(self):
        r = calcular_margem(_linha_base(), comissao=0.03)
        # 200 de receita, 120 de custo, 50 de frete, 6 de comissao
        assert r["margem_contribuicao"].iloc[0] == pytest.approx(24.0)

    def test_frete_absorvido_pode_zerar_a_margem(self):
        """
        O caso central do projeto. A margem bruta e positiva e a margem
        real e negativa, e so o segundo numero paga as contas.
        """
        r = calcular_margem(_linha_base(custo_frete_real=95.0), comissao=0.03)
        assert r["margem_bruta"].iloc[0] > 0
        assert r["margem_contribuicao"].iloc[0] < 0

    def test_frete_subsidiado_e_a_diferenca_nao_cobrada(self):
        r = calcular_margem(_linha_base(custo_frete_real=50.0, frete_cobrado=18.0))
        assert r["frete_subsidiado"].iloc[0] == pytest.approx(32.0)

    def test_margem_indisponivel_quando_custo_nao_e_confiavel(self):
        r = calcular_margem(_linha_base(custo_confiavel=False))
        assert pd.isna(r["margem_contribuicao"].iloc[0])

    def test_receita_e_mantida_mesmo_sem_custo(self):
        """Sem custo nao ha margem, mas o faturamento continua real."""
        r = calcular_margem(_linha_base(custo_confiavel=False))
        assert r["receita_total"].iloc[0] == pytest.approx(200.0)
