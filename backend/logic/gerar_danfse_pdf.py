"""
gerar_danfse_pdf.py — Gera um PDF no formato do DANFSe (Documento Auxiliar
da NFS-e), calibrado contra um documento oficial real (nota da Webmotors,
emitida em São Paulo) usado como referência nesta conversa.

Cobre todas as seções do modelo oficial: cabeçalho, chave de acesso, grid
de identificação, prestador, tomador, destinatário/intermediário, serviço,
tributação municipal (ISSQN), tributação federal, tributação IBS/CBS
(Reforma Tributária, 5 blocos de campo) e valor total.

Não é uma cópia pixel-a-pixel do documento oficial (fonte exata, logo
oficial "NFSe", algoritmo de QR code do SERPRO) — mas replica a mesma
estrutura de seções, mesmos rótulos e mesma organização em tabelas, com
QR code apontando pra consulta da chave de acesso no portal nacional.

Uso:
    from gerar_danfse_pdf import gerar_pdf_nota, gerar_lote_pdfs
    gerar_pdf_nota(dados, "nota_600.pdf")
    gerar_lote_pdfs([dados1, dados2, ...], "pasta_destino", "lote.zip")
"""
import os
import zipfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Image, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

LARGURA_PAGINA, _ = A4
MARGEM = 8 * mm
LARGURA_UTIL = LARGURA_PAGINA - 2 * MARGEM

PRETO = colors.black
CINZA_CLARO = colors.HexColor("#e8e8e8")
CINZA_ESCURO = colors.HexColor("#333333")

FONTE_LABEL = ("Helvetica-Bold", 5.8)
FONTE_VALOR = ("Helvetica", 8)
FONTE_SECAO = ("Helvetica-Bold", 7.5)


def _fmt(v, prefixo=""):
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{prefixo}{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefixo}{v}"


def _fmt_pct(v):
    if v is None or v == "":
        return "-"
    try:
        return f"{float(str(v).replace(',', '.')):,.2f} %".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v) + " %"


def _fmt_data(v):
    if not v:
        return "-"
    try:
        from datetime import datetime
        s = v.replace("Z", "")
        if "+" in s[10:]:
            s = s[:s.index("+", 10)]
        elif s.count("-") > 2:
            s = s[:s.rindex("-")]
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return v


def _fmt_data_curta(v):
    if not v:
        return "-"
    d = _fmt_data(v)
    return d.split(" ")[0] if " " in d else d


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_ESTILO_LABEL = ParagraphStyle("lbl", fontName=FONTE_LABEL[0], fontSize=FONTE_LABEL[1], textColor=CINZA_ESCURO, leading=FONTE_LABEL[1]+2)
_ESTILO_VALOR = ParagraphStyle("val", fontName=FONTE_VALOR[0], fontSize=FONTE_VALOR[1], leading=FONTE_VALOR[1]+2.5, wordWrap="CJK")

def _tabela_campos(pares, larguras=None, linha_inferior=False, largura_total=None):
    """pares: lista de (rótulo, valor). 2 linhas — rótulos em cima, valores
    embaixo. Usa Paragraph (não string crua) nas células, pra garantir
    quebra de linha mesmo em textos bem longos (ex: descrição do serviço).
    linha_inferior=True desenha uma linha fina embaixo (usado só no bloco
    de identificação da NFS-e, que tem divisórias entre cada linha —
    diferente de Prestador/Tomador, que não têm linha entre os campos).
    largura_total: usar quando a tabela NÃO ocupa a página inteira (ex:
    dentro do bloco de identificação, que divide espaço com o QR code)."""
    n = len(pares)
    total = largura_total if largura_total is not None else LARGURA_UTIL
    if larguras is None:
        larguras = [total / n] * n
    labels = [Paragraph(_esc(p[0]).upper(), _ESTILO_LABEL) for p in pares]
    valores = []
    for p in pares:
        if isinstance(p[1], Paragraph):
            valores.append(p[1])
        else:
            valores.append(Paragraph(_esc(p[1]) if p[1] not in (None, "") else "-", _ESTILO_VALOR))
    t = Table([labels, valores], colWidths=larguras)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if linha_inferior:
        estilo.append(("LINEBELOW", (0, 1), (-1, 1), 0.5, PRETO))
    t.setStyle(TableStyle(estilo))
    return t


def _linha_texto_simples(texto):
    """Uma linha só, com uma frase (ex: "DESTINATÁRIO ... NÃO IDENTIFICADO")."""
    estilo = ParagraphStyle("simples", fontName="Helvetica", fontSize=7, alignment=TA_CENTER, leading=9)
    t = Table([[Paragraph(_esc(texto), estilo)]], colWidths=[LARGURA_UTIL])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, PRETO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _barra_secao(titulo):
    t = Table([[titulo.upper()]], colWidths=[LARGURA_UTIL])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONTE_SECAO[0]),
        ("FONTSIZE", (0, 0), (-1, -1), FONTE_SECAO[1]),
        ("BACKGROUND", (0, 0), (-1, -1), CINZA_CLARO),
        ("LINEABOVE", (0, 0), (-1, 0), 0.75, PRETO),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, PRETO),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _gerar_qrcode_flowable(chave_acesso, tamanho=24 * mm):
    try:
        import qrcode
        import io
        url = f"https://www.nfse.gov.br/consultanacional/#/consulta/{chave_acesso}"
        img = qrcode.make(url, box_size=4, border=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Image(buf, width=tamanho, height=tamanho)
    except Exception:
        return Spacer(tamanho, tamanho)


def _desenhar_moldura(canvas, doc):
    """Desenha uma borda em volta de toda a página (moldura externa do
    documento), repetida em toda página — igual ao papel timbrado fiscal."""
    canvas.saveState()
    canvas.setLineWidth(0.75)
    canvas.setStrokeColor(PRETO)
    canvas.rect(MARGEM, MARGEM, LARGURA_PAGINA - 2 * MARGEM, doc.pagesize[1] - 2 * MARGEM)
    canvas.restoreState()


def gerar_pdf_nota(dados: dict, caminho_saida: str):
    os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)
    doc = SimpleDocTemplate(
        caminho_saida, pagesize=A4,
        leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM, bottomMargin=MARGEM,
    )
    story = []
    p = dados.get("prestador") or {}
    t = dados.get("tomador") or {}

    # ── Cabeçalho ─────────────────────────────────────────────────────────
    COR_VERDE_LOGO = colors.HexColor("#2e8b3d")
    COR_AZUL_LOGO = colors.HexColor("#1565c0")
    COR_AZUL_INFO = colors.HexColor("#1a5276")

    estilo_logo = ParagraphStyle("logo", fontName="Helvetica-Bold", fontSize=17, leading=18)
    estilo_logo_sub = ParagraphStyle("logosub", fontName="Helvetica", fontSize=6.5, textColor=COR_AZUL_INFO, leading=8)
    bloco_logo = [
        Paragraph('<font color="#2e8b3d">NFS</font><font color="#1565c0">e</font>', estilo_logo),
        Paragraph("Nota Fiscal de<br/>Serviço eletrônica", estilo_logo_sub),
    ]

    estilo_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=11, alignment=TA_CENTER, leading=13)
    bloco_titulo = [Paragraph("DANFSe v2.0", estilo_titulo),
                    Paragraph("Documento Auxiliar da NFS-e", ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER))]

    municipio_txt = f"{dados.get('municipio_emissao') or '-'} - {dados.get('uf_emissao') or '-'}"
    info_topo = Paragraph(
        f"<b>Município:</b> {municipio_txt}<br/>"
        f"<b>Ambiente Gerador:</b> {dados.get('tpAmb') or '1'}<br/>"
        f"<b>Tipo de Ambiente:</b> {dados.get('tpAmb') or '1'}",
        ParagraphStyle("info", fontName="Helvetica", fontSize=7, leading=9.5, alignment=TA_LEFT, textColor=COR_AZUL_INFO),
    )
    cabecalho_topo = Table(
        [[bloco_logo, bloco_titulo, info_topo]],
        colWidths=[LARGURA_UTIL * 0.28, LARGURA_UTIL * 0.40, LARGURA_UTIL * 0.32],
    )
    cabecalho_topo.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    cabecalho = Table([[cabecalho_topo]], colWidths=[LARGURA_UTIL])
    cabecalho.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, PRETO),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(cabecalho)

    # ── Bloco de identificação da NFS-e (chave + grid 3x3) + QR code ───────
    # O QR fica AQUI (não no cabeçalho) — no canto superior direito deste
    # bloco, ocupando a altura toda dele.
    situ_desc = "NFS-e Gerada" if dados.get("cStat") == "100" else (dados.get("cStat") or "-")
    fin_map = {"1": "NFS-e regular"}
    finalidade_txt = fin_map.get(dados.get("finalidade"), dados.get("finalidade") or "NFS-e regular")

    LARGURA_BLOCO_ESQ = LARGURA_UTIL * 0.76

    bloco_identif_esquerda = [
        _tabela_campos([("Chave de Acesso da NFS-e", dados.get("chave_acesso") or "")],
                       largura_total=LARGURA_BLOCO_ESQ),
        _tabela_campos([
            ("Número da NFS-e", dados.get("numero") or ""),
            ("Competência da NFS-e", _fmt_data_curta(dados.get("competencia"))),
            ("Data e Hora da Emissão da NFS-e", _fmt_data(dados.get("dhEmi"))),
        ], largura_total=LARGURA_BLOCO_ESQ),
        _tabela_campos([
            ("Número da DPS", dados.get("nDPS") or ""),
            ("Série da DPS", dados.get("serie") or ""),
            ("Data e Hora da Emissão da DPS", _fmt_data(dados.get("dhEmiDPS")) or _fmt_data(dados.get("dhEmi"))),
        ], largura_total=LARGURA_BLOCO_ESQ),
        _tabela_campos([
            ("Emitente da NFS-e", "Prestador"),
            ("Situação da NFS-e", situ_desc),
            ("Finalidade", finalidade_txt),
        ], largura_total=LARGURA_BLOCO_ESQ),
    ]

    qr_bloco_direita = [
        _gerar_qrcode_flowable(dados.get("chave_acesso") or ""),
        Spacer(1, 3),
        Paragraph("A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR ou pela "
                  "consulta da chave de acesso no portal nacional da NFS-e",
                  ParagraphStyle("qrtxt", fontName="Helvetica", fontSize=6, leading=7.5)),
    ]

    bloco_identificacao = Table(
        [[bloco_identif_esquerda, qr_bloco_direita]],
        colWidths=[LARGURA_BLOCO_ESQ, LARGURA_UTIL - LARGURA_BLOCO_ESQ],
    )
    bloco_identificacao.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.75, PRETO),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, PRETO),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bloco_identificacao)

    # ── Prestador ────────────────────────────────────────────────────────
    story.append(_barra_secao("Prestador / Fornecedor"))
    story.append(_tabela_campos([
        ("CNPJ / CPF / NIF", p.get("cnpj") or p.get("cpf") or p.get("nif") or ""),
        ("Indicador Municipal (Inscrição)", p.get("im") or ""),
        ("Telefone", p.get("fone") or ""),
    ]))
    story.append(_tabela_campos([
        ("Nome / Nome Empresarial", p.get("nome") or ""),
        ("Município / UF", f"{p.get('municipio') or ''} / {p.get('uf') or ''}" if p.get("municipio") else ""),
        ("Código IBGE / CEP", f"{p.get('cmun') or '-'} / {p.get('cep') or '-'}"),
    ], larguras=[LARGURA_UTIL * 0.5, LARGURA_UTIL * 0.25, LARGURA_UTIL * 0.25]))
    story.append(_tabela_campos([
        ("Endereço", p.get("endereco") or ""),
        ("E-mail", p.get("email") or ""),
    ], larguras=[LARGURA_UTIL * 0.6, LARGURA_UTIL * 0.4]))
    story.append(_tabela_campos([
        ("Simples Nacional na Data de Competência", p.get("simples_nacional") or "Não Optante"),
        ("Regime de Apuração Tributária pelo SN", p.get("regime_apuracao") or ""),
    ]))

    # ── Tomador ──────────────────────────────────────────────────────────
    story.append(_barra_secao("Tomador / Adquirente"))
    story.append(_tabela_campos([
        ("CNPJ / CPF / NIF", t.get("cnpj") or t.get("cpf") or t.get("nif") or ""),
        ("Indicador Municipal (Inscrição)", t.get("im") or ""),
        ("Telefone", t.get("fone") or ""),
    ]))
    story.append(_tabela_campos([
        ("Nome / Nome Empresarial", t.get("nome") or ""),
        ("Município / UF", f"{t.get('municipio') or ''} / {t.get('uf') or ''}" if t.get("municipio") else ""),
        ("Código IBGE / CEP", f"{t.get('cmun') or '-'} / {t.get('cep') or '-'}"),
    ], larguras=[LARGURA_UTIL * 0.5, LARGURA_UTIL * 0.25, LARGURA_UTIL * 0.25]))
    story.append(_tabela_campos([("Endereço", t.get("endereco") or ""), ("E-mail", t.get("email") or "")],
                                 larguras=[LARGURA_UTIL * 0.6, LARGURA_UTIL * 0.4]))

    # ── Destinatário / Intermediário ────────────────────────────────────
    if dados.get("destinatario"):
        story.append(_linha_texto_simples(f"DESTINATÁRIO DA OPERAÇÃO: {dados['destinatario'].get('nome','')}"))
    else:
        story.append(_linha_texto_simples("DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"))
    if dados.get("intermediario"):
        story.append(_linha_texto_simples(f"INTERMEDIÁRIO DA OPERAÇÃO: {dados['intermediario'].get('nome','')}"))
    else:
        story.append(_linha_texto_simples("INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"))

    # ── Serviço ──────────────────────────────────────────────────────────
    story.append(_barra_secao("Serviço Prestado"))
    story.append(_tabela_campos([
        ("Código de Tributação Nacional / Municipal",
         f"{dados.get('codigo_servico') or ''} / {dados.get('codigo_servico_mun') or '-'}"),
        ("Código da NBS", dados.get("codigo_nbs") or ""),
        ("Local da Prestação / Sigla UF / País",
         f"{dados.get('municipio_emissao') or ''} / {dados.get('uf_emissao') or ''} / -"),
    ]))
    if dados.get("descricao_codigo"):
        story.append(_tabela_campos([("", dados.get("descricao_codigo"))]))
    story.append(_tabela_campos([("Descrição do Serviço", dados.get("descricao_servico") or "")]))

    # ── Tributação Municipal (ISSQN) ────────────────────────────────────
    story.append(_barra_secao("Tributação Municipal (ISSQN)"))
    story.append(_tabela_campos([
        ("Tipo de Tributação do ISSQN", dados.get("tipo_tributacao_issqn_desc") or "Operação Tributável"),
        ("Município / Sigla UF / País de Incidência do ISSQN",
         f"{dados.get('municipio_emissao') or ''} / {dados.get('uf_emissao') or ''} / -"),
    ]))
    story.append(_tabela_campos([
        ("BC ISSQN", _fmt(dados.get("valor_bc_iss"), "R$ ")),
        ("Alíquota Aplicada", _fmt_pct(dados.get("aliquota_iss"))),
        ("Retenção do ISSQN", "Retido" if dados.get("iss_retido_pelo_tomador") else "Não Retido"),
        ("ISSQN Apurado", _fmt(dados.get("valor_iss"), "R$ ")),
    ]))

    # ── Tributação Federal (exceto CBS) ─────────────────────────────────
    story.append(_barra_secao("Tributação Federal (Exceto CBS)"))
    story.append(_tabela_campos([
        ("IRRF", _fmt(dados.get("irrf"), "R$ ")),
        ("Contribuição Previdenciária - Retida", _fmt(dados.get("contrib_previdenciaria_retida"), "R$ ")),
        ("Contribuições Sociais - Retidas", _fmt(dados.get("contrib_sociais_retidas"), "R$ ")),
    ]))
    story.append(_tabela_campos([
        ("PIS - Débito Apuração Própria", _fmt(dados.get("pis_debito"), "R$ ")),
        ("COFINS - Débito Apuração Própria", _fmt(dados.get("cofins_debito"), "R$ ")),
        ("Descrição Contrib. Sociais - Retidas", dados.get("descricao_contrib_sociais_retidas") or ""),
    ]))

    # ── Tributação IBS/CBS (best-effort) ────────────────────────────────
    story.append(_barra_secao("Tributação IBS / CBS"))
    story.append(_tabela_campos([
        ("CST / cClassTrib", f"{dados.get('cst_ibscbs') or '-'} / {dados.get('cclasstrib') or '-'}"),
        ("Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF",
         f"{dados.get('indicador_operacao_ibscbs') or '-'} / {dados.get('codigo_ibge_incidencia_ibscbs') or '-'} / "
         f"{dados.get('municipio_incidencia_ibscbs') or dados.get('municipio_emissao') or '-'} / {dados.get('uf_incidencia_ibscbs') or dados.get('uf_emissao') or '-'}"),
    ], larguras=[LARGURA_UTIL * 0.35, LARGURA_UTIL * 0.65]))
    story.append(_tabela_campos([
        ("Exclusões e Reduções da Base de Cálculo", _fmt(dados.get("exclusoes_reducoes_bc_ibscbs"), "R$ ")),
        ("Base de Cálculo Após Exclusões e Reduções", _fmt(dados.get("bc_apos_exclusoes_ibscbs"), "R$ ")),
        ("Red. Alíquota IBS / Red. Alíquota CBS",
         f"{dados.get('red_aliq_ibs') or '-'} / {dados.get('red_aliq_cbs') or '-'}"),
    ]))
    story.append(_tabela_campos([
        ("Alíquota - IBS UF / IBS Mun", f"{dados.get('aliq_ibs_uf') or '-'} / {dados.get('aliq_ibs_mun') or '-'}"),
        ("Alíq. Efetiva Municipal - IBS", _fmt_pct(dados.get("aliq_efetiva_municipal_ibs"))),
        ("Valor Apurado Municipal - IBS", _fmt(dados.get("valor_apurado_municipal_ibs"), "R$ ")),
    ]))
    story.append(_tabela_campos([
        ("Alíq. Efetiva Estadual - IBS", _fmt_pct(dados.get("aliq_efetiva_estadual_ibs"))),
        ("Valor Apurado Estadual - IBS", _fmt(dados.get("valor_apurado_estadual_ibs"), "R$ ")),
        ("Valor Total Apurado - IBS", _fmt(dados.get("valor_total_apurado_ibs"), "R$ ")),
    ]))
    story.append(_tabela_campos([
        ("Alíquota - CBS", _fmt_pct(dados.get("aliq_cbs"))),
        ("Alíquota Efetiva - CBS", _fmt_pct(dados.get("aliq_efetiva_cbs"))),
        ("Valor Total Apurado - CBS", _fmt(dados.get("valor_total_apurado_cbs"), "R$ ")),
    ]))

    # ── Valor total ───────────────────────────────────────────────────────
    story.append(_barra_secao("Valor Total da NFS-e"))
    story.append(_tabela_campos([
        ("Valor da Operação / Serviço", _fmt(dados.get("valor_servico"), "R$ ")),
        ("Desconto Incondicionado", _fmt(dados.get("desconto_incondicionado"), "R$ ")),
        ("Desconto Condicionado", _fmt(dados.get("desconto_condicionado"), "R$ ")),
    ]))
    valor_liq_total = dados.get("valor_liquido")
    if valor_liq_total is not None and dados.get("valor_total_ibscbs"):
        valor_liq_mais_ibscbs = round(valor_liq_total, 2)
    else:
        valor_liq_mais_ibscbs = valor_liq_total
    story.append(_tabela_campos([
        ("Total das Retenções (ISSQN / Federais)", _fmt(dados.get("total_retencoes"), "R$ ")),
        ("Valor Líquido da NFS-e", _fmt(dados.get("valor_liquido"), "R$ ")),
        ("Total do IBS/CBS", _fmt(dados.get("valor_total_ibscbs"), "R$ ")),
        ("Valor Líquido da NFS-e + IBS/CBS", _fmt(valor_liq_mais_ibscbs, "R$ ")),
    ]))

    # ── Informações complementares ──────────────────────────────────────
    story.append(_barra_secao("Informações Complementares"))
    linhas_info = []
    if dados.get("numero_rps"):
        linhas_info.append(f"Número RPS.: {dados.get('numero_rps')}")
    linhas_info.append(
        f"Totais Aproximados dos Tributos cfe. Lei n° 12.741/2012: "
        f"Federais: {_fmt(dados.get('totais_aprox_federais') or 0.0, 'R$ ')}; "
        f"Estaduais: {_fmt(dados.get('totais_aprox_estaduais') or 0.0, 'R$ ')}; "
        f"Municipais: {_fmt(dados.get('totais_aprox_municipais'), 'R$ ')};"
    )
    valor_info = Paragraph("<br/>".join(_esc(l) for l in linhas_info), _ESTILO_VALOR)
    story.append(_tabela_campos([("", valor_info)]))

    # ── Rodapé de assinatura ──────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(_tabela_campos([
        ("Data Cientificação", ""),
        ("Identificação e Assinatura", ""),
        ("N° NFS-e / Chave NFS-e", f"{dados.get('numero') or ''} / {dados.get('chave_acesso') or ''}"),
    ], larguras=[LARGURA_UTIL * 0.25, LARGURA_UTIL * 0.35, LARGURA_UTIL * 0.4]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Documento gerado internamente pelo Riozen Fiscal a partir dos dados oficiais consultados na API "
        "ADN Contribuinte (Receita Federal) — réplica aproximada do DANFSe oficial, que pode ser consultado no "
        "Portal Nacional da NFS-e usando a chave de acesso acima.",
        ParagraphStyle("rodape", fontName="Helvetica-Oblique", fontSize=6, textColor=CINZA_ESCURO, leading=7.5),
    ))

    doc.build(story, onFirstPage=_desenhar_moldura, onLaterPages=_desenhar_moldura)
    return caminho_saida


def gerar_lote_pdfs(lista_dados: list, pasta_temp: str, caminho_zip: str, callback_log=None) -> str:
    def log(msg):
        if callback_log:
            callback_log(msg)

    os.makedirs(pasta_temp, exist_ok=True)
    caminhos = []
    for i, dados in enumerate(lista_dados):
        numero = dados.get("numero") or f"item{i+1}"
        nome_arquivo = f"NFSE_{numero}.pdf".replace("/", "-")
        caminho = os.path.join(pasta_temp, nome_arquivo)
        try:
            gerar_pdf_nota(dados, caminho)
            caminhos.append(caminho)
            log(f"  PDF gerado: {nome_arquivo}")
        except Exception as ex:
            log(f"  AVISO: falha ao gerar PDF da nota {numero}: {ex}")

    os.makedirs(os.path.dirname(caminho_zip) or ".", exist_ok=True)
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for c in caminhos:
            zf.write(c, arcname=os.path.basename(c))

    log(f"ZIP gerado com {len(caminhos)} PDF(s): {caminho_zip}")
    return caminho_zip
