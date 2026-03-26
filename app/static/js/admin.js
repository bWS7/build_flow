/* ═══════════════════════════════════════════════════════════════════════════
   SOUSA ARAUJO — admin.js
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

const META_LOCK_PREFIX = 'meta-locked-s';
const MESES = ['abril', 'maio', 'junho'];

// ── Toast ──────────────────────────────────────────────────────────────────
let toastTimer;
function showToast(msg, tipo = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast toast--${tipo} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

// ── Modais ─────────────────────────────────────────────────────────────────
function openModal(id) {
  document.getElementById(id).removeAttribute('hidden');
}
function closeModal(id) {
  document.getElementById(id).setAttribute('hidden', '');
}
// Fechar modal clicando fora
document.querySelectorAll('.modal-overlay').forEach(el => {
  el.addEventListener('click', (e) => {
    if (e.target === el) el.setAttribute('hidden', '');
  });
});

// ── Criar usuário ──────────────────────────────────────────────────────────
async function criarUsuario() {
  const dados = {
    nome:  document.getElementById('u-nome').value.trim(),
    email: document.getElementById('u-email').value.trim(),
    senha: document.getElementById('u-senha').value,
    tipo:  document.getElementById('u-tipo').value,
  };

  if (!dados.nome || !dados.email || !dados.senha || !dados.tipo) {
    showToast('Preencha todos os campos.', 'error'); return;
  }

  try {
    const resp = await fetch('/admin/usuario/criar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast('Usuário criado com sucesso!', 'success');
      closeModal('modal-usuario');
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(json.erro || 'Erro ao criar usuário.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

function abrirEdicaoUsuario(id, nome, email, tipo) {
  document.getElementById('edit-u-id').value = id;
  document.getElementById('edit-u-nome').value = nome;
  document.getElementById('edit-u-email').value = email;
  document.getElementById('edit-u-tipo').value = tipo;
  document.getElementById('edit-u-senha').value = '';
  openModal('modal-editar-usuario');
}

async function salvarEdicaoUsuario() {
  const id = document.getElementById('edit-u-id').value;
  const dados = {
    nome: document.getElementById('edit-u-nome').value.trim(),
    email: document.getElementById('edit-u-email').value.trim(),
    tipo: document.getElementById('edit-u-tipo').value,
    senha: document.getElementById('edit-u-senha').value,
  };

  if (!dados.nome || !dados.email || !dados.tipo) {
    showToast('Preencha nome, e-mail e tipo.', 'error'); return;
  }

  try {
    const resp = await fetch(`/admin/usuario/${id}/editar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast('Usuário atualizado com sucesso!', 'success');
      closeModal('modal-editar-usuario');
      setTimeout(() => location.reload(), 700);
    } else {
      showToast(json.erro || 'Erro ao atualizar usuário.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

// ── Toggle usuário ativo/inativo ───────────────────────────────────────────
async function toggleUsuario(id, btn) {
  try {
    const resp = await fetch(`/admin/usuario/${id}/toggle`, { method: 'POST' });
    const json = await resp.json();
    if (resp.ok) {
      showToast(json.ativo ? 'Usuário ativado.' : 'Usuário desativado.', 'success');
      setTimeout(() => location.reload(), 700);
    } else {
      showToast(json.erro || 'Erro.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

// ── Criar empreendimento ───────────────────────────────────────────────────
async function criarEmpreendimento() {
  const nome = document.getElementById('emp-nome').value.trim();
  if (!nome) { showToast('Informe o nome.', 'error'); return; }

  try {
    const resp = await fetch('/admin/empreendimento/criar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome }),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast('Empreendimento criado!', 'success');
      closeModal('modal-empreendimento');
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(json.erro || 'Erro ao criar.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

// ── Toggle empreendimento ──────────────────────────────────────────────────
async function toggleEmpreendimento(id, btn) {
  try {
    const resp = await fetch(`/admin/empreendimento/${id}/toggle`, { method: 'POST' });
    const json = await resp.json();
    if (resp.ok) {
      showToast(json.ativo ? 'Empreendimento ativado.' : 'Desativado.', 'success');
      setTimeout(() => location.reload(), 700);
    } else {
      showToast(json.erro || 'Erro.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

// ── Formatação de valor em reais (ex: 1.500.000,00) ───────────────────────
function formatarValorBR(input) {
  let digits = input.value.replace(/\D/g, '');
  if (!digits) { input.value = ''; return; }
  const num = parseInt(digits, 10) / 100;
  input.value = num.toLocaleString('pt-BR', { minimumFractionDigits: 2 });
}

function parsearValorBR(str) {
  if (!str) return 0;
  return parseFloat(str.replace(/\./g, '').replace(',', '.')) || 0;
}

function obterMetaEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-semana="${semana}"]`),
    acoesEl: document.getElementById(`acoes-s${semana}`),
    valorEl: document.getElementById(`valor-s${semana}`),
    btn: document.getElementById(`btn-s${semana}`),
  };
}

function renderizarMetaBloqueada(semana) {
  const { item, acoesEl, valorEl, btn } = obterMetaEls(semana);
  if (!acoesEl || !valorEl || !btn) return;
  acoesEl.readOnly = true;
  valorEl.readOnly = true;
  valorEl.oninput = null;
  btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar';
  btn.classList.remove('btn--primary');
  btn.classList.add('btn--ghost');
  btn.onclick = () => editarMeta(semana, btn);
  if (item) item.dataset.locked = 'true';
  localStorage.setItem(`${META_LOCK_PREFIX}${semana}`, '1');
}

function renderizarMetaEditavel(semana) {
  const { item, acoesEl, valorEl, btn } = obterMetaEls(semana);
  if (!acoesEl || !valorEl || !btn) return;
  acoesEl.readOnly = false;
  valorEl.readOnly = false;
  valorEl.oninput = function () { formatarValorBR(this); };
  btn.innerHTML = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMeta(semana, btn);
  if (item) item.dataset.locked = 'false';
  localStorage.removeItem(`${META_LOCK_PREFIX}${semana}`);
}

// ── Salvar meta ────────────────────────────────────────────────────────────
async function salvarMeta(semana, btn) {
  const acoesEl = document.getElementById(`acoes-s${semana}`);
  const valorEl = document.getElementById(`valor-s${semana}`);
  const acoes = parseInt(acoesEl.value) || 0;
  const valor = parsearValorBR(valorEl.value);

  try {
    const resp = await fetch('/admin/meta/salvar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ semana, acoes_planejadas: acoes, valor_meta: valor }),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast(`Semana ${semana} salva!`, 'success');
      renderizarMetaBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

function editarMeta(semana, btn) {
  renderizarMetaEditavel(semana);
}

// ── Meses colapsáveis ───────────────────────────────────────────────────────
function toggleMes(mesId) {
  const body  = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  const isCollapsed = body.classList.toggle('mes-body--collapsed');
  arrow.classList.toggle('mes-arrow--collapsed', isCollapsed);
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.meta-item[data-semana]').forEach((item) => {
    const semana = item.dataset.semana;
    const lockedByServer = item.dataset.locked === 'true';
    const lockedByClient = localStorage.getItem(`${META_LOCK_PREFIX}${semana}`) === '1';
    if (lockedByServer || lockedByClient) renderizarMetaBloqueada(semana);
  });

  MESES.forEach(mesId => {
    const body  = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });
});
