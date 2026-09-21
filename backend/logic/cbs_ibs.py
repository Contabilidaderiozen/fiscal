"""
APURAÇÃO CBS/IBS — módulo do Sistema Riozen (Fiscal > Apuração > CBS/IBS)

Base legal: LC 214/2025 (Reforma Tributária). Pontos confirmados
diretamente no texto da lei antes de codar, sem inventar nada:

  - Base de cálculo "por fora": o IBS/CBS NÃO integra a própria base —
    é calculado sobre o valor da operação e somado ao preço (art. 12,
    §2º, I: "Não integram a base de cálculo do IBS e da CBS: I - o
    montante do IBS e da CBS incidentes sobre a operação").
  - Crédito amplo: qualquer aquisição com nota fiscal idônea em que o
    contribuinte seja adquirente gera direito a crédito, exceto uso ou
    consumo pessoal (art. 47, caput, e art. 57). Não há distinção fina
    por tipo de operação como havia no PIS/COFINS (Normal NC/Monofásico)
    — por isso a regra simplificada usada aqui é "toda entrada com CFOP
    preenchido gera crédito".
  - Mecanismo não cumulativo: valor a pagar = débito (saídas) menos
    crédito (entradas) do período (art. 45).

⚠️ Alíquotas: a LC 214/2025 NÃO fixa um número pronto pra alíquota do
IBS/CBS a partir de 2027 — ela é calculada por fórmula e publicada por
Resolução do Senado/Ato Conjunto (arts. 349 a 369). Os valores abaixo
são os únicos confirmados até o momento desta implementação; qualquer
ano fora dessa tabela trava com erro em vez de estimar.
"""
import os
import pandas as pd

# ─── Alíquotas combinadas (CBS + IBS) confirmadas por ano ───────────────
# 2026: CBS 0,9% (fixo na lei, art. 346) + IBS 0% (ainda não cobrado, art. 343 só entra em 2027)
# 2027-2028: CBS 8,4% (alíquota de referência, confirmada via API oficial
#            piloto-cbs.tributos.gov.br) + IBS 0,1% (fixo na lei, art. 344:
#            0,05% estadual + 0,05% municipal)
# 2029+: ainda não publicado — não fica na tabela, trava com erro.
ALIQUOTAS_ANO = {
    2026: {"cbs": 0.009, "ibs": 0.000, "fonte": "CBS fixo em lei (art. 346); IBS ainda não cobrado (art. 343)"},
    2027: {"cbs": 0.084, "ibs": 0.001, "fonte": "CBS = alíquota de referência confirmada via API oficial; IBS fixo em lei (art. 344)"},
    2028: {"cbs": 0.084, "ibs": 0.001, "fonte": "mesmo valor de 2027 até confirmação de nova alíquota de referência"},
}


class AliquotaIndisponivelError(Exception):
    pass


def aliquota_combinada_do_ano(ano: int) -> float:
    dados = ALIQUOTAS_ANO.get(ano)
    if not dados:
        raise AliquotaIndisponivelError(
            f"Não há alíquota combinada de IBS/CBS confirmada pra {ano}. "
            f"A partir de 2029 a alíquota é calculada por fórmula (LC 214/2025, "
            f"arts. 349 a 369) e publicada por Resolução do Senado — atualize a "
            f"tabela ALIQUOTAS_ANO assim que houver publicação oficial pra esse ano."
        )
    return round(dados["cbs"] + dados["ibs"], 6)


# ─── Leitura das planilhas do NBS (mesmo formato já usado no PIS/COFINS:
#     Saída = 'Lista Pis Cofins', Entrada = 'Credito_Pis_Cofins') ───────
def ler_notas_saida(arquivos, log=print):
    """Lê a(s) planilha(s) de Saída e devolve lista de linhas
    (nota, cfop, valor) + total, sem nenhuma classificação — aqui só
    interessa o Faturamento total (débito) e o detalhe por nota."""
    linhas = []
    total = 0.0
    for path in arquivos:
        ext = os.path.splitext(path)[1].lower()
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine, skiprows=5, header=0, sheet_name=0)
        df = df.dropna(how="all")
        col_nota  = df.columns[0]
        col_cfop  = df.columns[5]
        col_fat   = df.columns[15]  # 'Fat. Bruto'
        soma_arquivo = 0.0
        for _, row in df.iterrows():
            valor = row[col_fat]
            try:
                valor = float(valor) if pd.notna(valor) else 0.0
            except Exception:
                valor = 0.0
            if valor == 0.0:
                continue
            linhas.append({
                "arquivo": os.path.basename(path),
                "nota": row[col_nota],
                "cfop": row[col_cfop],
                "valor": round(valor, 2),
            })
            soma_arquivo += valor
        total += soma_arquivo
        log(f"   Saída {os.path.basename(path)}: {len(df)} linhas lidas, R$ {soma_arquivo:,.2f}")
    return linhas, round(total, 2)


def ler_itens_entrada(arquivos, log=print):
    """Lê a(s) planilha(s) de Entrada e devolve lista de itens (nota,
    cfop, valor) + total — só os itens que têm CFOP preenchido contam
    como base de crédito (regra simplificada confirmada com Emerson,
    já que a LC 214 não distingue tipo de operação como o PIS/COFINS
    fazia)."""
    linhas = []
    total = 0.0
    for path in arquivos:
        ext = os.path.splitext(path)[1].lower()
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine, skiprows=5, header=0, sheet_name=0)
        df = df.dropna(how="all")
        col_nota       = df.columns[2]   # 'Nota Fiscal' (nível NF)
        col_cfop_item  = df.columns[22]  # 'Cfop' (nível item)
        col_valor_item = df.columns[25]  # 'Base Pis' (nível item, usada como valor da linha)
        soma_arquivo = 0.0
        for _, row in df.iterrows():
            cfop = row[col_cfop_item]
            if pd.isna(cfop) or str(cfop).strip() == "":
                continue
            valor = row[col_valor_item]
            try:
                valor = float(valor) if pd.notna(valor) else 0.0
            except Exception:
                valor = 0.0
            if valor == 0.0:
                continue
            linhas.append({
                "arquivo": os.path.basename(path),
                "nota": row[col_nota],
                "cfop": cfop,
                "valor": round(valor, 2),
            })
            soma_arquivo += valor
        total += soma_arquivo
        log(f"   Entrada {os.path.basename(path)}: {len(df)} linhas lidas, R$ {soma_arquivo:,.2f} creditável")
    return linhas, round(total, 2)


def apurar(arquivos_saida, arquivos_entrada, ano, aliq_debito, aliq_credito, log=print):
    """Roda a apuração completa: lê as planilhas, calcula débito, crédito
    e valor a pagar (ou saldo credor, se negativo)."""
    log("Lendo planilhas de Saída (débito)...")
    linhas_saida, faturamento_total = ler_notas_saida(arquivos_saida, log)

    log("\nLendo planilhas de Entrada (crédito)...")
    linhas_entrada, total_entrada_creditavel = ler_itens_entrada(arquivos_entrada, log)

    debito = round(faturamento_total * aliq_debito, 2)
    credito = round(total_entrada_creditavel * aliq_credito, 2)
    valor_apurado = round(debito - credito, 2)

    log(f"\nFaturamento de Saída:        R$ {faturamento_total:,.2f}")
    log(f"Alíquota Débito ({ano}):      {aliq_debito:.4%}")
    log(f"Débito (IBS/CBS s/ saída):    R$ {debito:,.2f}")
    log(f"Total de Entrada creditável:  R$ {total_entrada_creditavel:,.2f}")
    log(f"Alíquota Crédito ({ano}):     {aliq_credito:.4%}")
    log(f"Crédito (IBS/CBS s/ entrada): R$ {credito:,.2f}")
    if valor_apurado >= 0:
        log(f"\nVALOR A PAGAR:                R$ {valor_apurado:,.2f}")
    else:
        log(f"\nSALDO CREDOR (a compensar):   R$ {abs(valor_apurado):,.2f}")

    return {
        "linhas_saida": linhas_saida,
        "faturamento_total": faturamento_total,
        "aliq_debito": aliq_debito,
        "debito": debito,
        "linhas_entrada": linhas_entrada,
        "total_entrada_creditavel": total_entrada_creditavel,
        "aliq_credito": aliq_credito,
        "credito": credito,
        "valor_apurado": valor_apurado,
    }


def gerar_relatorio(resultado, ano, periodo_rotulo, saida_path):
    """Monta o arquivo Excel de 3 abas (Débito, Crédito, Apuração) a
    partir do resultado de apurar()."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from .pis_cofins_formatacao import _formatar_planilha, _destacar_totais

    FMT_MOEDA = '#,##0.00_);[Red](#,##0.00)'
    FMT_PCT = '0.00%'
    BOLD = Font(bold=True)

    wb = Workbook()
    wb.remove(wb.active)

    # ---- aba Débito ----
    ws_deb = wb.create_sheet("DEBITO")
    ws_deb.append(["Arquivo", "Nota", "CFOP", "Valor (Fat. Bruto)"])
    for linha in resultado["linhas_saida"]:
        ws_deb.append([linha["arquivo"], linha["nota"], linha["cfop"], linha["valor"]])
    r_total_deb = ws_deb.max_row + 1
    ws_deb.cell(r_total_deb, 1, value="TOTAL")
    ws_deb.cell(r_total_deb, 4, value=f"=SUM(D2:D{r_total_deb-1})").number_format = FMT_MOEDA
    for c in range(1, 5):
        ws_deb.cell(1, c).number_format = FMT_MOEDA if c == 4 else "@"
    for row in ws_deb.iter_rows(min_row=2, max_row=r_total_deb-1, min_col=4, max_col=4):
        for cell in row:
            cell.number_format = FMT_MOEDA
    _formatar_planilha(ws_deb, header_row=1, freeze_cell="A2")
    _destacar_totais(ws_deb, [r_total_deb], min_col=1, max_col=4)
    ws_deb.column_dimensions["A"].width = 24
    ws_deb.column_dimensions["B"].width = 12
    ws_deb.column_dimensions["C"].width = 10
    ws_deb.column_dimensions["D"].width = 18

    # ---- aba Crédito ----
    ws_cred = wb.create_sheet("CREDITO")
    ws_cred.append(["Arquivo", "Nota", "CFOP", "Valor (base creditável)"])
    for linha in resultado["linhas_entrada"]:
        ws_cred.append([linha["arquivo"], linha["nota"], linha["cfop"], linha["valor"]])
    r_total_cred = ws_cred.max_row + 1
    ws_cred.cell(r_total_cred, 1, value="TOTAL")
    ws_cred.cell(r_total_cred, 4, value=f"=SUM(D2:D{r_total_cred-1})").number_format = FMT_MOEDA
    for row in ws_cred.iter_rows(min_row=2, max_row=r_total_cred-1, min_col=4, max_col=4):
        for cell in row:
            cell.number_format = FMT_MOEDA
    _formatar_planilha(ws_cred, header_row=1, freeze_cell="A2")
    _destacar_totais(ws_cred, [r_total_cred], min_col=1, max_col=4)
    ws_cred.column_dimensions["A"].width = 24
    ws_cred.column_dimensions["B"].width = 12
    ws_cred.column_dimensions["C"].width = 10
    ws_cred.column_dimensions["D"].width = 20

    # ---- aba Apuração ----
    ws_apu = wb.create_sheet("APURACAO", 0)
    linhas_apuracao = [
        ("Período", periodo_rotulo),
        ("Ano de referência", ano),
        ("", ""),
        ("Faturamento de Saída (base do débito)", resultado["faturamento_total"]),
        ("Alíquota combinada usada no Débito (CBS+IBS)", resultado["aliq_debito"]),
        ("DÉBITO (IBS/CBS sobre as saídas)", resultado["debito"]),
        ("", ""),
        ("Total de Entrada creditável (base do crédito)", resultado["total_entrada_creditavel"]),
        ("Alíquota combinada usada no Crédito (CBS+IBS)", resultado["aliq_credito"]),
        ("CRÉDITO (IBS/CBS sobre as entradas)", resultado["credito"]),
        ("", ""),
        ("VALOR A PAGAR" if resultado["valor_apurado"] >= 0 else "SALDO CREDOR (a compensar)",
         abs(resultado["valor_apurado"])),
    ]
    for desc, valor in linhas_apuracao:
        r = ws_apu.max_row + 1
        ws_apu.cell(r, 1, value=desc).font = BOLD if desc.isupper() or "VALOR A PAGAR" in desc or "SALDO CREDOR" in desc else Font()
        if isinstance(valor, float) and "Alíquota" not in desc:
            ws_apu.cell(r, 2, value=valor).number_format = FMT_MOEDA
        elif isinstance(valor, float):
            ws_apu.cell(r, 2, value=valor).number_format = FMT_PCT
        else:
            ws_apu.cell(r, 2, value=valor)
    ws_apu.column_dimensions["A"].width = 48
    ws_apu.column_dimensions["B"].width = 20
    # destaque visual na linha final (valor a pagar / saldo credor)
    r_final = ws_apu.max_row
    fill = PatternFill("solid", fgColor="FFF2CC" if resultado["valor_apurado"] >= 0 else "D9EAD3")
    for c in range(1, 3):
        ws_apu.cell(r_final, c).fill = fill
        ws_apu.cell(r_final, c).font = Font(bold=True, size=12)

    wb.save(saida_path)
    return saida_path
