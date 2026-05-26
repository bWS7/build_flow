'use strict';

let vendasCache = [];
let vendasFiltradasCache = [];
let acoesCache = [];
let activeSituacaoChart = '';
let deleteState = { id: null, btnEl: null, mode: 'single' };
const MESES_VENDAS_TOPBAR = ['abril', 'maio', 'junho'];

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

function calcularPctPlanejadoRealizado(realizadoMetrica, metaMetrica, realizadoAcoes, metaAcoes) {
  const componentes = [];
  if (Number(metaMetrica || 0) > 0) componentes.push(Number(realizadoMetrica || 0) / Number(metaMetrica || 0));
  if (Number(metaAcoes || 0) > 0) componentes.push(Number(realizadoAcoes || 0) / Number(metaAcoes || 0));
  if (!componentes.length) return 100;
  return Number((Math.min((componentes.reduce((acc, item) => acc + item, 0) / componentes.length) * 100, 100)).toFixed(1));
}

function resumoPlanejadoRealizado(financeiro) {
  return `${financeiro.total_vendidas || 0} de ${financeiro.meta_quantidade || 0} vendas • ${financeiro.acoes_realizadas || 0} de ${financeiro.meta_acoes || 0} acoes`;
}

function formatarCampoMoeda(valor) {
  const digitos = String(valor || '').replace(/\D/g, '');
  if (!digitos) return '';
  const numero = Number(digitos) / 100;
  return numero.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function aplicarMascaraMoeda(input) {
  if (!input) return;
  input.value = formatarCampoMoeda(input.value);
}

function renderizarBotaoExcluirRegistro(id) {
  if (!PODE_EDITAR_SEMANA) return '';
  return `<button class="btn-del" onclick="deletarVenda(${id}, this)" title="Excluir registro"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg></button>`;
}

function aplicarBloqueioEdicao() {
  if (PODE_EDITAR_SEMANA) return;
  document.querySelectorAll('#form-cadastro-venda input, #form-cadastro-venda select, #form-cadastro-venda textarea, #action-form-wrapper input, #action-form-wrapper select, #action-form-wrapper textarea').forEach((el) => {
    el.disabled = true;
  });
  document.querySelectorAll('#form-cadastro-venda button, #action-form-wrapper button').forEach((el) => {
    el.disabled = true;
  });
  document.querySelectorAll('#form-venda input, #form-venda select, #form-venda textarea, #form-venda button').forEach((el) => {
    el.disabled = true;
  });
  const toggleBtn = document.getElementById('toggle-form');
  const toggleActionBtn = document.getElementById('toggle-action-form');
  const deleteAllEl = document.getElementById('btn-delete-all');
  if (toggleBtn) toggleBtn.disabled = true;
  if (toggleActionBtn) toggleActionBtn.disabled = true;
  if (deleteAllEl) deleteAllEl.disabled = true;
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
    ...vendasFiltradasCache.map((item) => [
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
  link.download = `vendas_${MES_ATUAL}.csv`;
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

  document.getElementById('funil-total').textContent = `${total} reservas`;

  if (!chart || !legend) return;

  if (!total || !segmentos.length) {
    chart.className = 'sales-funnel__chart sales-funnel__chart--empty';
    chart.style.background = '#F6F0ED';
    chart.dataset.segments = '[]';
    chart.innerHTML = '<span class="sales-funnel__center sales-funnel__center--empty">0<small>reservas</small></span>';
  } else {
    const gradiente = segmentos.map((segmento) => `${segmento.cor} ${segmento.inicio}deg ${segmento.fim}deg`).join(', ');
    chart.className = `sales-funnel__chart${activeSituacaoChart ? ' sales-funnel__chart--active' : ''}`;
    chart.style.background = `conic-gradient(${gradiente})`;
    chart.dataset.segments = JSON.stringify(segmentos);
    chart.innerHTML = `
      <span class="sales-funnel__center">
        <strong>${itemAtivo ? itemAtivo.quantidade : total}</strong>
        <small>${itemAtivo ? itemAtivo.label : 'reservas'}</small>
      </span>
    `;
  }

  legend.innerHTML = funil.map((item) => `
    <button class="sales-funnel__item ${activeSituacaoChart === item.label ? 'sales-funnel__item--active' : ''}" type="button" onclick="toggleSituacaoChart(${JSON.stringify(item.label)})">
      <span class="sales-funnel__dot" style="background:${item.cor}"></span>
      <div>
        <strong>${item.label}</strong>
        <p>${item.quantidade} reservas | ${Number(item.percentual || 0).toFixed(1)}%</p>
      </div>
    </button>
  `).join('');
}

function atualizarFinanceiro(financeiro) {
  const metaBaseEl = document.getElementById('meta-base-total');
  const metaEl = document.getElementById('meta-quantidade');
  const atingimentoEl = document.getElementById('atingimento-meta');
  const totalVendidasEl = document.getElementById('total-vendidas');
  const metaAcoesEl = document.getElementById('meta-acoes');
  const acoesRealizadasEl = document.getElementById('acoes-realizadas');
  const resumoBarEl = document.getElementById('bar-resumo-geral');
  const resumoTxtEl = document.getElementById('txt-resumo-geral');
  const pctEl = document.getElementById('pct-valor');
  const txtEl = document.getElementById('txt-valor');
  const barEl = document.getElementById('bar-valor');
  const pctAcoesEl = document.getElementById('pct-acoes');
  const txtAcoesEl = document.getElementById('txt-acoes');
  const barAcoesEl = document.getElementById('bar-acoes');
  if (metaBaseEl) metaBaseEl.textContent = String(financeiro.meta_base_total || 0);
  if (metaEl) metaEl.textContent = String(financeiro.meta_quantidade || 0);
  if (atingimentoEl) atingimentoEl.textContent = `${financeiro.percentual_atingimento || 0}%`;
  if (totalVendidasEl) totalVendidasEl.textContent = String(financeiro.total_vendidas || 0);
  if (metaAcoesEl) metaAcoesEl.textContent = String(financeiro.meta_acoes || 0);
  if (acoesRealizadasEl) acoesRealizadasEl.textContent = String(financeiro.acoes_realizadas || 0);
  if (resumoBarEl) resumoBarEl.style.width = `${Math.min(financeiro.percentual_planejado_realizado || 0, 100)}%`;
  if (resumoTxtEl) resumoTxtEl.textContent = resumoPlanejadoRealizado(financeiro);
  if (pctEl) pctEl.textContent = `${financeiro.percentual_atingimento || 0}%`;
  if (txtEl) txtEl.textContent = `${financeiro.total_vendidas || 0} de ${financeiro.meta_quantidade || 0} unidades vendidas`;
  if (barEl) barEl.style.width = `${Math.min(financeiro.percentual_atingimento || 0, 100)}%`;
  if (pctAcoesEl) pctAcoesEl.textContent = `${financeiro.percentual_acoes || 0}%`;
  if (txtAcoesEl) txtAcoesEl.textContent = `${financeiro.acoes_realizadas || 0} de ${financeiro.meta_acoes || 0} ações realizadas`;
  if (barAcoesEl) barAcoesEl.style.width = `${Math.min(financeiro.percentual_acoes || 0, 100)}%`;
  renderizarFunil(financeiro.funil || []);
}

function renderizarOpcoesAcao() {
  const select = document.getElementById('acao-venda-id');
  const feedback = document.getElementById('acao-feedback');
  if (!select) {
    if (feedback) {
      feedback.textContent = vendasCache.length
        ? 'A acao sera registrada normalmente nesta semana.'
        : 'Voce pode registrar uma acao diretamente, mesmo sem venda anterior.';
    }
    return;
  }

  const registros = [...vendasCache]
    .sort((a, b) => String(a.reserva || '').localeCompare(String(b.reserva || ''), 'pt-BR'));

  select.innerHTML = '<option value="">Selecione...</option>' + registros.map((item) => (
    `<option value="${item.id}">${item.reserva} - ${item.cliente}</option>`
  )).join('');

  if (feedback) {
    feedback.textContent = registros.length
      ? 'Selecione uma venda do período para registrar a ação.'
      : 'Cadastre uma venda primeiro para registrar ações.';
  }
}

function badgeClass(situacao) {
  return `badge--${String(situacao || '').toLowerCase().replaceAll(' ', '-')}`;
}

function renderizarTabela(registros) {
  const tbody = document.getElementById('tbody-vendas');
  const totalRegistros = document.getElementById('total-registros');
  if (totalRegistros) totalRegistros.textContent = `${registros.length} reservas`;
  if (!tbody) return;

  if (!registros.length) {
    tbody.innerHTML = '<tr id="empty-row"><td colspan="12" class="td-empty">Nenhuma reserva encontrada para os filtros atuais.</td></tr>';
    return;
  }

  tbody.innerHTML = registros.map((r) => `
    <tr data-id="${r.id}" onclick="abrirVenda(${r.id})">
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
      <td onclick="event.stopPropagation()">${renderizarBotaoExcluirRegistro(r.id)}</td>
    </tr>
  `).join('');
}

function renderizarTabelaAcoes(acoes) {
  const tbody = document.getElementById('tbody-acoes-vendas');
  const counter = document.getElementById('total-acoes');
  if (!tbody || !counter) return;
  acoesCache = Array.isArray(acoes) ? acoes : [];
  counter.textContent = `${acoesCache.length} acoes`;

  if (!acoesCache.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="td-empty">Nenhuma acao registrada neste periodo.</td></tr>';
    return;
  }

  tbody.innerHTML = acoesCache.map((r) => `
    <tr>
      <td class="td-id">${r.id}</td>
      <td>${r.registro_id ? ('Registro #' + r.registro_id) : 'Acao direta'}</td>
      <td>${r.descricao || '-'}</td>
      <td>${r.responsavel || '-'}</td>
      <td class="td-data">${(r.data || '').trim() || '-'}</td>
      <td>${PODE_EDITAR_SEMANA ? `<button class="btn-del" onclick="deletarAcao(${r.id}, this)" title="Excluir acao"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg></button>` : ''}</td>
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
    meta_quantidade: INITIAL_FINANCEIRO.meta_quantidade || 0,
    meta_acoes: INITIAL_FINANCEIRO.meta_acoes || 0,
    meta_base_total: INITIAL_FINANCEIRO.meta_base_total || 0,
    valor_realizado: valorRealizado,
    percentual_atingimento: (INITIAL_FINANCEIRO.meta_quantidade || 0) > 0
      ? Number(((totalVendidas / INITIAL_FINANCEIRO.meta_quantidade) * 100).toFixed(1))
      : 0,
    acoes_realizadas: acoesCache.length,
    percentual_acoes: (INITIAL_FINANCEIRO.meta_acoes || 0) > 0
      ? Number(((acoesCache.length / INITIAL_FINANCEIRO.meta_acoes) * 100).toFixed(1))
      : 0,
    percentual_planejado_realizado: calcularPctPlanejadoRealizado(
      totalVendidas,
      INITIAL_FINANCEIRO.meta_quantidade || 0,
      acoesCache.length,
      INITIAL_FINANCEIRO.meta_acoes || 0,
    ),
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

  const filtrados = vendasCache.filter((item) => {
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

  vendasFiltradasCache = filtrados;
  renderizarTabela(filtrados);
  renderizarTabelaAcoes(acoesCache);
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
  if (titleEl) titleEl.textContent = 'Excluir registro';
  if (textEl) textEl.textContent = 'Deseja excluir esta venda? Essa ação não poderá ser desfeita.';
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
  if (titleEl) titleEl.textContent = 'Excluir registros da semana';
  if (textEl) textEl.textContent = 'Deseja realmente excluir todos os registros de vendas desta semana? Essa acao nao podera ser desfeita.';
  if (confirmEl) confirmEl.textContent = 'Excluir semana';
  document.getElementById('modal-delete')?.removeAttribute('hidden');
}

function abrirVenda(id) {
  const venda = vendasCache.find((item) => item.id === id);
  if (!venda) return;
  document.getElementById('vi-id').textContent = `#${venda.id}`;
  document.getElementById('vi-reserva').value = venda.reserva;
  document.getElementById('vi-data').value = venda.data_iso;
  preencherSelect(document.getElementById('vi-situacao'), SITUACOES, venda.situacao);
  preencherSelect(document.getElementById('vi-empreendimento'), EMPREENDIMENTOS, venda.empreendimento);
  preencherSelect(document.getElementById('vi-tipo-venda'), TIPOS_VENDA, venda.tipo_venda);
  document.getElementById('vi-bloco').value = venda.bloco || '';
  document.getElementById('vi-unidade').value = venda.unidade || '';
  document.getElementById('vi-cliente').value = venda.cliente;
  document.getElementById('vi-corretor').value = venda.corretor || '';
  document.getElementById('vi-imobiliaria').value = venda.imobiliaria || '';
  document.getElementById('vi-valor').value = formatarCampoMoeda(venda.valor_presente || 0);
  const acaoEl = document.getElementById('vi-acao');
  if (acaoEl) acaoEl.value = venda.acao_realizada || '';
  document.getElementById('form-venda').dataset.id = String(venda.id);
  document.getElementById('modal-venda').removeAttribute('hidden');
}

function closeVenda() {
  document.getElementById('modal-venda')?.setAttribute('hidden', '');
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
  const valores = colunas.map((coluna) => (coluna || '').trim());

  // Layout exportado do banco:
  // id | reserva | data | situacao | empreendimento | bloco | unidade | cliente | corretor | imobiliaria | valor | criado_por | criado_em | tipo_venda
  if (valores.length >= 14) {
    return {
      reserva: valores[1] || '',
      data: valores[2] || '',
      situacao: valores[3] || '',
      empreendimento: valores[4] || '',
      bloco: valores[5] || '',
      unidade: valores[6] || '',
      cliente: valores[7] || '',
      corretor: valores[8] || '',
      imobiliaria: valores[9] || '',
      valor_presente: valores[10] || '',
      tipo_venda: valores[13] || '',
    };
  }

  // Layout com id no inicio e tipo_venda no fim.
  if (valores.length >= 12) {
    return {
      reserva: valores[1] || '',
      data: valores[2] || '',
      situacao: valores[3] || '',
      empreendimento: valores[4] || '',
      bloco: valores[5] || '',
      unidade: valores[6] || '',
      cliente: valores[7] || '',
      corretor: valores[8] || '',
      imobiliaria: valores[9] || '',
      valor_presente: valores[10] || '',
      tipo_venda: valores[11] || '',
    };
  }

  return {
    reserva: valores[0] || '',
    data: valores[1] || '',
    situacao: valores[2] || '',
    empreendimento: valores[3] || '',
    bloco: valores[4] || '',
    unidade: valores[5] || '',
    cliente: valores[6] || '',
    corretor: valores[7] || '',
    imobiliaria: valores[8] || '',
    valor_presente: valores[9] || '',
    tipo_venda: valores[10] || '',
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
    const params = new URLSearchParams({ mes: MES_ATUAL });
    if (SEMANA_ATUAL) params.set('semana', SEMANA_ATUAL);
    const resp = await fetch(`/vendas/registros?${params.toString()}`);
    const json = await resp.json();
    vendasCache = json.registros || [];
    acoesCache = json.acoes || [];
    Object.assign(INITIAL_FINANCEIRO, json.financeiro || {});
    aplicarFiltros();
    renderizarOpcoesAcao();
  } catch {
    showToast('Não foi possível atualizar os dados.', 'error');
  }
}

async function salvarAcaoRealizada() {
  const vendaIdElFallback = document.getElementById('acao-venda-id');
  if (!vendaIdElFallback) {
    if (!PODE_EDITAR_SEMANA) {
      showToast('Esta semana esta bloqueada para edicao.', 'error');
      return;
    }
    const descricaoDiretaEl = document.getElementById('acao-descricao');
    const feedbackDiretoEl = document.getElementById('acao-feedback');
    const btnDiretoEl = document.getElementById('btn-salvar-acao');
    if (!descricaoDiretaEl || !btnDiretoEl) return;
    const acaoDireta = descricaoDiretaEl.value.trim();
    if (!acaoDireta) {
      showToast('Descreva a acao realizada.', 'error');
      return;
    }
    btnDiretoEl.disabled = true;
    try {
      const resp = await fetch('/vendas/acao', {
        method: 'POST',
        headers: csrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ mes: MES_ATUAL, semana: SEMANA_ATUAL, acao_realizada: acaoDireta }),
      });
      const json = await resp.json();
      if (resp.ok && json.sucesso) {
        descricaoDiretaEl.value = '';
        if (feedbackDiretoEl) feedbackDiretoEl.textContent = 'Acao registrada com sucesso.';
        showToast('Acao registrada com sucesso!');
        recarregarDados();
      } else {
        showToast(json.erro || 'Erro ao salvar acao.', 'error');
      }
    } catch {
      showToast('Falha de conexao.', 'error');
    } finally {
      btnDiretoEl.disabled = false;
    }
    return;
  }
  if (!PODE_EDITAR_SEMANA) {
    showToast('Esta semana está bloqueada para edição.', 'error');
    return;
  }
  const vendaIdEl = document.getElementById('acao-venda-id');
  const descricaoEl = document.getElementById('acao-descricao');
  const feedbackEl = document.getElementById('acao-feedback');
  const btnSalvarEl = document.getElementById('btn-salvar-acao');
  if (!vendaIdEl || !descricaoEl || !btnSalvarEl) return;

  const vendaId = vendaIdEl.value.trim();
  const acaoRealizada = descricaoEl.value.trim();
  if (!vendaId) {
    showToast('Selecione uma venda para registrar a ação.', 'error');
    return;
  }
  if (!acaoRealizada) {
    showToast('Descreva a ação realizada.', 'error');
    return;
  }

  btnSalvarEl.disabled = true;
  try {
    const resp = await fetch('/vendas/acao', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ venda_id: vendaId, mes: MES_ATUAL, semana: SEMANA_ATUAL, acao_realizada: acaoRealizada }),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      descricaoEl.value = '';
      if (feedbackEl) feedbackEl.textContent = 'Ação registrada com sucesso.';
      showToast('Ação registrada com sucesso!');
      recarregarDados();
    } else {
      showToast(json.erro || 'Erro ao salvar ação.', 'error');
      if (feedbackEl) feedbackEl.textContent = json.erro || 'Erro ao salvar ação.';
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  } finally {
    btnSalvarEl.disabled = false;
  }
}

async function salvarVendaEditada() {
  if (!PODE_EDITAR_SEMANA) {
    showToast('Esta semana está bloqueada para edição.', 'error');
    return;
  }
  const id = document.getElementById('form-venda').dataset.id;
  const btn = document.getElementById('btn-salvar-modal');
  const dados = {
    reserva: document.getElementById('vi-reserva').value.trim(),
    data: document.getElementById('vi-data').value.trim(),
    mes: MES_ATUAL,
    semana: SEMANA_ATUAL,
    situacao: document.getElementById('vi-situacao').value.trim(),
    empreendimento: document.getElementById('vi-empreendimento').value.trim(),
    tipo_venda: document.getElementById('vi-tipo-venda').value.trim(),
    bloco: document.getElementById('vi-bloco').value.trim(),
    unidade: document.getElementById('vi-unidade').value.trim(),
    cliente: document.getElementById('vi-cliente').value.trim(),
    corretor: document.getElementById('vi-corretor').value.trim(),
    imobiliaria: document.getElementById('vi-imobiliaria').value.trim(),
    valor_presente: document.getElementById('vi-valor').value,
    acao_realizada: document.getElementById('vi-acao')?.value.trim() || '',
  };
  if (!validarCamposBasicos(dados)) {
    showToast('Preencha os campos obrigatórios.', 'error');
    return;
  }

  btn.disabled = true;
  try {
    const resp = await fetch(`/vendas/registro/${id}`, {
      method: 'PUT',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(dados),
    });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      closeVenda();
      showToast('Venda atualizada com sucesso!');
      recarregarDados();
    } else {
      showToast(json.erro || 'Erro ao atualizar venda.', 'error');
    }
  } catch {
    showToast('Falha de conexão.', 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deletarVenda(id, btnEl) {
  if (!PODE_EDITAR_SEMANA) {
    showToast('Esta semana está bloqueada para edição.', 'error');
    return;
  }
  openDeleteModal(id, btnEl);
}

async function confirmarExclusaoVenda() {
  const { id, btnEl, mode } = deleteState;
  if (!btnEl) return;
  closeDeleteModal();
  btnEl.disabled = true;
  try {
    const params = new URLSearchParams({ mes: MES_ATUAL, semana: SEMANA_ATUAL });
    const url = mode === 'all' ? `/vendas/registros?${params.toString()}` : `/vendas/registro/${id}`;
    const resp = await fetch(url, { method: 'DELETE', headers: csrfHeaders() });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast(mode === 'all' ? `${json.quantidade || 0} registros da semana foram excluidos.` : 'Venda excluida.');
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

async function deletarAcao(id, btnEl) {
  if (!PODE_EDITAR_SEMANA) {
    showToast('Esta semana esta bloqueada para edicao.', 'error');
    return;
  }
  btnEl.disabled = true;
  try {
    const resp = await fetch(`/vendas/acao/${id}`, { method: 'DELETE', headers: csrfHeaders() });
    const json = await resp.json();
    if (resp.ok && json.sucesso) {
      showToast('Acao excluida.');
      acoesCache = acoesCache.filter((acao) => acao.id !== id);
      renderizarTabelaAcoes(acoesCache);
      recarregarDados();
    } else {
      showToast(json.erro || 'Erro ao excluir acao.', 'error');
      btnEl.disabled = false;
    }
  } catch {
    showToast('Falha de conexao.', 'error');
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
  socket.on('vendas_atualizadas', (payload) => {
    if (MES_ATUAL !== 'resumo_trimestral' && payload.mes !== MES_ATUAL) return;
    recarregarDados();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  vendasCache = Array.isArray(INITIAL_REGISTROS) ? INITIAL_REGISTROS : [];

  const buscaEl = document.getElementById('filtro-busca');
  const situacaoEl = document.getElementById('filtro-situacao');
  const empreendimentoEl = document.getElementById('filtro-empreendimento');
  const exportarEl = document.getElementById('btn-exportar-grid');
  const limparEl = document.getElementById('btn-limpar-filtros');
  const deleteAllEl = document.getElementById('btn-delete-all');
  const confirmarDeleteEl = document.getElementById('confirm-delete-btn');
  const chartEl = document.getElementById('funil-chart');
  const formCadastro = document.getElementById('form-cadastro-venda');
  const previewBulkEl = document.getElementById('btn-preview-bulk');
  const saveBulkEl = document.getElementById('btn-save-bulk');
  const saveAcaoEl = document.getElementById('btn-salvar-acao');
  const limparAcaoEl = document.getElementById('btn-limpar-acao');
  const toggleBtn = document.getElementById('toggle-form');
  const toggleActionBtn = document.getElementById('toggle-action-form');
  const formWrapper = document.getElementById('form-wrapper');
  const actionFormWrapper = document.getElementById('action-form-wrapper');

  document.querySelectorAll('[data-money-field="true"]').forEach((input) => {
    input.addEventListener('input', () => aplicarMascaraMoeda(input));
    if (input.value) aplicarMascaraMoeda(input);
  });

  window.toggleMesVendas = function toggleMesVendas(mesId) {
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
  if (confirmarDeleteEl) confirmarDeleteEl.addEventListener('click', confirmarExclusaoVenda);
  if (chartEl) chartEl.addEventListener('click', handleFunilChartClick);
  if (saveAcaoEl) saveAcaoEl.addEventListener('click', salvarAcaoRealizada);
  if (limparAcaoEl) {
    limparAcaoEl.addEventListener('click', () => {
      const descricaoEl = document.getElementById('acao-descricao');
      const vendaIdEl = document.getElementById('acao-venda-id');
      const feedbackEl = document.getElementById('acao-feedback');
      if (descricaoEl) descricaoEl.value = '';
      if (vendaIdEl) vendaIdEl.value = '';
      if (feedbackEl) feedbackEl.textContent = 'Selecione uma venda do período para registrar a ação.';
    });
  }

  acoesCache = Array.isArray(INITIAL_ACOES) ? INITIAL_ACOES : [];
  renderizarTabelaAcoes(acoesCache);

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

  if (toggleBtn && formWrapper) {
    const syncMainToggleLabel = () => {
      const aberto = formWrapper.style.display !== 'none';
      toggleBtn.textContent = aberto ? '- Recolher' : '+ Expandir';
    };
    syncMainToggleLabel();
    toggleBtn.addEventListener('click', () => {
      requestAnimationFrame(syncMainToggleLabel);
    });
  }

  if (toggleActionBtn && actionFormWrapper) {
    let actionVisible = false;
    actionFormWrapper.style.display = 'none';
    toggleActionBtn.textContent = '+ Expandir';
    toggleActionBtn.addEventListener('click', () => {
      actionVisible = !actionVisible;
      actionFormWrapper.style.display = actionVisible ? '' : 'none';
      toggleActionBtn.textContent = actionVisible ? '- Recolher' : '+ Expandir';
    });
  }

  if (formCadastro) {
    formCadastro.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!PODE_EDITAR_SEMANA) {
        showToast('Esta semana está bloqueada para edição.', 'error');
        return;
      }
      const btn = document.getElementById('btn-salvar-venda');
      const dados = coletarForm(formCadastro);
      dados.mes = MES_ATUAL;
      dados.semana = SEMANA_ATUAL;
      if (!validarCamposBasicos(dados)) {
        showToast('Preencha os campos obrigatórios.', 'error');
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Salvando...';
      try {
        const resp = await fetch('/vendas/cadastrar', {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(dados),
        });
        const json = await resp.json();
        if (resp.ok && json.sucesso) {
          formCadastro.reset();
          showToast(json.ignorado ? (json.erro || 'Venda ignorada.') : 'Venda salva com sucesso!');
          recarregarDados();
        } else {
          showToast(json.erro || 'Erro ao salvar venda.', 'error');
        }
      } catch {
        showToast('Falha de conexão.', 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Salvar Venda';
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
      if (!PODE_EDITAR_SEMANA) {
        showToast('Esta semana está bloqueada para edição.', 'error');
        return;
      }
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
        const linhasComPeriodo = linhas.map((linha) => ({ ...linha, mes: MES_ATUAL, semana: SEMANA_ATUAL }));
        const resp = await fetch('/vendas/bulk-cadastrar', {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ linhas: linhasComPeriodo }),
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

  MESES_VENDAS_TOPBAR.forEach((mesId) => {
    const body = document.getElementById(`body-${mesId}`);
    const arrow = document.getElementById(`arrow-${mesId}`);
    if (!body || !arrow) return;
    body.classList.add('week-month__body--collapsed');
    arrow.classList.add('week-month__arrow--collapsed');
  });

  aplicarFiltros();
  renderizarOpcoesAcao();
  aplicarBloqueioEdicao();
  conectarSocket();
  recarregarDados();
});
