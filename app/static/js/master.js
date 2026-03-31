'use strict';

let timerIntervalId = null;
let goalAnimationFrameId = null;
let refreshTimeoutId = null;
let refreshInFlight = false;

function formatarTempoDecorrido(totalMs) {
  if (totalMs <= 0) return '0d 00h 00min 00s';
  const totalSegundos = Math.floor(totalMs / 1000);
  const dias = Math.floor(totalSegundos / 86400);
  const horas = Math.floor((totalSegundos % 86400) / 3600);
  const minutos = Math.floor((totalSegundos % 3600) / 60);
  const segundos = totalSegundos % 60;
  return `${dias}d ${String(horas).padStart(2, '0')}h ${String(minutos).padStart(2, '0')}min ${String(segundos).padStart(2, '0')}s`;
}

function formatarNumeroBr(valor, casas = 1) {
  return Number(valor || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

function formatarInteiroBr(valor) {
  return Math.round(Number(valor || 0)).toLocaleString('pt-BR');
}

function formatarMoedaInteira(valor) {
  return `R$ ${formatarInteiroBr(valor)}`;
}

function animarPercentual(element, target, onUpdate, duration = 1400) {
  if (!element) return;

  if (goalAnimationFrameId) {
    window.cancelAnimationFrame(goalAnimationFrameId);
  }

  const inicio = performance.now();

  function frame(now) {
    const progresso = Math.min((now - inicio) / duration, 1);
    const eased = 1 - Math.pow(1 - progresso, 3);
    const atual = target * eased;

    element.textContent = atual.toFixed(1);
    if (typeof onUpdate === 'function') onUpdate(atual);

    if (progresso < 1) {
      goalAnimationFrameId = window.requestAnimationFrame(frame);
    } else {
      goalAnimationFrameId = null;
    }
  }

  element.textContent = '0.0';
  if (typeof onUpdate === 'function') onUpdate(0);
  goalAnimationFrameId = window.requestAnimationFrame(frame);
}

function iniciarObjetivoMaster() {
  const container = document.querySelector('[data-master-goal]');
  if (!container) return;

  const valueEl = container.querySelector('[data-master-goal-value]');
  if (!valueEl) return;

  const target = Number.parseFloat(String(valueEl.textContent || '').replace('%', '').replace(',', '.')) || 0;
  animarPercentual(valueEl, target, (valorAtual) => {
    container.style.setProperty('--panel-progress', `${Math.min(valorAtual, 100)}%`);
  });
}

function iniciarTimerMaster() {
  const container = document.querySelector('[data-master-timer]');
  if (!container) return;

  const valueEl = container.querySelector('[data-master-timer-value]');
  const pctEl = container.querySelector('[data-master-timer-pct]');
  const startedAt = new Date(container.dataset.startedAt);
  const deadlineAt = new Date(container.dataset.deadlineAt);
  const total = Math.max(deadlineAt.getTime() - startedAt.getTime(), 1);

  if (timerIntervalId) {
    window.clearInterval(timerIntervalId);
  }

  function tick() {
    const now = Date.now();
    const decorrido = Math.min(Math.max(now - startedAt.getTime(), 0), total);
    const percentual = Math.min((decorrido / total) * 100, 100);

    if (valueEl) valueEl.textContent = formatarTempoDecorrido(decorrido);
    if (pctEl) pctEl.textContent = percentual.toFixed(1);
    container.style.setProperty('--panel-progress', `${percentual}%`);
  }

  tick();
  timerIntervalId = window.setInterval(tick, 1000);
}

function atualizarCard(card) {
  const item = document.querySelector(`[data-master-card="${card.slug}"]`);
  if (!item) return;

  const percentualEl = item.querySelector('[data-master-card-percentual]');
  const metaEl = item.querySelector('[data-master-card-meta]');
  const contextEl = item.querySelector('[data-master-card-context]');
  const fillEl = item.querySelector('[data-master-card-fill]');

  if (percentualEl) percentualEl.textContent = `${formatarNumeroBr(card.percentual, 1)}%`;
  if (metaEl) {
    metaEl.textContent = card.monetario
      ? `${formatarMoedaInteira(card.realizado)} x ${formatarMoedaInteira(card.meta)}`
      : `${formatarInteiroBr(card.realizado)} x ${formatarInteiroBr(card.meta)}`;
  }
  if (contextEl) contextEl.textContent = card.comparativo_label || '';
  if (fillEl) fillEl.style.width = `${Math.min(Number(card.percentual || 0), 100)}%`;
}

function renderizarTabela(cards) {
  const tbody = document.querySelector('[data-master-table-body]');
  if (!tbody) return;

  tbody.innerHTML = (cards || []).map((card) => `
    <tr>
      <td>${card.nome}</td>
      <td>${card.monetario ? formatarMoedaInteira(card.realizado) : formatarInteiroBr(card.realizado)}</td>
      <td>${card.monetario ? formatarMoedaInteira(card.meta) : formatarInteiroBr(card.meta)}</td>
      <td>${formatarNumeroBr(card.percentual, 1)}%</td>
      <td>${card.descricao}</td>
    </tr>
  `).join('');
}

function aplicarDadosMaster(payload) {
  const cards = Array.isArray(payload.cards_master) ? payload.cards_master : [];
  cards.forEach(atualizarCard);
  renderizarTabela(cards);

  const goalValueEl = document.querySelector('[data-master-goal-value]');
  const goalCopyEl = document.querySelector('[data-master-goal-copy]');
  const timerEl = document.querySelector('[data-master-timer]');
  const highlightNameEl = document.querySelector('[data-master-highlight-name]');
  const highlightCopyEl = document.querySelector('[data-master-highlight-copy]');
  const alertNameEl = document.querySelector('[data-master-alert-name]');
  const alertCopyEl = document.querySelector('[data-master-alert-copy]');

  if (goalValueEl) goalValueEl.textContent = formatarNumeroBr(payload.objetivo_geral, 1);
  if (goalCopyEl) {
    goalCopyEl.textContent = `${formatarNumeroBr(payload.objetivo_realizado_total, 1)} de ${formatarInteiroBr(payload.objetivo_meta_total)} pontos percentuais rumo aos 100% em cada frente.`;
  }
  if (timerEl) {
    timerEl.dataset.startedAt = payload.timer_started_at_iso;
    timerEl.dataset.deadlineAt = payload.timer_deadline_at_iso;
  }
  if (highlightNameEl) highlightNameEl.textContent = payload.destaque_principal?.nome || 'Sem dados';
  if (highlightCopyEl) highlightCopyEl.textContent = `${formatarNumeroBr(payload.destaque_principal?.percentual || 0, 1)}% da meta trimestral.`;
  if (alertNameEl) alertNameEl.textContent = payload.alerta_principal?.nome || 'Sem dados';
  if (alertCopyEl) alertCopyEl.textContent = `${formatarNumeroBr(payload.alerta_principal?.percentual || 0, 1)}% da meta atual.`;

  iniciarObjetivoMaster();
  iniciarTimerMaster();
}

async function carregarDadosMaster() {
  if (refreshInFlight || !window.MASTER_DATA_URL) return;
  refreshInFlight = true;

  try {
    const response = await fetch(window.MASTER_DATA_URL, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!response.ok) return;
    const payload = await response.json();
    aplicarDadosMaster(payload);
  } catch (_) {
    // Se a atualização falhar, mantemos os dados atuais na tela.
  } finally {
    refreshInFlight = false;
  }
}

function agendarAtualizacaoMaster() {
  if (refreshTimeoutId) {
    window.clearTimeout(refreshTimeoutId);
  }

  refreshTimeoutId = window.setTimeout(() => {
    refreshTimeoutId = null;
    carregarDadosMaster();
  }, 250);
}

function conectarSocketMaster() {
  if (typeof io !== 'function') return;

  const socket = io({ transports: ['polling'] });
  ['dados_atualizados', 'vendas_atualizadas', 'investidores_atualizados'].forEach((eventName) => {
    socket.on(eventName, agendarAtualizacaoMaster);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  iniciarObjetivoMaster();
  iniciarTimerMaster();
  conectarSocketMaster();
});
