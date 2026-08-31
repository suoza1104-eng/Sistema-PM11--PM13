window.PM11 = window.PM11 || {};

window.PM11.Balance = {
  schedule: [], metrics: {}, opts: { plans: [], items: [], gpms: [], work_centers: [], routes: [] },
  filters: {}, offsets: {}, book: [], selectedDay: null, target: 240, days: 30, start: '',
  mode: 'manual', preview: null, groupBy: 'none', chartMetric: 'hours', attempts: 50, balanceBy: 'none',

  async render() {
    const App = window.PM11.App;
    const proj = App.projects.find(x => x.id === App.projectId);
    this.target = Number(proj?.daily_inspection_target_minutes || this.target || 240);
    this.start = this.start || proj?.balance_anchor_date || new Date().toISOString().slice(0, 10);
    await this.load();
    this.draw();
  },

  async load() {
    const API = window.PM11.API, App = window.PM11.App;
    this.opts = await API.get('/api/pm11/balance/options');
    const q = { project_id: App.projectId, start: this.start, days: this.days, target_minutes: this.target, ...this.filters };
    const r = await API.get('/api/pm11/balance', q);
    this.schedule = r.schedule || [];
    this.metrics = r.metrics || {};
    this.book = await API.get('/api/pm11/balance/book', { project_id: App.projectId, ...this.filters });
  },

  draw() {
    const UI = window.PM11.UI;
    const fieldsHtml = `
      <div class="form-group"><label>Data Inicial</label><input class="control" id="bal-start" type="date" value="${this.start}"></div>
      <div class="form-group"><label>Projeção / Janela</label><select class="control" id="bal-days">${[30, 60, 90, 180, 365, 730].map(n => `<option value="${n}" ${n === this.days ? 'selected' : ''}>${n} dias</option>`).join('')}</select></div>
      <div class="form-group"><label>Tempo Máximo / Dia (min)</label><input class="control" id="bal-target" type="number" min="0" value="${this.target}"></div>
      <div class="form-group"><label>Rota</label><select class="control" id="bal-route"><option value="">Todas as rotas</option>${(this.opts.routes || []).map(x => `<option ${x === (this.filters.route || '') ? 'selected' : ''}>${UI.esc(x)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Plano</label><select class="control" id="bal-plan"><option value="">Todos os planos</option>${(this.opts.plans || []).map(p => `<option value="${p.id}" ${String(p.id) === String(this.filters.plan_id || '') ? 'selected' : ''}>${UI.esc(p.code)} — ${UI.esc(p.description || '')}</option>`).join('')}</select></div>
      <div class="form-group"><label>Item</label><select class="control" id="bal-item"><option value="">Todos os itens</option>${(this.opts.items || []).map(i => `<option value="${i.id}" ${String(i.id) === String(this.filters.item_id || '') ? 'selected' : ''}>#${i.legacy_identifier} — ${UI.esc(i.description || i.equipment_code || '')}</option>`).join('')}</select></div>
      <div class="form-group"><label>GPM</label><select class="control" id="bal-gpm"><option value="">Todos os GPMs</option>${(this.opts.gpms || []).map(x => `<option ${x === (this.filters.gpm || '') ? 'selected' : ''}>${UI.esc(x)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Agrupamento no gráfico</label><select class="control" id="bal-group"><option value="none">Sem agrupamento</option><option value="gpm" ${this.groupBy === 'gpm' ? 'selected' : ''}>GPM</option><option value="work_center" ${this.groupBy === 'work_center' ? 'selected' : ''}>Centro de Trabalho</option><option value="condition_code" ${this.groupBy === 'condition_code' ? 'selected' : ''}>Condição</option><option value="route" ${this.groupBy === 'route' ? 'selected' : ''}>Rota</option><option value="plan_code" ${this.groupBy === 'plan_code' ? 'selected' : ''}>Plano</option></select></div>
      <div class="form-group"><label>C. Trabalho (CT)</label><select class="control" id="bal-wc"><option value="">Todos os CTs</option>${(this.opts.work_centers || []).map(x => `<option ${x === (this.filters.work_center || '') ? 'selected' : ''}>${UI.esc(x)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Condição</label><select class="control" id="bal-cond"><option value="">Todas</option><option value="Q" ${this.filters.condition === 'Q' ? 'selected' : ''}>Q (Qualquer)</option><option value="P" ${this.filters.condition === 'P' ? 'selected' : ''}>P (Parado)</option><option value="M" ${this.filters.condition === 'M' ? 'selected' : ''}>M (Manutenção)</option><option value="F" ${this.filters.condition === 'F' ? 'selected' : ''}>F (Funcionando)</option></select></div>
    `;

    const actionsHtml = `
      <button class="btn btn-outline" id="btn-manual-balance" title="Abrir book e montar balanceamento arrastando itens">
        <svg viewBox="0 0 24 24"><path fill="currentColor" d="M3 5h18v4H3V5zm0 5h12v4H3v-4zm0 5h8v4H3v-4zm14-4 4 4-4 4v-3h-4v-2h4v-3z"/></svg>
        Balanceamento Manual
      </button>
      <button class="btn btn-primary" id="btn-auto-balance" title="Otimizar automaticamente por ciclo e rota respeitando a meta diária">
        <svg viewBox="0 0 24 24"><path fill="currentColor" d="M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5 1.5L9 5 6.5 10.5 1 13l5.5 2.5L9 21l2.5-5.5L17 13l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z"/></svg>
        + Balanceamento Automático
      </button>
      <button class="btn btn-outline" id="btn-restore-pre-balance" style="color: #991B1B; border-color: #FCA5A5; background: #FEF2F2;" title="Restaurar estado inicial do balanceamento (zerar deslocamentos)">
        <svg viewBox="0 0 24 24" style="width:16px;height:16px;"><path fill="currentColor" d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></svg>
        Restaurar Carga Inicial
      </button>
      <button class="btn btn-outline" id="btn-export-balance" title="Exportar relatório de balanceamento para Excel">
        <svg viewBox="0 0 24 24"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
        Exportar Excel
      </button>
    `;

    document.querySelector('#view').innerHTML =
      UI.pageHead('Balanceamento de Carga PM11', 'Projete a demanda de tempo de inspeção diária respeitando ciclo, rotas e limite de carga.', actionsHtml) +
      UI.filterCard(fieldsHtml, '', 'balance-filter-card') +
      this.cards() +
      `<div class="card" style="margin-top: 20px;">
        <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3>Carga Diária Projetada por Parada (${this.schedule.length} dias)</h3>
            <span class="card-subtitle">Clique nas colunas para visualizar ou mover as ordens de inspeção do dia.</span>
          </div>
          <div class="pm11-chart-switch"><button id="bal-show-hours" class="btn btn-xs ${this.chartMetric === 'hours' ? 'active' : ''}">Mostrar Horas</button><button id="bal-show-orders" class="btn btn-xs ${this.chartMetric === 'orders' ? 'active' : ''}">Mostrar Ordens</button></div>
        </div>
        <div class="card-body">
          ${this.chartLegend()}
          <div class="chart-bars" id="bal-bars">${this.bars()}</div>
        </div>
      </div>` +
      `<div class="card" style="margin-top: 20px;">
        <div class="card-header">
          <h3>Mapa de Calor de Distribuição</h3>
          <span class="card-subtitle">Intensidade de tempo de inspeção por parada ao longo do período.</span>
        </div>
        <div class="card-body no-padding">
          ${this.heat()}
        </div>
      </div>` +
      `<div class="balance-drawer" id="balance-drawer">
        <div class="balance-drawer-head">
          <div>
            <b id="balance-panel-title">Ordens</b>
            <div class="muted" id="balance-panel-subtitle"></div>
          </div>
          <button class="btn-icon" id="drawer-close">×</button>
        </div>
        <div class="balance-drawer-tabs">
          <button id="tab-day" class="active">Ordens do Dia</button>
          <button id="tab-book">Book de Ordens</button>
        </div>
        <div class="balance-drawer-body" id="balance-panel-body"></div>
      </div>`;

    this.bind();
    setTimeout(() => UI.enhanceSelects(), 40);
  },

  cards() {
    const UI = window.PM11.UI;
    const m = this.metrics;
    return `<div class="kpi-grid" id="balance-kpi-grid" style="margin-top: 20px;">
      <div class="kpi-card">
        <div class="kpi-icon bg-green-light"><svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm1 14h-2v-2h2v2zm0-4h-2V10h2v2z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">HH TOTAL PROJETADO</span><h3 class="kpi-value">${UI.fmtMin(m.avg_minutes * (this.schedule.length || 1))}</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon bg-blue-light"><svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">HH MÉDIO / PARADA</span><h3 class="kpi-value">${UI.fmtMin(m.avg_minutes)}</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon bg-blue-light"><svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm4 0h2v-2H7v2zm4 0h2v-2h-2v2zm4 0h2v-2h-2v2zm4 0h2v-2h-2v2zM4 17h16v2H4v-2zM4 5h16v2H4V5z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">UTILIZAÇÃO DA CAPACIDADE</span><h3 class="kpi-value">${m.target_utilization || 0}%</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon bg-green-light"><svg viewBox="0 0 24 24"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">ORDENS MÉDIAS / DIA</span><h3 class="kpi-value">${m.avg_items || 0}</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon bg-orange-light"><svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm1 14h-2v-2h2v2zm0-4h-2V10h2v2z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">PICO DIÁRIO</span><h3 class="kpi-value">${UI.fmtMin(m.max_minutes)}</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon bg-orange-light"><svg viewBox="0 0 24 24"><path d="M16 6l2.29 2.29-4.88 4.88-4-4L2 16.59 3.41 18l6-6 4 4 6.3-6.29L22 12V6z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">LINEARIDADE</span><h3 class="kpi-value">${m.linearity || 0}%</h3></div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon ${m.days_over_target > 0 ? 'bg-red-light' : 'bg-green-light'}"><svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg></div>
        <div class="kpi-content"><span class="kpi-title">DIAS ACIMA DA META</span><h3 class="kpi-value ${m.days_over_target > 0 ? 'txt-danger' : ''}">${m.days_over_target || 0}</h3></div>
      </div>
    </div>`;
  },

  bars() {
    const UI = window.PM11.UI;
    const valueOf = r => this.chartMetric === 'orders' ? Number(r.count || 0) : Number(r.minutes || 0);
    const max = Math.max(this.chartMetric === 'hours' ? this.target : 0, ...this.schedule.map(valueOf), 1), h = 250;
    const targetTop = 30 + (1 - Math.min(1, this.target / max)) * h;

    setTimeout(() => {
      const box = document.querySelector('#bal-bars');
      if (box && this.target > 0 && this.chartMetric === 'hours') {
        const l = document.createElement('div');
        l.className = 'target-line';
        l.style.top = targetTop + 'px';
        l.innerHTML = `<span>META ${UI.fmtMin(this.target)}</span>`;
        box.appendChild(l);
      }
    }, 0);

    return this.schedule.map((r, idx) => {
      const value = valueOf(r), ht = value ? Math.max(4, Math.min(h, (value / max) * h)) : 2;
      const isOver = this.target > 0 && r.minutes > this.target;
      const groups = {};
      (r.items || []).forEach(item => {
        const key = this.groupBy === 'none' ? 'Carga' : String(item[this.groupBy] || 'Sem cadastro');
        groups[key] = (groups[key] || 0) + (this.chartMetric === 'orders' ? 1 : Number(item.minutes || 0));
      });
      const colors = ['#72B900','#1687C9','#F59E0B','#7C3AED','#E4574F','#0F766E','#D946EF','#64748B'];
      const allNames = [...new Set(this.schedule.flatMap(day => (day.items || []).map(item => this.groupBy === 'none' ? 'Carga' : String(item[this.groupBy] || 'Sem cadastro'))))].sort();
      const segments = Object.entries(groups).map(([name, amount]) => `<div class="bar-segment" style="height:${value ? amount / value * ht : 0}px;background:${colors[Math.max(0, allNames.indexOf(name)) % colors.length]}" title="${UI.esc(name)}: ${this.chartMetric === 'orders' ? amount + ' ordem(ns)' : UI.fmtMin(amount)}"></div>`).join('');
      return `<div class="chart-bar-col" data-day="${idx}" title="${UI.fmtDate(r.date, true)} · ${UI.fmtMin(r.minutes)} · ${r.count} ordens">
        <div class="bar-val">${this.chartMetric === 'orders' ? r.count : (r.minutes ? UI.fmtMin(r.minutes) : '0')}</div>
        <div class="bar-track">
          <div class="bar-stack ${isOver ? 'over' : ''}" style="height:${ht}px">${segments}</div>
        </div>
        <div class="bar-lbl">${graphDayLabel(idx)}<br><span class="bar-subdate">${UI.fmtDate(r.date, false)}</span></div>
      </div>`;
    }).join('');
  },

  chartLegend() {
    if (this.groupBy === 'none') return '';
    const UI = window.PM11.UI, colors = ['#72B900','#1687C9','#F59E0B','#7C3AED','#E4574F','#0F766E','#D946EF','#64748B'];
    const names = [...new Set(this.schedule.flatMap(day => (day.items || []).map(item => String(item[this.groupBy] || 'Sem cadastro'))))].sort();
    return `<div class="pm11-chart-legend">${names.map((name,i)=>`<span><i style="background:${colors[i%colors.length]}"></i>${UI.esc(name)}</span>`).join('')}</div>`;
  },

  heat() {
    const UI = window.PM11.UI;
    if (!this.schedule || !this.schedule.length) return '<div class="muted" style="padding:15px;text-align:center;">Nenhuma parada no período.</div>';

    return `<div class="table-responsive-container">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th style="min-width: 160px;">Indicadores de Parada</th>
            ${this.schedule.map((s, idx) => `<th class="text-center">${graphDayLabel(idx)}<br><span style="font-size:9px;font-weight:normal;color:var(--text-muted);">${UI.fmtDate(s.date, false)}</span></th>`).join('')}
          </tr>
        </thead>
        <tbody>
          <tr class="heatmap-row-total">
            <td><strong>Tempo Total (HH/min)</strong></td>
            ${this.schedule.map((s, idx) => {
              const isOver = this.target > 0 && s.minutes > this.target;
              return `<td class="heatmap-cell ${isOver ? 'heat-exceeded' : s.minutes > 0 ? 'heat-low' : 'heat-empty'}" data-day="${idx}" style="cursor:pointer;" onclick="window.PM11.Balance.openDay(${idx})">${UI.fmtMin(s.minutes)}</td>`;
            }).join('')}
          </tr>
          <tr>
            <td><strong>Ordens de Inspeção (Qtd)</strong></td>
            ${this.schedule.map((s, idx) => `<td class="heatmap-cell text-center" data-day="${idx}" style="cursor:pointer;" onclick="window.PM11.Balance.openDay(${idx})">${s.count || 0}</td>`).join('')}
          </tr>
        </tbody>
      </table>
    </div>`;
  },

  async refreshFromControls() {
    this.start = document.querySelector('#bal-start').value;
    this.days = Number(document.querySelector('#bal-days').value);
    this.target = Number(document.querySelector('#bal-target').value || 0);
    this.filters = {
      plan_id: document.querySelector('#bal-plan').value,
      item_id: document.querySelector('#bal-item').value,
      route: document.querySelector('#bal-route').value,
      gpm: document.querySelector('#bal-gpm').value,
      work_center: document.querySelector('#bal-wc').value,
      condition: document.querySelector('#bal-cond').value
    };
    this.groupBy = document.querySelector('#bal-group')?.value || 'none';
    await this.load();
    this.draw();
  },

  bind() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;

    const bManual = document.querySelector('#btn-manual-balance');
    if (bManual) bManual.onclick = () => this.showBook();

    const bAuto = document.querySelector('#btn-auto-balance');
    if (bAuto) bAuto.onclick = () => this.openAutoConfig();

    const bRestore = document.querySelector('#btn-restore-pre-balance');
    if (bRestore) bRestore.onclick = () => this.restoreInitial();

    const bExport = document.querySelector('#btn-export-balance');
    if (bExport) bExport.onclick = () => UI.download(`/api/pm11/export/project?project_id=${App.projectId}&days=${this.days}&start=${this.start}`);

    ['bal-start', 'bal-days', 'bal-target', 'bal-plan', 'bal-item', 'bal-route', 'bal-gpm', 'bal-wc', 'bal-cond', 'bal-group'].forEach(id => {
      const el = document.querySelector('#' + id);
      if (el) el.onchange = () => this.refreshFromControls();
    });
    document.querySelector('#bal-show-hours')?.addEventListener('click', () => { this.chartMetric = 'hours'; this.draw(); });
    document.querySelector('#bal-show-orders')?.addEventListener('click', () => { this.chartMetric = 'orders'; this.draw(); });

    document.querySelectorAll('[data-day]').forEach(x => {
      x.onclick = () => this.openDay(Number(x.dataset.day));
      x.ondragover = e => { e.preventDefault(); x.classList.add('drop-target'); };
      x.ondragleave = () => x.classList.remove('drop-target');
      x.ondrop = e => {
        e.preventDefault();
        x.classList.remove('drop-target');
        const itemId = Number(e.dataTransfer.getData('text/pm11-item'));
        if (itemId) this.promptTransferPlanModal(itemId, Number(x.dataset.day));
      };
    });

    const bClose = document.querySelector('#drawer-close');
    if (bClose) bClose.onclick = () => this.closePanel();

    const tabDay = document.querySelector('#tab-day');
    if (tabDay) tabDay.onclick = () => this.showDay(this.selectedDay);

    const tabBook = document.querySelector('#tab-book');
    if (tabBook) tabBook.onclick = () => this.showBook();
  },

  openPanel() { document.querySelector('#balance-drawer').classList.add('open'); },
  closePanel() { document.querySelector('#balance-drawer').classList.remove('open'); },
  openDay(idx) { this.selectedDay = idx; this.openPanel(); this.showDay(idx); },

  showDay(idx) {
    const UI = window.PM11.UI;
    if (idx == null) idx = 0;
    this.openPanel();
    document.querySelector('#tab-day').classList.add('active');
    document.querySelector('#tab-book').classList.remove('active');
    const r = this.schedule[idx] || { date: '', minutes: 0, count: 0, items: [] };

    document.querySelector('#balance-panel-title').textContent = `${graphDayLabel(idx)} (${UI.fmtDate(r.date, true)})`;
    document.querySelector('#balance-panel-subtitle').textContent = `${UI.fmtMin(r.minutes)} · ${r.count} ordem(ns) agendada(s)`;

    document.querySelector('#balance-panel-body').innerHTML = `
      <div style="flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding-right:4px;">
        ${r.items.length ? r.items.map(x => this.orderCard(x, idx)).join('') : '<div class="preview-placeholder" style="padding:20px;text-align:center;color:var(--text-muted);">Nenhuma ordem agendada para este dia.</div>'}
      </div>
      <div style="margin-top:12px;"><button class="btn btn-outline btn-block" id="open-book-btn">Abrir Book de Ordens</button></div>
    `;

    document.querySelector('#open-book-btn').onclick = () => this.showBook();
    this.bindOrderCards();
  },

  orderCard(x, dayIdx = null) {
    const UI = window.PM11.UI;
    const isLocked = intBool(x.locked);
    const planText = x.plan_description || x.text_cycle || '';
    const cycleText = x.text_cycle || x.cycle_code || '';
    return `<div class="order-card" draggable="true" data-item="${x.item_id}" style="border-left: 4px solid ${isLocked ? '#DC2626' : 'var(--primary-color)'}; padding:10px; margin-bottom:8px; background:#FFFFFF; border-radius:6px; border:1px solid var(--border-color);">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <b style="font-size:12px; color:var(--text-color);">Rota ${UI.esc(x.route || '—')} · #${x.identifier}</b>
        <button class="btn btn-xs ${isLocked ? 'btn-danger' : 'btn-outline'} toggle-lock-btn" data-item="${x.item_id}" data-locked="${isLocked ? 1 : 0}" title="${isLocked ? 'Item Trancado (clique para destrancar)' : 'Item Destrancado (clique para trancar no balanceamento)'}">
          ${isLocked ? '🔒 Trancado' : '🔓 Destrancado'}
        </button>
      </div>
      <div style="font-size:12.5px; font-weight:600; margin:4px 0; color:#0F172A;">${UI.esc(x.description)}</div>
      <div style="font-size:11px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:6px 8px; margin:6px 0; color:#334155;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:2px;">
          <span style="font-weight:700; color:#0F766E;">📋 ${UI.esc(x.plan_code || 'Sem plano')}</span>
          ${cycleText ? `<span style="font-weight:600; color:#0284C7; background:#E0F2FE; padding:1px 6px; border-radius:4px; font-size:10px;">${UI.esc(cycleText)}</span>` : ''}
        </div>
        ${planText ? `<div style="color:#475569; font-size:10.5px; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${UI.esc(planText)}">${UI.esc(planText)}</div>` : ''}
      </div>
      <div class="muted" style="font-size:11px; display:flex; justify-content:space-between; align-items:center;">
        <span>Equip.: <strong>${UI.esc(x.equipment || '—')}</strong></span>
        <b style="color:#15803D;">${UI.fmtMin(x.minutes)}</b>
      </div>
    </div>`;
  },

  bindOrderCards() {
    document.querySelectorAll('#balance-panel-body .order-card[draggable]').forEach(c => {
      c.ondragstart = e => {
        c.classList.add('dragging');
        e.dataTransfer.setData('text/pm11-item', c.dataset.item);
      };
    });
    document.querySelectorAll('#balance-panel-body .toggle-lock-btn').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const itemId = Number(btn.dataset.item);
        const locked = Number(btn.dataset.locked) === 0;
        this.toggleLock(itemId, locked);
      };
    });
  },

  async toggleLock(itemId, locked) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    UI.showLoader(locked ? 'Trancando item...' : 'Destrancando item...');
    try {
      await API.post('/api/pm11/balance/lock', { project_id: App.projectId, item_id: itemId, locked });
      UI.toast(locked ? 'Item trancado (não mudará no balanceamento automático).' : 'Item destrancado.');
      await this.load();
      this.draw();
      if (this.selectedDay != null) this.openDay(this.selectedDay);
    } finally {
      UI.hideLoader();
    }
  },

  showBook() {
    const UI = window.PM11.UI;
    this.openPanel();
    document.querySelector('#tab-book').classList.add('active');
    document.querySelector('#tab-day').classList.remove('active');
    document.querySelector('#balance-panel-title').textContent = 'Book de Ordens';
    document.querySelector('#balance-panel-subtitle').textContent = 'Arraste uma inspeção para a barra do dia desejado';

    document.querySelector('#balance-panel-body').innerHTML = `
      <div style="margin-bottom:12px; display:flex; flex-direction:column; gap:8px;">
        <button type="button" class="btn btn-outline btn-block" id="btn-return-all-to-book" style="border-color:#CBD5E1; color:#1E293B; font-weight:600; padding:8px 12px;">
          ↩️ Retornar Ordens ao Book
        </button>
        <input class="control" id="book-search" placeholder="Buscar por ID, item, equipamento ou rota...">
      </div>
      <div id="book-list" style="flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding-right:4px;"></div>
    `;

    document.querySelector('#btn-return-all-to-book').onclick = () => this.promptReturnToBookModal();

    const renderList = () => {
      const q = (document.querySelector('#book-search').value || '').toLowerCase();
      const list = this.book.filter(x => (`${x.identifier} ${x.description} ${x.equipment} ${x.route} ${x.plan_code}`).toLowerCase().includes(q));
      document.querySelector('#book-list').innerHTML = list.length
        ? list.map(x => this.orderCard(x)).join('')
        : (this.book.length === 0
            ? '<div class="preview-placeholder" style="padding:24px 16px; text-align:center; color:#15803D; background:#F0FDF4; border:1px solid #BBF7D0; border-radius:8px; margin-top:10px;"><b style="font-size:13px; color:#166534;">🎉 Todas as ordens estão balanceadas!</b><p style="font-size:12px; margin:6px 0 0; color:#334155;">Nenhuma ordem pendente no Book de Ordens. Se desejar mover ordens de volta ao Book para reagendar, utilize o botão <b>Retornar Ordens ao Book</b> acima.</p></div>'
            : '<div class="preview-placeholder" style="padding:20px;text-align:center;color:var(--text-muted);">Nenhuma ordem encontrada para a pesquisa.</div>');
      this.bindOrderCards();
    };

    document.querySelector('#book-search').oninput = renderList;
    renderList();
  },

  promptReturnToBookModal() {
    document.getElementById('modal-return-to-book')?.remove();

    const modal = document.createElement('div');
    modal.id = 'modal-return-to-book';
    modal.className = 'modal-backdrop';
    modal.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(15,23,42,0.5); z-index:99999; display:flex; align-items:center; justify-content:center;';

    modal.innerHTML = `
      <div class="card" style="width:100%; max-width:460px; padding:24px; border-radius:12px; background:#fff; box-shadow:0 20px 40px rgba(0,0,0,0.25);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid #E2E8F0; padding-bottom:10px;">
          <h3 style="font-size:16px; font-weight:700; color:#0F172A; margin:0;">↩️ Retornar Ordens ao Book</h3>
          <button type="button" class="btn-icon" id="close-modal-return-book" style="border:0; background:transparent; font-size:20px; cursor:pointer;">×</button>
        </div>
        <div style="text-align:center; margin-bottom:20px;">
          <p style="font-size:14px; font-weight:600; color:#1E293B; margin-bottom:8px;">
            Deseja remover as ordens do gráfico e retorná-las para o Book de Ordens?
          </p>
          <p class="subtitle" style="font-size:12px; color:#64748B; line-height:1.4;">
            Escolha se deseja retornar todas as ordens posicionadas ou apenas aquelas que não estão trancadas.
          </p>
        </div>
        <div style="display:flex; flex-direction:column; gap:10px;">
          <button type="button" class="btn btn-primary" id="btn-modal-return-all" style="width:100%; padding:10px; font-weight:700;">
            📦 Retornar TODAS as Ordens
          </button>
          <button type="button" class="btn btn-warning" id="btn-modal-return-unlocked" style="width:100%; padding:10px; font-weight:700; background-color:#F59E0B; border-color:#D97706; color:#FFF;">
            🔓 Retornar APENAS Destrancadas
          </button>
          <button type="button" class="btn btn-outline" id="btn-modal-cancel-return" style="width:100%; padding:8px;">
            ❌ Cancelar
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('#close-modal-return-book').onclick = closeModal;
    modal.querySelector('#btn-modal-cancel-return').onclick = closeModal;

    modal.querySelector('#btn-modal-return-all').onclick = async () => {
      closeModal();
      await this.executeReturnToBook(false);
    };

    modal.querySelector('#btn-modal-return-unlocked').onclick = async () => {
      closeModal();
      await this.executeReturnToBook(true);
    };
  },

  async executeReturnToBook(onlyUnlocked) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    UI.showLoader(onlyUnlocked ? 'Retornando ordens destrancadas ao Book...' : 'Retornando todas as ordens ao Book...');
    try {
      await API.post('/api/pm11/balance/return-all', {
        project_id: App.projectId,
        only_unlocked: onlyUnlocked
      });
      UI.toast(
        onlyUnlocked ? 'Ordens destrancadas retornadas ao Book!' : 'Todas as ordens retornadas ao Book!',
        'success'
      );
      await this.load();
      this.draw();
      this.showBook();
    } catch (err) {
      UI.toast(`Erro ao retornar ordens ao Book: ${err.message}`, 'error');
    } finally {
      UI.hideLoader();
    }
  },

  async promptTransferPlanModal(itemId, dayIdx) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    UI.showLoader('Buscando planos elegíveis...');
    try {
      const data = await API.get(`/api/pm11/balance/eligible-plans?project_id=${App.projectId}&item_id=${itemId}&day_idx=${dayIdx}&start=${this.start}&days=${this.days}`);
      if (data.error) {
        UI.toast(data.error, 'error');
        return;
      }

      const item = data.item;
      const dayLabel = graphDayLabel(dayIdx);
      const targetDate = UI.fmtDate(data.target_date, true);
      const eligible = data.eligible_plans || [];
      const familyPlans = data.family_plans || [];

      let optionsHtml = '';
      if (eligible.length > 0) {
        optionsHtml = eligible.map((p, idx) => `
          <label style="display:flex; align-items:flex-start; gap:10px; padding:12px; border:1px solid #CBD5E1; border-radius:8px; margin-bottom:8px; cursor:pointer; background:${idx === 0 ? '#F0FDF4' : '#FFFFFF'};">
            <input type="radio" name="target_plan_id" value="${p.id}" ${idx === 0 ? 'checked' : ''} style="margin-top:3px;">
            <div>
              <b style="color:#166534; font-size:13px;">${UI.esc(p.code)}</b>
              <span class="badge green" style="margin-left:6px;">Elegível na Data</span>
              <p style="margin:4px 0 0; font-size:12px; color:#334155;">${UI.esc(p.description || 'Sem descrição')}</p>
              <small style="color:#64748B; font-size:11px;">Offset do Plano: ${p.offset_days} dia(s)</small>
            </div>
          </label>
        `).join('');
      } else {
        optionsHtml = `
          <div style="padding:12px; background:#FEF3C7; border:1px solid #F59E0B; border-radius:8px; margin-bottom:12px;">
            <strong style="color:#B45309; font-size:13px;">⚠️ Nenhum Plano Elegível Agendado para esta Data</strong>
            <p style="margin:4px 0 0; font-size:12px; color:#1F2937;">Nenhum plano da família <b>${data.family_prefix}</b> (${item.cycle_value} ${item.unit}) está agendado para a data ${dayLabel} (${targetDate}).</p>
          </div>
        `;
        if (familyPlans.length > 0) {
          optionsHtml += `<p style="font-size:12px; font-weight:700; margin:10px 0 6px;">Outros Planos da mesma Família (${familyPlans.length}):</p>` +
            familyPlans.map((p, idx) => `
              <label style="display:flex; align-items:flex-start; gap:10px; padding:10px; border:1px solid #E2E8F0; border-radius:6px; margin-bottom:6px; cursor:pointer; background:#FFFFFF;">
                <input type="radio" name="target_plan_id" value="${p.id}" ${idx === 0 ? 'checked' : ''} style="margin-top:3px;">
                <div>
                  <b style="color:#1E293B; font-size:12px;">${UI.esc(p.code)}</b>
                  <p style="margin:2px 0 0; font-size:11px; color:#64748B;">${UI.esc(p.description || '')} (Offset: ${p.offset_days}d)</p>
                </div>
              </label>
            `).join('');
        }
      }

      UI.modal('Troca de Plano — Seleção de Plano Elegível', `
        <div style="padding:4px;">
          <div style="margin-bottom:14px; padding:12px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <b style="font-size:14px; color:#0F172A;">Item #${item.legacy_identifier} — ${UI.esc(item.description)}</b>
              <span class="badge blue">Parada Destino: ${dayLabel} (${targetDate})</span>
            </div>
            <div style="font-size:12px; color:#475569;">
              <span>Plano Atual: <b style="color:#B91C1C;">${UI.esc(item.plan_code)}</b></span> ·
              <span>Ciclo: <b>${item.cycle_value} ${item.unit} (${item.text_cycle || 'SEMANAL'})</b></span>
            </div>
          </div>

          <div style="margin-bottom:12px; font-size:12px; color:#64748B; background:#F1F5F9; padding:8px 12px; border-radius:6px;">
            💡 <b>Critério de Troca:</b> O item sairá do plano <b>${UI.esc(item.plan_code)}</b> e entrará no novo plano selecionado abaixo (mesmo ciclo e 9 caracteres idênticos <b>${data.family_prefix}</b>).
          </div>

          <div style="max-height:280px; overflow-y:auto; margin-bottom:10px;">
            ${optionsHtml}
          </div>
        </div>
      `, {
        saveText: '🚀 Confirmar e Transferir Item de Plano',
        onSave: async () => {
          const selected = document.querySelector('input[name="target_plan_id"]:checked');
          if (!selected) {
            UI.toast('Selecione um plano de destino.', 'warning');
            return false;
          }
          const targetPlanId = Number(selected.value);
          const chosenPlan = (eligible.concat(familyPlans)).find(p => p.id === targetPlanId);

          UI.showLoader('Transferindo item para novo plano...');
          try {
            await API.post('/api/pm11/balance/apply', {
              project_id: App.projectId,
              assignments: { [itemId]: targetPlanId }
            });
            UI.toast(`Item #${item.legacy_identifier} transferido com sucesso para o plano ${chosenPlan?.code || targetPlanId}!`);
            await this.load();
            this.draw();
            this.openDay(dayIdx);
          } finally {
            UI.hideLoader();
          }
        }
      });
    } finally {
      UI.hideLoader();
    }
  },

  async moveItemToDay(itemId, dayIdx) {
    this.promptTransferPlanModal(itemId, dayIdx);
  },

  async restoreInitial() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!confirm('Restaurar a carga inicial zerará o deslocamento de todos os itens destrancados. Continuar?')) return;

    UI.showLoader('Restaurando carga inicial...');
    try {
      await API.post('/api/pm11/balance/reset', { project_id: App.projectId });
      UI.toast('Carga inicial restaurada.');
      await this.load();
      this.draw();
    } finally {
      UI.hideLoader();
    }
  },

  showBalanceProgress() {
    this.hideBalanceProgress();
    const overlay = document.createElement('div');
    overlay.id = 'pm11-balance-progress'; overlay.className = 'pm11-balance-progress';
    overlay.innerHTML = `<div class="pm11-balance-progress-card"><div class="pm11-balance-orbit"><span></span><i></i><b></b><div>PM11</div></div><div class="pm11-balance-kicker">OTIMIZAÇÃO INTELIGENTE</div><h2>Buscando o melhor balanceamento</h2><p id="pm11-progress-step">Preparando famílias, ciclos e sequências de rota...</p><div class="pm11-progress-track"><div id="pm11-progress-fill"></div></div><div class="pm11-progress-meta"><span id="pm11-progress-detail">Analisando restrições</span><strong id="pm11-progress-percent">4%</strong></div><div class="pm11-progress-phases"><span class="active">Mapear</span><span>Simular</span><span>Comparar</span><span>Refinar</span></div><small>Os itens permanecem inalterados até você confirmar a melhor prévia.</small></div>`;
    document.body.appendChild(overlay);
    const stages=[[18,'Organizando itens por rota e família...','Mapeando planos elegíveis',0],[42,'Executando múltiplos cenários...','Testando distribuições de carga',1],[68,'Comparando gaps, picos e linearidade...','Selecionando os melhores resultados',2],[88,'Refinando a melhor combinação...','Reduzindo a diferença entre os dias',3]];
    let progress=4,stage=0;
    this.balanceProgressTimer=setInterval(()=>{if(stage<stages.length&&progress>=stages[stage][0])stage++;const current=stages[Math.min(stage,stages.length-1)];progress=Math.min(92,progress+(progress<45?2:progress<75?1:.35));overlay.querySelector('#pm11-progress-fill').style.width=`${progress}%`;overlay.querySelector('#pm11-progress-percent').textContent=`${Math.floor(progress)}%`;overlay.querySelector('#pm11-progress-step').textContent=current[1];overlay.querySelector('#pm11-progress-detail').textContent=current[2];overlay.querySelectorAll('.pm11-progress-phases span').forEach((el,idx)=>el.classList.toggle('active',idx<=current[3]));},90);
  },
  async finishBalanceProgress(success=true) {
    const overlay=document.querySelector('#pm11-balance-progress');if(!overlay)return;clearInterval(this.balanceProgressTimer);overlay.querySelector('#pm11-progress-fill').style.width='100%';overlay.querySelector('#pm11-progress-percent').textContent='100%';overlay.querySelector('#pm11-progress-step').textContent=success?'Melhor balanceamento encontrado!':'Não foi possível concluir';overlay.querySelector('#pm11-progress-detail').textContent=success?'Prévia pronta para comparação':'Verifique a mensagem apresentada';overlay.classList.toggle('error',!success);await new Promise(resolve=>setTimeout(resolve,success?420:650));this.hideBalanceProgress();
  },
  hideBalanceProgress() { clearInterval(this.balanceProgressTimer);this.balanceProgressTimer=null;document.querySelector('#pm11-balance-progress')?.remove(); },

  openAutoConfig() {
    const UI = window.PM11.UI;
    UI.modal('Configurar Balanceamento Automático PM11', `
      <div class="pm11-auto-config-intro"><span>✦</span><div><b>Busca inteligente do menor gap</b><p>Defina quantos cenários serão comparados e se a linearidade deve ser calculada para a carteira inteira ou separadamente por grupo.</p></div></div>
      <div class="pm11-auto-config-grid">
        <div class="form-group"><label>Quantidade de balanceamentos</label><input class="control" id="pm11-auto-attempts" type="number" min="1" max="1000" value="${this.attempts}"><small>Mais tentativas aumentam a busca e o tempo de processamento.</small></div>
        <div class="form-group"><label>Estratégia de linearidade</label><select class="control" id="pm11-auto-balance-by"><option value="none">Carga total do projeto</option><option value="work_center" ${this.balanceBy === 'work_center' ? 'selected' : ''}>Separar por Centro de Trabalho</option><option value="gpm" ${this.balanceBy === 'gpm' ? 'selected' : ''}>Separar por GPM</option></select><small>Cada CT ou GPM terá sua própria carga diária linear.</small></div>
      </div>
      <div class="pm11-auto-rules"><b>Regras preservadas</b><div><span>✓ Mesmo ciclo e texto do ciclo</span><span>✓ Mesmos 9 primeiros caracteres do plano</span><span>✓ Sequência e agrupamento por rota</span><span>✓ Itens trancados não se movem</span></div></div>
    `, {
      wide: true,
      saveText: 'Executar Balanceamento',
      onSave: () => {
        this.attempts = Math.max(1, Math.min(1000, Number(document.querySelector('#pm11-auto-attempts')?.value || 50)));
        this.balanceBy = document.querySelector('#pm11-auto-balance-by')?.value || 'none';
        setTimeout(() => this.autoPreview(), 80);
      }
    });
  },

  async autoPreview() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    this.showBalanceProgress();
    try {
      this.preview = await API.post('/api/pm11/balance/auto-preview', {
        project_id: App.projectId,
        start: this.start,
        days: this.days,
        target_minutes: this.target,
        attempts: this.attempts,
        balance_by: this.balanceBy,
        ...this.filters
      });
      await this.finishBalanceProgress(true);
    } catch (err) {
      await this.finishBalanceProgress(false);
      UI.toast(err.message || 'Erro ao calcular balanceamento', 'error');
      return;
    }

    const p = this.preview;
    if (!p) return;

    const box = (title, m) => `<div class="card p-15" style="flex:1; background:#FAFCFA; border:1px solid var(--border-color); border-radius:8px;">
      <h4 style="color:var(--primary-dark); font-size:14px; margin-bottom:10px;">${title}</h4>
      <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:13px;"><span>Tempo Médio / Parada:</span><b>${UI.fmtMin(m.avg_minutes)}</b></div>
      <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:13px;"><span>Pico Diário:</span><b>${UI.fmtMin(m.max_minutes)}</b></div>
      <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:13px;"><span>Linearidade:</span><b>${m.linearity}%</b></div>
      <div style="display:flex; justify-content:space-between; font-size:13px;"><span>Dias Acima da Meta:</span><b class="${m.days_over_target > 0 ? 'txt-danger' : ''}">${m.days_over_target}</b></div>
    </div>`;

    UI.modal('Prévia do Balanceamento Automático PM11',
      `<div style="display:flex; gap:15px; margin-bottom:15px;">
        ${box('ANTES DO BALANCEAMENTO', p.before_metrics)}
        ${box('DEPOIS DO BALANCEAMENTO', p.after_metrics)}
      </div>
      <div class="helpbox" style="margin-top:10px;">
        <b>${p.changed_items}</b> item(ns) serão ajustados horizontalmente por ciclo e rota em ${p.elapsed_seconds}s. Itens trancados 🔒 foram preservados.
      </div>`,
      {
        wide: true,
        saveText: 'Aplicar Balanceamento',
        onSave: async () => {
          try {
            const applied = await API.post('/api/pm11/balance/apply', { project_id: App.projectId, assignments: p.assignments });
            UI.toast(`Balanceamento aplicado: ${applied.updated || 0} item(ns) movimentado(s) entre planos.`);
            await this.load();
            this.draw();
          } catch (err) {
            UI.toast(err.message || 'Erro ao aplicar balanceamento', 'error');
            return false;
          }
        }
      }
    );
    setTimeout(() => {
      const info = document.querySelector('.modal .helpbox');
      if (info) info.textContent = `${p.changed_items} item(ns) serão reassociados. Foram comparadas ${p.attempts || 1} tentativas e ${p.refinement_rounds || 0} rodadas de refinamento em ${p.elapsed_seconds}s.${p.constrained_families?.length ? ` Limite estrutural: ${p.constrained_families.length} família(s) não possuem planos para todos os dias.` : ''}${p.failures?.length ? ` ${p.failures.length} item(ns) sem destino elegível.` : ''}`;
    }, 0);
  }
};

function intBool(v) { return v === true || v === 1 || v === '1'; }
function maxOne(v) { return Math.max(1, int(v)); }
function int(v) { return parseInt(v, 10) || 0; }
function graphDayLabel(index) {
  const days = ['SEG', 'TER', 'QUA', 'QUI', 'SEX'];
  return `${days[index % 5]}${Math.floor(index / 5) + 1}`;
}
