"""
PROCESSADOR PIS/COFINS - CRÉDITOS (versão web, parametrizada)
Preserva a lógica de processar_pis_cofins.py, mas recebe arquivos
explícitos em vez de escanear uma pasta, e recebe o % proporcional já
calculado (lido do resultado de Débitos) em vez de escanear a pasta
irmã em busca do arquivo mais recente.
"""
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
import copy, os, zipfile, re, io
from .pis_cofins_formatacao import _formatar_planilha, _destacar_totais

FMT_MOEDA = '#,##0.00_);[Red](#,##0.00)'
FMT_RS    = '_-"R$"\\ * #,##0.00_-;\\-"R$"\\ * #,##0.00_-;_-"R$"\\ * "-"??_-;_-@_-'
FMT_PCT   = '0.00%'

COLUNAS_PADRAO = [
    'Empresa','Operação','Nota Fiscal','Serie','Total Nota','Data Entrada',
    'Isenta','Base Pis','Base Cofins','CFOP','Valor PIS','CST Pis',
    'CST Cofins','Valor Cofins','PIS+Cofins','Total Bruto',
    'Nat Bc Créd - SERV','Código Produto','Descrição','Ncm','Cfop',
    'CST Pis.1','CST Cofins.1','Base Pis.1','Alíquota Pis',
    'Valor Pis','Base Cofins.1','Alíquota Cofins','Valor Cofins.1','Total Recolher'
]

IDX_NCM        = 18
IDX_TOTAL_NOTA = 4
IDX_COD_PROD   = 16
IDX_DESC_ITEM  = 17
IDX_CFOP_ITEM  = 19
IDX_CST_PIS1   = 20
IDX_BASE_PIS1  = 22
IDX_ALIQ_PIS1  = 23
IDX_VAL_PIS1   = 24
IDX_BASE_COF1  = 25
IDX_ALIQ_COF1  = 26
IDX_VAL_COF1   = 27
IDX_TOTAL_REC  = 28
IDX_ICMS_ITEM  = 29


def limpar_ncm(val):
    if pd.isna(val) or str(val).strip() == '': return ''
    try: return str(int(float(str(val).strip())))
    except: return str(val).strip()


def limpar_conta(val):
    return str(val).replace('.', '').strip() if val else val


def safe(val):
    return None if pd.isna(val) else val


def normalizar_df(df, log):
    cols = [str(c).strip() for c in df.columns]
    extras = [i for i, c in enumerate(cols)
              if 'NAT BC' in c.upper() or 'NAT. BC' in c.upper()
              or ('VALOR ICMS' in c.upper() and 'ITEM' not in c.upper() and i < 20)]
    if extras:
        df = df.drop(df.columns[extras], axis=1)
        log(f"      Removidas {len(extras)} coluna(s) extras")
    df.columns = range(len(df.columns))
    return df


def buscar_pct_proporcional(debitos_processado_path, log):
    """Lê o % proporcional (linha 'DEMAIS', col Z) do resultado de Débitos."""
    if not debitos_processado_path:
        log("   AVISO: nenhum arquivo de Débitos fornecido para o % proporcional")
        return None
    try:
        wb = load_workbook(debitos_processado_path, data_only=True)
        ws = wb['DEBITOS']
        for i in range(ws.max_row, max(1, ws.max_row - 50), -1):
            v = str(ws.cell(i, 24).value or '').strip().upper()  # col X
            if v == 'DEMAIS':
                pct = ws.cell(i, 26).value  # col Z
                f = float(pct)
                log(f"   % proporcional dos débitos: {f:.2%} (linha {i})")
                return f
        log("   AVISO: linha 'DEMAIS' não encontrada no arquivo de débitos")
    except Exception as e:
        log(f"   AVISO: erro ao ler % proporcional dos débitos: {e}")
    return None


def processar_creditos(xls_files, modelo, balancete, pct_proporcional, saida, log=print):
    """
    pct_proporcional: número já calculado pelo processar_debitos (não é
    lido de volta do .xlsx de Débitos — fórmulas escritas via openpyxl
    não têm valor em cache até serem abertas por um motor de planilha).
    """
    pct_prop_debitos = pct_proporcional
    if pct_prop_debitos is not None:
        log(f"   % proporcional recebido dos débitos: {pct_prop_debitos:.2%}")
    else:
        log("   AVISO: nenhum % proporcional fornecido")

    log("\n" + "="*60)
    log("PROCESSADOR PIS/COFINS - CRÉDITOS")
    log("="*60)

    log("\n[1] Lendo arquivos XLS...")
    if not xls_files:
        raise ValueError("Nenhum arquivo de filial (crédito) fornecido!")

    all_dfs = []
    for path in xls_files:
        fname = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        df = pd.read_excel(path, engine=engine, skiprows=5, header=0)
        df = df.dropna(how='all').reset_index(drop=True)
        df = normalizar_df(df, log)
        all_dfs.append(df)
        log(f"   OK: {fname} ({len(df)} linhas, {len(df.columns)} colunas)")

    if not all_dfs:
        raise ValueError("Nenhum arquivo lido!")

    combined = pd.concat(all_dfs, ignore_index=True)
    for col_idx in [0, 2, 3, 5]:
        combined.iloc[:, col_idx] = combined.iloc[:, col_idx].ffill()

    combined['_is_nf']   = combined.iloc[:, IDX_TOTAL_NOTA].notna() & combined.iloc[:, IDX_NCM].isna()
    combined['_is_item'] = combined.iloc[:, IDX_NCM].notna()
    log(f"   Total: {len(combined)} | NF: {combined['_is_nf'].sum()} | Itens: {combined['_is_item'].sum()}")

    log("\n[2] Carregando modelo...")
    if not modelo:
        raise ValueError("Modelo não fornecido!")

    wb_orig = load_workbook(modelo)
    ws_orig = wb_orig['CREDITOS']

    fmt_nf   = {cell.column: {'bold': cell.font.bold, 'numFmt': cell.number_format}
                for cell in ws_orig[2] if cell.has_style}
    fmt_item = {cell.column: {'numFmt': cell.number_format}
                for cell in ws_orig[3] if cell.has_style}
    col_widths = {col: ws_orig.column_dimensions[col].width
                  for col in ws_orig.column_dimensions}

    secao_fixa_inicio = None
    for i in range(1, ws_orig.max_row + 1):
        v26 = ws_orig.cell(i, 26).value
        v28 = ws_orig.cell(i, 28).value
        if v26 and v28 and 'DESCRI' in str(v26).upper() and 'CONTA' in str(v28).upper():
            secao_fixa_inicio = i

    log(f"   Seção fixa no modelo: linha {secao_fixa_inicio}")

    secao_fixa_data = []
    if secao_fixa_inicio:
        for i in range(secao_fixa_inicio, ws_orig.max_row + 1):
            row_data = {}
            for c in range(1, 50):
                cell = ws_orig.cell(i, c)
                if cell.value is not None:
                    row_data[c] = {
                        'value': cell.value,
                        'numFmt': cell.number_format,
                        'bold': cell.font.bold,
                        'fill': copy.copy(cell.fill),
                        'font': copy.copy(cell.font),
                        'alignment': copy.copy(cell.alignment),
                    }
            secao_fixa_data.append(row_data)
    log(f"   Seção fixa capturada: {len(secao_fixa_data)} linhas")
    wb_orig.close()

    import shutil
    shutil.copy(modelo, saida)
    wb = load_workbook(saida)

    if "CREDITOS" in wb.sheetnames:
        del wb["CREDITOS"]
    ws_cred = wb.create_sheet("CREDITOS", 0)
    ws_ncm  = wb["NCM"]
    bal_nome = next((n for n in wb.sheetnames if n.upper() == "BALANCETE"), None)
    if bal_nome is None:
        wb.create_sheet("Balancete")
        bal_nome = "Balancete"
    ws_bal = wb[bal_nome]

    for col, width in col_widths.items():
        ws_cred.column_dimensions[col].width = width

    cab = ['Empresa','Operação','Nota Fiscal','Serie','Total Nota','Data Entrada',
           'Isenta','Base Pis ','Base Cofins','CFOP','Valor PIS','CST Pis',
           'CST Cofins','Valor Cofins','PIS+Cofins','Total Bruto','Valor ICMS Normal ',
           'Nat Bc Créd - SERV ','Nat Bc Créd - PROD ','Código Produto','Descrição',
           'Ncm','Cfop','','CST Pis','CST Cofins','Base Pis','Alíquota Pis ',
           'Valor Pis','Base Cofins','Alíquota Cofins','Valor Cofins',
           'Total Recolher','Valor ICMS Normal Itens']
    for i, label in enumerate(cab, 1):
        ws_cred.cell(row=1, column=i, value=label).font = Font(bold=True)
    for col, label in [(37,'NCM'),(38,'TIPO'),(39,'PIS'),(40,'COFINS')]:
        ws_cred.cell(row=1, column=col, value=label).font = Font(bold=True)

    log("\n[3] Atualizando Balancete...")
    bal_max = ws_bal.max_row
    if balancete:
        log(f"   {os.path.basename(balancete)}")
        wb_bal_src = None
        try:
            wb_bal_src = load_workbook(balancete, read_only=True, data_only=True)
        except Exception:
            try:
                with zipfile.ZipFile(balancete, 'r') as zin:
                    xml = zin.read('xl/styles.xml').decode('utf-8')
                counter = [0]
                def fix_style(m):
                    tag = m.group(0)
                    if 'name=' not in tag:
                        tag = tag.replace('<cellStyle ', f'<cellStyle name="B{counter[0]}" ')
                        counter[0] += 1
                    return tag
                xml = re.sub(r'<cellStyle [^/]*/>', fix_style, xml)
                buf = io.BytesIO()
                with zipfile.ZipFile(balancete, 'r') as zin:
                    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
                        for item in zin.infolist():
                            data = xml.encode('utf-8') if item.filename == 'xl/styles.xml' else zin.read(item.filename)
                            zout.writestr(item, data)
                buf.seek(0)
                wb_bal_src = load_workbook(buf, read_only=True, data_only=True)
                log("   (estilos reparados automaticamente)")
            except Exception as e2:
                log(f"   AVISO: nao foi possivel abrir balancete ({e2})")

        if wb_bal_src:
            ws_bs = wb_bal_src.active
            COL_MAP = {1: 1, 2: 2, 3: 4, 4: 7, 5: 8, 6: 9}
            for row in ws_bal.iter_rows(min_row=4, max_row=ws_bal.max_row):
                for cell in row:
                    cell.value = None
            dest = 4
            for i, row in enumerate(ws_bs.iter_rows(min_row=4, values_only=True), start=4):
                if i == 4:
                    headers = ["Conta","Nome da Conta","Saldo Anterior","Devedor","Credor","Movimento do Mês"]
                    for j, h in enumerate(headers, 1):
                        ws_bal.cell(row=dest, column=j, value=h)
                    dest += 1
                    continue
                if row[0] is None: continue
                conta = limpar_conta(row[0])
                try: conta = int(conta)
                except: pass
                for dest_col, orig_col in COL_MAP.items():
                    v = row[orig_col - 1] if orig_col - 1 < len(row) else None
                    if dest_col == 1: v = conta
                    ws_bal.cell(row=dest, column=dest_col, value=v)
                dest += 1
            bal_max = dest - 1
            log(f"   {dest-5} linhas de dados (max_row={bal_max})")
    else:
        log("   Balancete nao encontrado - pulando")

    log("\n[4] Verificando NCMs...")
    existing_ncms = {}
    for row in ws_ncm.iter_rows(min_row=2, values_only=True):
        if row[0]: existing_ncms.setdefault(limpar_ncm(row[0]), row)  # 1ª ocorrência vence (igual VLOOKUP)

    missing_ncms = {}
    for _, row in combined[combined['_is_item']].iterrows():
        ncm = limpar_ncm(row.iloc[IDX_NCM])
        if ncm and ncm not in existing_ncms and ncm not in missing_ncms:
            pis = row.iloc[IDX_VAL_PIS1] if pd.notna(row.iloc[IDX_VAL_PIS1]) else 0
            cof = row.iloc[IDX_VAL_COF1] if pd.notna(row.iloc[IDX_VAL_COF1]) else 0
            try: pv, cv = float(pis), float(cof)
            except: pv = cv = 0
            tipo = "Normal NC" if (pv > 0 or cv > 0) else "Monofasico"
            missing_ncms[ncm] = (tipo, pv, cv)

    if missing_ncms:
        nr = ws_ncm.max_row + 1
        for ncm, (tipo, pv, cv) in missing_ncms.items():
            try: ncm_val = int(ncm)
            except: ncm_val = ncm
            ws_ncm.cell(row=nr, column=1, value=ncm_val)
            ws_ncm.cell(row=nr, column=2, value=tipo)
            ws_ncm.cell(row=nr, column=3, value=pv)
            ws_ncm.cell(row=nr, column=4, value=cv)
            nr += 1
        log(f"   {len(missing_ncms)} NCMs adicionados")
    else:
        log("   Todos cadastrados!")

    log("\n[5] Escrevendo dados...")
    dest_row = 2
    nf_rows = 0
    item_rows = 0
    for _, row in combined.iterrows():
        if row['_is_nf']:
            for col, idx in [(1,0),(2,1),(3,2),(4,3),(5,4),(6,5),(7,6),(8,7),(9,8),
                             (10,9),(11,10),(12,11),(13,12),(14,13),(15,14),(16,15),(17,16)]:
                cell = ws_cred.cell(row=dest_row, column=col, value=safe(row.iloc[idx]))
                if col in fmt_nf:
                    if fmt_nf[col].get('bold'): cell.font = Font(bold=True)
                    if fmt_nf[col].get('numFmt'): cell.number_format = fmt_nf[col]['numFmt']
            nf_rows += 1

        if row['_is_item']:
            r = dest_row
            ws_cred.cell(row=r, column=3,  value=safe(row.iloc[2]))
            ws_cred.cell(row=r, column=20, value=safe(row.iloc[IDX_COD_PROD]))
            ws_cred.cell(row=r, column=21, value=safe(row.iloc[IDX_DESC_ITEM]))
            ncm_str = limpar_ncm(row.iloc[IDX_NCM])
            try: ws_cred.cell(row=r, column=22, value=int(ncm_str))
            except: ws_cred.cell(row=r, column=22, value=ncm_str)
            ws_cred.cell(row=r, column=23, value=safe(row.iloc[IDX_CFOP_ITEM]))
            ws_cred.cell(row=r, column=24, value=f'=W{r}&" - "&AL{r}')
            for col, idx_d in [(25,IDX_CST_PIS1),(27,IDX_BASE_PIS1),(28,IDX_ALIQ_PIS1),
                               (29,IDX_VAL_PIS1),(30,IDX_BASE_COF1),(31,IDX_ALIQ_COF1),
                               (32,IDX_VAL_COF1),(33,IDX_TOTAL_REC)]:
                cell = ws_cred.cell(row=r, column=col, value=safe(row.iloc[idx_d]))
                if col in fmt_item and fmt_item[col].get('numFmt'):
                    cell.number_format = fmt_item[col]['numFmt']
            if IDX_ICMS_ITEM < len(row) and pd.notna(row.iloc[IDX_ICMS_ITEM]):
                ws_cred.cell(row=r, column=34, value=safe(row.iloc[IDX_ICMS_ITEM])).number_format = FMT_MOEDA
            for col, n in [(37,1),(38,2),(39,3),(40,4)]:
                ws_cred.cell(row=r, column=col, value=f'=IFERROR(VLOOKUP($V{r},NCM!$A:$D,{n},0),"")')
            item_rows += 1

        dest_row += 1

    last_data_row = dest_row - 1
    log(f"   NF: {nf_rows} | Itens: {item_rows} | Ultima linha: {last_data_row}")

    log("\n[6] Gerando resumo...")
    cfop_tipos = {}
    for _, row in combined[combined['_is_item']].iterrows():
        ncm = limpar_ncm(row.iloc[IDX_NCM])
        cfop = row.iloc[IDX_CFOP_ITEM]
        if not ncm or pd.isna(cfop): continue
        if ncm in existing_ncms: tipo = existing_ncms[ncm][1] or 'Normal NC'
        elif ncm in missing_ncms: tipo = missing_ncms[ncm][0]
        else: tipo = 'Normal NC'
        try: key = f"{int(cfop)} - {tipo}"
        except: key = f"{cfop} - {tipo}"
        cfop_tipos[key] = tipo

    normal_nc  = sorted([k for k, v in cfop_tipos.items() if 'Normal' in v])
    monofasico = sorted([k for k, v in cfop_tipos.items() if 'Monofas' in v])
    log(f"   Normal NC:  {normal_nc}")
    log(f"   Monofasico: {monofasico}")

    resumo_row   = last_data_row + 3
    subtotal_row = resumo_row + 1

    headers = [(27,"Base Pis"),(28,"Alíquota Pis "),(29,"Valor Pis"),
               (30,"Base Cofins"),(31,"Alíquota Cofins"),(32,"Valor Cofins"),
               (33,"Total Recolher"),(34,"Valor ICMS Normal Itens")]

    for col, label in headers:
        c = ws_cred.cell(row=resumo_row, column=col, value=label)
        c.number_format = FMT_RS

    for col, rng in [(27,"AA"),(29,"AC"),(30,"AD"),(32,"AF"),(33,"AG"),(34,"AH")]:
        ws_cred.cell(row=subtotal_row, column=col,
                     value=f"=SUBTOTAL(9,{rng}2:{rng}{last_data_row})").number_format = FMT_RS

    def escrever_tabela(header_row, descricoes, aliq_pis, aliq_cof):
        for col, label in [(26,"Descrição")] + headers:
            c = ws_cred.cell(row=header_row, column=col, value=label)
            c.font = Font(bold=True)
            c.number_format = FMT_RS
        first = header_row + 1
        for i, desc in enumerate(descricoes):
            r = first + i
            ws_cred.cell(row=r, column=26, value=desc)
            ws_cred.cell(row=r, column=27, value=f'=SUMIF($X$2:$X${last_data_row},Z{r},AA$2:AA${last_data_row})').number_format = FMT_RS
            ws_cred.cell(row=r, column=28, value=aliq_pis).number_format = FMT_PCT
            ws_cred.cell(row=r, column=29, value=f'=AA{r}*AB{r}').number_format = FMT_RS
            ws_cred.cell(row=r, column=30, value=f'=SUMIF($X$2:$X${last_data_row},$Z{r},AD$2:AD${last_data_row})').number_format = FMT_RS
            ws_cred.cell(row=r, column=31, value=aliq_cof).number_format = FMT_PCT
            ws_cred.cell(row=r, column=32, value=f'=AD{r}*AE{r}').number_format = FMT_RS
            ws_cred.cell(row=r, column=33, value=f'=AF{r}+AC{r}').number_format = FMT_RS
            ws_cred.cell(row=r, column=34, value=f'=SUMIF($X$2:$X${last_data_row},$Z{r},AH$2:AH${last_data_row})').number_format = FMT_RS
        last  = first + len(descricoes) - 1
        total = last + 1
        fill_amarelo = PatternFill("solid", fgColor="FFFF00")
        for col in range(26, 35):
            ws_cred.cell(row=total, column=col).fill  = fill_amarelo
            ws_cred.cell(row=total, column=col).font  = Font(bold=True)
        ws_cred.cell(row=total, column=26, value="TOTAL")
        for col, rng in [(27,'AA'),(29,'AC'),(30,'AD'),(32,'AF'),(33,'AG'),(34,'AH')]:
            ws_cred.cell(row=total, column=col, value=f'=SUM({rng}{first}:{rng}{last})').number_format = FMT_RS
        ws_cred.cell(row=total, column=28, value='-')
        ws_cred.cell(row=total, column=31, value='-')
        return total

    if not normal_nc: normal_nc = ['(sem lançamentos)']
    if not monofasico: monofasico = ['(sem lançamentos)']

    nc_header   = resumo_row + 3
    nc_total    = escrever_tabela(nc_header, normal_nc, 0.0165, 0.076)
    mono_header = nc_total + 2
    mono_total  = escrever_tabela(mono_header, monofasico, 0, 0)

    tg_row    = mono_total + 2
    check_row = tg_row + 1
    for row_n, label in [(tg_row,"TOTAL GERAL"),(check_row,"CHECK")]:
        ws_cred.cell(row=row_n, column=26, value=label).font = Font(bold=True)
    for col, c in [(27,'AA'),(29,'AC'),(30,'AD'),(32,'AF'),(33,'AG'),(34,'AH')]:
        ws_cred.cell(row=tg_row,    column=col, value=f'={c}{nc_total}+{c}{mono_total}').number_format = FMT_RS
        ws_cred.cell(row=check_row, column=col, value=f'={c}{tg_row}-{c}{subtotal_row}').number_format = FMT_RS
    for col in [28, 31]:
        ws_cred.cell(row=tg_row,    column=col, value='-')
        ws_cred.cell(row=check_row, column=col, value='-')

    log("\n[7] Copiando seção fixa do modelo...")
    if secao_fixa_data:
        dest_secao = check_row + 3
        row_offset = dest_secao - secao_fixa_inicio
        for offset, row_data in enumerate(secao_fixa_data):
            r = dest_secao + offset
            for c, fmt in row_data.items():
                v = fmt['value']
                if isinstance(v, str) and v.startswith('='):
                    v = re.sub(r'Balancete!\$A\$4:\$F\$\d+', f'Balancete!$A$4:$F${bal_max}', v)
                    for old_r in range(secao_fixa_inicio, secao_fixa_inicio + len(secao_fixa_data)):
                        new_r = old_r + row_offset
                        v = re.sub(rf'(\$[A-Z]{{1,2}})\${old_r}(?![0-9])', rf'\g<1>${new_r}', v)
                        v = re.sub(rf'([A-Z]{{1,2}}){old_r}(?![0-9])', rf'\g<1>{new_r}', v)
                cell = ws_cred.cell(r, c, value=v)
                if fmt.get('numFmt'): cell.number_format = fmt['numFmt']
                if fmt.get('fill'):   cell.fill      = fmt['fill']
                if fmt.get('font'):   cell.font       = fmt['font']
                if fmt.get('alignment'): cell.alignment = fmt['alignment']
        log(f"   Seção fixa colocada a partir da linha {dest_secao} ({len(secao_fixa_data)} linhas)")

        if pct_prop_debitos is not None:
            pct_linha_orig = secao_fixa_inicio + 1
            pct_linha_dest = dest_secao + (pct_linha_orig - secao_fixa_inicio)
            ws_cred.cell(pct_linha_dest, 31, value=round(pct_prop_debitos, 10))
            log(f"   % proporcional atualizado: {pct_prop_debitos:.2%} na linha {pct_linha_dest} col AE")

    ws_cred.auto_filter.ref = f"A1:AO{last_data_row}"

    log("\n[8] Aplicando formatação visual...")
    _formatar_planilha(ws_cred, header_row=1, freeze_cell="A2",
                        header_fill="1F4E78", header_font_color="FFFFFF",
                        max_col=34)
    _destacar_totais(ws_cred, [resumo_row, subtotal_row, tg_row, check_row],
                      cor_fundo="D9E1F2", min_col=26, max_col=34)

    log("\n[8] Salvando...")
    wb.save(saida)
    log(f"\nCONCLUIDO! Arquivo: {os.path.basename(saida)}")
    return saida
