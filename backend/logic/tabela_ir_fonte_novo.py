"""
tabela_ir_fonte_novo.py — Carrega a tabela de IRRF por código de serviço
(700+ códigos, base: Relacao_Codigos_Servico_x_IR_Fonte.csv) e combina com
a TABELA_LC116 antiga (já revisada pela Riozen) para o julgamento de PCC
(PIS/COFINS/CSLL).

Regime usado: IRRF 1,5% (art. 647 RIR/1999) ou 1% (art. 649, limpeza/
vigilância/mão de obra) — o padrão real que a Riozen aplica, NÃO o regime
combinado da IN 1234/2012 (que é para órgãos públicos).
"""
import os
import csv

_PASTA = os.path.dirname(os.path.abspath(__file__))
_CSV_IR_FONTE = os.path.join(_PASTA, "Relacao_Codigos_Servico_x_IR_Fonte.csv")

_cache_ir_fonte = None


def _parse_aliquota(texto: str):
    """Converte '1,50%' -> 1.5 ; 'Isento' -> 0.0 (isento) ; '' ou 'Auto-recolhimento' -> None (não identificado/não retido)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if "isento" in texto.lower():
        return 0.0
    if "auto-recolhimento" in texto.lower() or "auto recolhimento" in texto.lower():
        return None  # não retido pelo tomador — tratado à parte
    texto = texto.replace("%", "").replace(",", ".").strip()
    try:
        return float(texto)
    except ValueError:
        return None


def carregar_ir_fonte() -> dict:
    """Lê o CSV (separado por ';', padrão Excel-BR) e retorna dict:
    codigo (ex: '01.01.01') -> dict com aliquota/categoria/base_legal/status."""
    global _cache_ir_fonte
    if _cache_ir_fonte is not None:
        return _cache_ir_fonte

    tabela = {}
    if not os.path.exists(_CSV_IR_FONTE):
        print(f"AVISO: {_CSV_IR_FONTE} não encontrado — IRRF não será verificado pelos códigos novos.")
        _cache_ir_fonte = {}
        return _cache_ir_fonte

    conteudo = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(_CSV_IR_FONTE, "r", encoding=enc) as f:
                conteudo = f.readlines()
            break
        except UnicodeDecodeError:
            continue

    if conteudo is None:
        print(f"AVISO: não consegui ler {_CSV_IR_FONTE} com nenhuma codificação testada.")
        _cache_ir_fonte = {}
        return _cache_ir_fonte

    leitor = csv.reader(conteudo, delimiter=";")
    for i, linha in enumerate(leitor):
        if i == 0:
            continue
        if len(linha) < 4:
            continue
        codigo = linha[0].strip()
        if not codigo:
            continue
        descricao = linha[1].strip() if len(linha) > 1 else ""
        categoria = linha[2].strip() if len(linha) > 2 else ""
        aliquota_txt = linha[3].strip() if len(linha) > 3 else ""
        base_legal = linha[4].strip() if len(linha) > 4 else ""
        status = linha[5].strip() if len(linha) > 5 else ""
        tabela[codigo] = {
            "descricao": descricao,
            "categoria": categoria,
            "irrf_aliq": _parse_aliquota(aliquota_txt),
            "auto_recolhimento": "auto-recolhimento" in aliquota_txt.lower(),
            "base_legal": base_legal,
            "identificado": status.strip().upper() == "SIM" or "isento" in aliquota_txt.lower(),
        }

    _cache_ir_fonte = tabela
    return tabela


def _normalizar_codigo(codigo_bruto: str) -> str:
    """Converte '170601' (6 dígitos, formato cTribNac da API) para '17.06.01' (formato desta tabela)."""
    codigo_bruto = str(codigo_bruto or "").strip()
    apenas_digitos = "".join(c for c in codigo_bruto if c.isdigit())
    if len(apenas_digitos) == 6:
        return f"{apenas_digitos[0:2]}.{apenas_digitos[2:4]}.{apenas_digitos[4:6]}"
    return codigo_bruto  # já pode vir no formato certo, ou ser um código desconhecido


def consultar_irrf(codigo_servico: str) -> dict:
    """Retorna {'aliquota': float ou None, 'status': str, 'base_legal': str} para o código informado."""
    tabela = carregar_ir_fonte()
    codigo_norm = _normalizar_codigo(codigo_servico)
    info = tabela.get(codigo_norm)
    if not info:
        return {"aliquota": None, "status": "CODIGO_NAO_ENCONTRADO_NA_TABELA_IR", "base_legal": "", "codigo_normalizado": codigo_norm}

    if info["auto_recolhimento"]:
        status = "AUTO_RECOLHIMENTO"
    elif info["irrf_aliq"] == 0.0:
        status = "ISENTO"
    elif not info["identificado"]:
        status = "NAO_IDENTIFICADO"
    else:
        status = "RETIDO"

    return {
        "aliquota": info["irrf_aliq"],
        "status": status,
        "base_legal": info["base_legal"],
        "categoria": info["categoria"],
        "codigo_normalizado": codigo_norm,
    }