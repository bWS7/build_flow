/* ═══════════════════════════════════════════════════════════════════════════
   SOUSA ARAUJO — admin.js
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

const META_LOCK_PREFIX = 'meta-locked-s';
function getMesIds(prefix = '') {
  const ids = Array.from(document.querySelectorAll('.mes-body[id^="body-"]'))
    .map((el) => el.id.replace('body-', ''));
  if (!prefix) return ids.filter((id) => !id.includes('-'));
  return ids.filter((id) => id.startsWith(`${prefix}-`));
}

const MESES = getMesIds();
const MESES_FINANCEIRO = getMesIds('financeiro');
const MESES_FORNECEDORES = getMesIds('fornecedores');
const MESES_NEGOCIACAO_FORNECEDORES = getMesIds('negociacao-fornecedores');
const MESES_GIRO = getMesIds('giro');
const MESES_MEDICAO = getMesIds('medicao');
const MESES_VENDAS = getMesIds('vendas');
const MESES_INVESTIDORES = getMesIds('investidores');
const ADMIN_COLLAPSIBLES = ['metas-varejo', 'metas-investidores', 'metas-financeiro', 'metas-fornecedores', 'metas-negociacao-fornecedores', 'metas-giro', 'metas-medicao', 'metas-relacionamento'];
const CAN_EDIT_LOCKED_METAS = window.CAN_EDIT_LOCKED_METAS === true;

async function disponibilizarMeta(scope, semana, btn) {
  try {
    const resp = await fetch('/admin/meta/disponibilizar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ scope, semana }),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast(`Meta da semana ${semana} disponibilizada.`, 'success');
      setTimeout(() => location.reload(), 300);
    } else {
      showToast(json.erro || 'Erro ao disponibilizar meta.', 'error');
    }
  } catch {
    showToast('Falha de conexão ao disponibilizar meta.', 'error');
  }
}

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': window.APP_CSRF_TOKEN || '', ...extra };
}

function aplicarEstadoBloqueado(btn, textoEditar, onEdit) {
  if (!btn) return;
  btn.classList.remove('btn--primary');
  btn.classList.add('btn--ghost');
  if (CAN_EDIT_LOCKED_METAS) {
    btn.disabled = false;
    btn.innerHTML = textoEditar;
    btn.onclick = onEdit;
  } else {
    btn.disabled = true;
    btn.textContent = 'Preenchido';
    btn.onclick = null;
  }
}

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
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
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
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
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
    const resp = await fetch(`/admin/usuario/${id}/toggle`, {
      method: 'POST',
      headers: csrfHeaders(),
    });
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
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
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
    const resp = await fetch(`/admin/empreendimento/${id}/toggle`, {
      method: 'POST',
      headers: csrfHeaders(),
    });
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

// ── Criar fornecedor (cadastro para Negociação Fornecedores) ──────────────
async function criarFornecedorCadastro() {
  const nome = document.getElementById('fornecedor-cadastro-nome').value.trim();
  if (!nome) { showToast('Informe o nome.', 'error'); return; }

  try {
    const resp = await fetch('/admin/fornecedor-cadastro/criar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ nome }),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast('Fornecedor criado!', 'success');
      closeModal('modal-fornecedor-cadastro');
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(json.erro || 'Erro ao criar.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  }
}

// ── Toggle fornecedor (cadastro) ───────────────────────────────────────────
async function toggleFornecedorCadastro(id, btn) {
  try {
    const resp = await fetch(`/admin/fornecedor-cadastro/${id}/toggle`, {
      method: 'POST',
      headers: csrfHeaders(),
    });
    const json = await resp.json();
    if (resp.ok) {
      showToast(json.ativo ? 'Fornecedor ativado.' : 'Desativado.', 'success');
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

function parsearInteiroSeguro(valor) {
  return Math.max(parseInt(valor || '0', 10) || 0, 0);
}

function prefixoMetaPorLabel(texto) {
  const label = String(texto || '').toLowerCase();
  if (label.includes('(r$)') || label.includes('valor meta') || label.includes('meta bancos') || label.includes('meta giro') || label.includes('meta fornecedores') || label.includes('meta medicao')) {
    return 'Valores (R$)';
  }
  if (label.includes('unidades') || label.includes('acoes planejadas')) {
    return 'Qtd';
  }
  return '';
}

function aprimorarCamposMetas() {
  document.querySelectorAll('[id^="body-metas-"] .field').forEach((field) => {
    if (field.dataset.metaEnhanced === 'true') return;
    const labelEl = field.querySelector('.field__label');
    const inputEl = field.querySelector('.field__input');
    if (!labelEl || !inputEl) return;

    const prefixo = prefixoMetaPorLabel(labelEl.textContent);
    if (!prefixo) return;

    const wrap = document.createElement('div');
    wrap.className = 'meta-field-wrap';

    const badge = document.createElement('span');
    badge.className = `meta-field-prefix${prefixo === 'Qtd' ? ' meta-field-prefix--qty' : ''}`;
    badge.textContent = prefixo;

    inputEl.parentNode.insertBefore(wrap, inputEl);
    wrap.appendChild(badge);
    wrap.appendChild(inputEl);
    field.dataset.metaEnhanced = 'true';
  });
}

function obterMetaBase(scope, monetario = true) {
  const input = document.getElementById(`meta-base-${scope}`);
  if (!input) return 0;
  return monetario ? Math.max(parsearValorBR(input.value), 0) : parsearInteiroSeguro(input.value);
}

async function salvarMetaBase(scope, btn, monetario = true) {
  const valor = obterMetaBase(scope, monetario);
  if (!btn) return;
  btn.disabled = true;
  const textoOriginal = btn.textContent;
  btn.textContent = 'Salvando...';

  try {
    const resp = await fetch('/admin/meta-base/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        scope,
        valor,
        tipo: monetario ? 'monetario' : 'inteiro',
      }),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast('Meta base salva com sucesso!', 'success');
    } else {
      showToast(json.erro || 'Erro ao salvar meta base.', 'error');
    }
  } catch {
    showToast('Falha de conexao ao salvar meta base.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = textoOriginal;
  }
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
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMeta(semana, btn));
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
  const metaBaseTotal = obterMetaBase('relacionamento');

  try {
    const resp = await fetch('/admin/meta/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, acoes_planejadas: acoes, valor_meta: valor, meta_base_total: metaBaseTotal }),
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

function obterMetaVendaEls(mes) {
  return {
    item: document.querySelector(`.meta-item[data-meta-venda="${mes}"]`),
    input: document.getElementById(`meta-venda-${mes}`),
    acoesEl: document.getElementById(`acoes-venda-${mes}`),
    btn: document.getElementById(`btn-meta-venda-${mes}`),
  };
}

function renderizarMetaVendaBloqueada(mes) {
  const { item, input, acoesEl, btn } = obterMetaVendaEls(mes);
  if (!input || !btn) return;
  input.readOnly = true;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaVenda(mes, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaVendaEditavel(mes) {
  const { item, input, acoesEl, btn } = obterMetaVendaEls(mes);
  if (!input || !btn) return;
  input.readOnly = false;
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar Meta';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaVenda(mes, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaVenda(mes, btn) {
  const input = document.getElementById(`meta-venda-${mes}`);
  const acoesEl = document.getElementById(`acoes-venda-${mes}`);
  const quantidade = parsearInteiroSeguro(input ? input.value : '0');
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('vendas', false);

  try {
    const resp = await fetch('/admin/meta-venda/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana: mes, quantidade_meta: quantidade, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de ${mes} salva com sucesso!`, 'success');
      renderizarMetaVendaBloqueada(mes);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de vendas.', 'error');
    }
  } catch (error) {
    showToast('Erro ao salvar meta de vendas.', 'error');
  }
}

// ── Meses colapsáveis ───────────────────────────────────────────────────────
function toggleMes(mesId) {
  const body  = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  const isCollapsed = body.classList.toggle('mes-body--collapsed');
  arrow.classList.toggle('mes-arrow--collapsed', isCollapsed);
}

function toggleMesFinanceiro(mesId) {
  const body = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  const isCollapsed = body.classList.toggle('mes-body--collapsed');
  arrow.classList.toggle('mes-arrow--collapsed', isCollapsed);
}

function toggleMesVendas(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleMesInvestidores(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleMesGiro(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleMesFornecedores(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleMesNegociacaoFornecedores(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleMesMedicao(mesId) {
  toggleMesFinanceiro(mesId);
}

function toggleAdminCard(cardId) {
  const body = document.getElementById(`body-${cardId}`);
  const arrow = document.getElementById(`arrow-${cardId}`);
  if (!body || !arrow) return;
  const collapsed = body.classList.toggle('admin-card__body--collapsed');
  arrow.classList.toggle('admin-card__arrow--collapsed', collapsed);
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.meta-item[data-semana]').forEach((item) => {
    const semana = item.dataset.semana;
    const lockedByServer = item.dataset.locked === 'true';
    const lockedByClient = localStorage.getItem(`${META_LOCK_PREFIX}${semana}`) === '1';
    if (lockedByServer || lockedByClient) renderizarMetaBloqueada(semana);
  });

  document.querySelectorAll('.meta-item[data-meta-venda]').forEach((item) => {
    const mes = item.dataset.metaVenda;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaVendaBloqueada(mes);
  });

  document.querySelectorAll('.meta-item[data-meta-investidor]').forEach((item) => {
    const mes = item.dataset.metaInvestidor;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaInvestidorBloqueada(mes);
  });

  ADMIN_COLLAPSIBLES.forEach((cardId) => {
    const body = document.getElementById(`body-${cardId}`);
    const arrow = document.getElementById(`arrow-${cardId}`);
    if (body && arrow) {
      body.classList.add('admin-card__body--collapsed');
      arrow.classList.add('admin-card__arrow--collapsed');
    }
  });

  MESES.forEach(mesId => {
    const body  = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  document.querySelectorAll('.meta-item[data-meta-financeiro]').forEach((item) => {
    const semana = item.dataset.metaFinanceiro;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaFinanceiroBloqueada(semana);
  });

  document.querySelectorAll('.meta-item[data-meta-giro]').forEach((item) => {
    const semana = item.dataset.metaGiro;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaGiroBloqueada(semana);
  });

  document.querySelectorAll('.meta-item[data-meta-fornecedor]').forEach((item) => {
    const semana = item.dataset.metaFornecedor;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaFornecedorBloqueada(semana);
  });

  document.querySelectorAll('.meta-item[data-meta-negociacao-fornecedor]').forEach((item) => {
    const semana = item.dataset.metaNegociacaoFornecedor;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaNegociacaoFornecedorBloqueada(semana);
  });

  document.querySelectorAll('.meta-item[data-meta-medicao]').forEach((item) => {
    const semana = item.dataset.metaMedicao;
    const lockedByServer = item.dataset.locked === 'true';
    if (lockedByServer) renderizarMetaMedicaoBloqueada(semana);
  });

  MESES_FINANCEIRO.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_GIRO.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_FORNECEDORES.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_NEGOCIACAO_FORNECEDORES.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_MEDICAO.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_VENDAS.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });

  MESES_INVESTIDORES.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (body && arrow) {
      body.classList.add('mes-body--collapsed');
      arrow.classList.add('mes-arrow--collapsed');
    }
  });
});

function obterMetaInvestidorEls(mes) {
  return {
    item: document.querySelector(`.meta-item[data-meta-investidor="${mes}"]`),
    input: document.getElementById(`meta-investidor-${mes}`),
    acoesEl: document.getElementById(`acoes-investidor-${mes}`),
    btn: document.getElementById(`btn-meta-investidor-${mes}`),
  };
}

function renderizarMetaInvestidorBloqueada(mes) {
  const { item, input, acoesEl, btn } = obterMetaInvestidorEls(mes);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaInvestidor(mes, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaInvestidorEditavel(mes) {
  const { item, input, acoesEl, btn } = obterMetaInvestidorEls(mes);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar Meta';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaInvestidor(mes, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaInvestidor(mes, btn) {
  const input = document.getElementById(`meta-investidor-${mes}`);
  const acoesEl = document.getElementById(`acoes-investidor-${mes}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('investidores');

  try {
    const resp = await fetch('/admin/meta-investidor/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana: mes, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de ${mes} salva com sucesso!`, 'success');
      renderizarMetaInvestidorBloqueada(mes);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de investidores.', 'error');
    }
  } catch (error) {
    showToast('Erro ao salvar meta de investidores.', 'error');
  }
}

function editarMetaInvestidor(mes, btn) {
  renderizarMetaInvestidorEditavel(mes);
}

function editarMetaVenda(mes, btn) {
  renderizarMetaVendaEditavel(mes);
}

function obterMetaFinanceiroEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-meta-financeiro="${semana}"]`),
    input: document.getElementById(`meta-financeiro-s${semana}`),
    acoesEl: document.getElementById(`acoes-financeiro-s${semana}`),
    btn: document.getElementById(`btn-meta-financeiro-s${semana}`),
  };
}

function renderizarMetaFinanceiroBloqueada(semana) {
  const { item, input, acoesEl, btn } = obterMetaFinanceiroEls(semana);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaFinanceiro(semana, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaFinanceiroEditavel(semana) {
  const { item, input, acoesEl, btn } = obterMetaFinanceiroEls(semana);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaFinanceiro(semana, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaFinanceiro(semana, btn) {
  const input = document.getElementById(`meta-financeiro-s${semana}`);
  const acoesEl = document.getElementById(`acoes-financeiro-s${semana}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('financeiro');

  try {
    const resp = await fetch('/admin/meta-financeiro/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta financeira da semana ${semana} salva!`, 'success');
      renderizarMetaFinanceiroBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro ao salvar meta financeira.', 'error');
    }
  } catch {
    showToast('Erro ao salvar meta financeira.', 'error');
  }
}

function editarMetaFinanceiro(semana, btn) {
  renderizarMetaFinanceiroEditavel(semana);
}

function obterMetaGiroEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-meta-giro="${semana}"]`),
    input: document.getElementById(`meta-giro-s${semana}`),
    acoesEl: document.getElementById(`acoes-giro-s${semana}`),
    btn: document.getElementById(`btn-meta-giro-s${semana}`),
  };
}

function renderizarMetaGiroBloqueada(semana) {
  const { item, input, acoesEl, btn } = obterMetaGiroEls(semana);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaGiro(semana, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaGiroEditavel(semana) {
  const { item, input, acoesEl, btn } = obterMetaGiroEls(semana);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaGiro(semana, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaGiro(semana, btn) {
  const input = document.getElementById(`meta-giro-s${semana}`);
  const acoesEl = document.getElementById(`acoes-giro-s${semana}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('giro');

  try {
    const resp = await fetch('/admin/meta-giro/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de giro da semana ${semana} salva!`, 'success');
      renderizarMetaGiroBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de giro.', 'error');
    }
  } catch {
    showToast('Erro ao salvar meta de giro.', 'error');
  }
}

function editarMetaGiro(semana, btn) {
  renderizarMetaGiroEditavel(semana);
}

function obterMetaFornecedorEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-meta-fornecedor="${semana}"]`),
    input: document.getElementById(`meta-fornecedor-s${semana}`),
    acoesEl: document.getElementById(`acoes-fornecedor-s${semana}`),
    btn: document.getElementById(`btn-meta-fornecedor-s${semana}`),
  };
}

function renderizarMetaFornecedorBloqueada(semana) {
  const { item, input, acoesEl, btn } = obterMetaFornecedorEls(semana);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaFornecedor(semana, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaFornecedorEditavel(semana) {
  const { item, input, acoesEl, btn } = obterMetaFornecedorEls(semana);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaFornecedor(semana, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaFornecedor(semana, btn) {
  const input = document.getElementById(`meta-fornecedor-s${semana}`);
  const acoesEl = document.getElementById(`acoes-fornecedor-s${semana}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('fornecedores');
  try {
    const resp = await fetch('/admin/meta-fornecedor/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de fornecedores da semana ${semana} salva!`, 'success');
      renderizarMetaFornecedorBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de fornecedores.', 'error');
    }
  } catch {
    showToast('Erro ao salvar meta de fornecedores.', 'error');
  }
}

function editarMetaFornecedor(semana, btn) {
  renderizarMetaFornecedorEditavel(semana);
}

function obterMetaNegociacaoFornecedorEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-meta-negociacao-fornecedor="${semana}"]`),
    input: document.getElementById(`meta-negociacao-fornecedor-s${semana}`),
    acoesEl: document.getElementById(`acoes-negociacao-fornecedor-s${semana}`),
    btn: document.getElementById(`btn-meta-negociacao-fornecedor-s${semana}`),
  };
}

function renderizarMetaNegociacaoFornecedorBloqueada(semana) {
  const { item, input, acoesEl, btn } = obterMetaNegociacaoFornecedorEls(semana);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaNegociacaoFornecedor(semana, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaNegociacaoFornecedorEditavel(semana) {
  const { item, input, acoesEl, btn } = obterMetaNegociacaoFornecedorEls(semana);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaNegociacaoFornecedor(semana, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaNegociacaoFornecedor(semana, btn) {
  const input = document.getElementById(`meta-negociacao-fornecedor-s${semana}`);
  const acoesEl = document.getElementById(`acoes-negociacao-fornecedor-s${semana}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('negociacao_fornecedores');
  try {
    const resp = await fetch('/admin/meta-negociacao-fornecedores/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de negociação fornecedores da semana ${semana} salva!`, 'success');
      renderizarMetaNegociacaoFornecedorBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de negociação fornecedores.', 'error');
    }
  } catch {
    showToast('Erro ao salvar meta de negociação fornecedores.', 'error');
  }
}

function editarMetaNegociacaoFornecedor(semana, btn) {
  renderizarMetaNegociacaoFornecedorEditavel(semana);
}

function obterMetaMedicaoEls(semana) {
  return {
    item: document.querySelector(`.meta-item[data-meta-medicao="${semana}"]`),
    input: document.getElementById(`meta-medicao-s${semana}`),
    acoesEl: document.getElementById(`acoes-medicao-s${semana}`),
    btn: document.getElementById(`btn-meta-medicao-s${semana}`),
  };
}

function renderizarMetaMedicaoBloqueada(semana) {
  const { item, input, acoesEl, btn } = obterMetaMedicaoEls(semana);
  if (!input || !btn) return;
  input.readOnly = true;
  input.oninput = null;
  if (acoesEl) acoesEl.readOnly = true;
  aplicarEstadoBloqueado(btn, '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Editar', () => editarMetaMedicao(semana, btn));
  if (item) item.dataset.locked = 'true';
}

function renderizarMetaMedicaoEditavel(semana) {
  const { item, input, acoesEl, btn } = obterMetaMedicaoEls(semana);
  if (!input || !btn) return;
  input.readOnly = false;
  input.oninput = function () { formatarValorBR(this); };
  if (acoesEl) acoesEl.readOnly = false;
  btn.textContent = 'Salvar';
  btn.classList.remove('btn--ghost');
  btn.classList.add('btn--primary');
  btn.onclick = () => salvarMetaMedicao(semana, btn);
  if (item) item.dataset.locked = 'false';
}

async function salvarMetaMedicao(semana, btn) {
  const input = document.getElementById(`meta-medicao-s${semana}`);
  const acoesEl = document.getElementById(`acoes-medicao-s${semana}`);
  const valor = Math.max(parsearValorBR(input ? input.value : '0') || 0, 0);
  const acoes = parsearInteiroSeguro(acoesEl ? acoesEl.value : '0');
  const metaBaseTotal = obterMetaBase('medicao');

  try {
    const resp = await fetch('/admin/meta-medicao/salvar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ semana, valor_meta: valor, acoes_planejadas: acoes, meta_base_total: metaBaseTotal }),
    });
    const raw = await resp.text();
    const json = raw ? JSON.parse(raw) : {};
    if (resp.ok) {
      showToast(`Meta de medicao da semana ${semana} salva!`, 'success');
      renderizarMetaMedicaoBloqueada(semana);
    } else {
      showToast(json.erro || 'Erro ao salvar meta de medicao.', 'error');
    }
  } catch {
    showToast('Erro ao salvar meta de medicao.', 'error');
  }
}

function editarMetaMedicao(semana, btn) {
  renderizarMetaMedicaoEditavel(semana);
}

aprimorarCamposMetas();
