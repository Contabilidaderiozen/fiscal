"""
Autenticação por sessão via cookie assinado.

Fluxo:
1. POST /api/login com login/senha -> valida contra o banco (db.autenticar) ->
   se ok, grava um cookie httpOnly assinado com os dados do usuário.
2. Toda rota protegida usa a dependência `usuario_atual` -> lê e valida o
   cookie -> devolve o dict do usuário ou lança 401.
3. POST /api/logout -> apaga o cookie.

O cookie é ASSINADO (itsdangerous), não criptografado: o conteúdo (id, nome,
login, setor, perfil) fica legível se alguém abrir o cookie, mas não pode ser
FORJADO sem a chave secreta do servidor — qualquer alteração invalida a
assinatura. Isso é suficiente aqui porque não guardamos senha nem dado
sensível no cookie, só identificação de sessão.
"""

import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, Response

import db

NOME_COOKIE = "riozen_sessao"
DURACAO_SESSAO_SEGUNDOS = 60 * 60 * 12  # 12 horas

# Chave secreta do servidor. Em produção: definir a variável de ambiente
# RIOZEN_SECRET_KEY (nunca deixar o valor padrão abaixo em produção real).
_CHAVE_SECRETA = os.environ.get("RIOZEN_SECRET_KEY", "troque-esta-chave-em-producao")

_serializer = URLSafeTimedSerializer(_CHAVE_SECRETA)


def criar_sessao(response: Response, usuario: dict):
    token = _serializer.dumps(usuario)
    response.set_cookie(
        key=NOME_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=DURACAO_SESSAO_SEGUNDOS,
        # secure=True deve ser ativado quando o sistema rodar atrás de HTTPS
        # (recomendado mesmo em rede interna, mas não obrigatório pro MVP).
    )


def apagar_sessao(response: Response):
    response.delete_cookie(NOME_COOKIE)


def usuario_atual(request: Request) -> dict:
    """Dependência FastAPI: exige sessão válida. Lança 401 se não houver."""
    token = request.cookies.get(NOME_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sessao nao encontrada. Faca login novamente.")
    try:
        dados = _serializer.loads(token, max_age=DURACAO_SESSAO_SEGUNDOS)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Sessao expirada. Faca login novamente.")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Sessao invalida. Faca login novamente.")
    return dados


def usuario_atual_opcional(request: Request):
    """Igual usuario_atual, mas retorna None em vez de lançar erro."""
    token = request.cookies.get(NOME_COOKIE)
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=DURACAO_SESSAO_SEGUNDOS)
    except (BadSignature, SignatureExpired):
        return None
