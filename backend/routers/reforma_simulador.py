"""
Router do Simulador IBS/CBS — versão de entrada manual (sliders), sem
cruzamento automático via NBS ainda (isso fica pra quando o problema do
CNPJ de fornecedor/cliente for resolvido).

Regime Geral e Simples fora da DAS já funcionam de ponta a ponta (só
dependem da alíquota do Regime Geral, que já temos). Simples DAS depende
da tabela do Anexo XVIII (5 Anexos × 7 anos) — enquanto ela não estiver
carregada em tabela_simples_anexos.json, o endpoint devolve um erro
específico e claro em vez de calcular com dado inventado.
"""
import os
import shutil
import tempfile
import traceback
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

import auth
from logic import reforma_tributaria_simulador as sim

router = APIRouter(prefix="/api/reforma-simulador", tags=["reforma-simulador"])


class SimulacaoBody(BaseModel):
    regime: str  # "regime_geral" | "simples_das" | "simples_fora_das"
    ano: int
    aliq_geral: float  # já vem como fração (0.0921), não porcentagem (9.21)
    faturamento_12m: float
    pct_desp: float
    pct_forn_das: float
    pct_cli_com_credito: float  # % "mix real" informado nas etapas — os
                                 # cenários 0% e 100% são calculados à parte
    anexo: Optional[str] = None  # obrigatório só se regime == "simples_das"


def _rodar_regime(body: SimulacaoBody, pct_cli_override: float):
    premissa_credito_das = sim.PREMISSA_CREDITO_DAS_POR_ANO.get(body.ano)
    if premissa_credito_das is None:
        raise HTTPException(
            status_code=400,
            detail=f"Não há premissa de crédito presumido (Simples DAS) cadastrada para o ano {body.ano}.",
        )

    if body.regime == "regime_geral":
        return sim.simular_regime_geral(
            body.aliq_geral, body.pct_desp, body.pct_forn_das, premissa_credito_das, pct_cli_override
        )
    if body.regime == "simples_fora_das":
        return sim.simular_simples_fora_das(
            body.aliq_geral, body.pct_desp, body.pct_forn_das, premissa_credito_das, pct_cli_override
        )
    if body.regime == "simples_das":
        if not body.anexo:
            raise HTTPException(status_code=400, detail="Informe o Anexo do Simples Nacional.")
        try:
            return sim.simular_simples_das(
                body.anexo, body.faturamento_12m, body.ano, body.pct_desp, body.pct_forn_das,
                body.aliq_geral, premissa_credito_das, pct_cli_override,
            )
        except sim.DadosInsuficientesError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except ValueError as e:
            # ex: faturamento acima do limite do Simples
            raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=400, detail=f"Regime inválido: {body.regime!r}")


def _serializar(resultado, fator_escala=None):
    base = {
        "preco_inicial": resultado.preco_inicial,
        "credito_entrada": resultado.credito_entrada,
        "base_apos_credito": resultado.base_apos_credito,
        "ibs_cbs_devido": resultado.ibs_cbs_devido,
        "credito_cliente": resultado.credito_cliente,
        "preco_venda": resultado.preco_venda,
        "custo_liquido_cliente": resultado.custo_liquido_cliente,
        "memoria_calculo": resultado.memoria_calculo,
    }
    if fator_escala:
        base["valores_reais"] = {
            "faturamento_base": round(100 * fator_escala, 2),
            "credito_entrada": round(resultado.credito_entrada * fator_escala, 2),
            "ibs_cbs_devido": round(resultado.ibs_cbs_devido * fator_escala, 2),
            "credito_cliente": round(resultado.credito_cliente * fator_escala, 2),
            "preco_venda": round(resultado.preco_venda * fator_escala, 2),
            "custo_liquido_cliente": round(resultado.custo_liquido_cliente * fator_escala, 2),
        }
    return base


@router.post("/simular")
def simular(body: SimulacaoBody, usuario: dict = Depends(auth.usuario_atual)):
    if body.faturamento_12m > sim.FATURAMENTO_LIMITE_SIMPLES and body.regime == "simples_das":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Faturamento de R$ {body.faturamento_12m:,.2f} ultrapassa o limite do Simples "
                f"(R$ {sim.FATURAMENTO_LIMITE_SIMPLES:,.2f}) — a empresa não pode ficar no DAS, "
                f"mas ainda pode simular 'Simples fora da DAS' ou 'Regime Geral'."
            ),
        )

    try:
        cenario_0 = _rodar_regime(body, 0.0)
        cenario_real = _rodar_regime(body, body.pct_cli_com_credito)
        cenario_100 = _rodar_regime(body, 1.0)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail=f"Erro inesperado ao simular: {traceback.format_exc()}")

    fator_escala = (body.faturamento_12m / 100) if body.faturamento_12m else None

    resposta = {
        "ok": True,
        "faturamento_usado": body.faturamento_12m,
        "cenarios": {
            "0": _serializar(cenario_0, fator_escala),
            "real": _serializar(cenario_real, fator_escala),
            "100": _serializar(cenario_100, fator_escala),
        },
        "comparativo": None,
    }

    # Comparativo Regime Geral x regime escolhido (só faz sentido se a
    # empresa está simulando um regime do Simples)
    if body.regime in ("simples_das", "simples_fora_das"):
        try:
            premissa_credito_das = sim.PREMISSA_CREDITO_DAS_POR_ANO.get(body.ano)
            ref_regime_geral = sim.simular_regime_geral(
                body.aliq_geral, body.pct_desp, body.pct_forn_das,
                premissa_credito_das, body.pct_cli_com_credito,
            )
            resposta["comparativo"] = sim.montar_comparativo(
                ref_regime_geral, cenario_real, "Regime Geral", "Regime atual (simulado)"
            )
        except Exception:
            pass  # comparativo é um extra — se falhar, não derruba a simulação principal

    return resposta


@router.get("/referencia")
def referencia(usuario: dict = Depends(auth.usuario_atual)):
    """Dados de apoio pra tela: tabela de alíquotas por ano, CNAEs
    sugeridos, e quais Anexos/Anos já têm tabela do Simples carregada
    (pra tela saber o que já pode oferecer sem dar erro)."""
    anexos_disponiveis = {
        anexo: sorted(int(ano) for ano in dados.keys())
        for anexo, dados in sim.TABELA_SIMPLES_ANEXOS.items()
    }
    return {
        "aliquota_regime_geral_por_ano": sim.ALIQ_REGIME_GERAL_POR_ANO,
        "premissa_credito_das_por_ano": sim.PREMISSA_CREDITO_DAS_POR_ANO,
        "premissa_credito_das_confirmado": sorted(sim.PREMISSA_CREDITO_DAS_CONFIRMADO),
        "cnae_sugestoes": sim.CNAE_SUGESTOES,
        "faturamento_limite_simples": sim.FATURAMENTO_LIMITE_SIMPLES,
        "anexos_disponiveis": anexos_disponiveis,
    }


def _salvar_temp(upload: UploadFile, destino_dir: str) -> str:
    caminho = os.path.join(destino_dir, upload.filename)
    with open(caminho, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return caminho


@router.post("/calcular-da-planilha")
async def calcular_da_planilha(
    planilhas_saida: List[UploadFile] = File(...),
    planilhas_entrada: List[UploadFile] = File(...),
    usuario: dict = Depends(auth.usuario_atual),
):
    """
    Lê as planilhas do NBS (mesmo formato já usado no PIS/COFINS: Saída =
    'Lista Pis Cofins', Entrada = 'Credito_Pis_Cofins', uma por filial) e
    devolve faturamento_total, despesa_creditavel_total e pct_desp já
    calculados — pra tela pré-preencher os campos em vez do usuário
    digitar manualmente. Modo "Riozen" do simulador (regime sempre
    Regime Geral).
    """
    logs = []
    def log(msg): logs.append(str(msg))

    tmp_dir = tempfile.mkdtemp(prefix="reforma_sim_")
    try:
        saida_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_saida]
        entrada_paths = [_salvar_temp(f, tmp_dir) for f in planilhas_entrada]
        resultado = sim.calcular_faturamento_e_despesas(saida_paths, entrada_paths, log=log)
        resultado["logs"] = logs
        return resultado
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Falha ao ler as planilhas: {traceback.format_exc()}",
        )
