'use strict';

function formatarTempoDecorrido(totalMs) {
  if (totalMs <= 0) return '0d 00h 00min 00s';
  const totalSegundos = Math.floor(totalMs / 1000);
  const dias = Math.floor(totalSegundos / 86400);
  const horas = Math.floor((totalSegundos % 86400) / 3600);
  const minutos = Math.floor((totalSegundos % 3600) / 60);
  const segundos = totalSegundos % 60;
  return `${dias}d ${String(horas).padStart(2, '0')}h ${String(minutos).padStart(2, '0')}min ${String(segundos).padStart(2, '0')}s`;
}

function animarPercentual(element, target, onUpdate, duration = 1400) {
  if (!element) return;

  const inicio = performance.now();

  function frame(now) {
    const progresso = Math.min((now - inicio) / duration, 1);
    const eased = 1 - Math.pow(1 - progresso, 3);
    const atual = target * eased;

    element.textContent = atual.toFixed(1);
    if (typeof onUpdate === 'function') onUpdate(atual);

    if (progresso < 1) {
      window.requestAnimationFrame(frame);
    }
  }

  element.textContent = '0.0';
  if (typeof onUpdate === 'function') onUpdate(0);
  window.requestAnimationFrame(frame);
}

function iniciarObjetivoMaster() {
  const container = document.querySelector('[data-master-goal]');
  if (!container) return;

  const valueEl = container.querySelector('[data-master-goal-value]');
  if (!valueEl) return;

  const target = Number.parseFloat(valueEl.textContent.replace('%', '').replace(',', '.')) || 0;
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

  function tick() {
    const now = Date.now();
    const decorrido = Math.min(Math.max(now - startedAt.getTime(), 0), total);
    const percentual = Math.min((decorrido / total) * 100, 100);

    if (valueEl) valueEl.textContent = formatarTempoDecorrido(decorrido);
    if (pctEl) pctEl.textContent = percentual.toFixed(1);
    container.style.setProperty('--panel-progress', `${percentual}%`);
  }

  tick();
  window.setInterval(tick, 1000);
}

document.addEventListener('DOMContentLoaded', () => {
  iniciarObjetivoMaster();
  iniciarTimerMaster();
});
