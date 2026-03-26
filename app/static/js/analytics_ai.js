'use strict';

(function () {
  const root = document.querySelector('[data-analytics-ai]');
  if (!root) return;

  const toggle = root.querySelector('[data-ai-toggle]');
  const panel = root.querySelector('[data-ai-panel]');
  const closeBtn = root.querySelector('[data-ai-close]');
  const form = root.querySelector('[data-ai-form]');
  const input = root.querySelector('[data-ai-input]');
  const messages = root.querySelector('[data-ai-messages]');
  const status = root.querySelector('[data-ai-status]');

  const config = {
    url: root.dataset.chatUrl,
    mes: root.dataset.mes,
    empreendimento: root.dataset.empreendimento || '',
    responsavel: root.dataset.responsavel || '',
    tipoContato: root.dataset.tipoContato || '',
    situacao: root.dataset.situacao || '',
  };

  const history = [];

  function csrfHeaders(extra = {}) {
    return { 'X-CSRFToken': window.APP_CSRF_TOKEN || '', ...extra };
  }

  function setOpen(open) {
    root.classList.toggle('analytics-ai--open', open);
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) input.focus();
  }

  function setStatus(text) {
    status.textContent = text || '';
  }

  function addMessage(role, text) {
    const item = document.createElement('div');
    item.className = `analytics-ai__message analytics-ai__message--${role}`;
    item.textContent = text;
    messages.appendChild(item);
    messages.scrollTop = messages.scrollHeight;
  }

  async function sendMessage(message) {
    history.push({ role: 'user', content: message });
    addMessage('user', message);
    setStatus('Kamille está analisando os dados do relatório...');

    try {
      const response = await fetch(config.url, {
        method: 'POST',
        headers: csrfHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          message,
          history,
          mes: config.mes,
          empreendimento: config.empreendimento,
          responsavel: config.responsavel,
          tipo_contato: config.tipoContato,
          situacao: config.situacao,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.erro || 'Falha ao consultar a assistente.');
      }

      history.push({ role: 'assistant', content: payload.answer });
      addMessage('assistant', payload.answer);
      setStatus('Kamille está pronta para uma nova análise.');
    } catch (error) {
      addMessage('assistant', error.message || 'Não consegui responder agora. Tente novamente em instantes.');
      setStatus('Kamille encontrou um problema nesta consulta.');
    }
  }

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  closeBtn.addEventListener('click', () => setOpen(false));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    await sendMessage(message);
  });

  if (root.dataset.enabled === 'true') {
    setStatus('Pergunte para a Kamille sobre metas, gargalos, tendências e oportunidades do trimestre.');
  } else {
    setStatus('Configure GEMINI_API_KEY para habilitar a Kamille.');
    form.querySelector('button').disabled = true;
    input.disabled = true;
  }
})();
