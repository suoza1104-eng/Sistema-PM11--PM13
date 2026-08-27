window.PM11 = window.PM11 || {};

window.PM11.Plans = {
  rows: [],
  catalogs: { cycles: [], centers: [], processes: [], types: [], lines: [], subareas: [] },
  selected: new Set(),
  filters: { search: '', cycle_code: '', status: '', row_color: '' },
  async render() {
    await this.load();
    this.draw();
  },
  async load() {
    const API = window.PM11.API;
    this.catalogs = await API.get('/api/catalogs');
    this.rows = await API.get('/api/plans', this.filters);
  },
  draw() {
    const UI = window.PM11.UI;
    const project = window.PM11.App.projects.find(x => x.id === window.PM11.App.projectId) || {};
    const v = document.querySelector('#view');
    const fieldsHtml = `
      <div class="form-group"><label>Pesquisar</label><input class="control" id="pl-f-search" placeholder="Código ou descrição..." value="${UI.esc(this.filters.search)}"></div>
      <div class="form-group"><label>Ciclo</label><select class="control" id="pl-f-cycle"><option value="">Todos</option>${this.catalogs.cycles.map(c => `<option value="${c.code}" ${this.filters.cycle_code === c.code ? 'selected' : ''}>${c.code} — ${UI.esc(c.text_cycle)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Status</label><select class="control" id="pl-f-status"><option value="">Todos</option><option value="ACTIVE" ${this.filters.status === 'ACTIVE' ? 'selected' : ''}>Ativos</option><option value="INACTIVE" ${this.filters.status === 'INACTIVE' ? 'selected' : ''}>Inativos</option></select></div>
      <div class="form-group"><label>Marcador de cor</label><select class="control" id="pl-f-color"><option value="">Todas as cores</option>${UI.colorSelect(this.filters.row_color).replace('<option value="" selected>Sem cor</option>', '')}</select></div>
    `;
    const actionsHtml = `<button class="btn btn-outline" id="pl-clear">Limpar</button><button class="btn btn-primary" id="pl-filter">Filtrar</button>`;
    const tableHtml = `<table class="data-table sticky-head sticky-actions" id="plans-table"><thead><tr><th class="check-col"><input type="checkbox" id="pl-all"></th><th>CÓDIGO</th><th>DESCRIÇÃO</th><th>CAR.</th><th>CICLO</th><th>UNID.</th><th>TEXTO CICLO</th><th>HORIZ.</th><th>OFFSET</th><th>DIA DA SEMANA</th><th>DATA INICIAL</th><th>STATUS</th><th class="actions-col">AÇÕES</th></tr></thead><tbody>${this.body()}</tbody></table>`;

    v.innerHTML = UI.pageHead('Planos PM11', 'Cadastre e gerencie Planos de Inspeção com o mesmo fluxo operacional do PM13.', `<button class="btn btn-primary" id="pl-new">+ Novo Plano</button>`) +
      UI.filterCard(fieldsHtml, actionsHtml, 'plans-filter-card') +
      UI.selectionBar('pl-selection', this.selected.size, `<button class="btn btn-xs btn-outline" data-bulk="edit">Editar em massa</button><button class="btn btn-xs btn-outline" data-bulk="model">Salvar como modelo</button><button class="btn btn-xs btn-outline" data-bulk="color">Colorir</button><button class="btn btn-xs btn-danger" data-bulk="delete">Excluir</button>`) +
      UI.tableCard(`${this.rows.length} plano(s) encontrado(s)`, UI.tableTools('plans'), tableHtml);
    const anchor = `<div class="card" style="margin-bottom:16px"><div class="card-body"><div class="form-group" style="max-width:340px"><label>Data de Início da Programação</label><input class="control" id="pl-anchor-date" type="date" value="${UI.esc(project.balance_anchor_date || '')}"></div></div></div>`;
    v.insertAdjacentHTML('afterbegin', anchor);
    this.bind();
  },
  sapCycles: [
    'DIÁRIA', 'DOIS DIAS', '3 DIAS', '1 SEMANA', 'DUAS SEMANAS', '3 SEMANAS',
    '4 SEMANAS = 1M', '6 SEMANAS', '9 SEMANAS = 2M', 'TRIMESTRAL = 3M',
    '17 SEMANAS = 4M', 'SEMESTRAL = 26S', '9 MESES = 39S', 'ANUAL',
    '18 MESES = 78S', '2 ANOS', '3 ANOS', '4 ANOS'
  ],
  body() {
    const UI = window.PM11.UI;
    if (!this.rows.length) return UI.tableEmpty(13);
    const validTexts = new Set(this.sapCycles.map(x => x.toUpperCase()));
    const cell = (field, value, extraClass='', title='Clique duas vezes para editar') => `<td class="editable-cell ${extraClass}" data-field="${field}" title="${title}">${value}</td>`;
    return this.rows.map(p => {
      const txt = (p.text_cycle || '').trim();
      const isValid = !txt || validTexts.has(txt.toUpperCase());
      const textCellClass = isValid ? '' : 'cell-invalid-cycle';
      const textCellTitle = isValid ? 'Clique duas vezes para editar' : '⚠️ Texto do Ciclo incompatível com a tabela padrão SAP. Clique duas vezes para corrigir!';
      return `<tr class="${UI.rowClass(p.row_color, this.selected.has(p.id))}" data-id="${p.id}">
        <td><input class="pl-check" type="checkbox" value="${p.id}" ${this.selected.has(p.id) ? 'checked' : ''}></td>
        ${cell('code', `<b>${UI.esc(p.code)}</b>`)}
        ${cell('description', UI.esc(p.description))}
        <td>${p.char_count}</td>
        ${cell('cycle_code', UI.esc(p.cycle_code || p.cycle_value || ''))}
        <td>${UI.esc(p.unit || '')}</td>
        ${cell('text_cycle', UI.esc(txt || '—'), textCellClass, textCellTitle)}
        <td>${p.horizon ?? ''}%</td>
        ${cell('offset_days', UI.esc(p.offset_days ?? '—'))}
        <td style="font-weight:600; color:#0F766E;">${UI.esc(p.day_of_week_label || '—')}</td>
        <td style="font-weight:600; color:#0284C7;">${UI.esc(p.calculated_start_date || '—')}</td>
        ${cell('status', UI.badgeStatus(p.status))}
        <td><div class="row-actions"><button class="btn btn-xs btn-outline" data-act="edit">Editar</button><button class="btn btn-xs btn-outline" data-act="clone">Duplicar</button><button class="btn btn-xs btn-outline" data-act="model">Salvar modelo</button><button class="btn btn-xs btn-outline" data-act="apply">Aplicar modelo</button><button class="btn btn-xs btn-danger" data-act="delete">Excluir</button></div></td>
      </tr>`;
    }).join('');
  },
  bind() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    document.querySelector('#pl-anchor-date').onchange = async e => { await API.post(`/api/projects/${App.projectId}/anchor-date`, { balance_anchor_date: e.target.value }); const p=App.projects.find(x=>x.id===App.projectId); if(p)p.balance_anchor_date=e.target.value; await this.render(); UI.toast('Data de início atualizada.'); };
    document.querySelector('#pl-new').onclick = () => this.edit();
    document.querySelector('#pl-filter').onclick = async () => {
      this.filters = { search: document.querySelector('#pl-f-search').value, cycle_code: document.querySelector('#pl-f-cycle').value, status: document.querySelector('#pl-f-status').value, row_color: document.querySelector('#pl-f-color').value };
      await this.render();
    };
    document.querySelector('#pl-clear').onclick = async () => {
      this.filters = { search: '', cycle_code: '', status: '', row_color: '' };
      await this.render();
    };
    document.querySelector('#pl-all').onchange = e => {
      this.selected = new Set(e.target.checked ? this.rows.map(x => x.id) : []);
      this.draw();
    };
    document.querySelectorAll('.pl-check').forEach(c => c.onchange = e => {
      const id = Number(e.target.value);
      e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      this.draw();
    });
    document.querySelectorAll('#plans-table tbody tr[data-id]').forEach(tr => {
      const id = Number(tr.dataset.id);
      tr.querySelectorAll('[data-act]').forEach(b => b.onclick = e => {
        e.stopPropagation();
        ({ edit: () => this.edit(id), clone: () => this.clone(id), model: () => this.saveModel(id), apply: () => this.applyModel(id), delete: () => this.del([id]) }[b.dataset.act])();
      });
      tr.querySelectorAll('td.editable-cell').forEach(td => td.ondblclick = e => {
        e.stopPropagation();
        td.dataset.field === 'code' ? this.edit(id) : this.inlineEdit(td, id, td.dataset.field);
      });
    });
    document.querySelectorAll('[data-bulk]').forEach(b => b.onclick = () => ({ edit: () => this.bulkEdit(), model: () => this.bulkSaveModel(), color: () => this.bulkColor(), delete: () => this.del([...this.selected]) }[b.dataset.bulk])());
    UI.bindTableTools('plans-table');
  },
  inlineEdit(cell, id, field) {
    if (cell.classList.contains('cell-editing')) return;
    const UI = window.PM11.UI, API = window.PM11.API, row = this.rows.find(x => x.id === id);
    if (!row) return;
    const originalHtml = cell.innerHTML, original = row[field] ?? '';
    const editor = document.createElement(['cycle_code', 'status', 'text_cycle'].includes(field) ? 'select' : 'input');
    if (field === 'offset_days') { editor.type = 'number'; editor.min = '1'; }
    if (field === 'cycle_code') editor.innerHTML = this.catalogs.cycles.map(c => `<option value="${UI.esc(c.code)}">${UI.esc(c.code)} — ${UI.esc(c.text_cycle)}</option>`).join('');
    if (field === 'text_cycle') editor.innerHTML = '<option value="">— Selecionar Ciclo SAP —</option>' + this.sapCycles.map(t => `<option value="${UI.esc(t)}" ${t.toUpperCase() === String(original).toUpperCase() ? 'selected' : ''}>${UI.esc(t)}</option>`).join('');
    if (field === 'status') editor.innerHTML = '<option value="ACTIVE">ATIVO</option><option value="INACTIVE">INATIVO</option>';
    editor.className = 'table-inline-input'; editor.value = original; cell.classList.add('cell-editing'); cell.innerHTML = ''; cell.appendChild(editor); editor.focus(); if (editor.select) editor.select();
    let done = false;
    const cancel = () => { if (done) return; done = true; cell.classList.remove('cell-editing'); cell.innerHTML = originalHtml; };
    const save = async () => { if (done) return; const value = editor.value.trim(); if (String(value) === String(original)) return cancel(); done = true; editor.disabled = true; try { await API.put('/api/plans/' + id, { ...row, [field]: field === 'code' ? value.toUpperCase() : value }); UI.toast('Plano atualizado.'); await this.render(); } catch (e) { done = false; editor.disabled = false; editor.focus(); UI.toast(e.message, 'error'); } };
    editor.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault(); cancel(); } if (e.key === 'Enter') { e.preventDefault(); save(); } };
    editor.onblur = save; if (editor.tagName === 'SELECT') editor.onchange = save;
  },
  planForm(p = {}) {
    const UI = window.PM11.UI;
    const cy = this.catalogs.cycles.find(x => x.code === (p.cycle_code || ''));
    return `<div class="form-section"><div class="form-section-title">Composição do Código do Plano</div><div class="form-grid modern"><div class="fg-2"><label>Centro (1)</label><select class="control" id="pe-center">${this.catalogs.centers.map(x => `<option value="${x.code}" ${(p.center_code || 'U') === x.code ? 'selected' : ''}>${x.code} — ${UI.esc(x.description)}</option>`).join('')}</select></div><div class="fg-2"><label>Processo (1)</label><select class="control" id="pe-process">${this.catalogs.processes.map(x => `<option value="${x.code}" ${(p.process_code || 'R') === x.code ? 'selected' : ''}>${x.code} — ${UI.esc(x.description)}</option>`).join('')}</select></div><div class="fg-2"><label>Tipo (1)</label><select class="control" id="pe-type">${this.catalogs.types.map(x => `<option value="${x.code}" ${(p.type_code || 'I') === x.code ? 'selected' : ''}>${x.code} — ${UI.esc(x.description)}</option>`).join('')}</select></div><div class="fg-2"><label>Linha (3)</label><button class="control picker-control" id="pe-line" data-value="${UI.esc(p.line_code || '')}"><span>${UI.esc(p.line_code || 'Pesquisar / criar...')}</span><b>⌄</b></button></div><div class="fg-2"><label>Subárea (3)</label><button class="control picker-control" id="pe-sub" data-value="${UI.esc(p.subarea_code || '')}"><span>${UI.esc(p.subarea_code || 'Pesquisar / criar...')}</span><b>⌄</b></button></div><div class="fg-2"><label>Sufixo (3)</label><input class="control" id="pe-suffix" maxlength="3" value="${UI.esc(p.suffix || '001')}"></div><div class="fg-12"><div class="code-preview"><div><small>CÓDIGO GERADO</small><div class="code" id="pe-code">${UI.esc(p.code || '')}</div></div><small>X X X XXX XXX XXX</small></div></div></div></div><div class="form-section"><div class="form-section-title">Descrição e Periodicidade</div><div class="form-grid modern"><div class="fg-8"><label>Descrição do Plano <span class="char-counter" id="pe-count">${(p.description || '').length}</span></label><input class="control" id="pe-desc" value="${UI.esc(p.description || '')}"></div><div class="fg-4"><label>Periodicidade</label><select class="control" id="pe-cycle"><option value="">— selecione —</option>${this.catalogs.cycles.map(x => `<option value="${x.code}" ${(p.cycle_code || '') === x.code ? 'selected' : ''}>${x.code} — ${UI.esc(x.text_cycle)}</option>`).join('')}</select></div><div class="fg-2"><label>Ciclo</label><input class="control derived-field" id="pe-cv" readonly value="${p.cycle_value ?? cy?.cycle_value ?? ''}"></div><div class="fg-2"><label>Unidade</label><input class="control derived-field" id="pe-unit" readonly value="${UI.esc(p.unit || cy?.unit || '')}"></div><div class="fg-3"><label>Horizonte</label><input class="control derived-field" id="pe-horizon" readonly value="${p.horizon ?? cy?.horizon ?? ''}"></div><div class="fg-3"><label>Contador</label><input class="control" id="pe-counter" value="${UI.esc(p.counter || '')}"></div><div class="fg-2"><label>Status</label><select class="control" id="pe-status"><option value="ACTIVE" ${p.status !== 'INACTIVE' ? 'selected' : ''}>ATIVO</option><option value="INACTIVE" ${p.status === 'INACTIVE' ? 'selected' : ''}>INATIVO</option></select></div><div class="fg-12"><label>Texto do Ciclo</label><input class="control derived-field" id="pe-text" readonly value="${UI.esc(p.text_cycle || cy?.text_cycle || '')}"></div></div></div><div class="helpbox">Linha e Subárea são catálogos dinâmicos: digite um novo código de 3 caracteres e pressione Enter para cadastrá-lo e já selecionar.</div>`;
  },
  edit(id = null) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const p = id ? this.rows.find(x => x.id === id) : {};
    UI.modal(id ? 'Editar Plano PM11' : 'Novo Plano PM11', this.planForm(p), {
      wide: true,
      onOpen: () => {
        const oldCounter = document.querySelector('#pe-counter');
        if (oldCounter) { oldCounter.id = 'pe-offset'; oldCounter.type = 'number'; oldCounter.min = '1'; oldCounter.value = p.offset_days ?? ''; oldCounter.closest('div').querySelector('label').textContent = 'Offset'; }
        const code = () => {
          const v = ['pe-center', 'pe-process', 'pe-type'].map(x => document.querySelector('#' + x).value).join('') + document.querySelector('#pe-line').dataset.value + document.querySelector('#pe-sub').dataset.value + document.querySelector('#pe-suffix').value.toUpperCase();
          document.querySelector('#pe-code').textContent = v;
        };
        ['pe-center', 'pe-process', 'pe-type', 'pe-suffix'].forEach(x => document.querySelector('#' + x).oninput = code);
        const desc = document.querySelector('#pe-desc');
        desc.oninput = () => {
          const c = document.querySelector('#pe-count');
          c.textContent = desc.value.length;
          c.classList.toggle('over', desc.value.length > 40);
        };
        const cycle = document.querySelector('#pe-cycle');
        cycle.onchange = () => {
          const x = this.catalogs.cycles.find(c => c.code === cycle.value) || {};
          document.querySelector('#pe-cv').value = x.cycle_value ?? '';
          document.querySelector('#pe-unit').value = x.unit || '';
          document.querySelector('#pe-horizon').value = x.horizon ?? '';
          document.querySelector('#pe-text').value = x.text_cycle || '';
        };
        const bindCat = (id, kind, rows) => {
          const b = document.querySelector('#' + id);
          b.onclick = () => UI.floatingPicker(b, {
            rows, valueKey: 'code', primary: r => `${r.code} — ${r.description || ''}`, secondary: r => kind === 'lines' ? 'Linha de Produção' : 'Subárea', searchPlaceholder: 'Código ou descrição...', allowCreate: async code => {
              if (code.length !== 3) throw new Error('Digite exatamente 3 caracteres.');
              const description = prompt('Descrição para ' + code + ':', '') || '';
              await API.post('/api/catalogs/upsert', { kind, code, description });
              this.catalogs = await API.get('/api/catalogs');
              return { code, description };
            }, onSelect: r => {
              b.dataset.value = r.code;
              b.querySelector('span').textContent = `${r.code}${r.description ? ' — ' + r.description : ''}`;
              code();
            }
          });
        };
        bindCat('pe-line', 'lines', this.catalogs.lines);
        bindCat('pe-sub', 'subareas', this.catalogs.subareas);
        code();
      },
      onSave: async () => {
        const d = { center_code: document.querySelector('#pe-center').value, process_code: document.querySelector('#pe-process').value, type_code: document.querySelector('#pe-type').value, line_code: document.querySelector('#pe-line').dataset.value, subarea_code: document.querySelector('#pe-sub').dataset.value, suffix: document.querySelector('#pe-suffix').value.toUpperCase(), description: document.querySelector('#pe-desc').value, cycle_code: document.querySelector('#pe-cycle').value, offset_days: document.querySelector('#pe-offset').value || null, status: document.querySelector('#pe-status').value, project_id: App.projectId };
        if (!d.line_code || !d.subarea_code || d.suffix.length !== 3) throw new Error('Preencha Linha, Subárea e Sufixo com 3 caracteres.');
        id ? await API.put('/api/plans/' + id, d) : await API.post('/api/plans', d);
        UI.toast('Plano salvo.');
        await this.render();
      }
    });
  },
  async clone(id) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const incl = confirm('Duplicar também os Itens e todas as Características do Plano?');
    const r = await API.post('/api/plans/clone', { project_id: App.projectId, plan_id: id, include_children: incl });
    UI.toast(`Plano duplicado${incl ? ` com ${r.items_cloned} Itens` : ''}.`);
    await this.render();
  },
  async saveModel(id) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const name = prompt('Nome do modelo/pacote:');
    if (!name) return;
    await API.post('/api/plans/save-package-template', { project_id: App.projectId, plan_id: id, name, category: 'PLANOS' });
    UI.toast('Pacote salvo na Biblioteca.');
  },
  async bulkSaveModel() {
    const UI = window.PM11.UI;
    if (this.selected.size !== 1) return UI.toast('Selecione exatamente um Plano para salvar como modelo.', 'warn');
    return this.saveModel([...this.selected][0]);
  },
  async applyModel(planId) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const t = await API.get('/api/templates/equipment');
    if (!t.length) return UI.toast('Nenhum pacote/modelo salvo na Biblioteca.', 'warn');
    const txt = t.map(x => `${x.id} — ${x.name} (${x.item_count} itens)`).join('\n');
    const id = Number(prompt('Informe o ID do modelo a aplicar:\n' + txt));
    if (!id) return;
    const equip = prompt('Código do equipamento destino (opcional):', '') || '';
    await API.post('/api/templates/equipment/apply', { project_id: App.projectId, template_id: id, equipment_code: equip, plan_id_override: planId });
    UI.toast('Modelo aplicado.');
  },
  bulkEdit() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!this.selected.size) return;
    UI.modal('Editar Planos em Massa', `<div class="form-section"><div class="form-section-title">Somente campos marcados serão alterados</div><div class="form-grid modern"><div class="fg-4"><label><input type="checkbox" id="b-cycle-on"> Ciclo</label><select class="control" id="b-cycle">${this.catalogs.cycles.map(c => `<option value="${c.code}">${c.code} — ${UI.esc(c.text_cycle)}</option>`).join('')}</select></div><div class="fg-4"><label><input type="checkbox" id="b-status-on"> Status</label><select class="control" id="b-status"><option value="ACTIVE">ATIVO</option><option value="INACTIVE">INATIVO</option></select></div><div class="fg-4"><label><input type="checkbox" id="b-offset-on"> Offset</label><input class="control" type="number" min="1" id="b-offset"></div></div></div>`, {
      onSave: async () => {
        const u = {};
        if (document.querySelector('#b-cycle-on').checked) u.cycle_code = document.querySelector('#b-cycle').value;
        if (document.querySelector('#b-status-on').checked) u.status = document.querySelector('#b-status').value;
        if (document.querySelector('#b-offset-on').checked) u.offset_days = document.querySelector('#b-offset').value || null;
        await API.post('/api/plans/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: u });
        this.selected.clear();
        await this.render();
      }
    });
  },
  bulkColor() {
    const API = window.PM11.API, App = window.PM11.App;
    const c = prompt('Cor: yellow, green, blue, red, purple ou vazio para remover', 'yellow');
    if (c === null) return;
    API.post('/api/plans/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: { row_color: c } }).then(() => {
      this.selected.clear();
      this.render();
    });
  },
  async del(ids) {
    const API = window.PM11.API, App = window.PM11.App;
    if (!ids.length || !confirm(`Excluir ${ids.length} Plano(s)? Itens vinculados ficarão sem Plano.`)) return;
    await window.PM11.API.post('/api/plans/bulk-delete', { project_id: window.PM11.App.projectId, ids });
    ids.forEach(x => this.selected.delete(x));
    await this.render();
  }
};
