"""
fornecedor_regime.py — Consulta e cache do regime tributário (Simples
Nacional ou não) de fornecedores/prestadores de serviço, usado para
corrigir a verificação de retenção de IRRF/PIS/COFINS/CSLL em
nfse_adn_api.py.

Por que isso importa: empresas optantes pelo Simples Nacional já recolhem
PIS/COFINS/CSLL (e, na quase totalidade dos casos, também não sofrem
retenção de IRRF) dentro da guia única do DAS. A tabela de códigos de
serviço (tabela_ir_fonte_novo.py) não sabe o regime do prestador — só o
código do serviço — por isso essa checagem precisa ser feita à parte, por
CNPJ do prestador.

Fonte de dados: BrasilAPI (https://brasilapi.com.br/api/cnpj/v1/{cnpj}),
que espelha os dados públicos e abertos da Receita Federal, incluindo o
campo "opcao_pelo_simples". Gratuita, sem necessidade de chave/cadastro.

Cache: banco SQLite na mesma pasta de rede compartilhada do acervo de notas
(pasta_db, a mesma do banco de tarefas) — cada CNPJ só é consultado uma vez
e o resultado fica disponível pra qualquer usuário. Resultados são
revalidados automaticamente depois de VALIDADE_DIAS (regime raramente
muda, mas pode).
"""
import os
import re
import time
import sqlite3
from datetime import datetime, timedelta

NOME_ARQUIVO = "fornecedores_regime.db"
VALIDADE_DIAS = 180  # revalida a cada ~6 meses
URL_BASE = "https://brasilapi.com.br/api/cnpj/v1"


def _caminho_db(pasta_db: str) -> str:
    return os.path.join(pasta_db, NOME_ARQUIVO)


def _conectar(pasta_db: str) -> sqlite3.Connection:
    os.makedirs(pasta_db, exist_ok=True)
    conn = sqlite3.connect(_caminho_db(pasta_db), timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            cnpj            TEXT PRIMARY KEY,
            razao_social    TEXT,
            opcao_simples   INTEGER,   -- 1 = sim, 0 = nao, NULL = nao verificado
            data_consulta   TEXT NOT NULL,
            erro            TEXT
        )
    """)
    return conn


def cnpj_limpo(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj or "")


def _consultar_api(cnpj: str) -> dict:
    """Consulta a BrasilAPI para um único CNPJ. Levanta exceção se falhar."""
    import requests
    resp = requests.get(f"{URL_BASE}/{cnpj}", timeout=15)
    if resp.status_code == 404:
        raise RuntimeError("CNPJ não encontrado na base da Receita Federal")
    resp.raise_for_status()
    dados = resp.json()
    return {
        "razao_social": dados.get("razao_social") or dados.get("nome_fantasia") or "",
        "opcao_simples": bool(dados.get("opcao_pelo_simples")),
    }


def _buscar_cache(conn, cnpj: str):
    cur = conn.execute(
        "SELECT razao_social, opcao_simples, data_consulta, erro FROM fornecedores WHERE cnpj=?",
        (cnpj,)
    )
    return cur.fetchone()


def _salvar(conn, cnpj: str, razao_social: str, opcao_simples, erro: str = None):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO fornecedores (cnpj, razao_social, opcao_simples, data_consulta, erro)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(cnpj) DO UPDATE SET
            razao_social=excluded.razao_social,
            opcao_simples=excluded.opcao_simples,
            data_consulta=excluded.data_consulta,
            erro=excluded.erro
    """, (cnpj, razao_social, opcao_simples, agora, erro))
    conn.commit()


def obter_regime_lote(pasta_db: str, cnpjs: list, log=None, forcar: bool = False) -> dict:
    """
    Recebe uma lista de CNPJs (com ou sem duplicatas/formatação) e retorna
    um dict {cnpj_limpo: {"razao_social":..., "opcao_simples": True/False/None,
    "verificado": True/False}}.

    "opcao_simples" fica None quando não foi possível verificar (API fora do
    ar, CNPJ não encontrado etc.) — nesse caso o chamador NÃO deve assumir
    que não é Simples, e deve manter o alerta de retenção original, por
    segurança (evita mascarar uma divergência real).
    """
    def _log(msg):
        if log:
            log(msg)

    unicos = sorted({cnpj_limpo(c) for c in cnpjs if c})
    if not unicos:
        return {}

    conn = _conectar(pasta_db)
    resultado = {}
    limite_validade = datetime.now() - timedelta(days=VALIDADE_DIAS)
    consultados_agora = 0

    try:
        for cnpj in unicos:
            linha = _buscar_cache(conn, cnpj)
            usar_cache = False
            if linha and not forcar:
                razao_social, opcao_simples, data_consulta_str, _erro = linha
                try:
                    data_consulta = datetime.strptime(data_consulta_str, "%Y-%m-%d %H:%M:%S")
                    usar_cache = data_consulta > limite_validade and opcao_simples is not None
                except Exception:
                    usar_cache = False

            if usar_cache:
                resultado[cnpj] = {
                    "razao_social": razao_social,
                    "opcao_simples": bool(opcao_simples),
                    "verificado": True,
                }
                continue

            # Precisa consultar (fornecedor novo, cache vencido, ou consulta
            # anterior falhou e ainda não sabemos o regime)
            try:
                info = _consultar_api(cnpj)
                _salvar(conn, cnpj, info["razao_social"], int(info["opcao_simples"]))
                resultado[cnpj] = {
                    "razao_social": info["razao_social"],
                    "opcao_simples": info["opcao_simples"],
                    "verificado": True,
                }
                _log(f"  Regime consultado: {cnpj} — "
                     f"{'Simples Nacional' if info['opcao_simples'] else 'Normal (Lucro Real/Presumido)'}")
            except Exception as ex:
                razao_anterior = linha[0] if linha else ""
                _salvar(conn, cnpj, razao_anterior, None, erro=str(ex))
                resultado[cnpj] = {
                    "razao_social": razao_anterior,
                    "opcao_simples": None,
                    "verificado": False,
                }
                _log(f"  AVISO: não foi possível verificar regime de {cnpj}: {ex}")

            consultados_agora += 1
            time.sleep(1.2)  # nao sobrecarregar a API publica gratuita

    finally:
        conn.close()

    if consultados_agora:
        _log(f"Regime tributário: {consultados_agora} fornecedor(es) novo(s)/revalidado(s), "
             f"{len(unicos) - consultados_agora} já em cache.")
    else:
        _log(f"Regime tributário: {len(unicos)} fornecedor(es), todos já em cache.")

    return resultado
