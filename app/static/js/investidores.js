'use strict';

let investidoresCache = [];
let investidoresFiltradosCache = [];
let activeSituacaoChart = '';
let deleteState = { id: null, btnEl: null, mode: 'single' };
const MESES_INVESTIDORES_TOPBAR = ['abril', 'maio', 'junho'];

function csrfHeaders(extra = {}) {
  return { 'X-CSRFToken': window.APP_CSRF_TOKEN || '', ...extra };
}

let toastTimer;
function showToast(msg, tipo = 'success') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast toast--${tipo} show`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

function fmtMoeda(valor) {
  return 'R$ ' + Number(valor || 0).toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtMoedaInteira(valor) {
  return 'R$ ' + Math.round(Number(valor || 0)).toLocaleString('pt-BR');
}

function normalizarSituacaoLabel(valor) {
  return String(valor || '').trim().toUpperCase();
}

function normalizarChaveGrafico(valor) {
  return String(valor || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim()
    .toUpperCase();
}

function situacaoParaLabelGrafico(situacao) {
  const valor = normalizarChaveGrafico(situacao);
  if (valor === 'CONTRATO ASSINADO' || valor === 'CONTRATO ASSINADO CLIENTES') {
    return 'Contrato Assinado / Contrato Assinado Clientes';
  }
  const mapa = {
    VENDIDA: 'Vendida',
    CANCELADA: 'Cancelada',
    CONFECCAO_DE_CONTRATO: 'Confecção de Contrato',
    'CONFECCAO DE CONTRATO': 'Confecção de Contrato',
    'ENVIO UAU': 'Envio UAU',
    'NOVA RESERVA': 'Nova Reserva',
    'PENDENTE DE ASSINATURA': 'Pendente de Assinatura',
  };
  return mapa[valor] || situacao;
}

function preencherSelect(el, options, selectedValue) {
  if (!el) return;
  el.innerHTML = options.map((option) => {
    const selected = option === selectedValue ? ' selected' : '';
    return `<option value="${option}"${selected}>${option}</option>`;
  }).join('');
}

function escaparCsv(valor) {
  const texto = String(valor ?? '');
  if (/[;"\n]/.test(texto)) {
    return `"${texto.replace(/"/g, '""')}"`;
  }
  return texto;
}

function baixarCsvAtual() {
  const linhas = [
    ['Reserva', 'Data', 'Situacao', 'Empreendimento', 'Bloco', 'Unidade', 'Cliente', 'Corretor', 'Imobiliaria', 'Valor Presente', 'Tipo de Venda'],
    ...investidoresFiltradosCache.map((item) => [
      item.reserva,
      item.data,
      item.situacao,
      item.empreendimento,
      item.bloco || '',
      item.unidade || '',
      item.cliente,
      item.corretor || '',
      item.imobiliaria || '',
      Number(item.valor_presente || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      item.tipo_venda || '',
    ]),
  ];
  const conteudo = '\uFEFF' + linhas.map((linha) => linha.map(escaparCsv).join(';')).join('\r\n');
  const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `investidores_${MES_ATUAL}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function obterSegmentosFunil(funil) {
  const total = funil.reduce((acc, item) => acc + Number(item.quantidade || 0), 0);
  let acumulado = 0;
  return funil
    .filter((item) => Number(item.quantidade || 0) > 0)
    .map((item) => {
      const amplitude = total ? (Number(item.quantidade || 0) / total) * 360 : 0;
      const segmento = {
        label: item.label,
        cor: item.cor,
        quantidade: Number(item.quantidade || 0),
        percentual: Number(item.percentual || 0),
        inicio: acumulado,
        fim: acumulado + amplitude,
      };
      acumulado += amplitude;
      return segmento;
    });
}

function labelParaFiltroSituacao(label) {
  const mapa = {
    Vendida: 'VENDIDA',
    Cancelada: 'CANCELADA',
    'Confecção de Contrato': 'CONFECCAO DE CONTRATO',
    'Envio UAU': 'ENVIO UAU',
    'Nova Reserva': 'NOVA RESERVA',
    'Pendente de Assinatura': 'PENDENTE DE ASSINATURA',
  };
  return mapa[label] || '';
}

function renderizarFunil(funil) {
  const chart = document.getElementById('funil-chart');
  const legend = document.getElementById('funil-legenda');
  const total = funil.reduce((acc, item) => acc + Number(item.quantidade || 0), 0);
  const segmentos = obterSegmentosFunil(funil);
  const itemAtivo = funil.find((item) => item.label === activeSituacaoChart);

  document.getElementById('funil-total').textContent = `${total} investidores`;

  if (!chart || !legend) return;

  if (!total || !segmentos.length) {
    chart.className = 'sales-funnel__chart sales-funnel__chart--empty';
    chart.style.background = '#F6F0ED';
    chart.dataset.segments = '[]';
    chart.innerHTML = '<span class="sales-funnel__center sales-funnel__center--empty">0<small>investidores</small></span>';
  } else {
    const gradiente = segmentos.map((segmento) => `${segmento.cor} ${segmento.inicio}deg ${segmento.fim}deg`).join(', ');
    chart.className = `sales-funnel__chart${activeSituacaoChart ? ' sales-funnel__chart--active' : ''}`;
    chart.style.background = `conic-gradient(${gradiente})`;
    chart.dataset.segments = JSON.stringify(segmentos);
    chart.innerHTML = `
      <span class="sales-funnel__center">
        <strong>${itemAtivo ? itemAtivo.quantidade : total}</strong>
        <small>${itemAtivo ? itemAtivo.label : 'investidores'}</small>
      </span>
    `;
  }

  legend.innerHTML = funil.map((item) => `
    <button class="sales-funnel__item ${activeSituacaoChart === item.label ? 'sales-funnel__item--active' : ''}" type="button" onclick="toggleSituacaoChart(${JSON.stringify(item.label)})">
      <span class="sales-funnel__dot" style="background:${item.cor}"></span>
      <div>
        <strong>${item.label}</strong>
        <p>${item.quantidade} investidores | ${Number(item.percentual || 0).toFixed(1)}%</p>
      </div>
    </button>
  `).join('');
}

function atualizarInsights(financeiro) {
  const meta = Number(financeiro.meta_valor || 0);
  const valorRealizado = Number(financeiro.valor_realizado || 0);
  const vendidas = Number(financeiro.total_vendidas || 0);
  const restante = Math.max(meta - valorRealizado, 0);
  const ticketMedio = vendidas > 0 ? valorRealizado / vendidas : 0;
  const ritmo = meta <= 0
    ? 'Meta pendente'
    : valorRealizado >= meta
      ? 'Meta atingida'
    : vendidas === 0
        ? 'Sem investidores realizados'
        : 'Meta em andamento';

  const restanteEl = document.getElementById('insight-restante');
  const ritmoEl = document.getElementById('insight-ritmo');
  const ticketEl = document.getElementById('insight-ticket');

  if (restanteEl) restanteEl.textContent = fmtMoedaInteira(restante);
  if (ritmoEl) ritmoEl.textContent = ritmo;
  if (ticketEl) ticketEl.textContent = fmtMoedaInteira(ticketMedio);
}

function atualizarFinanceiro(financeiro) {
  const metaEl = document.getElementById('meta-valor');
  const valorEl = document.getElementById('valor-realizado');
  const atingimentoEl = document.getElementById('atingimento-meta');
  const totalVendidasEl = document.getElementById('total-vendidas');
  const pctEl = document.getElementById('pct-valor');
  const txtEl = document.getElementById('txt-valor');
  const barEl = document.getElementById('bar-valor');

  if (metaEl) metaEl.textContent = fmtMoedaInteira(financeiro.meta_valor || 0);
  if (valorEl) valorEl.textContent = fmtMoedaInteira(financeiro.valor_realizado || 0);
  if (atingimentoEl) atingimentoEl.textContent = `${financeiro.percentual_atingimento || 0}%`;
  if (totalVendidasEl) totalVendidasEl.textContent = String(financeiro.total_vendidas || 0);
  if (pctEl) pctEl.textContent = `${financeiro.percentual_atingimento || 0}%`;
  if (txtEl) txtEl.textContent = `${fmtMoedaInteira(financeiro.valor_realizado || 0)} de ${fmtMoedaInteira(financeiro.meta_valor || 0)} realizados`;
  if (barEl) barEl.style.width = `${Math.min(financeiro.percentual_atingimento || 0, 100)}%`;

  atualizarInsights(financeiro);
  renderizarFunil(financeiro.funil || []);
}

function badgeClass(situacao) {
  return `badge--${String(situacao || '').toLowerCase().replaceAll(' ', '-')}`;
}

function renderizarTabela(registros) {
  const tbody = document.getElementById('tbody-investidores');
  const totalRegistros = document.getElementById('total-registros');
  if (totalRegistros) totalRegistros.textContent = `${registros.length} investidores`;
  if (!tbody) return;

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="12" class="td-empty">Nenhum investidor encontrado para os filtros atuais.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => `
    <tr data-id="${r.id}" onclick="abrirInvestidor(${r.id})">
      <td>${r.reserva}</td>
      <td>${r.data}</td>
      <td><span class="badge ${badgeClass(r.situacao)}">${r.situacao}</span></td>
      <td>${r.empreendimento}</td>
      <td>${r.bloco || '—'}</td>
      <td>${r.unidade || '—'}</td>
      <td>${r.cliente}</td>
      <td>${r.corretor || '—'}</td>
      <td>${r.imobiliaria || '—'}</td>
      <td>${r.valor_presente > 0 ? fmtMoeda(r.valor_presente) : '—'}</td>
      <td>${r.tipo_venda || ''}</td>
      <td onclick="event.stopPropagation()"><button class="btn-del" onclick="deletarInvestidor(${r.id}, this)" title="Excluir"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg></button></td>
    </tr>
  `).join('');
}

function calcularFinanceiroFiltrado(registros) {
  const base = {};
  for (const item of INITIAL_FINANCEIRO.funil || []) {
    base[item.label] = { label: item.label, quantidade: 0, percentual: 0, cor: item.cor };
  }

  let totalVendidas = 0;
  let valorRealizado = 0;
  for (const item of registros) {
    const label = situacaoParaLabelGrafico(item.situacao);
    if (!base[label]) continue;
    base[label].quantidade += 1;
    if (normalizarSituacaoLabel(item.situacao) === 'VENDIDA') {
      totalVendidas += 1;
      valorRealizado += Number(item.valor_presente || 0);
    }
  }

  const total = registros.length;
  const funil = Object.values(base).map((item) => ({
    ...item,
    percentual: total ? Number(((item.quantidade / total) * 100).toFixed(1)) : 0,
  }));

  return {
    meta_valor: INITIAL_FINANCEIRO.meta_valor || 0,
    valor_realizado: valorRealizado,
    percentual_atingimento: (INITIAL_FINANCEIRO.meta_valor || 0) > 0
      ? Number(((valorRealizado / INITIAL_FINANCEIRO.meta_valor) * 100).toFixed(1))
      : 0,
    total_vendidas: totalVendidas,
    total_registros: total,
    funil,
  };
}

function aplicarFiltros() {
  const buscaEl = document.getElementById('filtro-busca');
  const situacaoEl = document.getElementById('filtro-situacao');
  const empreendimentoEl = document.getElementById('filtro-empreendimento');

  const termo = buscaEl ? buscaEl.value.trim().toUpperCase() : '';
  const situacaoSelecionada = situacaoEl ? situacaoEl.value.trim().toUpperCase() : '';
  const empreendimentoSelecionado = empreendimentoEl ? empreendimentoEl.value.trim().toUpperCase() : '';

  const filtrados = investidoresCache.filter((item) => {
    const labelGrafico = situacaoParaLabelGrafico(item.situacao);
    const matchChart = !activeSituacaoChart || labelGrafico === activeSituacaoChart;
    const matchSituacao = !situacaoSelecionada || normalizarSituacaoLabel(item.situacao) === situacaoSelecionada;
    const matchEmpreendimento = !empreendimentoSelecionado || String(item.empreendimento || '').toUpperCase() === empreendimentoSelecionado;
    const textoLinha = [
      item.reserva, item.cliente, item.corretor, item.imobiliaria,
      item.unidade, item.bloco, item.empreendimento, item.tipo_venda, item.data,
    ].join(' ').toUpperCase();
    const matchBusca = !termo || textoLinha.includes(termo);
    return matchChart && matchSituacao && matchEmpreendimento && matchBusca;
  });

  investidoresFiltradosCache = filtrados;
  renderizarTabela(filtrados);
  atualizarFinanceiro(calcularFinanceiroFiltrado(filtrados));
}

function toggleSituacaoChart(label) {
  activeSituacaoChart = activeSituacaoChart === label ? '' : label;
  const filtroSituacao = document.getElementById('filtro-situacao');
  if (filtroSituacao) {
    filtroSituacao.value = activeSituacaoChart ? labelParaFiltroSituacao(activeSituacaoChart) : '';
  }
  aplicarFiltros();
}

function handleFunilChartClick(event) {
  const chart = event.currentTarget;
  const segmentos = JSON.parse(chart.dataset.segments || '[]');
  if (!segmentos.length) return;

  const rect = chart.getBoundingClientRect();
  const centerX = rect.width / 2;
  const centerY = rect.height / 2;
  const dx = event.clientX - rect.left - centerX;
  const dy = event.clientY - rect.top - centerY;
  const distancia = Math.sqrt((dx * dx) + (dy * dy));
  const raioExterno = rect.width / 2;
  const raioInterno = rect.width * 0.22;

  if (distancia < raioInterno || distancia > raioExterno) return;

  const angulo = (Math.atan2(dy, dx) * (180 / Math.PI) + 450) % 360;
  const segmento = segmentos.find((item) => angulo >= item.inicio && angulo < item.fim);
  if (segmento) toggleSituacaoChart(segmento.label);
}

function openDeleteModal(id, btnEl) {
  deleteState = { id, btnEl, mode: 'single' };
  const titleEl = document.getElementById('delete-modal-title');
  const textEl = document.getElementById('delete-modal-text');
  const confirmEl = document.getElementById('confirm-delete-btn');
  if (titleEl) titleEl.textContent = 'Excluir investidor';
  if (textEl) textEl.textContent = 'Deseja excluir este investidor? Essa ação não poderá ser desfeita.';
  if (confirmEl) confirmEl.textContent = 'Excluir';
  document.getElementById('modal-delete')?.removeAttribute('hidden');
}

function closeDeleteModal() {
  deleteState = { id: null, btnEl: null, mode: 'single' };
  document.getElementById('modal-delete')?.setAttribute('hidden', '');
}

function openDeleteAllModal() {
  deleteState = { id: null, btnEl: document.getElementById('btn-delete-all'), mode: 'all' };
  const titleEl = document.getElementById('delete-modal-title');
  const textEl = document.getElementById('delete-modal-text');
  const confirmEl = document.getElementById('confirm-delete-btn');
  if (titleEl) titleEl.textContent = 'Excluir todos os investidores';
  if (textEl) textEl.textContent = 'Deseja realmente excluir todos os registros de investidores? Essa ação apagará todas as informações e não poderá ser desfeita.';
  if (confirmEl) confirmEl.textContent = 'Excluir tudo';
  document.getElementById('modal-delete')?.removeAttribute('hidden');
}

function abrirInvestidor(id) {
  const investidor = investidoresCache.find((item) => item.id === id);
  if (!investidor) return;
  document.getElementById('ii-id').textContent = `#${investidor.id}`;
  document.getElementById('ii-reserva').value = investidor.reserva;
  document.getElementById('ii-data').value = investidor.data_iso;
  preencherSelect(document.getElementById('ii-situacao'), SITUACOES, investidor.situacao);
  preencherSelect(document.getElementById('ii-tipo-venda'), TIPOS_VENDA, investidor.tipo_venda);
  preencherSelect(document.getElementById('ii-empreendimento'), EMPREENDIMENTOS, investidor.empreendimento);
  document.getElementById('ii-bloco').value = investidor.bloco || '';
  document.getElementById('ii-unidade').value = investidor.unidade || '';
  document.getElementById('ii-cliente').value = investidor.cliente;
  document.getElementById('ii-corretor').value = investidor.corretor || '';
  document.getElementById('ii-imobiliaria').value = investidor.imobiliaria || '';
  document.getElementById('ii-valor').value = investidor.valor_presente || 0;
  document.getElementById('form-investidor').dataset.id = String(investidor.id);
  document.getElementById('modal-investidor').removeAttribute('hidden');
}

function closeInvestidor() {
  document.getElementById('modal-investidor')?.setAttribute('hidden', '');
}

function coletarForm(form) {
  const dados = {};
  new FormData(form).forEach((v, k) => { dados[k] = String(v).trim(); });
  return dados;
}

function validarCamposBasicos(dados) {
  return dados.reserva && dados.data && dados.situacao && dados.tipo_venda && dados.empreendimento && dados.cliente;
}

function normalizarLinhaBulk(colunas) {
  return {
    reserva: (colunas[0] || '').trim(),
    data: (colunas[1] || '').trim(),
    situacao: (colunas[2] || '').trim(),
    empreendimento: (colunas[3] || '').trim(),
    bloco: (colunas[4] || '').trim(),
    unidade: (colunas[5] || '').trim(),
    cliente: (colunas[6] || '').trim(),
    corretor: (colunas[7] || '').trim(),
    imobiliaria: (colunas[8] || '').trim(),
    valor_presente: (colunas[9] || '').trim(),
    tipo_venda: (colunas[10] || '').trim(),
  };
}

function parseBulkText(texto) {
  const linhas = String(texto || '').split(/\r?\n/).map((linha) => linha.trim()).filter(Boolean);
  if (!linhas.length) return [];
  let dados = linhas.map((linha) => normalizarLinhaBulk(linha.split('\t')));
  const primeira = Object.values(dados[0]).join(' ').toLowerCase();
  if (primeira.includes('reserva') && primeira.includes('empreendimento')) {
    dados = dados.slice(1);
  }
  return dados.filter((linha) => Object.values(linha).some(Boolean));
}

async function recarregarDados() {
  try {
    const resp = await fetch(`/investidores/registros?mes=${MES_ATUAL}&semana=${SEMANA_ATUAL}`);
    const json = await resp.json();
    investidoresCache = json.registros || [];
    Object.assign(INITIAL_FINANCEIRO, json.financeiro || {});
    aplicarFiltros();
  } catch {
    showToast('Não foi possível atualizar os dados.', 'error');
  }
}

async function salvarInvestidorEditado() {
  const id = document.getElementById('form-investidor').dataset.id;
  const btn = document.getElementById('btn-salvar-modal');
  const dados = {
    reserva: document.getElementById('ii-reserva').value.trim(),
    data: document.getElementById('ii-data').value.trim(),
    situacao: document.getElementById('ii-situacao').value.trim(),
    tipo_venda: document.getElementById('ii-tipo-venda').value.trim(),
    empreendimento: document.getElementById('ii-empreendimento').value.trim(),
    bloco: document.getElementById('ii-bloco').value.trim(),
    unidade: document.getElementById('ii-unidade').value.trim(),
    cliente: document.getElementById('ii-cliente').value.trim(),
    corretor: document.getElementById('ii-corretor').value.trim(),
    imobiliaria: document.getElementById('ii-imobiliaria').value.trim(),
    valor_presente: document.getElementById('ii-valor').value,
  };
  if (!validarCamposBasicos(dados)) {
    showToast('Preencha os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const resp = await fetch(`/investidores/registro/${id}`, {
      method: 'PUT',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      closeInvestidor();
      showToast('Investidor atualizado com sucesso!');
      recarregarDados();
    } else {
      showToast(json.erro || 'Erro ao atualizar investidor.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deletarInvestidor(id, btnEl) {
  openDeleteModal(id, btnEl);
}

async function confirmarExclusaoInvestidor() {
  const { id, btnEl, mode } = deleteState;
  if (!btnEl) return;
  closeDeleteModal();
  btnEl.disabled = true;
  try {
    const url = mode === 'all' ? '/investidores/registros' : `/investidores/registro/${id}`;
    const resp = await fetch(url, { method: 'DELETE', headers: csrfHeaders() });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast(mode === 'all' ? 'Todos os registros de investidores foram excluídos.' : 'Investidor excluido.');
      recarregarDados();
    } else {
      showToast(json.erro || 'Erro ao excluir.', 'error');
      btnEl.disabled = false;
    }
  } catch {
    showToast('Falha de conexão.', 'error');
    btnEl.disabled = false;
  } finally {
    btnEl.disabled = false;
  }
}

function conectarSocket() {
  const socket = io({ transports: ['polling'] });
  socket.on('connect', () => {
    const badge = document.getElementById('live-badge');
    if (badge) badge.style.opacity = '1';
  });
  socket.on('disconnect', () => {
    const badge = document.getElementById('live-badge');
    if (badge) badge.style.opacity = '.4';
  });
  socket.on('investidores_atualizados', (payload) => {
    if (payload.mes !== MES_ATUAL) return;
    investidoresCache = payload.registros || [];
    Object.assign(INITIAL_FINANCEIRO, payload.financeiro || {});
    aplicarFiltros();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  investidoresCache = Array.isArray(INITIAL_REGISTROS) ? INITIAL_REGISTROS : [];

  const buscaEl = document.getElementById('filtro-busca');
  const situacaoEl = document.getElementById('filtro-situacao');
  const empreendimentoEl = document.getElementById('filtro-empreendimento');
  const exportarEl = document.getElementById('btn-exportar-grid');
  const limparEl = document.getElementById('btn-limpar-filtros');
  const deleteAllEl = document.getElementById('btn-delete-all');
  const confirmarDeleteEl = document.getElementById('confirm-delete-btn');
  const chartEl = document.getElementById('funil-chart');
  const formCadastro = document.getElementById('form-cadastro-investidor');
  const previewBulkEl = document.getElementById('btn-preview-bulk');
  const saveBulkEl = document.getElementById('btn-save-bulk');
  const toggleBtn = document.getElementById('toggle-form');
  const formWrapper = document.getElementById('form-wrapper');

  window.toggleMesInvestidores = function toggleMesInvestidores(mesId) {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    const collapsed = body.classList.toggle('week-month__body--collapsed');
    arrow.classList.toggle('week-month__arrow--collapsed', collapsed);
  };

  if (buscaEl) buscaEl.addEventListener('input', aplicarFiltros);
  if (situacaoEl) situacaoEl.addEventListener('change', aplicarFiltros);
  if (empreendimentoEl) empreendimentoEl.addEventListener('change', aplicarFiltros);
  if (exportarEl) exportarEl.addEventListener('click', baixarCsvAtual);
  if (limparEl) {
    limparEl.addEventListener('click', () => {
      activeSituacaoChart = '';
      if (buscaEl) buscaEl.value = '';
      if (situacaoEl) situacaoEl.value = '';
      if (empreendimentoEl) empreendimentoEl.value = '';
      aplicarFiltros();
    });
  }
  if (deleteAllEl) deleteAllEl.addEventListener('click', openDeleteAllModal);
  if (confirmarDeleteEl) confirmarDeleteEl.addEventListener('click', confirmarExclusaoInvestidor);
  if (chartEl) chartEl.addEventListener('click', handleFunilChartClick);

  if (toggleBtn && formWrapper) {
    let formVisible = false;
    formWrapper.style.display = 'none';
    toggleBtn.textContent = '▼ Expandir';
    toggleBtn.addEventListener('click', () => {
      formVisible = !formVisible;
      formWrapper.style.display = formVisible ? '' : 'none';
      toggleBtn.textContent = formVisible ? '▲ Recolher' : '▼ Expandir';
    });
  }

  if (formCadastro) {
    formCadastro.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn-salvar-investidor');
      const dados = coletarForm(formCadastro);
      if (!validarCamposBasicos(dados)) {
        showToast('Preencha os campos obrigatórios.', 'error');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Salvando...';
      try {
        const resp = await fetch('/investidores/cadastrar', {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(dados),
        });
        const json = await resp.json();
        if (resp.ok && json.sucesso) {
          formCadastro.reset();
          showToast(json.ignorado ? (json.erro || 'Investidor ignorado.') : 'Investidor salvo com sucesso!');
          recarregarDados();
        } else {
          showToast(json.erro || 'Erro ao salvar investidor.', 'error');
        }
      } catch {
        showToast('Falha de conexão.', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Salvar Investidor';
      }
    });
  }

  if (previewBulkEl) {
    previewBulkEl.addEventListener('click', () => {
      const linhas = parseBulkText(document.getElementById('bulk-paste').value);
      const feedback = document.getElementById('bulk-feedback');
      if (!feedback) return;
      if (!linhas.length) {
        feedback.textContent = 'Nenhuma linha válida encontrada.';
        return;
      }
      const invalidas = linhas.filter((linha) => !validarCamposBasicos(linha));
      feedback.textContent = invalidas.length
        ? `${linhas.length} linhas detectadas, ${invalidas.length} com campos obrigatórios faltando.`
        : `${linhas.length} linhas prontas para importação.`;
    });
  }

  if (saveBulkEl) {
    saveBulkEl.addEventListener('click', async () => {
      const linhas = parseBulkText(document.getElementById('bulk-paste').value);
      const feedback = document.getElementById('bulk-feedback');
      if (!linhas.length) {
        showToast('Cole ao menos uma linha para importar.', 'error');
        return;
      }
      if (linhas.some((linha) => !validarCamposBasicos(linha))) {
        showToast('Há linhas com campos obrigatórios faltando.', 'error');
        return;
      }

      try {
        const resp = await fetch('/investidores/bulk-cadastrar', {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ linhas }),
        });
        const json = await resp.json();
        if (resp.ok && json.sucesso) {
          document.getElementById('bulk-paste').value = '';
          if (feedback) {
            feedback.textContent = `${json.quantidade} linhas importadas com sucesso.${json.ignoradas ? ` ${json.ignoradas} linhas ignoradas por empreendimento desconsiderado.` : ''}`;
          }
          showToast('Importação concluída!');
          recarregarDados();
        } else {
          showToast(json.erro || 'Erro na importação.', 'error');
          if (feedback) feedback.textContent = json.erro || 'Erro na importação.';
        }
      } catch {
        showToast('Falha de conexão.', 'error');
      }
    });
  }

  MESES_INVESTIDORES_TOPBAR.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    body.classList.add('week-month__body--collapsed');
    arrow.classList.add('week-month__arrow--collapsed');
  });

  aplicarFiltros();
  conectarSocket();
});
