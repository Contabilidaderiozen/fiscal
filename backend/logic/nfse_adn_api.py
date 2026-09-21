"""
nfse_adn_api.py — Integração oficial com a API "NFS-e - ADN Contribuinte"
(Ambiente de Dados Nacional, mantido pela SERPRO/Receita Federal), para
consulta de documentos fiscais (NFS-e recebidas como tomador de serviço)
via mTLS com certificado digital e-CNPJ.

Isso SUBSTITUI a automação via navegador (Selenium) do nfse_entrada.py —
sem Chrome, sem clique em menu, sem risco de CAPTCHA. A autenticação é
feita diretamente na conexão HTTPS (TLS mútuo), usando o certificado da
empresa em formato .pfx.

Especificação usada (real, não inferida): OpenAPI v1 da API NFS-e - ADN
Contribuinte, obtida em:
  https://adn.nfse.gov.br/contribuintes/swagger/v1/swagger.json

Endpoints:
  GET /DFe/{NSU}?cnpjConsulta=...&lote=true
      Retorna um lote de documentos fiscais a partir do NSU informado.
      Não existe filtro por data no lado do servidor — o modelo é
      sequencial por NSU (mesmo paradigma da "Distribuição DFe" da NF-e
      clássica). Por isso filtramos por data no lado do cliente, avançando
      o NSU até passar do período desejado.

  GET /NFSe/{ChaveAcesso}/Eventos
      Retorna eventos vinculados a uma NFS-e (cancelamento, confirmação
      etc.) — não usado nesta primeira versão, mas o endpoint já está
      documentado aqui para o caso de precisarmos verificar cancelamentos.

Formato dos documentos: cada item do lote traz o campo "ArquivoXml" com o
XML da NFS-e comprimido em GZip e representado em base64 (conforme a
descrição oficial da API). Decodificamos com base64 + gzip antes de parsear.

Configuração necessária (arquivo separado, NÃO fica neste .py nem em
nenhum lugar versionado no Git — contém senha de certificado):

  certificados/senhas.json
  {
    "Toyota|PILARES": {"cnpj": "22134988000114", "pfx": "moitinho_pilares.pfx", "senha": "..."},
    "BYD|JACAREPAGUA": {"cnpj": "52752754000100", "pfx": "mr_rio_jacarepagua.pfx", "senha": "..."}
  }

  Os caminhos de "pfx" são relativos à própria pasta "certificados/".
"""
import os
import re
import json
import base64
import gzip
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_PRODUCAO    = "https://adn.nfse.gov.br/contribuintes"
BASE_HOMOLOGACAO = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

_PASTA_MODULO       = os.path.dirname(os.path.abspath(__file__))
_PASTA_CERTIFICADOS = os.path.join(_PASTA_MODULO, "certificados")
_ARQUIVO_SENHAS     = os.path.join(_PASTA_CERTIFICADOS, "senhas.json")
_ARQUIVO_CHECKPOINT = os.path.join(_PASTA_CERTIFICADOS, "nsu_checkpoint.json")


# ── Configuração de certificados ──────────────────────────────────────────────
def _carregar_config_certificado(empresa: str, filial: str) -> dict:
    """Lê certificados/senhas.json e retorna {'pfx': caminho_absoluto, 'senha': str, 'cnpj': str}."""
    if not os.path.exists(_ARQUIVO_SENHAS):
        raise RuntimeError(
            f"Arquivo de configuração não encontrado: {_ARQUIVO_SENHAS}\n"
            "Crie esse arquivo (dentro da pasta 'certificados') com a estrutura:\n"
            '{"Empresa|Filial": {"cnpj": "00000000000100", "pfx": "arquivo.pfx", "senha": "..."}}'
        )
    with open(_ARQUIVO_SENHAS, "r", encoding="utf-8") as f:
        config = json.load(f)

    chave = f"{empresa}|{filial}"
    if chave not in config:
        raise RuntimeError(f"Certificado não configurado para '{chave}' em {_ARQUIVO_SENHAS}")

    info = config[chave]
    pfx_path = info["pfx"]
    if not os.path.isabs(pfx_path):
        pfx_path = os.path.join(_PASTA_CERTIFICADOS, pfx_path)
    if not os.path.exists(pfx_path):
        raise RuntimeError(f"Arquivo .pfx não encontrado: {pfx_path}")

    return {"pfx": pfx_path, "senha": info["senha"], "cnpj": info.get("cnpj", "")}


def _preparar_certificado_temp(pfx_path: str, senha: str):
    """Converte o .pfx (com senha) em arquivos PEM temporários (cert + chave
    privada sem senha), porque a biblioteca 'requests' exige caminhos de
    arquivo para autenticação mTLS, não bytes em memória.

    Retorna (caminho_cert_pem, caminho_key_pem, pasta_temp). O chamador é
    responsável por apagar pasta_temp depois de usar — a chave privada fica
    sem proteção de senha nesses arquivos temporários, então o tempo de vida
    deles deve ser o mínimo possível (só durante as chamadas HTTP)."""
    from cryptography.hazmat.primitives.serialization import (
        pkcs12, Encoding, PrivateFormat, NoEncryption
    )

    with open(pfx_path, "rb") as f:
        dados_pfx = f.read()

    chave_privada, certificado, cadeia_extra = pkcs12.load_key_and_certificates(
        dados_pfx, senha.encode("utf-8")
    )
    if chave_privada is None or certificado is None:
        raise RuntimeError(f"Não consegui ler certificado/chave de {pfx_path} — senha errada ou arquivo inválido.")

    pasta_temp = tempfile.mkdtemp(prefix="nfse_cert_")
    caminho_cert = os.path.join(pasta_temp, "cert.pem")
    caminho_key = os.path.join(pasta_temp, "key.pem")

    with open(caminho_cert, "wb") as f:
        f.write(certificado.public_bytes(Encoding.PEM))
        if cadeia_extra:
            for c in cadeia_extra:
                f.write(c.public_bytes(Encoding.PEM))

    with open(caminho_key, "wb") as f:
        f.write(chave_privada.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
    try:
        os.chmod(caminho_key, 0o600)  # melhor esforço no Windows
    except Exception:
        pass

    return caminho_cert, caminho_key, pasta_temp


# ── Checkpoint de NSU (permite continuar de onde parou entre execuções) ──────
def _ler_checkpoint(cnpj: str) -> int:
    if not os.path.exists(_ARQUIVO_CHECKPOINT):
        return 0
    try:
        with open(_ARQUIVO_CHECKPOINT, "r", encoding="utf-8") as f:
            return int(json.load(f).get(cnpj, 0))
    except Exception:
        return 0


def _salvar_checkpoint(cnpj: str, nsu: int):
    dados = {}
    if os.path.exists(_ARQUIVO_CHECKPOINT):
        try:
            with open(_ARQUIVO_CHECKPOINT, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            dados = {}
    dados[cnpj] = nsu
    os.makedirs(os.path.dirname(_ARQUIVO_CHECKPOINT), exist_ok=True)
    with open(_ARQUIVO_CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)


# ── Decodificação e leitura do XML ────────────────────────────────────────────
def _decodificar_xml(arquivo_xml_b64: str) -> bytes:
    """ArquivoXml vem em GZip + base64binary (conforme a documentação oficial)."""
    dados_gzip = base64.b64decode(arquivo_xml_b64)
    return gzip.decompress(dados_gzip)


def _parsear_xml_bytes(xml_bytes: bytes) -> dict:
    """Extrai os campos relevantes do XML da NFS-e (mesmo schema usado pelo
    download manual do portal — busca por nome de tag ignorando namespace,
    já validado contra um XML real nesta mesma conversa)."""
    dados = {}
    root = ET.fromstring(xml_bytes)

    def tag_sem_ns(el):
        return el.tag.split("}")[-1] if "}" in el.tag else el.tag

    valores = {}
    for el in root.iter():
        nome = tag_sem_ns(el).lower()
        if el.text and el.text.strip():
            valores.setdefault(nome, el.text.strip())

    def achar(*candidatos):
        for c in candidatos:
            if c in valores:
                return valores[c]
        for chave, val in valores.items():
            if any(c in chave for c in candidatos):
                return val
        return None

    dados["numero"]         = achar("nnfse", "numero", "nnf")
    dados["serie"]          = achar("serie", "sserie")
    dados["codigo_servico"] = achar("ctribnac", "coditemlistaservico", "itemlistaservico",
                                     "codigotributacaomunicipal", "ctribmun")
    dados["valor_servico"]  = achar("vservprest", "valorservico", "vliq", "vservicos")
    dados["iss_retido"]     = achar("vissretido", "vretissqn", "vissret")
    dados["irrf_retido"]    = achar("virrf", "vretirrf")
    dados["pis_retido"]     = achar("vpis", "vretpis")
    dados["cofins_retido"]  = achar("vcofins", "vretcofins")
    dados["csll_retido"]    = achar("vcsll", "vretcsll")
    dados["prestador_cnpj"] = achar("cnpj")
    dados["prestador_nome"] = achar("xnome", "razaosocial")
    dados["data_emissao"]   = achar("dhemi", "dataemissao", "demi")

    for campo in ("valor_servico", "iss_retido", "irrf_retido", "pis_retido", "cofins_retido", "csll_retido"):
        if dados.get(campo):
            try:
                dados[campo] = float(str(dados[campo]).replace(",", "."))
            except Exception:
                pass

    return {k: v for k, v in dados.items() if v is not None}


# ── Consulta principal (percorre o NSU) ───────────────────────────────────────
def consultar_documentos_nsu(cnpj: str, pfx_path: str, senha: str,
                              data_inicio: str, data_fim: str,
                              ambiente: str = "producao",
                              nsu_inicial: int = None,
                              usar_checkpoint: bool = True,
                              log=None, prog=None,
                              max_chamadas: int = 3000,
                              pasta_pdfs: str = None) -> list:
    """
    Consulta documentos fiscais (NFS-e) via API ADN Contribuinte, avançando
    o NSU sequencialmente e filtrando por data de geração dentro do período
    pedido. Retorna lista de dicts já no formato esperado por
    nfse_entrada.verificar_retencoes().

    Se pasta_pdfs for informado, gera um PDF (formato DANFSe) de cada nota
    nova encontrada, direto no momento em que o XML é decodificado — antes
    de qualquer coisa passar pelo acervo. Isso é proposital: o acervo pode
    não guardar os dados completos necessários pro PDF, então gerar aqui é
    a forma mais simples de garantir que sempre funciona pra notas
    efetivamente buscadas na API nesta execução.
    """
    import requests
    import time as _time

    def _log(msg):
        if log: log(msg)

    def _prog(pct, msg=""):
        if prog: prog(pct, msg)

    cnpj_limpo = re.sub(r'\D', '', cnpj)
    base_url = BASE_PRODUCAO if ambiente == "producao" else BASE_HOMOLOGACAO

    if nsu_inicial is None:
        nsu_inicial = _ler_checkpoint(cnpj_limpo) if usar_checkpoint else 0

    dt_ini = datetime.strptime(data_inicio, "%d/%m/%Y")
    dt_fim = datetime.strptime(data_fim, "%d/%m/%Y").replace(hour=23, minute=59, second=59)

    caminho_cert, caminho_key, pasta_temp_cert = _preparar_certificado_temp(pfx_path, senha)
    _log(f"Certificado carregado ({os.path.basename(pfx_path)}). Consultando a partir do NSU {nsu_inicial}...")

    resultados = []
    nsu_atual = nsu_inicial
    maior_nsu_visto = nsu_inicial
    _amostra_logada = False

    try:
        for _tentativa in range(max_chamadas):
            resp = requests.get(
                f"{base_url}/DFe/{nsu_atual}",
                params={"cnpjConsulta": cnpj_limpo, "lote": True},
                cert=(caminho_cert, caminho_key),
                timeout=30,
            )

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

                if item.get("TipoDocumento") != "NFSE":
                    continue  # ignora DPS, eventos, CNC — só notas por enquanto

                data_ger_str = item.get("DataHoraGeracao")
                data_ger = None
                if data_ger_str:
                    try:
                        data_ger = datetime.fromisoformat(data_ger_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        data_ger = None

                if not _amostra_logada:
                    _amostra_logada = True
                    _log(f"AMOSTRA DIAGNÓSTICO — DataHoraGeracao bruto: {data_ger_str!r} | interpretado: {data_ger!r}")

                if data_ger and data_ger > dt_fim:
                    continue  # já passou do período — ignora mas continua avançando NSU
                if data_ger and data_ger < dt_ini:
                    continue  # ainda não chegou no período pedido

                xml_b64 = item.get("ArquivoXml")
                if not xml_b64:
                    continue
                try:
                    xml_bytes = _decodificar_xml(xml_b64)
                    nota = _parsear_xml_bytes(xml_bytes)
                    nota["nsu"] = nsu_item
                    nota["chave_acesso"] = item.get("ChaveAcesso")
                    # Campo de data confiável (ISO, já validado acima) — usado
                    # pelo acervo pra refiltrar por período depois. O campo
                    # "data_emissao" vem de texto livre do XML (dhemi/demi) e
                    # não tem formato garantido, por isso não serve pra isso.
                    nota["data_geracao_nsu"] = data_ger.isoformat() if data_ger else None
                    # Dados completos + PDF (formato DANFSe) — feito aqui, na
                    # hora que temos o XML bruto em mãos, porque o acervo
                    # (usado pro relatório Excel) pode não preservar todos os
                    # campos extras necessários pro PDF completo.
                    if pasta_pdfs:
                        try:
                            from . import nfse_dados_completos as _ndc
                            from . import gerar_danfse_pdf as _gpdf
                            dados_completos = _ndc.extrair_dados_completos(
                                xml_bytes, chave_acesso=item.get("ChaveAcesso"), nsu=nsu_item)
                            os.makedirs(pasta_pdfs, exist_ok=True)
                            numero_pdf = dados_completos.get("numero") or f"nsu{nsu_item}"
                            caminho_pdf = os.path.join(pasta_pdfs, f"NFSE_{numero_pdf}.pdf".replace("/", "-"))
                            _gpdf.gerar_pdf_nota(dados_completos, caminho_pdf)
                        except Exception as ex_pdf:
                            _log(f"  AVISO: não foi possível gerar PDF do NSU {nsu_item}: {ex_pdf}")
                    resultados.append(nota)
                except Exception as ex:
                    _log(f"AVISO: erro ao decodificar/ler XML do NSU {nsu_item}: {ex}")

            # IMPORTANTE: a API trata o NSU informado como filtro EXCLUSIVO
            # ("documentos com NSU maior que este"), não inclusivo. Usar
            # maior_nsu_visto + 1 fazia a próxima chamada pular o documento
            # que estivesse bem em cima desse limite (achado ao investigar
            # uma nota perdida no módulo de Saída — mesmo bug, mesma causa).
            # Sem o +1, a próxima chamada pede a partir de maior_nsu_visto
            # mesmo, e a API já exclui esse valor sozinha — nenhum documento
            # é perdido nem repetido.
            nsu_atual = maior_nsu_visto
            _time.sleep(1.5)
            _prog(min(50 + len(resultados), 90), f"{len(resultados)} nota(s) no período")
            _log(f"  NSU processado até {maior_nsu_visto} — {len(resultados)} nota(s) no período até aqui.")

        if usar_checkpoint:
            _salvar_checkpoint(cnpj_limpo, maior_nsu_visto)

        sem_data_confiavel = sum(1 for n in resultados if not n.get("data_geracao_nsu"))
        if sem_data_confiavel:
            _log(f"AVISO DIAGNÓSTICO: {sem_data_confiavel} de {len(resultados)} nota(s) sem DataHoraGeracao válida (campo data_geracao_nsu vazio).")

    finally:
        for arq in (caminho_cert, caminho_key):
            try: os.remove(arq)
            except Exception: pass
        try: os.rmdir(pasta_temp_cert)
        except Exception: pass

    _log(f"Total de notas NFS-e encontradas no período: {len(resultados)}")
    return resultados


# ── Função principal (mesmo padrão do processar() do nfse_entrada.py) ────────
def processar(empresa: str, filial: str, data_inicio: str, data_fim: str,
              pasta_destino: str, pasta_db: str, ambiente: str = "producao",
              ignorar_checkpoint: bool = False,
              callback_log=None, callback_progresso=None) -> dict:
    """
    Função principal — mesmo formato de retorno do processar() de
    nfse_entrada.py, pra poder ser chamada do painel.py da mesma forma.

    pasta_db: pasta de rede compartilhada (mesma do banco de tarefas) onde
    fica o acervo permanente de notas (nfse_acervo.py) — necessária pra que
    qualquer usuário consiga reconstruir relatórios de períodos já buscados
    por qualquer outro usuário, mesmo sem o certificado digital.

    ignorar_checkpoint: se True, busca a partir do NSU 0 em vez de continuar
    do último checkpoint salvo — necessário pra reprocessar um período cujo
    NSU já foi ultrapassado (o checkpoint só anda pra frente).
    """
    import traceback

    def log(msg):
        if callback_log: callback_log(msg)

    def prog(pct, msg=""):
        if callback_progresso: callback_progresso(pct, msg)

    log("Iniciando apuração NFS-e de entrada (via API oficial ADN Contribuinte)")
    log(f"Empresa: {empresa} | Filial: {filial}")
    log(f"Período: {data_inicio} a {data_fim}")
    log(f"Ignorar checkpoint de NSU: {'SIM' if ignorar_checkpoint else 'não'}")
    log("─" * 56)

    try:
        cfg = _carregar_config_certificado(empresa, filial)
    except Exception as ex:
        return {"ok": False, "mensagem": str(ex)}

    pasta_pdfs = os.path.join(pasta_destino, "pdfs_temp")
    try:
        notas_raw = consultar_documentos_nsu(
            cnpj=cfg["cnpj"], pfx_path=cfg["pfx"], senha=cfg["senha"],
            data_inicio=data_inicio, data_fim=data_fim,
            ambiente=ambiente, log=log, prog=prog,
            usar_checkpoint=not ignorar_checkpoint,
            nsu_inicial=0 if ignorar_checkpoint else None,
            pasta_pdfs=pasta_pdfs,
        )
    except Exception as ex:
        traceback.print_exc()
        return {"ok": False, "mensagem": f"Erro na consulta à API: {ex}"}

    # Reaproveita a verificação de retenções e a geração do Excel já
    # existentes no nfse_entrada.py — mesma tabela LC 116, mesmo layout de
    # relatório, sem duplicar essa lógica.
    from . import nfse_entrada as _ne
    from . import nfse_acervo as _acervo

    if notas_raw:
        prog(90, "Analisando retenções")
        log(f"\nAnalisando retenções de {len(notas_raw)} nota(s) nova(s) da API...")

        notas_novas_analisadas = []
        sem_chave = 0
        for nota in notas_raw:
            resultado = _ne.verificar_retencoes(nota)
            # Garante que os campos usados pelo acervo sobrevivem, independente
            # de verificar_retencoes() preservar ou não o dict original —
            # sem isso, salvar_notas() descarta a nota silenciosamente.
            resultado["chave_acesso"] = nota.get("chave_acesso")
            resultado["nsu"] = nota.get("nsu")
            resultado["data_geracao_nsu"] = nota.get("data_geracao_nsu")
            resultado["prestador_cnpj"] = nota.get("prestador_cnpj")
            resultado["prestador_nome"] = nota.get("prestador_nome")
            if not resultado.get("chave_acesso"):
                sem_chave += 1
            notas_novas_analisadas.append(resultado)
            if resultado["alertas"]:
                log(f"  ⚠ NF {resultado['numero']}: {' | '.join(resultado['alertas'])}")
            else:
                log(f"  ✓ NF {resultado['numero']}: OK")

        if sem_chave:
            log(f"AVISO DIAGNÓSTICO: {sem_chave} de {len(notas_novas_analisadas)} nota(s) sem chave_acesso (não serão salvas no acervo).")

        resultado_gravacao = _acervo.salvar_notas(pasta_db, empresa, filial, cfg["cnpj"], notas_novas_analisadas)
        log(f"Acervo: {resultado_gravacao['gravadas']} nota(s) gravada(s), "
            f"{resultado_gravacao['ignoradas_sem_chave']} ignorada(s) por falta de chave_acesso.")
    else:
        log("Nenhuma nota nova na API para este período — verificando acervo já guardado...")

    # O relatório sempre é montado a partir do acervo completo do período —
    # não só das notas novas desta execução. Isso permite reprocessar um
    # período já varrido antes (mesmo que o cursor de NSU já tenha passado)
    # e permite que qualquer outro usuário, mesmo sem certificado, veja o
    # mesmo relatório a partir do acervo compartilhado.
    notas_analisadas = _acervo.buscar_periodo(pasta_db, empresa, filial, data_inicio, data_fim)

    if not notas_analisadas:
        return {"ok": False, "mensagem": "Nenhuma nota encontrada no período informado (nem na API, nem no acervo já guardado)."}

    # Corrige falsos positivos de retenção: fornecedor optante do Simples
    # Nacional já recolhe PIS/COFINS/CSLL (e, via de regra, também não sofre
    # retenção de IRRF) dentro do DAS — a tabela de códigos de serviço não
    # sabe disso, só o CNPJ do prestador revela o regime.
    from . import fornecedor_regime as _regime

    log("\nVerificando regime tributário dos fornecedores (Simples Nacional)...")
    cnpjs_prestadores = [n.get("prestador_cnpj") for n in notas_analisadas]
    regimes = _regime.obter_regime_lote(pasta_db, cnpjs_prestadores, log=log)

    qtd_simples = 0
    for nota in notas_analisadas:
        cnpj_p = _regime.cnpj_limpo(nota.get("prestador_cnpj"))
        info = regimes.get(cnpj_p)
        if info and info["opcao_simples"] is True:
            nota["regime_prestador"] = "SIMPLES_NACIONAL"
            nota["alertas"] = ["Prestador optante do Simples Nacional — retenção de IRRF/PIS/COFINS/CSLL não exigida."]
            nota["status_geral"] = "OK"
            qtd_simples += 1
        elif info and info["opcao_simples"] is False:
            nota["regime_prestador"] = "NORMAL"
            # mantém alertas originais — regras normais de retenção se aplicam
        else:
            nota["regime_prestador"] = "NAO_VERIFICADO"
            # mantém alertas originais, por segurança (não mascara divergência real)

    if qtd_simples:
        log(f"{qtd_simples} nota(s) de fornecedor(es) do Simples Nacional — alertas de retenção ajustados.")

    prog(95, "Gerando Excel")
    periodo = f"{data_inicio} a {data_fim}"
    caminho = _ne.gerar_relatorio_excel(
        notas_analisadas=notas_analisadas,
        cnpj_tomador=cfg["cnpj"],
        periodo=periodo,
        pasta_destino=pasta_destino,
        callback_log=callback_log,
    )

    # PDF de auditoria + PDF de apoio pra EFD-Reinf — a partir dos mesmos
    # dados já calculados acima, sem precisar consultar nada de novo.
    caminho_pdf_auditoria = None
    caminho_pdf_reinf = None
    try:
        from . import gerar_pdf_retencoes as _gpr
        periodo_arq = periodo.replace("/", "-")
        caminho_pdf_auditoria = os.path.join(pasta_destino, f"AUDITORIA_RETENCOES_{periodo_arq}.pdf")
        _gpr.gerar_pdf_auditoria_retencoes(notas_analisadas, cfg["cnpj"], periodo, caminho_pdf_auditoria)
        caminho_pdf_reinf = os.path.join(pasta_destino, f"REINF_APOIO_{periodo_arq}.pdf")
        _gpr.gerar_pdf_reinf(notas_analisadas, cfg["cnpj"], periodo, caminho_pdf_reinf)
        log(f"  PDF de auditoria: {os.path.basename(caminho_pdf_auditoria)}")
        log(f"  PDF de apoio à Reinf: {os.path.basename(caminho_pdf_reinf)}")
    except Exception as ex_pdf:
        log(f"  AVISO: não foi possível gerar os PDFs de retenção: {ex_pdf}")

    total_div = sum(1 for n in notas_analisadas if n.get("status_geral") != "OK")

    # Empacota os PDFs gerados nesta execução (se houver) num único ZIP.
    caminho_pdfs_zip = None
    if os.path.isdir(pasta_pdfs) and os.listdir(pasta_pdfs):
        try:
            import zipfile
            caminho_pdfs_zip = os.path.join(pasta_destino, f"NFSE_ENTRADA_PDFS_{periodo}.zip".replace("/", "-"))
            with zipfile.ZipFile(caminho_pdfs_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for nome_arq in os.listdir(pasta_pdfs):
                    zf.write(os.path.join(pasta_pdfs, nome_arq), arcname=nome_arq)
            log(f"  PDFs (lote): {os.path.basename(caminho_pdfs_zip)} ({len(os.listdir(pasta_pdfs))} arquivo(s))")
            import shutil
            shutil.rmtree(pasta_pdfs, ignore_errors=True)
        except Exception as ex_zip:
            log(f"  AVISO: não foi possível empacotar os PDFs em ZIP: {ex_zip}")

    prog(100, "Concluído")
    log(f"\n{'─'*56}")
    log(f"  Total de notas: {len(notas_analisadas)}")
    log(f"  Com divergência: {total_div}")
    log(f"  Relatório: {os.path.basename(caminho)}")
    log(f"{'─'*56}")

    return {
        "ok": True,
        "caminho_relatorio": caminho,
        "caminho_pdfs_zip": caminho_pdfs_zip,
        "caminho_pdf_auditoria": caminho_pdf_auditoria,
        "caminho_pdf_reinf": caminho_pdf_reinf,
        "total_notas": len(notas_analisadas),
        "notas_divergentes": total_div,
        "notas": notas_analisadas,
        "mensagem": f"{len(notas_analisadas)} nota(s) processada(s). {total_div} com divergência.",
    }
