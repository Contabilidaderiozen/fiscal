"""
Router de Análise Fiscal — NFS-e Entrada e NFS-e Saída.

Só expõe via HTTP o que já existe e já foi validado contra produção em
logic/nfse_adn_api.py e logic/nfse_saida_api.py — este arquivo não
reimplementa nenhuma regra fiscal, só orquestra upload→processar→download.

Como cada consulta pode gerar de 1 a 4 arquivos (relatório Excel, PDFs em
lote, PDF de auditoria, PDF de apoio à Reinf), o padrão aqui é: o POST
devolve um "token" de sessão + quais arquivos ficaram disponíveis; cada
arquivo é baixado depois por um GET separado usando esse token — assim a
tela consegue reproduzir os múltiplos botões de download do EXE (Abrir
Relatório / Baixar PDFs / PDF de Auditoria / PDF para Reinf) em vez de
forçar tudo num download só.

⚠️ Sem streaming de log ao vivo (isso exigiria SSE/WebSocket) — mesmo
padrão simplificado já usado nos outros módulos desta sessão: o log
inteiro chega de uma vez, junto com o resultado final.
"""
import os
import tempfile
import time
import traceback
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse

import auth
import db
from logic import nfse_adn_api, nfse_saida_api

router = APIRouter(prefix="/api/nfse", tags=["nfse"])

# Mesmas filiais/certificados já configurados em certificados/senhas.json
# (conferido nesta mesma conversa) — usado só pra montar os seletores da
# tela, a fonte de verdade de credencial continua sendo aquele arquivo.
FILIAIS = {
    "Toyota": ["PILARES", "TIJUCA", "CAMPO GRANDE", "BARRA - JARDIM OCEANICO",
               "JACAREPAGUA WP", "LEXUS", "ALVORADA", "RECREIO"],
    "BYD": ["JACAREPAGUA", "CAMPO GRANDE", "SAO JOAO DE MERITI", "BARRA MANSA"],
    "Riozen": ["INTERMEDIACAO"],
}

# Sessões de resultado em memória: token -> {"criado_em": ts, "arquivos": {tipo: caminho}}
# Pruned de forma preguiçosa (a cada novo POST) — suficiente pra um time
# pequeno usando isso, sem precisar de outro banco só pra isso.
_SESSOES = {}
_SESSAO_TTL_SEG = 3 * 60 * 60  # 3 horas


def _pasta_db_compartilhada() -> str:
    return os.path.dirname(db.CAMINHO_DB)


def _limpar_sessoes_antigas():
    agora = time.time()
    expiradas = [tok for tok, s in _SESSOES.items() if agora - s["criado_em"] > _SESSAO_TTL_SEG]
    for tok in expiradas:
        _SESSOES.pop(tok, None)


def _nova_sessao(arquivos: dict) -> str:
    _limpar_sessoes_antigas()
    token = uuid.uuid4().hex
    _SESSOES[token] = {"criado_em": time.time(), "arquivos": arquivos}
    return token


@router.get("/filiais")
def listar_filiais(usuario: dict = Depends(auth.usuario_atual)):
    return FILIAIS


@router.post("/entrada/consultar")
def consultar_entrada(
    empresa: str = Form(...),
    filial: str = Form(...),
    data_inicio: str = Form(...),   # DD/MM/AAAA
    data_fim: str = Form(...),
    ambiente: str = Form("producao"),
    ignorar_checkpoint: bool = Form(False),
    usuario: dict = Depends(auth.usuario_atual),
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="nfse_entrada_")
    try:
        resultado = nfse_adn_api.processar(
            empresa=empresa, filial=filial,
            data_inicio=data_inicio, data_fim=data_fim,
            pasta_destino=tmp_dir, pasta_db=_pasta_db_compartilhada(),
            ambiente=ambiente, ignorar_checkpoint=ignorar_checkpoint,
            callback_log=log,
        )
    except Exception:
        return JSONResponse(status_code=500, content={
            "ok": False, "mensagem": "Erro inesperado ao consultar.",
            "logs": logs, "traceback": traceback.format_exc(),
        })

    if not resultado.get("ok"):
        return JSONResponse(status_code=200, content={**resultado, "logs": logs})

    arquivos = {}
    if resultado.get("caminho_relatorio"):
        arquivos["relatorio"] = resultado["caminho_relatorio"]
    if resultado.get("caminho_pdfs_zip"):
        arquivos["pdfs_zip"] = resultado["caminho_pdfs_zip"]
    if resultado.get("caminho_pdf_auditoria"):
        arquivos["pdf_auditoria"] = resultado["caminho_pdf_auditoria"]
    if resultado.get("caminho_pdf_reinf"):
        arquivos["pdf_reinf"] = resultado["caminho_pdf_reinf"]

    token = _nova_sessao(arquivos)

    return {
        "ok": True,
        "mensagem": resultado.get("mensagem"),
        "total_notas": resultado.get("total_notas"),
        "notas_divergentes": resultado.get("notas_divergentes"),
        "logs": logs,
        "token": token,
        "arquivos_disponiveis": list(arquivos.keys()),
    }


@router.post("/saida/consultar")
def consultar_saida(
    empresa: str = Form(...),
    filial: str = Form(...),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    ambiente: str = Form("producao"),
    ignorar_checkpoint: bool = Form(False),
    usuario: dict = Depends(auth.usuario_atual),
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="nfse_saida_")
    try:
        resultado = nfse_saida_api.processar(
            empresa=empresa, filial=filial,
            data_inicio=data_inicio, data_fim=data_fim,
            pasta_destino=tmp_dir,
            ambiente=ambiente, ignorar_checkpoint=ignorar_checkpoint,
            callback_log=log,
        )
    except Exception:
        return JSONResponse(status_code=500, content={
            "ok": False, "mensagem": "Erro inesperado ao consultar.",
            "logs": logs, "traceback": traceback.format_exc(),
        })

    if not resultado.get("ok"):
        return JSONResponse(status_code=200, content={**resultado, "logs": logs})

    arquivos = {}
    if resultado.get("caminho_relatorio"):
        arquivos["relatorio"] = resultado["caminho_relatorio"]
    token = _nova_sessao(arquivos)

    return {
        "ok": True,
        "mensagem": resultado.get("mensagem"),
        "total_notas": resultado.get("total_notas"),
        "notas_divergentes": resultado.get("notas_divergentes"),
        "total_ativas": resultado.get("total_ativas"),
        "total_canceladas": resultado.get("total_canceladas"),
        "aliquota_mais_comum": resultado.get("aliquota_mais_comum"),
        "iss_total_periodo": resultado.get("iss_total_periodo"),
        "logs": logs,
        "token": token,
        "arquivos_disponiveis": list(arquivos.keys()),
    }


@router.get("/download/{token}/{tipo}")
def baixar_arquivo(token: str, tipo: str, usuario: dict = Depends(auth.usuario_atual)):
    sessao = _SESSOES.get(token)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão expirada ou inexistente — refaça a consulta.")
    caminho = sessao["arquivos"].get(tipo)
    if not caminho or not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail=f"Arquivo '{tipo}' não disponível nesta consulta.")
    return FileResponse(caminho, filename=os.path.basename(caminho))
