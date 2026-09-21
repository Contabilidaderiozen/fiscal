"""
Router da tela de Configurações — Modo, Usuários, Modelos, Empresas,
Alterar Senha, Log.

Restrição de acesso (igual o EXE): as abas Usuários/Modelos/Empresas só
funcionam pra admin. Modo/Senha/Log ficam disponíveis pra qualquer
usuário logado.
"""
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

import auth
import configuracoes as cfg

router = APIRouter(prefix="/api/configuracoes", tags=["configuracoes"])


def _perfil(usuario: dict) -> str:
    """Mesma lógica usada em admin.py — duplicada aqui (não importada de
    main.py) pra não criar import circular."""
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


def _exigir_admin(usuario: dict = Depends(auth.usuario_atual)):
    if _perfil(usuario) != "admin":
        raise HTTPException(status_code=403, detail="Só administradores podem acessar isso.")
    return usuario


# ═════════════════════════════════════════════════════════════════════
# CATÁLOGO DE OBRIGAÇÕES (referência estática pra tela montar os checkboxes)
# ═════════════════════════════════════════════════════════════════════
@router.get("/catalogo-obrigacoes")
def catalogo_obrigacoes(usuario: dict = Depends(_exigir_admin)):
    return {
        setor: [{"obrigacao": o, "dia_padrao": d, "regra_padrao": r} for o, d, r in lista]
        for setor, lista in cfg.CATALOGO_OBRIGACOES.items()
    }


# ═════════════════════════════════════════════════════════════════════
# USUÁRIOS
# ═════════════════════════════════════════════════════════════════════
class UsuarioNovoBody(BaseModel):
    nome: str
    login: str
    senha: str
    setor: str
    perfil: str = "usuario"
    email: Optional[str] = ""


class UsuarioEdicaoBody(BaseModel):
    nome: str
    setor: str
    perfil: str
    email: Optional[str] = ""
    nova_senha: Optional[str] = None


@router.get("/usuarios")
def api_listar_usuarios(usuario: dict = Depends(_exigir_admin)):
    return {"itens": cfg.listar_usuarios()}


@router.post("/usuarios")
def api_criar_usuario(body: UsuarioNovoBody, usuario: dict = Depends(_exigir_admin)):
    if not body.nome.strip() or not body.login.strip() or not body.senha.strip():
        raise HTTPException(status_code=400, detail="Preencha nome, login e senha.")
    resultado = cfg.criar_usuario(body.nome, body.login, body.senha, body.setor, body.perfil, body.email)
    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["erro"])
    cfg.log_evento("ACAO", f"Usuário criado: {body.nome} (@{body.login})", usuario=usuario["login"])
    return {"ok": True}


@router.put("/usuarios/{usuario_id}")
def api_editar_usuario(usuario_id: int, body: UsuarioEdicaoBody, usuario: dict = Depends(_exigir_admin)):
    cfg.editar_usuario(usuario_id, body.nome, body.setor, body.perfil, body.email, body.nova_senha)
    cfg.log_evento("ACAO", f"Usuário editado: {body.nome} (id {usuario_id})", usuario=usuario["login"])
    return {"ok": True}


@router.post("/usuarios/{usuario_id}/toggle-ativo")
def api_toggle_ativo(usuario_id: int, usuario: dict = Depends(_exigir_admin)):
    cfg.toggle_ativo_usuario(usuario_id)
    cfg.log_evento("ACAO", f"Usuário ativado/desativado (id {usuario_id})", usuario=usuario["login"])
    return {"ok": True}


@router.delete("/usuarios/{usuario_id}")
def api_excluir_usuario(usuario_id: int, usuario: dict = Depends(_exigir_admin)):
    cfg.excluir_usuario(usuario_id)
    cfg.log_evento("ACAO", f"Usuário excluído (id {usuario_id})", usuario=usuario["login"])
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════
# ALTERAR SENHA (o próprio usuário, não precisa ser admin)
# ═════════════════════════════════════════════════════════════════════
class AlterarSenhaBody(BaseModel):
    senha_atual: str
    nova_senha: str
    confirmar: str


@router.post("/alterar-senha")
def api_alterar_senha(body: AlterarSenhaBody, usuario: dict = Depends(auth.usuario_atual)):
    if not body.senha_atual or not body.nova_senha or not body.confirmar:
        raise HTTPException(status_code=400, detail="Preencha todos os campos.")
    if body.nova_senha != body.confirmar:
        raise HTTPException(status_code=400, detail="A nova senha e a confirmação não coincidem.")
    if len(body.nova_senha) < 4:
        raise HTTPException(status_code=400, detail="A nova senha deve ter ao menos 4 caracteres.")

    import db
    checagem = db.autenticar(usuario["login"], body.senha_atual)
    if not checagem:
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    cfg.alterar_senha(usuario["id"], body.nova_senha)
    cfg.log_evento("ACAO", "Senha alterada", usuario=usuario["login"])
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════
# MODELOS DE TAREFA
# ═════════════════════════════════════════════════════════════════════
class ModeloNovoBody(BaseModel):
    nome: str
    setor: str
    escopo: str = "Por Filial"


class SubtarefaBody(BaseModel):
    titulo: str


@router.get("/modelos")
def api_listar_modelos(usuario: dict = Depends(_exigir_admin)):
    return {"itens": cfg.listar_modelos()}


@router.post("/modelos")
def api_criar_modelo(body: ModeloNovoBody, usuario: dict = Depends(_exigir_admin)):
    if not body.nome.strip():
        raise HTTPException(status_code=400, detail="Digite o nome.")
    resultado = cfg.criar_modelo(body.nome, body.setor, body.escopo)
    if not resultado["ok"]:
        raise HTTPException(status_code=400, detail=resultado["erro"])
    cfg.log_evento("ACAO", f"Modelo criado: {body.nome}", usuario=usuario["login"])
    return resultado


@router.delete("/modelos/{modelo_id}")
def api_excluir_modelo(modelo_id: int, usuario: dict = Depends(_exigir_admin)):
    cfg.excluir_modelo(modelo_id)
    cfg.log_evento("ACAO", f"Modelo excluído (id {modelo_id})", usuario=usuario["login"])
    return {"ok": True}


@router.get("/modelos/{modelo_id}/subtarefas")
def api_listar_subtarefas(modelo_id: int, usuario: dict = Depends(_exigir_admin)):
    return {"itens": cfg.listar_subtarefas_modelo(modelo_id)}


@router.post("/modelos/{modelo_id}/subtarefas")
def api_add_subtarefa(modelo_id: int, body: SubtarefaBody, usuario: dict = Depends(_exigir_admin)):
    if not body.titulo.strip():
        raise HTTPException(status_code=400, detail="Digite o título da subtarefa.")
    cfg.adicionar_subtarefa_modelo(modelo_id, body.titulo)
    return {"ok": True}


@router.delete("/subtarefas/{sub_id}")
def api_excluir_subtarefa(sub_id: int, usuario: dict = Depends(_exigir_admin)):
    cfg.excluir_subtarefa_modelo(sub_id)
    return {"ok": True}


@router.post("/subtarefas/{sub_id}/mover/{direcao}")
def api_mover_subtarefa(sub_id: int, direcao: str, usuario: dict = Depends(_exigir_admin)):
    if direcao not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Direção inválida.")
    cfg.reordenar_subtarefa_modelo(sub_id, direcao)
    return {"ok": True}


# ═════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═════════════════════════════════════════════════════════════════════
class EmpresaBody(BaseModel):
    nome: str
    cnpj: str
    im: Optional[str] = ""
    ie: Optional[str] = ""
    grupo: Optional[str] = ""
    copiar_de: Optional[int] = None  # id de outra empresa, só usado ao criar


class ObrigacaoItem(BaseModel):
    setor: str
    obrigacao: str
    dia_venc: Optional[int] = None
    regra_feriado: str = "postergar"
    ativo: bool = True


class EmpresaCompletaBody(BaseModel):
    regime: str = ""
    atividade: str = ""
    municipio: str = "Rio de Janeiro"
    uf: str = "RJ"
    obrigacoes: List[ObrigacaoItem] = []


@router.get("/empresas")
def api_listar_empresas(usuario: dict = Depends(_exigir_admin)):
    return {"itens": cfg.listar_empresas()}


@router.get("/empresas/{empresa_id}")
def api_obter_empresa(empresa_id: int, usuario: dict = Depends(_exigir_admin)):
    empresa = cfg.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return {
        "empresa": empresa,
        "param": cfg.obter_param(empresa_id),
        "obrigacoes": cfg.listar_obrigacoes(empresa_id),
    }


@router.post("/empresas")
def api_criar_empresa(body: EmpresaBody, usuario: dict = Depends(_exigir_admin)):
    if not body.nome.strip() or not body.cnpj.strip():
        raise HTTPException(status_code=400, detail="Nome e CNPJ são obrigatórios.")
    eid = cfg.criar_empresa(body.nome, body.cnpj, body.im, body.ie, body.grupo)
    if body.copiar_de:
        cfg.copiar_param(body.copiar_de, eid)
    cfg.log_evento("ACAO", f"Empresa criada: {body.nome}", detalhes=f"CNPJ: {body.cnpj}", usuario=usuario["login"])
    return {"ok": True, "id": eid}


@router.put("/empresas/{empresa_id}")
def api_editar_empresa(empresa_id: int, body: EmpresaBody, usuario: dict = Depends(_exigir_admin)):
    if not body.nome.strip() or not body.cnpj.strip():
        raise HTTPException(status_code=400, detail="Nome e CNPJ são obrigatórios.")
    cfg.editar_empresa(empresa_id, body.nome, body.cnpj, body.im, body.ie, body.grupo)
    cfg.log_evento("ACAO", f"Empresa editada: {body.nome}", detalhes=f"CNPJ: {body.cnpj}", usuario=usuario["login"])
    return {"ok": True}


@router.post("/empresas/{empresa_id}/parametrizacao")
def api_salvar_parametrizacao(empresa_id: int, body: EmpresaCompletaBody, usuario: dict = Depends(_exigir_admin)):
    empresa = cfg.obter_empresa(empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")

    cfg.salvar_param(empresa_id, body.regime, body.atividade, body.municipio, body.uf)
    cfg.salvar_obrigacoes(empresa_id, [o.dict() for o in body.obrigacoes])

    try:
        ids_geradas = cfg.gerar_tarefas_parametrizacao(empresa_id, usuario["id"])
        msg = f"{len(ids_geradas)} tarefa(s) gerada(s)." if ids_geradas else "Tarefas do mês já existiam."
    except Exception as e:
        ids_geradas = []
        msg = f"Salvo, mas falhou ao gerar tarefas: {e}"

    cfg.log_evento("ACAO", f"Parametrização salva: {empresa['nome']}", usuario=usuario["login"])
    return {"ok": True, "mensagem": msg, "tarefas_geradas": len(ids_geradas)}


# ═════════════════════════════════════════════════════════════════════
# LOG
# ═════════════════════════════════════════════════════════════════════
@router.get("/log")
def api_listar_log(limite: int = 200, usuario: dict = Depends(auth.usuario_atual)):
    return {"itens": cfg.listar_log(limite), "total": cfg.contar_log()}


@router.get("/log/exportar/{formato}")
def api_exportar_log(formato: str, usuario: dict = Depends(auth.usuario_atual)):
    entradas = cfg.listar_log(limite=100000)
    if formato == "json":
        return JSONResponse(content=entradas)
    if formato == "txt":
        linhas = [
            f"[{e['timestamp']}] {e['tipo']:8} | {e['usuario'] or '':12} | {e['descricao']}"
            + (f"\n{'':38}{e['detalhes']}" if e.get("detalhes") else "")
            for e in entradas
        ]
        return PlainTextResponse("\n".join(linhas))
    raise HTTPException(status_code=400, detail="Formato inválido (use json ou txt).")
