# Sistema Riozen (web) — base inicial

## O que tem aqui
Esqueleto funcional: login + navegacao (Inicio -> Fiscal/Contabil/Geral),
testado ponta a ponta (login invalido, login valido, sessao, perfil de
acesso, logout). Os MODULOS em si (Apuracao, NFS-e, Reforma Tributaria,
NCM/cClassTrib etc.) ainda sao placeholders "Em breve" — entram nas
proximas etapas.

## Como rodar (no servidor Windows)

1. Copiar a pasta inteira `SistemaRiozen` pra dentro de `Z:\` (ou onde
   preferir na rede).
2. Instalar Python 3.11+ no servidor, se ainda nao tiver.
3. Abrir um terminal na pasta `SistemaRiozen\backend` e rodar:
   ```
   pip install -r requirements.txt
   ```
4. Definir duas variaveis de ambiente (permanentes, via
   "Editar variaveis de ambiente do sistema" no Windows):
   - `RIOZEN_DB_PATH` = `Z:\Tarefas\tarefas_riozen.db`  (o banco JA
     existente, mesmo do painel.py — nao eh um banco novo)
   - `RIOZEN_SECRET_KEY` = uma string aleatoria longa (chave de
     assinatura dos cookies de sessao — troque o valor padrao do
     auth.py por essa variavel antes de ir pra producao)
5. Testar rodando manualmente primeiro:
   ```
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   e abrindo `http://NOME-DO-SERVIDOR:8000` de outro PC da rede.
6. Se abrir e logar normal, aí sim configurar como servico permanente
   (NSSM ou equivalente) pra nao depender de terminal aberto.
7. Em cada PC, criar um atalho na area de trabalho apontando pra
   `http://NOME-DO-SERVIDOR:8000`.

## Pontos de atencao (nao esquecer)

- O login usa a MESMA tabela `usuarios` e o MESMO hash de senha
  (SHA-256) que o painel.py ja usa hoje — ninguem precisa trocar senha.
- NAO portei o usuario `adm/adm123` fixo no codigo do painel.py (era
  uma senha hardcoded, arriscado numa pasta de rede). Se quiser um
  superadmin separado, crie um usuario normal na tabela `usuarios` com
  `perfil='admin'`.
- Antes de ir pra producao de verdade: trocar `RIOZEN_SECRET_KEY` pra
  um valor unico e secreto (nao deixar o padrao do codigo).

## Reforma Tributaria — integrada

A ferramenta de Reforma Tributaria (frontend/reforma_tributaria/) foi
plugada no sistema. Ela e 100% independente do backend (sem chamada de
API), entao so precisa dos arquivos estarem no lugar certo.

PENDENTE: falta o arquivo real `dados_imposto_seletivo.js` (a ferramenta
de Imposto Seletivo esta rodando com uma lista vazia por enquanto — nao
quebra, so nao tem dado nenhum). Assim que tiver o arquivo real, e so
substituir o que esta em frontend/reforma_tributaria/dados_imposto_seletivo.js
e recarregar a pagina (sem precisar reiniciar o servico).

Removida a linha <script src="usuarios.js"> do index.html original —
era uma trava de login antiga ja desativada no proprio codigo (nao e
mais referenciada em lugar nenhum), e o arquivo nem tinha sido enviado.

## Assistente flutuante — instalado

Mascote animado (o "R") com chat, flutuante em todas as telas logadas
(painel principal + Reforma Tributaria). Responde em duas camadas:

1. BASE LOCAL (frontend/static/js/dados_assistente_kb.js) — respostas
   prontas pra perguntas de navegacao, sem custo, sem internet. Pra
   adicionar pergunta nova, e so editar esse arquivo (formato comentado
   nele mesmo) e dar F5 — nao precisa reiniciar o servico.

2. IA DE VERDADE (backend/routers/assistente.py) — usada so quando a
   base local nao tem resposta. Chama a API da Anthropic com busca web,
   igual ao ia_assistente.py do desktop.

### IMPORTANTE — sobre a chave de API

O arquivo config_ia.json que veio no upload tinha uma chave de API
REAL, em texto puro. Essa chave NAO foi usada em nada aqui — recomendo
fortemente revogar ela no console da Anthropic e gerar uma nova antes
de configurar o servidor.

A chave nova NUNCA deve ir num arquivo dentro da pasta de rede
(Z:\Riozen_Fiscal\...) — vai direto como variavel de ambiente do
servidor, do lado do RIOZEN_DB_PATH e RIOZEN_SECRET_KEY que ja existem:

    RIOZEN_ANTHROPIC_API_KEY = sua-chave-nova-aqui

Sem essa variavel definida, o assistente continua funcionando
normalmente pra perguntas de navegacao (base local) — so avisa
educadamente que a parte de IA ainda nao foi configurada quando cai
nesse caso.
