"""
Cadastro de Clientes/Fornecedores — regime tributário por CNPJ.

Usa o MESMO banco (tarefas_riozen.db) e o mesmo padrão de conexão que
db.py já usa pro resto do sistema (sqlite3.connect + contextmanager),
só numa tabela nova.

Essa tabela é a peça que faltava pro Simulador IBS/CBS conseguir saber se
um fornecedor/cliente é Regime Geral, Simples (DAS) ou Simples fora da
DAS — mas é útil por si só também (registro cadastral), independente de
qual fonte de dado (NBS, PDF do Livro Fiscal, etc.) vai alimentar o
cruzamento por CNPJ mais pra frente.
"""
import re
from datetime import datetime, timezone

from db import conexao

REGIMES_VALIDOS = ("regime_geral", "simples_das", "simples_fora_das")


def _limpar_cnpj(cnpj: str) -> str:
    """Guarda só os dígitos — evita duplicar o mesmo CNPJ com/sem
    pontuação como registros diferentes."""
    return re.sub(r"\D", "", cnpj or "")


def inicializar_tabela():
    """Cria a tabela se ainda não existir. Chamar uma vez na subida do
    backend (ex: dentro do main.py, junto dos outros @app.on_event ou
    logo depois de criar o `app`)."""
    with conexao() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cadastro_regime_tributario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT NOT NULL UNIQUE,
                razao_social TEXT,
                regime_tributario TEXT NOT NULL CHECK (regime_tributario IN
                    ('regime_geral', 'simples_das', 'simples_fora_das')),
                observacao TEXT,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cadastro_regime_cnpj
            ON cadastro_regime_tributario(cnpj)
        """)


def listar(busca: str = None):
    """busca: filtra por CNPJ (só dígitos) ou trecho da razão social."""
    with conexao() as conn:
        if busca:
            busca_cnpj = _limpar_cnpj(busca)
            if busca_cnpj:
                rows = conn.execute(
                    "SELECT * FROM cadastro_regime_tributario "
                    "WHERE cnpj LIKE ? OR razao_social LIKE ? "
                    "ORDER BY razao_social COLLATE NOCASE",
                    (f"%{busca_cnpj}%", f"%{busca}%"),
                ).fetchall()
            else:
                # termo de busca sem nenhum dígito — não faz sentido
                # comparar contra CNPJ (viraria '%%' e bateria com tudo),
                # então filtra só por razão social.
                rows = conn.execute(
                    "SELECT * FROM cadastro_regime_tributario "
                    "WHERE razao_social LIKE ? "
                    "ORDER BY razao_social COLLATE NOCASE",
                    (f"%{busca}%",),
                ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cadastro_regime_tributario ORDER BY razao_social COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]


def buscar_por_cnpj(cnpj: str):
    cnpj_limpo = _limpar_cnpj(cnpj)
    with conexao() as conn:
        row = conn.execute(
            "SELECT * FROM cadastro_regime_tributario WHERE cnpj = ?", (cnpj_limpo,)
        ).fetchone()
        return dict(row) if row else None


def buscar_varios_por_cnpj(cnpjs: list):
    """Usado pelo simulador: dado um lote de CNPJs (de um período inteiro
    de notas), devolve um dict {cnpj_limpo: regime_tributario} só com os
    que estão cadastrados — os que faltam, quem chamou decide o que fazer
    (excluir do cálculo, contar como 'não classificado', etc.), não
    inventamos regime pra CNPJ desconhecido."""
    cnpjs_limpos = list({_limpar_cnpj(c) for c in cnpjs if c})
    if not cnpjs_limpos:
        return {}
    with conexao() as conn:
        placeholders = ",".join("?" for _ in cnpjs_limpos)
        rows = conn.execute(
            f"SELECT cnpj, regime_tributario FROM cadastro_regime_tributario "
            f"WHERE cnpj IN ({placeholders})",
            cnpjs_limpos,
        ).fetchall()
        return {r["cnpj"]: r["regime_tributario"] for r in rows}


def criar_ou_atualizar(cnpj: str, regime_tributario: str, razao_social: str = None, observacao: str = None):
    if regime_tributario not in REGIMES_VALIDOS:
        raise ValueError(f"regime_tributario inválido: {regime_tributario!r} (esperado: {REGIMES_VALIDOS})")
    cnpj_limpo = _limpar_cnpj(cnpj)
    if len(cnpj_limpo) != 14:
        raise ValueError(f"CNPJ inválido (esperado 14 dígitos, veio {len(cnpj_limpo)}): {cnpj!r}")

    agora = datetime.now(timezone.utc).isoformat()
    existente = buscar_por_cnpj(cnpj_limpo)
    with conexao() as conn:
        if existente:
            conn.execute(
                "UPDATE cadastro_regime_tributario "
                "SET regime_tributario=?, razao_social=?, observacao=?, atualizado_em=? "
                "WHERE cnpj=?",
                (regime_tributario, razao_social, observacao, agora, cnpj_limpo),
            )
        else:
            conn.execute(
                "INSERT INTO cadastro_regime_tributario "
                "(cnpj, razao_social, regime_tributario, observacao, criado_em, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (cnpj_limpo, razao_social, regime_tributario, observacao, agora, agora),
            )
    return buscar_por_cnpj(cnpj_limpo)


def excluir(cnpj: str):
    cnpj_limpo = _limpar_cnpj(cnpj)
    with conexao() as conn:
        cur = conn.execute("DELETE FROM cadastro_regime_tributario WHERE cnpj=?", (cnpj_limpo,))
        return cur.rowcount > 0
