"""
nfse_acervo.py — Acervo permanente e compartilhado de notas NFS-e de entrada.

Guarda toda nota já buscada da API ADN Contribuinte (nfse_adn_api.py), indexada
por chave_acesso, num banco SQLite na pasta de rede compartilhada (a mesma
pasta do banco de tarefas, resolvida por painel._get_pasta_db()).

Isso separa duas coisas que antes estavam misturadas no checkpoint de NSU:
  1. De onde continuar buscando na API (cursor NSU — nsu_checkpoint.json,
     local por máquina, sempre avança, nunca volta)
  2. O que já foi encontrado e pode virar relatório (este acervo — permanente,
     compartilhado entre usuários, nunca perde histórico)

Qualquer usuário com acesso à pasta de rede consegue reconstruir o relatório
de qualquer período já buscado antes por qualquer outro usuário, sem precisar
do certificado digital nem chamar a API de novo.
"""
import os
import sqlite3
import json
from datetime import datetime

NOME_ARQUIVO = "nfse_entrada_acervo.db"


def _caminho_db(pasta_db: str) -> str:
    return os.path.join(pasta_db, NOME_ARQUIVO)


def _conectar(pasta_db: str) -> sqlite3.Connection:
    os.makedirs(pasta_db, exist_ok=True)
    conn = sqlite3.connect(_caminho_db(pasta_db), timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            chave_acesso   TEXT PRIMARY KEY,
            empresa        TEXT NOT NULL,
            filial         TEXT NOT NULL,
            cnpj_tomador   TEXT NOT NULL,
            nsu            INTEGER,
            data_emissao   TEXT,
            status_geral   TEXT,
            dados_json     TEXT NOT NULL,
            atualizado_em  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notas_periodo ON notas (empresa, filial, data_emissao)")
    return conn


def salvar_notas(pasta_db: str, empresa: str, filial: str, cnpj_tomador: str, notas_analisadas: list) -> dict:
    """Insere ou atualiza (upsert) cada nota no acervo, deduplicando por chave_acesso.
    Se a nota já existir (reprocessada), sobrescreve com os dados mais recentes —
    útil se a lógica de verificar_retencoes for corrigida/melhorada no futuro.
    Retorna {"gravadas": N, "ignoradas_sem_chave": N} para diagnóstico."""
    if not notas_analisadas:
        return {"gravadas": 0, "ignoradas_sem_chave": 0}
    conn = _conectar(pasta_db)
    gravadas = 0
    ignoradas = 0
    try:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for nota in notas_analisadas:
            chave = nota.get("chave_acesso")
            if not chave:
                ignoradas += 1
                continue  # sem chave de acesso nao da pra deduplicar - ignora
            conn.execute("""
                INSERT INTO notas (chave_acesso, empresa, filial, cnpj_tomador, nsu,
                                    data_emissao, status_geral, dados_json, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chave_acesso) DO UPDATE SET
                    nsu=excluded.nsu,
                    data_emissao=excluded.data_emissao,
                    status_geral=excluded.status_geral,
                    dados_json=excluded.dados_json,
                    atualizado_em=excluded.atualizado_em
            """, (
                chave, empresa, filial, cnpj_tomador, nota.get("nsu"),
                nota.get("data_geracao_nsu") or nota.get("data_emissao"),
                nota.get("status_geral"),
                json.dumps(nota, ensure_ascii=False), agora
            ))
            gravadas += 1
        conn.commit()
        return {"gravadas": gravadas, "ignoradas_sem_chave": ignoradas}
    finally:
        conn.close()


def buscar_periodo(pasta_db: str, empresa: str, filial: str, data_inicio: str, data_fim: str) -> list:
    """
    Retorna todas as notas já guardadas no acervo para essa empresa/filial cuja
    data de emissão caia no período pedido (DD/MM/AAAA), não importa quando
    foram buscadas nem qual usuário/máquina as buscou.
    """
    dt_ini = datetime.strptime(data_inicio, "%d/%m/%Y")
    dt_fim = datetime.strptime(data_fim, "%d/%m/%Y").replace(hour=23, minute=59, second=59)

    conn = _conectar(pasta_db)
    try:
        cur = conn.execute(
            "SELECT dados_json, data_emissao FROM notas WHERE empresa=? AND filial=?",
            (empresa, filial)
        )
        resultado = []
        for dados_json, data_emissao_str in cur.fetchall():
            if not data_emissao_str:
                continue
            try:
                data_emissao = datetime.fromisoformat(
                    data_emissao_str.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                continue
            if dt_ini <= data_emissao <= dt_fim:
                resultado.append(json.loads(dados_json))
        return resultado
    finally:
        conn.close()
