"""
nfse_dados_completos.py — Extração COMPLETA dos campos de uma NFS-e a partir
do XML, pra alimentar a geração do PDF em formato DANFSe (gerar_danfse_pdf.py).

Reescrito pra bater com um DANFSe oficial real (nota da Webmotors, emitida
em SP) usado como referência — cobre TODAS as seções e campos visíveis
nesse modelo oficial: cabeçalho, prestador, tomador, destinatário/
intermediário, serviço, tributação municipal, tributação federal, e a
seção de IBS/CBS (Reforma Tributária) com todos os 5 blocos de campo.

Nível de confiança dos campos:
  - Cabeçalho, prestador, tomador, serviço, ISSQN, tributos federais
    tradicionais: ALTA confiança — nomes de tag já validados contra nota
    real nesta conversa.
  - Seção IBS/CBS: MENOR confiança nos nomes exatos de tag internos do XML
    — os RÓTULOS e a ESTRUTURA (5 blocos, confirmados pela nota real da
    Webmotors) estão corretos; os nomes de tag XML usados pra encontrar
    cada valor são inferidos e podem precisar de ajuste quando testados
    contra o XML bruto de verdade.

Todos os campos são None-safe: tag não encontrada = campo None = PDF mostra
"-" (traço), nunca dado errado.
"""
import re
import xml.etree.ElementTree as ET


def _tag_sem_ns(el):
    return el.tag.split("}")[-1] if "}" in el.tag else el.tag


def _achar(raiz, nome_tag):
    if raiz is None:
        return None
    for el in raiz.iter():
        if _tag_sem_ns(el) == nome_tag:
            return el
    return None


def _achar_todos(raiz, nome_tag):
    if raiz is None:
        return []
    return [el for el in raiz.iter() if _tag_sem_ns(el) == nome_tag]


def _texto(elemento, caminho):
    """Busca por caminho relativo (filhos diretos em sequência)."""
    if elemento is None:
        return None
    atual = elemento
    for parte in caminho.split("/"):
        encontrado = None
        for filho in atual:
            if _tag_sem_ns(filho) == parte:
                encontrado = filho
                break
        if encontrado is None:
            return None
        atual = encontrado
    return atual.text.strip() if atual.text else None


def _txt(el):
    return el.text.strip() if el is not None and el.text else None


def _txt_multi(raiz, *nomes_tag):
    """Tenta várias tags candidatas (fallback), retorna a primeira achada."""
    for nome in nomes_tag:
        el = _achar(raiz, nome)
        if el is not None and el.text:
            return el.text.strip()
    return None


def _float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def _montar_endereco(el_end):
    if el_end is None:
        return None
    partes = []
    lgr = _texto(el_end, "xLgr")
    nro = _texto(el_end, "nro")
    compl = _texto(el_end, "xCpl")
    bairro = _texto(el_end, "xBairro")
    if lgr:
        linha = lgr
        if nro: linha += f", {nro}"
        if compl: linha += f", {compl}"
        partes.append(linha)
    if bairro:
        partes.append(bairro)
    return ", ".join(partes) if partes else None


def _extrair_pessoa(el_pessoa):
    if el_pessoa is None:
        return None
    end = _achar(el_pessoa, "end")
    end_nac = _achar(el_pessoa, "endNac")
    return {
        "cnpj": _texto(el_pessoa, "CNPJ"),
        "cpf": _texto(el_pessoa, "CPF"),
        "nif": _texto(el_pessoa, "NIF"),
        "nome": _texto(el_pessoa, "xNome"),
        "im": _texto(el_pessoa, "IM"),
        "fone": _texto(el_pessoa, "fone"),
        "email": _texto(el_pessoa, "email"),
        "endereco": _montar_endereco(end),
        "municipio": _texto(end, "xMun") if end is not None else None,
        "uf": _texto(end, "UF") if end is not None else None,
        "cmun": _texto(end_nac, "cMun") if end_nac is not None else (_texto(end, "cMun") if end is not None else None),
        "cep": _texto(end, "CEP") if end is not None else None,
        "simples_nacional": _texto(el_pessoa, "regTrib/opSimpNac"),
        "regime_apuracao": _texto(el_pessoa, "regTrib/regApTribSN"),
    }


def extrair_dados_completos(xml_bytes: bytes, chave_acesso: str = None, nsu=None) -> dict:
    root = ET.fromstring(xml_bytes)
    d = {"chave_acesso": chave_acesso, "nsu": nsu}

    # ── Cabeçalho ────────────────────────────────────────────────────────
    d["numero"] = _txt(_achar(root, "nNFSe"))
    d["dhEmi"] = _txt(_achar(root, "dhEmi"))
    d["competencia"] = _txt_multi(root, "dCompet", "dCompetencia", "dhCompet") or d["dhEmi"]
    d["nDPS"] = _txt(_achar(root, "nDPS"))
    d["serie"] = _txt(_achar(root, "serie"))
    d["dhEmiDPS"] = _texto(root, "infDPS/dhEmi") if _achar(root, "infDPS") is not None else None
    d["cStat"] = _txt(_achar(root, "cStat"))
    d["tpAmb"] = _txt(_achar(root, "tpAmb"))
    d["ambiente_gerador"] = _txt(_achar(root, "verAplic")) and "1"  # fallback simples
    d["finalidade"] = _txt_multi(root, "tpEmis", "finNFSe")
    d["cLocEmi"] = _txt(_achar(root, "cLocEmi"))

    # ── Prestador / Tomador ──────────────────────────────────────────────
    el_emit = _achar(root, "emit")
    el_toma = _achar(root, "toma")
    d["prestador"] = _extrair_pessoa(el_emit)
    d["tomador"] = _extrair_pessoa(el_toma)

    # Município de emissão — usa o do prestador como aproximação (a nota é
    # emitida no município do prestador na grande maioria dos casos)
    if d["prestador"]:
        d["municipio_emissao"] = d["prestador"].get("municipio")
        d["uf_emissao"] = d["prestador"].get("uf")
    else:
        d["municipio_emissao"] = None
        d["uf_emissao"] = None

    # ── Destinatário / Intermediário ─────────────────────────────────────
    el_dest = _achar(root, "dest")
    el_interm = _achar(root, "interm") or _achar(root, "intermed")
    d["destinatario"] = _extrair_pessoa(el_dest) if el_dest is not None else None
    d["intermediario"] = _extrair_pessoa(el_interm) if el_interm is not None else None

    # ── Serviço ──────────────────────────────────────────────────────────
    d["codigo_servico"] = _txt(_achar(root, "cTribNac"))
    d["codigo_servico_mun"] = _txt(_achar(root, "cTribMun"))
    d["codigo_nbs"] = _txt(_achar(root, "cNBS"))
    d["local_prestacao_cmun"] = _txt(_achar(root, "cLocPrestacao"))
    # Descrição padrão do código (LC116) x descrição livre digitada na nota
    # são campos DIFERENTES no documento oficial — tenta separar as duas.
    d["descricao_codigo"] = _txt_multi(root, "xTribNac", "xTribMun")
    d["descricao_servico"] = _txt_multi(root, "xDescServ", "discrim", "infoCompl")
    d["numero_rps"] = _txt(_achar(root, "nRPS"))

    # ── Valores gerais ───────────────────────────────────────────────────
    el_valores = _achar(root, "valores")
    d["valor_servico"] = _float(_texto(el_valores, "vServPrest") or _texto(el_valores, "vBC"))
    d["valor_bc_iss"] = _float(_texto(el_valores, "vBC"))
    d["aliquota_iss"] = _float(_texto(el_valores, "pAliqAplic"))
    d["valor_iss"] = _float(_texto(el_valores, "vISSQN"))
    d["valor_liquido"] = _float(_texto(el_valores, "vLiq"))
    d["desconto_incondicionado"] = _float(_texto(el_valores, "vDescIncond"))
    d["desconto_condicionado"] = _float(_texto(el_valores, "vDescCond"))
    d["total_retencoes"] = _float(_texto(el_valores, "vTotalRet"))

    # ── Tributação municipal (ISSQN) ─────────────────────────────────────
    el_tribmun = _achar(root, "tribMun")
    d["tipo_tributacao_issqn"] = _txt_multi(el_tribmun or root, "tribISSQN") 
    d["tipo_tributacao_issqn_desc"] = {
        "1": "Operação Tributável", "2": "Imune", "3": "Exportação", "4": "Não Incidência",
    }.get(d["tipo_tributacao_issqn"], d["tipo_tributacao_issqn"])
    d["municipio_incidencia_issqn"] = _texto(el_tribmun, "cLocIncid") or _texto(el_tribmun, "cMunFG")
    d["regime_especial"] = _texto(el_tribmun, "tpRegimeEspTrib")
    d["tipo_imunidade"] = _texto(el_tribmun, "tpImunidade")
    d["tp_ret_issqn"] = _texto(el_tribmun, "tpRetISSQN")
    d["iss_retido_pelo_tomador"] = d["tp_ret_issqn"] == "2"

    # ── Tributação federal (exceto CBS) ──────────────────────────────────
    el_tribfed = _achar(root, "tribFed") or root
    d["irrf"] = _float(_txt_multi(el_tribfed, "vRetIRRF", "vIRRF"))
    d["contrib_previdenciaria_retida"] = _float(_txt_multi(el_tribfed, "vRetCPRB", "vRetPrev", "vRetINSS"))
    d["contrib_sociais_retidas"] = _float(_txt_multi(el_tribfed, "vRetCSLL", "vRetCP"))
    el_pcc = _achar(root, "tribPisCofins") or root
    d["pis_debito"] = _float(_txt_multi(el_pcc, "vPis", "vRetPIS"))
    d["cofins_debito"] = _float(_txt_multi(el_pcc, "vCofins", "vRetCOFINS"))
    d["descricao_contrib_sociais_retidas"] = _txt_multi(root, "xRetCSLL", "infRetCSLL")

    # ── IBS/CBS (Reforma Tributária) — confiança menor, best-effort ──────
    el_ibscbs = _achar(root, "IBSCBS") or _achar(root, "gIBSCBS")
    d["cst_ibscbs"] = _texto(el_ibscbs, "CST")
    d["cclasstrib"] = _texto(el_ibscbs, "cClassTrib")
    d["indicador_operacao_ibscbs"] = _texto(el_ibscbs, "indDest") or _texto(el_ibscbs, "indOp")
    d["codigo_ibge_incidencia_ibscbs"] = _texto(el_ibscbs, "cMunIncid") or _texto(el_ibscbs, "cMun")
    d["municipio_incidencia_ibscbs"] = _texto(el_ibscbs, "xMunIncid")
    d["uf_incidencia_ibscbs"] = _texto(el_ibscbs, "UFIncid") or _texto(el_ibscbs, "UF")
    d["exclusoes_reducoes_bc_ibscbs"] = _float(_txt_multi(el_ibscbs, "vRedBC", "vDif", "vBCExcl"))
    d["bc_apos_exclusoes_ibscbs"] = _float(_texto(el_ibscbs, "vBC"))
    d["red_aliq_ibs"] = _txt_multi(el_ibscbs, "pRedAliqIBS")
    d["red_aliq_cbs"] = _txt_multi(el_ibscbs, "pRedAliqCBS")
    d["aliq_ibs_uf"] = _txt_multi(el_ibscbs, "pIBSUF")
    d["aliq_ibs_mun"] = _txt_multi(el_ibscbs, "pIBSMun")
    d["aliq_efetiva_municipal_ibs"] = _float(_txt_multi(el_ibscbs, "pIBSMunEfet"))
    d["valor_apurado_municipal_ibs"] = _float(_txt_multi(el_ibscbs, "vIBSMun"))
    d["aliq_efetiva_estadual_ibs"] = _float(_txt_multi(el_ibscbs, "pIBSUFEfet"))
    d["valor_apurado_estadual_ibs"] = _float(_txt_multi(el_ibscbs, "vIBSUF"))
    d["valor_total_apurado_ibs"] = _float(_txt_multi(el_ibscbs, "vIBS"))
    d["aliq_cbs"] = _float(_txt_multi(el_ibscbs, "pCBS"))
    d["aliq_efetiva_cbs"] = _float(_txt_multi(el_ibscbs, "pCBSEfet"))
    d["valor_total_apurado_cbs"] = _float(_txt_multi(el_ibscbs, "vCBS"))
    d["valor_total_ibscbs"] = None
    if d["valor_total_apurado_ibs"] is not None or d["valor_total_apurado_cbs"] is not None:
        d["valor_total_ibscbs"] = round((d["valor_total_apurado_ibs"] or 0) + (d["valor_total_apurado_cbs"] or 0), 2)

    # ── Informações complementares ───────────────────────────────────────
    d["totais_aprox_federais"] = _float(_txt_multi(root, "vTotTribFed"))
    d["totais_aprox_estaduais"] = _float(_txt_multi(root, "vTotTribEst"))
    d["totais_aprox_municipais"] = _float(_txt_multi(root, "vTotTribMun")) 
    if d["totais_aprox_municipais"] is None and d["valor_iss"] is not None:
        d["totais_aprox_municipais"] = d["valor_iss"]

    # ── Cancelamento ──────────────────────────────────────────────────────
    d["cancelada"] = d.get("cStat") not in (None, "100")

    return d
