'use strict';

let registrosCache = [];
let acoesCache = [];
let deleteState = { id: null, btnEl: null };
const MESES_FINANCEIRO = ['abril', 'maio', 'junho'];

function renderizarOpcoesAcao() {
  const feedback = document.getElementById('acao-feedback');
  if (!feedback) return;
  feedback.textContent = registrosCache.length
    ? 'A acao sera registrada normalmente nesta semana.'
    : 'Voce pode registrar uma acao diretamente, mesmo sem registro anterior.';
}


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

function resumoPlanejadoRealizado(valorAtual, valorMeta, acoesRealizadas, acoesPlanejadas) {
  return `${fmtValor(valorAtual)} de ${fmtValor(valorMeta)} na metrica • ${acoesRealizadas || 0} de ${acoesPlanejadas || 0} acoes`;
}

function badgeClassNegociacao(negociacao) {
  return negociacao === 'INTEGRAL' ? 'badge--sim' : 'badge--ligar-em-outro-momento';
}

function atualizarIndicadores(ind) {
  const metaBase = document.getElementById('meta-base-total');
  if (metaBase) metaBase.textContent = 'R$ ' + Math.round(ind.meta_base_total || 0).toLocaleString('pt-BR');
  const valorMeta = document.getElementById('valor-meta');
  if (valorMeta) valorMeta.textContent = 'R$ ' + Math.round(ind.valor_meta || 0).toLocaleString('pt-BR');
  const valorPrincipal = document.getElementById('valor-arrecadado') || document.getElementById('valor-captado') || document.getElementById('valor-negociado') || document.getElementById('valor-realizado');
  const valorAtual = ind.valor_arrecadado || 0;
  if (valorPrincipal) valorPrincipal.textContent = 'R$ ' + Math.round(valorAtual).toLocaleString('pt-BR');
  const acoesPlanejadas = document.getElementById('acoes-planejadas');
  if (acoesPlanejadas) acoesPlanejadas.textContent = String(ind.acoes_planejadas || 0);
  const acoesRealizadas = document.getElementById('acoes-realizadas');
  if (acoesRealizadas) acoesRealizadas.textContent = String(ind.acoes_realizadas || 0);
  document.getElementById('bar-valor').style.width = `${ind.pct_valor || 0}%`;
  document.getElementById('pct-valor').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('txt-valor').textContent = `${fmtValor(valorAtual)} de ${fmtValor(ind.valor_meta || 0)}`;
  document.getElementById('pct-acoes').textContent = `${ind.pct_acoes || 0}%`;
  document.getElementById('bar-acoes').style.width = `${Math.min(ind.pct_acoes || 0, 100)}%`;
  document.getElementById('txt-acoes').textContent = `${ind.acoes_realizadas || 0} de ${ind.acoes_planejadas || 0} acoes realizadas`;
  const resumoBar = document.getElementById('bar-resumo');
  if (resumoBar) resumoBar.style.width = `${Math.min(ind.pct_planejado_realizado || ind.pct_valor || 0, 100)}%`;
  const resumoTexto = document.getElementById('txt-resumo');
  if (resumoTexto) resumoTexto.textContent = resumoPlanejadoRealizado(valorAtual, ind.valor_meta || 0, ind.acoes_realizadas || 0, ind.acoes_planejadas || 0);
}

function abrirFicha(id) {
  const r = registrosCache.find((item) => item.id === id);
  if (!r) return;
  const podeEditar = podeGerenciarRegistro(r);
  document.getElementById('fi-id').textContent = `#${r.id}`;
  preencherSelect(document.getElementById('fi-banco'), BANCOS, r.banco);
  preencherSelect(document.getElementById('fi-negociacao'), NEGOCIACOES, r.negociacao);
  document.getElementById('fi-valor').value = r.valor_arrecadado || 0;
  document.getElementById('fi-tipo').value = r.tipo_negociacao || '';
  document.getElementById('fi-referencia').value = r.referencia || '';
  document.getElementById('fi-resp').value = r.responsavel || '';
  document.getElementById('fi-semana').value = `Semana ${r.semana}`;
  document.getElementById('fi-data').value = r.criado_em || '';
  document.getElementById('fi-obs').value = r.observacao || '';
  document.getElementById('fi-acao').value = r.acao_realizada || '';
  document.getElementById('form-ficha').dataset.id = String(r.id);
  document.getElementById('fi-permissao').textContent = podeEditar ? '' : 'Somente o responsável ou admin pode editar este registro.';
  document.getElementById('btn-salvar-ficha').hidden = !podeEditar;
  ['fi-banco', 'fi-negociacao', 'fi-valor', 'fi-tipo', 'fi-referencia', 'fi-obs', 'fi-acao'].forEach((idCampo) => {
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

function toggleMesFinanceiro(mesId) {
  const body = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  if (!body || !arrow) return;
  const collapsed = body.classList.toggle('week-month__body--collapsed');
  arrow.classList.toggle('week-month__arrow--collapsed', collapsed);
}

function renderizarTabela(registros) {
  registrosCache = registros;
  const tbody = document.getElementById('tbody-bancos');
  const counter = document.getElementById('total-registros');
  counter.textContent = `${registros.length} registros`;

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="9" class="td-empty">Nenhum registro nesta semana. Cadastre o primeiro acima.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => {
    const classeRow = r.negociacao === 'INTEGRAL' ? 'row--sim' : 'row--ligar';
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
      <tr data-id="${r.id}" class="${classeRow}" style="cursor:pointer" onclick="abrirFicha(${r.id})">
        <td class="td-id">${r.id}</td>
        <td>${r.banco}</td>
        <td><span class="badge ${badgeClassNegociacao(r.negociacao)}">${r.negociacao || '—'}</span></td>
        <td class="td-valor">${fmtValor(r.valor_arrecadado)}</td>
        <td>${r.tipo_negociacao}</td>
        <td>${r.referencia || '—'}</td>
        <td>${r.responsavel}</td>
        <td class="td-data">${(r.criado_em || '').split(' ')[0] || '—'}</td>
        <td onclick="event.stopPropagation()">${acaoExcluir}</td>
      </tr>`;
  }).join('');
}

function renderizarTabelaAcoes(acoes) {
  const tbody = document.getElementById('tbody-acoes-bancos');
  const counter = document.getElementById('total-acoes');
  if (!tbody || !counter) return;
  acoesCache = Array.isArray(acoes) ? acoes : [];
  counter.textContent = `${acoesCache.length} acoes`;

  if (!acoesCache.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="td-empty">Nenhuma acao registrada nesta semana.</td></tr>';
    return;
  }

  tbody.innerHTML = acoesCache.map((r) => `
      <tr>
        <td class="td-id">${r.id}</td>
        <td>${r.registro_id ? ('Registro #' + r.registro_id) : 'Acao direta'}</td>
        <td>${r.descricao || '-'}</td>
        <td>${r.responsavel || '-'}</td>
        <td class="td-data">${r.data || '-'}</td>
        <td>${IS_ADMIN || r.responsavel === CURRENT_USER_NOME ? `<button class="btn-del" onclick="deletarAcao(${r.id}, this)" title="Excluir acao"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg></button>` : ''}</td>
      </tr>`).join('');
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
  socket.on('financeiro_atualizado', (payload) => {
    if (payload.indicadores && payload.indicadores.semana === SEMANA_ATUAL) {
      atualizarIndicadores(payload.indicadores);
      renderizarTabela(payload.registros || []);
      renderizarTabelaAcoes(payload.acoes || []);
      renderizarOpcoesAcao();
    }
  });
}

document.getElementById('form-cadastro').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = document.getElementById('btn-salvar');
  const dados = {};
  new FormData(form).forEach((v, k) => { dados[k] = v.trim(); });

  if (!dados.banco || !dados.negociacao || !dados.valor_arrecadado || !dados.tipo_negociacao || !dados.referencia) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvando...';

  try {
    const resp = await fetch('/financeiro/cadastrar', {
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
    const resp = await fetch(`/financeiro/registro/${id}`, {
      method: 'DELETE',
      headers: csrfHeaders(),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      const atualizados = registrosCache.filter((registro) => registro.id !== id);
      renderizarTabela(atualizados);
      renderizarTabelaAcoes(acoesCache);
      renderizarOpcoesAcao();
      showToast('Registro excluido com sucesso!', 'success');
      _buscarAtualizacao();
    } else {
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
    banco: document.getElementById('fi-banco').value.trim(),
    negociacao: document.getElementById('fi-negociacao').value.trim(),
    valor_arrecadado: document.getElementById('fi-valor').value,
    tipo_negociacao: document.getElementById('fi-tipo').value.trim(),
    referencia: document.getElementById('fi-referencia').value.trim(),
    observacao: document.getElementById('fi-obs').value.trim(),
    acao_realizada: document.getElementById('fi-acao').value.trim(),
  };

  if (!dados.banco || !dados.negociacao || !dados.valor_arrecadado || !dados.tipo_negociacao || !dados.referencia) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const resp = await fetch(`/financeiro/registro/${id}`, {
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
    const resp = await fetch(`/financeiro/registros?semana=${SEMANA_ATUAL}`);
    const json = await resp.json();
    atualizarIndicadores(json.indicadores || {});
    renderizarTabela(json.registros || []);
    renderizarTabelaAcoes(json.acoes || []);
    renderizarOpcoesAcao();
  } catch {
    // websocket cobre esse fluxo na maior parte do tempo
  }
}

const toggleBtn = document.getElementById('toggle-form');
const formWrapper = document.getElementById('form-wrapper');
const actionToggleBtn = document.getElementById('toggle-action-form');
const actionFormWrapper = document.getElementById('action-form-wrapper');
let formVisible = false;
let actionFormVisible = false;

if (toggleBtn && formWrapper) {
  toggleBtn.addEventListener('click', () => {
    formVisible = !formVisible;
    formWrapper.style.display = formVisible ? '' : 'none';
    toggleBtn.textContent = formVisible ? '- Recolher' : '+ Expandir';
  });
}

if (actionToggleBtn && actionFormWrapper) {
  actionToggleBtn.addEventListener('click', () => {
    actionFormVisible = !actionFormVisible;
    actionFormWrapper.style.display = actionFormVisible ? '' : 'none';
    actionToggleBtn.textContent = actionFormVisible ? '- Recolher' : '+ Expandir';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  registrosCache = Array.isArray(INITIAL_REGISTROS) ? INITIAL_REGISTROS : [];
  acoesCache = Array.isArray(INITIAL_ACOES) ? INITIAL_ACOES : [];
  renderizarTabela(registrosCache);
  renderizarTabelaAcoes(acoesCache);
  renderizarOpcoesAcao();
  _buscarAtualizacao();
  const formAcao = document.getElementById('form-acao');
  if (formAcao) {
    formAcao.addEventListener('submit', (event) => {
      event.preventDefault();
      salvarAcaoRealizada();
    });
  }
  const btnLimparAcao = document.getElementById('btn-limpar-acao');
  if (btnLimparAcao) {
    btnLimparAcao.addEventListener('click', () => {
      const textarea = document.getElementById('acao-descricao');
      const feedback = document.getElementById('acao-feedback');
      if (textarea) textarea.value = '';
      if (feedback) feedback.textContent = registrosCache.length
        ? 'A acao sera registrada normalmente nesta semana.'
        : 'Voce pode registrar uma acao diretamente, mesmo sem registro anterior.';
    });
  }
  const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener('click', confirmarExclusaoRegistro);
  }
  MESES_FINANCEIRO.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    body.classList.add('week-month__body--collapsed');
    arrow.classList.add('week-month__arrow--collapsed');
  });
  if (formWrapper && toggleBtn) {
    formWrapper.style.display = 'none';
    toggleBtn.textContent = '+ Expandir';
  }
  if (actionFormWrapper && actionToggleBtn) {
    actionFormWrapper.style.display = 'none';
    actionToggleBtn.textContent = '+ Expandir';
  }
});

conectarSocket();


async function salvarAcaoRealizada() {
  const textarea = document.getElementById('acao-descricao');
  const feedback = document.getElementById('acao-feedback');
  const btn = document.getElementById('btn-salvar-acao');
  const acao = textarea ? textarea.value.trim() : '';
  if (!acao) {
    showToast('Descreva a acao realizada.', 'error');
    return;
  }
  btn.disabled = true;
  if (feedback) feedback.textContent = 'Salvando acao...';
  try {
    const resp = await fetch('/financeiro/acao', { method: 'POST', headers: csrfHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ semana: SEMANA_ATUAL, acao_realizada: acao }) });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast('Acao registrada com sucesso!', 'success');
      if (textarea) textarea.value = '';
      if (feedback) feedback.textContent = 'Acao salva com sucesso.';
      _buscarAtualizacao();
    } else {
      if (feedback) feedback.textContent = '';
      showToast(json.erro || 'Erro ao salvar a acao.', 'error');
    }
  } catch {
    if (feedback) feedback.textContent = '';
    showToast('Falha de conexao. Tente novamente.', 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deletarAcao(id, btnEl) {
  if (!id || !btnEl) return;
  btnEl.disabled = true;
  try {
    const resp = await fetch(`/financeiro/acao/${id}`, {
      method: 'DELETE',
      headers: csrfHeaders(),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      renderizarTabelaAcoes(acoesCache.filter((acao) => acao.id !== id));
      showToast('Acao excluida com sucesso!', 'success');
      _buscarAtualizacao();
    } else {
      showToast(json.erro || 'Erro ao excluir acao.', 'error');
      btnEl.disabled = false;
    }
  } catch {
    showToast('Falha de conexao.', 'error');
    btnEl.disabled = false;
  }
}
