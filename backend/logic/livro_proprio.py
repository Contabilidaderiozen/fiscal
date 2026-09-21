"""
livro_proprio.py — Livro próprio de ICMS (crédito/débito) montado a
partir dos Livros de Entrada e Saída detalhados, nota a nota.
=============================================================================
Objetivo: em vez de confiar apenas no resumo consolidado que o NBS gera
(Livro Fiscal / Registro de Apuração), este módulo lê cada nota individual
dos Livros de Entrada (crédito) e Saída (débito), reconstrói os totais por
código de natureza/CFOP de forma independente, e compara com os totais
oficiais do Livro Fiscal (que já são extraídos por icms_apuracao.py).

Não mexe em nada de icms_apuracao.py — apenas consome o resultado dele
(res.linhas e res.linhas_entrada) para a comparação final.

Formato das colunas validado contra PDFs reais da MR RIO AUTOMÓVEIS
(período 08/2026):
  Entrada: Data Espécie Série Número DataDocumento Emitente UF Valor
           Código+ICMS Grupo(1/2/3) Creditado [A=.../C=.../D=... opcional]
  Saída:   Espécie Série Número Dia UF Valor Código+ICMS <numéricos extras>
           [CFOP x.xxx | GARANTIA | NFS-e: nnnn]
"""

import re
import pdfplumber
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class NotaFiscal:
    tipo:        str            # "entrada" ou "saida"
    especie:     str            # "NF-e" ou "NFS"
    serie:       str
    numero:      str
    data:        str            # dd/mm/aaaa quando disponível (entrada) ou dd (saída, sem mês)
    uf:          str
    valor:       float
    codigo:      str            # CFOP / código de natureza (4 dígitos)
    cancelada:   bool = False
    emitente:    str = ""       # só entrada (CNPJ/CPF)
    nfse_numero: str = ""       # só saída, quando linha é NFS
    observacao:  str = ""       # GARANTIA, "CFOP 5.949" etc.


@dataclass
class RelatorioLivroProprio:
    notas_entrada:      List[NotaFiscal] = field(default_factory=list)
    notas_saida:        List[NotaFiscal] = field(default_factory=list)
    totais_entrada:     Dict[str, float] = field(default_factory=dict)   # por código
    totais_saida:       Dict[str, float] = field(default_factory=dict)
    qtd_entrada:        Dict[str, int]   = field(default_factory=dict)
    qtd_saida:          Dict[str, int]   = field(default_factory=dict)
    anomalias:          List[str] = field(default_factory=list)
    comparacao_entrada: List[dict] = field(default_factory=list)   # [{codigo, nosso, nbs, diff, status}]
    comparacao_saida:   List[dict] = field(default_factory=list)
    divergente:         bool = False


# ═══════════════════════════════════════════════════════════════
# EXTRAÇÃO — LIVRO DE ENTRADA
# ═══════════════════════════════════════════════════════════════

_PADRAO_ENTRADA_NORMAL = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(NF-e|NFS|NF)\s+(\S+)\s+(\S+)\s+(\d{2}/\d{2}/\d{2})\s+"
    r"(\d+)\s+([A-Z]{2})\s+([\d.]+,\d{2})\s+(\d{4})ICMS\s+(\d)\s+([\d.]+,\d{2})",
    re.MULTILINE,
)
_PADRAO_ENTRADA_CANCEL = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(NF-e|NFS|NF)\s+(\S+)\s+(\S+)\s+(\d{2}/\d{2}/\d{2})\s+"
    r"(\d+)\s+([\d.]+,\d{2})\s+Cancelada",
    re.MULTILINE,
)


def extrair_notas_entrada(caminho_pdf: str, callback_log=None) -> List[NotaFiscal]:
    def log(msg):
        if callback_log:
            callback_log(msg)

    log("📥 Lendo Livro de Entrada...")
    with pdfplumber.open(caminho_pdf) as pdf:
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)

    notas: List[NotaFiscal] = []
    for m in _PADRAO_ENTRADA_NORMAL.finditer(texto):
        notas.append(NotaFiscal(
            tipo="entrada", especie=m.group(2), serie=m.group(3), numero=m.group(4),
            data=m.group(1), emitente=m.group(6), uf=m.group(7),
            valor=_p(m.group(8)), codigo=m.group(9), cancelada=False,
        ))
    for m in _PADRAO_ENTRADA_CANCEL.finditer(texto):
        notas.append(NotaFiscal(
            tipo="entrada", especie=m.group(2), serie=m.group(3), numero=m.group(4),
            data=m.group(1), emitente=m.group(6), uf="", valor=0.0,
            codigo="", cancelada=True,
        ))
    log(f"   {len(notas)} notas de entrada extraídas.")
    return notas


# ═══════════════════════════════════════════════════════════════
# EXTRAÇÃO — LIVRO DE SAÍDA
# ═══════════════════════════════════════════════════════════════

_PADRAO_SAIDA_NORMAL = re.compile(
    r"^(NF-e|NFS|NF)\s+(\S+)\s+(\d+)\s+(\d{2})\s+([A-Z]{2})\s+([\d.]+,\d{2})\s+(\d{4})ICMS\s+"
    r"[\d.,\s]+?(?:\s+(CFOP\s[\d.]+|GARANTIA|NFS-e:\s*\d+))?$",
    re.MULTILINE,
)
_PADRAO_SAIDA_CANCEL = re.compile(
    r"^(NF-e|NFS|NF)\s+(\S+)\s+(\d+)\s+(\d{2})\s+([A-Z]{2})\s+ICMS\s+Cancelada",
    re.MULTILINE,
)


def extrair_notas_saida(caminho_pdf: str, callback_log=None) -> List[NotaFiscal]:
    def log(msg):
        if callback_log:
            callback_log(msg)

    log("📤 Lendo Livro de Saída...")
    with pdfplumber.open(caminho_pdf) as pdf:
        texto = "\n".join((p.extract_text() or "") for p in pdf.pages)

    notas: List[NotaFiscal] = []
    for m in _PADRAO_SAIDA_NORMAL.finditer(texto):
        obs = m.group(8) or ""
        nfse_num = ""
        mm = re.match(r"NFS-e:\s*(\d+)", obs)
        if mm:
            nfse_num = mm.group(1)
        notas.append(NotaFiscal(
            tipo="saida", especie=m.group(1), serie=m.group(2), numero=m.group(3),
            data=m.group(4), uf=m.group(5), valor=_p(m.group(6)), codigo=m.group(7),
            cancelada=False, nfse_numero=nfse_num, observacao=obs,
        ))
    for m in _PADRAO_SAIDA_CANCEL.finditer(texto):
        notas.append(NotaFiscal(
            tipo="saida", especie=m.group(1), serie=m.group(2), numero=m.group(3),
            data=m.group(4), uf=m.group(5), valor=0.0, codigo="", cancelada=True,
        ))
    log(f"   {len(notas)} notas de saída extraídas.")
    return notas


# ═══════════════════════════════════════════════════════════════
# MONTAGEM DO LIVRO PRÓPRIO
# ═══════════════════════════════════════════════════════════════

def _agrupar_por_codigo(notas: List[NotaFiscal]):
    totais: Dict[str, float] = {}
    qtd: Dict[str, int] = {}
    for n in notas:
        if n.cancelada or not n.codigo:
            continue
        totais[n.codigo] = totais.get(n.codigo, 0.0) + n.valor
        qtd[n.codigo] = qtd.get(n.codigo, 0) + 1
    return totais, qtd


def detectar_anomalias(notas_entrada: List[NotaFiscal], notas_saida: List[NotaFiscal]) -> List[str]:
    """
    Verificações nota a nota, dentro do próprio livro (não depende do NBS):
      - notas duplicadas (mesma espécie+série+número aparecendo 2x)
      - "cancelada" com valor diferente de zero (não deveria acontecer)
      - valor exatamente R$ 0,00 sem estar marcada como cancelada
        (R$ 0,01 é um padrão normal já observado nesta empresa — não é
        tratado como anomalia)
    """
    avisos: List[str] = []

    for grupo, tipo in [(notas_entrada, "Entrada"), (notas_saida, "Saída")]:
        vistos: Dict[str, List[NotaFiscal]] = {}
        for n in grupo:
            chave = f"{n.especie} {n.serie}-{n.numero}"
            vistos.setdefault(chave, []).append(n)
        for chave, lista in vistos.items():
            if len(lista) > 1:
                avisos.append(
                    f"[{tipo}] Nota duplicada ({chave}): aparece {len(lista)} vezes "
                    f"— valores {[f'R$ {n.valor:,.2f}' for n in lista]}"
                )
        for n in grupo:
            if n.cancelada and n.valor != 0:
                avisos.append(f"[{tipo}] Nota marcada Cancelada mas com valor R$ {n.valor:,.2f} ({n.especie} {n.serie}-{n.numero})")
            if not n.cancelada and n.valor == 0.0:
                avisos.append(f"[{tipo}] Nota com valor R$ 0,00 sem estar marcada Cancelada ({n.especie} {n.serie}-{n.numero}, CFOP {n.codigo})")

    return avisos


def _comparar_totais(nosso: Dict[str, float], oficial_linhas, tolerancia=0.02) -> List[dict]:
    """
    oficial_linhas: lista de LinhaCFOP (de icms_apuracao) — usa l.base_total,
    que corresponde à coluna "Valor" do Livro Fiscal (mesma grandeza que
    somamos nota a nota).
    """
    oficial = {l.cfop: l.base_total for l in oficial_linhas}
    codigos = sorted(set(nosso) | set(oficial))
    linhas = []
    for cod in codigos:
        n = nosso.get(cod, 0.0)
        o = oficial.get(cod, 0.0)
        diff = round(n - o, 2)
        status = "OK" if abs(diff) < tolerancia else "DIVERGENTE"
        linhas.append({"codigo": cod, "nosso": round(n, 2), "nbs": round(o, 2), "diferenca": diff, "status": status})
    return linhas


def montar_e_comparar(
    caminho_entrada: str,
    caminho_saida: str,
    apuracao_nbs,             # resultado de icms_apuracao.apurar_icms(...)
    callback_log=None,
) -> RelatorioLivroProprio:
    def log(msg):
        if callback_log:
            callback_log(msg)

    notas_entrada = extrair_notas_entrada(caminho_entrada, callback_log)
    notas_saida = extrair_notas_saida(caminho_saida, callback_log)

    totais_entrada, qtd_entrada = _agrupar_por_codigo(notas_entrada)
    totais_saida, qtd_saida = _agrupar_por_codigo(notas_saida)

    log("🔍 Verificando anomalias (duplicidade, cancelamento, valor zerado)...")
    anomalias = detectar_anomalias(notas_entrada, notas_saida)
    if anomalias:
        for a in anomalias:
            log(f"   ⚠️  {a}")
    else:
        log("   ✅ Nenhuma anomalia encontrada nas notas.")

    log("⚖️  Comparando livro próprio × Livro Fiscal (NBS)...")
    comp_entrada = _comparar_totais(totais_entrada, apuracao_nbs.linhas_entrada)
    comp_saida = _comparar_totais(totais_saida, apuracao_nbs.linhas)

    divergente = any(l["status"] == "DIVERGENTE" for l in comp_entrada + comp_saida)
    if divergente:
        log("   ⚠️  Encontrada(s) divergência(s) entre o livro próprio e o Livro Fiscal:")
        for l in comp_entrada + comp_saida:
            if l["status"] == "DIVERGENTE":
                log(f"      CFOP {l['codigo']}: nosso R$ {l['nosso']:,.2f} × NBS R$ {l['nbs']:,.2f} "
                    f"(diferença R$ {l['diferenca']:,.2f})")
    else:
        log("   ✅ Livro próprio bate 100% com o Livro Fiscal do NBS, código por código.")

    return RelatorioLivroProprio(
        notas_entrada=notas_entrada, notas_saida=notas_saida,
        totais_entrada=totais_entrada, totais_saida=totais_saida,
        qtd_entrada=qtd_entrada, qtd_saida=qtd_saida,
        anomalias=anomalias,
        comparacao_entrada=comp_entrada, comparacao_saida=comp_saida,
        divergente=divergente,
    )


# ═══════════════════════════════════════════════════════════════
# CRUZAMENTO COM A SEFAZ (resumo por NSU + busca completa sob demanda)
# ═══════════════════════════════════════════════════════════════

def cruzar_com_sefaz(notas_entrada: List[NotaFiscal], notas_saida: List[NotaFiscal],
                      resumos_sefaz: List[dict], nosso_cnpj: str,
                      callback_log=None) -> dict:
    """
    Cruza o que foi extraído do PDF (notas_entrada/notas_saida) contra o
    resumo (resNFe) trazido da SEFAZ via nfe_distribuicao.consultar_resumo_periodo.

    O resumo da SEFAZ NÃO tem CFOP/ICMS (ver aviso em nfe_distribuicao.py)
    — essa função só identifica DIVERGÊNCIAS DE EXISTÊNCIA/VALOR (nota que
    a SEFAZ tem e não está no PDF, nota do PDF que não aparece na SEFAZ,
    valor total batendo ou não). A busca do XML completo (com CFOP/ICMS)
    fica pro chamador decidir, só pras notas que aparecerem aqui como
    divergentes — ver buscar_detalhe_divergentes().
    """
    def log(msg):
        if callback_log:
            callback_log(msg)

    nosso_cnpj = re.sub(r"\D", "", nosso_cnpj or "")

    # Índice do que já temos no PDF: (cnpj_outra_parte, serie, numero) -> NotaFiscal
    # Para Entrada, "outra parte" é o emitente (fornecedor) — já vem no PDF.
    # Para Saída, o PDF não traz CNPJ do destinatário, então indexamos só
    # por (serie, numero), sem CNPJ (a chave da SEFAZ, quando formos nós o
    # emitente, é comparada só por série/número mesmo).
    idx_entrada = {}
    for n in notas_entrada:
        if n.cancelada:
            continue
        chave_idx = (re.sub(r"\D", "", n.emitente or ""), n.serie, n.numero)
        idx_entrada[chave_idx] = n

    idx_saida = {}
    for n in notas_saida:
        if n.cancelada:
            continue
        idx_saida[(n.serie, n.numero)] = n

    divergencias_entrada = []  # notas que a SEFAZ tem (destinatário=nós) e não achamos no PDF, ou valor bate errado
    divergencias_saida = []
    notas_pdf_nao_confirmadas_sefaz = []  # notas do PDF cuja chave não apareceu no resumo da SEFAZ

    chaves_sefaz_vistas = set()

    for r in resumos_sefaz:
        cnpj_emit = r.get("cnpj_emitente") or r.get("chave_cnpj_emitente")
        serie = r.get("chave_serie")
        numero = r.get("chave_numero")
        if not (cnpj_emit and serie and numero):
            continue  # resumo sem chave decodificável — ignora, não dá pra cruzar

        chaves_sefaz_vistas.add((cnpj_emit, serie, numero))
        valor_sefaz = r.get("valor_total")
        cancelada_sefaz = r.get("situacao") not in ("1", None)  # 1 = autorizada

        if cnpj_emit == nosso_cnpj:
            # Nós somos o emitente -> nota de SAÍDA
            nota_pdf = idx_saida.get((serie, numero))
            if nota_pdf is None:
                if not cancelada_sefaz:
                    divergencias_saida.append({
                        "tipo": "FALTANDO_NO_PDF", "chave": r.get("chave"),
                        "serie": serie, "numero": numero, "valor_sefaz": valor_sefaz,
                        "descricao": f"SEFAZ tem NF-e de Saída {serie}-{numero} (R$ {valor_sefaz}) que não achei no Livro de Saída em PDF.",
                    })
            else:
                diff = round((nota_pdf.valor or 0) - (valor_sefaz or 0), 2)
                if abs(diff) > 0.02:
                    divergencias_saida.append({
                        "tipo": "VALOR_DIVERGENTE", "chave": r.get("chave"),
                        "serie": serie, "numero": numero,
                        "valor_pdf": nota_pdf.valor, "valor_sefaz": valor_sefaz, "diferenca": diff,
                        "descricao": f"NF-e Saída {serie}-{numero}: PDF tem R$ {nota_pdf.valor:,.2f}, SEFAZ tem R$ {valor_sefaz:,.2f}.",
                    })
        else:
            # Outra empresa é a emitente, nós somos destinatário -> ENTRADA
            nota_pdf = idx_entrada.get((cnpj_emit, serie, numero))
            if nota_pdf is None:
                if not cancelada_sefaz:
                    divergencias_entrada.append({
                        "tipo": "FALTANDO_NO_PDF", "chave": r.get("chave"),
                        "serie": serie, "numero": numero, "cnpj_emitente": cnpj_emit,
                        "valor_sefaz": valor_sefaz,
                        "descricao": f"SEFAZ tem NF-e de Entrada {serie}-{numero} do fornecedor {cnpj_emit} (R$ {valor_sefaz}) que não achei no Livro de Entrada em PDF.",
                    })
            else:
                diff = round((nota_pdf.valor or 0) - (valor_sefaz or 0), 2)
                if abs(diff) > 0.02:
                    divergencias_entrada.append({
                        "tipo": "VALOR_DIVERGENTE", "chave": r.get("chave"),
                        "serie": serie, "numero": numero, "cnpj_emitente": cnpj_emit,
                        "valor_pdf": nota_pdf.valor, "valor_sefaz": valor_sefaz, "diferenca": diff,
                        "descricao": f"NF-e Entrada {serie}-{numero}: PDF tem R$ {nota_pdf.valor:,.2f}, SEFAZ tem R$ {valor_sefaz:,.2f}.",
                    })

    # Notas do PDF que a SEFAZ nunca mencionou no período consultado —
    # pode ser nota fora da janela de NSU já varrida, ou nota que só existe
    # no nosso lançamento (problema mais sério). Reportado à parte porque
    # tem taxa de falso positivo maior (depende do checkpoint de NSU estar
    # em dia) — não é tratado com o mesmo peso das divergências acima.
    for chave_idx, nota in idx_entrada.items():
        cnpj_emit, serie, numero = chave_idx
        if (cnpj_emit, serie, numero) not in chaves_sefaz_vistas:
            notas_pdf_nao_confirmadas_sefaz.append({
                "tipo": "entrada", "serie": serie, "numero": numero,
                "emitente": cnpj_emit, "valor": nota.valor,
            })
    for (serie, numero), nota in idx_saida.items():
        if not any(s == serie and n == numero for (_, s, n) in chaves_sefaz_vistas):
            notas_pdf_nao_confirmadas_sefaz.append({
                "tipo": "saida", "serie": serie, "numero": numero, "valor": nota.valor,
            })

    log(f"Cruzamento com SEFAZ: {len(divergencias_entrada)} divergência(s) de Entrada, "
        f"{len(divergencias_saida)} de Saída, {len(notas_pdf_nao_confirmadas_sefaz)} nota(s) do PDF "
        f"sem confirmação da SEFAZ no período varrido.")

    return {
        "divergencias_entrada": divergencias_entrada,
        "divergencias_saida": divergencias_saida,
        "notas_pdf_nao_confirmadas_sefaz": notas_pdf_nao_confirmadas_sefaz,
        "total_resumos_sefaz": len(resumos_sefaz),
    }


def buscar_detalhe_divergentes(divergencias_entrada: List[dict], divergencias_saida: List[dict],
                                empresa: str, filial: str, ambiente: str = "producao",
                                limite: int = 30, callback_log=None) -> dict:
    """
    Busca sob demanda (NT 2014.002 consChNFe) o XML completo — com
    CFOP/base/ICMS — SÓ das notas que apareceram divergentes no cruzamento
    acima. Nunca chama isso para todas as notas do período (ver aviso em
    nfe_distribuicao.py sobre risco de bloqueio por uso indevido).

    limite: teto de consultas individuais nesta chamada, por segurança —
    se houver mais divergências que isso, para e avisa (evita martelar a
    SEFAZ por um bug de comparação que gere centenas de "divergências").
    """
    import nfe_distribuicao as nd

    def log(msg):
        if callback_log:
            callback_log(msg)

    todas = [d for d in (divergencias_entrada + divergencias_saida) if d.get("chave")]
    if len(todas) > limite:
        log(f"⚠️  {len(todas)} divergência(s) com chave — acima do limite de {limite} consultas "
            f"individuais por segurança. Buscando detalhe só das primeiras {limite}; "
            f"revise o cruzamento antes de insistir (pode ser bug na comparação, não divergência real).")
        todas = todas[:limite]

    detalhes = {}
    for d in todas:
        chave = d["chave"]
        log(f"Buscando XML completo da nota {d.get('serie')}-{d.get('numero')} (chave {chave})...")
        try:
            resultado = nd.consultar_nfe_completa(empresa, filial, chave, ambiente=ambiente, log=log)
            detalhes[chave] = resultado
        except nd.ErroConsumoIndevido as ex:
            log(f"🛑 {ex} — parando busca de detalhe (não insistir).")
            break
        except Exception as ex:
            log(f"AVISO: erro ao buscar detalhe da nota {chave}: {ex}")
            detalhes[chave] = {"ok": False, "erro": str(ex), "itens": []}

    return detalhes


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
