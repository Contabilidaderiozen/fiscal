"""
Apuracao de ICMS — le o Livro Fiscal (PDF) e calcula ICMS/FECP a pagar
usando a mesma logica do desktop (logic/icms_apuracao.py, portado sem
alteracao nenhuma na formula).
"""

import os
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException

import auth
from logic.icms_apuracao import apurar_icms
from logic.livro_proprio import (
    montar_e_comparar, extrair_notas_entrada, extrair_notas_saida,
    cruzar_com_sefaz, buscar_detalhe_divergentes,
)

router = APIRouter()


@router.post("/api/icms/apurar")
async def apurar(
    pdf: UploadFile = File(...),
    grupo: str = Form(""),
    filial: str = Form(""),
    periodo: str = Form(""),
    usuario: dict = Depends(auth.usuario_atual),
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF (Livro Fiscal de ICMS).")

    conteudo = await pdf.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    logs = []

    def coletar_log(msg):
        logs.append(str(msg))

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(conteudo)
            tmp_path = tmp.name

        res = apurar_icms(tmp_path, callback_log=coletar_log)

        return {
            "ok": True,
            "logs": logs,
            "grupo": grupo,
            "filial": filial,
            "periodo_selecionado": periodo,
            "resultado": {
                "empresa": res.empresa,
                "cnpj": res.cnpj,
                "insc_est": res.insc_est,
                "periodo": res.periodo,
                "fecp_base": res.fecp_base,
                "fecp": res.fecp,
                "fecp_no_nbs": res.fecp_no_nbs,
                "icms_013": res.icms_013,
                "total_applied": res.total_applied,
                "total_not_yet": res.total_not_yet,
                "icms_guia_nbs": res.icms_guia_nbs,
                "fecp_guia_nbs": res.fecp_guia_nbs,
                "icms_a_pagar": res.icms_a_pagar,
                "fecp_a_pagar": res.fecp_a_pagar,
                "tudo_correto_nbs": res.tudo_correto_nbs,
                "observacoes": res.observacoes,
            },
        }
    except Exception as ex:
        return {"ok": False, "logs": logs, "erro": str(ex)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/api/icms/apurar-completo")
async def apurar_completo(
    fiscal: UploadFile = File(..., description="Livro Fiscal (apuração) — mesmo PDF do endpoint /apurar"),
    entrada: UploadFile = File(..., description="Registro de Entradas (livro detalhado, nota a nota)"),
    saida: UploadFile = File(..., description="Registro de Saídas (livro detalhado, nota a nota)"),
    grupo: str = Form(""),
    filial: str = Form(""),
    periodo: str = Form(""),
    usuario: dict = Depends(auth.usuario_atual),
):
    """
    Apuração completa: lê os 3 livros (Fiscal, Entrada, Saída), calcula o
    ICMS/FECP a pagar (mesma fórmula validada do endpoint /apurar) E
    reconstrói um livro próprio a partir das notas individuais de Entrada
    (crédito) e Saída (débito), comparando nota a nota com o Livro Fiscal
    oficial gerado pelo NBS.
    """
    for arq, nome in [(fiscal, "Livro Fiscal"), (entrada, "Livro de Entrada"), (saida, "Livro de Saída")]:
        if not arq.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Envie um PDF válido para {nome}.")

    logs = []

    def coletar_log(msg):
        logs.append(str(msg))

    tmp_paths = {}
    try:
        for chave, arq in [("fiscal", fiscal), ("entrada", entrada), ("saida", saida)]:
            conteudo = await arq.read()
            if not conteudo:
                raise HTTPException(status_code=400, detail=f"Arquivo vazio: {arq.filename}")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(conteudo)
                tmp_paths[chave] = tmp.name

        res_nbs = apurar_icms(tmp_paths["fiscal"], callback_log=coletar_log)
        rel = montar_e_comparar(tmp_paths["entrada"], tmp_paths["saida"], res_nbs, callback_log=coletar_log)

        return {
            "ok": True,
            "logs": logs,
            "grupo": grupo,
            "filial": filial,
            "periodo_selecionado": periodo,
            "resultado": {
                "empresa": res_nbs.empresa,
                "cnpj": res_nbs.cnpj,
                "insc_est": res_nbs.insc_est,
                "periodo": res_nbs.periodo,
                "fecp_base": res_nbs.fecp_base,
                "fecp": res_nbs.fecp,
                "fecp_no_nbs": res_nbs.fecp_no_nbs,
                "icms_013": res_nbs.icms_013,
                "total_applied": res_nbs.total_applied,
                "total_not_yet": res_nbs.total_not_yet,
                "icms_guia_nbs": res_nbs.icms_guia_nbs,
                "fecp_guia_nbs": res_nbs.fecp_guia_nbs,
                "icms_a_pagar": res_nbs.icms_a_pagar,
                "fecp_a_pagar": res_nbs.fecp_a_pagar,
                "tudo_correto_nbs": res_nbs.tudo_correto_nbs,
                "observacoes": res_nbs.observacoes,
            },
            "livro_proprio": {
                "qtd_notas_entrada": len(rel.notas_entrada),
                "qtd_notas_saida": len(rel.notas_saida),
                "totais_entrada": rel.totais_entrada,
                "totais_saida": rel.totais_saida,
                "comparacao_entrada": rel.comparacao_entrada,
                "comparacao_saida": rel.comparacao_saida,
                "divergente": rel.divergente,
                "anomalias": rel.anomalias,
            },
        }
    except HTTPException:
        raise
    except Exception as ex:
        return {"ok": False, "logs": logs, "erro": str(ex)}
    finally:
        for p in tmp_paths.values():
            if p and os.path.exists(p):
                os.remove(p)


@router.post("/api/icms/conferir-sefaz")
async def conferir_sefaz(
    entrada: UploadFile = File(..., description="Registro de Entradas (livro detalhado, nota a nota)"),
    saida: UploadFile = File(..., description="Registro de Saídas (livro detalhado, nota a nota)"),
    empresa: str = Form(..., description="Ex.: 'BYD' — chave usada em certificados/senhas.json"),
    filial: str = Form(..., description="Ex.: 'JACAREPAGUA' — chave usada em certificados/senhas.json"),
    data_inicio: str = Form(..., description="dd/mm/aaaa"),
    data_fim: str = Form(..., description="dd/mm/aaaa"),
    ambiente: str = Form("producao"),
    buscar_detalhe: bool = Form(True, description="Se True, busca XML completo das notas divergentes (sob demanda)"),
    usuario: dict = Depends(auth.usuario_atual),
):
    """
    Cruza o Livro de Entrada/Saída (PDF) contra o resumo de notas que a
    SEFAZ tem registrado pro CNPJ da empresa/filial no período (via
    NFeDistribuicaoDFe — NT 2014.002). Detecta nota faltante, nota
    "fantasma" (SEFAZ tem, PDF não) e divergência de valor total.

    Requer certificado digital configurado em certificados/senhas.json
    (mesmo arquivo já usado pelo NFS-e) para a chave "{empresa}|{filial}".

    ⚠️ Esta chamada NÃO foi testada contra a SEFAZ real (sem certificado
    nem rede disponíveis no ambiente onde foi escrita) — ver aviso
    detalhado no topo de logic/nfe_distribuicao.py.
    """
    for arq, nome in [(entrada, "Livro de Entrada"), (saida, "Livro de Saída")]:
        if not arq.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Envie um PDF válido para {nome}.")

    logs = []

    def coletar_log(msg):
        logs.append(str(msg))

    tmp_paths = {}
    try:
        # Import feito AQUI DENTRO (não no topo do arquivo) de propósito —
        # se nfe_distribuicao.py ou nfse_adn_api.py tiverem qualquer
        # problema (import faltando, erro de sintaxe em módulo importado
        # por eles etc.), isso vira um erro JSON explicável em vez de um
        # 500 cru sem detalhe nenhum.
        import logic.nfe_distribuicao as nfe_dist
        import logic.nfse_adn_api as nfse_api

        for chave, arq in [("entrada", entrada), ("saida", saida)]:
            conteudo = await arq.read()
            if not conteudo:
                raise HTTPException(status_code=400, detail=f"Arquivo vazio: {arq.filename}")
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(conteudo)
                tmp_paths[chave] = tmp.name

        coletar_log("Lendo Livro de Entrada/Saída em PDF...")
        notas_entrada = extrair_notas_entrada(tmp_paths["entrada"], callback_log=coletar_log)
        notas_saida = extrair_notas_saida(tmp_paths["saida"], callback_log=coletar_log)

        coletar_log("Consultando resumo de notas na SEFAZ (NFeDistribuicaoDFe)...")
        try:
            resumo_sefaz = nfe_dist.consultar_resumo_periodo(
                empresa=empresa, filial=filial,
                data_inicio=data_inicio, data_fim=data_fim,
                ambiente=ambiente, log=coletar_log,
            )
        except nfe_dist.ErroConsumoIndevido as ex:
            return {"ok": False, "logs": logs, "erro": f"SEFAZ bloqueou por consumo indevido: {ex}"}

        if not resumo_sefaz["ok"]:
            return {"ok": False, "logs": logs, "erro": resumo_sefaz.get("erro") or "Falha ao consultar SEFAZ."}

        # Precisamos do CNPJ da própria empresa/filial pra saber quem é "nós"
        # no cruzamento (distinguir nota que emitimos de nota que recebemos).
        cfg_cert = nfse_api._carregar_config_certificado(empresa, filial)
        nosso_cnpj = cfg_cert["cnpj"]

        cruzamento = cruzar_com_sefaz(
            notas_entrada, notas_saida, resumo_sefaz["notas"], nosso_cnpj,
            callback_log=coletar_log,
        )

        detalhes_divergentes = {}
        if buscar_detalhe and (cruzamento["divergencias_entrada"] or cruzamento["divergencias_saida"]):
            coletar_log("Buscando XML completo (CFOP/ICMS) só das notas divergentes...")
            detalhes_divergentes = buscar_detalhe_divergentes(
                cruzamento["divergencias_entrada"], cruzamento["divergencias_saida"],
                empresa, filial, ambiente=ambiente, callback_log=coletar_log,
            )

        return {
            "ok": True,
            "logs": logs,
            "periodo": f"{data_inicio} a {data_fim}",
            "total_notas_pdf_entrada": len(notas_entrada),
            "total_notas_pdf_saida": len(notas_saida),
            "total_resumos_sefaz": cruzamento["total_resumos_sefaz"],
            "divergencias_entrada": cruzamento["divergencias_entrada"],
            "divergencias_saida": cruzamento["divergencias_saida"],
            "notas_pdf_nao_confirmadas_sefaz": cruzamento["notas_pdf_nao_confirmadas_sefaz"],
            "detalhes_divergentes": detalhes_divergentes,
        }
    except HTTPException:
        raise
    except Exception as ex:
        import traceback
        tb = traceback.format_exc()
        logs.append("─" * 40)
        logs.append("ERRO — traceback completo:")
        logs.append(tb)
        return {"ok": False, "logs": logs, "erro": str(ex)}
    finally:
        for p in tmp_paths.values():
            if p and os.path.exists(p):
                os.remove(p)
