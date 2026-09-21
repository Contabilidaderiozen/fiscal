"""
Sistema Riozen (web) — backend principal.

Roda como serviço no servidor Windows (via NSSM), acessado por todo mundo na
rede pelo navegador. Serve a API (/api/...) e os arquivos estáticos do
frontend (login, shell de navegação, e futuramente cada módulo).

Pra rodar localmente:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import os
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import auth

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="Sistema Riozen")

# Cadastro de Clientes/Fornecedores (regime tributário) — usado pelo
# futuro Simulador IBS/CBS. Cria a tabela no tarefas_riozen.db se ainda
# não existir; não afeta nada que já existe no banco.
import cadastro_regime
cadastro_regime.inicializar_tabela()


# ---------------------------------------------------------------------------
# Perfil de acesso (portado do painel.py: _perfil_de_usuario)
# ---------------------------------------------------------------------------
def perfil_de_usuario(usuario: dict) -> str:
    if not usuario:
        return "fiscal"
    perfil = (usuario.get("perfil") or "usuario").lower().strip()
    setor = (usuario.get("setor") or "fiscal").lower().strip()
    if perfil == "admin":
        return "admin"
    if setor == "todos":
        return "admin"
    if setor == "fiscal":
        return "fiscal"
    if setor in ("contabil", "contábil"):
        return "contabil"
    return "fiscal"


# ---------------------------------------------------------------------------
# API — autenticação
# ---------------------------------------------------------------------------
class LoginBody(BaseModel):
    login: str
    senha: str


@app.post("/api/login")
def login(body: LoginBody, response: Response):
    usuario = db.autenticar(body.login, body.senha)
    if not usuario:
        raise HTTPException(status_code=401, detail="Login ou senha invalidos.")
    auth.criar_sessao(response, usuario)
    return {
        "ok": True,
        "usuario": {**usuario, "perfil_acesso": perfil_de_usuario(usuario)},
    }


@app.post("/api/logout")
def logout(response: Response):
    auth.apagar_sessao(response)
    return {"ok": True}


@app.get("/api/me")
def me(usuario: dict = Depends(auth.usuario_atual)):
    return {**usuario, "perfil_acesso": perfil_de_usuario(usuario)}


# ---------------------------------------------------------------------------
# Paginas — login e shell principal
# ---------------------------------------------------------------------------
@app.get("/login")
def pagina_login(request_usuario=Depends(auth.usuario_atual_opcional)):
    if request_usuario:
        return RedirectResponse("/")
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/")
def pagina_inicial(request_usuario=Depends(auth.usuario_atual_opcional)):
    if not request_usuario:
        return RedirectResponse("/login")
    return FileResponse(FRONTEND_DIR / "index.html")


# Estaticos (css/js) — sem exigir login, pois o login.html tambem precisa deles
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

# Reforma Tributaria — ferramenta autonoma (sem dependencia de backend/API),
# so precisa ser servida como arquivos estaticos. O link e passado pela
# sidebar do shell principal, ja com nome/login/perfil na URL.
app.mount("/reforma-tributaria", StaticFiles(directory=FRONTEND_DIR / "reforma_tributaria", html=True), name="reforma_tributaria")


# ---------------------------------------------------------------------------
# Modulos (routers) - serao adicionados aqui conforme migrarmos cada um
# ---------------------------------------------------------------------------
from routers import assistente
app.include_router(assistente.router, tags=["assistente"])
from routers import icms
app.include_router(icms.router, tags=["icms"])
from routers import pis_cofins
app.include_router(pis_cofins.router, tags=["pis_cofins"])
from routers import admin
app.include_router(admin.router, tags=["admin"])
from routers import cadastro_regime as router_cadastro_regime
app.include_router(router_cadastro_regime.router, tags=["cadastro-regime"])
from routers import reforma_simulador
app.include_router(reforma_simulador.router, tags=["reforma-simulador"])
from routers import cbs_ibs
app.include_router(cbs_ibs.router, tags=["cbs-ibs"])
import configuracoes
configuracoes.inicializar_tabelas()
from routers import configuracoes as router_configuracoes
app.include_router(router_configuracoes.router, tags=["configuracoes"])
from routers import nfse
app.include_router(nfse.router, tags=["nfse"])
# from routers import reforma_tributaria
# app.include_router(reforma_tributaria.router, prefix="/api/reforma", tags=["reforma"])
