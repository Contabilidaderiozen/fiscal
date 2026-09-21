"""
Camada de banco de dados do Sistema Riozen (web).

Aponta pro MESMO arquivo tarefas_riozen.db que o Riozen Fiscal (desktop) já usa
em Z:\\Tarefas — não é um banco novo, é o mesmo banco, agora acessado por um
processo único (o backend), o que na verdade resolve a preocupação de múltiplos
processos escrevendo direto no SQLite ao mesmo tempo.

A função autenticar() usa exatamente o mesmo hash (SHA-256 sem salt) que o
tarefas_db.py original, pra que usuários e senhas já cadastrados continuem
funcionando sem precisar resetar nada. Ver nota de segurança no fim do arquivo.
"""

import sqlite3
import hashlib
import os
from contextlib import contextmanager

# Caminho do banco compartilhado. Em produção isso deve apontar pro
# Z:\Tarefas\tarefas_riozen.db real. Pode ser sobrescrito por variável de
# ambiente RIOZEN_DB_PATH (útil pra testes locais).
CAMINHO_DB = os.environ.get("RIOZEN_DB_PATH", r"Z:\Tarefas\tarefas_riozen.db")


def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


@contextmanager
def conexao():
    conn = sqlite3.connect(CAMINHO_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def autenticar(login: str, senha: str):
    """Confere login/senha na tabela usuarios. Retorna dict do usuário ou None.

    Idêntico em comportamento ao autenticar() do tarefas_db.py original.
    """
    with conexao() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, nome, login, setor, perfil FROM usuarios "
            "WHERE login=? AND senha=? AND ativo=1",
            (login.strip(), _hash_senha(senha)),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "nome": row["nome"],
            "login": row["login"],
            "setor": row["setor"],
            "perfil": row["perfil"],
        }


# ---------------------------------------------------------------------------
# NOTA DE SEGURANÇA
# ---------------------------------------------------------------------------
# O hash de senha atual é SHA-256 sem salt — igual ao painel.py/tarefas_db.py
# de hoje. Isso era aceitável rodando 100% local (o hash nunca saía da
# máquina). Agora que o sistema fica exposto numa rede compartilhada, com
# múltiplos usuários acessando via navegador, vale migrar pra bcrypt/argon2
# em algum momento (não bloqueia o lançamento inicial, mas fica registrado
# como próximo passo de segurança).
