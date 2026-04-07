'use strict';

let registrosCache = [];
let deleteState = { id: null, btnEl: null };
const MESES_RELACIONAMENTO = ['abril', 'maio', 'junho'];

function renderizarOpcoesAcao() {
  const select = document.getElementById('acao-registro-id');
  if (!select) return;
  const atual = select.value;
  const options = ['<option value="">Selecione...</option>'];
  registrosCache.forEach((r) => options.push(`<option value="${r.id}">${r.cliente || 'Registro'} - ${r.empreendimento || ('#' + r.id)}</option>`));
  select.innerHTML = options.join('');
  if (registrosCache.some((r) => String(r.id) === atual)) select.value = atual;
  select.disabled = !registrosCache.length;
}

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': window.APP_CSRF_TOKEN || '', ...extra };
}

function podeExcluirRegistro(registro) {
  return IS_ADMIN || registro.responsavel === CURRENT_USER_NOME;
}

function podeEditarRegistro(registro) {
  return IS_ADMIN || registro.responsavel === CURRENT_USER_NOME;
}

function preencherSelect(el, options, selectedValue) {
  if (!el) return;
  el.innerHTML = options.map((option) => {
    const selected = option === selectedValue ? ' selected' : '';
    return `<option value="${option}"${selected}>${option}</option>`;
  }).join('');
}

function isSituacaoRejeitada(situacao) {
  return ['NÃO', 'NAO', 'CONTATO REJEITADO'].includes(situacao);
}

function isSituacaoPositiva(situacao) {
  return ['SIM', 'SIM (INTEGRAL)', 'SIM (PARCIAL)'].includes(situacao);
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
  return v > 0
    ? 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: 2 })
    : '—';
}

function atualizarIndicadores(ind) {
  const metaBase = document.getElementById('meta-base-total');
  if (metaBase) metaBase.textContent = 'R$ ' + Math.round(ind.meta_base_total || 0).toLocaleString('pt-BR');
  document.getElementById('acoes-planejadas').textContent = String(ind.acoes_planejadas || 0);
  document.getElementById('acoes-realizadas').textContent = String(ind.acoes_realizadas || 0);
  document.getElementById('valor-meta').textContent =
    'R$ ' + Math.round(ind.valor_meta || 0).toLocaleString('pt-BR');
  document.getElementById('valor-realizado').textContent =
    'R$ ' + Math.round(ind.soma_valores || 0).toLocaleString('pt-BR');

  document.getElementById('bar-acoes').style.width = `${Math.min(ind.pct_acoes || 0, 100)}%`;
  document.getElementById('pct-acoes').textContent = `${ind.pct_acoes || 0}%`;
  document.getElementById('txt-acoes').textContent =
    `${ind.acoes_realizadas || 0} de ${ind.acoes_planejadas || 0} acoes`;

  document.getElementById('bar-valor').style.width = `${Math.min(ind.pct_valor || 0, 100)}%`;
  document.getElementById('pct-valor').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('txt-valor').textContent =
    `${fmtValor(ind.soma_valores || 0)} de ${fmtValor(ind.valor_meta || 0)}`;

  const resumoBar = document.getElementById('bar-resumo');
  if (resumoBar) resumoBar.style.width = `${Math.min(ind.pct_valor || 0, 100)}%`;
  const resumoTexto = document.getElementById('txt-resumo');
  if (resumoTexto) resumoTexto.textContent = `${fmtValor(ind.soma_valores || 0)} realizados e ${ind.acoes_realizadas || 0} acoes registradas nesta semana.`;
}

function statusIcon(situacao) {
  if (isSituacaoPositiva(situacao)) {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  }
  if (isSituacaoRejeitada(situacao)) {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  }
  if (situacao === 'LIGAR EM OUTRO MOMENTO') {
    return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
  }
  return '<span style="color:#ccc">—</span>';
}

function abrirFicha(id) {
  const r = registrosCache.find(x => x.id === id);
  if (!r) return;
  const podeEditar = podeEditarRegistro(r);
  document.getElementById('fi-id').textContent = `#${r.id}`;
  document.getElementById('fi-cliente').value = r.cliente;
  preencherSelect(document.getElementById('fi-emp'), EMPREENDIMENTOS, r.empreendimento);
  document.getElementById('fi-tel').value = r.telefone;
  document.getElementById('fi-email').value = r.email_cliente || '';
  preencherSelect(document.getElementById('fi-tipo'), TIPOS_CONTATO, r.tipo_contato);
  preencherSelect(document.getElementById('fi-situacao'), SITUACOES, r.situacao);
  document.getElementById('fi-valor').value = r.valor || 0;
  document.getElementById('fi-resp').value = r.responsavel;
  document.getElementById('fi-semana').value = `Semana ${r.semana}`;
  document.getElementById('fi-data').value = r.criado_em;
  document.getElementById('fi-obs').value = r.observacao || '';
  document.getElementById('fi-acao').value = r.acao_realizada || '';
  document.getElementById('form-ficha').dataset.id = String(r.id);
  document.getElementById('fi-permissao').textContent = podeEditar ? '' : 'Somente o responsável ou admin pode editar este registro.';
  document.getElementById('btn-salvar-ficha').hidden = !podeEditar;
  ['fi-cliente', 'fi-emp', 'fi-tel', 'fi-email', 'fi-tipo', 'fi-situacao', 'fi-valor', 'fi-obs', 'fi-acao']
    .forEach((idCampo) => {
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

function toggleMesRelacionamento(mesId) {
  const body = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  if (!body || !arrow) return;
  const collapsed = body.classList.toggle('week-month__body--collapsed');
  arrow.classList.toggle('week-month__arrow--collapsed', collapsed);
}

function renderizarTabela(registros) {
  registrosCache = registros;
  const tbody = document.getElementById('tbody-clientes');
  const counter = document.getElementById('total-registros');
  counter.textContent = registros.length + ' registros';

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="11" class="td-empty">Nenhum registro nesta semana. Cadastre o primeiro acima.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => {
    const classeRow = isSituacaoPositiva(r.situacao) ? 'row--sim'
      : isSituacaoRejeitada(r.situacao) ? 'row--rejeitado'
      : r.situacao === 'LIGAR EM OUTRO MOMENTO' ? 'row--ligar' : '';
    const classeBadge = isSituacaoPositiva(r.situacao) ? 'badge--sim'
      : isSituacaoRejeitada(r.situacao) ? 'badge--contato-rejeitado'
      : r.situacao === 'LIGAR EM OUTRO MOMENTO' ? 'badge--ligar-em-outro-momento'
      : 'badge--não';
    const acaoExcluir = podeExcluirRegistro(r)
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
        <td>${r.empreendimento}</td>
        <td class="td-nome">${r.cliente}</td>
        <td>${r.telefone}</td>
        <td>${r.tipo_contato}</td>
        <td><span class="badge ${classeBadge}">${r.situacao}</span></td>
        <td class="td-valor">${fmtValor(r.valor)}</td>
        <td>${r.responsavel}</td>
        <td class="td-data">${r.criado_em.split(' ')[0]}</td>
        <td class="td-icon">${statusIcon(r.situacao)}</td>
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
  socket.on('dados_atualizados', (payload) => {
    if (payload.indicadores && payload.indicadores.semana === SEMANA_ATUAL) {
      atualizarIndicadores(payload.indicadores);
      renderizarTabela(payload.registros);
    }
  });
}

document.getElementById('form-cadastro').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = document.getElementById('btn-salvar');
  const dados = {};
  new FormData(form).forEach((v, k) => { dados[k] = v.trim(); });

  if (!dados.empreendimento || !dados.cliente || !dados.telefone || !dados.tipo_contato || !dados.situacao) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvando...';

  try {
    const resp = await fetch('/relacionamento/cadastrar', {
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
    const resp = await fetch(`/relacionamento/registro/${id}`, {
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
  if (!registro || !podeEditarRegistro(registro)) {
    showToast('Você não pode editar este registro.', 'error');
    return;
  }

  const btn = document.getElementById('btn-salvar-ficha');
  const dados = {
    empreendimento: document.getElementById('fi-emp').value.trim(),
    cliente: document.getElementById('fi-cliente').value.trim(),
    telefone: document.getElementById('fi-tel').value.trim(),
    email_cliente: document.getElementById('fi-email').value.trim(),
    tipo_contato: document.getElementById('fi-tipo').value.trim(),
    situacao: document.getElementById('fi-situacao').value.trim(),
    valor: document.getElementById('fi-valor').value,
    observacao: document.getElementById('fi-obs').value.trim(),
    acao_realizada: document.getElementById('fi-acao').value.trim(),
  };

  if (!dados.empreendimento || !dados.cliente || !dados.telefone || !dados.tipo_contato || !dados.situacao) {
    showToast('Preencha todos os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const resp = await fetch(`/relacionamento/registro/${id}`, {
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
    const resp = await fetch(`/relacionamento/registros?semana=${SEMANA_ATUAL}`);
    const json = await resp.json();
    atualizarIndicadores(json.indicadores);
    renderizarTabela(json.registros);
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
  renderizarTabela(registrosCache);
  renderizarOpcoesAcao();
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
      const select = document.getElementById('acao-registro-id');
      const textarea = document.getElementById('acao-descricao');
      const feedback = document.getElementById('acao-feedback');
      if (select) select.value = '';
      if (textarea) textarea.value = '';
      if (feedback) feedback.textContent = '';
    });
  }
  const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener('click', confirmarExclusaoRegistro);
  }
  MESES_RELACIONAMENTO.forEach((mesId) => {
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
  const select = document.getElementById('acao-registro-id');
  const textarea = document.getElementById('acao-descricao');
  const feedback = document.getElementById('acao-feedback');
  const btn = document.getElementById('btn-salvar-acao');
  const id = select ? select.value : '';
  const acao = textarea ? textarea.value.trim() : '';
  if (!id || !acao) {
    showToast('Selecione um registro e descreva a acao realizada.', 'error');
    return;
  }
  btn.disabled = true;
  if (feedback) feedback.textContent = 'Salvando acao...';
  try {
    const resp = await fetch('/relacionamento/acao', { method: 'POST', headers: csrfHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ id, acao_realizada: acao }) });
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
