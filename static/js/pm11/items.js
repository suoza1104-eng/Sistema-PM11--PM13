window.PM11 = window.PM11 || {};

window.PM11.Items = {
  rows: [], plans: [], opts: { gpms: [], work_centers: [] }, selected: new Set(), copied: null, filters: { search: '', plan_id: '', status: '', route: '', gpm: '', work_center: '', condition: '', priority: '', row_color: '' },
  async render() { await this.load(); this.draw(); },
  async load() {
    const API = window.PM11.API;
    [this.rows, this.plans, this.opts] = await Promise.all([API.get('/api/items', this.filters), API.get('/api/plans'), API.get('/api/items/filter-options')]);
  },
  draw() {
    const UI = window.PM11.UI;
    const v = document.querySelector('#view');
    const fieldsHtml = `
      <div class="form-group"><label>Pesquisar</label><input class="control" id="it-f-search" placeholder="ID, equipamento ou descrição..." value="${UI.esc(this.filters.search)}"></div>
      <div class="form-group"><label>Centro de Trabalho</label><select class="control" id="it-f-wc"><option value="">Todos</option>${this.opts.work_centers.map(x => `<option ${x === this.filters.work_center ? 'selected' : ''}>${UI.esc(x)}</option>`).join('')}</select></div>
      <div class="form-group"><label>GPM</label><select class="control" id="it-f-gpm"><option value="">Todos</option>${this.opts.gpms.map(x => `<option ${x === this.filters.gpm ? 'selected' : ''}>${UI.esc(x)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Condição</label><select class="control" id="it-f-cond"><option value="">Todas</option>${[['Q', 'Qualquer'], ['P', 'Parado'], ['M', 'Manutenção'], ['F', 'Funcionando']].map(([c, n]) => `<option value="${c}" ${c === this.filters.condition ? 'selected' : ''}>${c} — ${n}</option>`).join('')}</select></div>
      <div class="form-group"><label>Prioridade</label><select class="control" id="it-f-pri"><option value="">Todas</option>${[0, 1, 2, 3, 4].map(n => `<option value="${n}" ${String(n) === String(this.filters.priority) ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
      <div class="form-group"><label>Plano</label><select class="control" id="it-f-plan"><option value="">Todos</option>${this.plans.map(p => `<option value="${p.id}" ${String(p.id) === String(this.filters.plan_id) ? 'selected' : ''}>${p.code}</option>`).join('')}</select></div>
      <div class="form-group"><label>Rota</label><input class="control" id="it-f-route" maxlength="4" value="${UI.esc(this.filters.route)}"></div>
      <div class="form-group"><label>Status</label><select class="control" id="it-f-status"><option value="">Todos</option><option value="ACTIVE" ${this.filters.status === 'ACTIVE' ? 'selected' : ''}>Ativos</option><option value="INACTIVE" ${this.filters.status === 'INACTIVE' ? 'selected' : ''}>Inativos</option></select></div>
      <div class="form-group"><label>Marcador</label><select class="control" id="it-f-color"><option value="">Todas</option>${UI.colorSelect(this.filters.row_color).replace('<option value="" selected>Sem cor</option>', '')}</select></div>
    `;
    const actionsHtml = `<button class="btn btn-outline" id="it-clear">Limpar</button><button class="btn btn-primary" id="it-filter">Filtrar</button>`;
    const tableHtml = `<table class="data-table sticky-head sticky-actions" id="items-table"><thead><tr><th><input type="checkbox" id="it-all"></th><th>ID</th><th>EQUIPAMENTO</th><th>GPM</th><th>C.T.</th><th>COND.</th><th>PRI.</th><th>PLANO</th><th>ROTA</th><th>DESCRIÇÃO</th><th>CAR.</th><th>t(min)</th><th>STATUS</th><th class="actions-col">AÇÕES</th></tr></thead><tbody>${this.body()}</tbody></table>`;

    v.innerHTML = UI.pageHead('Itens de Inspeção', 'Cada Item gera uma Ordem PM11 e herda a periodicidade do Plano vinculado.', `<button class="btn btn-primary" id="it-new">+ Novo Item</button>`) +
      UI.filterCard(fieldsHtml, actionsHtml, 'items-filter-card') +
      UI.selectionBar('it-selection', this.selected.size, `<button class="btn btn-xs btn-outline" data-bulk="plan">Atribuir Plano</button><button class="btn btn-xs btn-outline" data-bulk="edit">Editar Campos</button><button class="btn btn-xs btn-outline" data-bulk="model">Aplicar Modelo</button><button class="btn btn-xs btn-outline" data-bulk="save">Salvar como Modelo</button><button class="btn btn-xs btn-outline" data-bulk="clone">Clonar</button><button class="btn btn-xs btn-outline" data-bulk="color">Colorir</button><button class="btn btn-xs btn-danger" data-bulk="delete">Excluir</button>`) +
      UI.tableCard(`${this.rows.length} item(ns) encontrado(s)`, UI.tableTools('items'), tableHtml);
    this.bind();
  },
  body() {
    const UI = window.PM11.UI;
    if (!this.rows.length) return UI.tableEmpty(14);

    return this.rows.map(i => {
      const issues = [];
      if (i.validation_issues_json) {
        try {
          const parsed = typeof i.validation_issues_json === 'string' ? JSON.parse(i.validation_issues_json) : i.validation_issues_json;
          if (Array.isArray(parsed)) issues.push(...parsed);
        } catch(e) {}
      }

      const getIssue = field => issues.find(x => x.field === field);
      const cell = (field, value) => {
        const iss = getIssue(field);
        const errClass = iss ? (iss.severity === 'ERROR' ? 'cell-invalid-error' : 'cell-invalid-warning') : '';
        const title = iss ? `⚠️ ${iss.message}` : 'Clique duas vezes para editar';
        return `<td class="editable-cell ${errClass}" data-field="${field}" title="${title}">${value}</td>`;
      };

      const isError = issues.some(x => x.severity === 'ERROR');
      const isWarn = issues.length > 0 && !isError;
      const rowValidationClass = isError ? 'row-color-red' : (isWarn ? 'row-color-yellow' : '');

      const indicator = issues.length > 0
        ? `<span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" data-act="issue-info" style="cursor:pointer; margin-right:6px; font-size:14px;" title="Clique para ver o diagnóstico e sugestão de correção:\n${issues.map(x=>'• '+x.message).join('\n')}">${isError ? '⛔' : '⚠️'}</span>`
        : '';

      return `<tr data-id="${i.id}" class="${rowValidationClass} ${UI.rowClass(i.row_color, this.selected.has(i.id), this.copied?.id === i.id)}">
        <td><div style="display:flex; align-items:center; justify-content:center; gap:4px;">${indicator}<input class="it-check" type="checkbox" value="${i.id}" ${this.selected.has(i.id) ? 'checked' : ''}></div></td>
        <td><b>${i.legacy_identifier}</b></td>
        ${cell('equipment_code', UI.esc(i.equipment_code))}
        ${cell('gpm', UI.esc(i.gpm))}
        ${cell('work_center', UI.esc(i.work_center))}
        ${cell('condition_code', UI.esc(i.condition_code))}
        ${cell('priority', i.priority)}
        <td><button class="plan-pill ${i.plan_id ? '' : 'empty'}" data-plan="1">${i.plan_code ? UI.esc(i.plan_code) : 'Sem Plano'} <span>⌄</span></button></td>
        ${cell('route', UI.esc(i.route))}
        ${cell('description', UI.esc(i.description))}
        <td>${i.characteristic_count || 0}</td>
        ${cell('inspection_minutes', i.inspection_minutes)}
        ${cell('status', UI.badgeStatus(i.status))}
        <td><div class="row-actions"><button class="btn btn-xs btn-outline" data-act="edit">Editar</button><button class="btn btn-xs btn-outline" data-act="clone">Clonar</button><button class="btn btn-xs btn-outline" data-act="save">Salvar modelo</button><button class="btn btn-xs btn-danger" data-act="delete">Excluir</button></div></td>
      </tr>`;
    }).join('');
  },
  openIssueModal(row, issues) {
    const UI = window.PM11.UI;
    const issuesHtml = (issues || []).map(iss => `
      <div style="padding:12px; margin-bottom:10px; border-radius:6px; background:${iss.severity === 'ERROR' ? '#FEE2E2' : '#FEF3C7'}; border:1px solid ${iss.severity === 'ERROR' ? '#EF4444' : '#F59E0B'};">
        <strong style="color:${iss.severity === 'ERROR' ? '#991B1B' : '#B45309'}; font-size:13px;">${iss.severity === 'ERROR' ? '⛔ Erro Crítico' : '⚠️ Alerta de Incompatibilidade'}</strong>
        <p style="margin:6px 0 0; font-size:13px; color:#1F2937;">${UI.esc(iss.message)}</p>
      </div>
    `).join('');

    UI.modal('Diagnóstico do Item de Inspeção e Sugestão', `
      <div style="padding:4px;">
        <h4 style="margin:0 0 12px; font-size:14px; font-weight:700; color:#111;">Diagnóstico para o Item #${row.legacy_identifier} — “${UI.esc(row.description)}”:</h4>
        ${issuesHtml}
        <div class="helpbox" style="margin-top:14px;">
          💡 Clique no botão <b>Corrigir / Editar</b> abaixo para abrir a janela de edição do Item.
        </div>
      </div>
    `, {
      saveText: 'Corrigir / Editar',
      onSave: async () => {
        this.edit(row.id);
      }
    });
  },
  bind() {
    const UI = window.PM11.UI, API = window.PM11.API;
    document.querySelector('#it-new').onclick = () => this.edit();
    document.querySelector('#it-filter').onclick = async () => {
      this.filters = { search: itval('it-f-search'), work_center: itval('it-f-wc'), gpm: itval('it-f-gpm'), condition: itval('it-f-cond'), priority: itval('it-f-pri'), plan_id: itval('it-f-plan'), route: itval('it-f-route'), status: itval('it-f-status'), row_color: itval('it-f-color') };
      await this.render();
    };
    document.querySelector('#it-clear').onclick = async () => {
      this.filters = { search: '', plan_id: '', status: '', route: '', gpm: '', work_center: '', condition: '', priority: '', row_color: '' };
      await this.render();
    };
    document.querySelector('#it-all').onchange = e => {
      this.selected = new Set(e.target.checked ? this.rows.map(x => x.id) : []);
      this.draw();
    };
    document.querySelectorAll('.it-check').forEach(c => c.onchange = e => {
      const id = Number(e.target.value);
      e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      this.draw();
    });
    document.querySelectorAll('#items-table tbody tr[data-id]').forEach(tr => {
      const id = Number(tr.dataset.id), row = this.rows.find(x => x.id === id);
      const issueBtn = tr.querySelector('[data-act="issue-info"]');
      if (issueBtn) {
        issueBtn.onclick = e => {
          e.stopPropagation();
          if (row) {
            const issues = [];
            if (row.validation_issues_json) {
              try {
                const parsed = typeof row.validation_issues_json === 'string' ? JSON.parse(row.validation_issues_json) : row.validation_issues_json;
                if (Array.isArray(parsed)) issues.push(...parsed);
              } catch(err) {}
            }
            this.openIssueModal(row, issues);
          }
        };
      }
      tr.querySelector('[data-plan]').onclick = e => {
        e.stopPropagation();
        const b = e.currentTarget;
        UI.floatingPicker(b, {
          rows: [{ id: '', code: 'Sem Plano', description: 'Remover associação' }, ...this.plans], valueKey: 'id', primary: r => r.code, secondary: r => r.description, searchPlaceholder: 'Código ou descrição do Plano...', onSelect: async p => {
            await API.put('/api/items/' + id, { plan_id: p.id || null });
            UI.toast('Plano atualizado.');
            await this.render();
          }
        });
      };
      tr.querySelectorAll('[data-act]').forEach(b => b.onclick = e => {
        if (b.dataset.act === 'issue-info') return;
        e.stopPropagation();
        ({ edit: () => this.edit(id), clone: () => this.clone([id]), save: () => this.saveModel(id), delete: () => this.del([id]) }[b.dataset.act])();
      });
      tr.querySelectorAll('td.editable-cell').forEach(td => td.ondblclick = e => { e.stopPropagation(); this.inlineEdit(td, id, td.dataset.field); });
      tr.onclick = e => {
        if (e.target.closest('button,input,select,td.editable-cell,.row-issue-indicator')) return;
        this.selected.has(id) ? this.selected.delete(id) : this.selected.add(id);
        this.draw();
      };
    });
    document.querySelectorAll('[data-bulk]').forEach(b => b.onclick = () => ({ plan: () => this.assignPlan(), edit: () => this.bulkEdit(), model: () => this.applyModel(), save: () => this.bulkSaveModel(), clone: () => this.clone([...this.selected]), color: () => this.bulkColor(), delete: () => this.del([...this.selected]) }[b.dataset.bulk])());
    UI.bindTableTools('items-table');
    document.onkeydown = e => this.keys(e);
  },
  inlineEdit(cell, id, field) {
    if (cell.classList.contains('cell-editing')) return;
    const UI = window.PM11.UI, API = window.PM11.API, row = this.rows.find(x => x.id === id);
    if (!row) return;
    const originalHtml = cell.innerHTML, original = row[field] ?? '';
    const optionMap = { gpm: this.opts.gpms, work_center: this.opts.work_centers, condition_code: [['Q', 'Qualquer'], ['P', 'Parado'], ['M', 'Manutenção'], ['F', 'Funcionando']], priority: [0, 1, 2, 3, 4], status: [['ACTIVE', 'ATIVO'], ['INACTIVE', 'INATIVO']] };
    let editor;
    if (optionMap[field]) {
      editor = document.createElement('select');
      const options = optionMap[field].map(x => Array.isArray(x) ? x : [x, x]);
      if (original !== '' && !options.some(x => String(x[0]) === String(original))) options.unshift([original, original]);
      editor.innerHTML = options.map(([value, label]) => `<option value="${UI.esc(value)}">${UI.esc(label)}</option>`).join('');
    } else {
      editor = document.createElement('input'); editor.type = field === 'inspection_minutes' ? 'number' : 'text';
      if (field === 'inspection_minutes') editor.step = '0.1'; if (field === 'description') editor.maxLength = 35; if (field === 'route') editor.maxLength = 4;
    }
    editor.className = 'table-inline-input'; editor.value = original; cell.classList.add('cell-editing'); cell.innerHTML = ''; cell.appendChild(editor); editor.focus(); if (editor.select) editor.select();
    let done = false;
    const cancel = () => { if (done) return; done = true; cell.classList.remove('cell-editing'); cell.innerHTML = originalHtml; };
    const save = async () => { if (done) return; let value = editor.value.trim(); if (field === 'priority') value = Number(value); if (field === 'inspection_minutes') value = Number(value || 0); if (String(value) === String(original)) return cancel(); done = true; editor.disabled = true; try { await API.put('/api/items/' + id, { ...row, [field]: value }); UI.toast('Item atualizado.'); await this.render(); } catch (e) { done = false; editor.disabled = false; editor.focus(); UI.toast(e.message, 'error'); } };
    editor.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); cancel(); } if (e.key === 'Enter') { e.preventDefault(); save(); } };
    editor.onblur = save; if (editor.tagName === 'SELECT') editor.onchange = save;
  },
  edit(id = null) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const i = id ? this.rows.find(x => x.id === id) : { condition_code: 'Q', priority: 0, status: 'ACTIVE' };
    const p = this.plans.find(x => x.id === i.plan_id);
    UI.modal(id ? 'Editar Item PM11' : 'Novo Item PM11', `
      <div class="form-section">
        <div class="form-section-title">Vínculo e Localização</div>
        <div class="form-grid modern">
          <div class="fg-4"><label>Equipamento SAP</label><input class="control" id="ie-eq" value="${UI.esc(i.equipment_code || '')}" placeholder="Ex.: 10350434"></div>
          <div class="fg-2"><label>GPM</label><input class="control" id="ie-gpm" value="${UI.esc(i.gpm || '')}" placeholder="Ex.: 041"></div>
          <div class="fg-3"><label>Centro de Trabalho</label><input class="control" id="ie-wc" value="${UI.esc(i.work_center || '')}" placeholder="Ex.: R55E-041"></div>
          <div class="fg-3"><label>Plano de Inspeção</label><button class="control picker-control" id="ie-plan" data-value="${i.plan_id || ''}"><span>${p ? `${p.code} — ${UI.esc(p.description)}` : 'Pesquisar / selecionar Plano...'}</span><b>⌄</b></button></div>
          <div class="fg-2"><label>Condição</label><select class="control" id="ie-cond">${[['Q', 'Q — Qualquer'], ['P', 'P — Parado'], ['M', 'M — Manutenção'], ['F', 'F — Funcionando']].map(([c, n]) => `<option value="${c}" ${i.condition_code === c ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
          <div class="fg-2"><label>Prioridade</label><select class="control" id="ie-pri">${[0, 1, 2, 3, 4].map(n => `<option ${i.priority === n ? 'selected' : ''}>${n}</option>`).join('')}</select></div>
          <div class="fg-2"><label>Identificador</label><input class="control derived-field" readonly value="${i.legacy_identifier || 'Automático'}"></div>
          <div class="fg-2"><label>Rota (4)</label><input class="control" id="ie-route" maxlength="4" value="${UI.esc(i.route || '')}" placeholder="Ex.: 1500"></div>
          <div class="fg-2"><label>t(min)</label><input class="control" id="ie-time" type="number" step="0.1" min="0" value="${i.inspection_minutes ?? 0}"></div>
          <div class="fg-2"><label>Status</label><select class="control" id="ie-status"><option value="ACTIVE" ${i.status !== 'INACTIVE' ? 'selected' : ''}>ATIVO</option><option value="INACTIVE" ${i.status === 'INACTIVE' ? 'selected' : ''}>INATIVO</option></select></div>
        </div>
      </div>
      <div class="form-section">
        <div class="form-section-title">Descrição da Ordem de Inspeção</div>
        <div class="form-grid modern">
          <div class="fg-9"><label>Descrição <span class="char-counter" id="ie-count">${(i.description || '').length}/35</span></label><input class="control" id="ie-desc" maxlength="35" value="${UI.esc(i.description || '')}" placeholder="Ex.: REC3 MONOVIA"></div>
          <div class="fg-3"><label>Criticidade</label><input class="control" id="ie-crit" value="${UI.esc(i.criticality || '')}" placeholder="Ex.: A, B..."></div>
        </div>
      </div>
    `, {
      wide: true, onOpen: () => {
        const b = document.querySelector('#ie-plan');
        b.onclick = () => UI.floatingPicker(b, {
          rows: this.plans, valueKey: 'id', primary: r => r.code, secondary: r => r.description, searchPlaceholder: 'Código ou descrição...', onSelect: p => {
            b.dataset.value = p.id;
            b.querySelector('span').textContent = `${p.code} — ${p.description}`;
          }
        });
        document.querySelector('#ie-desc').oninput = e => document.querySelector('#ie-count').textContent = e.target.value.length + '/35';
      }, onSave: async () => {
        const d = { project_id: App.projectId, plan_id: Number(document.querySelector('#ie-plan').dataset.value) || null, equipment_code: itval('ie-eq'), gpm: itval('ie-gpm'), work_center: itval('ie-wc'), condition_code: itval('ie-cond'), priority: Number(itval('ie-pri')), route: itval('ie-route'), inspection_minutes: Number(itval('ie-time') || 0), description: itval('ie-desc'), criticality: itval('ie-crit'), status: itval('ie-status') };
        id ? await API.put('/api/items/' + id, d) : await API.post('/api/items', d);
        UI.toast('Item salvo.');
        await this.render();
      }
    });
  },
  async assignPlan() {
    const API = window.PM11.API, App = window.PM11.App;
    if (!this.selected.size) return;
    const choices = this.plans.map(x => `${x.id} — ${x.code} — ${x.description}`).join('\n');
    const p = Number(prompt('ID do Plano a atribuir:\n' + choices));
    if (!p) return;
    await API.post('/api/items/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: { plan_id: p } });
    this.selected.clear();
    await this.render();
  },
  bulkEdit() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!this.selected.size) return;
    UI.modal('Editar Itens em Massa', `<div class="form-section"><div class="form-section-title">Marque somente os campos que deseja substituir</div><div class="form-grid modern"><div class="fg-3"><label><input type="checkbox" id="bi-cond-on"> Condição</label><select class="control" id="bi-cond">${[['Q', 'Qualquer'], ['P', 'Parado'], ['M', 'Manutenção'], ['F', 'Funcionando']].map(([c, n]) => `<option value="${c}">${c} — ${n}</option>`).join('')}</select></div><div class="fg-3"><label><input type="checkbox" id="bi-pri-on"> Prioridade</label><select class="control" id="bi-pri">${[0, 1, 2, 3, 4].map(n => `<option>${n}</option>`).join('')}</select></div><div class="fg-3"><label><input type="checkbox" id="bi-gpm-on"> GPM</label><input class="control" id="bi-gpm"></div><div class="fg-3"><label><input type="checkbox" id="bi-wc-on"> C.T.</label><input class="control" id="bi-wc"></div><div class="fg-3"><label><input type="checkbox" id="bi-time-on"> t(min)</label><input class="control" id="bi-time" type="number"></div><div class="fg-3"><label><input type="checkbox" id="bi-status-on"> Status</label><select class="control" id="bi-status"><option value="ACTIVE">ATIVO</option><option value="INACTIVE">INATIVO</option></select></div></div></div>`, {
      onSave: async () => {
        const u = {};
        for (const [on, key, id, conv] of [['bi-cond-on', 'condition_code', 'bi-cond'], ['bi-pri-on', 'priority', 'bi-pri', Number], ['bi-gpm-on', 'gpm', 'bi-gpm'], ['bi-wc-on', 'work_center', 'bi-wc'], ['bi-time-on', 'inspection_minutes', 'bi-time', Number], ['bi-status-on', 'status', 'bi-status']]) if (document.querySelector('#' + on).checked) u[key] = conv ? conv(itval(id)) : itval(id);
        await API.post('/api/items/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: u });
        this.selected.clear();
        await this.render();
      }
    });
  },
  async clone(ids) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!ids.length) return;
    const withChars = confirm('Clonar também as Características de Controle?');
    for (const id of ids) await API.post('/api/items/clone', { project_id: App.projectId, item_id: id, include_characteristics: withChars });
    UI.toast(`${ids.length} Item(ns) clonado(s).`);
    this.selected.clear();
    await this.render();
  },
  async saveModel(id) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const name = prompt('Nome do modelo do Item:');
    if (!name) return;
    await API.post('/api/items/save-template', { project_id: App.projectId, item_id: id, name, category: 'ITENS' });
    UI.toast('Modelo de Item salvo na Biblioteca.');
  },
  async bulkSaveModel() {
    const UI = window.PM11.UI;
    if (this.selected.size !== 1) return UI.toast('Selecione exatamente um Item para salvar como modelo.', 'warn');
    return this.saveModel([...this.selected][0]);
  },
  async applyModel() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!this.selected.size) return;
    const t = await API.get('/api/templates/characteristics');
    if (!t.length) return UI.toast('Não existem padrões de Características.', 'warn');
    const id = Number(prompt('ID do padrão:\n' + t.map(x => `${x.id} — ${x.name} (${x.row_count})`).join('\n')));
    if (!id) return;
    const policy = (prompt('Política: IGNORE, REPLACE ou ADD', 'IGNORE') || 'IGNORE').toUpperCase();
    await API.post('/api/templates/characteristics/apply', { project_id: App.projectId, template_id: id, item_ids: [...this.selected], policy });
    UI.toast('Padrão aplicado.');
    this.selected.clear();
    await this.render();
  },
  bulkColor() {
    const API = window.PM11.API, App = window.PM11.App;
    const c = prompt('Cor: yellow, green, blue, red, purple ou vazio', 'yellow');
    if (c === null) return;
    API.post('/api/items/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: { row_color: c } }).then(() => {
      this.selected.clear();
      this.render();
    });
  },
  async del(ids) {
    const API = window.PM11.API, App = window.PM11.App;
    if (!ids.length || !confirm(`Excluir ${ids.length} Item(ns) e suas Características?`)) return;
    await API.post('/api/items/bulk-delete', { project_id: App.projectId, ids });
    ids.forEach(x => this.selected.delete(x));
    await this.render();
  },
  keys(e) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (window.currentMode && window.currentMode !== 'PM11') return;
    const tag = document.activeElement?.tagName;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
    if (e.key === 'Escape') {
      this.copied = null;
      this.selected.clear();
      this.draw();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c' && this.selected.size === 1) {
      e.preventDefault();
      this.copied = this.rows.find(x => x.id === [...this.selected][0]);
      this.draw();
      UI.toast('Linha copiada. Selecione um ou vários destinos e pressione Ctrl+V.');
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v' && this.copied && this.selected.size) {
      e.preventDefault();
      const u = { plan_id: this.copied.plan_id, equipment_code: this.copied.equipment_code, gpm: this.copied.gpm, work_center: this.copied.work_center, condition_code: this.copied.condition_code, priority: this.copied.priority, route: this.copied.route, description: this.copied.description, inspection_minutes: this.copied.inspection_minutes, criticality: this.copied.criticality, status: this.copied.status };
      window.PM11.API.post('/api/items/bulk-update', { project_id: window.PM11.App.projectId, ids: [...this.selected].filter(x => x !== this.copied.id), updates: u }).then(() => {
        window.PM11.UI.toast('Linha colada nos destinos selecionados.');
        this.render();
      });
    }
  }
};
function itval(id) { return document.querySelector('#' + id)?.value ?? ''; }
