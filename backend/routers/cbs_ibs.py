"""
Router do módulo CBS/IBS — Fiscal > Apuração > CBS/IBS.

Endpoint único (mais simples que o PIS/COFINS, já que aqui não tem
seção fixa nem mix de fornecedores ainda — deferido pra quando o
cadastro de Clientes/Fornecedores estiver pronto): recebe as planilhas
de Saída e Entrada, o período e as duas alíquotas, e devolve o Excel de
3 abas (Débito, Crédito, Apuração).
"""
import os
import shutil
import tempfile
import traceback
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse

import auth
from logic import cbs_ibs as _cbs_ibs

router = APIRouter(prefix="/api/cbs-ibs", tags=["cbs-ibs"])


def _salvar_temp(upload: UploadFile, destino_dir: str) -> str:
    caminho = os.path.join(destino_dir, upload.filename)
    with open(caminho, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return caminho


@router.get("/referencia")
def referencia(usuario: dict = Depends(auth.usuario_atual)):
    """Alíquotas combinadas já confirmadas por ano — a tela usa isso
    pra pré-preencher os campos de Débito/Crédito (ainda editáveis)."""
    return {"aliquotas_por_ano": {ano: dados["cbs"] + dados["ibs"] for ano, dados in _cbs_ibs.ALIQUOTAS_ANO.items()}}


@router.post("/apurar")
async def apurar_cbs_ibs(
    periodo: str = Form(...),          # "MM/AAAA"
    ano: int = Form(...),
    aliq_debito: float = Form(...),    # fração, ex: 0.085
    aliq_credito: float = Form(...),
    planilhas_saida: List[UploadFile] = File(...),
    planilhas_entrada: List[UploadFile] = File(...),
    usuario: dict = Depends(auth.usuario_atual),
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="cbs_ibs_")
    try:
        saida_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_saida]
        entrada_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_entrada]

        resultado = _cbs_ibs.apurar(
            arquivos_saida=saida_paths,
            arquivos_entrada=entrada_paths,
            ano=ano,
            aliq_debito=aliq_debito,
            aliq_credito=aliq_credito,
            log=log,
        )

        periodo_arquivo = periodo.replace("/", "")
        arquivo_saida = os.path.join(tmp_dir, f"APURACAO_CBS_IBS_{periodo_arquivo}.xlsx")
        _cbs_ibs.gerar_relatorio(resultado, ano, periodo, arquivo_saida)

        import json, base64
        log_b64 = base64.b64encode(json.dumps(logs, ensure_ascii=False).encode("utf-8")).decode("ascii")

        return FileResponse(
            arquivo_saida,
            filename=os.path.basename(arquivo_saida),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "X-Log-B64": log_b64,
                "X-Valor-Apurado": repr(resultado["valor_apurado"]),
                "Access-Control-Expose-Headers": "X-Log-B64, X-Valor-Apurado",
            },
        )

    except _cbs_ibs.AliquotaIndisponivelError as e:
        return JSONResponse(status_code=422, content={"erro": str(e), "logs": logs})
    except Exception:
        return JSONResponse(status_code=500, content={
            "erro": "Falha ao apurar CBS/IBS", "logs": logs, "traceback": traceback.format_exc(),
        })
