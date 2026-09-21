"""
SIMULADOR DE IMPACTOS IBS/CBS — motor de cálculo
Baseado em ESPECIFICACAO_SIMULADOR_IBS_CBS.md (Riozen Fiscal Web)

Referência: LC 214/2025 (Reforma Tributária), Anexo XVIII.

⚠️ DADOS PENDENTES DE CONFIRMAÇÃO OFICIAL — ver `TABELA_SIMPLES_ANEXOS`
mais abaixo. Os valores marcados como "placeholder" foram observados no
simulador da FIESP (https://apps.fiesp.com.br/SimuladorIbsCbs/), não são
fonte oficial, e NÃO devem ser usados pra decisão real sem confirmação
por LC 214/2025, Comitê Gestor do IBS, ou Econet. `calcular_aliquota_simples`
recusa calcular (levanta erro claro) pra qualquer combinação Anexo/Ano que
não esteja carregada na tabela — nunca inventa nem interpola valor.

Este módulo é 100% stateless — não grava nada em banco. Cada simulação é
uma chamada de função pura, sem efeito colateral.
"""
import json
import os
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

_DIR_ATUAL = os.path.dirname(os.path.abspath(__file__))
_ARQ_TABELA_SIMPLES = os.path.join(_DIR_ATUAL, "reforma_tributaria_modelos", "tabela_simples_anexos.json")

BASE_PRECO = 100.0

FATURAMENTO_LIMITE_SIMPLES = 4_800_000.00  # LC 123/2006 — confirmar se LC 214/2025 alterou

# ─── 4.1 — Alíquota de referência do Regime Geral por ano ───────────────
# ⚠️ PLACEHOLDER — observado no simulador da FIESP, NÃO é fonte oficial.
# Confirmar com Receita Federal / Comitê Gestor do IBS / piloto-cbs.tributos.gov.br
# antes de usar pra qualquer decisão real.
ALIQ_REGIME_GERAL_POR_ANO = {
    2027: 0.0921, 2028: 0.0921,
    2029: 0.1108,
    2030: 0.1295,
    2031: 0.1482,
    2032: 0.1669,
    2033: 0.2791,  # "2033 em diante"
}

# ─── 4.3 — Premissa de crédito presumido pra fornecedor do Simples DAS ──
# ⚠️ PLACEHOLDER — só o valor de 2027 veio confirmado no documento original
# (2,1%). Os demais anos foram inferidos seguindo a MESMA proporção que
# ALIQ_REGIME_GERAL_POR_ANO tem em relação a 2027 (9,21%) — isso é uma
# SUPOSIÇÃO DE PROJETO, não um dado confirmado. Marcar visualmente na tela
# quando estiver usando um ano != 2027 até isso ser validado.
_PCT_2027 = 0.021
PREMISSA_CREDITO_DAS_POR_ANO = {
    ano: round(_PCT_2027 * (aliq / ALIQ_REGIME_GERAL_POR_ANO[2027]), 6)
    for ano, aliq in ALIQ_REGIME_GERAL_POR_ANO.items()
}
PREMISSA_CREDITO_DAS_CONFIRMADO = {2027}  # anos com valor de fato confirmado, não inferido

# ─── 4.4 — CNAEs sugeridos (uso interno Riozen) ─────────────────────────
CNAE_SUGESTOES = {
    "45": {
        "descricao": "Comércio de veículos automotores, peças e acessórios",
        "anexo_simples": "I",
        # ⚠️ % de despesas tributadas sugerido pra pré-preencher o slider —
        # AINDA NÃO DEFINIDO. Ficar em None até decidir com Emerson um valor
        # de partida razoável (ou remover a sugestão e deixar sempre manual).
        "pct_despesas_sugerido": None,
    },
}

# ─── 4.2 — Tabela do Simples Nacional (Anexos I a V) ────────────────────
# Estrutura esperada no JSON (ver tabela_simples_anexos.json):
# {
#   "I": {
#     "2027": {
#       "partilha_cbs": 0.3402, "partilha_ibs": 0.0,
#       "faixas": [
#         {"ate": 180000.00,  "aliquota_nominal": 0.040, "deduzir": 0.0},
#         {"ate": 360000.00,  "aliquota_nominal": 0.073, "deduzir": 5940.0},
#         ...
#         {"ate": 4800000.00, "aliquota_nominal": 0.189, "deduzir": 378000.0}
#       ]
#     },
#     "2028": { ... }
#   },
#   "II": { ... }, "III": { ... }, "IV": { ... }, "V": { ... }
# }
def _carregar_tabela_simples():
    if not os.path.exists(_ARQ_TABELA_SIMPLES):
        return {}
    with open(_ARQ_TABELA_SIMPLES, "r", encoding="utf-8") as f:
        return json.load(f)


TABELA_SIMPLES_ANEXOS = _carregar_tabela_simples()


class DadosInsuficientesError(Exception):
    """Levantado quando a tabela do Simples não tem a combinação
    Anexo/Ano/Faixa pedida — nunca inventamos nem extrapolamos."""
    pass


def calcular_aliquota_simples(anexo: str, faturamento_12m: float, ano: int):
    """
    Retorna dict: {
        aliquota_efetiva_total, aliquota_efetiva_cbs, aliquota_efetiva_ibs,
        faixa_usada, partilha_cbs, partilha_ibs
    }
    Levanta DadosInsuficientesError se Anexo/Ano não estiverem carregados.
    """
    anexo = str(anexo).strip().upper()
    dados_anexo = TABELA_SIMPLES_ANEXOS.get(anexo)
    if not dados_anexo:
        raise DadosInsuficientesError(
            f"Não há tabela carregada para o Anexo {anexo}. "
            f"Preencha tabela_simples_anexos.json antes de simular esse anexo."
        )
    dados_ano = dados_anexo.get(str(ano))
    if not dados_ano:
        raise DadosInsuficientesError(
            f"Não há tabela carregada para o Anexo {anexo}, ano {ano}. "
            f"Preencha tabela_simples_anexos.json antes de simular esse ano."
        )

    faixas = dados_ano["faixas"]
    faixa_usada = None
    for faixa in faixas:
        if faturamento_12m <= faixa["ate"]:
            faixa_usada = faixa
            break
    if faixa_usada is None:
        # acima da última faixa (ex.: > 4,8mi) — fora do Simples de qualquer forma
        raise DadosInsuficientesError(
            f"Faturamento de {faturamento_12m:,.2f} está acima de todas as faixas "
            f"cadastradas pro Anexo {anexo}/{ano} (empresa não pode estar no Simples)."
        )

    if faturamento_12m == 0:
        aliquota_efetiva_total = 0.0
    else:
        aliquota_efetiva_total = (
            faturamento_12m * faixa_usada["aliquota_nominal"] - faixa_usada["deduzir"]
        ) / faturamento_12m

    partilha_cbs = dados_ano["partilha_cbs"]
    partilha_ibs = dados_ano["partilha_ibs"]

    return {
        "aliquota_efetiva_total": aliquota_efetiva_total,
        "aliquota_efetiva_cbs": aliquota_efetiva_total * partilha_cbs,
        "aliquota_efetiva_ibs": aliquota_efetiva_total * partilha_ibs,
        "faixa_usada": faixa_usada,
        "partilha_cbs": partilha_cbs,
        "partilha_ibs": partilha_ibs,
    }


@dataclass
class ResultadoSimulacao:
    preco_inicial: float
    credito_entrada: float
    base_apos_credito: float
    ibs_cbs_devido: float
    credito_cliente: float
    preco_venda: float
    custo_liquido_cliente: float
    memoria_calculo: list = field(default_factory=list)


def _memoria(msgs):
    return list(msgs)


def simular_regime_geral(aliq_geral, pct_desp, pct_forn_das, premissa_credito_das,
                          pct_cli_com_credito) -> ResultadoSimulacao:
    """
    ⚠️ Ponto crítico (spec seção 3.1, ainda não confirmado em fonte oficial):
    o IBS/CBS devido incide sobre o preço CHEIO (BASE_PRECO), não sobre a
    base líquida de créditos. Isso é uma premissa observada no simulador da
    FIESP — validar antes de usar o resultado pra decisão real.
    """
    pct_forn_geral = 1 - pct_forn_das
    base_despesas = BASE_PRECO * pct_desp
    credito_entrada = base_despesas * (pct_forn_geral * aliq_geral + pct_forn_das * premissa_credito_das)
    base_apos_credito = BASE_PRECO - credito_entrada
    ibs_cbs_devido = BASE_PRECO * aliq_geral
    credito_cliente = ibs_cbs_devido * pct_cli_com_credito
    preco_venda = BASE_PRECO + ibs_cbs_devido
    custo_liquido_cliente = preco_venda - credito_cliente

    return ResultadoSimulacao(
        preco_inicial=BASE_PRECO,
        credito_entrada=round(credito_entrada, 4),
        base_apos_credito=round(base_apos_credito, 4),
        ibs_cbs_devido=round(ibs_cbs_devido, 4),
        credito_cliente=round(credito_cliente, 4),
        preco_venda=round(preco_venda, 4),
        custo_liquido_cliente=round(custo_liquido_cliente, 4),
        memoria_calculo=_memoria([
            f"Base de despesas sujeitas a crédito: {pct_desp:.1%} de R$ 100 = R$ {base_despesas:.2f}",
            f"Crédito de entrada: {pct_forn_geral:.1%} fornecedores Regime Geral (alíq. {aliq_geral:.2%}) "
            f"+ {pct_forn_das:.1%} fornecedores Simples DAS (crédito presumido {premissa_credito_das:.2%}) "
            f"= R$ {credito_entrada:.2f}",
            f"IBS/CBS devido = alíquota do Regime Geral ({aliq_geral:.2%}) × preço cheio (R$ 100) = R$ {ibs_cbs_devido:.2f} "
            f"[⚠️ incidência sobre preço cheio, não sobre base líquida — premissa a confirmar]",
            f"Crédito repassado ao cliente: {pct_cli_com_credito:.1%} do IBS/CBS devido = R$ {credito_cliente:.2f}",
            f"Preço de venda = R$ 100 + R$ {ibs_cbs_devido:.2f} = R$ {preco_venda:.2f}",
            f"Custo líquido efetivo do cliente = R$ {preco_venda:.2f} - R$ {credito_cliente:.2f} = R$ {custo_liquido_cliente:.2f}",
        ]),
    )


def simular_simples_fora_das(aliq_geral, pct_desp, pct_forn_das, premissa_credito_das,
                              pct_cli_com_credito) -> ResultadoSimulacao:
    """Simples fora da DAS recolhe IBS/CBS igual ao Regime Geral (mesma
    alíquota) — só muda a forma de recolhimento dos DEMAIS tributos, que
    não fazem parte do escopo deste simulador."""
    resultado = simular_regime_geral(aliq_geral, pct_desp, pct_forn_das,
                                      premissa_credito_das, pct_cli_com_credito)
    resultado.memoria_calculo.insert(
        0, "Simples fora da DAS: IBS/CBS segue a mesma alíquota e regra do Regime Geral."
    )
    return resultado


def simular_simples_das(anexo, faturamento_12m, ano, pct_desp, pct_forn_das,
                         aliq_geral, premissa_credito_das, pct_cli_com_credito) -> ResultadoSimulacao:
    if faturamento_12m > FATURAMENTO_LIMITE_SIMPLES:
        raise ValueError(
            f"Faturamento de R$ {faturamento_12m:,.2f} ultrapassa o limite do Simples "
            f"(R$ {FATURAMENTO_LIMITE_SIMPLES:,.2f}) — empresa não pode ficar no DAS."
        )

    aliq_info = calcular_aliquota_simples(anexo, faturamento_12m, ano)
    aliq_efetiva_ibs_cbs = aliq_info["aliquota_efetiva_total"]  # parcela do DAS que é IBS+CBS

    pct_forn_geral = 1 - pct_forn_das
    base_despesas = BASE_PRECO * pct_desp
    credito_entrada = base_despesas * (pct_forn_geral * aliq_geral + pct_forn_das * premissa_credito_das)
    base_apos_credito = BASE_PRECO - credito_entrada
    ibs_cbs_devido = BASE_PRECO * aliq_efetiva_ibs_cbs
    credito_cliente = ibs_cbs_devido * pct_cli_com_credito
    preco_venda = BASE_PRECO + ibs_cbs_devido
    custo_liquido_cliente = preco_venda - credito_cliente

    return ResultadoSimulacao(
        preco_inicial=BASE_PRECO,
        credito_entrada=round(credito_entrada, 4),
        base_apos_credito=round(base_apos_credito, 4),
        ibs_cbs_devido=round(ibs_cbs_devido, 4),
        credito_cliente=round(credito_cliente, 4),
        preco_venda=round(preco_venda, 4),
        custo_liquido_cliente=round(custo_liquido_cliente, 4),
        memoria_calculo=_memoria([
            f"Faixa do Simples (Anexo {anexo}, {ano}): até R$ {aliq_info['faixa_usada']['ate']:,.2f}, "
            f"alíquota nominal {aliq_info['faixa_usada']['aliquota_nominal']:.2%}, "
            f"parcela a deduzir R$ {aliq_info['faixa_usada']['deduzir']:,.2f}",
            f"Alíquota efetiva total do DAS: {aliq_info['aliquota_efetiva_total']:.4%}",
            f"Partilha do ano — CBS {aliq_info['partilha_cbs']:.2%} / IBS {aliq_info['partilha_ibs']:.2%} "
            f"→ CBS efetivo {aliq_info['aliquota_efetiva_cbs']:.4%} / IBS efetivo {aliq_info['aliquota_efetiva_ibs']:.4%}",
            f"IBS/CBS devido = {aliq_efetiva_ibs_cbs:.4%} × preço cheio (R$ 100) = R$ {ibs_cbs_devido:.2f}",
            f"Crédito repassado ao cliente: {pct_cli_com_credito:.1%} do IBS/CBS devido = R$ {credito_cliente:.2f}",
            f"Preço de venda = R$ 100 + R$ {ibs_cbs_devido:.2f} = R$ {preco_venda:.2f}",
            f"Custo líquido efetivo do cliente = R$ {preco_venda:.2f} - R$ {credito_cliente:.2f} = R$ {custo_liquido_cliente:.2f}",
        ]),
    )


def calcular_faturamento_e_despesas(arquivos_saida, arquivos_entrada, log=print):
    """
    Lê as mesmas planilhas do NBS já usadas no módulo PIS/COFINS (Saída =
    'Lista Pis Cofins', Entrada = 'Credito_Pis_Cofins', uma por filial) e
    calcula, sem qualquer input manual:

      faturamento_total = soma da coluna 'Fat. Bruto' de todas as notas
                           de Saída (mesma coluna, mesma lógica que já
                           usamos e validamos no PIS/COFINS).
      despesa_creditavel_total = soma do valor de TODAS as linhas de item
                           da Entrada que têm CFOP preenchido (regra
                           simplificada pra ferramenta gerencial — não
                           depende de tabela de NCM externa).
      pct_desp = despesa_creditavel_total / faturamento_total

    ⚠️ Ferramenta de estimativa gerencial — a base de crédito de IBS/CBS
    real pode ter exclusões que essa regra simplificada não captura.
    """
    faturamento_total = 0.0
    detalhe_saida = []
    for path in arquivos_saida:
        ext = os.path.splitext(path)[1].lower()
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine, skiprows=5, header=0, sheet_name=0)
        df = df.dropna(how="all")
        col_fat = df.columns[15]  # 'Fat. Bruto'
        soma = float(pd.to_numeric(df[col_fat], errors="coerce").fillna(0).sum())
        detalhe_saida.append({"arquivo": os.path.basename(path), "fat_bruto": round(soma, 2)})
        faturamento_total += soma
        log(f"   Saída {os.path.basename(path)}: Fat. Bruto = R$ {soma:,.2f}")

    despesa_creditavel_total = 0.0
    detalhe_entrada = []
    for path in arquivos_entrada:
        ext = os.path.splitext(path)[1].lower()
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine, skiprows=5, header=0, sheet_name=0)
        df = df.dropna(how="all")
        col_cfop_item = df.columns[22]  # 'Cfop' (nível item)
        col_valor_item = df.columns[25]  # 'Base Pis' (nível item, usada como valor da linha)
        mask = df[col_cfop_item].notna() & (df[col_cfop_item].astype(str).str.strip() != "")
        soma = float(pd.to_numeric(df.loc[mask, col_valor_item], errors="coerce").fillna(0).sum())
        detalhe_entrada.append({
            "arquivo": os.path.basename(path), "despesa_creditavel": round(soma, 2), "itens": int(mask.sum()),
        })
        despesa_creditavel_total += soma
        log(f"   Entrada {os.path.basename(path)}: despesa creditável = R$ {soma:,.2f} ({int(mask.sum())} itens)")

    pct_desp = (despesa_creditavel_total / faturamento_total) if faturamento_total else 0.0

    return {
        "faturamento_total": round(faturamento_total, 2),
        "despesa_creditavel_total": round(despesa_creditavel_total, 2),
        "pct_desp": pct_desp,
        "detalhe_saida": detalhe_saida,
        "detalhe_entrada": detalhe_entrada,
    }


def montar_comparativo(resultado_a: ResultadoSimulacao, resultado_b: ResultadoSimulacao, label_a: str, label_b: str):
    """Monta a tabela comparativa (seção 2.5) com variação % linha a linha."""
    def variacao(a, b):
        if a == 0:
            return None
        return (b - a) / a

    linhas = [
        ("Preço inicial", resultado_a.preco_inicial, resultado_b.preco_inicial),
        ("Crédito recebido dos fornecedores", resultado_a.credito_entrada, resultado_b.credito_entrada),
        ("Base após créditos de entrada", resultado_a.base_apos_credito, resultado_b.base_apos_credito),
        ("IBS/CBS devido", resultado_a.ibs_cbs_devido, resultado_b.ibs_cbs_devido),
        ("Crédito aproveitado pelo cliente", resultado_a.credito_cliente, resultado_b.credito_cliente),
        ("Preço de venda", resultado_a.preco_venda, resultado_b.preco_venda),
        ("Custo líquido efetivo do cliente", resultado_a.custo_liquido_cliente, resultado_b.custo_liquido_cliente),
    ]
    return {
        "label_a": label_a,
        "label_b": label_b,
        "linhas": [
            {"descricao": desc, "valor_a": round(va, 4), "valor_b": round(vb, 4), "variacao_pct": variacao(va, vb)}
            for desc, va, vb in linhas
        ],
    }
