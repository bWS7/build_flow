'use strict';

let registrosCache = [];
let deleteState = { id: null, btnEl: null };
const MESES_FORNECEDORES = ['abril', 'maio', 'junho'];

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

function situacaoPositiva(situacao) {
  return situacao === 'SIM (INTEGRAL)' || situacao === 'SIM (PARCIAL)';
}

function badgeClassSituacao(situacao) {
  if (situacao === 'SIM (INTEGRAL)') return 'badge--sim';
  if (situacao === 'SIM (PARCIAL)') return 'badge--ligar-em-outro-momento';
  return 'badge--contato-rejeitado';
}

function atualizarIndicadores(ind) {
  document.getElementById('valor-meta').textContent = 'R$ ' + Math.round(ind.valor_meta || 0).toLocaleString('pt-BR');
  document.getElementById('valor-negociado').textContent = 'R$ ' + Math.round(ind.valor_negociado || 0).toLocaleString('pt-BR');
  document.getElementById('pct-atingimento').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('total-fornecedores').textContent = String(ind.total_fornecedores || 0);
  document.getElementById('bar-valor').style.width = `${ind.pct_valor || 0}%`;
  document.getElementById('pct-valor').textContent = `${ind.pct_valor || 0}%`;
  document.getElementById('txt-valor').textContent = `${fmtValor(ind.valor_negociado || 0)} de ${fmtValor(ind.valor_meta || 0)}`;
  document.getElementById('pct-empreendimentos').textContent = String(ind.total_empreendimentos || 0);
  document.getElementById('bar-empreendimentos').style.width = `${ind.total_empreendimentos ? 100 : 0}%`;
  document.getElementById('txt-empreendimentos').textContent = `${ind.total_empreendimentos || 0} empreendimentos com registro na semana`;
}

function abrirFicha(id) {
  const r = registrosCache.find((item) => item.id === id);
  if (!r) return;
  const podeEditar = podeGerenciarRegistro(r);
  document.getElementById('fi-id').textContent = `#${r.id}`;
  preencherSelect(document.getElementById('fi-empreendimento'), EMPREENDIMENTOS, r.empreendimento);
  preencherSelect(document.getElementById('fi-situacao'), SITUACOES, r.situacao);
  document.getElementById('fi-fornecedor').value = r.nome_fornecedor || '';
  document.getElementById('fi-servico').value = r.servico_prestado || '';
  document.getElementById('fi-email').value = r.email || '';
  document.getElementById('fi-telefone').value = r.telefone || '';
  document.getElementById('fi-valor').value = r.valor_negociado || 0;
  document.getElementById('fi-resp').value = r.responsavel || '';
  document.getElementById('fi-semana').value = `Semana ${r.semana}`;
  document.getElementById('fi-data').value = r.criado_em || '';
  document.getElementById('fi-obs').value = r.observacao || '';
  document.getElementById('form-ficha').dataset.id = String(r.id);
  document.getElementById('fi-permissao').textContent = podeEditar ? '' : 'Somente o responsavel ou admin pode editar este registro.';
  document.getElementById('btn-salvar-ficha').hidden = !podeEditar;
  ['fi-empreendimento', 'fi-fornecedor', 'fi-servico', 'fi-email', 'fi-telefone', 'fi-situacao', 'fi-valor', 'fi-obs'].forEach((idCampo) => {
    const campo = document.getElementById(idCampo);
    if (campo) campo.disabled = !podeEditar;
  });
  document.getElementById('modal-ficha').removeAttribute('hidden');
}

function closeFicha() { document.getElementById('modal-ficha').setAttribute('hidden', ''); }
function openDeleteModal(id, btnEl) { deleteState = { id, btnEl }; document.getElementById('modal-delete').removeAttribute('hidden'); }
function closeDeleteModal() { deleteState = { id: null, btnEl: null }; document.getElementById('modal-delete').setAttribute('hidden', ''); }

function toggleMesFornecedores(mesId) {
  const body = document.getElementById(`body-${mesId}`);
  const arrow = document.getElementById(`arrow-${mesId}`);
  if (!body || !arrow) return;
  const collapsed = body.classList.toggle('week-month__body--collapsed');
  arrow.classList.toggle('week-month__arrow--collapsed', collapsed);
}

function renderizarTabela(registros) {
  registrosCache = registros;
  const tbody = document.getElementById('tbody-fornecedores');
  const counter = document.getElementById('total-registros');
  counter.textContent = `${registros.length} registros`;

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="9" class="td-empty">Nenhum registro nesta semana. Cadastre o primeiro acima.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => {
    const classeRow = r.situacao === 'SIM (INTEGRAL)' ? 'row--sim' : (r.situacao === 'SIM (PARCIAL)' ? 'row--ligar' : '');
    const acaoExcluir = podeGerenciarRegistro(r)
      ? `<button class="btn-del" onclick="deletarRegistro(${r.id}, this)" title="Excluir">X</button>`
      : '';

    return `
      <tr data-id="${r.id}" class="${classeRow}" style="cursor:pointer" onclick="abrirFicha(${r.id})">
        <td class="td-id">${r.id}</td>
        <td>${r.empreendimento}</td>
        <td>${r.nome_fornecedor}</td>
        <td>${r.servico_prestado}</td>
        <td><span class="badge ${badgeClassSituacao(r.situacao)}">${r.situacao || 'NAO'}</span></td>
        <td class="td-valor">${fmtValor(r.valor_negociado)}</td>
        <td>${r.responsavel}</td>
        <td class="td-data">${(r.criado_em || '').split(' ')[0] || '-'}</td>
        <td onclick="event.stopPropagation()">${acaoExcluir}</td>
      </tr>`;
  }).join('');
}

let socket;
function conectarSocket() {
  socket = io({ transports: ['polling'] });
  socket.on('connect', () => { document.getElementById('live-badge').style.opacity = '1'; });
  socket.on('disconnect', () => { document.getElementById('live-badge').style.opacity = '.4'; });
  socket.on('fornecedores_atualizado', (payload) => {
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
  new FormData(form).forEach((v, k) => { dados[k] = String(v).trim(); });

  if (!dados.empreendimento || !dados.nome_fornecedor || !dados.servico_prestado || !dados.email || !dados.telefone || !dados.situacao || !dados.valor_negociado) {
    showToast('Preencha todos os campos obrigatorios.', 'error');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Salvando...';
  try {
    const resp = await fetch('/fornecedores/cadastrar', {
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
    showToast('Falha de conexao. Tente novamente.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar Registro';
  }
});

async function deletarRegistro(id, btnEl) { openDeleteModal(id, btnEl); }

async function confirmarExclusaoRegistro() {
  const { id, btnEl } = deleteState;
  if (!id || !btnEl) return;
  closeDeleteModal();
  btnEl.disabled = true;
  try {
    const resp = await fetch(`/fornecedores/registro/${id}`, { method: 'DELETE', headers: csrfHeaders() });
    const json = await resp.json();
    if (!resp.ok) {
      showToast(json.erro || 'Erro ao excluir.', 'error');
      btnEl.disabled = false;
    }
  } catch {
    showToast('Falha de conexao.', 'error');
    btnEl.disabled = false;
  }
}

async function salvarFicha() {
  const form = document.getElementById('form-ficha');
  const id = form.dataset.id;
  const registro = registrosCache.find((item) => item.id === Number(id));
  if (!registro || !podeGerenciarRegistro(registro)) {
    showToast('Voce nao pode editar este registro.', 'error');
    return;
  }

  const dados = {
    empreendimento: document.getElementById('fi-empreendimento').value.trim(),
    nome_fornecedor: document.getElementById('fi-fornecedor').value.trim(),
    servico_prestado: document.getElementById('fi-servico').value.trim(),
    email: document.getElementById('fi-email').value.trim(),
    telefone: document.getElementById('fi-telefone').value.trim(),
    situacao: document.getElementById('fi-situacao').value.trim(),
    valor_negociado: document.getElementById('fi-valor').value,
    observacao: document.getElementById('fi-obs').value.trim(),
  };

  const btn = document.getElementById('btn-salvar-ficha');
  btn.disabled = true;
  try {
    const resp = await fetch(`/fornecedores/registro/${id}`, {
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
    showToast('Falha de conexao.', 'error');
  } finally {
    btn.disabled = false;
  }
}

async function _buscarAtualizacao() {
  try {
    const resp = await fetch(`/fornecedores/registros?semana=${SEMANA_ATUAL}`);
    const json = await resp.json();
    atualizarIndicadores(json.indicadores || {});
    renderizarTabela(json.registros || []);
  } catch {}
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
  if (confirmDeleteBtn) confirmDeleteBtn.addEventListener('click', confirmarExclusaoRegistro);
  MESES_FORNECEDORES.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    body.classList.add('week-month__body--collapsed');
    arrow.classList.add('week-month__arrow--collapsed');
  });
  formWrapper.style.display = 'none';
  toggleBtn.textContent = '▼ Expandir';
});

conectarSocket();
