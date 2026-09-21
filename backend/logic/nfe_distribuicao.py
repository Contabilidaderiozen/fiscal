"""
nfe_distribuicao.py — Integração com o Web Service "NFeDistribuicaoDFe" da
SEFAZ (Ambiente Nacional), especificado na Nota Técnica 2014.002.

⚠️ AVISO IMPORTANTE: diferente do nfse_adn_api.py (testado contra a API real
nesta mesma sessão), este módulo NÃO PÔDE ser testado contra a SEFAZ de
verdade — não há certificado nem rede liberada pra fazenda.gov.br no
ambiente onde isso foi escrito. Tudo que dava pra validar sem rede foi
validado (decodificação de chave de acesso — módulo 11 —, round-trip
gzip+base64 do docZip, parsing de XML). A chamada SOAP em si (envelope,
namespace, cStat de retorno) segue a especificação da NT 2014.002 mas
precisa ser confirmada na primeira execução real. Se dar erro de SOAP
Fault, o mais provável é ajuste de namespace/SOAPAction — isolei isso nas
funções _montar_soap_* e _parse_retorno_soap pra ficar fácil de corrigir
sem mexer no resto.

O QUE ESTE WEBSERVICE ENTREGA (e o que NÃO entrega):
  - Consulta por NSU (distNSU) — modo em lote, de baixo custo, mas só
    devolve resNFe: um RESUMO (chave, CNPJ emitente, valor total da nota,
    data de emissão, situação). NÃO tem CFOP, base de cálculo nem ICMS
    por item.
  - Consulta por chave individual (consChNFe) — devolve o XML completo
    (procNFe), com todos os itens/CFOP/ICMS. Mas é uso pontual: fazer isso
    pra toda nota do mês esbarra nas "Regras de Uso Indevido" da própria
    NT 2014.002 (risco de bloqueio do certificado, cStat 656).

Por isso a estratégia aqui é "busca completa sob demanda": usa o resumo
(barato, em lote) pra mapear todas as notas do período e cruzar contra o
Livro de Entrada/Saída em PDF (livro_proprio.py); só busca o XML completo
das notas que aparecerem divergentes ou faltando.

Endpoint (confirmado no Portal Nacional da NF-e em 03/09/2026):
  Serviço: NFeDistribuicaoDFe, versão 1.00, autorizador Ambiente Nacional
  https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx
  (homologação: trocar www1 por hom1 — não confirmado, seguir padrão dos
  demais serviços do Ambiente Nacional)

Certificado: reaproveita EXATAMENTE o mesmo arquivo de configuração do
NFS-e (certificados/senhas.json, chave "Empresa|Filial") — mesma função
_carregar_config_certificado do nfse_adn_api.py. Se a empresa usar um
certificado diferente pra NF-e do que usa pra NFS-e, isso precisa ser
resolvido no próprio senhas.json (chave separada), não neste módulo.

Checkpoint de NSU: arquivo PRÓPRIO (nsu_checkpoint_nfe.json), separado do
nsu_checkpoint.json do NFS-e — são streams de NSU completamente
independentes (sistemas diferentes: SEFAZ estadual/nacional vs ADN
municipal/SERPRO), misturar os dois quebraria os dois.
"""

import os
import re
import json
import gzip
import base64
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime

try:
    # Import relativo de pacote (logic.nfse_adn_api) — não depende de a
    # pasta logic/ estar, ela mesma, no sys.path (diferente de um bare
    # "import nfse_adn_api", que só funciona se logic/ estiver solta no
    # path — não é garantido no contexto do FastAPI, causava
    # ModuleNotFoundError na primeira chamada real do endpoint).
    from . import nfse_adn_api as _nfse_api
except ImportError:
    # Fallback pra quando este arquivo é importado fora do pacote (ex.:
    # testes locais rodando direto na pasta, sem o backend inteiro).
    import nfse_adn_api as _nfse_api

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
WSDL_NS = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"

URL_PRODUCAO = "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"
URL_HOMOLOGACAO = "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx"

# Código IBGE da UF autorizadora (cUFAutor) — usar o código do estado onde
# a empresa consultante está cadastrada, não o UF do documento consultado.
CODIGO_UF = {
    "RJ": 33, "SP": 35, "MG": 31, "ES": 32, "BA": 29, "PR": 41, "RS": 43,
    "SC": 42, "GO": 52, "MT": 51, "MS": 50, "DF": 53, "PE": 26, "CE": 23,
}

_PASTA_MODULO = os.path.dirname(os.path.abspath(__file__))
_PASTA_CERTIFICADOS = os.path.join(_PASTA_MODULO, "certificados")
_ARQUIVO_CHECKPOINT_NFE = os.path.join(_PASTA_CERTIFICADOS, "nsu_checkpoint_nfe.json")

# cStat que encerram a consulta normalmente (sem erro)
CSTAT_NENHUM_DOCUMENTO = "137"
CSTAT_DOCUMENTOS_LOCALIZADOS = "138"
# cStat que exigem parar e AVISAR — não adianta tentar de novo na hora
CSTAT_CONSUMO_INDEVIDO = "656"
CSTAT_SERVICO_PARALISADO = {"108", "109"}


class ErroConsumoIndevido(RuntimeError):
    """SEFAZ rejeitou por excesso de consultas (cStat 656). Não retentar
    automaticamente — a NT 2014.002 prevê bloqueio temporário do CNPJ
    quando isso acontece."""
    pass


# ── Checkpoint de NSU (arquivo próprio, separado do NFS-e) ──────────────────
def _ler_checkpoint(cnpj: str) -> int:
    if not os.path.exists(_ARQUIVO_CHECKPOINT_NFE):
        return 0
    try:
        with open(_ARQUIVO_CHECKPOINT_NFE, "r", encoding="utf-8") as f:
            return int(json.load(f).get(cnpj, 0))
    except Exception:
        return 0


def _salvar_checkpoint(cnpj: str, nsu: int):
    dados = {}
    if os.path.exists(_ARQUIVO_CHECKPOINT_NFE):
        try:
            with open(_ARQUIVO_CHECKPOINT_NFE, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            dados = {}
    dados[cnpj] = nsu
    os.makedirs(os.path.dirname(_ARQUIVO_CHECKPOINT_NFE), exist_ok=True)
    with open(_ARQUIVO_CHECKPOINT_NFE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)


# ── Decodificação da chave de acesso (44 dígitos, validado localmente) ──────
def decodificar_chave(chave: str) -> dict:
    """Extrai cUF, AAMM, CNPJ emitente, modelo, série, número, tpEmis, cNF
    e DV de uma chave de acesso de 44 dígitos — sem precisar de nenhuma
    chamada de rede. Usado pra cruzar o resumo (resNFe) da SEFAZ contra as
    notas já extraídas do PDF (que não trazem a chave, só série+número)."""
    chave = re.sub(r"\D", "", chave or "")
    if len(chave) != 44:
        raise ValueError(f"Chave de acesso inválida (esperado 44 dígitos, veio {len(chave)}): {chave!r}")
    return {
        "cuf": chave[0:2],
        "aamm": chave[2:6],
        "cnpj_emitente": chave[6:20],
        "modelo": chave[20:22],
        "serie": str(int(chave[22:25])),
        "numero": str(int(chave[25:34])),
        "tpemis": chave[34:35],
        "cnf": chave[35:43],
        "dv": chave[43:44],
    }


# ── Montagem e parsing do envelope SOAP ──────────────────────────────────────
def _montar_soap_distdfe(cnpj: str, cuf_autor: int, tp_amb: int,
                          ult_nsu: str = None, ch_nfe: str = None) -> str:
    """Monta o envelope SOAP 1.2 do pedido distDFeInt. Exatamente um entre
    ult_nsu (consulta em lote por NSU) ou ch_nfe (consulta de UM documento
    específico) deve ser informado."""
    if bool(ult_nsu) == bool(ch_nfe):
        raise ValueError("Informe exatamente um entre ult_nsu e ch_nfe.")

    if ult_nsu is not None:
        consulta_xml = f'<distNSU><ultNSU>{int(ult_nsu):015d}</ultNSU></distNSU>'
    else:
        consulta_xml = f'<consChNFe><chNFe>{ch_nfe}</chNFe></consChNFe>'

    return f'''<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="{SOAP_NS}">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="{WSDL_NS}">
      <nfeDadosMsg>
        <distDFeInt xmlns="{NFE_NS}" versao="1.35">
          <tpAmb>{tp_amb}</tpAmb>
          <cUFAutor>{cuf_autor}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          {consulta_xml}
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>'''.encode("utf-8")


def _parse_retorno_soap(corpo_resposta: bytes) -> dict:
    """Extrai cStat, xMotivo, ultNSU, maxNSU e a lista de docZip (nsu,
    schema, xml_bytes já descomprimido) da resposta SOAP."""
    root = ET.fromstring(corpo_resposta)

    def achar(tag):
        for el in root.iter():
            if el.tag.split("}")[-1] == tag:
                return el
        return None

    ret = achar("retDistDFeInt")
    if ret is None:
        # Pode ser um soap:Fault — devolve o texto bruto pro chamador logar
        fault = achar("Fault") or achar("Reason") or achar("Text")
        raise RuntimeError(f"Resposta SOAP sem retDistDFeInt (possível Fault): "
                            f"{(fault.text if fault is not None else corpo_resposta[:500])!r}")

    def texto(tag):
        el = None
        for filho in ret.iter():
            if filho.tag.split("}")[-1] == tag:
                el = filho
                break
        return el.text if el is not None else None

    docs = []
    for docZip in ret.iter():
        if docZip.tag.split("}")[-1] != "docZip":
            continue
        nsu = docZip.attrib.get("NSU")
        schema = docZip.attrib.get("schema", "")
        try:
            xml_bytes = gzip.decompress(base64.b64decode(docZip.text))
        except Exception as ex:
            xml_bytes = None
        docs.append({"nsu": nsu, "schema": schema, "xml_bytes": xml_bytes, "erro": None if xml_bytes else str(ex)})

    return {
        "cstat": texto("cStat"),
        "xmotivo": texto("xMotivo"),
        "ultnsu": texto("ultNSU"),
        "maxnsu": texto("maxNSU"),
        "docs": docs,
    }


def _chamar_webservice(url: str, envelope: bytes, cert_pem: str, key_pem: str, timeout: int = 30) -> bytes:
    import requests
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    resp = requests.post(url, data=envelope, headers=headers, cert=(cert_pem, key_pem), timeout=timeout)
    resp.raise_for_status()
    return resp.content


# ── Parsing dos formatos de retorno ──────────────────────────────────────────
def _tag_sem_ns(el):
    return el.tag.split("}")[-1] if "}" in el.tag else el.tag


def _parsear_resnfe(xml_bytes: bytes) -> dict:
    """resNFe — resumo. Sem CFOP/ICMS, só cabeçalho."""
    root = ET.fromstring(xml_bytes)
    valores = {_tag_sem_ns(el).lower(): (el.text or "").strip() for el in root.iter() if el.text and el.text.strip()}
    return {
        "chave": valores.get("chnfe"),
        "cnpj_emitente": valores.get("cnpj"),
        "nome_emitente": valores.get("xnome"),
        "data_emissao": valores.get("dhemi"),
        "tipo_nf": valores.get("tpnf"),  # 0=Entrada, 1=Saída (do ponto de vista do EMITENTE)
        "valor_total": _to_float(valores.get("vnf")),
        "situacao": valores.get("csitnfe"),  # 1=autorizada, outros=cancelada/denegada/etc.
        "protocolo": valores.get("nprot"),
    }


def _parsear_procnfe_itens(xml_bytes: bytes) -> list:
    """procNFe (XML completo) — extrai CFOP/base/ICMS por item, já agregado
    por CFOP dentro da própria nota (uma nota pode ter itens de CFOPs
    diferentes, embora seja raro no varejo de veículos/peças)."""
    root = ET.fromstring(xml_bytes)
    agregados = {}  # cfop -> {"base": 0, "icms": 0, "valor_produtos": 0}

    for det in root.iter():
        if _tag_sem_ns(det) != "det":
            continue
        cfop = None
        vprod = 0.0
        vbc = 0.0
        vicms = 0.0
        for el in det.iter():
            nome = _tag_sem_ns(el).lower()
            if el.text is None:
                continue
            txt = el.text.strip()
            if nome == "cfop":
                cfop = txt
            elif nome == "vprod":
                vprod = _to_float(txt) or 0.0
            elif nome == "vbc" and vbc == 0.0:
                vbc = _to_float(txt) or 0.0
            elif nome == "vicms" and vicms == 0.0:
                vicms = _to_float(txt) or 0.0
        if cfop:
            ag = agregados.setdefault(cfop, {"base": 0.0, "icms": 0.0, "valor_produtos": 0.0})
            ag["base"] += vbc
            ag["icms"] += vicms
            ag["valor_produtos"] += vprod

    return [{"cfop": cfop, **vals} for cfop, vals in agregados.items()]


def _to_float(s):
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── Consulta principal: resumo em lote por NSU ───────────────────────────────
def consultar_resumo_periodo(empresa: str, filial: str,
                              data_inicio: str, data_fim: str,
                              ambiente: str = "producao",
                              usar_checkpoint: bool = True,
                              nsu_inicial: int = None,
                              max_chamadas: int = 500,
                              log=None, prog=None) -> dict:
    """
    Consulta o resumo (resNFe) de todas as notas do período em que o CNPJ
    da empresa/filial aparece como emitente OU destinatário — em lote, via
    NSU sequencial. NÃO traz CFOP/ICMS (ver aviso no topo do arquivo).

    Retorna {"ok": bool, "notas": [...resumos...], "erro": str|None}.
    """
    import time as _time

    def _log(msg):
        if log:
            log(msg)

    def _prog(pct, msg=""):
        if prog:
            prog(pct, msg)

    cfg = _nfse_api._carregar_config_certificado(empresa, filial)
    cnpj = re.sub(r"\D", "", cfg["cnpj"])

    dt_ini = datetime.strptime(data_inicio, "%d/%m/%Y")
    dt_fim = datetime.strptime(data_fim, "%d/%m/%Y").replace(hour=23, minute=59, second=59)

    uf = _uf_do_cnpj_ou_padrao(empresa, filial)
    cuf_autor = CODIGO_UF.get(uf, 33)  # padrão RJ se não achar
    tp_amb = 1 if ambiente == "producao" else 2
    url = URL_PRODUCAO if ambiente == "producao" else URL_HOMOLOGACAO

    if nsu_inicial is None:
        nsu_inicial = _ler_checkpoint(cnpj) if usar_checkpoint else 0

    cert_pem, key_pem, pasta_temp = _nfse_api._preparar_certificado_temp(cfg["pfx"], cfg["senha"])
    _log(f"Certificado carregado. Consultando NFeDistribuicaoDFe a partir do NSU {nsu_inicial}...")
    _log(f"CNPJ: {cnpj} | cUFAutor: {cuf_autor} | Ambiente: {ambiente}")

    resultados = []
    nsu_atual = nsu_inicial
    maior_nsu_visto = nsu_inicial

    try:
        for _tentativa in range(max_chamadas):
            envelope = _montar_soap_distdfe(cnpj, cuf_autor, tp_amb, ult_nsu=str(nsu_atual))
            corpo = _chamar_webservice(url, envelope, cert_pem, key_pem)
            ret = _parse_retorno_soap(corpo)

            cstat = ret["cstat"]
            if cstat == CSTAT_CONSUMO_INDEVIDO:
                raise ErroConsumoIndevido(
                    f"SEFAZ rejeitou por consumo indevido (cStat 656): {ret['xmotivo']}. "
                    "Não adianta tentar de novo agora — aguarde antes de reconsultar."
                )
            if cstat in CSTAT_SERVICO_PARALISADO:
                raise RuntimeError(f"Serviço SEFAZ indisponível (cStat {cstat}): {ret['xmotivo']}")
            if cstat == CSTAT_NENHUM_DOCUMENTO:
                _log("Nenhum documento adicional — fim da consulta.")
                break
            if cstat != CSTAT_DOCUMENTOS_LOCALIZADOS:
                _log(f"AVISO: cStat inesperado {cstat} — {ret['xmotivo']}. Parando por segurança.")
                break

            for doc in ret["docs"]:
                nsu_item = int(doc["nsu"]) if doc["nsu"] else nsu_atual
                maior_nsu_visto = max(maior_nsu_visto, nsu_item)

                if doc["xml_bytes"] is None:
                    _log(f"AVISO: falha ao descomprimir docZip do NSU {nsu_item}: {doc['erro']}")
                    continue
                if "resNFe" not in (doc["schema"] or ""):
                    continue  # ignora resEvento e outros por enquanto

                try:
                    resumo = _parsear_resnfe(doc["xml_bytes"])
                except Exception as ex:
                    _log(f"AVISO: erro ao parsear resNFe do NSU {nsu_item}: {ex}")
                    continue

                data_ger = None
                if resumo.get("data_emissao"):
                    try:
                        data_ger = datetime.fromisoformat(
                            resumo["data_emissao"].replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        pass

                if data_ger and (data_ger > dt_fim or data_ger < dt_ini):
                    continue  # fora do período pedido, mas continua avançando NSU

                resumo["nsu"] = nsu_item
                # Decodifica a chave pra ter serie/numero — permite cruzar
                # com o que foi extraído do PDF (que não traz a chave).
                try:
                    resumo.update({f"chave_{k}": v for k, v in decodificar_chave(resumo["chave"]).items()})
                except Exception:
                    pass
                resultados.append(resumo)

            # NOTA: assumindo NSU exclusivo (mesmo padrão observado e
            # validado no nfse_adn_api.py) — se a SEFAZ tratar como
            # inclusivo, isso vai gerar NSUs repetidos no início de cada
            # lote seguinte (não perde nota, só reprocessa 1 a mais).
            nsu_atual = maior_nsu_visto
            _time.sleep(1.5)
            _prog(min(50 + len(resultados), 90), f"{len(resultados)} nota(s) no período")
            _log(f"  NSU até {maior_nsu_visto} — {len(resultados)} nota(s) no período até aqui.")

        if usar_checkpoint:
            _salvar_checkpoint(cnpj, maior_nsu_visto)

    finally:
        for arq in (cert_pem, key_pem):
            try:
                os.remove(arq)
            except Exception:
                pass
        try:
            os.rmdir(pasta_temp)
        except Exception:
            pass

    _log(f"Total de notas (resumo) encontradas no período: {len(resultados)}")
    return {"ok": True, "notas": resultados, "erro": None}


# ── Consulta sob demanda: XML completo de UMA nota específica ───────────────
def consultar_nfe_completa(empresa: str, filial: str, chave: str,
                            ambiente: str = "producao", log=None) -> dict:
    """
    Busca o XML completo (procNFe) de UMA nota específica por chave de
    acesso, e extrai CFOP/base/ICMS por item. Uso pontual — só chamar pra
    notas que já apareceram divergentes ou faltando na comparação com o
    resumo (nunca em loop por todas as notas do período, ver aviso no
    topo do arquivo).
    """
    def _log(msg):
        if log:
            log(msg)

    cfg = _nfse_api._carregar_config_certificado(empresa, filial)
    cnpj = re.sub(r"\D", "", cfg["cnpj"])
    chave = re.sub(r"\D", "", chave)

    uf = _uf_do_cnpj_ou_padrao(empresa, filial)
    cuf_autor = CODIGO_UF.get(uf, 33)
    tp_amb = 1 if ambiente == "producao" else 2
    url = URL_PRODUCAO if ambiente == "producao" else URL_HOMOLOGACAO

    cert_pem, key_pem, pasta_temp = _nfse_api._preparar_certificado_temp(cfg["pfx"], cfg["senha"])
    try:
        envelope = _montar_soap_distdfe(cnpj, cuf_autor, tp_amb, ch_nfe=chave)
        corpo = _chamar_webservice(url, envelope, cert_pem, key_pem)
        ret = _parse_retorno_soap(corpo)

        if ret["cstat"] == CSTAT_CONSUMO_INDEVIDO:
            raise ErroConsumoIndevido(f"SEFAZ rejeitou por consumo indevido: {ret['xmotivo']}")
        if ret["cstat"] != CSTAT_DOCUMENTOS_LOCALIZADOS or not ret["docs"]:
            return {"ok": False, "erro": f"Nota não retornada (cStat {ret['cstat']}: {ret['xmotivo']})", "itens": []}

        doc = ret["docs"][0]
        if doc["xml_bytes"] is None:
            return {"ok": False, "erro": f"Falha ao descomprimir XML: {doc['erro']}", "itens": []}

        itens = _parsear_procnfe_itens(doc["xml_bytes"])
        _log(f"  Chave {chave}: {len(itens)} CFOP(s) distinto(s) na nota.")
        return {"ok": True, "erro": None, "itens": itens, "schema": doc["schema"]}
    finally:
        for arq in (cert_pem, key_pem):
            try:
                os.remove(arq)
            except Exception:
                pass
        try:
            os.rmdir(pasta_temp)
        except Exception:
            pass


def _uf_do_cnpj_ou_padrao(empresa: str, filial: str) -> str:
    """Tenta achar a UF a partir do cadastro de filiais do tarefas_db
    (EMPRESAS). Se não achar, quem chama já aplica o padrão RJ."""
    try:
        import tarefas_db
        for nome_filial, cnpj_fmt in tarefas_db.EMPRESAS.get(empresa, []):
            if nome_filial == filial:
                return "RJ"  # todas as filiais cadastradas hoje são RJ
    except Exception:
        pass
    return "RJ"
