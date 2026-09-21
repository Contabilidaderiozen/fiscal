"""
Camada de dados da tela de Configurações — porta pro padrão web (db.conexao())
a lógica que já existia em tarefas_db.py (usado pelo painel.py, o EXE
desktop). Usa o MESMO banco (tarefas_riozen.db) e a MESMA tabela `usuarios`
que o login web já usa (via db.autenticar) — não cria nada paralelo.

Tabelas que este módulo cria (se ainda não existirem): modelos_tarefa,
subtarefas_modelo, empresas, empresas_param, empresas_obrigacoes, tarefas,
subtarefas_exec, historico, log_sistema. A tabela `usuarios` já existe
(criada pelo tarefas_db.py original) e não é recriada aqui.

⚠️ Diferença deliberada do original: o log do EXE (`_LOG_ENTRIES`) vivia só
em memória do processo — se o app fechasse, o log sumia. Aqui persiste em
SQLite (tabela log_sistema), porque o servidor web é compartilhado por
vários usuários ao mesmo tempo e já vimos o serviço reiniciar sozinho
algumas vezes nesta conta — perder o log nesse caso seria pior que no EXE
de um usuário só.
"""
import hashlib
from datetime import datetime, date, timedelta
import calendar

from db import conexao

# Filiais conhecidas do grupo Riozen — mesma lista do tarefas_db.py
# original (EMPRESAS), usada só pra popular a tabela `empresas` na
# primeira vez, se ela estiver vazia.
FILIAIS_CONHECIDAS = {
    "Toyota": [
        ("PILARES",                 "22.134.988/0001-14"),
        ("TIJUCA",                  "22.134.988/0002-03"),
        ("CAMPO GRANDE",            "22.134.988/0003-86"),
        ("BARRA - JARDIM OCEANICO", "22.134.988/0004-67"),
        ("JACAREPAGUA WP",          "22.134.988/0005-48"),
        ("LEXUS",                   "22.134.988/0006-29"),
        ("ALVORADA",                "22.134.988/0007-00"),
        ("RECREIO",                 "22.134.988/0008-90"),
    ],
    "BYD": [
        ("JACAREPAGUA",             "52.752.754/0001-00"),
        ("CAMPO GRANDE",            "52.752.754/0002-82"),
        ("SAO JOAO DE MERITI",      "52.752.754/0003-63"),
        ("BARRA MANSA",             "52.752.754/0004-44"),
    ],
    "Riozen": [
        ("INTERMEDIACAO",           "58.489.102/0001-00"),
    ],
}

CATALOGO_OBRIGACOES = {
    "Fiscal": [
        ("ISS",                 5,  "postergar"),
        ("ICMS",               13,  "postergar"),
        ("SPED Fiscal",        20,  "postergar"),
        ("PIS/COFINS",         25,  "postergar"),
        ("EFD Contribuicoes",  10,  "postergar"),
        ("REINF",              15,  "postergar"),
        ("DCTF",               15,  "postergar"),
        ("DCTFWeb",            15,  "postergar"),
        ("IRRF",               20,  "postergar"),
        ("DIFAL",              10,  "postergar"),
        ("GIA/DAPI",           20,  "postergar"),
    ],
    "DP": [
        ("Folha",               5,  "antecipar"),
        ("FGTS",                7,  "postergar"),
        ("eSocial",             7,  "postergar"),
        ("INSS",               20,  "postergar"),
        ("CAGED",               7,  "postergar"),
        ("IRRF Folha",         20,  "postergar"),
        ("CSLL Retida",        20,  "postergar"),
    ],
    "Contabil": [
        ("IRPJ/CSLL",          30,  "postergar"),
        ("ECF",                31,  "postergar"),
        ("ECD",                31,  "postergar"),
        ("DEFIS",              31,  "postergar"),
        ("Balanco",            31,  "postergar"),
        ("DMPL",               31,  "postergar"),
    ],
}


def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def _agora() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def inicializar_tabelas():
    """Cria as tabelas que ainda não existirem. Chamar uma vez na subida
    do backend (main.py), igual já fazemos com cadastro_regime."""
    with conexao() as conn:
        c = conn.cursor()

        # Migração defensiva: a tabela `usuarios` já existe (criada pelo
        # tarefas_db.py original) — mas a coluna `email` só era adicionada
        # via ALTER TABLE quando alguém abria a tela Configurações no EXE.
        # Se isso nunca rodou neste banco, a coluna pode não existir e
        # qualquer consulta que a referencie quebra. Tenta adicionar; se já
        # existir, o banco recusa e a gente ignora o erro.
        try:
            c.execute("ALTER TABLE usuarios ADD COLUMN email TEXT DEFAULT ''")
        except Exception:
            pass

        c.execute("""CREATE TABLE IF NOT EXISTS modelos_tarefa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE, setor TEXT NOT NULL,
            escopo TEXT NOT NULL DEFAULT 'Por Filial',
            ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS subtarefas_modelo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modelo_id INTEGER NOT NULL, ordem INTEGER NOT NULL DEFAULT 0,
            titulo TEXT NOT NULL,
            FOREIGN KEY(modelo_id) REFERENCES modelos_tarefa(id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL, cnpj TEXT, im TEXT, ie TEXT, grupo TEXT,
            ativo INTEGER DEFAULT 1, criado_em TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS empresas_param (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_id INTEGER NOT NULL,
            regime TEXT, atividade TEXT, municipio TEXT, uf TEXT,
            atualizado_em TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS empresas_obrigacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_id INTEGER NOT NULL,
            setor TEXT, obrigacao TEXT, dia_venc INTEGER,
            regra_feriado TEXT, ativo INTEGER DEFAULT 1, obs TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS tarefas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, titulo TEXT NOT NULL,
            modelo_id INTEGER, escopo TEXT NOT NULL DEFAULT 'Por Matriz',
            empresa TEXT, filial_nome TEXT, filial_cnpj TEXT,
            setor TEXT NOT NULL, prioridade TEXT NOT NULL DEFAULT 'Normal',
            status TEXT NOT NULL DEFAULT 'A fazer',
            criado_por INTEGER NOT NULL, responsavel INTEGER,
            data_inicio TEXT, data_fim TEXT, data_venc TEXT,
            criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
            concluido_por INTEGER, concluido_em TEXT,
            recorrente INTEGER DEFAULT 0, recorrencia_tipo TEXT,
            origem TEXT DEFAULT 'manual', obrigacao TEXT,
            empresa_id INTEGER, periodo TEXT, tarefa_pai_id INTEGER
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS subtarefas_exec (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tarefa_id INTEGER NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 0, titulo TEXT NOT NULL,
            concluida INTEGER NOT NULL DEFAULT 0,
            concluida_por INTEGER, concluida_em TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tarefa_id INTEGER NOT NULL,
            usuario_id INTEGER NOT NULL, acao TEXT NOT NULL,
            detalhe TEXT, momento TEXT NOT NULL
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS log_sistema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL, tipo TEXT NOT NULL,
            usuario TEXT, descricao TEXT NOT NULL, detalhes TEXT
        )""")

        # Auto-seed das 13 filiais do grupo Riozen — igual o painel.py fazia
        # na primeira vez que alguém abria a aba Empresas. Nome/CNPJ já são
        # conhecidos (não muda por empresa); regime/atividade/município e
        # obrigações continuam em branco, pra preencher manualmente uma
        # vez por filial (varia — Barra Mansa é outro município, etc).
        ja_tem_empresa = c.execute("SELECT COUNT(*) AS n FROM empresas").fetchone()["n"]
        if not ja_tem_empresa:
            agora = _agora()
            for grupo, filiais in FILIAIS_CONHECIDAS.items():
                for nome_filial, cnpj in filiais:
                    c.execute(
                        "INSERT INTO empresas (nome,cnpj,im,ie,grupo,ativo,criado_em) VALUES (?,?,?,?,?,1,?)",
                        (f"{grupo} {nome_filial}", cnpj, "", "", grupo, agora),
                    )


# ═════════════════════════════════════════════════════════════════════
# LOG
# ═════════════════════════════════════════════════════════════════════
def log_evento(tipo: str, descricao: str, detalhes: str = "", usuario: str = "sistema"):
    """tipo: ACAO | ERRO | SCRIPT | SISTEMA"""
    with conexao() as conn:
        conn.execute(
            "INSERT INTO log_sistema (timestamp, tipo, usuario, descricao, detalhes) VALUES (?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tipo, usuario, descricao, detalhes or ""),
        )


def listar_log(limite: int = 200):
    with conexao() as conn:
        rows = conn.execute(
            "SELECT timestamp, tipo, usuario, descricao, detalhes FROM log_sistema "
            "ORDER BY id DESC LIMIT ?", (limite,)
        ).fetchall()
        return [dict(r) for r in rows]


def contar_log():
    with conexao() as conn:
        return conn.execute("SELECT COUNT(*) AS n FROM log_sistema").fetchone()["n"]


# ═════════════════════════════════════════════════════════════════════
# USUÁRIOS
# ═════════════════════════════════════════════════════════════════════
def listar_usuarios():
    with conexao() as conn:
        rows = conn.execute(
            "SELECT id,nome,login,setor,perfil,ativo,COALESCE(email,'') AS email "
            "FROM usuarios ORDER BY nome"
        ).fetchall()
        return [dict(r) for r in rows]


def criar_usuario(nome, login, senha, setor, perfil="usuario", email=""):
    with conexao() as conn:
        try:
            conn.execute(
                "INSERT INTO usuarios (nome,login,senha,setor,perfil,ativo,email,criado_em) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (nome.strip(), login.strip(), _hash_senha(senha), setor, perfil,
                 (email or "").strip(), _agora()),
            )
            return {"ok": True}
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                return {"ok": False, "erro": "Login já existe."}
            return {"ok": False, "erro": str(e)}


def editar_usuario(usuario_id, nome, setor, perfil, email, nova_senha=None):
    with conexao() as conn:
        if nova_senha:
            conn.execute(
                "UPDATE usuarios SET nome=?, setor=?, perfil=?, email=?, senha=? WHERE id=?",
                (nome.strip(), setor, perfil, (email or "").strip(), _hash_senha(nova_senha), usuario_id),
            )
        else:
            conn.execute(
                "UPDATE usuarios SET nome=?, setor=?, perfil=?, email=? WHERE id=?",
                (nome.strip(), setor, perfil, (email or "").strip(), usuario_id),
            )
    return {"ok": True}


def alterar_senha(usuario_id, nova_senha):
    with conexao() as conn:
        conn.execute("UPDATE usuarios SET senha=? WHERE id=?", (_hash_senha(nova_senha), usuario_id))


def toggle_ativo_usuario(usuario_id):
    with conexao() as conn:
        row = conn.execute("SELECT ativo FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        if row:
            conn.execute("UPDATE usuarios SET ativo=? WHERE id=?", (0 if row["ativo"] else 1, usuario_id))


def excluir_usuario(usuario_id):
    with conexao() as conn:
        conn.execute("UPDATE tarefas SET responsavel=NULL WHERE responsavel=?", (usuario_id,))
        conn.execute("UPDATE tarefas SET concluido_por=NULL WHERE concluido_por=?", (usuario_id,))
        conn.execute("DELETE FROM historico WHERE usuario_id=?", (usuario_id,))
        conn.execute("DELETE FROM usuarios WHERE id=?", (usuario_id,))


# ═════════════════════════════════════════════════════════════════════
# MODELOS DE TAREFA
# ═════════════════════════════════════════════════════════════════════
def listar_modelos():
    with conexao() as conn:
        rows = conn.execute(
            "SELECT id,nome,setor,escopo,ativo FROM modelos_tarefa ORDER BY nome"
        ).fetchall()
        return [dict(r) for r in rows]


def criar_modelo(nome, setor, escopo):
    with conexao() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO modelos_tarefa (nome,setor,escopo,ativo,criado_em) VALUES (?,?,?,1,?)",
                (nome.strip(), setor, escopo, _agora()),
            )
            return {"ok": True, "id": cur.lastrowid}
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                return {"ok": False, "erro": "Modelo com este nome já existe."}
            return {"ok": False, "erro": str(e)}


def excluir_modelo(modelo_id):
    with conexao() as conn:
        conn.execute("DELETE FROM subtarefas_modelo WHERE modelo_id=?", (modelo_id,))
        conn.execute("DELETE FROM modelos_tarefa WHERE id=?", (modelo_id,))


def listar_subtarefas_modelo(modelo_id):
    with conexao() as conn:
        rows = conn.execute(
            "SELECT id,ordem,titulo FROM subtarefas_modelo WHERE modelo_id=? ORDER BY ordem",
            (modelo_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def adicionar_subtarefa_modelo(modelo_id, titulo):
    with conexao() as conn:
        ordem = conn.execute(
            "SELECT COALESCE(MAX(ordem),0)+1 AS n FROM subtarefas_modelo WHERE modelo_id=?",
            (modelo_id,),
        ).fetchone()["n"]
        conn.execute(
            "INSERT INTO subtarefas_modelo (modelo_id,ordem,titulo) VALUES (?,?,?)",
            (modelo_id, ordem, titulo.strip()),
        )


def excluir_subtarefa_modelo(sub_id):
    with conexao() as conn:
        conn.execute("DELETE FROM subtarefas_modelo WHERE id=?", (sub_id,))


def reordenar_subtarefa_modelo(sub_id, direcao):
    """direcao: 'up' ou 'down'"""
    with conexao() as conn:
        row = conn.execute(
            "SELECT modelo_id, ordem FROM subtarefas_modelo WHERE id=?", (sub_id,)
        ).fetchone()
        if not row:
            return
        modelo_id, ordem_atual = row["modelo_id"], row["ordem"]
        op = "<" if direcao == "up" else ">"
        order_dir = "DESC" if direcao == "up" else "ASC"
        vizinho = conn.execute(
            f"SELECT id, ordem FROM subtarefas_modelo WHERE modelo_id=? AND ordem {op} ? "
            f"ORDER BY ordem {order_dir} LIMIT 1",
            (modelo_id, ordem_atual),
        ).fetchone()
        if vizinho:
            conn.execute("UPDATE subtarefas_modelo SET ordem=? WHERE id=?", (vizinho["ordem"], sub_id))
            conn.execute("UPDATE subtarefas_modelo SET ordem=? WHERE id=?", (ordem_atual, vizinho["id"]))


# ═════════════════════════════════════════════════════════════════════
# EMPRESAS
# ═════════════════════════════════════════════════════════════════════
def listar_empresas(so_ativas=True):
    with conexao() as conn:
        sql = "SELECT id,nome,cnpj,im,ie,grupo,ativo FROM empresas"
        if so_ativas:
            sql += " WHERE ativo=1"
        sql += " ORDER BY grupo, nome"
        return [dict(r) for r in conn.execute(sql).fetchall()]


def obter_empresa(empresa_id):
    with conexao() as conn:
        row = conn.execute(
            "SELECT id,nome,cnpj,im,ie,grupo,ativo FROM empresas WHERE id=?", (empresa_id,)
        ).fetchone()
        return dict(row) if row else None


def criar_empresa(nome, cnpj, im, ie, grupo):
    with conexao() as conn:
        cur = conn.execute(
            "INSERT INTO empresas (nome,cnpj,im,ie,grupo,ativo,criado_em) VALUES (?,?,?,?,?,1,?)",
            (nome.strip(), (cnpj or "").strip(), (im or "").strip(), (ie or "").strip(),
             (grupo or "").strip(), _agora()),
        )
        return cur.lastrowid


def editar_empresa(empresa_id, nome, cnpj, im, ie, grupo):
    with conexao() as conn:
        conn.execute(
            "UPDATE empresas SET nome=?,cnpj=?,im=?,ie=?,grupo=? WHERE id=?",
            (nome.strip(), (cnpj or "").strip(), (im or "").strip(), (ie or "").strip(),
             (grupo or "").strip(), empresa_id),
        )


def obter_param(empresa_id):
    with conexao() as conn:
        row = conn.execute(
            "SELECT regime,atividade,municipio,uf FROM empresas_param WHERE empresa_id=?",
            (empresa_id,),
        ).fetchone()
        if not row:
            return {"regime": "", "atividade": "", "municipio": "", "uf": ""}
        return dict(row)


def salvar_param(empresa_id, regime, atividade, municipio, uf):
    with conexao() as conn:
        existe = conn.execute(
            "SELECT id FROM empresas_param WHERE empresa_id=?", (empresa_id,)
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE empresas_param SET regime=?,atividade=?,municipio=?,uf=?,atualizado_em=? "
                "WHERE empresa_id=?",
                (regime, atividade, municipio, uf, _agora(), empresa_id),
            )
        else:
            conn.execute(
                "INSERT INTO empresas_param (empresa_id,regime,atividade,municipio,uf,atualizado_em) "
                "VALUES (?,?,?,?,?,?)",
                (empresa_id, regime, atividade, municipio, uf, _agora()),
            )


def listar_obrigacoes(empresa_id):
    with conexao() as conn:
        rows = conn.execute(
            "SELECT id,setor,obrigacao,dia_venc,regra_feriado,ativo,obs "
            "FROM empresas_obrigacoes WHERE empresa_id=? ORDER BY setor,obrigacao",
            (empresa_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def salvar_obrigacoes(empresa_id, obrigacoes):
    with conexao() as conn:
        conn.execute("DELETE FROM empresas_obrigacoes WHERE empresa_id=?", (empresa_id,))
        for ob in obrigacoes:
            conn.execute(
                "INSERT INTO empresas_obrigacoes "
                "(empresa_id,setor,obrigacao,dia_venc,regra_feriado,ativo,obs) VALUES (?,?,?,?,?,?,?)",
                (empresa_id, ob["setor"], ob["obrigacao"], ob.get("dia_venc"),
                 ob.get("regra_feriado", "postergar"), 1 if ob.get("ativo", True) else 0, ob.get("obs", "")),
            )


def copiar_param(empresa_origem_id, empresa_destino_id):
    param = obter_param(empresa_origem_id)
    salvar_param(empresa_destino_id, param["regime"], param["atividade"], param["municipio"], param["uf"])
    salvar_obrigacoes(empresa_destino_id, listar_obrigacoes(empresa_origem_id))


# ═════════════════════════════════════════════════════════════════════
# GERAÇÃO DE TAREFAS (a partir da parametrização de uma empresa)
# ═════════════════════════════════════════════════════════════════════
_FERIADOS_FED = {"01-01", "04-21", "05-01", "09-07", "10-12", "11-02", "11-15", "11-20", "12-25"}
_FERIADOS_MUN = {
    "Rio de Janeiro": {"01-20", "04-23", "11-20"},
    "Sao Joao de Meriti": {"05-03", "11-20"},
    "Barra Mansa": {"08-11", "11-20"},
}
_DIA_VENC_PAD = {
    "ISS": {"Rio de Janeiro": 5, "Sao Joao de Meriti": 10, "Barra Mansa": 15},
    "ICMS": 13, "SPED Fiscal": 20, "PIS/COFINS": 25, "EFD Contribuicoes": 10,
    "REINF": 15, "DCTF": 15, "DCTFWeb": 15, "IRRF": 20, "DIFAL": 10,
    "Folha": 5, "FGTS": 7, "eSocial": 7, "INSS": 20, "CAGED": 7,
    "IRPJ/CSLL": 30, "ECF": 31, "ECD": 31, "DEFIS": 31,
}


def _pascoa(y):
    a = y % 19; b = y // 100; c = y % 100; d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19*a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2*e + 2*i - h - k) % 7; m = (a + 11*h + 22*l) // 451
    mo = (h + l - 7*m + 114) // 31; dy = ((h + l - 7*m + 114) % 31) + 1
    return date(y, mo, dy)


def _moveis(y):
    p = _pascoa(y)
    return {
        (p - timedelta(2)).strftime("%m-%d"),
        (p - timedelta(48)).strftime("%m-%d"),
        (p - timedelta(47)).strftime("%m-%d"),
        (p + timedelta(60)).strftime("%m-%d"),
    }


def _calcular_venc(obrigacao, ano, mes, municipio, dia_venc_override=None, regra_override=None):
    def _feriado(d):
        md = d.strftime("%m-%d")
        mun = _FERIADOS_MUN.get(municipio, set())
        return md in _FERIADOS_FED or md in mun or md in _moveis(d.year)

    def _prox_util(d):
        while d.weekday() >= 5 or _feriado(d):
            d += timedelta(1)
        return d

    def _ant_util(d):
        while d.weekday() >= 5 or _feriado(d):
            d -= timedelta(1)
        return d

    pad = _DIA_VENC_PAD.get(obrigacao)
    if dia_venc_override:
        dia_base = int(dia_venc_override)
    elif isinstance(pad, dict):
        dia_base = pad.get(municipio) or list(pad.values())[0]
    elif pad:
        dia_base = int(pad)
    else:
        dia_base = 10

    mv = mes + 1; av = ano
    if mv > 12:
        mv = 1; av += 1
    dia_base = min(dia_base, calendar.monthrange(av, mv)[1])
    data_base = date(av, mv, dia_base)

    regra = regra_override or ("antecipar" if obrigacao == "Folha" else "postergar")
    if data_base.weekday() >= 5 or _feriado(data_base):
        data_final = _prox_util(data_base) if regra == "postergar" else _ant_util(data_base)
    else:
        data_final = data_base
    return data_final.strftime("%d/%m/%Y")


def gerar_tarefas_parametrizacao(empresa_id, usuario_id):
    """Gera tarefas do mês atual a partir da parametrização/obrigações da
    empresa. Ignora obrigação que já tenha tarefa nesse período (evita
    duplicar se a empresa for salva de novo no mesmo mês)."""
    agora = datetime.now()
    ano, mes = agora.year, agora.month
    periodo = f"{mes:02d}/{ano}"

    with conexao() as conn:
        emp = conn.execute("SELECT nome, cnpj FROM empresas WHERE id=?", (empresa_id,)).fetchone()
        if not emp:
            return []
        emp_nome, emp_cnpj = emp["nome"], emp["cnpj"]

        param = conn.execute(
            "SELECT municipio FROM empresas_param WHERE empresa_id=?", (empresa_id,)
        ).fetchone()
        municipio = param["municipio"] if param and param["municipio"] else "Rio de Janeiro"

        obrigacoes = conn.execute(
            "SELECT setor, obrigacao, dia_venc, regra_feriado FROM empresas_obrigacoes "
            "WHERE empresa_id=? AND ativo=1", (empresa_id,),
        ).fetchall()

        ids_criados = []
        for ob in obrigacoes:
            setor, obrigacao, dia_venc, regra_feriado = ob["setor"], ob["obrigacao"], ob["dia_venc"], ob["regra_feriado"]
            ja_existe = conn.execute(
                "SELECT id FROM tarefas WHERE empresa_id=? AND obrigacao=? AND periodo=? AND origem='parametrizacao'",
                (empresa_id, obrigacao, periodo),
            ).fetchone()
            if ja_existe:
                continue

            try:
                data_venc = _calcular_venc(obrigacao, ano, mes, municipio, dia_venc, regra_feriado)
            except Exception:
                data_venc = None

            agora_str = _agora()
            cur = conn.execute(
                """INSERT INTO tarefas
                   (titulo, modelo_id, escopo, empresa, filial_nome, filial_cnpj,
                    setor, prioridade, status, criado_por, responsavel,
                    data_inicio, data_fim, data_venc, criado_em, atualizado_em,
                    origem, obrigacao, empresa_id, periodo)
                   VALUES (?,?,?,?,?,?,?,?,'A fazer',?,?,?,?,?,?,?,?,?,?,?)""",
                (obrigacao, None, "Por Empresa", emp_nome, None, emp_cnpj,
                 setor, "Normal", usuario_id, None,
                 None, None, data_venc, agora_str, agora_str,
                 "parametrizacao", obrigacao, empresa_id, periodo),
            )
            tid = cur.lastrowid
            conn.execute(
                "INSERT INTO historico (tarefa_id,usuario_id,acao,detalhe,momento) VALUES (?,?,'Criada',?,?)",
                (tid, usuario_id, f"Tarefa gerada automaticamente [Por Empresa] origem parametrizacao", agora_str),
            )
            ids_criados.append(tid)
        return ids_criados
