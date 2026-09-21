"""
icms_apuracao.py — Apuração de ICMS para livros fiscais do NBS
==============================================================
Lógica de colunas (SAIDAS):
  col1=CFOP  col2=Base  col3=Imp.Debitado(FECP base)
  col4=ICMS próprio(crédito)  col5=Op.Débito  col6=Outros

Fórmula unificada (funciona mesmo quando NBS já fez parte do cálculo):
  FECP            = col3_total × 2%
  credits_applied = col4 dos CFOPs especiais já na seção de créditos p.2
  credits_not_yet = col4 dos CFOPs especiais NÃO na seção de créditos p.2
  ICMS a pagar    = 013 + credits_applied - credits_not_yet - FECP
  FECP a pagar    = FECP
"""

import re
import pdfplumber
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


CFOPS_CREDITO = {
    "6108": "Saída c/ Crédito",
    "6404": "Saída ST",
    "6411": "Devolução",
    "5949": "Retorno",
    "5551": "Ativo Imobilizado",
}
ALIQUOTA_FECP = 0.02


@dataclass
class LinhaCFOP:
    cfop:          str
    descricao:     str
    base_total:    float
    imp_debitado:  float   # col3 — base FECP
    icms_proprio:  float   # col4 — crédito
    op_debito:     float
    outros:        float


@dataclass
class ApuracaoICMS:
    empresa:            str
    cnpj:               str
    insc_est:           str
    periodo:            str
    linhas:             List[LinhaCFOP] = field(default_factory=list)
    # Linhas de ENTRADAS do Livro Fiscal (aditivo — não usado na fórmula
    # de ICMS/FECP original, apenas exposto para comparação com o livro
    # próprio montado a partir do Livro de Entrada detalhado).
    linhas_entrada:     List[LinhaCFOP] = field(default_factory=list)
    # Totais de saídas
    fecp_base:          float = 0.0   # col3 total
    col4_total:         float = 0.0   # col4 total = campo 001
    # 013 extraído da pág. 2
    icms_013:           float = 0.0
    # Créditos
    credits_applied:    Dict[str, float] = field(default_factory=dict)  # já aplicados NBS
    credits_not_yet:    Dict[str, float] = field(default_factory=dict)  # NBS não aplicou
    total_applied:      float = 0.0
    total_not_yet:      float = 0.0
    # FECP
    fecp:               float = 0.0
    fecp_no_nbs:        bool  = False   # True se NBS já calculou FECP
    # Guias já no NBS
    icms_guia_nbs:      float = 0.0   # valor guia 0213 (ICMS)
    fecp_guia_nbs:      float = 0.0   # valor guia 7501 (FECP)
    # Resultado final
    icms_a_pagar:       float = 0.0
    fecp_a_pagar:       float = 0.0
    # Flags de status
    tudo_correto_nbs:   bool  = False   # True se NBS já estava correto
    observacoes:        List[str] = field(default_factory=list)


def apurar_icms(caminho_pdf: str, callback_log=None) -> ApuracaoICMS:
    def log(msg):
        if callback_log: callback_log(msg)

    log("📄 Lendo Livro Fiscal ICMS...")
    with pdfplumber.open(caminho_pdf) as pdf:
        paginas = [p.extract_text() or "" for p in pdf.pages]

    p1 = paginas[0] if paginas else ""
    p2 = paginas[1] if len(paginas) > 1 else ""

    empresa, cnpj, insc_est, periodo = _extrair_cabecalho(p1)
    log(f"   Empresa:  {empresa}")
    log(f"   CNPJ:     {cnpj}")
    log(f"   Período:  {periodo}")

    linhas = _extrair_cfops_saida(p1)
    log(f"   {len(linhas)} CFOPs de saída encontrados.")

    # Aditivo: também lê a seção ENTRADAS do mesmo Livro Fiscal (página 1),
    # só para expor os totais oficiais por código e permitir comparação
    # com o livro próprio montado do Livro de Entrada detalhado.
    # Não entra em nenhum cálculo de ICMS/FECP/013 existente.
    linhas_entrada = _extrair_cfops_entrada(p1)
    log(f"   {len(linhas_entrada)} CFOPs de entrada encontrados (informativo).")

    icms_013  = _extrair_013(p2)
    guias_nbs = _extrair_guias_nbs(p2)
    fecp_nbs  = guias_nbs.get("7501", 0.0)
    icms_guia = guias_nbs.get("0213", 0.0)
    log(f"   Campo 013 (NBS): R$ {icms_013:,.2f}")
    if icms_guia: log(f"   Guia ICMS 0213:  R$ {icms_guia:,.2f}")
    if fecp_nbs:  log(f"   Guia FECP 7501:  R$ {fecp_nbs:,.2f}")

    fecp_base  = sum(l.imp_debitado for l in linhas)
    col4_total = sum(l.icms_proprio  for l in linhas)
    fecp       = fecp_base * ALIQUOTA_FECP

    # Detecta quais créditos foram aplicados pelo NBS (aparecem na seção crédito pág.2)
    creditos_aplicados, creditos_nao_aplicados = _detectar_creditos(p2, linhas)
    total_aplic  = sum(creditos_aplicados.values())
    total_nao    = sum(creditos_nao_aplicados.values())

    # Status do NBS
    fecp_ja_calculado = fecp_nbs > 0
    obs = []

    # Loga status dos créditos
    for cfop, val in creditos_aplicados.items():
        log(f"   ✅ NBS já aplicou crédito {cfop} ({CFOPS_CREDITO[cfop]}): R$ {val:,.2f}")
        obs.append(f"NBS já aplicou crédito CFOP {cfop}: R$ {val:,.2f}")
    for cfop, val in creditos_nao_aplicados.items():
        log(f"   ⚠️  NBS NÃO aplicou crédito {cfop} ({CFOPS_CREDITO[cfop]}): R$ {val:,.2f} → ajustando")
        obs.append(f"Ajuste: crédito CFOP {cfop} aplicado manualmente: R$ {val:,.2f}")

    if not creditos_aplicados and not creditos_nao_aplicados:
        log("   ℹ️  Nenhum CFOP de crédito especial neste período.")

    if fecp_ja_calculado:
        log(f"   ✅ NBS já calculou FECP: R$ {fecp_nbs:,.2f}")
        obs.append(f"NBS já calculou FECP: R$ {fecp_nbs:,.2f}")
    else:
        log(f"   ⚠️  NBS NÃO calculou FECP → calculando: R$ {fecp:,.2f}")
        obs.append(f"FECP calculado manualmente (base R$ {fecp_base:,.2f} × 2%): R$ {fecp:,.2f}")

    # Fórmula unificada:
    # ICMS = 013 + credits_applied - credits_not_yet - FECP
    icms_a_pagar = max(0.0, icms_013 + total_aplic - total_nao - fecp)
    fecp_a_pagar = fecp

    # Verifica se o NBS já estava correto
    tudo_ok = (len(creditos_nao_aplicados) == 0 and fecp_ja_calculado)

    log(f"\n{'─'*52}")
    if tudo_ok:
        log("  ✅ NBS já calculou corretamente — sem ajustes necessários.", )
    else:
        log("  ⚙️  Ajustes aplicados:")
    log(f"  Base FECP (imp.debitado):   R$ {fecp_base:>12,.2f}")
    log(f"  FECP (2%):                  R$ {fecp:>12,.2f}")
    log(f"  ICMS campo 013 (NBS):       R$ {icms_013:>12,.2f}")
    if creditos_aplicados:
        log(f"  (+) Créditos já aplicados:  R$ {total_aplic:>12,.2f}")
    if creditos_nao_aplicados:
        log(f"  (-) Créditos ajustados:     R$ {total_nao:>12,.2f}")
    log(f"  (-) FECP:                   R$ {fecp:>12,.2f}")
    log(f"  {'─'*52}")
    log(f"  ✅ ICMS A PAGAR:            R$ {icms_a_pagar:>12,.2f}")
    log(f"  ✅ FECP A PAGAR:            R$ {fecp_a_pagar:>12,.2f}")

    # Verificação final: se NBS tem guias, compara com nosso cálculo
    if icms_guia and fecp_nbs:
        diff_icms = abs(icms_guia - icms_a_pagar)
        diff_fecp = abs(fecp_nbs  - fecp_a_pagar)
        if diff_icms < 0.10 and diff_fecp < 0.10:
            log("   ✅ Guias NBS conferem com o cálculo.")
        else:
            log(f"   ⚠️  Divergência: guia ICMS={icms_guia:,.2f} calc={icms_a_pagar:,.2f} "
                f"| guia FECP={fecp_nbs:,.2f} calc={fecp_a_pagar:,.2f}")

    return ApuracaoICMS(
        empresa=empresa, cnpj=cnpj, insc_est=insc_est, periodo=periodo,
        linhas=linhas, linhas_entrada=linhas_entrada,
        fecp_base=fecp_base, col4_total=col4_total,
        icms_013=icms_013,
        credits_applied=creditos_aplicados, credits_not_yet=creditos_nao_aplicados,
        total_applied=total_aplic, total_not_yet=total_nao,
        fecp=fecp, fecp_no_nbs=fecp_ja_calculado,
        icms_guia_nbs=icms_guia, fecp_guia_nbs=fecp_nbs,
        icms_a_pagar=icms_a_pagar, fecp_a_pagar=fecp_a_pagar,
        tudo_correto_nbs=tudo_ok, observacoes=obs,
    )


# ═══════════════════════════════════════════════════════════════
# PARSERS
# ═══════════════════════════════════════════════════════════════

def _extrair_cabecalho(texto):
    empresa = re.search(r"Firma[:\s]+([^\n]+)", texto)
    cnpj    = re.search(r"CNPJ\s*\(MF\)[:\s]+([\d./-]+)", texto)
    insc    = re.search(r"Insc\.\s*Est\.\s*[:\s]+(\d+)", texto)
    per     = re.search(r"Per[íi]odo[:\s]+([\d/]+)\s*[-–]\s*([\d/]+)", texto)
    return (
        empresa.group(1).strip() if empresa else "",
        cnpj.group(1).strip()    if cnpj    else "",
        insc.group(1).strip()    if insc    else "",
        f"{per.group(1)} a {per.group(2)}" if per else "",
    )


def _extrair_cfops_saida(texto) -> List[LinhaCFOP]:
    """Extrai CFOPs de SAIDAS — para antes das linhas de Subtotais."""
    linhas = []
    idx = max(texto.find("SAIDAS"), texto.find("SAÍDAS"))
    if idx < 0:
        return linhas

    trecho = texto[idx:]
    fim = trecho.find("Subtotais")
    if fim > 0:
        trecho = trecho[:fim]

    padrao = re.compile(
        r"^([567]\d{3})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})",
        re.MULTILINE
    )
    for m in padrao.finditer(trecho):
        linhas.append(LinhaCFOP(
            cfop         = m.group(1),
            descricao    = CFOPS_CREDITO.get(m.group(1), ""),
            base_total   = _p(m.group(2)),
            imp_debitado = _p(m.group(3)),
            icms_proprio = _p(m.group(4)),
            op_debito    = _p(m.group(5)),
            outros       = _p(m.group(6)),
        ))
    return linhas


def _extrair_cfops_entrada(texto) -> List[LinhaCFOP]:
    """
    Extrai CFOPs de ENTRADAS do Livro Fiscal (apuração) — espelha
    _extrair_cfops_saida (mesmo formato de 5 colunas numéricas após o
    código), só muda a seção procurada (ENTRADAS em vez de SAIDAS) e a
    faixa de código (1xxx/2xxx/3xxx em vez de 5xxx/6xxx/7xxx).

    Aditivo — usado apenas para comparação com o livro próprio, não
    participa da fórmula de ICMS/FECP/013.
    """
    linhas = []
    idx = texto.find("ENTRADAS")
    if idx < 0:
        return linhas

    trecho = texto[idx:]
    fim = trecho.find("Subtotais")
    if fim > 0:
        trecho = trecho[:fim]

    padrao = re.compile(
        r"^([123]\d{3})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})\s+"
        r"([\d.]+,\d{2})",
        re.MULTILINE
    )
    for m in padrao.finditer(trecho):
        linhas.append(LinhaCFOP(
            cfop         = m.group(1),
            descricao    = "",
            base_total   = _p(m.group(2)),
            imp_debitado = _p(m.group(3)),
            icms_proprio = _p(m.group(4)),
            op_debito    = _p(m.group(5)),
            outros       = _p(m.group(6)),
        ))
    return linhas


def _extrair_013(texto_p2) -> float:
    """Extrai campo 013 — Imposto a Recolher."""
    # Padrão direto do NBS: "013 - Imposto a Recolher 12.838,20"
    m = re.search(
        r"013\s*[-–]\s*Imposto\s+a\s+Recolher\s+([\d.]+,\d{2})",
        texto_p2, re.IGNORECASE
    )
    if m: return _p(m.group(1))
    # Fallback genérico
    m = re.search(
        r"013[^\d]+([\d.]+,\d{2})",
        texto_p2, re.IGNORECASE
    )
    if m: return _p(m.group(1))
    return 0.0


def _extrair_guias_nbs(texto_p2) -> dict:
    """
    Extrai guias de recolhimento já presentes no livro do NBS.
    Códigos de receita:
      0213 = ICMS
      7501 = FECP
    Formato no PDF: 'CÓDIGO DD/MM/AAAA VALOR' ou 'CÓDIGO VALOR'
    """
    guias = {}
    for codigo in ["0213", "7501"]:
        # Formato com data: CÓDIGO DD/MM/AAAA VALOR
        m = re.search(
            codigo + r"\s+\d{2}/\d{2}/\d{4}\s+([\d.]+,\d{2})",
            texto_p2
        )
        if m:
            guias[codigo] = _p(m.group(1))
            continue
        # Formato sem data: CÓDIGO VALOR
        m = re.search(codigo + r"\s+([\d.]+,\d{2})", texto_p2)
        if m:
            guias[codigo] = _p(m.group(1))
    return guias


def _extrair_fecp_nbs(texto_p2) -> float:
    """Retorna valor do FECP já calculado pelo NBS (guia 7501), ou 0."""
    return _extrair_guias_nbs(texto_p2).get("7501", 0.0)


def _detectar_creditos(
    texto_p2: str,
    linhas: List[LinhaCFOP]
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Separa créditos em dois grupos:
      - credits_applied: CFOPs especiais que aparecem na seção crédito da pág.2
        (NBS já os aplicou no 013 — precisamos SOMAR de volta para usar a fórmula)
      - credits_not_yet: CFOPs especiais que NÃO aparecem na pág.2
        (NBS não aplicou — precisamos SUBTRAIR do 013)
    """
    aplicados  = {}
    nao_aplic  = {}
    for l in linhas:
        if l.cfop not in CFOPS_CREDITO or l.icms_proprio == 0:
            continue
        if re.search(l.cfop, texto_p2):
            aplicados[l.cfop] = l.icms_proprio
        else:
            nao_aplic[l.cfop] = l.icms_proprio
    return aplicados, nao_aplic


def _p(s: str) -> float:
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return abs(float(s))
    except ValueError:
        return 0.0