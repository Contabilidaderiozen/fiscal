/* ==========================================================================
   FERRAMENTAS POR SETOR — REFORMA TRIBUTÁRIA — RIOZEN
   Fiscal (comparador de carga), Pricing (formação de preço),
   TI (checklist técnico), Governança (relatório de status).
   ========================================================================== */

/* ── Constantes fiscais conhecidas ────────────────────────────────────── */
// Alíquotas oficiais da FASE DE TESTE de 2026 (Informe Técnico 2025.002).
// Anos seguintes ainda não têm alíquota padrão definida em lei — por isso
// as ferramentas abaixo só projetam 2026, nunca anos futuros.
const ALIQ_TESTE_2026 = { ibsUF: 0.1, ibsMun: 0.0, cbs: 0.9 };

// 2027: o IBS sobe pra 0,05% (UF) + 0,05% (Município) — publicado no
// Informe Técnico 2025.002. O CBS de 2027 (8,4%) foi checado direto na
// API oficial da Receita Federal (piloto-cbs.tributos.gov.br) em
// 25/08/2026 — é a "alíquota de referência" do Art. 18 da LC 214/2025
// (o valor que vale se a União não legislar uma alíquota própria
// diferente — normalmente é bem próximo do que acaba virando lei).
const ALIQ_2027 = { ibsUF: 0.05, ibsMun: 0.05, cbs: 8.4 };

function _ibsEfetivo2027(cct) {
  const redIBS = parseFloat(cct["Percentual Redução IBS"]) || 0;
  return (ALIQ_2027.ibsUF + ALIQ_2027.ibsMun) * (1 - redIBS / 100);
}

function _cbsEfetivo2027(cct) {
  const redCBS = parseFloat(cct["Percentual Redução CBS"]) || 0;
  return ALIQ_2027.cbs * (1 - redCBS / 100);
}

// Imposto Seletivo — fonte: API oficial da Receita Federal. Cobertura
// parcial (só os NCMs de veículos consultados diretamente na API).
function _impostoSeletivoDoNCM(item) {
  const dados = typeof DADOS_IMPOSTO_SELETIVO !== "undefined" ? DADOS_IMPOSTO_SELETIVO : { itens: [] };
  const digItem = item.dig;
  const candidatos = (dados.itens || []).filter((it) => digItem.startsWith(_apenasDigitosFT(it.ncm)));
  if (!candidatos.length) return null;
  candidatos.sort((a, b) => _apenasDigitosFT(b.ncm).length - _apenasDigitosFT(a.ncm).length);
  return candidatos[0];
}

/* ── Utilitários de busca (mesma lógica do NCM/cClassTrib do painel) ──── */
function _apenasDigitosFT(s) { return (s || "").replace(/\D/g, ""); }
function _normalizarTextoFT(s) {
  return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
function _ehNumericaFT(s) { return /^[\d.\s-]+$/.test(s.trim()) && _apenasDigitosFT(s).length > 0; }
function _todasPalavrasFT(textoNorm, consultaNorm) {
  return consultaNorm.split(/\s+/).filter(Boolean).every((p) => textoNorm.includes(p));
}

const _IDX_NCM_FT = (typeof DADOS_NCM !== "undefined" ? DADOS_NCM : []).map((n) => ({
  ...n, dig: _apenasDigitosFT(n.c), dnorm: _normalizarTextoFT(n.d),
}));
const _IDX_CCT_FT = (typeof DADOS_CCLASSTRIB !== "undefined" ? DADOS_CCLASSTRIB : []).map((r) => ({
  ...r,
  digCct: _apenasDigitosFT(r["Código da Classificação Tributária"]),
  digCst: _apenasDigitosFT(r["Código da Situação Tributária"]),
  dnorm: _normalizarTextoFT(
    (r["Descrição do Código da Classificação Tributária"] || "") + " " +
    (r["Descrição da Situação Tributária"] || "")
  ),
}));

// Pré-preenche o cClassTrib padrão (000001 — regra geral) num campo de
// "selecionado", pra não obrigar busca manual em venda comum de veículo
// (novo, seminovo ou comissão) — cobre a maioria dos casos, sem redução
// específica. O campo de busca continua disponível pra trocar se precisar.
function _autoPreencherCCTPadrao(idCampoSelecionado) {
  const padrao = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === "000001");
  if (!padrao) return null;
  document.getElementById(idCampoSelecionado).innerHTML =
    `<span class="sel-codigo">000001</span>${_escaparFT(padrao["Descrição do Código da Classificação Tributária"])}
    <span style="color:var(--text-faint); font-size:12px;"> (preenchido automaticamente — troque a busca se
    precisar de outro código)</span>`;
  return padrao;
}

function buscarNCM_FT(q) {
  if (!q.trim()) return [];
  if (_ehNumericaFT(q)) { const d = _apenasDigitosFT(q); return _IDX_NCM_FT.filter((n) => n.dig.startsWith(d)); }
  const qn = _normalizarTextoFT(q);
  return _IDX_NCM_FT.filter((n) => _todasPalavrasFT(n.dnorm, qn));
}

function buscarCCT_FT(q) {
  if (!q.trim()) return [];
  if (_ehNumericaFT(q)) {
    const d = _apenasDigitosFT(q);
    return _IDX_CCT_FT.filter((r) => r.digCct.startsWith(d) || r.digCst.startsWith(d));
  }
  const qn = _normalizarTextoFT(q);
  return _IDX_CCT_FT.filter((r) => _todasPalavrasFT(r.dnorm, qn));
}

function _regimesMonofasicoDoNCM(item) {
  const dados = typeof DADOS_PIS_COFINS_MONO !== "undefined" ? DADOS_PIS_COFINS_MONO : { regimes: [] };
  const encontrados = [];
  for (const regime of dados.regimes || []) {
    for (const cod of regime.ncms) {
      const digRegime = _apenasDigitosFT(cod.split(" ")[0]);
      if (item.dig.startsWith(digRegime)) { encontrados.push(regime); break; }
    }
  }
  return encontrados;
}

function _renderListaCompacta(container, resultados, tipo, onSelecionar) {
  if (resultados.length === 0) { container.innerHTML = ""; return; }
  const top = resultados.slice(0, 30);
  container.innerHTML = top.map((r) => {
    if (tipo === "ncm") {
      return `<div class="item-resultado" data-cod="${r.c}"><span class="item-codigo">${r.c}</span><span class="item-desc">${_escaparFT(r.d)}</span></div>`;
    }
    const cod = r["Código da Classificação Tributária"];
    const desc = r["Descrição do Código da Classificação Tributária"];
    return `<div class="item-resultado" data-cod="${cod}"><span class="item-codigo">${cod}</span><span class="item-desc">${_escaparFT(desc)}</span></div>`;
  }).join("");
  container.querySelectorAll(".item-resultado").forEach((el) => {
    el.addEventListener("click", () => onSelecionar(el.dataset.cod));
  });
}

function _escaparFT(t) { const d = document.createElement("div"); d.textContent = t == null ? "" : String(t); return d.innerHTML; }
function _fmtR$(v) { return "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function _fmtPct(v) { return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%"; }

/* ══════════════════════════════════════════════════════════════════════
   FISCAL — Calculadora Comparativa de Carga Tributária
   ══════════════════════════════════════════════════════════════════════ */
const _estadoCalcFiscal = { ncm: null, cct: null };

function _iniciarCalcFiscal() {
  const buscaNcm = document.getElementById("calc-fiscal-ncm-busca");
  const buscaCct = document.getElementById("calc-fiscal-cct-busca");
  const valorEl = document.getElementById("calc-fiscal-valor");

  buscaNcm.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("calc-fiscal-ncm-lista"), buscarNCM_FT(buscaNcm.value), "ncm", (cod) => {
      _estadoCalcFiscal.ncm = _IDX_NCM_FT.find((n) => n.c === cod);
      document.getElementById("calc-fiscal-ncm-lista").innerHTML = "";
      buscaNcm.value = "";
      document.getElementById("calc-fiscal-ncm-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoCalcFiscal.ncm.d)}`;
      _recalcularFiscal();
    });
  });

  buscaCct.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("calc-fiscal-cct-lista"), buscarCCT_FT(buscaCct.value), "cct", (cod) => {
      _estadoCalcFiscal.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("calc-fiscal-cct-lista").innerHTML = "";
      buscaCct.value = "";
      document.getElementById("calc-fiscal-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoCalcFiscal.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularFiscal();
    });
  });

  valorEl.addEventListener("input", _recalcularFiscal);
  document.getElementById("calc-fiscal-situacao").addEventListener("change", _recalcularFiscal);
}

function _recalcularFiscal() {
  const container = document.getElementById("calc-fiscal-resultado");
  const valor = parseFloat(document.getElementById("calc-fiscal-valor").value);
  if (!valor || valor <= 0) { container.innerHTML = ""; return; }

  const situacao = document.getElementById("calc-fiscal-situacao").value;
  if (situacao === "usado") {
    container.innerHTML = `
      <div class="ficha-secao destaque-mudanca">
        <h3>⚠️ VEÍCULO/ITEM USADO — REGIME DIFERENTE</h3>
        <p class="texto-corpo">
          O <b>Art. 6º da Lei nº 10.485/2002</b> exclui produtos usados desse regime monofásico inteiro —
          nem a alíquota cheia, nem a redução a 0% se aplicam aqui. Isso vale pra qualquer usado, inclusive
          veículo que passou por test drive ou frota própria antes de virar usado.
        </p>
        <p class="texto-corpo">
          Essa calculadora <b>não cobre a tributação de usados</b> — nem hoje (PIS/COFINS), nem sabemos com
          certeza como fica na Reforma (IBS/CBS pode ter uma base de cálculo diferenciada pra usados, ainda
          não pesquisamos isso). <b>Consulte o Fiscal antes de usar qualquer número pra um item usado.</b>
        </p>
      </div>
    `;
    return;
  }

  let hojeHtml, hojeValor = null;
  if (_estadoCalcFiscal.ncm) {
    const regimes = _regimesMonofasicoDoNCM(_estadoCalcFiscal.ncm);
    if (regimes.length > 0) {
      const r = regimes[0];
      // A Riozen é revendedora (concessionária/comerciante varejista) — na
      // venda pro consumidor final, a alíquota já reduzida a 0% se aplicar
      // (Art. 3º, §2º da Lei 10.485/2002). Se não tiver essa faixa
      // específica no regime, cai pro que existir.
      const temFaixas = r.aliquotas.revenda_atacado_varejo || r.aliquotas.revenda_por_atacadista_varejista;
      const aliq = temFaixas || r.aliquotas.venda_geral || Object.values(r.aliquotas)[0];
      const ehRevenda = !!temFaixas;
      hojeValor = valor * (aliq.pis + aliq.cofins) / 100;
      hojeHtml = `<div class="resultado-valor">${_fmtR$(hojeValor)}</div>
        <div class="resultado-detalhe">${ehRevenda ? "Revenda (Riozen vendendo pro consumidor final)" : "Venda geral"}:
        PIS ${_fmtPct(aliq.pis)} + COFINS ${_fmtPct(aliq.cofins)} (monofásico — ${_escaparFT(r.descricao)})<br>
        ${ehRevenda ? "A alíquota cheia (cobrada só do fabricante/importador na venda pra Riozen) já foi recolhida antes — não se paga de novo na revenda.<br>" : ""}
        Base: ${r.base_legal}<br><b>Regime válido só até 31/12/2026.</b></div>`;
    } else {
      hojeHtml = `<div class="resultado-detalhe">Esse NCM não está no regime monofásico mapeado (veículos/autopeças/pneus) —
        provavelmente segue o regime normal de PIS/COFINS não cumulativo (1,65% + 7,6%), mas confirme com o Fiscal
        pra ter certeza do enquadramento certo.</div>`;
    }
  } else {
    hojeHtml = `<div class="resultado-detalhe">Selecione um NCM acima pra calcular o regime de hoje.</div>`;
  }

  let reformaHtml, reformaValor = null;
  if (_estadoCalcFiscal.cct) {
    const redIBS = parseFloat(_estadoCalcFiscal.cct["Percentual Redução IBS"]) || 0;
    const redCBS = parseFloat(_estadoCalcFiscal.cct["Percentual Redução CBS"]) || 0;
    const aliqIBS = (ALIQ_TESTE_2026.ibsUF + ALIQ_TESTE_2026.ibsMun) * (1 - redIBS / 100);
    const aliqCBS = ALIQ_TESTE_2026.cbs * (1 - redCBS / 100);
    reformaValor = valor * (aliqIBS + aliqCBS) / 100;
    reformaHtml = `<div class="resultado-valor">${_fmtR$(reformaValor)}</div>
      <div class="resultado-detalhe">IBS efetivo ${_fmtPct(aliqIBS)} + CBS efetivo ${_fmtPct(aliqCBS)}
      (redução IBS ${_fmtPct(redIBS)}, redução CBS ${_fmtPct(redCBS)})</div>`;
  } else {
    reformaHtml = `<div class="resultado-detalhe">Selecione um cClassTrib acima pra calcular a fase de teste de 2026.</div>`;
  }

  let painel2027Html;
  if (_estadoCalcFiscal.cct) {
    const aliqIBS2027 = _ibsEfetivo2027(_estadoCalcFiscal.cct);
    const valorIBS2027 = valor * aliqIBS2027 / 100;

    let linhaIS = "";
    let valorIS2027 = 0;
    if (_estadoCalcFiscal.ncm) {
      const is = _impostoSeletivoDoNCM(_estadoCalcFiscal.ncm);
      if (is) {
        if (is.tributado) {
          valorIS2027 = valor * is.aliquota_ad_valorem / 100;
          linhaIS = `<br>+ IS (Imposto Seletivo) ${_fmtPct(is.aliquota_ad_valorem)} = ${_fmtR$(valorIS2027)} <span style="color:var(--success);">(conhecido)</span>`;
        } else {
          linhaIS = `<br>+ IS (Imposto Seletivo): <span style="color:var(--success);">isento</span>`;
        }
      } else {
        linhaIS = `<br>+ IS (Imposto Seletivo): <span class="valor-pendente">esse NCM específico ainda não foi consultado na API oficial — cobertura parcial, só 7 NCMs de veículos</span>`;
      }
    } else {
      linhaIS = `<br>+ IS (Imposto Seletivo): selecione um NCM acima pra conferir`;
    }

    const aliqCBS2027 = _cbsEfetivo2027(_estadoCalcFiscal.cct);
    const valorCBS2027 = valor * aliqCBS2027 / 100;
    const total2027 = valorIBS2027 + valorCBS2027 + valorIS2027;
    painel2027Html = `<div class="resultado-valor">${_fmtR$(total2027)}</div>
      <div class="resultado-detalhe">IBS efetivo ${_fmtPct(aliqIBS2027)} = ${_fmtR$(valorIBS2027)}<br>
      CBS efetivo ${_fmtPct(aliqCBS2027)} = ${_fmtR$(valorCBS2027)} <span style="color:var(--success);">(alíquota de referência)</span>${linhaIS}<br>
      O regime monofásico de hoje já não vale mais nessa data.</div>`;
  } else {
    painel2027Html = `<div class="resultado-detalhe">Selecione um cClassTrib acima.</div>`;
  }

  let diferencaHtml = "";
  if (hojeValor !== null && reformaValor !== null) {
    const dif = reformaValor - hojeValor;
    const classe = dif > 0 ? "maior" : "menor";
    diferencaHtml = `<div class="resultado-diferenca ${classe}">
      ${dif > 0 ? "▲" : "▼"} Hoje x fase de teste 2026: ${_fmtR$(Math.abs(dif))} ${dif > 0 ? "a mais" : "a menos"}, em cima de ${_fmtR$(valor)}
    </div>`;
  }

  container.innerHTML = `
    <div class="resultado-comparativo">
      <div class="resultado-painel"><h4>Hoje (até 12/2026)</h4>${hojeHtml}</div>
      <div class="resultado-painel"><h4>Reforma — fase de teste 2026</h4>${reformaHtml}</div>
      <div class="resultado-painel"><h4>2027 (alíquota de referência)</h4>${painel2027Html}</div>
      ${diferencaHtml}
    </div>
    <div class="aviso-calibragem">
      2026: alíquotas de calibragem/teste (IBS 0,1% + CBS 0,9%), não representam a carga final.
      2027: IBS 0,05%+0,05%, CBS 8,4% (<b>alíquota de referência</b> — checado direto na API oficial da
      Receita Federal em 25/08/2026, conforme Art. 18 da LC 214/2025) e Imposto Seletivo de veículos já
      definido em lei. Essa alíquota de referência vale se a União não legislar um valor próprio diferente
      — normalmente fica bem próxima do que acaba virando lei.
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   PRICING — Calculadora de Formação de Preço
   ══════════════════════════════════════════════════════════════════════ */
const _estadoCalcPricing = { ncm: null, cct: null };

function _iniciarCalcPricing() {
  const buscaNcm = document.getElementById("calc-pricing-ncm-busca");
  const buscaCct = document.getElementById("calc-pricing-cct-busca");

  buscaNcm.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("calc-pricing-ncm-lista"), buscarNCM_FT(buscaNcm.value), "ncm", (cod) => {
      _estadoCalcPricing.ncm = _IDX_NCM_FT.find((n) => n.c === cod);
      document.getElementById("calc-pricing-ncm-lista").innerHTML = "";
      buscaNcm.value = "";
      document.getElementById("calc-pricing-ncm-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoCalcPricing.ncm.d)}`;
      _recalcularPricing();
    });
  });

  buscaCct.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("calc-pricing-cct-lista"), buscarCCT_FT(buscaCct.value), "cct", (cod) => {
      _estadoCalcPricing.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("calc-pricing-cct-lista").innerHTML = "";
      buscaCct.value = "";
      document.getElementById("calc-pricing-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoCalcPricing.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularPricing();
    });
  });

  document.getElementById("calc-pricing-custo").addEventListener("input", _recalcularPricing);
  document.getElementById("calc-pricing-margem").addEventListener("input", _recalcularPricing);
  document.getElementById("calc-pricing-situacao").addEventListener("change", _recalcularPricing);
}

function _aliquotaHojeDoNCM(item) {
  const regimes = _regimesMonofasicoDoNCM(item);
  if (regimes.length === 0) return null;
  const r = regimes[0];
  // Riozen é revendedora — na venda pro consumidor final, usa a alíquota
  // de revenda (0%, quando existir essa faixa no regime).
  const temFaixaRevenda = r.aliquotas.revenda_atacado_varejo || r.aliquotas.revenda_por_atacadista_varejista;
  const aliq = temFaixaRevenda || r.aliquotas.venda_geral || Object.values(r.aliquotas)[0];
  return { pct: aliq.pis + aliq.cofins, regime: r, ehRevenda: !!temFaixaRevenda };
}

function _recalcularPricing() {
  const container = document.getElementById("calc-pricing-resultado");
  const custo = parseFloat(document.getElementById("calc-pricing-custo").value);
  const margem = parseFloat(document.getElementById("calc-pricing-margem").value);
  if (!custo || custo <= 0 || margem == null || isNaN(margem)) { container.innerHTML = ""; return; }

  const situacao = document.getElementById("calc-pricing-situacao").value;
  if (situacao === "usado") {
    container.innerHTML = `
      <div class="ficha-secao destaque-mudanca">
        <h3>⚠️ VEÍCULO/ITEM USADO — REGIME DIFERENTE</h3>
        <p class="texto-corpo">
          O <b>Art. 6º da Lei nº 10.485/2002</b> exclui produtos usados desse regime monofásico inteiro.
          Isso vale pra qualquer usado, inclusive veículo que passou por test drive ou frota própria antes
          de virar usado.
        </p>
        <p class="texto-corpo">
          Essa calculadora <b>não cobre a formação de preço de usados</b> — a fórmula acima não se aplica.
          <b>Consulte o Fiscal antes de usar qualquer número pra um item usado.</b>
        </p>
      </div>
    `;
    return;
  }

  let hojeHtml, precoHoje = null, aliqHojePct = 0;
  if (_estadoCalcPricing.ncm) {
    const info = _aliquotaHojeDoNCM(_estadoCalcPricing.ncm);
    if (info) {
      aliqHojePct = info.pct;
      const divisor = 1 - (margem + aliqHojePct) / 100;
      if (divisor <= 0) {
        hojeHtml = `<div class="resultado-detalhe">Margem + imposto ultrapassa 100% — ajuste os valores.</div>`;
      } else {
        precoHoje = custo / divisor;
        hojeHtml = `<div class="resultado-valor">${_fmtR$(precoHoje)}</div>
          <div class="resultado-detalhe">${info.ehRevenda ? "Revenda (Riozen → consumidor)" : "Venda geral"}:
          PIS+COFINS ${_fmtPct(aliqHojePct)} (monofásico) + margem ${_fmtPct(margem)}</div>`;
      }
    } else {
      hojeHtml = `<div class="resultado-detalhe">NCM fora do regime monofásico mapeado — confirme a alíquota real com o Fiscal antes de usar esse número.</div>`;
    }
  } else {
    hojeHtml = `<div class="resultado-detalhe">Selecione um NCM acima.</div>`;
  }

  let reformaHtml, precoReforma = null;
  if (_estadoCalcPricing.cct) {
    const redIBS = parseFloat(_estadoCalcPricing.cct["Percentual Redução IBS"]) || 0;
    const redCBS = parseFloat(_estadoCalcPricing.cct["Percentual Redução CBS"]) || 0;
    const aliqIBS = (ALIQ_TESTE_2026.ibsUF + ALIQ_TESTE_2026.ibsMun) * (1 - redIBS / 100);
    const aliqCBS = ALIQ_TESTE_2026.cbs * (1 - redCBS / 100);
    const aliqReformaPct = aliqIBS + aliqCBS;
    const divisor = 1 - (margem + aliqReformaPct) / 100;
    if (divisor <= 0) {
      reformaHtml = `<div class="resultado-detalhe">Margem + imposto ultrapassa 100% — ajuste os valores.</div>`;
    } else {
      precoReforma = custo / divisor;
      reformaHtml = `<div class="resultado-valor">${_fmtR$(precoReforma)}</div>
        <div class="resultado-detalhe">IBS+CBS efetivo ${_fmtPct(aliqReformaPct)} (fase de teste 2026) + margem ${_fmtPct(margem)}</div>`;
    }
  } else {
    reformaHtml = `<div class="resultado-detalhe">Selecione um cClassTrib acima.</div>`;
  }

  let diferencaHtml = "";
  if (precoHoje !== null && precoReforma !== null) {
    const dif = precoReforma - precoHoje;
    const classe = dif > 0 ? "maior" : "menor";
    diferencaHtml = `<div class="resultado-diferenca ${classe}">
      ${dif > 0 ? "▲" : "▼"} Pra manter a mesma margem, o preço precisaria ${dif > 0 ? "subir" : "cair"}
      ${_fmtR$(Math.abs(dif))} na fase de teste de 2026
    </div>`;
  }

  let painel2027Html;
  if (_estadoCalcPricing.cct) {
    const aliqIBS2027 = _ibsEfetivo2027(_estadoCalcPricing.cct);
    const aliqCBS2027 = _cbsEfetivo2027(_estadoCalcPricing.cct);
    const divisor2027 = 1 - (margem + aliqIBS2027 + aliqCBS2027) / 100;
    const preco2027 = divisor2027 > 0 ? custo / divisor2027 : null;
    painel2027Html = preco2027 !== null
      ? `<div class="resultado-valor">${_fmtR$(preco2027)}</div>
         <div class="resultado-detalhe">IBS+CBS efetivo ${_fmtPct(aliqIBS2027 + aliqCBS2027)}
         (CBS = alíquota de referência) + margem ${_fmtPct(margem)}</div>`
      : `<div class="resultado-detalhe">Margem + imposto ultrapassa 100% — ajuste os valores.</div>`;
  } else {
    painel2027Html = `<div class="resultado-detalhe">Selecione um cClassTrib acima.</div>`;
  }

  container.innerHTML = `
    <div class="resultado-comparativo">
      <div class="resultado-painel"><h4>Preço hoje (até 12/2026)</h4>${hojeHtml}</div>
      <div class="resultado-painel"><h4>Preço — fase de teste 2026</h4>${reformaHtml}</div>
      <div class="resultado-painel"><h4>Preço — 2027 (alíquota de referência)</h4>${painel2027Html}</div>
      ${diferencaHtml}
    </div>
    <div class="aviso-calibragem">
      Fórmula de preço "por dentro" (o imposto é embutido no preço final, não somado por fora).
      2026: alíquotas de calibragem. 2027: IBS 0,10% + CBS 8,4% (alíquota de referência, Art. 18 da
      LC 214/2025 — checado na API oficial em 25/08/2026).
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   TI — Checklist Técnico por Documento Fiscal
   ══════════════════════════════════════════════════════════════════════ */
const _INDICADORES_TI = [
  ["Exige Tributação", "Grupo padrão de tributação (gTrib)"],
  ["Tributação Regular", "Grupo de tributação regular (gTribRegular)"],
  ["Crédito Presumido", "Grupo de crédito presumido (gCredPresOper)"],
  ["Estorno de Crédito", "Grupo de estorno de crédito (gEstornoCred)"],
  ["Diferimento", "Grupo de diferimento (gDif)"],
  ["Transferência de Crédito", "Grupo de transferência de crédito (gTransfCred)"],
  ["Monofásica", "Grupo monofásico padrão (gMonoPadrao)"],
  ["Tributação Monofásica sujeita a retenção", "Grupo monofásico com retenção (gMonoReten)"],
  ["Tributação Monofásica retida anteriormente", "Grupo monofásico retido antes (gMonoRet)"],
  ["Crédito Presumido IBS Zona Franca de Manaus", "Grupo de crédito presumido ZFM (gCredPresIBSZFM)"],
  ["Ajuste de Competência", "Grupo de ajuste por competência (gAjusteCompet)"],
];

const _DOCS_TI = [
  ["NFe", "NF-e"], ["NFCe", "NFC-e"], ["CTe", "CT-e"], ["CTe OS", "CT-e OS"],
  ["BPe", "BP-e"], ["BPe TM", "BP-e TM"], ["BPe TA", "BP-e TA"], ["NF3e", "NF3-e"],
  ["NFCom", "NFCom"], ["NFSE", "NFS-e"], ["NFAg", "NFAg"], ["NFSVIA", "NFS-e Via"],
  ["NFABI", "NF-e ABI"], ["NFGas", "NFGás"], ["DERE", "DeRE"], ["DIR", "DIR"], ["DUIMP", "DUIMP"],
];

function _iniciarChecklistTI() {
  const busca = document.getElementById("calc-ti-cct-busca");
  busca.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("calc-ti-cct-lista"), buscarCCT_FT(busca.value), "cct", (cod) => {
      document.getElementById("calc-ti-cct-lista").innerHTML = "";
      busca.value = "";
      _renderChecklistTI(_IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod));
    });
  });
}

function _renderChecklistTI(r) {
  const container = document.getElementById("calc-ti-resultado");
  if (!r) { container.innerHTML = ""; return; }

  const itensChecklist = _INDICADORES_TI.map(([campo, explicacao]) => {
    const sim = (r[campo] || "").trim().toLowerCase() === "sim";
    return `<div class="checklist-item">
      <span class="checklist-marca ${sim ? "sim" : "nao"}">${sim ? "☑" : "☐"}</span>
      <span class="checklist-texto"><b>${campo}</b><span>${explicacao} — ${sim ? "precisa preencher" : "não se aplica a esse código"}</span></span>
    </div>`;
  }).join("");

  const docsChips = _DOCS_TI.map(([campo, rotulo]) => {
    const permitido = (r[campo] || "").trim().toLowerCase() === "sim";
    return `<span class="doc-chip ${permitido ? "permitido" : "vedado"}">${rotulo}</span>`;
  }).join("");

  container.innerHTML = `
    <div class="ficha-cabecalho" style="margin-top:20px;">
      <div class="ficha-codigo">${r["Código da Classificação Tributária"]}</div>
      <div class="ficha-desc">${_escaparFT(r["Descrição do Código da Classificação Tributária"])}</div>
    </div>
    <div class="ficha-secao">
      <h3>GRUPOS A CONSIDERAR NO XML</h3>
      ${itensChecklist}
    </div>
    <div class="ficha-secao">
      <h3>DOCUMENTOS FISCAIS EM QUE ESSE cClassTrib É PERMITIDO</h3>
      <div class="docs-grid">${docsChips}</div>
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   GOVERNANÇA — Relatório de Status
   ══════════════════════════════════════════════════════════════════════ */
function _gerarRelatorioGovernanca() {
  const container = document.getElementById("relatorio-corpo");
  if (!estado.plano) { container.innerHTML = "<p>Carregando dados do plano...</p>"; return; }

  const acoes = todasAcoes();
  const pct = progresso(acoes);
  const agora = new Date().toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });

  const categoriasHtml = estado.plano.categorias.map((cat) => {
    const p = progresso(cat.acoes);
    const conc = cat.acoes.filter((a) => a.status === "Concluído").length;
    const and = cat.acoes.filter((a) => a.status === "Em Andamento").length;
    const pen = cat.acoes.filter((a) => a.status === "Pendente").length;
    return `<div class="relatorio-categoria">
      <h4>${String(cat.num).padStart(2, "0")} — ${cat.titulo} (${p}%)</h4>
      <div class="relatorio-barra-linha">
        <span class="mini-barra" style="width:160px;"><span class="mini-barra-preenchida" style="width:${p}%"></span></span>
        <span style="font-size:12px; color:var(--text-muted);">${conc} concluídas · ${and} em andamento · ${pen} pendentes</span>
      </div>
    </div>`;
  }).join("");

  const emAndamento = acoes.filter((a) => a.status === "Em Andamento");
  const destaquesHtml = emAndamento.length === 0
    ? `<p style="color:var(--text-faint); font-size:13px;">Nenhuma ação em andamento no momento.</p>`
    : emAndamento.map((a) => {
        const ultima = a.observacoes && a.observacoes.length ? a.observacoes[a.observacoes.length - 1] : null;
        return `<div class="relatorio-destaque">
          <span class="cod">${a.cod}</span>${_escaparFT(a.desc)} <i>(${a.setor})</i>
          ${ultima ? `<span class="ultima-ata">Último registro (${formatarDataHora(ultima.data)}): ${_escaparFT(ultima.texto)}</span>` : ""}
        </div>`;
      }).join("");

  container.innerHTML = `
    <div class="relatorio-cabecalho">
      <div class="data">Gerado em ${agora}</div>
      <div class="resultado-valor" style="margin-top:6px;">${pct}% concluído no geral</div>
      <div style="font-size:13px; color:var(--text-muted); margin-top:4px;">
        ${acoes.filter(a=>a.status==="Concluído").length} concluídas ·
        ${acoes.filter(a=>a.status==="Em Andamento").length} em andamento ·
        ${acoes.filter(a=>a.status==="Pendente").length} pendentes ·
        ${acoes.length} ações no total
      </div>
    </div>

    <h3 style="font-size:13px; color:var(--text-faint); text-transform:uppercase; letter-spacing:1px;">Progresso por categoria</h3>
    ${categoriasHtml}

    <h3 style="font-size:13px; color:var(--text-faint); text-transform:uppercase; letter-spacing:1px; margin-top:24px;">Em andamento agora</h3>
    ${destaquesHtml}
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   COMPRAS — Comparador de Custo Líquido por Fornecedor
   ══════════════════════════════════════════════════════════════════════ */
const _estadoComprasNCM = { a: null, b: null };

function _sugerirCreditoCompras(letra) {
  const item = _estadoComprasNCM[letra];
  const campoAliq = document.getElementById(`compras-aliq-${letra}`);
  const caixa = document.getElementById(`compras-ncm-selecionado-${letra}`);
  if (!item) return;

  const cabecalho = `<span class="sel-codigo">${item.c}</span>${_escaparFT(item.d)}`;
  const regimes = _regimesMonofasicoDoNCM(item);
  if (regimes.length > 0) {
    const r = regimes[0];
    const temFaixaRevenda = r.aliquotas.revenda_atacado_varejo || r.aliquotas.revenda_por_atacadista_varejista;
    const aliq = temFaixaRevenda || Object.values(r.aliquotas)[0];
    campoAliq.value = (aliq.pis + aliq.cofins).toFixed(2);
    caixa.innerHTML = cabecalho +
      `<div style="margin-top:6px; color:var(--success); font-size:12px;">% sugerido automaticamente: ${_fmtPct(aliq.pis + aliq.cofins)}
      (${temFaixaRevenda ? "revenda, já recolhido antes" : "regime monofásico"} — confirme antes de usar)</div>`;
  } else if (document.getElementById(`compras-regime-${letra}`).value === "normal") {
    campoAliq.value = "9.25";
    caixa.innerHTML = cabecalho +
      `<div style="margin-top:6px; color:var(--warn); font-size:12px;">% sugerido: 9,25% (PIS 1,65% + COFINS 7,6%,
      regra padrão do Lucro Real não-cumulativo — esse NCM não está em nenhum regime especial que já mapeamos,
      então usamos a regra geral. Confirme se não existe alguma exceção pra esse item específico.)</div>`;
  } else {
    caixa.innerHTML = cabecalho +
      `<div style="margin-top:6px; color:var(--text-faint); font-size:12px;">Fornecedor do Simples Nacional — não dá
      pra sugerir automaticamente, varia demais. Use o guia rápido acima.</div>`;
  }
}

function _iniciarCalcCompras() {
  ["compras-preco-a", "compras-aliq-a", "compras-preco-b", "compras-aliq-b"].forEach((id) =>
    document.getElementById(id).addEventListener("input", _recalcularCompras)
  );
  ["a", "b"].forEach((letra) => {
    document.getElementById(`compras-regime-${letra}`).addEventListener("change", () => {
      _sugerirCreditoCompras(letra);
      _recalcularCompras();
    });

    const busca = document.getElementById(`compras-ncm-busca-${letra}`);
    busca.addEventListener("input", () => {
      _renderListaCompacta(document.getElementById(`compras-ncm-lista-${letra}`), buscarNCM_FT(busca.value), "ncm", (cod) => {
        _estadoComprasNCM[letra] = _IDX_NCM_FT.find((n) => n.c === cod);
        document.getElementById(`compras-ncm-lista-${letra}`).innerHTML = "";
        busca.value = "";
        _sugerirCreditoCompras(letra);
        _recalcularCompras();
      });
    });
  });
}

function _recalcularCompras() {
  const container = document.getElementById("compras-resultado");
  const precoA = parseFloat(document.getElementById("compras-preco-a").value);
  const precoB = parseFloat(document.getElementById("compras-preco-b").value);
  const aliqA = parseFloat(document.getElementById("compras-aliq-a").value) || 0;
  const aliqB = parseFloat(document.getElementById("compras-aliq-b").value) || 0;
  const regimeA = document.getElementById("compras-regime-a").value === "simples" ? "(Simples Nacional)" : "(Regime Normal)";
  const regimeB = document.getElementById("compras-regime-b").value === "simples" ? "(Simples Nacional)" : "(Regime Normal)";

  if (!precoA || !precoB) { container.innerHTML = ""; return; }

  const credA = precoA * aliqA / 100, liqA = precoA - credA;
  const credB = precoB * aliqB / 100, liqB = precoB - credB;
  const melhor = liqA <= liqB ? "A" : "B";

  container.innerHTML = `
    <div class="resultado-comparativo">
      <div class="resultado-painel">
        <h4>Fornecedor A ${regimeA}</h4>
        <div class="resultado-valor">${_fmtR$(liqA)}</div>
        <div class="resultado-detalhe">Preço de tabela: ${_fmtR$(precoA)}<br>Crédito recuperável: ${_fmtR$(credA)} (${_fmtPct(aliqA)})</div>
      </div>
      <div class="resultado-painel">
        <h4>Fornecedor B ${regimeB}</h4>
        <div class="resultado-valor">${_fmtR$(liqB)}</div>
        <div class="resultado-detalhe">Preço de tabela: ${_fmtR$(precoB)}<br>Crédito recuperável: ${_fmtR$(credB)} (${_fmtPct(aliqB)})</div>
      </div>
      <div class="resultado-diferenca ${melhor === "A" ? "menor" : "maior"}">
        ✓ Fornecedor ${melhor} tem o menor custo líquido — diferença de ${_fmtR$(Math.abs(liqA - liqB))}
      </div>
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   COMERCIAL — Simulador de Comissão
   ══════════════════════════════════════════════════════════════════════ */
const _estadoComercial = { cct: null };

function _iniciarSimComercial() {
  const busca = document.getElementById("comercial-cct-busca");
  busca.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("comercial-cct-lista"), buscarCCT_FT(busca.value), "cct", (cod) => {
      _estadoComercial.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("comercial-cct-lista").innerHTML = "";
      busca.value = "";
      document.getElementById("comercial-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoComercial.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularComercial();
    });
  });
  document.getElementById("comercial-valor").addEventListener("input", _recalcularComercial);
  document.getElementById("comercial-comissao").addEventListener("input", _recalcularComercial);

  _estadoComercial.cct = _autoPreencherCCTPadrao("comercial-cct-selecionado");
}

function _recalcularComercial() {
  const container = document.getElementById("comercial-resultado");
  const valor = parseFloat(document.getElementById("comercial-valor").value);
  const comissaoPct = parseFloat(document.getElementById("comercial-comissao").value);
  if (!valor || comissaoPct == null || isNaN(comissaoPct)) { container.innerHTML = ""; return; }

  const comissaoBruta = valor * comissaoPct / 100;
  let html = `<div class="resultado-comparativo">
    <div class="resultado-painel">
      <h4>Comissão sobre valor bruto (hoje)</h4>
      <div class="resultado-valor">${_fmtR$(comissaoBruta)}</div>
      <div class="resultado-detalhe">${_fmtPct(comissaoPct)} sobre ${_fmtR$(valor)}</div>
    </div>`;

  if (_estadoComercial.cct) {
    const redIBS = parseFloat(_estadoComercial.cct["Percentual Redução IBS"]) || 0;
    const redCBS = parseFloat(_estadoComercial.cct["Percentual Redução CBS"]) || 0;
    const aliqTotal = (ALIQ_TESTE_2026.ibsUF + ALIQ_TESTE_2026.ibsMun) * (1 - redIBS / 100) + ALIQ_TESTE_2026.cbs * (1 - redCBS / 100);
    const valorLiquido = valor * (1 - aliqTotal / 100);
    const comissaoLiquida = valorLiquido * comissaoPct / 100;
    const dif = comissaoBruta - comissaoLiquida;

    html += `<div class="resultado-painel">
      <h4>Comissão sobre valor líquido de imposto</h4>
      <div class="resultado-valor">${_fmtR$(comissaoLiquida)}</div>
      <div class="resultado-detalhe">${_fmtPct(comissaoPct)} sobre ${_fmtR$(valorLiquido)} (líquido de IBS/CBS ${_fmtPct(aliqTotal)}, fase teste 2026)</div>
    </div>
    <div class="resultado-diferenca ${dif > 0 ? "maior" : "menor"}">
      ${dif > 0 ? "▼" : "▲"} Se a base mudar pro valor líquido, a comissão cai ${_fmtR$(Math.abs(dif))}
    </div>`;
  } else {
    html += `<div class="resultado-painel"><div class="resultado-detalhe">Selecione um cClassTrib acima pra comparar com a base líquida de imposto.</div></div>`;
  }

  if (_estadoComercial.cct) {
    const aliqIBS2027 = _ibsEfetivo2027(_estadoComercial.cct);
    const aliqCBS2027 = _cbsEfetivo2027(_estadoComercial.cct);
    const valorLiquido2027 = valor * (1 - (aliqIBS2027 + aliqCBS2027) / 100);
    const comissao2027 = valorLiquido2027 * comissaoPct / 100;
    html += `<div class="resultado-painel">
      <h4>2027 (alíquota de referência)</h4>
      <div class="resultado-valor">${_fmtR$(comissao2027)}</div>
      <div class="resultado-detalhe">${_fmtPct(comissaoPct)} sobre o valor líquido de IBS+CBS ${_fmtPct(aliqIBS2027 + aliqCBS2027)}
      (CBS = alíquota de referência, Art. 18 LC 214/2025)</div>
    </div>`;
  }
  html += `</div>`;
  container.innerHTML = html;
}

/* ══════════════════════════════════════════════════════════════════════
   FINANCEIRO — Simulador de Fluxo de Caixa (Split Payment)
   ══════════════════════════════════════════════════════════════════════ */
const _estadoFinanceiro = { cct: null, ncm: null };

function _iniciarSimFinanceiro() {
  const buscaNcm = document.getElementById("financeiro-ncm-busca");
  buscaNcm.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("financeiro-ncm-lista"), buscarNCM_FT(buscaNcm.value), "ncm", (cod) => {
      _estadoFinanceiro.ncm = _IDX_NCM_FT.find((n) => n.c === cod);
      document.getElementById("financeiro-ncm-lista").innerHTML = "";
      buscaNcm.value = "";
      document.getElementById("financeiro-ncm-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoFinanceiro.ncm.d)}`;
      _recalcularFinanceiro();
    });
  });

  const busca = document.getElementById("financeiro-cct-busca");
  busca.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("financeiro-cct-lista"), buscarCCT_FT(busca.value), "cct", (cod) => {
      _estadoFinanceiro.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("financeiro-cct-lista").innerHTML = "";
      busca.value = "";
      document.getElementById("financeiro-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoFinanceiro.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularFinanceiro();
    });
  });
  document.getElementById("financeiro-valor").addEventListener("input", _recalcularFinanceiro);
  document.getElementById("financeiro-prazo").addEventListener("input", _recalcularFinanceiro);
}

function _recalcularFinanceiro() {
  const container = document.getElementById("financeiro-resultado");
  const valor = parseFloat(document.getElementById("financeiro-valor").value);
  const prazo = parseFloat(document.getElementById("financeiro-prazo").value) || 0;
  if (!valor) { container.innerHTML = ""; return; }

  // "Hoje" — PIS/COFINS de verdade (igual a Calculadora Fiscal), não a
  // alíquota de teste do IBS/CBS. Pra revenda de veículo/autopeça/pneu,
  // isso costuma ser 0% (já recolhido lá atrás, na venda do fabricante).
  let hojeHtml, valorHoje = null;
  if (_estadoFinanceiro.ncm) {
    const regimes = _regimesMonofasicoDoNCM(_estadoFinanceiro.ncm);
    if (regimes.length > 0) {
      const r = regimes[0];
      const temFaixas = r.aliquotas.revenda_atacado_varejo || r.aliquotas.revenda_por_atacadista_varejista;
      const aliq = temFaixas || r.aliquotas.venda_geral || Object.values(r.aliquotas)[0];
      valorHoje = valor * (aliq.pis + aliq.cofins) / 100;
      hojeHtml = valorHoje > 0
        ? `Recebe o valor total na hora do pagamento.<br>
           Paga ${_fmtR$(valorHoje)} de PIS/COFINS só daqui a ${prazo} dias (na apuração).<br>
           <b>Fica com o dinheiro do imposto em caixa por ${prazo} dias.</b>`
        : `Recebe o valor total na hora do pagamento.<br>
           <b>PIS/COFINS dessa venda já é 0% (revenda — o fabricante já recolheu antes).</b><br>
           Não tem imposto federal retido nem a reter nessa operação específica hoje.`;
    } else {
      hojeHtml = `Esse NCM não está no regime monofásico mapeado — provavelmente segue o regime normal
        (1,65%+7,6%), mas essa ferramenta não calcula esse caso ainda. Considerando só o valor recebido:`;
      valorHoje = 0;
    }
  } else {
    hojeHtml = `Selecione um NCM acima pra calcular o PIS/COFINS real de hoje. Sem isso, o comparativo abaixo
      só mostra a fase de teste e 2027.`;
  }

  let painel2026Html = "", painel2027Html = "", diferencaHtml = "";
  if (_estadoFinanceiro.cct) {
    const redIBS = parseFloat(_estadoFinanceiro.cct["Percentual Redução IBS"]) || 0;
    const redCBS = parseFloat(_estadoFinanceiro.cct["Percentual Redução CBS"]) || 0;
    const aliqTotal2026 = (ALIQ_TESTE_2026.ibsUF + ALIQ_TESTE_2026.ibsMun) * (1 - redIBS / 100) + ALIQ_TESTE_2026.cbs * (1 - redCBS / 100);
    const valorImposto2026 = valor * aliqTotal2026 / 100;

    const aliqIBS2027 = _ibsEfetivo2027(_estadoFinanceiro.cct);
    const aliqCBS2027 = _cbsEfetivo2027(_estadoFinanceiro.cct);
    const valorImposto2027 = valor * (aliqIBS2027 + aliqCBS2027) / 100;

    painel2026Html = `<div class="resultado-painel">
      <h4>Reforma — Split Payment (teste 2026)</h4>
      <div class="resultado-valor">${_fmtR$(valor - valorImposto2026)}</div>
      <div class="resultado-detalhe">Recebe só o valor líquido — ${_fmtR$(valorImposto2026)} vai direto pro
      governo no momento do pagamento (IBS+CBS teste, ${_fmtPct(aliqTotal2026)}).<br>
      <b>Não fica um centavo desse imposto em caixa, nem por um dia.</b></div>
    </div>`;

    const notaHojeConhecido = (valorHoje !== null && valorHoje === 0)
      ? " — mesmo que hoje o PIS/COFINS dessa venda já seja 0%"
      : "";
    painel2027Html = `<div class="resultado-painel">
      <h4>2027 (alíquota de referência)</h4>
      <div class="resultado-valor">${_fmtR$(valor - valorImposto2027)}</div>
      <div class="resultado-detalhe">IBS+CBS retido: ${_fmtR$(valorImposto2027)} (${_fmtPct(aliqIBS2027 + aliqCBS2027)},
      CBS = alíquota de referência, Art. 18 LC 214/2025).<br><b>Esse valor sai do caixa na hora${notaHojeConhecido}.</b></div>
    </div>`;

    if (valorHoje !== null) {
      const dif = valorImposto2027 - valorHoje;
      diferencaHtml = `<div class="resultado-diferenca ${dif > 0 ? "maior" : "menor"}">
        ${dif > 0 ? "▲" : "▼"} Retenção instantânea em 2027 x imposto de hoje: ${_fmtR$(Math.abs(dif))}
        ${dif > 0 ? "a mais saindo do caixa na hora da venda" : "a menos"}, em cima de ${_fmtR$(valor)}
      </div>`;
    }
  } else {
    painel2026Html = `<div class="resultado-painel"><div class="resultado-detalhe">Selecione um cClassTrib acima.</div></div>`;
    painel2027Html = `<div class="resultado-painel"><div class="resultado-detalhe">Selecione um cClassTrib acima.</div></div>`;
  }

  container.innerHTML = `
    <div class="resultado-comparativo">
      <div class="resultado-painel">
        <h4>Hoje (até 12/2026) — PIS/COFINS</h4>
        <div class="resultado-valor">${_fmtR$(valor)}</div>
        <div class="resultado-detalhe">${hojeHtml}</div>
      </div>
      ${painel2026Html}
      ${painel2027Html}
      ${diferencaHtml}
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   CONTROLADORIA — Sugestão de Plano de Contas
   ══════════════════════════════════════════════════════════════════════ */
const _PLANO_CONTAS_SUGERIDO = [
  { grupo: "Ativo Circulante", conta: "1.1.2.XX", nome: "IBS a Recuperar", desc: "Créditos de IBS apurados em compras, aguardando compensação." },
  { grupo: "Ativo Circulante", conta: "1.1.2.XX", nome: "CBS a Recuperar", desc: "Créditos de CBS apurados em compras, aguardando compensação." },
  { grupo: "Ativo Circulante", conta: "1.1.2.XX", nome: "Crédito Presumido de IBS/CBS a Apropriar", desc: "Créditos presumidos previstos em lei (ex: Zona Franca de Manaus), enquanto não confirmados financeiramente." },
  { grupo: "Passivo Circulante", conta: "2.1.3.XX", nome: "IBS a Recolher", desc: "IBS apurado sobre vendas, a pagar ao Comitê Gestor do IBS." },
  { grupo: "Passivo Circulante", conta: "2.1.3.XX", nome: "CBS a Recolher", desc: "CBS apurada sobre vendas, a pagar à União (Receita Federal)." },
  { grupo: "Passivo Circulante", conta: "2.1.3.XX", nome: "IS a Recolher", desc: "Imposto Seletivo apurado, quando aplicável ao produto (ex: veículos, combustíveis)." },
  { grupo: "Dedução da Receita Bruta", conta: "3.1.1.XX", nome: "(-) IBS sobre Vendas", desc: "IBS destacado na nota, deduzido da receita bruta — o imposto é \"por fora\", não compõe a receita." },
  { grupo: "Dedução da Receita Bruta", conta: "3.1.1.XX", nome: "(-) CBS sobre Vendas", desc: "CBS destacada na nota, deduzida da receita bruta." },
  { grupo: "Contas Transitórias (uso interno no mês)", conta: "1.1.9.XX / 2.1.9.XX", nome: "IBS/CBS em Apuração", desc: "Usada durante o período de apuração — zera no fechamento do mês, vira uma das contas definitivas acima." },
];

function _renderPlanoContas() {
  const container = document.getElementById("controladoria-contas");
  const grupos = [...new Set(_PLANO_CONTAS_SUGERIDO.map((c) => c.grupo))];
  container.innerHTML = grupos.map((g) => {
    const contas = _PLANO_CONTAS_SUGERIDO.filter((c) => c.grupo === g);
    return `<div class="ficha-secao">
      <h3>${_escaparFT(g).toUpperCase()}</h3>
      ${contas.map((c) => `
        <div class="checklist-item">
          <span class="checklist-marca sim">•</span>
          <span class="checklist-texto"><b>${_escaparFT(c.nome)}</b>
          <span style="color:var(--text-faint); font-family:var(--font-mono);">&nbsp;(${c.conta})</span>
          <span>${_escaparFT(c.desc)}</span></span>
        </div>
      `).join("")}
    </div>`;
  }).join("");
}

/* ══════════════════════════════════════════════════════════════════════
   LOGÍSTICA — Por Que a Localização Importa Menos Agora
   ══════════════════════════════════════════════════════════════════════ */
function _iniciarSimLogistica() {
  document.getElementById("logistica-origem").addEventListener("change", _recalcularLogistica);
  document.getElementById("logistica-valor").addEventListener("input", _recalcularLogistica);
  _recalcularLogistica();
}

function _recalcularLogistica() {
  const container = document.getElementById("logistica-resultado");
  const beneficio = parseFloat(document.getElementById("logistica-origem").value);
  const valor = parseFloat(document.getElementById("logistica-valor").value) || 0;
  const economiaHoje = valor * beneficio / 100;

  container.innerHTML = `
    <div class="resultado-comparativo">
      <div class="resultado-painel">
        <h4>Hoje (ICMS na origem)</h4>
        <div class="resultado-valor">${_fmtR$(economiaHoje)}</div>
        <div class="resultado-detalhe">Economia ilustrativa de operar num estado com incentivo fiscal de ICMS,
        pra uma operação de ${_fmtR$(valor)}. É esse tipo de vantagem que hoje motiva concentrar CDs/fábricas em
        certos estados.</div>
      </div>
      <div class="resultado-painel">
        <h4>Reforma (IBS no destino)</h4>
        <div class="resultado-valor">${_fmtR$(0)}</div>
        <div class="resultado-detalhe">O IBS é cobrado com base em onde está o CLIENTE, não onde fica o
        CD/fábrica — esse tipo de economia por localização deixa de existir. A decisão de onde ficar volta a
        ser sobre logística de verdade (frete, prazo, proximidade do cliente), não sobre benefício fiscal.</div>
      </div>
    </div>
    <div class="aviso-calibragem">
      Número ilustrativo pra explicar o conceito — não é uma tabela real de benefícios fiscais por estado.
      Cada benefício específico precisa ser levantado caso a caso com o Fiscal/Jurídico.
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   ABA 2026 → 2027
   ══════════════════════════════════════════════════════════════════════ */
// Códigos de ação do Plano diretamente ligados à virada de 2027 (saída do
// regime monofásico de veículos/autopeças/pneus e adequação ao novo modelo).
const _ACOES_2027 = ["1.6", "1.7", "2.3", "2.4", "4.10", "5.6", "6.1"];

function _renderContador2027() {
  const el = document.getElementById("contador-dias");
  if (!el) return;
  const alvo = new Date("2027-01-01T00:00:00");
  const agora = new Date();
  const dias = Math.max(0, Math.ceil((alvo - agora) / (1000 * 60 * 60 * 24)));
  el.textContent = dias;
}

function _renderAcoes2027() {
  const container = document.getElementById("acoes-2027-lista");
  if (!container || !estado.plano) return;
  const todas = todasAcoes();
  const relacionadas = _ACOES_2027
    .map((cod) => todas.find((a) => a.cod === cod))
    .filter(Boolean);

  container.innerHTML = relacionadas.map((a) => `
    <div class="acao-2027-linha">
      <span class="cod">${a.cod}</span>
      <span class="desc">${_escaparFT(a.desc)}</span>
      <span class="setor-tag">${a.setor}</span>
      <span class="acao-status ${classeStatus(a.status)}" style="pointer-events:none;">
        <span class="acao-status-icone">${iconeStatus(a.status)}</span>
        <span class="acao-status-texto">${a.status}</span>
      </span>
    </div>
  `).join("");
}

function _iniciarAba2027() {
  _renderContador2027();
  _renderAcoes2027();
}

/* ══════════════════════════════════════════════════════════════════════
   COMERCIAL — Venda de Seminovo (tributação sobre a margem)
   ══════════════════════════════════════════════════════════════════════ */
const _estadoSeminovo = { cct: null };

/* ══════════════════════════════════════════════════════════════════════
   COMERCIAL — Comissão de Consórcio/Financiamento
   ══════════════════════════════════════════════════════════════════════ */
const _estadoCF = { cct: null };

function _iniciarComissaoCF() {
  const busca = document.getElementById("cf-cct-busca");
  busca.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("cf-cct-lista"), buscarCCT_FT(busca.value), "cct", (cod) => {
      _estadoCF.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("cf-cct-lista").innerHTML = "";
      busca.value = "";
      document.getElementById("cf-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoCF.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularCF();
    });
  });
  document.getElementById("cf-valor").addEventListener("input", _recalcularCF);
  document.getElementById("cf-parceiro").addEventListener("input", _recalcularCF);
  document.getElementById("cf-tipo").addEventListener("change", _recalcularCF);

  _estadoCF.cct = _autoPreencherCCTPadrao("cf-cct-selecionado");
}

function _recalcularCF() {
  const container = document.getElementById("cf-resultado");
  const valor = parseFloat(document.getElementById("cf-valor").value);
  const tipo = document.getElementById("cf-tipo").value;
  const parceiro = document.getElementById("cf-parceiro").value.trim();
  if (!valor || valor <= 0) { container.innerHTML = ""; return; }

  // Comissão é serviço, não é item do regime monofásico (Lei 10.485/2002 é só
  // pra veículos/autopeças/pneus) — hoje segue o PIS/COFINS padrão não-cumulativo.
  const aliqHoje = 1.65 + 7.6; // 9,25%
  const valorHoje = valor * aliqHoje / 100;

  const rotuloTipo = tipo === "consorcio" ? "Consórcio" : "Financiamento";
  const tituloComResultado = parceiro ? `${rotuloTipo} — ${_escaparFT(parceiro)}` : rotuloTipo;

  const notaTipo = tipo === "consorcio"
    ? `<b>Consórcio:</b> a base de cálculo segue regra própria (Art. 204 da LC 214/2025) — apurada pelo
       <b>regime de caixa</b> (conta quando o valor é efetivamente recebido, não quando é só
       contratado/faturado). O código cClassTrib usado é o mesmo da regra geral (000001) — não achamos
       redução específica pra esse serviço na tabela oficial.`
    : `<b>Financiamento:</b> não achei uma regra de intermediação específica pra esse tipo na lei (só
       existe regra própria pra consórcio/seguro/previdência/capitalização) — segue as regras normais de
       prestação de serviço, código cClassTrib padrão (000001).`;

  let html = `<h3 style="font-family:var(--font-mono); font-size:12px; color:var(--text-faint); letter-spacing:1px; margin:0 0 10px;">${tituloComResultado.toUpperCase()}</h3>
    <div class="resultado-comparativo">
    <div class="resultado-painel">
      <h4>Hoje (até 12/2026) — PIS/COFINS</h4>
      <div class="resultado-valor">${_fmtR$(valorHoje)}</div>
      <div class="resultado-detalhe">${_fmtPct(aliqHoje)} sobre ${_fmtR$(valor)} (regime não-cumulativo
      padrão — comissão de serviço não é regime monofásico de veículo)</div>
    </div>`;

  if (_estadoCF.cct) {
    const redIBS = parseFloat(_estadoCF.cct["Percentual Redução IBS"]) || 0;
    const redCBS = parseFloat(_estadoCF.cct["Percentual Redução CBS"]) || 0;
    const aliqIBS2026 = (ALIQ_TESTE_2026.ibsUF + ALIQ_TESTE_2026.ibsMun) * (1 - redIBS / 100);
    const aliqCBS2026 = ALIQ_TESTE_2026.cbs * (1 - redCBS / 100);
    const valor2026 = valor * (aliqIBS2026 + aliqCBS2026) / 100;

    const aliqIBS2027 = _ibsEfetivo2027(_estadoCF.cct);
    const aliqCBS2027 = _cbsEfetivo2027(_estadoCF.cct);
    const valor2027 = valor * (aliqIBS2027 + aliqCBS2027) / 100;

    html += `
      <div class="resultado-painel">
        <h4>Reforma — fase de teste 2026</h4>
        <div class="resultado-valor">${_fmtR$(valor2026)}</div>
        <div class="resultado-detalhe">IBS+CBS efetivo ${_fmtPct(aliqIBS2026 + aliqCBS2026)}</div>
      </div>
      <div class="resultado-painel">
        <h4>2027 (alíquota de referência)</h4>
        <div class="resultado-valor">${_fmtR$(valor2027)}</div>
        <div class="resultado-detalhe">IBS+CBS efetivo ${_fmtPct(aliqIBS2027 + aliqCBS2027)} (CBS =
        alíquota de referência, Art. 18 LC 214/2025)</div>
      </div>`;
  } else {
    html += `<div class="resultado-painel"><div class="resultado-detalhe">Selecione um cClassTrib
      acima pra calcular a fase de teste 2026 e 2027.</div></div>`;
  }
  html += `</div>
    <div class="aviso-calibragem">${notaTipo}</div>`;

  container.innerHTML = html;
}

function _iniciarVendaSeminovo() {
  const busca = document.getElementById("seminovo-cct-busca");
  busca.addEventListener("input", () => {
    _renderListaCompacta(document.getElementById("seminovo-cct-lista"), buscarCCT_FT(busca.value), "cct", (cod) => {
      _estadoSeminovo.cct = _IDX_CCT_FT.find((r) => r["Código da Classificação Tributária"] === cod);
      document.getElementById("seminovo-cct-lista").innerHTML = "";
      busca.value = "";
      document.getElementById("seminovo-cct-selecionado").innerHTML =
        `<span class="sel-codigo">${cod}</span>${_escaparFT(_estadoSeminovo.cct["Descrição do Código da Classificação Tributária"])}`;
      _recalcularSeminovo();
    });
  });
  document.getElementById("seminovo-venda").addEventListener("input", _recalcularSeminovo);
  document.getElementById("seminovo-aquisicao").addEventListener("input", _recalcularSeminovo);
  document.getElementById("seminovo-origem").addEventListener("change", _recalcularSeminovo);

  _estadoSeminovo.cct = _autoPreencherCCTPadrao("seminovo-cct-selecionado");
}

function _recalcularSeminovo() {
  const container = document.getElementById("seminovo-resultado");
  const venda = parseFloat(document.getElementById("seminovo-venda").value);
  const aquisicao = parseFloat(document.getElementById("seminovo-aquisicao").value);
  const origem = document.getElementById("seminovo-origem").value;

  if (!venda || aquisicao == null || isNaN(aquisicao)) { container.innerHTML = ""; return; }

  const margem = venda - aquisicao;
  const baseLegal = origem === "pf"
    ? "Art. 171 da LC 214/2025 — crédito presumido na compra de pessoa física"
    : "Art. 406 e 407 da LC 214/2025 — redução a zero sobre a parcela até o valor de aquisição";
  const notaCct = origem === "pf"
    ? "Na hora de registrar a COMPRA desse veículo (não a venda), o código a usar é o cClassTrib 410017 — confirmado direto na tabela oficial, vinculado ao Art. 171."
    : "";

  if (margem <= 0) {
    container.innerHTML = `
      <div class="ficha-secao">
        <h3>RESULTADO</h3>
        <div class="resultado-valor" style="color:var(--success);">${_fmtR$(0)}</div>
        <div class="resultado-detalhe">Venda igual ou abaixo do valor de aquisição — sem margem, sem
        imposto a pagar sobre essa operação (mas também sem lucro nela).</div>
      </div>
    `;
    return;
  }

  if (!_estadoSeminovo.cct) {
    container.innerHTML = `<div class="ficha-secao"><div class="resultado-detalhe">
      Margem de ${_fmtR$(margem)} identificada. Selecione um cClassTrib acima pra calcular o imposto sobre
      essa margem.</div></div>`;
    return;
  }

  const aliqIBS = _ibsEfetivo2027(_estadoSeminovo.cct);
  const aliqCBS = _cbsEfetivo2027(_estadoSeminovo.cct);
  const imposto = margem * (aliqIBS + aliqCBS) / 100;

  container.innerHTML = `
    <div class="ficha-secao">
      <h3>RESULTADO</h3>
      <div class="resultado-valor">${_fmtR$(imposto)}</div>
      <div class="resultado-detalhe">
        Margem tributável: ${_fmtR$(venda)} − ${_fmtR$(aquisicao)} = ${_fmtR$(margem)}<br>
        IBS+CBS efetivo sobre a margem: ${_fmtPct(aliqIBS + aliqCBS)} (alíquota de referência 2027)<br>
        <b>Base legal:</b> ${baseLegal}
        ${notaCct ? `<br><span style="color:var(--success);">${notaCct}</span>` : ""}
      </div>
    </div>
    <div class="aviso-calibragem">
      O imposto incide só sobre a margem (venda − aquisição), não sobre o valor total da venda — esse é o
      benefício específico pra veículos/máquinas/equipamentos usados. Compra de pessoa física usa um
      mecanismo formalmente diferente (crédito presumido) do que compra de empresa (redução a zero), mas o
      resultado prático — imposto só sobre a margem — é o mesmo nos dois casos.
    </div>
  `;
}

/* ══════════════════════════════════════════════════════════════════════
   CONTROLADORIA — Crédito de Estoque na Virada de 2027
   ══════════════════════════════════════════════════════════════════════ */
function _iniciarCreditoEstoque() {
  document.getElementById("estoque-valor").addEventListener("input", _recalcularEstoque);
}

function _recalcularEstoque() {
  const container = document.getElementById("estoque-resultado");
  const valor = parseFloat(document.getElementById("estoque-valor").value);
  if (!valor || valor <= 0) { container.innerHTML = ""; return; }

  const credito = valor * 9.25 / 100;
  const parcela = credito / 12;

  container.innerHTML = `
    <div class="ficha-secao">
      <h3>CRÉDITO PRESUMIDO CALCULADO</h3>
      <div class="resultado-valor">${_fmtR$(credito)}</div>
      <div class="resultado-detalhe">
        9,25% sobre ${_fmtR$(valor)} de estoque<br>
        Liberado em 12 parcelas mensais iguais de <b>${_fmtR$(parcela)}</b>, a partir do período seguinte
        à apuração (que precisa ser feita até junho/2027)<br>
        Só compensável com CBS — não pode ser resgatado em dinheiro nem usado em outro tributo
      </div>
    </div>
  `;
}

/* ── Navegação entre a grade de setores e cada ferramenta ─────────────── */
function _iniciarSubNav() {
  document.querySelectorAll(".sub-nav-ferramenta").forEach((nav) => {
    nav.querySelectorAll(".sub-nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        nav.querySelectorAll(".sub-nav-btn").forEach((b) => b.classList.remove("ativo"));
        btn.classList.add("ativo");
        const pai = nav.parentElement;
        pai.querySelectorAll(".sub-conteudo").forEach((c) => c.style.display = "none");
        document.getElementById(btn.dataset.subaba).style.display = "block";
        if (btn.dataset.subaba === "controladoria-contas-view") _renderPlanoContas();
      });
    });
  });
}

/* ── Biblioteca de cláusulas — botão de copiar ────────────────────────── */
function _iniciarBibliotecaClausulas() {
  document.querySelectorAll(".btn-copiar-clausula").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const texto = document.getElementById(btn.dataset.alvo).innerText;
      try {
        await navigator.clipboard.writeText(texto);
      } catch (e) {
        // clipboard pode falhar em file:// sem permissão — seleciona o texto como alternativa
        const range = document.createRange();
        range.selectNodeContents(document.getElementById(btn.dataset.alvo));
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
      const original = btn.textContent;
      btn.textContent = "✓ Copiado";
      btn.classList.add("copiado");
      setTimeout(() => { btn.textContent = original; btn.classList.remove("copiado"); }, 1800);
    });
  });
}

function _iniciarFerramentasSetor() {
  document.querySelectorAll(".setor-card.clicavel").forEach((card) => {
    card.addEventListener("click", () => {
      document.getElementById("setores-grid-view").style.display = "none";
      document.getElementById(`ferramenta-${card.dataset.ferramenta}`).style.display = "block";
      if (card.dataset.ferramenta === "governanca") _gerarRelatorioGovernanca();
      if (card.dataset.ferramenta === "controladoria") _renderPlanoContas();
    });
  });

  document.querySelectorAll(".btn-voltar-setores").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".ferramenta-view").forEach((v) => v.style.display = "none");
      document.getElementById("setores-grid-view").style.display = "block";
    });
  });

  document.getElementById("btn-imprimir-relatorio").addEventListener("click", () => window.print());

  _iniciarSubNav();
  _iniciarBibliotecaClausulas();
  _iniciarCalcFiscal();
  _iniciarCalcPricing();
  _iniciarChecklistTI();
  _iniciarCalcCompras();
  _iniciarSimComercial();
  _iniciarSimFinanceiro();
  _iniciarSimLogistica();
  _iniciarVendaSeminovo();
  _iniciarComissaoCF();
  _iniciarCreditoEstoque();
}

document.addEventListener("DOMContentLoaded", () => {
  // Espera o login/carregamento principal (script.js) terminar antes de
  // religar os eventos das ferramentas, senão os elementos ainda não
  // existem visíveis / o "estado.plano" ainda não carregou.
  // (nota: "let estado" não vira propriedade de window, por isso o
  // typeof aqui é sobre o identificador direto, não window.estado)
  const _tentar = setInterval(() => {
    let pronto = false;
    try { pronto = document.getElementById("app-conteudo").style.display !== "none" && typeof estado !== "undefined" && estado.plano; } catch (e) {}
    if (pronto) {
      clearInterval(_tentar);
      _iniciarFerramentasSetor();
      _iniciarAba2027();
      // Reatualiza a lista de ações toda vez que a aba é aberta, caso o
      // status tenha mudado desde a última vez (ex: alguém atualizou no
      // Plano de Ação e voltou aqui).
      const btnAba2027 = document.querySelector('.aba-nav[data-alvo="aba-2027"]');
      if (btnAba2027) btnAba2027.addEventListener("click", _renderAcoes2027);
    }
  }, 150);
});
