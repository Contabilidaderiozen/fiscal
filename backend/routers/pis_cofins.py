"""
Router PIS/COFINS — Débitos, Créditos e Apuração.

Fluxo pela tela (3 chamadas em sequência, não uma só):
  1. POST /api/pis-cofins/debitos    -> devolve o arquivo + o % proporcional
     no header 'X-Pct-Proporcional' (a tela guarda esse número).
  2. POST /api/pis-cofins/creditos   -> recebe esse % de volta no campo
     'pct_proporcional' do form, junto com os arquivos de crédito.
  3. POST /api/pis-cofins/apuracao   -> recebe os arquivos processados de
     Débitos e Créditos (as saídas dos passos 1 e 2) e gera a apuração final.
"""
import os
import shutil
import tempfile
import traceback
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api/pis-cofins", tags=["pis-cofins"])

# ─── Modelos fixos por empresa (residem no servidor) ────────────────────
# Este arquivo (pis_cofins.py) mora em backend\routers\, mas os modelos
# ficam em backend\logic\pis_cofins_modelos\ — por isso o caminho sobe um
# nível (..) antes de entrar em logic\.
_DIR_ATUAL = os.path.dirname(os.path.abspath(__file__))
_MODELOS_DIR = os.path.normpath(os.path.join(_DIR_ATUAL, "..", "logic", "pis_cofins_modelos"))

MODELOS_DEBITO = {
    "BYD":    os.path.join(_MODELOS_DIR, "DEBITOS_BYD.xls"),
    "TOYOTA": os.path.join(_MODELOS_DIR, "DEBITOS_TOYOTA.xls"),
}
MODELOS_CREDITO = {
    "BYD":    os.path.join(_MODELOS_DIR, "CREDITOS_UNIFICADO_BYD.xlsx"),
    "TOYOTA": os.path.join(_MODELOS_DIR, "CREDITOS_UNIFICADO_TOYOTA.xlsx"),
}
# ATENÇÃO: hoje só existe um modelo de apuração (MODELO_APURACAO.xlsx),
# sem distinção por empresa. Assumindo o mesmo modelo pras duas — se BYD
# e Toyota precisarem de modelos de apuração diferentes no futuro, é só
# colocar dois arquivos aqui como nos outros dois dicionários acima.
MODELO_APURACAO_PADRAO = os.path.join(_MODELOS_DIR, "MODELO_APURACAO.xlsx")


def _salvar_temp(upload: UploadFile, destino_dir: str) -> str:
    caminho = os.path.join(destino_dir, upload.filename)
    with open(caminho, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return caminho


def _erro(msg, logs, status=500, tb=None):
    content = {"erro": msg, "logs": logs}
    if tb:
        content["traceback"] = tb
    return JSONResponse(status_code=status, content=content)


def _headers_com_log(logs, extras=None):
    """HTTP headers não podem ter quebra de linha, então o log (que tem
    várias linhas) vai como JSON + base64 num header próprio — a tela lê
    e decodifica pra mostrar, mesmo numa resposta que é um arquivo
    binário pra download (não um JSON)."""
    import json, base64
    log_b64 = base64.b64encode(json.dumps(logs, ensure_ascii=False).encode("utf-8")).decode("ascii")
    headers = {"X-Log-B64": log_b64}
    if extras:
        headers.update(extras)
    headers["Access-Control-Expose-Headers"] = ", ".join(headers.keys())
    return headers


# ══════════════════════════════════════════════════════════════════════
# 1. DÉBITOS
# ══════════════════════════════════════════════════════════════════════
@router.post("/debitos")
async def apurar_debitos(
    empresa: str = Form(...),
    periodo: str = Form(...),
    planilhas_debito: List[UploadFile] = File(...),
    balancete: UploadFile = File(...),
    arquivo_170: Optional[UploadFile] = File(None),
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="pis_cofins_deb_")
    try:
        empresa_key = empresa.strip().upper()
        modelo = MODELOS_DEBITO.get(empresa_key)
        if not modelo or not os.path.exists(modelo):
            return _erro(f"Modelo de débitos não encontrado para empresa '{empresa}'.", logs, 400)

        xls_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_debito]
        balancete_path = _salvar_temp(balancete, tmp_dir)
        arquivo170_path = _salvar_temp(arquivo_170, tmp_dir) if arquivo_170 else None

        periodo_arquivo = periodo.replace("/", "")
        saida_path = os.path.join(tmp_dir, f"DEBITOS_PROCESSADO_{periodo_arquivo}.xlsx")

        try:
            from logic import pis_cofins_debitos as _deb
        except Exception:
            return _erro("ImportError ao carregar pis_cofins_debitos", logs, 500, traceback.format_exc())

        resultado = _deb.processar_debitos(
            xls_files=xls_paths,
            modelo=modelo,
            balancete=balancete_path,
            arquivo170=arquivo170_path,
            saida=saida_path,
            log=log,
        )

        return FileResponse(
            resultado["arquivo"],
            filename=os.path.basename(resultado["arquivo"]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=_headers_com_log(logs, {
                "X-Pct-Proporcional": repr(resultado["pct_proporcional"]),
                "X-Fat-Bruto-Total": repr(resultado["fat_bruto_total"]),
                "X-Valor-Veiculo-Usado": repr(resultado["valor_veiculo_usado"]),
            }),
        )

    except Exception:
        return _erro("Falha ao processar débitos", logs, 500, traceback.format_exc())


# ══════════════════════════════════════════════════════════════════════
# 2. CRÉDITOS
# ══════════════════════════════════════════════════════════════════════
@router.post("/creditos")
async def apurar_creditos(
    empresa: str = Form(...),
    periodo: str = Form(...),
    pct_proporcional: float = Form(...),   # veio do header X-Pct-Proporcional da etapa de Débitos
    planilhas_credito: List[UploadFile] = File(...),
    balancete: UploadFile = File(...),
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="pis_cofins_cred_")
    try:
        empresa_key = empresa.strip().upper()
        modelo = MODELOS_CREDITO.get(empresa_key)
        if not modelo or not os.path.exists(modelo):
            return _erro(f"Modelo de créditos não encontrado para empresa '{empresa}'.", logs, 400)

        xls_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_credito]
        balancete_path = _salvar_temp(balancete, tmp_dir)

        periodo_arquivo = periodo.replace("/", "")
        saida_path = os.path.join(tmp_dir, f"CREDITOS_PROCESSADO_{periodo_arquivo}.xlsx")

        try:
            from logic import pis_cofins_creditos as _cred
        except Exception:
            return _erro("ImportError ao carregar pis_cofins_creditos", logs, 500, traceback.format_exc())

        arquivo = _cred.processar_creditos(
            xls_files=xls_paths,
            modelo=modelo,
            balancete=balancete_path,
            pct_proporcional=pct_proporcional,
            saida=saida_path,
            log=log,
        )

        return FileResponse(
            arquivo,
            filename=os.path.basename(arquivo),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=_headers_com_log(logs),
        )

    except Exception:
        return _erro("Falha ao processar créditos", logs, 500, traceback.format_exc())


# ══════════════════════════════════════════════════════════════════════
# 3. APURAÇÃO
# ══════════════════════════════════════════════════════════════════════
_MESES_PT = ["", "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
             "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]


@router.post("/apuracao")
async def gerar_apuracao(
    empresa: str = Form(...),
    periodo: str = Form(...),   # "MM/AAAA"
    arquivo_debitos: UploadFile = File(...),    # saída da etapa 1 (Débitos)
    arquivo_creditos: UploadFile = File(...),   # saída da etapa 2 (Créditos)
):
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="pis_cofins_apu_")
    try:
        modelo = MODELO_APURACAO_PADRAO
        if not os.path.exists(modelo):
            return _erro("Modelo de apuração não encontrado no servidor.", logs, 400)

        deb_path = _salvar_temp(arquivo_debitos, tmp_dir)
        cred_path = _salvar_temp(arquivo_creditos, tmp_dir)

        try:
            mes_num = int(periodo.split("/")[0])
            mes_ref = _MESES_PT[mes_num]
        except Exception:
            mes_ref = periodo  # fallback: usa o texto cru se não conseguir parsear

        periodo_arquivo = periodo.replace("/", "")
        saida_path = os.path.join(tmp_dir, f"APURACAO_{periodo_arquivo}.xlsx")

        try:
            from logic import pis_cofins_apuracao as _apu
        except Exception:
            return _erro("ImportError ao carregar pis_cofins_apuracao", logs, 500, traceback.format_exc())

        arquivo = _apu.processar_apuracao(
            arq_debitos=deb_path,
            arq_creditos=cred_path,
            modelo=modelo,
            mes_referencia=mes_ref,
            saida=saida_path,
            log=log,
        )

        return FileResponse(
            arquivo,
            filename=os.path.basename(arquivo),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=_headers_com_log(logs),
        )

    except Exception:
        return _erro("Falha ao gerar apuração", logs, 500, traceback.format_exc())
