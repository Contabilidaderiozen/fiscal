"""
gerar_pdf_retencoes.py — Gera dois PDFs a partir do resultado já calculado
pelo pipeline de NFS-e Entrada (nfse_entrada.verificar_retencoes):

  1) PDF de Auditoria — lista todas as notas do período com as retenções
     esperadas vs. as que de fato constam na nota, destacando onde deveria
     ter havido retenção e não houve (e vice-versa).

  2) PDF para a EFD-Reinf — formato simples e direto: número da nota, valor,
     e o valor de cada retenção (IRRF/PIS/COFINS/CSLL) quando houver —
     pronto pra apoiar o lançamento do evento de retenção (R-4020).

Não substitui o preenchimento oficial da Reinf — é um documento de apoio
com os valores já calculados, pra facilitar a conferência e o lançamento.
"""
import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

PRETO = colors.black
CINZA_CLARO = colors.HexColor("#e8e8e8")
VERMELHO_CLARO = colors.HexColor("#ffe0e0")
AMARELO_CLARO = colors.HexColor("#fff3cd")
VERDE_CLARO = colors.HexColor("#e8f5ea")


def _moeda(v):
    try:
        return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _cabecalho(titulo, cnpj_tomador, periodo):
    estilo_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, alignment=TA_CENTER, spaceAfter=4)
    estilo_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, alignment=TA_CENTER, textColor=colors.HexColor("#444444"))
    return [
        Paragraph(titulo, estilo_titulo),
        Paragraph(f"CNPJ Tomador: {cnpj_tomador}  •  Período: {periodo}", estilo_sub),
        Spacer(1, 12),
    ]


def gerar_pdf_auditoria_retencoes(notas_analisadas: list, cnpj_tomador: str,
                                   periodo: str, caminho_saida: str) -> str:
    """PDF completo de conferência: todas as notas, com o que deveria ter
    sido retido vs. o que realmente consta, e destaque nas divergências."""
    os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)
    doc = SimpleDocTemplate(caminho_saida, pagesize=landscape(A4),
                             leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    story = _cabecalho("Auditoria de Retenções — NFS-e Entrada", cnpj_tomador, periodo)

    cabecalho_tab = ["Nota", "Prestador", "Código", "Valor Nota",
                     "IRRF Esp.", "IRRF Nota", "PIS Esp.", "PIS Nota",
                     "COFINS Esp.", "COFINS Nota", "CSLL Esp.", "CSLL Nota", "Status"]
    linhas = [cabecalho_tab]
    cores_linha = []

    divergentes = []
    for n in notas_analisadas:
        status = n.get("status_geral", "")
        linhas.append([
            str(n.get("numero", "")),
            (n.get("prestador_nome", "") or "")[:28],
            str(n.get("codigo_servico", "")),
            _moeda(n.get("valor_servico")),
            _moeda(n.get("irrf_esperado")), _moeda(n.get("irrf_retido_nota")),
            _moeda(n.get("pis_esperado")), _moeda(n.get("pis_retido_nota")),
            _moeda(n.get("cofins_esperado")), _moeda(n.get("cofins_retido_nota")),
            _moeda(n.get("csll_esperado")), _moeda(n.get("csll_retido_nota")),
            status,
        ])
        if status == "DIVERGENCIA":
            cores_linha.append(VERMELHO_CLARO)
            divergentes.append(n)
        elif status == "PCC_NAO_VERIFICADO":
            cores_linha.append(AMARELO_CLARO)
        else:
            cores_linha.append(VERDE_CLARO)

    tabela = Table(linhas, repeatRows=1)
    estilo = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-2, -1), "RIGHT"),
    ]
    for i, cor in enumerate(cores_linha, start=1):
        estilo.append(("BACKGROUND", (0, i), (-1, i), cor))
    tabela.setStyle(TableStyle(estilo))
    story.append(tabela)

    # ── Resumo de divergências ────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"<b>{len(divergentes)} nota(s) com divergência de retenção</b> "
        f"(de {len(notas_analisadas)} nota(s) no período)",
        ParagraphStyle("resumo", fontName="Helvetica-Bold", fontSize=10),
    ))
    if divergentes:
        story.append(Spacer(1, 6))
        for n in divergentes:
            alertas = "; ".join(n.get("alertas", []))
            story.append(Paragraph(
                f"• Nota {n.get('numero','')} — {n.get('prestador_nome','')}: {alertas}",
                ParagraphStyle("alerta", fontName="Helvetica", fontSize=8, leftIndent=10),
            ))

    doc.build(story)
    return caminho_saida


def gerar_pdf_reinf(notas_analisadas: list, cnpj_tomador: str,
                     periodo: str, caminho_saida: str) -> str:
    """PDF simples e direto pra apoiar o lançamento na EFD-Reinf: número da
    nota, valor, e cada retenção (IRRF/PIS/COFINS/CSLL) quando houver."""
    os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)
    doc = SimpleDocTemplate(caminho_saida, pagesize=A4,
                             leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = _cabecalho("Retenções na Fonte — Apoio EFD-Reinf (Evento R-4020)", cnpj_tomador, periodo)

    cabecalho_tab = ["Nota", "Prestador", "CNPJ Prestador", "Valor da Nota",
                     "IRRF", "PIS", "COFINS", "CSLL", "Total Retido"]
    linhas = [cabecalho_tab]
    total_geral = {"irrf": 0.0, "pis": 0.0, "cofins": 0.0, "csll": 0.0, "valor": 0.0}

    notas_com_retencao = 0
    for n in notas_analisadas:
        irrf = float(n.get("irrf_retido_nota") or n.get("irrf_esperado") or 0)
        pis = float(n.get("pis_retido_nota") or n.get("pis_esperado") or 0)
        cofins = float(n.get("cofins_retido_nota") or n.get("cofins_esperado") or 0)
        csll = float(n.get("csll_retido_nota") or n.get("csll_esperado") or 0)
        total = round(irrf + pis + cofins + csll, 2)
        if total > 0:
            notas_com_retencao += 1

        total_geral["irrf"] += irrf
        total_geral["pis"] += pis
        total_geral["cofins"] += cofins
        total_geral["csll"] += csll
        total_geral["valor"] += float(n.get("valor_servico") or 0)

        linhas.append([
            str(n.get("numero", "")),
            (n.get("prestador_nome", "") or "")[:26],
            n.get("prestador_cnpj", ""),
            _moeda(n.get("valor_servico")),
            _moeda(irrf) if irrf else "—",
            _moeda(pis) if pis else "—",
            _moeda(cofins) if cofins else "—",
            _moeda(csll) if csll else "—",
            _moeda(total) if total else "—",
        ])

    linhas.append([
        "TOTAL", "", "", _moeda(total_geral["valor"]),
        _moeda(total_geral["irrf"]), _moeda(total_geral["pis"]),
        _moeda(total_geral["cofins"]), _moeda(total_geral["csll"]),
        _moeda(sum(v for k, v in total_geral.items() if k != "valor")),
    ])

    tabela = Table(linhas, repeatRows=1)
    tabela.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), CINZA_CLARO),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tabela)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"{notas_com_retencao} de {len(notas_analisadas)} nota(s) com alguma retenção no período.",
        ParagraphStyle("resumo2", fontName="Helvetica", fontSize=9),
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Documento de apoio gerado pelo Riozen Fiscal — os valores usados são os retidos na "
        "própria nota quando informados, ou o valor esperado calculado pela tabela de retenção "
        "quando a nota não trouxer o valor. Conferir antes de lançar na EFD-Reinf.",
        ParagraphStyle("rodape2", fontName="Helvetica-Oblique", fontSize=7, textColor=colors.HexColor("#555555")),
    ))

    doc.build(story)
    return caminho_saida
