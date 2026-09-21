/* ==========================================================================
   ASSISTENTE FLUTUANTE — RIOZEN
   Monta sozinho (nao precisa de HTML no corpo da pagina, so incluir este
   script + o assistente.css + o dados_assistente_kb.js). Funciona em
   qualquer pagina do sistema que tenha sessao ativa.

   Fluxo por categoria: ao abrir pela 1a vez, mostra um menu com os
   assuntos definidos em CATEGORIAS_ASSISTENTE (dados_assistente_kb.js).
   Depois de escolher uma categoria, as perguntas seguintes buscam so
   dentro dela (BASE_CONHECIMENTO_ASSISTENTE[categoriaId]) antes de cair
   pra IA. Digitar "menu" a qualquer momento volta pro menu de assuntos.
   ========================================================================== */

(function () {
  const CAMINHO_FRAMES = "/static/img/assistente/";

  // Cada estado tem sua sequencia de frames (nomes exatamente como enviados).
  const ESTADOS = {
    idle:  { frames: 6, prefixo: "avatar_idle_",  intervalo: 260, loop: true },
    blink: { frames: 5, prefixo: "avatar_blink_", intervalo: 70,  loop: false },
    happy: { frames: 6, prefixo: "avatar_happy_", intervalo: 90,  loop: false },
    talk:  { frames: 8, prefixo: "avatar_talk_",  intervalo: 110, loop: true },
    think: { frames: 6, prefixo: "avatar_think_", intervalo: 180, loop: true },
    wave:  { frames: 8, prefixo: "avatar_wave_",  intervalo: 90,  loop: false },
    walk:  { frames: 8, prefixo: "avatar_walk_",  intervalo: 100, loop: true },
  };

  function caminhoFrame(estado, indice) {
    const cfg = ESTADOS[estado];
    const n = String(indice).padStart(2, "0");
    return `${CAMINHO_FRAMES}${cfg.prefixo}${n}.png`;
  }

  /* ── Controlador de animacao ──────────────────────────────────────────── */
  function criarAnimador(imgEl) {
    let timerId = null;
    let estadoAtual = null;

    function pararTimer() {
      if (timerId) { clearInterval(timerId); timerId = null; }
    }

    // Toca um estado. Se loop=false, volta pro estado indicado em "depois"
    // (ou "idle" por padrao) ao terminar a sequencia.
    function tocar(nomeEstado, depois) {
      const cfg = ESTADOS[nomeEstado];
      if (!cfg) return;
      pararTimer();
      estadoAtual = nomeEstado;
      let i = 0;
      imgEl.src = caminhoFrame(nomeEstado, i);

      timerId = setInterval(() => {
        i++;
        if (i >= cfg.frames) {
          if (cfg.loop) {
            i = 0;
          } else {
            pararTimer();
            tocar(depois || "idle");
            return;
          }
        }
        imgEl.src = caminhoFrame(nomeEstado, i);
      }, cfg.intervalo);
    }

    // Pisca de vez em quando durante o idle, pra parecer vivo.
    function iniciarIdleComPiscadas() {
      tocar("idle");
      setInterval(() => {
        if (estadoAtual === "idle") tocar("blink", "idle");
      }, 4000 + Math.random() * 4000);
    }

    return { tocar, iniciarIdleComPiscadas, get estadoAtual() { return estadoAtual; } };
  }

  /* ── Montagem do DOM ──────────────────────────────────────────────────── */
  function montarWidget() {
    if (document.getElementById("assistente-riozen-raiz")) return; // ja existe

    const raiz = document.createElement("div");
    raiz.id = "assistente-riozen-raiz";
    raiz.innerHTML = `
      <div class="ar-painel" id="ar-painel">
        <div class="ar-cabecalho">
          <div class="ar-avatar-mini"><img id="ar-avatar-painel" src="${caminhoFrame("idle", 0)}" alt=""></div>
          <div class="ar-cabecalho-texto">
            <div class="ar-cabecalho-nome">Assistente Riozen</div>
            <div class="ar-cabecalho-status" id="ar-status">online</div>
          </div>
          <button class="ar-fechar" id="ar-fechar" title="Fechar">&times;</button>
        </div>
        <div class="ar-mensagens" id="ar-mensagens"></div>
        <div class="ar-rodape">
          <textarea class="ar-input" id="ar-input" rows="1" placeholder="Pergunte alguma coisa..."></textarea>
          <button class="ar-enviar" id="ar-enviar">Enviar</button>
        </div>
      </div>
      <button class="ar-botao" id="ar-botao" title="Assistente Riozen — arraste pra mover">
        <img id="ar-avatar-botao" src="${caminhoFrame("idle", 0)}" alt="Assistente">
        <span class="ar-badge-nao-lida" id="ar-badge"></span>
        <span class="ar-fechar-avatar" id="ar-fechar-avatar" title="Esconder assistente">&times;</span>
      </button>
    `;
    document.body.appendChild(raiz);

    const reabrir = document.createElement("button");
    reabrir.id = "ar-reabrir";
    reabrir.className = "ar-reabrir";
    reabrir.innerHTML = `<img src="${caminhoFrame("idle", 0)}" alt=""> Assistente`;
    document.body.appendChild(reabrir);

    return raiz;
  }

  /* ── Estado da conversa ───────────────────────────────────────────────── */
  let historico = []; // [{role: "user"|"assistant", texto: "..."}]
  let aberto = false;
  let primeiraAberturaFeita = false;
  let usuarioAtual = null;
  let categoriaAtual = null; // id da categoria escolhida no menu (ou null = nenhuma ainda)

  const CHAVE_POS = "riozen_assistente_pos";
  const CHAVE_OCULTO = "riozen_assistente_oculto";

  function mostrarMenuCategorias(mensagemAntes) {
    const box = document.getElementById("ar-mensagens");
    if (mensagemAntes) addMensagemDOM(mensagemAntes, "assistant");

    const wrap = document.createElement("div");
    wrap.className = "ar-menu-categorias";
    (typeof CATEGORIAS_ASSISTENTE !== "undefined" ? CATEGORIAS_ASSISTENTE : []).forEach((cat) => {
      const btn = document.createElement("button");
      btn.className = "ar-chip-categoria";
      btn.textContent = cat.rotulo;
      btn.addEventListener("click", () => escolherCategoria(cat));
      wrap.appendChild(btn);
    });
    box.appendChild(wrap);
    box.scrollTop = box.scrollHeight;
  }

  function escolherCategoria(cat) {
    categoriaAtual = cat.id;
    addMensagemDOM(cat.rotulo, "user");
    if (cat.promptEscolha) {
      addMensagemDOM(cat.promptEscolha, "assistant");
    }
  }

  /* ── Arrastar o widget pra qualquer posicao da tela ───────────────────── */
  function tornarArrastavel(raiz, botao) {
    let arrastando = false;
    let moveu = false;
    let offX = 0, offY = 0;

    function aplicarPosicao(left, top) {
      const w = raiz.offsetWidth || 78;
      const h = raiz.offsetHeight || 78;
      const maxLeft = window.innerWidth - w - 6;
      const maxTop = window.innerHeight - h - 6;
      left = Math.max(6, Math.min(maxLeft, left));
      top = Math.max(6, Math.min(maxTop, top));
      raiz.style.left = left + "px";
      raiz.style.top = top + "px";
      raiz.style.right = "auto";
      raiz.style.bottom = "auto";
      return { left, top };
    }

    // Restaura posicao salva, se houver.
    try {
      const salvo = JSON.parse(localStorage.getItem(CHAVE_POS) || "null");
      if (salvo && typeof salvo.left === "number") {
        aplicarPosicao(salvo.left, salvo.top);
      }
    } catch (e) { /* ignora */ }

    botao.addEventListener("pointerdown", (ev) => {
      if (ev.target.id === "ar-fechar-avatar") return; // deixa o X funcionar
      arrastando = true;
      moveu = false;
      const rect = raiz.getBoundingClientRect();
      offX = ev.clientX - rect.left;
      offY = ev.clientY - rect.top;
      botao.setPointerCapture(ev.pointerId);
      botao.classList.add("ar-arrastando");
    });

    botao.addEventListener("pointermove", (ev) => {
      if (!arrastando) return;
      moveu = true;
      aplicarPosicao(ev.clientX - offX, ev.clientY - offY);
    });

    function soltar(ev) {
      if (!arrastando) return;
      arrastando = false;
      botao.classList.remove("ar-arrastando");
      if (moveu) {
        const rect = raiz.getBoundingClientRect();
        localStorage.setItem(CHAVE_POS, JSON.stringify({ left: rect.left, top: rect.top }));
      }
    }
    botao.addEventListener("pointerup", soltar);
    botao.addEventListener("pointercancel", soltar);

    // Mantem dentro da tela se a janela for redimensionada.
    window.addEventListener("resize", () => {
      const rect = raiz.getBoundingClientRect();
      if (raiz.style.left) aplicarPosicao(rect.left, rect.top);
    });

    return { foiArrastado: () => moveu };
  }

  function esconderWidget(raiz) {
    raiz.style.display = "none";
    document.getElementById("ar-reabrir").classList.add("visivel");
    localStorage.setItem(CHAVE_OCULTO, "1");
  }
  function mostrarWidget(raiz) {
    raiz.style.display = "";
    document.getElementById("ar-reabrir").classList.remove("visivel");
    localStorage.removeItem(CHAVE_OCULTO);
  }

  function addMensagemDOM(texto, quem, fonte) {
    const box = document.getElementById("ar-mensagens");
    const div = document.createElement("div");
    div.className = "ar-msg " + (quem === "user" ? "ar-msg-usuario" : "ar-msg-assistente");
    div.textContent = texto;
    if (fonte) {
      const tag = document.createElement("div");
      tag.className = "ar-msg-fonte";
      tag.textContent = fonte;
      div.appendChild(tag);
    }
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function mostrarDigitando() {
    const box = document.getElementById("ar-mensagens");
    const div = document.createElement("div");
    div.className = "ar-digitando";
    div.id = "ar-digitando-atual";
    div.innerHTML = "<span></span><span></span><span></span>";
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }
  function removerDigitando() {
    const el = document.getElementById("ar-digitando-atual");
    if (el) el.remove();
  }

  async function enviarPergunta(animador) {
    const input = document.getElementById("ar-input");
    const texto = input.value.trim();
    if (!texto) return;

    input.value = "";
    document.getElementById("ar-enviar").disabled = true;

    addMensagemDOM(texto, "user");
    historico.push({ role: "user", texto });

    // Comando pra voltar ao menu de assuntos a qualquer momento.
    const textoNormalizado = texto.toLowerCase().trim();
    if (["menu", "voltar", "trocar assunto", "assuntos"].includes(textoNormalizado)) {
      categoriaAtual = null;
      animador.tocar("happy", "idle");
      mostrarMenuCategorias("Beleza, sobre o que você quer falar agora?");
      document.getElementById("ar-enviar").disabled = false;
      return;
    }

    const categorias = typeof CATEGORIAS_ASSISTENTE !== "undefined" ? CATEGORIAS_ASSISTENTE : [];
    const catInfo = categorias.find((c) => c.id === categoriaAtual);

    // 1) Se tiver categoria escolhida e ela não for "sempre IA", tenta a base local
    if (categoriaAtual && !(catInfo && catInfo.sempreIA)) {
      const localResp = (typeof buscarRespostaLocal === "function")
        ? buscarRespostaLocal(texto, categoriaAtual)
        : null;

      if (localResp) {
        animador.tocar("talk", "happy");
        setTimeout(() => {
          addMensagemDOM(localResp, "assistant", "base local");
          historico.push({ role: "assistant", texto: localResp });
          document.getElementById("ar-enviar").disabled = false;
        }, 500);
        return;
      }

      // Não achou nada na categoria — avisa antes de cair pra IA (se a
      // categoria tiver uma mensagem própria pra isso).
      if (catInfo && catInfo.semResposta) {
        animador.tocar("idle");
        addMensagemDOM(catInfo.semResposta, "assistant");
        document.getElementById("ar-enviar").disabled = false;
        return;
      }
    }

    // 2) Cai pra IA (backend) — pensa enquanto espera
    animador.tocar("think", "think");
    mostrarDigitando();
    document.getElementById("ar-status").textContent = "pensando...";

    try {
      const resp = await fetch("/api/assistente/perguntar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pergunta: texto,
          historico: historico.slice(-10), // ultimas trocas, pra dar contexto
        }),
      });
      const dados = await resp.json();
      removerDigitando();
      document.getElementById("ar-status").textContent = "online";

      animador.tocar("talk", dados.ok ? "happy" : "idle");
      const respostaTexto = dados.resposta || "Não consegui responder agora.";
      addMensagemDOM(respostaTexto, "assistant", dados.ok ? "IA" : null);
      historico.push({ role: "assistant", texto: respostaTexto });
    } catch (e) {
      removerDigitando();
      document.getElementById("ar-status").textContent = "online";
      animador.tocar("idle");
      addMensagemDOM("Não consegui falar com o servidor agora. Tenta de novo em instantes.", "assistant");
    } finally {
      document.getElementById("ar-enviar").disabled = false;
    }
  }

  /* ── Inicializacao ────────────────────────────────────────────────────── */
  async function iniciar() {
    // Assistente só faz sentido logado — confirma sessao antes de montar.
    try {
      const resp = await fetch("/api/me");
      if (!resp.ok) return;
      usuarioAtual = await resp.json();
    } catch (e) {
      return;
    }

    const raiz = montarWidget();
    if (!raiz) return;

    const imgBotao = document.getElementById("ar-avatar-botao");
    const imgPainel = document.getElementById("ar-avatar-painel");
    const animBotao = criarAnimador(imgBotao);
    const animPainel = criarAnimador(imgPainel);
    animBotao.iniciarIdleComPiscadas();

    const botaoEl = document.getElementById("ar-botao");
    const arraste = tornarArrastavel(raiz, botaoEl);

    // Comeca escondido se o usuario tinha fechado numa sessao anterior.
    if (localStorage.getItem(CHAVE_OCULTO) === "1") {
      esconderWidget(raiz);
    }

    document.getElementById("ar-fechar-avatar").addEventListener("click", (ev) => {
      ev.stopPropagation();
      esconderWidget(raiz);
    });

    document.getElementById("ar-reabrir").addEventListener("click", () => mostrarWidget(raiz));

    // Qualquer parte do sistema pode pedir pra reabrir o assistente
    // disparando este evento (ex: botao "Assistente" na sidebar).
    window.addEventListener("riozen:mostrar-assistente", () => mostrarWidget(raiz));

    botaoEl.addEventListener("click", () => {
      if (arraste.foiArrastado()) return; // foi arrastar, nao clique
      aberto = !aberto;
      const painel = document.getElementById("ar-painel");
      painel.classList.toggle("aberto", aberto);
      document.getElementById("ar-badge").classList.remove("visivel");

      if (aberto) {
        animPainel.iniciarIdleComPiscadas();
        if (!primeiraAberturaFeita) {
          primeiraAberturaFeita = true;
          animPainel.tocar("wave", "idle");
          const nome = (usuarioAtual && usuarioAtual.nome) ? usuarioAtual.nome.split(" ")[0] : "";
          const saudacao = nome ? `Oi, ${nome}! Sobre o que você quer falar hoje?` : "Oi! Sobre o que você quer falar hoje?";
          mostrarMenuCategorias(saudacao);
        }
      }
    });

    document.getElementById("ar-fechar").addEventListener("click", (ev) => {
      ev.stopPropagation();
      aberto = false;
      document.getElementById("ar-painel").classList.remove("aberto");
    });

    const input = document.getElementById("ar-input");
    document.getElementById("ar-enviar").addEventListener("click", () => enviarPergunta(animPainel));
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        enviarPergunta(animPainel);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
