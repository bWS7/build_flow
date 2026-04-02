'use strict';

let registrosCache = [];
let deleteState = { id: null, btnEl: null };
const MESES_MEDICAO = ['abril', 'maio', 'junho'];

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': window.APP_CSRF_TOKEN || '', ...extra };
}

function podeGerenciarRegistro(registro) {
  return IS_ADMIN || registro.responsavel === CURRENT_USER_NOME;
}

function preencherSelect(el, options, selectedValue) {
  if (!el) return;
  el.innerHTML = options.map((option) => {
    const selected = option === selectedValue ? ' selected' : '';
    return `<option value="${option}"${selected}>${option}</option>`;
  }).join('');
}

let toastTimer;
function showToast(msg, tipo = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast toast--${tipo} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

function fmtValor(v) {
  return 'R$ ' + Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 });
}

function atualizarIndicadores(ind) {
  document.getElementById('valor-meta').textContent = 'R$ ' + Math.round(ind.valor_meta || 0).toLocaleString('pt-BR');
  document.getElementById('valor-realizado').textContent = 'R$ ' + Math.round(ind.valor_realizado || 0).toLocaleString('pt-BR');
  document.getElementById('pct-atingimento').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('total-medicoes').textContent = String(ind.total_medicoes || 0);
  document.getElementById('bar-valor').style.width = `${ind.pct_valor || 0}%`;
  document.getElementById('pct-valor').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('txt-valor').textContent = `${fmtValor(ind.valor_realizado || 0)} de ${fmtValor(ind.valor_meta || 0)}`;
  document.getElementById('pct-empreendimentos').textContent = String(ind.total_empreendimentos || 0);
  document.getElementById('bar-empreendimentos').style.width = `${ind.total_empreendimentos ? 100 : 0}%`;
  document.getElementById('txt-empreendimentos').textContent = `${ind.total_empreendimentos || 0} empreendimentos com medição na semana`;
}

function abrirFicha(id) {
  const r = registrosCache.find((item) => item.id === id);
  if (!r) return;
  const podeEditar = podeGerenciarRegistro(r);
  document.getElementById('fi-id').textContent = `#${r.id}`;
  preencherSelect(document.getElementById('fi-empreendimento'), EMPREENDIMENTOS, r.empreendimento);
  document.getElementById('fi-valor').value = r.valor_medicao || 0;
  document.getElementById('fi-resp').value = r.responsavel || '';
  document.getElementById('fi-semana').value = `Semana ${r.semana}`;
  document.getElementById('fi-data').value = r.criado_em || '';
  document.getElementById('fi-obs').value = r.observacao || '';
  document.getElementById('form-ficha').dataset.id = String(r.id);
  document.getElementById('fi-permissao').textContent = podeEditar ? '' : 'Somente o responsável ou admin pode editar este registro.';
  document.getElementById('btn-salvar-ficha').hidden = !podeEditar;
  ['fi-empreendimento', 'fi-valor', 'fi-obs'].forEach((idCampo) => {
    const campo = document.getElementById(idCampo);
    if (campo) campo.disabled = !podeEditar;
  });
  document.getElementById('modal-ficha').removeAttribute('hidden');
}

function closeFicha() {
  document.getElementById('modal-ficha').setAttribute('hidden', '');
}

function openDeleteModal(id, btnEl) {
  deleteState = { id, btnEl };
  document.getElementById('modal-delete').removeAttribute('hidden');
}

function closeDeleteModal() {
  deleteState = { id: null, btnEl: null };
  document.getElementById('modal-delete').setAttribute('hidden', '');
}

function toggleMesMedicao(mesId) {
  const body = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  if (!body || !arrow) return;
  const collapsed = body.classList.toggle('week-month__body--collapsed');
  arrow.classList.toggle('week-month__arrow--collapsed', collapsed);
}

function renderizarTabela(registros) {
  registrosCache = registros;
  const tbody = document.getElementById('tbody-medicoes');
  const counter = document.getElementById('total-registros');
  counter.textContent = `${registros.length} registros`;

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="6" class="td-empty">Nenhum registro nesta semana. Cadastre o primeiro acima.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => {
    const acaoExcluir = podeGerenciarRegistro(r)
      ? `<button class="btn-del" onclick="deletarRegistro(${r.id}, this)" title="Excluir">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/>
            <path d="M19 6l-1 14H6L5 6"/>
            <path d="M10 11v6M14 11v6"/>
            <path d="M9 6V4h6v2"/>
          </svg>
        </button>`
      : '';

    return `
      <tr data-id="${r.id}" style="cursor:pointer" onclick="abrirFicha(${r.id})">
        <td class="td-id">${r.id}</td>
        <td>${r.empreendimento}</td>
        <td class="td-valor">${fmtValor(r.valor_medicao)}</td>
        <td>${r.responsavel}</td>
        <td class="td-data">${(r.criado_em || '').split(' ')[0] || '—'}</td>
        <td onclick="event.stopPropagation()">${acaoExcluir}</td>
      </tr>`;
  }).join('');
}

let socket;
function conectarSocket() {
  socket = io({ transports: ['polling'] });
  socket.on('connect', () => {
    document.getElementById('live-badge').style.opacity = '1';
  });
  socket.on('disconnect', () => {
    document.getElementById('live-badge').style.opacity = '.4';
  });
  socket.on('medicao_atualizada', (payload) => {
    if (payload.indicadores && payload.indicadores.semana === SEMANA_ATUAL) {
      atualizarIndicadores(payload.indicadores);
      renderizarTabela(payload.registros || []);
    }
  });
}

document.getElementById('form-cadastro').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = document.getElementById('btn-salvar');
  const dados = {};
  new FormData(form).forEach((v, k) => { dados[k] = v.trim(); });

  if (!dados.empreendimento || !dados.valor_medicao) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvando...';

  try {
    const resp = await fetch('/medicao/cadastrar', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast('Registro salvo com sucesso!', 'success');
      form.reset();
      _buscarAtualizacao();
    } else {
      showToast(json.erro || 'Erro ao salvar.', 'error');
    }
  } catch {
    showToast('Falha de conexão. Tente novamente.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Salvar Registro';
  }
});

async function deletarRegistro(id, btnEl) {
  openDeleteModal(id, btnEl);
}

async function confirmarExclusaoRegistro() {
  const { id, btnEl } = deleteState;
  if (!id || !btnEl) return;

  closeDeleteModal();
  btnEl.disabled = true;

  try {
    const resp = await fetch(`/medicao/registro/${id}`, {
      method: 'DELETE',
      headers: csrfHeaders(),
    });
    const json = await resp.json();
    if (!resp.ok) {
      showToast(json.erro || 'Erro ao excluir.', 'error');
      btnEl.disabled = false;
    }
  } catch {
    showToast('Falha de conexão.', 'error');
    btnEl.disabled = false;
  }
}

async function salvarFicha() {
  const form = document.getElementById('form-ficha');
  const id = form.dataset.id;
  const registro = registrosCache.find((item) => item.id === Number(id));
  if (!registro || !podeGerenciarRegistro(registro)) {
    showToast('Você não pode editar este registro.', 'error');
    return;
  }

  const btn = document.getElementById('btn-salvar-ficha');
  const dados = {
    empreendimento: document.getElementById('fi-empreendimento').value.trim(),
    valor_medicao: document.getElementById('fi-valor').value,
    observacao: document.getElementById('fi-obs').value.trim(),
  };

  if (!dados.empreendimento || !dados.valor_medicao) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const resp = await fetch(`/medicao/registro/${id}`, {
      method: 'PUT',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast('Registro atualizado com sucesso!', 'success');
      closeFicha();
      _buscarAtualizacao();
    } else {
      showToast(json.erro || 'Erro ao atualizar.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  } finally {
    btn.disabled = false;
  }
}

async function _buscarAtualizacao() {
  try {
    const resp = await fetch(`/medicao/registros?semana=${SEMANA_ATUAL}`);
    const json = await resp.json();
    atualizarIndicadores(json.indicadores || {});
    renderizarTabela(json.registros || []);
  } catch {
    // websocket cobre esse fluxo na maior parte do tempo
  }
}

const toggleBtn = document.getElementById('toggle-form');
const formWrapper = document.getElementById('form-wrapper');
let formVisible = false;
toggleBtn.addEventListener('click', () => {
  formVisible = !formVisible;
  formWrapper.style.display = formVisible ? '' : 'none';
  toggleBtn.textContent = formVisible ? '▲ Recolher' : '▼ Expandir';
});

document.addEventListener('DOMContentLoaded', () => {
  registrosCache = Array.isArray(INITIAL_REGISTROS) ? INITIAL_REGISTROS : [];
  renderizarTabela(registrosCache);
  const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener('click', confirmarExclusaoRegistro);
  }
  MESES_MEDICAO.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    body.classList.add('week-month__body--collapsed');
    arrow.classList.add('week-month__arrow--collapsed');
  });
  if (formWrapper && toggleBtn) {
    formWrapper.style.display = 'none';
    toggleBtn.textContent = '▼ Expandir';
  }
});

conectarSocket();
