/* ==========================================================================
   REFORMA TRIBUTÁRIA — RIOZEN
   Ferramenta autônoma (não depende do Riozen Fiscal rodando).
   Dados persistem no navegador local (localStorage) — cada máquina guarda
   o próprio progresso. Se abrir em outra máquina, começa do zero.
   ========================================================================== */

const CHAVE_ARMAZENAMENTO = "riozen_reforma_tributaria_v1";
const CHAVE_SESSAO = "riozen_rt_sessao"; // sessionStorage — dura só enquanto a aba estiver aberta

// Precisa ser IDÊNTICO ao _SEGREDO_REFORMA_TRIBUTARIA do painel.py.
// Serve só pra confirmar que o link de auto-login veio mesmo do painel
// (não dá pra alguém forjar a URL na mão sem saber esse segredo).
const SEGREDO_RT = "riozen-rt-2026-8mK2pXq9wZ4nR7vL";
const TOKEN_VALIDADE_SEGUNDOS = 300; // 5 minutos — depois disso, o link expira

/* ── Criptografia (Web Crypto API — nativa do navegador) ──────────────── */
async function sha256Hex(texto) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256Hex(chaveTexto, mensagem) {
  const chave = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(chaveTexto),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const assinatura = await crypto.subtle.sign("HMAC", chave, new TextEncoder().encode(mensagem));
  return [...new Uint8Array(assinatura)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/* ── Identificação (sem tela de login — acesso sempre direto) ────────────
   Se vier pelo painel (com os parâmetros de nome/login/perfil na URL),
   mostra quem é. Se abrir o arquivo direto, sem esses parâmetros, mostra
   um nome genérico — mas o acesso às ferramentas nunca fica bloqueado. */
function sessaoAtual() {
  try {
    const s = sessionStorage.getItem(CHAVE_SESSAO);
    return s ? JSON.parse(s) : null;
  } catch (e) { return null; }
}

function salvarSessao(dados) {
  try { sessionStorage.setItem(CHAVE_SESSAO, JSON.stringify(dados)); } catch (e) { /* ignora */ }
}

function limparSessao() {
  try { sessionStorage.removeItem(CHAVE_SESSAO); } catch (e) { /* ignora */ }
}

// Lê quem veio identificado do painel pela URL (sem exigir token/senha —
// só usado pra mostrar o nome certo, não é mais uma trava de acesso).
function lerIdentificacaoURL() {
  const params = new URLSearchParams(window.location.search);
  const login = params.get("login"), perfil = params.get("perfil"), nome = params.get("nome");
  if (!login && !nome) return null;
  // Limpa os parâmetros da URL depois de ler (não fica poluindo a barra de endereço)
  window.history.replaceState({}, document.title, window.location.pathname);
  return { login: login || "", perfil: perfil || "usuário", nome: nome || login || "Usuário" };
}

function identificarSessao() {
  // 1. Já tem sessão nesta aba (deu refresh na página, por exemplo)?
  const sessao = sessaoAtual();
  if (sessao) return sessao;

  // 2. Veio identificação do painel na URL?
  const doPainel = lerIdentificacaoURL();
  if (doPainel) { salvarSessao(doPainel); return doPainel; }

  // 3. Abriu o arquivo direto, sem vir do painel — segue mesmo assim.
  const generico = { login: "", perfil: "visitante", nome: "Visitante" };
  salvarSessao(generico);
  return generico;
}

function mostrarApp(sessao) {
  document.getElementById("app-conteudo").style.display = "block";
  document.getElementById("usuario-conectado-nome").textContent = `${sessao.nome} (${sessao.perfil})`;
}

/* ── Dados iniciais do Plano de Ação ──────────────────────────────────────
   Baseado no plano de ação real da Riozen para a Reforma Tributária.
   Setores usados: Fiscal, Compras, Jurídico, Comercial, Pricing, TI,
   Financeiro, RH, Controladoria, Logística, Governança.
   Status possíveis: "Pendente", "Em Andamento", "Concluído".
   ────────────────────────────────────────────────────────────────────── */
const PLANO_INICIAL = {
  lider: "",
  pmo: "",
  ultimaRevisao: "2025-10-03",
  categorias: [
    {
      num: 1,
      titulo: "Estudo de Impactos da Reforma Tributária",
      acoes: [
        { cod: "1.1", desc: "Definição de premissas para cálculo", setor: "Fiscal", status: "Pendente" },
        { cod: "1.2", desc: "Simulação de cenários AS IS e TO BE", setor: "Fiscal", status: "Pendente" },
        { cod: "1.3", desc: "Análise dos impactos", setor: "Fiscal", status: "Pendente" },
        { cod: "1.4", desc: "Apresentação interna dos resultados", setor: "Fiscal", status: "Pendente" },
        { cod: "1.5", desc: "Definições de Budget", setor: "Financeiro", status: "Pendente" },
        { cod: "1.6", desc: "Criação do Comitê de Reforma Tributária", setor: "Fiscal", status: "Pendente" },
        { cod: "1.7", desc: "Treinamento do time interno e áreas impactadas", setor: "Fiscal", status: "Pendente" },
      ],
    },
    {
      num: 2,
      titulo: "Compras e Gestão de Fornecedores",
      acoes: [
        { cod: "2.0", desc: "Identificação do regime tributário de cada Fornecedor", setor: "Fiscal", status: "Pendente" },
        { cod: "2.1", desc: "Análises dos impactos de preços líquidos x custos por item, fornecedor e região", setor: "Compras", status: "Pendente" },
        { cod: "2.2", desc: "Workshop ou cartilha de boas práticas na Reforma Tributária, com fornecedores mais representativos do Simples Nacional / MEI", setor: "Compras", status: "Pendente" },
        { cod: "2.3", desc: "Estratégia para créditos de abertura na transição (2026 e 2032)", setor: "Compras", status: "Pendente" },
        { cod: "2.4", desc: "Renegociação de contratos vigentes", setor: "Jurídico", status: "Pendente" },
        { cod: "2.5", desc: "Determinação do novo padrão de contratos com fornecedores", setor: "Jurídico", status: "Pendente" },
        { cod: "2.6", desc: "Solicitação de tributos em cadeia aos fornecedores", setor: "Compras", status: "Pendente" },
        { cod: "2.7", desc: "Acompanhamento de regularidade tributária dos fornecedores", setor: "Compras", status: "Pendente" },
        { cod: "2.8", desc: "Notificação para fornecedores que não vão gerar créditos integrais", setor: "Compras", status: "Pendente" },
        { cod: "2.9", desc: "Mudança nas políticas de compras e prazos de pagamento", setor: "Compras", status: "Pendente" },
        { cod: "2.10", desc: "Saneamento de cadastro de Fornecedores", setor: "Compras", status: "Pendente" },
        { cod: "2.11", desc: "Adequação das operações de importação — avaliar opções via trading, conta e ordem, importação direta ou nacionalização (sem II e Taxas)", setor: "Compras", status: "Pendente" },
        { cod: "2.12", desc: "Definição sobre inserção do IBS/CBS na base de ICMS, IPI, ISS nas compras", setor: "Fiscal", status: "Pendente" },
        { cod: "2.13", desc: "Identificação de compras sem documento fiscal", setor: "Compras", status: "Pendente" },
      ],
    },
    {
      num: 3,
      titulo: "Vendas e Gestão de Clientes",
      acoes: [
        { cod: "3.0", desc: "Identificação do regime tributário de cada Cliente", setor: "Fiscal", status: "Pendente" },
        { cod: "3.1", desc: "Análise dos impactos de preços líquidos x preços de venda para cliente meio de cadeia x fim de cadeia", setor: "Fiscal", status: "Pendente" },
        { cod: "3.2", desc: "Mudança no modelo de premiação e comissões sobre vendas", setor: "Comercial", status: "Pendente" },
        { cod: "3.3", desc: "Ajuste da formação do preço de venda", setor: "Pricing", status: "Pendente" },
        { cod: "3.4", desc: "Ajuste no modelo de contratos com clientes", setor: "Jurídico", status: "Pendente" },
        { cod: "3.5", desc: "Workshop com o time comercial sobre a Reforma Tributária", setor: "Fiscal", status: "Pendente" },
        { cod: "3.6", desc: "Saneamento no cadastro de Clientes", setor: "Comercial", status: "Pendente" },
        { cod: "3.7", desc: "Adequação das operações de exportação", setor: "Fiscal", status: "Pendente" },
        { cod: "3.8", desc: "Definição sobre inserção do IBS/CBS na base de ICMS, IPI, ISS", setor: "Fiscal", status: "Pendente" },
        { cod: "3.9", desc: "Identificação de operações atualmente não tributadas (ex: comodato, royalties, cashback, cartão presente, ponto de fidelidade)", setor: "Fiscal", status: "Pendente" },
      ],
    },
    {
      num: 4,
      titulo: "Mudanças em Sistemas e ERP",
      acoes: [
        { cod: "4.0", desc: "Atualizações notas SAP", setor: "TI", status: "Pendente" },
        { cod: "4.1", desc: "Definição de Budget para preparação de sistemas e ERP", setor: "TI", status: "Pendente" },
        { cod: "4.2", desc: "Preparação da equipe para a Reforma Tributária", setor: "TI", status: "Pendente" },
        { cod: "4.3", desc: "Preparação de novos campos para atender obrigações acessórias do IBS e da CBS", setor: "TI", status: "Pendente" },
        { cod: "4.4", desc: "Preparação de novos campos para atender obrigações acessórias do Imposto Seletivo, se aplicável", setor: "TI", status: "Pendente" },
        { cod: "4.5", desc: "DE/PARA de código de serviços para NBS", setor: "TI", status: "Pendente" },
        { cod: "4.6", desc: "Saneamento do cadastro de itens, por EAN/GTIN", setor: "TI", status: "Pendente" },
        { cod: "4.7", desc: "Preparação para escrituração completa de entradas (NFS-e, Faturas, Recibos, etc.)", setor: "TI", status: "Pendente" },
        { cod: "4.8", desc: "Implementação da solução de Invoice-To-Pay para escrituração completa de entradas e gestão de créditos em IVA recolhidos por fornecedores", setor: "Fiscal", status: "Pendente" },
        { cod: "4.9", desc: "Mudança na emissão de notas fiscais, para informar condição e forma de pagamento", setor: "TI", status: "Pendente" },
        { cod: "4.10", desc: "Implementação dos novos modelos de apuração e recolhimento de tributos", setor: "TI", status: "Pendente" },
        { cod: "4.11", desc: "Parâmetro para inserção (ou não) de IBS/CBS na base de ICMS, IPI, ISS", setor: "TI", status: "Pendente" },
      ],
    },
    {
      num: 5,
      titulo: "Impactos Financeiros e Orçamentários",
      acoes: [
        { cod: "5.1", desc: "Análise de impacto em capital de giro e necessidade de caixa ano a ano, durante o período de transição", setor: "Financeiro", status: "Pendente" },
        { cod: "5.2", desc: "Atualização de relatórios gerenciais em FP&A", setor: "Financeiro", status: "Pendente" },
        { cod: "5.3", desc: "Implementação de controles internos para nova realidade fiscal", setor: "Financeiro", status: "Pendente" },
        { cod: "5.4", desc: "Criação das novas contas contábeis e seus parâmetros", setor: "Financeiro", status: "Pendente" },
        { cod: "5.5", desc: "Renegociação de prazos com bancos, clientes e fornecedores", setor: "Financeiro", status: "Pendente" },
        { cod: "5.6", desc: "Atualização de budget de 1, 3 e 5 anos, já prevendo os novos tributos e seus impactos", setor: "Financeiro", status: "Pendente" },
      ],
    },
    {
      num: 6,
      titulo: "Ampliação de Créditos Tributários",
      acoes: [
        { cod: "6.1", desc: "Estratégia para créditos de abertura na transição", setor: "Fiscal", status: "Pendente" },
        { cod: "6.2", desc: "Validar benefícios em acordo ou convenção coletiva para garantia do crédito", setor: "RH", status: "Pendente" },
        { cod: "6.3", desc: "Análise de créditos tributários em potencial", setor: "Fiscal", status: "Pendente" },
        { cod: "6.4", desc: "Implementação de créditos", setor: "Fiscal", status: "Pendente" },
        { cod: "6.5", desc: "Gestão de ressarcimento de eventuais créditos já acumulados", setor: "Fiscal", status: "Pendente" },
        { cod: "6.6", desc: "Planejamento tributário para créditos acumulados sem previsão de restituição/compensação em 5 anos (ex: ICMS por diferimento)", setor: "Fiscal", status: "Pendente" },
        { cod: "6.7", desc: "Determinação dos melhores modelos para ampliar o creditamento de IBS e CBS", setor: "Fiscal", status: "Pendente" },
        { cod: "6.8", desc: "Determinação do melhor momento para troca de créditos atuais pela nova sistemática tributária", setor: "Fiscal", status: "Pendente" },
      ],
    },
    {
      num: 7,
      titulo: "Benefícios e Incentivos Fiscais",
      acoes: [
        { cod: "7.1", desc: "Levantamento detalhado dos montantes perdidos de benefícios e incentivos fiscais", setor: "Fiscal", status: "Pendente" },
        { cod: "7.2", desc: "Instrumentalização dos pedidos de restituição", setor: "Fiscal", status: "Pendente" },
        { cod: "7.3", desc: "Judicialização para ampliação dos valores a serem restituídos", setor: "Jurídico", status: "Pendente" },
        { cod: "7.4", desc: "Recebimento e gestão financeira dos créditos", setor: "Financeiro", status: "Pendente" },
      ],
    },
    {
      num: 8,
      titulo: "Controladoria",
      acoes: [
        { cod: "8.1", desc: 'Definir método de contabilização — contas transitórias ou definitivas para crédito de CBS e IBS, já que o crédito é uma expectativa até a confirmação financeira', setor: "Controladoria", status: "Pendente" },
        { cod: "8.2", desc: "Criar novas contas no ativo, passivo e dedução de receita, para CBS, IBS e IS (se aplicável)", setor: "Controladoria", status: "Pendente" },
        { cod: "8.3", desc: 'Levantar diferenças contábeis sujeitas ao "débito presumido" (art. 335 da Lei Complementar 214/2025)', setor: "Controladoria", status: "Pendente" },
        { cod: "8.4", desc: "Avaliar Cost Sharing, contrato, reembolso (em nome próprio ou de terceiros) e impactos em IVA", setor: "Controladoria", status: "Pendente" },
        { cod: "8.5", desc: "Acrescentar na rotina de conciliação contábil as novas contas de CBS, IBS e IS, com os devidos responsáveis", setor: "Compras", status: "Pendente" },
        { cod: "8.6", desc: "Mapear possíveis diferenças de estoques e estratégias para minimizar impactos tributários na transição", setor: "Compras", status: "Pendente" },
        { cod: "8.7", desc: "Avaliar diferimento de receitas e impacto em fluxo de caixa", setor: "Controladoria", status: "Pendente" },
      ],
    },
    {
      num: 9,
      titulo: "Logística",
      acoes: [
        { cod: "9.1", desc: "Análise do impacto tributário na cadeia de valor", setor: "Logística", status: "Pendente" },
        { cod: "9.2", desc: "Armazenagem, transporte, produção, distribuição, inbound e outbound", setor: "Logística", status: "Pendente" },
        { cod: "9.3", desc: "Redesenho das operações, com impacto financeiro efetivo", setor: "Financeiro", status: "Pendente" },
        { cod: "9.4", desc: "Mudança da estrutura da cadeia de valor", setor: "Logística", status: "Pendente" },
        { cod: "9.5", desc: "Mudança de local de fábricas, x-docking e centros de distribuição", setor: "Logística", status: "Pendente" },
      ],
    },
    {
      num: 10,
      titulo: "Governança e/ou Compliance",
      acoes: [
        { cod: "10.1", desc: "Formalização da Governança: papel dos líderes, responsabilidades e regras básicas em caso de mudança de cenário", setor: "Governança", status: "Pendente" },
        { cod: "10.2", desc: "Revisar as regras de compliance das áreas afetadas — reescrever processos, se necessário", setor: "Governança", status: "Pendente" },
        { cod: "10.3", desc: "Mapa de riscos operacionais pensando na organização como um todo", setor: "Governança", status: "Pendente" },
        { cod: "10.4", desc: "Garantir a formalização do avanço, com reports mensais ou trimestrais, via PMO ou TMO", setor: "Governança", status: "Pendente" },
      ],
    },
  ],
};

const CORES_SETOR = {
  "Fiscal": "#00c4ff", "Compras": "#e8a33d", "Jurídico": "#c77dff",
  "Comercial": "#ff8fa3", "Pricing": "#ff8fa3", "TI": "#4d7ea8",
  "Financeiro": "#35d399", "RH": "#f4d35e", "Controladoria": "#f4a259",
  "Logística": "#7c8ba1", "Governança": "#e56b6f",
};

/* ── Estado ────────────────────────────────────────────────────────────── */
let estado = { plano: null, filtroSetor: "Todos", filtroStatus: "Todos", ataAberta: new Set() };

function carregarEstado() {
  try {
    const salvo = localStorage.getItem(CHAVE_ARMAZENAMENTO);
    if (salvo) {
      estado.plano = JSON.parse(salvo);
      _garantirObservacoes();
      return;
    }
  } catch (e) { /* localStorage indisponível — segue com o padrão */ }
  estado.plano = JSON.parse(JSON.stringify(PLANO_INICIAL));
  _garantirObservacoes();
}

function _garantirObservacoes() {
  // Ações antigas (salvas antes desse recurso existir) não têm o campo —
  // garante que toda ação tenha a lista, mesmo vazia.
  for (const cat of estado.plano.categorias) {
    for (const acao of cat.acoes) {
      if (!Array.isArray(acao.observacoes)) acao.observacoes = [];
    }
  }
}

function salvarEstado() {
  try {
    localStorage.setItem(CHAVE_ARMAZENAMENTO, JSON.stringify(estado.plano));
  } catch (e) { /* ambiente sem localStorage (ex: file:// bloqueado) — segue sem salvar */ }
}

function todasAcoes() {
  return estado.plano.categorias.flatMap((c) => c.acoes.map((a) => ({ ...a, categoria: c })));
}

function todosSetores() {
  return [...new Set(todasAcoes().map((a) => a.setor))].sort();
}

/* ── Cálculo de progresso ──────────────────────────────────────────────── */
function progresso(acoes) {
  if (acoes.length === 0) return 0;
  const concluidas = acoes.filter((a) => a.status === "Concluído").length;
  return Math.round((concluidas / acoes.length) * 100);
}

/* ── Renderização ──────────────────────────────────────────────────────── */
function iconeStatus(status) {
  if (status === "Concluído") return "●";
  if (status === "Em Andamento") return "◐";
  return "○";
}

function classeStatus(status) {
  if (status === "Concluído") return "status-concluido";
  if (status === "Em Andamento") return "status-andamento";
  return "status-pendente";
}

function renderResumo() {
  const acoes = todasAcoes();
  const pct = progresso(acoes);
  const concluidas = acoes.filter((a) => a.status === "Concluído").length;
  const andamento = acoes.filter((a) => a.status === "Em Andamento").length;
  const pendentes = acoes.filter((a) => a.status === "Pendente").length;

  document.getElementById("resumo-pct").textContent = pct + "%";
  document.getElementById("resumo-barra-preenchida").style.width = pct + "%";
  document.getElementById("resumo-concluidas").textContent = concluidas;
  document.getElementById("resumo-andamento").textContent = andamento;
  document.getElementById("resumo-pendentes").textContent = pendentes;
  document.getElementById("resumo-total").textContent = acoes.length;
}

function renderFiltros() {
  const selSetor = document.getElementById("filtro-setor");
  const setorAtual = selSetor.value || "Todos";
  selSetor.innerHTML = '<option value="Todos">Todos os setores</option>' +
    todosSetores().map((s) => `<option value="${s}">${s}</option>`).join("");
  selSetor.value = estado.filtroSetor;
}

function acaoPassaFiltro(acao) {
  const setorOk = estado.filtroSetor === "Todos" || acao.setor === estado.filtroSetor;
  const statusOk = estado.filtroStatus === "Todos" || acao.status === estado.filtroStatus;
  return setorOk && statusOk;
}

function renderCategorias() {
  const container = document.getElementById("categorias");
  const abertasAntes = new Set(
    [...container.querySelectorAll("details.categoria[open]")].map((d) => d.dataset.num)
  );
  container.innerHTML = "";

  estado.plano.categorias.forEach((cat) => {
    const acoesFiltradas = cat.acoes.filter(acaoPassaFiltro);
    if (acoesFiltradas.length === 0) return;

    const pct = progresso(cat.acoes);
    const bloco = document.createElement("details");
    bloco.className = "categoria";
    bloco.dataset.num = cat.num;
    const forcarAberta = estado.filtroSetor !== "Todos" || estado.filtroStatus !== "Todos";
    bloco.open = forcarAberta || abertasAntes.has(String(cat.num));

    bloco.innerHTML = `
      <summary class="categoria-cabecalho">
        <span class="categoria-num">${String(cat.num).padStart(2, "0")}</span>
        <span class="categoria-titulo">${cat.titulo}</span>
        <span class="categoria-progresso">
          <span class="mini-barra"><span class="mini-barra-preenchida" style="width:${pct}%"></span></span>
          <span class="categoria-pct">${pct}%</span>
        </span>
      </summary>
      <div class="categoria-corpo">
        ${acoesFiltradas.map((a) => renderLinhaAcao(a, cat.num)).join("")}
      </div>
    `;
    container.appendChild(bloco);
  });

  if (container.children.length === 0) {
    container.innerHTML = '<p class="vazio">Nenhuma ação encontrada com esse filtro.</p>';
  }
}

function escaparHTML(texto) {
  const div = document.createElement("div");
  div.textContent = texto;
  return div.innerHTML;
}

function formatarDataHora(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("pt-BR") + " às " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function renderLinhaAcao(acao, catNum) {
  const cor = CORES_SETOR[acao.setor] || "#7c8ba1";
  const n = acao.observacoes.length;
  const ataEstaAberta = estado.ataAberta.has(acao.cod);

  const linha = `
    <div class="acao" data-cod="${acao.cod}">
      <span class="acao-cod">${acao.cod}</span>
      <span class="acao-desc">${escaparHTML(acao.desc)}</span>
      <span class="acao-setor" style="--cor-setor:${cor}">${acao.setor}</span>
      <button class="acao-ata-toggle ${n > 0 ? "tem-registro" : ""}" data-cod="${acao.cod}" title="Registros da ação (ATA)">
        📝 ${n > 0 ? n : ""}
      </button>
      <button class="acao-status ${classeStatus(acao.status)}" data-cod="${acao.cod}" title="Clique para mudar o status">
        <span class="acao-status-icone">${iconeStatus(acao.status)}</span>
        <span class="acao-status-texto">${acao.status}</span>
      </button>
    </div>
  `;

  if (!ataEstaAberta) return linha;

  const listaRegistros = acao.observacoes.length
    ? acao.observacoes.map((o) => `
        <div class="ata-registro">
          <span class="ata-registro-data">${formatarDataHora(o.data)}</span>
          <span class="ata-registro-texto">${escaparHTML(o.texto)}</span>
        </div>
      `).join("")
    : '<p class="ata-vazia">Nenhum registro ainda — a primeira anotação começa o histórico desta ação.</p>';

  const painelAta = `
    <div class="ata-painel" data-cod="${acao.cod}">
      <div class="ata-registros">${listaRegistros}</div>
      <div class="ata-novo">
        <textarea class="ata-novo-texto" data-cod="${acao.cod}"
          placeholder="Ex: Reunião de 21/08 — Fulano ficou responsável por levantar X até dia 28."></textarea>
        <button class="ata-novo-botao" data-cod="${acao.cod}">Registrar</button>
      </div>
      <p class="ata-aviso">Os registros ficam aqui como uma ATA — servem de histórico e não podem ser apagados.</p>
    </div>
  `;

  return linha + painelAta;
}

function renderTudo() {
  renderResumo();
  renderFiltros();
  renderCategorias();
  salvarEstado();
}

/* ── Interações ────────────────────────────────────────────────────────── */
const CICLO_STATUS = ["Pendente", "Em Andamento", "Concluído"];

function alternarStatus(cod) {
  for (const cat of estado.plano.categorias) {
    const acao = cat.acoes.find((a) => a.cod === cod);
    if (acao) {
      const i = CICLO_STATUS.indexOf(acao.status);
      acao.status = CICLO_STATUS[(i + 1) % CICLO_STATUS.length];
      return;
    }
  }
}

function registrarObservacao(cod, texto) {
  for (const cat of estado.plano.categorias) {
    const acao = cat.acoes.find((a) => a.cod === cod);
    if (acao) {
      // Só acrescenta ao final — nunca edita nem remove um registro existente.
      acao.observacoes.push({ data: new Date().toISOString(), texto });
      return;
    }
  }
}

function inicializarApp() {
  carregarEstado();
  renderTudo();

  document.getElementById("categorias").addEventListener("click", (ev) => {
    const btnStatus = ev.target.closest(".acao-status");
    if (btnStatus) {
      alternarStatus(btnStatus.dataset.cod);
      renderTudo();
      return;
    }

    const btnAta = ev.target.closest(".acao-ata-toggle");
    if (btnAta) {
      const cod = btnAta.dataset.cod;
      if (estado.ataAberta.has(cod)) estado.ataAberta.delete(cod);
      else estado.ataAberta.add(cod);
      renderCategorias();
      return;
    }

    const btnNovo = ev.target.closest(".ata-novo-botao");
    if (btnNovo) {
      const cod = btnNovo.dataset.cod;
      const campo = document.querySelector(`.ata-novo-texto[data-cod="${cod}"]`);
      const texto = campo.value.trim();
      if (!texto) return;
      registrarObservacao(cod, texto);
      renderTudo();
    }
  });

  document.getElementById("filtro-setor").addEventListener("change", (ev) => {
    estado.filtroSetor = ev.target.value;
    renderCategorias();
  });

  document.getElementById("filtro-status").addEventListener("change", (ev) => {
    estado.filtroStatus = ev.target.value;
    renderCategorias();
  });

  document.getElementById("btn-resetar").addEventListener("click", () => {
    if (confirm("Isso apaga todo o progresso salvo neste navegador e volta ao plano original. Confirma?")) {
      localStorage.removeItem(CHAVE_ARMAZENAMENTO);
      carregarEstado();
      renderTudo();
    }
  });

  // Navegação entre a visão geral e as áreas por setor
  document.querySelectorAll(".aba-nav").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".aba-nav").forEach((b) => b.classList.remove("ativa"));
      document.querySelectorAll(".aba-conteudo").forEach((c) => c.classList.remove("ativa"));
      btn.classList.add("ativa");
      document.getElementById(btn.dataset.alvo).classList.add("ativa");
    });
  });
}

/* ── Conteúdo dos tooltips — o que já levantamos da LC 214/2025 ─────────── */
const _EVENTOS_ANO = {
  2026: "Fase de teste: IBS+CBS com alíquotas simbólicas (0,10%+0,90%) rodando em paralelo com o sistema atual (ICMS, PIS/COFINS continuam normalmente). Sem impacto financeiro real ainda.",
  2027: "CBS substitui de vez o PIS/COFINS (alíquota de referência 8,4%) — inclusive o fim do regime monofásico de veículos/autopeças/pneus (Lei 10.485/2002). Imposto Seletivo entra em vigor. Redução de 50% em vendas ao governo via licitação.",
  2028: "Continuação da fase de transição — IBS ainda pequeno (0,10%), ICMS/ISS continuam sendo a base principal da tributação sobre consumo.",
  2029: "IBS começa a subir de verdade, substituindo o ICMS de forma gradual — início da migração efetiva entre os dois sistemas.",
  2030: "Transição gradual continua: IBS sobe, ICMS cai, na mesma proporção, ano a ano.",
  2031: "Transição gradual continua: IBS sobe, ICMS cai, na mesma proporção, ano a ano.",
  2032: "Último ano da fase de transição gradual — véspera do sistema completo entrar em vigor.",
  2033: "Sistema completo: ICMS e ISS deixam de existir de vez. Só resta IBS + CBS + Imposto Seletivo.",
};

// Só entra aqui quando temos um prazo/ação específica pra aquele mês —
// os outros meses do ano usam o texto geral do ano mesmo (_EVENTOS_ANO).
const _EVENTOS_MES = {
  "2027-5": "Prazo final pra apurar o crédito presumido de 9,25% sobre o estoque de veículos/autopeças/pneus existente em 01/01/2027 (Art. 381) — até junho.",
};

function _textoTooltipAno(ano) {
  const evento = _EVENTOS_ANO[ano];
  return evento ? `<b>${ano}</b>${evento}` : `<b>${ano}</b>Sem destaque específico registrado ainda.`;
}

function _textoTooltipMes(ano, indiceMes) {
  const chave = `${ano}-${indiceMes}`;
  const especifico = _EVENTOS_MES[chave];
  const rotulo = `${_MESES_PT[indiceMes]}/${ano}`;
  if (especifico) return `<b>${rotulo}</b>${especifico}`;
  const geral = _EVENTOS_ANO[ano] || "Sem destaque específico registrado ainda.";
  return `<b>${rotulo}</b>${geral}`;
}

function _iniciarTooltipsLinhaTempo() {
  const tooltip = document.getElementById("linha-tempo-tooltip");

  function mostrar(ev, html) {
    tooltip.innerHTML = html;
    tooltip.classList.add("visivel");
    const marco = ev.target.closest(".marco");
    const container = document.getElementById("linha-tempo-container");
    const rectMarco = marco.getBoundingClientRect();
    const rectContainer = container.getBoundingClientRect();
    tooltip.style.left = (rectMarco.left - rectContainer.left + rectMarco.width / 2) + "px";
  }
  function esconder() {
    tooltip.classList.remove("visivel");
  }

  document.getElementById("marcos-anos").addEventListener("mouseover", (ev) => {
    const marco = ev.target.closest(".marco");
    if (!marco) return;
    mostrar(ev, _textoTooltipAno(parseInt(marco.dataset.ano, 10)));
  });
  document.getElementById("marcos-anos").addEventListener("mouseout", esconder);

  // Meses são recriados toda vez que a visão muda — usa delegação no pai,
  // que continua o mesmo elemento mesmo quando o innerHTML é trocado.
  document.getElementById("marcos-meses").addEventListener("mouseover", (ev) => {
    const marco = ev.target.closest(".marco");
    if (!marco) return;
    const indice = [...marco.parentElement.children].indexOf(marco);
    const ano = Math.max(2026, Math.min(2033, new Date().getFullYear()));
    mostrar(ev, _textoTooltipMes(ano, indice));
  });
  document.getElementById("marcos-meses").addEventListener("mouseout", esconder);
}

function inicializar() {
  const sessao = identificarSessao();
  mostrarApp(sessao);
  inicializarApp();
  _iniciarLinhaTempo();
  _iniciarTooltipsLinhaTempo();
}

/* ── Linha do tempo — dinâmica de verdade, calculada pela data real ──────
   Ano/mês atual e % de progresso são recalculados automaticamente (a cada
   hora, sem precisar dar F5) usando new Date(). A posição é calculada por
   INDICE de marco + fracao dentro do periodo atual (nao por "dias corridos
   / dias totais"), pra bater exatamente com os marcos igualmente espacados
   na tela — assim, no dia 1 de cada mes/ano a barra ja chega exatamente no
   marco correspondente, e vai avancando dali pra frente conforme os dias
   passam. Clicar alterna entre a visao por ano (2026-2033) e por mes (do
   ano atual). */
const _MESES_PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
let _mostrandoMeses = false;

const _ANO_INICIO_LINHA = 2026;
const _ANO_FIM_LINHA = 2033;

function _atualizarLinhaTempoAnos() {
  const hoje = new Date();
  const anoClamp = Math.max(_ANO_INICIO_LINHA, Math.min(_ANO_FIM_LINHA, hoje.getFullYear()));
  const indice = anoClamp - _ANO_INICIO_LINHA; // 0 (2026) .. 7 (2033)

  const inicioAno = new Date(anoClamp, 0, 1);
  const fimAno = new Date(anoClamp + 1, 0, 1);
  const fracaoDentro = hoje.getFullYear() === anoClamp
    ? (hoje.getTime() - inicioAno.getTime()) / (fimAno.getTime() - inicioAno.getTime())
    : (hoje.getFullYear() > anoClamp ? 1 : 0);

  const totalIndices = _ANO_FIM_LINHA - _ANO_INICIO_LINHA; // 7 intervalos entre 8 marcos
  const pct = Math.max(0, Math.min(100, ((indice + fracaoDentro) / totalIndices) * 100));
  document.getElementById("progresso-anos").style.width = pct + "%";

  const anoAtual = hoje.getFullYear();
  document.querySelectorAll("#marcos-anos .marco").forEach((el) => {
    el.classList.toggle("atual", parseInt(el.dataset.ano, 10) === anoAtual);
  });
}

function _atualizarLinhaTempoMeses() {
  const hoje = new Date();
  const anoAtual = hoje.getFullYear();
  const anoExibido = Math.max(_ANO_INICIO_LINHA, Math.min(_ANO_FIM_LINHA, anoAtual));
  const dentroDoAnoAtual = anoExibido === anoAtual;

  const mesIndice = dentroDoAnoAtual ? hoje.getMonth() : 0;
  const diasNoMes = new Date(anoExibido, mesIndice + 1, 0).getDate();
  const fracaoDentroMes = dentroDoAnoAtual
    ? (hoje.getDate() - 1 + hoje.getHours() / 24) / diasNoMes
    : 0;

  const totalIndices = 11; // 11 intervalos entre os 12 marcos (Jan..Dez)
  const pct = Math.max(0, Math.min(100, ((mesIndice + fracaoDentroMes) / totalIndices) * 100));
  document.getElementById("progresso-meses").style.width = pct + "%";

  const cont = document.getElementById("marcos-meses");
  cont.innerHTML = _MESES_PT.map((m, i) => {
    const ativo = dentroDoAnoAtual && i === hoje.getMonth();
    return `<span class="marco${ativo ? " atual" : ""}">${m}</span>`;
  }).join("");

  const dica = document.getElementById("linha-tempo-dica");
  dica.textContent = dentroDoAnoAtual
    ? `${anoExibido} — clique pra ver os anos ▾`
    : `${anoExibido} (mais próximo do intervalo 2026-2033) — clique pra ver os anos ▾`;
}

function _iniciarLinhaTempo() {
  _atualizarLinhaTempoAnos();

  document.getElementById("linha-tempo-container").addEventListener("click", () => {
    _mostrandoMeses = !_mostrandoMeses;
    document.getElementById("linha-tempo-anos").style.display = _mostrandoMeses ? "none" : "block";
    document.getElementById("linha-tempo-meses").style.display = _mostrandoMeses ? "block" : "none";
    if (_mostrandoMeses) {
      _atualizarLinhaTempoMeses();
    } else {
      document.getElementById("linha-tempo-dica").textContent = "clique pra ver por mês ▾";
    }
  });

  // Recalcula sozinha de tempos em tempos, sem precisar recarregar a pagina.
  setInterval(() => {
    if (_mostrandoMeses) _atualizarLinhaTempoMeses();
    else _atualizarLinhaTempoAnos();
  }, 60 * 60 * 1000); // a cada hora
}

document.addEventListener("DOMContentLoaded", inicializar);
