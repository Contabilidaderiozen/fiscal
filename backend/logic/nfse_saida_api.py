"""
nfse_saida_api.py — Consulta NFS-e EMITIDAS (saída) pela empresa via API
oficial ADN Contribuinte, calcula total de ISS do período, e sinaliza
notas ativas com alíquota fora do padrão ou com ISS retido pelo tomador.

Reaproveita infraestrutura de certificado do nfse_adn_api.py (mesma API,
mesmo certificado por empresa/filial).

IMPORTANTE — pontos ainda não 100% confirmados (testar com dados reais):
- tpRetISSQN == "2" está sendo tratado como "retido pelo tomador" (padrão
  nacional comum), mas isso não foi testado contra uma nota real com
  retenção. Se aparecer errado, é o primeiro lugar a revisar.
- Detecção de nota CANCELADA (TipoDocumento == "CNC" ou "EVENTO" vinculado
  pela chave de acesso) ainda não testada contra um evento de cancelamento
  real — implementado como melhor esforço.
- Checkpoint de NSU é INDEPENDENTE do módulo de Entrada. Mesmo endpoint da
  API, mas cada lado (entrada/saída) anda pelo NSU e filtra o que
  interessa. Na primeira execução, isso significa reprocessar o mesmo
  trecho de NSU que a Entrada já andou — não tem como evitar sem unificar
  os dois módulos num só (fica pra depois, se fizer sentido).
"""
import os
import re
import json
import time as _time
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime

from . import nfse_adn_api as adn  # reaproveita certificado, decodificação, URLs

_PASTA_CERTIFICADOS = adn._PASTA_CERTIFICADOS
_ARQUIVO_CHECKPOINT_SAIDA = os.path.join(_PASTA_CERTIFICADOS, "nsu_checkpoint_saida.json")

def processar(empresa: str, filial: str, data_inicio: str, data_fim: str,
              pasta_destino: str, ambiente: str = "producao",
              ignorar_checkpoint: bool = False,
              callback_log=None, callback_progresso=None) -> dict:
    log(">>> VERSÃO DE TESTE DA ATUALIZAÇÃO <<<")   # ← linha temporária de teste
    
# ── Checkpoint de NSU (independente do módulo de Entrada) ────────────────────
def _ler_checkpoint_saida(cnpj: str) -> int:
    if not os.path.exists(_ARQUIVO_CHECKPOINT_SAIDA):
        return 0
    try:
        with open(_ARQUIVO_CHECKPOINT_SAIDA, "r", encoding="utf-8") as f:
            return int(json.load(f).get(cnpj, 0))
    except Exception:
        return 0


def _salvar_checkpoint_saida(cnpj: str, nsu: int):
    dados = {}
    if os.path.exists(_ARQUIVO_CHECKPOINT_SAIDA):
        try:
            with open(_ARQUIVO_CHECKPOINT_SAIDA, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            dados = {}
    dados[cnpj] = nsu
    os.makedirs(os.path.dirname(_ARQUIVO_CHECKPOINT_SAIDA), exist_ok=True)
    with open(_ARQUIVO_CHECKPOINT_SAIDA, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)


# ── Parser do XML de nota EMITIDA ──────────────────────────────────────────
def _texto(elemento, caminho):
    """Busca um valor de texto por caminho relativo simples, tolerando
    namespace (procura a tag por nome, ignorando o prefixo {...})."""
    if elemento is None:
        return None
    partes = caminho.split("/")
    atual = elemento
    for parte in partes:
        encontrado = None
        for filho in atual:
            tag = filho.tag.split("}")[-1] if "}" in filho.tag else filho.tag
            if tag == parte:
                encontrado = filho
                break
        if encontrado is None:
            return None
        atual = encontrado
    return atual.text.strip() if atual.text else None


def _achar_elemento(raiz, nome_tag):
    """Acha o PRIMEIRO elemento com essa tag (ignorando namespace),
    em qualquer profundidade da árvore."""
    for el in raiz.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == nome_tag:
            return el
    return None


def _parsear_xml_saida(xml_bytes: bytes, cnpj_proprio: str) -> dict:
    """Extrai campos da NFS-e emitida, usando os nomes de tag confirmados
    contra uma nota real da Riozen (formato NBS/SefinNacional):
      <emit><CNPJ>...</CNPJ></emit>           -> prestador (emitente)
      <DPS><infDPS><toma><CNPJ>...</CNPJ>     -> tomador
      <valores><vBC>,<pAliqAplic>,<vISSQN>,<vLiq>
      <infDPS><serv><cServ><cTribNac>
      <infDPS><serv><valores><tribMun><tribISSQN>,<tpRetISSQN>
    """
    root = ET.fromstring(xml_bytes)
    cnpj_limpo = re.sub(r'\D', '', cnpj_proprio)

    numero = _texto(root, "infNFSe/nNFSe") or None
    # nNFSe pode estar em profundidade diferente dependendo da versão do
    # schema — fallback: procura em qualquer lugar da árvore
    if not numero:
        el = _achar_elemento(root, "nNFSe")
        numero = el.text.strip() if el is not None and el.text else None

    el_emit = _achar_elemento(root, "emit")
    prestador_cnpj = _texto(el_emit, "CNPJ") if el_emit is not None else None
    prestador_nome = _texto(el_emit, "xNome") if el_emit is not None else None

    el_toma = _achar_elemento(root, "toma")
    tomador_cnpj = _texto(el_toma, "CNPJ") if el_toma is not None else None
    tomador_nome = _texto(el_toma, "xNome") if el_toma is not None else None

    el_valores_top = _achar_elemento(root, "valores")
    vbc = _texto(el_valores_top, "vBC")
    aliquota = _texto(el_valores_top, "pAliqAplic")
    valor_iss = _texto(el_valores_top, "vISSQN")
    valor_liquido = _texto(el_valores_top, "vLiq")

    el_ctribnac = _achar_elemento(root, "cTribNac")
    codigo_servico = el_ctribnac.text.strip() if el_ctribnac is not None and el_ctribnac.text else None

    el_tribmun = _achar_elemento(root, "tribMun")
    trib_issqn = _texto(el_tribmun, "tribISSQN") if el_tribmun is not None else None
    tp_ret_issqn = _texto(el_tribmun, "tpRetISSQN") if el_tribmun is not None else None

    el_dhemi = _achar_elemento(root, "dhEmi")
    data_emissao = el_dhemi.text.strip() if el_dhemi is not None and el_dhemi.text else None

    el_ccancel = _achar_elemento(root, "cStat")  # cStat=101 costuma indicar cancelamento na Distribuição DFe
    c_stat = el_ccancel.text.strip() if el_ccancel is not None and el_ccancel.text else None

    def _float(v):
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "."))
        except Exception:
            return None

    dados = {
        "numero": numero,
        "codigo_servico": codigo_servico,
        "data_emissao": data_emissao,
        "prestador_cnpj": prestador_cnpj,
        "prestador_nome": prestador_nome,
        "tomador_cnpj": tomador_cnpj,
        "tomador_nome": tomador_nome,
        "valor_bc_iss": _float(vbc),
        "aliquota_iss": _float(aliquota),
        "valor_iss": _float(valor_iss),
        "valor_liquido": _float(valor_liquido),
        # tpRetISSQN == "2" = retido pelo tomador (a confirmar com caso real)
        "iss_retido_pelo_tomador": tp_ret_issqn == "2",
        "tp_ret_issqn_bruto": tp_ret_issqn,
        "eh_prestador_proprio": (
            re.sub(r'\D', '', prestador_cnpj or "") == cnpj_limpo
        ),
        "cancelada": c_stat not in (None, "100"),  # 100 = autorizado; qualquer outro, suspeito
        "c_stat_bruto": c_stat,
    }
    return {k: v for k, v in dados.items() if v is not None}


# ── Consulta principal (percorre o NSU, filtra notas de SAÍDA) ──────────────
def consultar_notas_saida(cnpj: str, pfx_path: str, senha: str,
                           data_inicio: str, data_fim: str,
                           ambiente: str = "producao",
                           nsu_inicial: int = None,
                           usar_checkpoint: bool = True,
                           log=None, prog=None,
                           max_chamadas: int = 3000) -> list:
    """Mesmo paradigma de NSU do módulo de Entrada, mas filtrando notas
    onde o CNPJ consultado é o PRESTADOR (emitente), não o tomador."""
    import requests

    def _log(msg):
        if log: log(msg)

    def _prog(pct, msg=""):
        if prog: prog(pct, msg)

    cnpj_limpo = re.sub(r'\D', '', cnpj)
    base_url = adn.BASE_PRODUCAO if ambiente == "producao" else adn.BASE_HOMOLOGACAO

    if nsu_inicial is None:
        nsu_inicial = _ler_checkpoint_saida(cnpj_limpo) if usar_checkpoint else 0

    dt_ini = datetime.strptime(data_inicio, "%d/%m/%Y")
    dt_fim = datetime.strptime(data_fim, "%d/%m/%Y").replace(hour=23, minute=59, second=59)

    caminho_cert, caminho_key, pasta_temp_cert = adn._preparar_certificado_temp(pfx_path, senha)
    _log(f"Certificado carregado ({os.path.basename(pfx_path)}). Consultando notas de SAÍDA a partir do NSU {nsu_inicial}...")

    resultados = []
    nsu_atual = nsu_inicial
    maior_nsu_visto = nsu_inicial
    _contagem_tipo_ignorado = {}
    _qtd_data_filtrada = 0

    try:
        for _tentativa in range(max_chamadas):
            resp = None
            for _tentativa_429 in range(6):
                resp = requests.get(
                    f"{base_url}/DFe/{nsu_atual}",
                    params={"cnpjConsulta": cnpj_limpo, "lote": True},
                    cert=(caminho_cert, caminho_key),
                    timeout=30,
                )
                if resp.status_code != 429:
                    break
                espera = resp.headers.get("Retry-After")
                espera = float(espera) if espera else (5 * (_tentativa_429 + 1))
                _log(f"  AVISO: limite de requisições da API (429) — aguardando {espera:.0f}s...")
                _time.sleep(espera)
            else:
                raise RuntimeError("API continua recusando por limite de requisições (429).")

            if resp.status_code == 404:
                _log("Nenhum documento adicional encontrado (404) — fim da consulta.")
                break
            resp.raise_for_status()
            dados = resp.json()

            status = dados.get("StatusProcessamento")
            if status == "REJEICAO":
                erros = dados.get("Erros") or []
                msgs = "; ".join(e.get("Descricao", "") or e.get("Codigo", "") for e in erros)
                raise RuntimeError(f"API rejeitou a consulta (NSU {nsu_atual}): {msgs or 'sem detalhe'}")
            if status == "NENHUM_DOCUMENTO_LOCALIZADO":
                _log("Nenhum documento novo a partir deste NSU — fim da consulta.")
                break

            lote = dados.get("LoteDFe") or []
            if not lote:
                break

            for item in lote:
                nsu_item = item.get("NSU") or nsu_atual
                maior_nsu_visto = max(maior_nsu_visto, nsu_item)

                tipo_doc = item.get("TipoDocumento")
                if tipo_doc not in ("NFSE", "CNC", "EVENTO"):
                    _contagem_tipo_ignorado[tipo_doc] = _contagem_tipo_ignorado.get(tipo_doc, 0) + 1
                    continue

                xml_b64 = item.get("ArquivoXml")
                if not xml_b64:
                    continue

                try:
                    xml_bytes = adn._decodificar_xml(xml_b64)
                    nota = _parsear_xml_saida(xml_bytes, cnpj)
                except Exception as ex:
                    _log(f"AVISO: erro ao decodificar/ler XML do NSU {nsu_item}: {ex}")
                    continue

                # Filtro de período: usa a data de EMISSÃO real da nota
                # (dhEmi, dentro do XML) sempre que disponível — NÃO a data
                # de geração do NSU (carimbo de quando o documento chegou ao
                # ADN), que pode ficar fora do período mesmo pra notas
                # emitidas dentro dele (foi isso que descartou a nota 600 de
                # SAO JOAO DE MERITI em testes anteriores). Só cai pra data
                # de geração do NSU se a nota não tiver dhEmi legível.
                data_ref = None
                data_emissao_str = nota.get("data_emissao")
                if data_emissao_str:
                    try:
                        data_ref = datetime.fromisoformat(str(data_emissao_str).replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        data_ref = None
                if data_ref is None:
                    data_ger_str = item.get("DataHoraGeracao")
                    if data_ger_str:
                        try:
                            data_ref = datetime.fromisoformat(data_ger_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            data_ref = None
                if data_ref and (data_ref > dt_fim or data_ref < dt_ini):
                    _qtd_data_filtrada += 1
                    continue

                if not nota.get("eh_prestador_proprio"):
                    # Normal: a maioria dos documentos deste NSU são notas
                    # de ENTRADA (Riozen como tomadora), não interessa aqui.
                    # Mas se o CNPJ da Riozen também não aparece como
                    # tomador, é sinal de que o parser não identificou
                    # nenhum dos dois lados corretamente nesse XML — pode
                    # ser um EVENTO (estrutura diferente, sem emit/toma) ou
                    # uma nota real de estrutura fora do padrão esperado.
                    # Não silenciamos mais isso pra tipo EVENTO: um evento
                    # "vazio" (sem chave associada visível) pode na verdade
                    # ser a única pista de uma nota que devia ter vindo como
                    # NFSE e não veio — como aconteceu com a nota 600 de
                    # SAO JOAO DE MERITI.
                    tomador_ok = re.sub(r'\D', '', nota.get("tomador_cnpj") or "") == cnpj_limpo
                    if not tomador_ok:
                        _trecho_xml = xml_bytes[:600].decode("utf-8", errors="replace").replace("\n", " ").replace("\r", "")
                        _log(f"  AVISO: NSU {nsu_item} (tipo {tipo_doc}, nota {nota.get('numero','?')}, "
                             f"chave {item.get('ChaveAcesso','?')}) não bateu como prestador NEM como "
                             f"tomador da Riozen — prestador_cnpj={nota.get('prestador_cnpj')!r}, "
                             f"tomador_cnpj={nota.get('tomador_cnpj')!r}.")
                        _log(f"    Trecho do XML (primeiros 600 bytes): {_trecho_xml}")
                    continue
                nota["nsu"] = nsu_item
                nota["chave_acesso"] = item.get("ChaveAcesso")
                nota["tipo_documento_original"] = tipo_doc
                resultados.append(nota)

            # IMPORTANTE: a API trata o NSU informado como filtro EXCLUSIVO
            # ("documentos com NSU maior que este"), não inclusivo. Usar
            # maior_nsu_visto + 1 fazia a próxima chamada pular o documento
            # que estivesse bem em cima desse limite — foi assim que a nota
            # 600 de SAO JOAO DE MERITI (NSU 969) sumiu silenciosamente:
            # o lote anterior parou em NSU 968, a próxima chamada pediu a
            # partir de 969, e a API devolveu só o que vem DEPOIS de 969,
            # excluindo o próprio 969. Sem o +1, a próxima chamada pede a
            # partir de maior_nsu_visto mesmo, e a API já exclui esse valor
            # sozinha — nenhum documento é perdido nem repetido.
            nsu_atual = maior_nsu_visto
            _time.sleep(1.5)
            _prog(min(50 + len(resultados), 90), f"{len(resultados)} nota(s) de saída no período")
            _log(f"  NSU processado até {maior_nsu_visto} — {len(resultados)} nota(s) de saída no período até aqui.")

        if usar_checkpoint:
            _salvar_checkpoint_saida(cnpj_limpo, maior_nsu_visto)

    finally:
        for arq in (caminho_cert, caminho_key):
            try: os.remove(arq)
            except Exception: pass
        try: os.rmdir(pasta_temp_cert)
        except Exception: pass

    _log(f"Total de notas de saída encontradas no período: {len(resultados)}")
    if _qtd_data_filtrada:
        _log(f"  (diagnóstico) {_qtd_data_filtrada} documento(s) descartado(s) por data de geração fora do período.")
    if _contagem_tipo_ignorado:
        _resumo_tipos = ", ".join(f"{k or '(sem tipo)'}: {v}" for k, v in _contagem_tipo_ignorado.items())
        _log(f"  (diagnóstico) tipos de documento não processados: {_resumo_tipos}")
    return resultados


# ── Análise: total de ISS + detecção de alíquota fora do padrão ────────────
def analisar_notas_saida(notas: list) -> dict:
    """Calcula ISS total (só notas ativas) e sinaliza anomalias:
    alíquota diferente da mais comum no lote, ou ISS retido pelo tomador."""
    ativas = [n for n in notas if not n.get("cancelada")]
    canceladas = [n for n in notas if n.get("cancelada")]

    aliquotas_ativas = [n["aliquota_iss"] for n in ativas if n.get("aliquota_iss") is not None]
    aliquota_mais_comum = None
    if aliquotas_ativas:
        try:
            aliquota_mais_comum = statistics.mode(aliquotas_ativas)
        except statistics.StatisticsError:
            # sem moda única (empate) — usa a mediana como referência
            aliquota_mais_comum = statistics.median(aliquotas_ativas)

    iss_total = 0.0
    notas_analisadas = []
    for nota in notas:
        n = dict(nota)
        n["alertas"] = []
        n["status_geral"] = "OK"

        if n.get("cancelada"):
            n["status_geral"] = "CANCELADA"
            notas_analisadas.append(n)
            continue

        if n.get("valor_iss") is not None:
            iss_total += n["valor_iss"]

        if (aliquota_mais_comum is not None and n.get("aliquota_iss") is not None
                and abs(n["aliquota_iss"] - aliquota_mais_comum) > 0.001):
            n["alertas"].append(
                f"Alíquota de ISS ({n['aliquota_iss']}%) diferente da mais comum no período ({aliquota_mais_comum}%) — verificar."
            )
            n["status_geral"] = "DIVERGENCIA"

        if n.get("iss_retido_pelo_tomador"):
            n["alertas"].append(
                "ISS retido pelo tomador — não deve ser recolhido novamente pela Riozen. Conferir manualmente."
            )
            n["status_geral"] = "DIVERGENCIA"

        notas_analisadas.append(n)

    return {
        "notas": notas_analisadas,
        "total_ativas": len(ativas),
        "total_canceladas": len(canceladas),
        "aliquota_mais_comum": aliquota_mais_comum,
        "iss_total_periodo": round(iss_total, 2),
    }


# ── Relatório Excel (mesmo estilo visual do relatório de Entrada) ──────────
def gerar_relatorio_excel_saida(notas_analisadas: list, cnpj_prestador: str,
                                 periodo: str, pasta_destino: str,
                                 aliquota_mais_comum, iss_total_periodo: float,
                                 callback_log=None) -> str:
    """Gera relatório Excel das notas de SAÍDA (emitidas), mesma paleta e
    estrutura (aba detalhe + aba Resumo) do relatório de Entrada, adaptado
    às colunas relevantes pra quem emite (ISS a recolher), não pra quem
    recebe (retenções de IRRF/PIS/COFINS/CSLL).
    Retorna o caminho do arquivo gerado."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    def log(msg):
        if callback_log: callback_log(msg)

    log("Gerando relatório Excel de Saída...")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NFS-e Saída"

    # ── Paleta de cores (mesma do relatório de Entrada) ────────────────────
    AZUL_ESC  = "FF0A1929"
    AZUL_MED  = "FF1A3A5C"
    VERDE     = "FF00D084"
    VERMELHO  = "FFFF4757"
    CINZA_CLR = "FFF0F4F8"
    BRANCO    = "FFFFFFFF"

    def hdr_fill(cor): return PatternFill("solid", fgColor=cor)
    def fonte(negrito=False, cor="FF000000", tam=10):
        return Font(bold=negrito, color=cor, name="Consolas", size=tam)
    def borda_fina():
        s = Side(style="thin", color="FFB0C4D8")
        return Border(left=s, right=s, top=s, bottom=s)
    fmt_brl = '#,##0.00'
    aln_ctr = Alignment(horizontal="center", vertical="center", wrap_text=True)
    aln_esq = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    aln_dir = Alignment(horizontal="right",  vertical="center")

    # ── Cabeçalho geral ─────────────────────────────────────────────────────
    ws.merge_cells("A1:K1")
    ws["A1"] = "RELATÓRIO DE NFS-e EMITIDAS — APURAÇÃO DE ISS"
    ws["A1"].font      = fonte(negrito=True, cor=BRANCO, tam=13)
    ws["A1"].fill      = hdr_fill(AZUL_ESC)
    ws["A1"].alignment = aln_ctr

    ws.merge_cells("A2:K2")
    ws["A2"] = f"CNPJ Prestador: {cnpj_prestador}    Período: {periodo}    Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font      = fonte(cor=BRANCO, tam=9)
    ws["A2"].fill      = hdr_fill(AZUL_MED)
    ws["A2"].alignment = aln_ctr
    ws.row_dimensions[1].height = 28
    ws.row_dimensions[2].height = 18

    # ── Colunas ─────────────────────────────────────────────────────────────
    COLUNAS = [
        ("Nº Nota",             12, "str"),
        ("Data Emissão",        14, "str"),
        ("Tomador",             32, "str"),
        ("CNPJ Tomador",        20, "str"),
        ("Cód. Serviço",        12, "str"),
        ("Base ISS",            14, "num"),
        ("Alíquota\nISS (%)",   12, "num"),
        ("Valor ISS",           14, "num"),
        ("Valor Líquido",       14, "num"),
        ("ISS Retido\nTomador", 12, "status"),
        ("Status",              14, "status"),
        ("Observações",         50, "str"),
    ]

    ROW_CAB = 4
    ws.row_dimensions[ROW_CAB].height = 32

    for col_idx, (titulo, largura, tipo) in enumerate(COLUNAS, start=1):
        cel = ws.cell(row=ROW_CAB, column=col_idx, value=titulo)
        cel.font      = fonte(negrito=True, cor=BRANCO, tam=9)
        cel.fill      = hdr_fill(AZUL_MED)
        cel.alignment = aln_ctr
        cel.border    = borda_fina()
        ws.column_dimensions[get_column_letter(col_idx)].width = largura

    # ── Dados ───────────────────────────────────────────────────────────────
    ROW_INI = ROW_CAB + 1
    total_ok = total_div = total_cancel = 0

    for i, nota in enumerate(notas_analisadas):
        row = ROW_INI + i
        status = nota.get("status_geral", "")

        if status == "OK":            bg_linha = "FFE8F5EA"; total_ok += 1
        elif status == "DIVERGENCIA": bg_linha = "FFFFF3E0"; total_div += 1
        elif status == "CANCELADA":   bg_linha = "FFE8E8E8"; total_cancel += 1
        else:                         bg_linha = "FFFFE0E0"

        fill_linha = hdr_fill(bg_linha)
        retido = nota.get("iss_retido_pelo_tomador")

        valores_linha = [
            nota.get("numero", ""),
            nota.get("data_emissao", ""),
            nota.get("tomador_nome", ""),
            nota.get("tomador_cnpj", ""),
            nota.get("codigo_servico", ""),
            nota.get("valor_bc_iss", 0) or 0,
            nota.get("aliquota_iss", 0) or 0,
            nota.get("valor_iss", 0) or 0,
            nota.get("valor_liquido", 0) or 0,
            "SIM" if retido else ("—" if status == "CANCELADA" else "não"),
            status,
            " | ".join(nota.get("alertas", [])),
        ]

        for col_idx, val in enumerate(valores_linha, start=1):
            cel = ws.cell(row=row, column=col_idx, value=val)
            cel.fill   = fill_linha
            cel.border = borda_fina()
            cel.font   = fonte(tam=9)

            tipo_col = COLUNAS[col_idx-1][2]
            if tipo_col == "num" and isinstance(val, (int, float)):
                cel.number_format = fmt_brl
                cel.alignment = aln_dir
            elif tipo_col == "status":
                cel.alignment = aln_ctr
                if val == "SIM" or status == "DIVERGENCIA":
                    cel.font = fonte(negrito=True, cor=VERMELHO, tam=9)
                elif status == "OK":
                    cel.font = fonte(negrito=True, cor=VERDE, tam=9)
            else:
                cel.alignment = aln_esq

        ws.row_dimensions[row].height = 16

    # ── Aba Resumo ──────────────────────────────────────────────────────────
    ws_res = wb.create_sheet("Resumo")
    ws_res["A1"] = "RESUMO DA APURAÇÃO"
    ws_res["A1"].font = fonte(negrito=True, cor=BRANCO, tam=12)
    ws_res["A1"].fill = hdr_fill(AZUL_ESC)
    ws_res.merge_cells("A1:B1")
    ws_res["A1"].alignment = aln_ctr
    ws_res.row_dimensions[1].height = 24

    resumo_dados = [
        ("Total de notas no período", len(notas_analisadas), BRANCO),
        ("Notas ativas sem divergência (OK)", total_ok, "FFE8F5EA"),
        ("Notas com divergência (revisar)", total_div, "FFFFF3E0"),
        ("Notas canceladas", total_cancel, "FFE8E8E8"),
        ("", "", BRANCO),
        ("Alíquota de ISS mais comum no período",
         f"{aliquota_mais_comum}%" if aliquota_mais_comum is not None else "—", BRANCO),
        ("ISS total do período (só notas ativas)", round(iss_total_periodo, 2), BRANCO),
    ]

    for ri, (label, val, bg) in enumerate(resumo_dados, start=3):
        if not label: continue
        ws_res.cell(row=ri, column=1, value=label).font = fonte(tam=10)
        cel_val = ws_res.cell(row=ri, column=2, value=val)
        cel_val.fill = hdr_fill(bg)
        if isinstance(val, float): cel_val.number_format = fmt_brl
        for ci in range(1, 3):
            ws_res.cell(row=ri, column=ci).border = borda_fina()

    ws_res.column_dimensions["A"].width = 42
    ws_res.column_dimensions["B"].width = 20

    # ── Salvar ──────────────────────────────────────────────────────────────
    os.makedirs(pasta_destino, exist_ok=True)
    periodo_safe = periodo.replace("/", "-").replace(" ", "_")
    nome_arq = f"NFSE_SAIDA_ISS_{periodo_safe}.xlsx"
    caminho  = os.path.join(pasta_destino, nome_arq)
    wb.save(caminho)
    log(f"Relatório salvo: {caminho}")
    return caminho


# ── Função principal (mesmo padrão do módulo de Entrada) ───────────────────
def processar(empresa: str, filial: str, data_inicio: str, data_fim: str,
              pasta_destino: str, ambiente: str = "producao",
              ignorar_checkpoint: bool = False,
              callback_log=None, callback_progresso=None) -> dict:
    import traceback

    def log(msg):
        if callback_log: callback_log(msg)

    def prog(pct, msg=""):
        if callback_progresso: callback_progresso(pct, msg)

    log("Iniciando apuração NFS-e de SAÍDA (via API oficial ADN Contribuinte)")
    log(f"Empresa: {empresa} | Filial: {filial}")
    log(f"Período: {data_inicio} a {data_fim}")
    log(f"Ignorar checkpoint de NSU: {'SIM' if ignorar_checkpoint else 'não'}")
    log("─" * 56)

    try:
        cfg = adn._carregar_config_certificado(empresa, filial)
    except Exception as ex:
        return {"ok": False, "mensagem": str(ex)}

    try:
        notas_raw = consultar_notas_saida(
            cnpj=cfg["cnpj"], pfx_path=cfg["pfx"], senha=cfg["senha"],
            data_inicio=data_inicio, data_fim=data_fim,
            ambiente=ambiente, log=log, prog=prog,
            usar_checkpoint=not ignorar_checkpoint,
            nsu_inicial=0 if ignorar_checkpoint else None,
        )
    except Exception as ex:
        traceback.print_exc()
        return {"ok": False, "mensagem": f"Erro na consulta à API: {ex}"}

    if not notas_raw:
        return {"ok": False, "mensagem": "Nenhuma nota de saída encontrada no período informado."}

    prog(90, "Analisando ISS e alíquotas")
    analise = analisar_notas_saida(notas_raw)

    log(f"\n{'─'*56}")
    log(f"  Notas ativas: {analise['total_ativas']}")
    log(f"  Notas canceladas: {analise['total_canceladas']}")
    log(f"  Alíquota mais comum: {analise['aliquota_mais_comum']}%")
    log(f"  ISS total do período (só ativas): R$ {analise['iss_total_periodo']:.2f}")
    divergentes = sum(1 for n in analise["notas"] if n["status_geral"] == "DIVERGENCIA")
    log(f"  Notas com divergência: {divergentes}")
    log(f"{'─'*56}")

    prog(95, "Gerando Excel")
    periodo = f"{data_inicio} a {data_fim}"
    caminho = gerar_relatorio_excel_saida(
        notas_analisadas=analise["notas"],
        cnpj_prestador=cfg["cnpj"],
        periodo=periodo,
        pasta_destino=pasta_destino,
        aliquota_mais_comum=analise["aliquota_mais_comum"],
        iss_total_periodo=analise["iss_total_periodo"],
        callback_log=callback_log,
    )

    prog(100, "Concluído")
    total_notas = len(analise["notas"])
    return {
        "ok": True,
        "caminho_relatorio": caminho,
        "total_notas": total_notas,
        "notas_divergentes": divergentes,
        "total_ativas": analise["total_ativas"],
        "total_canceladas": analise["total_canceladas"],
        "aliquota_mais_comum": analise["aliquota_mais_comum"],
        "iss_total_periodo": analise["iss_total_periodo"],
        "notas": analise["notas"],
        "mensagem": f"{analise['total_ativas']} nota(s) ativa(s), {analise['total_canceladas']} cancelada(s). "
                    f"ISS total: R$ {analise['iss_total_periodo']:.2f}. {divergentes} com divergência.",
    }