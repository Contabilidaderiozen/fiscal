"""
GERADOR DE APURAÇÃO PIS/COFINS (versão web, parametrizada)
Preserva a lógica de gerar_apuracao.py, com duas mudanças deliberadas:

1. Recebe arquivos explícitos (Débitos processado, Créditos processado,
   modelo de Apuração) em vez de escanear pastas.
2. A comparação de cabeçalho ('DESCRICAO'/'CONTA'/'PROPORCIONAL') é feita
   de forma insensível a acento — o script original compara com
   igualdade exata sem acento ('DESCRICAO'), mas o texto real nas
   planilhas usa acentuação correta ('DESCRIÇÃO'), o que faz a
   comparação original falhar silenciosamente. Testado e confirmado
   contra o arquivo real CREDITOS_PROCESSADO_202606.xlsx.
"""
import re
import unicodedata
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill


def _norm(s):
    """Maiúsculas, sem acento, sem espaço nas pontas — pra comparações
    robustas de cabeçalho que não dependem da acentuação exata do texto
    dentro da planilha."""
    s = str(s or '').strip().upper()
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))


def get_num(v):
    try: return float(v or 0)
    except: return 0.0


_MESES_PT = {
    'JANUARY':'JANEIRO','FEBRUARY':'FEVEREIRO','MARCH':'MARÇO','APRIL':'ABRIL',
    'MAY':'MAIO','JUNE':'JUNHO','JULY':'JULHO','AUGUST':'AGOSTO',
    'SEPTEMBER':'SETEMBRO','OCTOBER':'OUTUBRO','NOVEMBER':'NOVEMBRO','DECEMBER':'DEZEMBRO'
}


def processar_apuracao(arq_debitos, arq_creditos, modelo, mes_referencia, saida, log=print):
    """
    mes_referencia: nome do mês em português maiúsculo (ex: 'AGOSTO'),
    usado só pra rotular as abas — não é lido de nenhum arquivo porque
    o período real já está implícito nos dados de entrada.
    """
    log("\n[1] Lendo débitos...")
    wb_deb = load_workbook(arq_debitos, data_only=False)
    ws_deb = wb_deb['DEBITOS']

    resumo_deb   = {}
    secao_outras = {}
    secao_fin    = {}
    fat_bruto_total  = 0
    fat_bruto_usados = 0

    last_data = 1
    for i in range(2, ws_deb.max_row+1):
        try:
            float(str(ws_deb.cell(i,1).value or ''))
            last_data = i
        except: pass
    log(f"   Dados até linha {last_data}")

    for i in range(2, last_data+1):
        chave = str(ws_deb.cell(i,9).value or '').strip()
        base  = get_num(ws_deb.cell(i,12).value)
        fat   = get_num(ws_deb.cell(i,19).value)
        icms  = get_num(ws_deb.cell(i,21).value)
        if not chave: continue
        if chave not in resumo_deb:
            resumo_deb[chave] = {'base_pis': 0, 'fat_bruto': 0, 'val_icms': 0}
        resumo_deb[chave]['base_pis']  += base
        resumo_deb[chave]['fat_bruto'] += fat
        resumo_deb[chave]['val_icms']  += icms
        fat_bruto_total += fat
        if 'VEICULO USADO' in chave.upper():
            fat_bruto_usados += fat

    # NOTA: o marcador 'DESCRIÇÃO' sozinho na col K também aparece nos
    # cabeçalhos das tabelas de resumo (Normal NC/Cumulativo/Zero-Mono),
    # que vêm ANTES da seção fixa de verdade — contar ocorrências de
    # 'DESCRIÇÃO' pra alternar entre 'outras'/'financeira' (como o script
    # original fazia) conta essas 3 ocorrências de resumo também e
    # classifica tudo errado. Em vez disso, usamos o texto ao lado (col M)
    # que é específico de cada seção real: 'BASE SEM EMISSÃO DE NOTA
    # FISCAL' (Outras Receitas) ou 'BASE RECEITA FINANCEIRA' (Financeira).
    modo_sf = None
    for i in range(last_data+1, ws_deb.max_row+1):
        k11 = str(ws_deb.cell(i,11).value or '').strip()
        k13 = ws_deb.cell(i,13).value
        k13_norm = _norm(k13)

        if _norm(k11) == 'DESCRICAO':
            if 'BASE SEM EMISSAO' in k13_norm:
                modo_sf = 'outras'
            elif 'BASE RECEITA FINANCEIRA' in k13_norm:
                modo_sf = 'financeira'
            # outras ocorrências de 'DESCRIÇÃO' (cabeçalhos de resumo)
            # não mudam modo_sf — ficam ignoradas.
            continue
        if 'TOTAL' in _norm(k11) and k13 is not None:
            continue
        if not k11 or k13 is None: continue

        bal_val = 0
        if k13:
            ws_bal = wb_deb['BALANCETE'] if 'BALANCETE' in wb_deb.sheetnames else None
            if ws_bal:
                try:
                    conta_int = int(float(str(k13)))
                    for bi in range(5, ws_bal.max_row+1):
                        bc = ws_bal.cell(bi,1).value
                        try:
                            if int(float(str(bc))) == conta_int:
                                bal_val = get_num(ws_bal.cell(bi,6).value)
                                break
                        except: pass
                except: pass

        if bal_val == 0: continue
        if modo_sf == 'outras':
            secao_outras[k11] = bal_val
        elif modo_sf == 'financeira':
            secao_fin[k11] = bal_val

    fat_demais = fat_bruto_total - fat_bruto_usados
    pct_prop   = fat_demais / fat_bruto_total if fat_bruto_total else 0
    log(f"   Fat. Bruto Total:  {fat_bruto_total:,.2f}")
    log(f"   Fat. Bruto Usados: {fat_bruto_usados:,.2f}")
    log(f"   % Proporcional:    {pct_prop:.2%}")

    icms_saida_nc = 0
    normal_nc = {k:v for k,v in resumo_deb.items()
                 if 'ZERO' not in k.upper() and 'MONOFASICO' not in k.upper()
                 and 'VEICULO USADO' not in k.upper() and 'VEICULO NOVO' not in k.upper()}
    veiculo_usado_base = sum(v['base_pis'] for k,v in resumo_deb.items() if 'VEICULO USADO' in k.upper())
    devolucao_base = sum(v['base_pis'] for k,v in resumo_deb.items() if 'DEVOLUCAO' in k.upper() or 'DEVOLUÇÃO' in k.upper())
    total_outras   = sum(secao_outras.values())
    total_fin_deb  = sum(secao_fin.values())
    log(f"   Normal NC itens:   {list(normal_nc.keys())}")
    log(f"   Outras Receitas: {len(secao_outras)} contas (R$ {total_outras:,.2f}) | "
        f"Financeira: {len(secao_fin)} contas (R$ {total_fin_deb:,.2f})")

    log("\n[2] Lendo créditos...")
    wb_cre = load_workbook(arq_creditos, data_only=True)
    ws_cre = wb_cre['CREDITOS']

    total_cred_nc = 0
    icms_entrada_nc = 0
    secao_cred = {}

    ws_ncm_cre = wb_cre['NCM'] if 'NCM' in wb_cre.sheetnames else None
    ncm_tipo_dict = {}
    if ws_ncm_cre:
        for ni in range(2, ws_ncm_cre.max_row+1):
            ncm_v = ws_ncm_cre.cell(ni,1).value
            tipo_v = str(ws_ncm_cre.cell(ni,2).value or '').strip()
            if ncm_v:
                try: ncm_tipo_dict.setdefault(int(float(str(ncm_v))), tipo_v)  # 1ª ocorrência vence (igual VLOOKUP)
                except: ncm_tipo_dict.setdefault(str(ncm_v).strip(), tipo_v)

    last_cre = 1
    for i in range(2, ws_cre.max_row+1):
        # Usar a Nota Fiscal (col3), preenchida tanto em linhas de NF
        # quanto em linhas de item — usar só a col1 (Empresa, só
        # preenchida em linhas de NF) corta a última linha quando ela
        # é uma linha de item, subestimando o intervalo de dados em
        # todas as somas que dependem de last_cre.
        try:
            float(str(ws_cre.cell(i,3).value or ''))
            last_cre = i
        except: pass
    log(f"   Dados créditos até linha {last_cre}")

    for i in range(2, last_cre+1):
        base = get_num(ws_cre.cell(i,8).value)
        ncm  = ws_cre.cell(i,22).value
        if base == 0: continue
        tipo = ''
        if ncm:
            try: tipo = ncm_tipo_dict.get(int(float(str(ncm))), '')
            except: tipo = ncm_tipo_dict.get(str(ncm).strip(), '')
        if 'NORMAL NC' in tipo.upper() or tipo == '':
            pass  # cálculo antigo removido — ver total_cred_nc abaixo, que
                  # replica a mesma soma agrupada por "CFOP - Tipo" que a
                  # própria aba CREDITOS usa no resumo (linha TOTAL da
                  # tabela Normal NC), pra garantir que os dois valores
                  # batam sempre — antes eram calculados de formas
                  # diferentes e podiam divergir.

    # Replica a lógica de agrupamento do próprio resumo de créditos
    # (chave "CFOP - Tipo", soma de "Base Pis" por item, col AA=27) em
    # Python, usando valores literais — não depende de reabrir o Excel
    # pra ter as fórmulas SUMIF calculadas.
    cfop_tipos_apu = {}
    soma_base_pis_por_chave = {}
    for i in range(2, last_cre+1):
        ncm  = ws_cre.cell(i,22).value
        cfop = ws_cre.cell(i,23).value
        base_item = get_num(ws_cre.cell(i,27).value)
        if not ncm or cfop is None: continue
        tipo = ''
        try: tipo = ncm_tipo_dict.get(int(float(str(ncm))), '')
        except: tipo = ncm_tipo_dict.get(str(ncm).strip(), '')
        if not tipo: tipo = 'Normal NC'
        try: key = f"{int(cfop)} - {tipo}"
        except: key = f"{cfop} - {tipo}"
        cfop_tipos_apu[key] = tipo
        soma_base_pis_por_chave[key] = soma_base_pis_por_chave.get(key, 0.0) + base_item

    total_cred_nc = sum(v for k, v in soma_base_pis_por_chave.items()
                         if 'NORMAL' in cfop_tipos_apu.get(k, '').upper())
    log(f"   Fornecedores (= TOTAL Normal NC do resumo de créditos): {total_cred_nc:,.2f}")

    icms_entrada_nc = 0
    for i in range(2, last_cre+1):
        c34 = ws_cre.cell(i, 34).value
        if c34:
            try: icms_entrada_nc += float(c34)
            except: pass
    log(f"   ICMS entrada NC (col34 dados): {icms_entrada_nc:,.2f}")

    pct_prop_cred = pct_prop
    secao_insumos_header = None
    for i in range(1, ws_cre.max_row+1):
        v26 = _norm(ws_cre.cell(i,26).value)
        v28 = _norm(ws_cre.cell(i,28).value)
        v31 = _norm(ws_cre.cell(i,31).value)
        if v26 == 'DESCRICAO' and v28 == 'CONTA' and v31 == 'PROPORCIONAL':
            secao_insumos_header = i
            try:
                f = float(ws_cre.cell(i+1, 31).value)
                if 0 < f <= 1:
                    pct_prop_cred = f
                    log(f"   % Proporcional créditos (já gravado): {pct_prop_cred:.2%}")
            except: pass
            break

    if secao_insumos_header is None:
        log("   AVISO: Cabeçalho de insumos não encontrado nos créditos!")

    IGNORE_DESC = {'DESCRICAO','TOTAL','CONTA','-','CHECK','TOTAL GERAL',
                   'NAO CUMULATIVO','CUMULATIVO','PIS','COFINS',
                   'ICMS PECAS E ACESSORIOS','ICMS VEICULO USADO','TOTAL ICMS BASE DECALCULO',''}

    bal_dict = {}
    bal_nome = next((n for n in wb_cre.sheetnames if n.upper() == 'BALANCETE'), None)
    if bal_nome:
        ws_bal_cre = wb_cre[bal_nome]
        for bi in range(1, ws_bal_cre.max_row+1):
            conta_v = ws_bal_cre.cell(bi, 1).value
            valor_v = ws_bal_cre.cell(bi, 6).value
            if conta_v and valor_v:
                try: bal_dict[int(float(str(conta_v)))] = get_num(valor_v)
                except: pass
        log(f"   Balancete créditos: {len(bal_dict)} contas carregadas")
    else:
        log("   AVISO: aba Balancete não encontrada nos créditos")

    start_line = secao_insumos_header + 2 if secao_insumos_header else last_cre + 1
    contas_usadas_bal = set()
    for i in range(start_line, ws_cre.max_row+1):
        desc  = str(ws_cre.cell(i,26).value or '').strip()
        conta = ws_cre.cell(i,28).value
        c31   = ws_cre.cell(i,31).value

        if not desc or _norm(desc) in {_norm(d) for d in IGNORE_DESC}: continue
        if _norm(desc) in ('TOTAL', 'CHECK', 'TOTAL GERAL'): break
        if 'ICMS' in desc.upper() and 'BASE' in desc.upper(): break

        val_prop = 0.0
        try:
            if c31 is not None and str(c31).strip() not in ('', '-'):
                val_prop = float(c31)
        except: pass

        # Fallback: se a fórmula não tinha valor calculado em cache
        # (arquivo nunca aberto por um motor de planilha), recalcula
        # direto a partir do Balancete já carregado acima — não depende
        # de a fórmula ter sido avaliada.
        if val_prop == 0.0 and conta and str(conta).strip() not in ('-', ''):
            try:
                conta_int = int(float(str(conta)))
                if conta_int not in contas_usadas_bal and conta_int in bal_dict:
                    val_prop = round(bal_dict[conta_int] * pct_prop_cred, 2)
                    contas_usadas_bal.add(conta_int)
            except: pass

        secao_cred[desc] = val_prop

    log(f"   Total créditos Normal NC: {total_cred_nc:,.2f}")
    log(f"   ICMS entrada NC (col34):  {icms_entrada_nc:,.2f}")
    log(f"   Insumos com valor: {sum(1 for v in secao_cred.values() if v)} de {len(secao_cred)}")

    log("\n[3] Gerando apuração...")
    import shutil
    shutil.copy(modelo, saida)
    wb_apu = load_workbook(saida)

    FMT_M = '#,##0.00_);[Red](#,##0.00)'
    BOLD  = Font(bold=True)
    MES_ATUAL = mes_referencia

    aba_nc = 'Pis e Cofins - NAO CUMULATIVO'
    ws_nc  = wb_apu[aba_nc]

    for c in range(1, ws_nc.max_column+1):
        v = ws_nc.cell(2, c).value
        if v and _norm(v) in ['JANEIRO','FEVEREIRO','MARCO','ABRIL','MAIO',
                               'JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO',
                               'NOVEMBRO','DEZEMBRO']:
            ws_nc.cell(2, c, value=MES_ATUAL)
            ws_nc.cell(12, c, value=MES_ATUAL)
            break

    fat_trib_row = None
    for i in range(1, 30):
        v = _norm(ws_nc.cell(i,1).value)
        if 'FATURAMENTO' in v and ('TRIBUT' in v or 'TOTAL' in v):
            fat_trib_row = i
            break
    if fat_trib_row is None:
        fat_trib_row = 9
    log(f"   FATURAMENTO TRIBUTAVEL na linha {fat_trib_row}")

    itens_fat = [(desc, vals['base_pis']) for desc, vals in normal_nc.items() if vals['base_pis'] != 0]
    itens_fat += [(desc, base) for desc, base in secao_outras.items() if base != 0]
    linhas_necessarias = len(itens_fat)
    linhas_disponiveis = fat_trib_row - 4

    if linhas_necessarias > linhas_disponiveis:
        extras = linhas_necessarias - linhas_disponiveis
        ws_nc.insert_rows(fat_trib_row, extras)
        fat_trib_row += extras

    for i in range(4, fat_trib_row):
        for c in range(1, 5):
            ws_nc.cell(i, c, value=None)

    row = 4
    for desc, base in itens_fat:
        ws_nc.cell(row, 1, value=desc)
        ws_nc.cell(row, 3, value=base).number_format = FMT_M
        row += 1

    ws_nc.cell(fat_trib_row, 3, value=f'=SUM(C4:C{fat_trib_row-1})')
    log(f"   Faturamento: {linhas_necessarias} itens | TRIBUTAVEL na linha {fat_trib_row}")

    fat_orig = 9
    deslocamento = fat_trib_row - fat_orig

    if deslocamento != 0:
        def deslocar_formula(formula, desloc, a_partir_da_linha):
            def substituir(m):
                col = m.group(1)
                r = int(m.group(2))
                if r >= a_partir_da_linha:
                    return f'{col}{r + desloc}'
                return m.group(0)
            return re.sub(r'(\$?[A-Z]+)(\d+)', substituir, formula)

        for i in range(fat_trib_row + 1, ws_nc.max_row + 1):
            for c in range(1, ws_nc.max_column + 1):
                v = ws_nc.cell(i, c).value
                if v and str(v).startswith('='):
                    nova = deslocar_formula(str(v), deslocamento, fat_orig)
                    if nova != str(v):
                        ws_nc.cell(i, c, value=nova)
        log(f"   Fórmulas ajustadas com deslocamento de {deslocamento} linhas")

        ws_res = wb_apu['RESUMO'] if 'RESUMO' in wb_apu.sheetnames else None
        if ws_res:
            for i in range(1, ws_res.max_row+1):
                for c in range(1, ws_res.max_column+1):
                    v = ws_res.cell(i,c).value
                    if v and str(v).startswith('=') and 'NAO CUMULATIVO' in _norm(v):
                        def deslocar_ref_resumo(m):
                            col = m.group(1)
                            r = int(m.group(2))
                            if r >= fat_orig:
                                return f'{col}{r + deslocamento}'
                            return m.group(0)
                        nova = re.sub(r'([A-Z]+)(\d+)', deslocar_ref_resumo, str(v))
                        if nova != str(v):
                            ws_res.cell(i, c, value=nova)

    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if "NF'S DEVOLUCAO" in v or 'DEVOLUCAO DE COMPRA' in v:
            if devolucao_base != 0:
                ws_nc.cell(i, 3, value=devolucao_base).number_format = FMT_M
            break

    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if v == 'FORNECEDORES':
            ws_nc.cell(i, 3, value=total_cred_nc).number_format = FMT_M
            break

    insumos_start = None
    insumos_end   = None
    fornecedores_row = None
    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if v == 'FORNECEDORES':
            fornecedores_row = i
            insumos_start = i + 1
        if insumos_start and v == 'TOTAL' and i > insumos_start:
            c3 = ws_nc.cell(i,3).value
            if c3 is not None:
                insumos_end = i
                break

    if insumos_start and insumos_end:
        def normalizar_desc(s):
            s = _norm(s)
            return s.replace(' ', '').replace('-', '').replace('/', '').replace("'", '').replace('.', '')

        cred_norm = {normalizar_desc(d): (d, v) for d, v in secao_cred.items()}
        atualizados = 0
        for i in range(insumos_start, insumos_end):
            desc_modelo = str(ws_nc.cell(i,1).value or '').strip()
            if not desc_modelo:
                ws_nc.cell(i, 3, value=None); continue
            chave = normalizar_desc(desc_modelo)
            if chave in cred_norm:
                _, val_prop = cred_norm[chave]
                ws_nc.cell(i, 3, value=round(val_prop, 2) if val_prop else None).number_format = FMT_M
                atualizados += 1
            else:
                ws_nc.cell(i, 3, value=None)
                log(f"   SEM MATCH: '{desc_modelo}'")

        ws_nc.cell(insumos_end, 3, value=f'=SUM(C{fornecedores_row}:C{insumos_end-1})').number_format = FMT_M
        log(f"   Insumos atualizados: {atualizados} | TOTAL na linha {insumos_end}")
    else:
        log(f"   ERRO: insumos_start={insumos_start} insumos_end={insumos_end}")

    val_rendimento = sum(v2 for k,v2 in secao_fin.items() if 'RENDIMENTO' in k.upper())
    val_outras_fin  = sum(v2 for k,v2 in secao_fin.items() if 'RENDIMENTO' not in k.upper())
    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if 'RENDIMENTO APLICACAO' in v:
            ws_nc.cell(i, 3, value=val_rendimento if val_rendimento else None).number_format = FMT_M
        if 'OUTRAS RECEITAS OPERACIONAIS' in v:
            ws_nc.cell(i, 3, value=val_outras_fin if val_outras_fin else None).number_format = FMT_M
            break

    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if 'EXCLUSAO DO ICMS SAID' in v or ('ICMS SA' in v and 'EXCLUS' in v):
            for j in range(i+1, i+6):
                vj = _norm(ws_nc.cell(j,1).value)
                if vj in ('ICMS', ''):
                    if ws_nc.cell(j,3).value is not None or ws_nc.cell(j+1,3).value is not None:
                        alvo = j if ws_nc.cell(j,3).value is not None else j+1
                        ws_nc.cell(alvo, 3, value=icms_saida_nc if icms_saida_nc else None).number_format = FMT_M
                        break
                if vj == 'TOTAL': break
            break

    for i in range(fat_trib_row, ws_nc.max_row+1):
        v = _norm(ws_nc.cell(i,1).value)
        if 'EXCLUSAO DO ICMS ENTR' in v or ('ICMS' in v and 'ENTR' in v and 'EXCLUS' in v):
            for j in range(i+1, i+6):
                vj = _norm(ws_nc.cell(j,1).value)
                if 'ICMS' in vj or vj == '':
                    ws_nc.cell(j, 3, value=icms_entrada_nc if icms_entrada_nc else None).number_format = FMT_M
                    break
                if vj == 'TOTAL': break
            break

    aba_cu = next((n for n in wb_apu.sheetnames if _norm(n) == 'PIS E COFINS - CUMULATIVO'), None)
    if aba_cu:
        ws_cu = wb_apu[aba_cu]
        for c in range(1, ws_cu.max_column+1):
            v = ws_cu.cell(2, c).value
            if v and _norm(v) in ['JANEIRO','FEVEREIRO','MARCO','ABRIL','MAIO',
                                   'JUNHO','JULHO','AGOSTO','SETEMBRO','OUTUBRO',
                                   'NOVEMBRO','DEZEMBRO']:
                ws_cu.cell(2, c, value=MES_ATUAL)
                ws_cu.cell(11, c, value=MES_ATUAL)
                break
        ws_cu.cell(4, 1, value='VEICULOS USADOS - NORMAL C')
        ws_cu.cell(4, 3, value=veiculo_usado_base).number_format = FMT_M
    else:
        log("   AVISO: aba CUMULATIVO não encontrada no modelo")

    fill_destaque = PatternFill("solid", fgColor="FFF2CC")
    ws_nc.cell(fat_trib_row, 1).fill = fill_destaque
    ws_nc.cell(fat_trib_row, 3).fill = fill_destaque
    ws_nc.cell(fat_trib_row, 1).font = Font(bold=True)
    if fornecedores_row:
        ws_nc.cell(fornecedores_row, 1).fill = fill_destaque
        ws_nc.cell(fornecedores_row, 3).fill = fill_destaque
        ws_nc.cell(fornecedores_row, 1).font = Font(bold=True)

    log("\n[4] Salvando...")
    wb_apu.save(saida)
    log(f"\nCONCLUIDO! Arquivo: {saida}")
    return saida
