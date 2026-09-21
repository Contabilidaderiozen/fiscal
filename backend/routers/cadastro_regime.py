"""
Router do Cadastro de Clientes/Fornecedores (regime tributário por CNPJ).

Só exige login normal (não precisa ser admin) — é um cadastro de uso
corrente, igual ao resto da área Geral.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import auth
import cadastro_regime

router = APIRouter(prefix="/api/cadastro-regime", tags=["cadastro-regime"])


class RegimeBody(BaseModel):
    cnpj: str
    regime_tributario: str
    razao_social: Optional[str] = None
    observacao: Optional[str] = None


@router.get("")
def listar_cadastro(busca: Optional[str] = None, usuario: dict = Depends(auth.usuario_atual)):
    return {"itens": cadastro_regime.listar(busca)}


@router.post("")
def salvar_cadastro(body: RegimeBody, usuario: dict = Depends(auth.usuario_atual)):
    try:
        registro = cadastro_regime.criar_ou_atualizar(
            cnpj=body.cnpj,
            regime_tributario=body.regime_tributario,
            razao_social=body.razao_social,
            observacao=body.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "registro": registro}


@router.delete("/{cnpj}")
def excluir_cadastro(cnpj: str, usuario: dict = Depends(auth.usuario_atual)):
    excluido = cadastro_regime.excluir(cnpj)
    if not excluido:
        raise HTTPException(status_code=404, detail="CNPJ não encontrado no cadastro.")
    return {"ok": True}
