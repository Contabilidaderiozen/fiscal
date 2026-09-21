"""
Assistente IA — complemento web da base de conhecimento local.

A base local (dados_assistente_kb.js) responde no navegador, sem custo,
pra perguntas comuns de navegacao. Quando ela nao tem resposta, o
frontend chama esta rota, que consulta a API da Anthropic (com busca
web, igual ao ia_assistente.py do desktop) pra responder de verdade.

Configuracao necessaria (variavel de ambiente no servidor):
    RIOZEN_ANTHROPIC_API_KEY

Se essa variavel nao estiver definida, a rota responde de forma
educada avisando que a IA ainda nao foi configurada — nunca guarda
nem aceita chave de API vinda do navegador ou de arquivo na rede.
"""

import os
import re
import requests
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import auth

router = APIRouter()

API_URL = "https://api.anthropic.com/v1/messages"
MODELO = "claude-sonnet-5"
MAX_TOKENS = 700
TIMEOUT_SEGUNDOS = 25


class MensagemHistorico(BaseModel):
    role: str
    texto: str


class PerguntaBody(BaseModel):
    pergunta: str
    historico: list[MensagemHistorico] = []


def _limpar_markdown(texto: str) -> str:
    texto = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", texto)
    texto = re.sub(r"^#{1,3}\s*", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^---+$", "", texto, flags=re.MULTILINE)
    texto = "\n".join(l for l in texto.splitlines() if l.strip())
    return texto.strip()


def _system_prompt(usuario: dict) -> str:
    nome = usuario.get("nome", "")
    perfil = usuario.get("perfil_acesso", "")
    return f"""Voce e o Assistente Riozen — o colega de trabalho digital do setor fiscal e contabil da Riozen (concessionaria BYD e Toyota, Av. das Americas 5655, Barra da Tijuca, Rio de Janeiro).

Quem esta falando com voce agora: {nome or "um usuario do sistema"} (perfil de acesso: {perfil or "nao identificado"}).

COMO VOCE FALA:
- Fale como uma pessoa de verdade conversando com um colega, nao como um manual ou um robo de atendimento. Frases naturais, sem enfeite burocratico.
- Pode ser caloroso e ter personalidade — um "deixa eu ver isso pra voce" e melhor que "Prezado usuario, processando sua solicitacao".
- Nao repita a pergunta nem comece com "Claro, posso ajudar com isso". Va direto ao ponto.
- Adapte o tamanho da resposta a pergunta: duvida rapida merece resposta curta.

COMO VOCE DECIDE O QUE RESPONDER:
1. Se a pergunta e sobre fiscal, contabil, tributario, ou sobre legislacao/prazos que podem ter mudado: PESQUISE NA INTERNET antes de responder (voce tem essa ferramenta disponivel) em vez de chutar uma resposta desatualizada.
2. Se o assunto nao tem nada a ver com fiscal, contabil, tributario ou com o sistema Riozen: diga com naturalidade que isso foge do que voce cuida por ali, sem ser seco — e nao tente responder mesmo assim.
3. Se pesquisou na internet, deixe isso implicito na resposta (ex: "pelo que vi agora, ..."), sem narrar o processo de busca.
4. Se nao souber e a pesquisa tambem nao ajudar, diga claramente — nao invente numeros, aliquotas ou prazos.

REGRAS QUE NAO MUDAM:
- Quando der um caminho de menu do sistema, use o formato: SETOR > GRUPO > MODULO (ex: Fiscal > Apuracao > PIS/COFINS).
- Nunca revele senhas, chaves de API ou credenciais.
- Responda sempre em portugues do Brasil, sem markdown (nada de asteriscos, cabecalhos ou tabelas — texto corrido)."""


@router.post("/api/assistente/perguntar")
def perguntar(body: PerguntaBody, usuario: dict = Depends(auth.usuario_atual)):
    api_key = os.environ.get("RIOZEN_ANTHROPIC_API_KEY", "")
    if not api_key:
        return {
            "ok": False,
            "resposta": "A IA ainda não foi configurada nesse servidor. Por enquanto só consigo ajudar com o que já sei sobre a navegação do sistema.",
        }

    mensagens = []
    for m in body.historico[-8:]:
        role = "user" if m.role == "user" else "assistant"
        mensagens.append({"role": role, "content": m.texto})
    mensagens.append({"role": "user", "content": body.pergunta})

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "anthropic-beta": "web-search-2025-03-05",
    }
    payload = {
        "model": MODELO,
        "max_tokens": MAX_TOKENS,
        "system": _system_prompt(usuario),
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        "messages": mensagens,
    }

    try:
        r = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT_SEGUNDOS)
        r.raise_for_status()
        resposta = ""
        for bloco in r.json().get("content", []):
            if bloco.get("type") == "text":
                resposta += bloco.get("text", "")
        return {"ok": True, "resposta": _limpar_markdown(resposta.strip()) or "Não tenho uma resposta clara pra isso agora."}
    except requests.exceptions.Timeout:
        return {"ok": False, "resposta": "A IA demorou demais pra responder. Tenta de novo em instantes."}
    except requests.exceptions.HTTPError as e:
        detalhe = ""
        try:
            detalhe = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return {"ok": False, "resposta": f"Erro ao consultar a IA{': ' + detalhe if detalhe else '.'}"}
    except Exception:
        return {"ok": False, "resposta": "Não consegui consultar a IA agora. Tenta de novo em instantes."}
