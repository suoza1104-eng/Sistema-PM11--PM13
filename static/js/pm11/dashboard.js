window.PM11 = window.PM11 || {};

window.PM11.Dashboard = {
  async render() {
    const API = window.PM11.API, UI = window.PM11.UI;
    const d = await API.get('/api/dashboard');
    const totalHours = (Number(d.total_minutes || 0) / 60).toFixed(1).replace('.', ',');
    const quality = Object.fromEntries((d.quality || []).map(x => [String(x.label || 'OK').toUpperCase(), Number(x.value || 0)]));
    const issuesTotal = Number(d.issues.missing_time || 0) + Number(d.issues.missing_route || 0) + Number(d.issues.missing_characteristics || 0);
    const m = d.balance_metrics || {};
    document.querySelector('#view').innerHTML = UI.pageHead('Painel Gerencial PM11', 'Visão executiva da carteira de inspeções, qualidade cadastral, métodos e equilíbrio da carga.') + `
      <div class="pm11-executive-kpis">
        ${this.kpi('Planos ativos', d.plans, 'periodicidades', 'green')}
        ${this.kpi('Itens de inspeção', d.items, 'ordens potenciais', 'blue')}
        ${this.kpi('HH da carteira', totalHours + 'h', 'tempo total cadastrado', 'orange')}
        ${this.kpi('Linearidade', (m.linearity || 0) + '%', 'equilíbrio em 30 dias', Number(m.linearity || 0) >= 80 ? 'green' : 'red')}
        ${this.kpi('Pico diário', this.fmtMin(m.max_minutes || 0), (m.days_over_target || 0) + ' dias acima da meta', 'orange')}
      </div>
      <div class="managerial-insights-grid pm11-managerial-grid">
        ${this.donutCard('QUANTITATIVO', 'Situação dos itens', 'pm11-quant-donut', 'pm11-quant-legend')}
        ${this.donutCard('QUALITATIVO', 'Qualidade cadastral', 'pm11-quality-donut', 'pm11-quality-legend')}
        <article class="managerial-card managerial-method-card"><div class="managerial-card-head"><div><span class="managerial-eyebrow">MÉTODOS</span><h3>Métodos de inspeção</h3></div><span class="managerial-card-badge">${d.characteristics} características</span></div><div id="pm11-methods" class="managerial-method-list"></div></article>
      </div>
      <div class="pm11-management-charts">
        <article class="card pm11-balance-card"><div class="card-header"><div><span class="managerial-eyebrow">BALANCEAMENTO</span><h3>Carga diária projetada — 30 dias</h3></div><div class="pm11-chart-summary"><b>${this.fmtMin(m.avg_minutes || 0)}</b><span>média/dia</span></div></div><div class="card-body"><div id="pm11-management-balance" class="pm11-management-bars"></div></div></article>
        <article class="card"><div class="card-header"><div><span class="managerial-eyebrow">CARTEIRA</span><h3>Itens por ciclo</h3></div></div><div class="card-body"><div id="pm11-cycle-bars" class="pm11-cycle-list"></div></div></article>
      </div>
      <article class="pm11-quality-strip"><div><span>Sem tempo</span><strong class="${d.issues.missing_time ? 'txt-danger' : ''}">${d.issues.missing_time}</strong></div><div><span>Sem rota</span><strong>${d.issues.missing_route}</strong></div><div><span>Sem características</span><strong>${d.issues.missing_characteristics}</strong></div><div class="pm11-quality-score"><span>Pendências mapeadas</span><strong>${issuesTotal}</strong></div></article>`;
    this.renderDonut('pm11-quant-donut','pm11-quant-legend',[{label:'Ativos',value:Number(d.items||0),color:'#72B900'},{label:'Inativos',value:Number(d.inactive_items||0),color:'#CBD5E1'}],d.total_items||d.items,'itens');
    this.renderDonut('pm11-quality-donut','pm11-quality-legend',[{label:'Conformes',value:quality.OK||0,color:'#168A5B'},{label:'Atenção',value:quality.WARNING||0,color:'#F2B84B'},{label:'Críticos',value:quality.ERROR||0,color:'#D94B4B'}],quality.OK||0,'conformes');
    this.renderMethods(d.top_methods||[]); this.renderBalance(d.daily_load||[]); this.renderCycles(d.by_cycle||[]);
  },
  kpi(title,value,desc,tone) { return `<article class="pm11-exec-kpi ${tone}"><span>${title}</span><strong>${value}</strong><small>${desc}</small></article>`; },
  donutCard(eyebrow,title,donut,legend) { return `<article class="managerial-card managerial-donut-card"><div class="managerial-card-head"><div><span class="managerial-eyebrow">${eyebrow}</span><h3>${title}</h3></div><span class="managerial-status-dot is-green"></span></div><div class="managerial-donut-layout"><div id="${donut}" class="managerial-donut"></div><div id="${legend}" class="managerial-legend"></div></div></article>`; },
  renderDonut(donutId,legendId,data,center,label) { const total=data.reduce((s,x)=>s+x.value,0);let cursor=0;const stops=data.map(x=>{const start=cursor;cursor+=total?x.value/total*100:0;return `${x.color} ${start}% ${cursor}%`;});const donut=document.querySelector('#'+donutId);donut.style.background=total?`conic-gradient(${stops.join(',')})`:'#E2E8F0';donut.innerHTML=`<div><strong>${center}</strong><span>${label}</span></div>`;document.querySelector('#'+legendId).innerHTML=data.map(x=>`<div class="managerial-legend-row"><i style="background:${x.color}"></i><span>${x.label}</span><strong>${x.value}</strong><small>${total?Math.round(x.value/total*100):0}%</small></div>`).join(''); },
  renderMethods(data) { const UI=window.PM11.UI,total=data.reduce((s,x)=>s+Number(x.value||0),0),colors=['#72B900','#1D8ACB','#E59A2F','#7557C7','#0F766E'];document.querySelector('#pm11-methods').innerHTML=data.slice(0,6).map((x,i)=>{const pct=total?Math.round(x.value/total*100):0;return `<div class="managerial-method-row"><div><span>${UI.esc(x.label)}</span><strong>${x.value}</strong></div><div class="managerial-method-track"><i style="width:${pct}%;background:${colors[i%colors.length]}"></i></div><small>${pct}%</small></div>`;}).join('')||'<div class="managerial-empty">Sem métodos cadastrados.</div>'; },
  renderBalance(data) { const max=Math.max(1,...data.map(x=>Number(x.minutes||0)));document.querySelector('#pm11-management-balance').innerHTML=data.map((x,i)=>`<div class="pm11-management-bar" title="${x.date}: ${this.fmtMin(x.minutes)} · ${x.count} itens"><span>${this.fmtMin(x.minutes)}</span><i style="height:${Math.max(2,Number(x.minutes||0)/max*100)}%"></i><small>${this.dayLabel(i)}</small></div>`).join(''); },
  renderCycles(data) { const UI=window.PM11.UI,max=Math.max(1,...data.map(x=>Number(x.value||0)));document.querySelector('#pm11-cycle-bars').innerHTML=data.slice(0,10).map(x=>`<div class="pm11-cycle-row"><div><span>${UI.esc(x.label)}</span><strong>${x.value}</strong></div><div><i style="width:${x.value/max*100}%"></i></div></div>`).join('')||'<div class="managerial-empty">Sem ciclos cadastrados.</div>'; },
  dayLabel(index) { const names=['SEG','TER','QUA','QUI','SEX'];return `${names[index%5]}${Math.floor(index/5)+1}`; },
  fmtMin(value) { const min=Math.round(Number(value||0));return `${Math.floor(min/60)}h${String(min%60).padStart(2,'0')}`; }
};
