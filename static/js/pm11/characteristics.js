window.PM11 = window.PM11 || {};

window.PM11.Characteristics = {
  rows: [], items: [], selected: new Set(), copied: null, inlineOptions: {}, filters: { search: '', item_id: '', type: '', status: '', row_color: '' },
  async render() { await this.load(); this.draw(); },
  async load() {
    const API = window.PM11.API;
    [this.rows, this.items] = await Promise.all([API.get('/api/characteristics', this.filters), API.get('/api/items')]);
  },
  draw() {
    const UI = window.PM11.UI;
    const fieldsHtml = `
      <div class="form-group"><label>Pesquisar</label><input class="control" id="ch-f-search" placeholder="Característica ou item..." value="${UI.esc(this.filters.search)}"></div>
      <div class="form-group"><label>Item de Inspeção</label><select class="control" id="ch-f-item"><option value="">Todos os Itens</option>${this.items.map(i => `<option value="${i.id}" ${String(i.id) === String(this.filters.item_id) ? 'selected' : ''}>#${i.legacy_identifier} — ${UI.esc(i.description)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Tipo</label><select class="control" id="ch-f-type"><option value="">Todos</option><option value="QUALITAT" ${this.filters.type === 'QUALITAT' ? 'selected' : ''}>Qualitativa</option><option value="QUANTITA" ${this.filters.type === 'QUANTITA' ? 'selected' : ''}>Quantitativa</option></select></div>
      <div class="form-group"><label>Status</label><select class="control" id="ch-f-status"><option value="">Todos</option><option value="ACTIVE" ${this.filters.status === 'ACTIVE' ? 'selected' : ''}>Ativas</option><option value="INACTIVE" ${this.filters.status === 'INACTIVE' ? 'selected' : ''}>Inativas</option></select></div>
      <div class="form-group"><label>Marcador</label><select class="control" id="ch-f-color"><option value="">Todas</option>${UI.colorSelect(this.filters.row_color).replace('<option value="" selected>Sem cor</option>', '')}</select></div>
    `;
    const actionsHtml = `<button class="btn btn-outline" id="ch-clear">Limpar</button><button class="btn btn-primary" id="ch-filter">Filtrar</button>`;
    const tableHtml = `<table class="data-table" id="chars-table"><thead><tr><th><input type="checkbox" id="ch-all"></th><th>ID ITEM</th><th>ITEM</th><th>CARACTERÍSTICA</th><th>TIPO</th><th>MÉTODO</th><th>CASAS</th><th>UNIDADE</th><th>REFERÊNCIA</th><th>LIM. INF.</th><th>LIM. SUP.</th><th>STATUS</th><th class="actions-col">AÇÕES</th></tr></thead><tbody>${this.body()}</tbody></table>`;

    document.querySelector('#view').innerHTML = UI.pageHead('Características de Controle', 'Configure o que o inspetor mede ou avalia em cada Ordem PM11.', `<button class="btn btn-primary" id="ch-new">+ Nova Característica</button>`) +
      UI.filterCard(fieldsHtml, actionsHtml, 'chars-filter-card') +
      UI.selectionBar('ch-selection', this.selected.size, `<button class="btn btn-xs btn-outline" data-bulk="edit">Editar em massa</button><button class="btn btn-xs btn-outline" data-bulk="save">Salvar padrão</button><button class="btn btn-xs btn-outline" data-bulk="color">Colorir</button><button class="btn btn-xs btn-danger" data-bulk="delete">Excluir</button>`) +
      UI.tableCard(`${this.rows.length} característica(s) encontrada(s)`, UI.tableTools('chars'), tableHtml);
    this.bind();
    setTimeout(() => UI.enhanceSelects(), 40);
  },
  body() {
    const UI = window.PM11.UI;
    if (!this.rows.length) return UI.tableEmpty(13);

    return this.rows.map(c => {
      const issues = [];
      if (c.validation_issues_json) {
        try {
          const parsed = typeof c.validation_issues_json === 'string' ? JSON.parse(c.validation_issues_json) : c.validation_issues_json;
          if (Array.isArray(parsed)) issues.push(...parsed);
        } catch(e) {}
      }

      // Fast live compatibility check if not validated yet
      if (window.TechnicalClasses) {
        const comp = window.TechnicalClasses.checkCompatibility(c.method_code, c.unit_code);
        if (!comp.compatible) issues.push({ severity: 'WARNING', field: 'unit_code', message: comp.warning });
      }

      const getIssue = field => issues.find(i => i.field === field);
      const cell = (field, value, extra = '') => {
        const iss = getIssue(field);
        const errClass = iss ? (iss.severity === 'ERROR' ? 'cell-invalid-error' : 'cell-invalid-warning') : '';
        const title = iss ? `⚠️ ${iss.message}` : 'Clique duas vezes para editar';
        return `<td class="editable-cell ${extra} ${errClass}" data-field="${field}" title="${title}">${value}</td>`;
      };

      const isError = issues.some(i => i.severity === 'ERROR');
      const isWarn = issues.length > 0 && !isError;
      const rowValidationClass = isError ? 'row-color-red' : (isWarn ? 'row-color-yellow' : '');

      const indicator = issues.length > 0
        ? `<span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" data-act="issue-info" style="cursor:pointer; margin-right:6px; font-size:14px;" title="Clique para ver o diagnóstico e sugestão de correção:\n${issues.map(x=>'• '+x.message).join('\n')}">${isError ? '⛔' : '⚠️'}</span>`
        : '';

      return `<tr data-id="${c.id}" class="${rowValidationClass} ${UI.rowClass(c.row_color, this.selected.has(c.id), this.copied?.id === c.id)}">
        <td><div style="display:flex; align-items:center; justify-content:center; gap:4px;">${indicator}<input class="ch-check" type="checkbox" value="${c.id}" ${this.selected.has(c.id) ? 'checked' : ''}></div></td>
        <td><b>${c.legacy_identifier}</b></td>
        <td>${UI.esc(c.item_description)}</td>
        ${cell('description', UI.esc(c.description))}
        ${cell('characteristic_type', ['QUANTITA','QUANTIT'].includes(c.characteristic_type) ? 'QUANTITATIVA' : 'QUALITATIVA')}
        ${cell('method_code', UI.esc(c.method_code))}
        ${cell('decimals', c.decimals ?? '')}
        ${cell('unit_code', UI.esc(c.unit_code))}
        ${cell('reference_value', c.reference_value ?? '')}
        ${cell('lower_limit', c.lower_limit ?? '')}
        ${cell('upper_limit', c.upper_limit ?? '')}
        ${cell('status', UI.badgeStatus(c.status))}
        <td><div class="row-actions"><button class="btn btn-xs btn-outline" data-act="edit">Editar</button><button class="btn btn-xs btn-danger" data-act="delete">Excluir</button></div></td>
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

    UI.modal('Diagnóstico de Inconsistência e Sugestão', `
      <div style="padding:4px;">
        <h4 style="margin:0 0 12px; font-size:14px; font-weight:700; color:#111;">Diagnóstico para a Característica “${UI.esc(row.description)}”:</h4>
        ${issuesHtml}
        <div class="helpbox" style="margin-top:14px;">
          💡 Clique no botão <b>Corrigir / Editar</b> abaixo para abrir a janela de edição e ajustar o Método, Unidade ou Valores.
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
    const UI = window.PM11.UI;
    document.querySelector('#ch-new').onclick = () => this.edit();
    document.querySelector('#ch-filter').onclick = async () => {
      this.filters = { search: cval('ch-f-search'), item_id: cval('ch-f-item'), type: cval('ch-f-type'), status: cval('ch-f-status'), row_color: cval('ch-f-color') };
      await this.render();
    };
    document.querySelector('#ch-clear').onclick = async () => {
      this.filters = { search: '', item_id: '', type: '', status: '', row_color: '' };
      await this.render();
    };
    document.querySelector('#ch-all').onchange = e => {
      this.selected = new Set(e.target.checked ? this.rows.map(x => x.id) : []);
      this.draw();
    };
    document.querySelectorAll('.ch-check').forEach(x => x.onchange = e => {
      const id = Number(e.target.value);
      e.target.checked ? this.selected.add(id) : this.selected.delete(id);
      this.draw();
    });
    document.querySelectorAll('#chars-table tbody tr[data-id]').forEach(tr => {
      const id = Number(tr.dataset.id);
      tr.querySelector('[data-act="edit"]').onclick = e => { e.stopPropagation(); this.edit(id); };
      tr.querySelector('[data-act="delete"]').onclick = e => { e.stopPropagation(); this.del([id]); };
      const issueBtn = tr.querySelector('[data-act="issue-info"]');
      if (issueBtn) {
        issueBtn.onclick = e => {
          e.stopPropagation();
          const row = this.rows.find(x => x.id === id);
          if (row) {
            const issues = [];
            if (row.validation_issues_json) {
              try {
                const parsed = typeof row.validation_issues_json === 'string' ? JSON.parse(row.validation_issues_json) : row.validation_issues_json;
                if (Array.isArray(parsed)) issues.push(...parsed);
              } catch(err) {}
            }
            if (window.TechnicalClasses) {
              const comp = window.TechnicalClasses.checkCompatibility(row.method_code, row.unit_code);
              if (!comp.compatible) issues.push({ severity: 'WARNING', field: 'unit_code', message: comp.warning });
            }
            this.openIssueModal(row, issues);
          }
        };
      }
      tr.querySelectorAll('td.editable-cell').forEach(td => td.ondblclick = e => {
        e.preventDefault();
        e.stopPropagation();
        this.inlineEdit(td, id, td.dataset.field);
      });
      tr.onclick = e => {
        if (e.target.closest('button,input,select,td.editable-cell')) return;
        this.selected.has(id) ? this.selected.delete(id) : this.selected.add(id);
        this.draw();
      };
    });
    document.querySelectorAll('[data-bulk]').forEach(b => b.onclick = () => ({ edit: () => this.bulkEdit(), save: () => this.savePattern(), color: () => this.bulkColor(), delete: () => this.del([...this.selected]) }[b.dataset.bulk])());
    UI.bindTableTools('chars-table');
    document.onkeydown = e => this.keys(e);
  },
  async inlineEdit(cell, id, field) {
    if (cell.classList.contains('cell-editing')) return;
    const UI = window.PM11.UI, API = window.PM11.API;
    const row = this.rows.find(x => x.id === id);
    if (!row) return;
    const originalHtml = cell.innerHTML;
    const originalValue = row[field] ?? '';
    let editor;

    if (field === 'characteristic_type') {
      editor = document.createElement('select');
      editor.innerHTML = '<option value="QUALITAT">QUALITATIVA</option><option value="QUANTIT">QUANTITATIVA</option>';
    } else if (field === 'method_code' || field === 'unit_code') {
      const kind = field === 'method_code' ? 'methods' : 'units';
      try {
        this.inlineOptions[kind] = this.inlineOptions[kind] || await API.get(`/api/${kind}`, { limit: 500 });
      } catch (error) {
        this.inlineOptions[kind] = [];
      }
      editor = document.createElement('select');

      const clsKey = window.TechnicalClasses ? (field === 'unit_code' ? window.TechnicalClasses.getMethodClass(row.method_code) : window.TechnicalClasses.getUnitClass(row.unit_code)) : null;
      let opts = (this.inlineOptions[kind] || []).map(item => typeof item === 'string' ? item : item.code || item.description);

      if (clsKey && window.TechnicalClasses) {
        const grouped = window.TechnicalClasses.sortDropdownOptions(opts, originalValue, clsKey);
        let html = '<option value="">— Selecione —</option>';
        grouped.forEach(g => {
          if (g.items.length > 0) {
            html += `<optgroup label="${g.header}">`;
            g.items.forEach(v => {
              html += `<option value="${UI.esc(v)}" ${String(v).toUpperCase() === String(originalValue).toUpperCase() ? 'selected' : ''}>${UI.esc(v)}</option>`;
            });
            html += `</optgroup>`;
          }
        });
        editor.innerHTML = html;
      } else {
        editor.innerHTML = '<option value="">— Selecione —</option>' + opts.map(v => `<option value="${UI.esc(v)}" ${String(v).toUpperCase() === String(originalValue).toUpperCase() ? 'selected' : ''}>${UI.esc(v)}</option>`).join('');
      }
    } else {
      editor = document.createElement('input');
      editor.type = ['decimals', 'reference_value', 'lower_limit', 'upper_limit'].includes(field) ? 'number' : 'text';
      if (editor.type === 'number') editor.step = field === 'decimals' ? '1' : 'any';
    }

    editor.className = 'table-inline-input';
    editor.value = originalValue;
    cell.classList.add('cell-editing');
    cell.innerHTML = '';
    cell.appendChild(editor);
    editor.focus();
    if (editor.tagName === 'INPUT') editor.select();

    let finished = false;
    const cancel = () => {
      if (finished) return;
      finished = true;
      cell.classList.remove('cell-editing');
      cell.innerHTML = originalHtml;
    };
    const save = async () => {
      if (finished) return;
      let value = editor.value.trim();
      if (field === 'status') {
        const normalized = value.toUpperCase();
        value = normalized === 'ATIVO' ? 'ACTIVE' : normalized === 'INATIVO' ? 'INACTIVE' : normalized;
      }
      if (['decimals', 'reference_value', 'lower_limit', 'upper_limit'].includes(field)) value = value === '' ? null : Number(value);
      if (value === originalValue || String(value ?? '') === String(originalValue ?? '')) return cancel();
      finished = true;
      editor.disabled = true;
      try {
        const payload = { ...row, [field]: value };
        await API.put('/api/characteristics/' + id, payload);
        UI.toast('Celula atualizada.');
        await this.render();
      } catch (error) {
        finished = false;
        editor.disabled = false;
        editor.focus();
        UI.toast(error.message || 'Nao foi possivel salvar.', 'error');
      }
    };
    editor.onkeydown = e => {
      if (e.key === 'Escape') { e.preventDefault(); cancel(); }
      if (e.key === 'Enter') { e.preventDefault(); save(); }
    };
    editor.onblur = () => save();
    if (selectFields.includes(field)) editor.onchange = () => save();
  },
  edit(id = null) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const c = id ? this.rows.find(x => x.id === id) : { characteristic_type: 'QUALITAT', status: 'ACTIVE' }, item = this.items.find(i => i.id === c.item_id);
    const lblStyle = 'display:block; width:100%; font-size:12px; font-weight:600; color:#374151; margin:0 0 6px 0;';
    const fieldStyle = 'display:flex; flex-direction:column; width:100%;';
    const modalHtml = `
      <div class="form-section" style="margin-bottom:20px; padding-bottom:16px; border-bottom:1px solid #E2E8F0;">
        <div class="form-section-title" style="font-size:13px; font-weight:700; text-transform:uppercase; color:#15803D; margin-bottom:14px; display:flex; align-items:center; gap:6px;">
          📌 Vínculo e Classificação
        </div>
        <div class="form-grid modern" style="display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; align-items:start; width:100%;">
          <div class="fg-6" style="${fieldStyle} grid-column:span 6;">
            <label style="${lblStyle}">Item de Inspeção</label>
            <button class="control picker-control" id="ce-item" data-value="${c.item_id || ''}" style="width:100%; height:40px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; cursor:pointer;">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#1F2937;">${item ? `#${item.legacy_identifier} — ${UI.esc(item.description)}` : 'Pesquisar / selecionar Item...'}</span>
              <b style="color:#9CA3AF; margin-left:6px; font-size:12px;">⌄</b>
            </button>
          </div>
          <div class="fg-3" style="${fieldStyle} grid-column:span 3;">
            <label style="${lblStyle}">Tipo</label>
            <select class="control" id="ce-type" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937;">
              <option value="QUALITAT" ${['QUALITAT','QUALITATIVA'].includes(c.characteristic_type) ? 'selected' : ''}>QUALITATIVA</option>
              <option value="QUANTIT" ${['QUANTIT','QUANTITA','QUANTITATIVA'].includes(c.characteristic_type) ? 'selected' : ''}>QUANTITATIVA</option>
            </select>
          </div>
          <div class="fg-3" style="${fieldStyle} grid-column:span 3;">
            <label style="${lblStyle}">Status</label>
            <select class="control" id="ce-status" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937;">
              <option value="ACTIVE" ${c.status !== 'INACTIVE' ? 'selected' : ''}>ATIVO</option>
              <option value="INACTIVE" ${c.status === 'INACTIVE' ? 'selected' : ''}>INATIVO</option>
            </select>
          </div>
          <div class="fg-12" style="${fieldStyle} grid-column:span 12;">
            <label style="${lblStyle}">Descrição da Característica</label>
            <input class="control" id="ce-desc" placeholder="Ex.: Vibração lado acoplado do motor" value="${UI.esc(c.description || '')}" style="width:100%; height:40px; padding:0 12px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937; box-sizing:border-box;">
          </div>
        </div>
      </div>

      <div class="form-section" style="margin-bottom:14px;">
        <div class="form-section-title" style="font-size:13px; font-weight:700; text-transform:uppercase; color:#15803D; margin-bottom:14px; display:flex; align-items:center; gap:6px;">
          📐 Método e Critérios Quantitativos
        </div>
        <div class="form-grid modern" style="display:grid; grid-template-columns:repeat(12, 1fr); gap:16px; align-items:start; width:100%;">
          <div class="fg-6" style="${fieldStyle} grid-column:span 6;">
            <label style="${lblStyle}">Método de Inspeção</label>
            <button class="control picker-control" id="ce-method" data-value="${UI.esc(c.method_code || '')}" style="width:100%; height:40px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; cursor:pointer;">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#1F2937;">${UI.esc(c.method_code || 'Pesquisar método...')}</span>
              <b style="color:#9CA3AF; margin-left:6px; font-size:12px;">⌄</b>
            </button>
          </div>
          <div class="fg-2 quantitative" style="${fieldStyle} grid-column:span 2;">
            <label style="${lblStyle}">Casas decimais</label>
            <input class="control" id="ce-dec" type="number" min="0" max="6" value="${c.decimals ?? 2}" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937; box-sizing:border-box;">
          </div>
          <div class="fg-4 quantitative" style="${fieldStyle} grid-column:span 4;">
            <label style="${lblStyle}">Unidade de Medida</label>
            <button class="control picker-control" id="ce-unit" data-value="${UI.esc(c.unit_code || '')}" style="width:100%; height:40px; display:flex; align-items:center; justify-content:space-between; padding:0 12px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; cursor:pointer;">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#1F2937;">${UI.esc(c.unit_code || 'Pesquisar unidade...')}</span>
              <b style="color:#9CA3AF; margin-left:6px; font-size:12px;">⌄</b>
            </button>
          </div>
          <div class="fg-4 quantitative" style="${fieldStyle} grid-column:span 4;">
            <label style="${lblStyle}">Valor de Referência</label>
            <input class="control" id="ce-ref" type="number" step="any" value="${c.reference_value ?? ''}" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937; box-sizing:border-box;">
          </div>
          <div class="fg-4 quantitative" style="${fieldStyle} grid-column:span 4;">
            <label style="${lblStyle}">Limite Inferior</label>
            <input class="control" id="ce-lo" type="number" step="any" value="${c.lower_limit ?? ''}" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937; box-sizing:border-box;">
          </div>
          <div class="fg-4 quantitative" style="${fieldStyle} grid-column:span 4;">
            <label style="${lblStyle}">Limite Superior</label>
            <input class="control" id="ce-hi" type="number" step="any" value="${c.upper_limit ?? ''}" style="width:100%; height:40px; padding:0 10px; border:1px solid #D1D5DB; border-radius:6px; background:#fff; font-size:13px; color:#1F2937; box-sizing:border-box;">
          </div>
        </div>
      </div>

      <div class="helpbox" style="margin-top:16px; padding:10px 14px; background:#EFF6FF; border:1px solid #BFDBFE; border-radius:6px; font-size:12px; color:#1E40AF;">
        💡 Digite a característica. O sistema prioriza métodos e unidades relacionados à grandeza física correspondente.
      </div>
    `;

    UI.modal(id ? 'Editar Característica de Controle' : 'Nova Característica de Controle', modalHtml, {
      wide: true, onOpen: () => {
        const itemBtn = document.querySelector('#ce-item');
        itemBtn.onclick = () => UI.floatingPicker(itemBtn, {
          rows: this.items, valueKey: 'id', primary: i => `#${i.legacy_identifier} — ${i.description}`, secondary: i => `${i.equipment_code || ''} ${i.plan_code || ''}`, searchPlaceholder: 'ID, equipamento ou descrição...', onSelect: i => {
            itemBtn.dataset.value = i.id;
            itemBtn.querySelector('span').textContent = `#${i.legacy_identifier} — ${i.description}`;
          }
        });
        const method = document.querySelector('#ce-method'), unit = document.querySelector('#ce-unit');
        method.onclick = async () => {
          const rows = await API.get('/api/methods', { hint: cval('ce-desc'), limit: 80 });
          UI.floatingPicker(method, {
            rows, valueKey: 'code', primary: r => `${r.code} — ${r.description}`, secondary: r => 'Método', searchPlaceholder: 'Digite método ou sigla...', onSelect: r => {
              method.dataset.value = r.code;
              method.querySelector('span').textContent = `${r.code} — ${r.description}`;
            }
          });
        };
        unit.onclick = async () => {
          const rows = await API.get('/api/units', { hint: cval('ce-desc'), limit: 80 });
          UI.floatingPicker(unit, {
            rows, valueKey: 'code', primary: r => `${r.code} — ${r.description}`, secondary: r => 'Unidade', searchPlaceholder: 'Digite unidade ou descrição...', onSelect: r => {
              unit.dataset.value = r.code;
              unit.querySelector('span').textContent = `${r.code} — ${r.description}`;
            }
          });
        };
        const type = document.querySelector('#ce-type');
        const toggle = () => document.querySelectorAll('.quantitative').forEach(x => {
          const isQuant = ['QUANTIT', 'QUANTITA', 'QUANTITATIVA'].includes(type.value);
          x.style.opacity = isQuant ? '1' : '.38';
          x.querySelectorAll('input,button').forEach(e => e.disabled = !isQuant);
        });
        type.onchange = toggle;
        toggle();
      }, onSave: async () => {
        const typ = cval('ce-type');
        const isQuant = ['QUANTIT', 'QUANTITA', 'QUANTITATIVA'].includes(typ);
        const d = {
          project_id: App.projectId,
          item_id: Number(document.querySelector('#ce-item').dataset.value),
          characteristic_type: isQuant ? 'QUANTIT' : 'QUALITAT',
          description: cval('ce-desc'),
          method_code: document.querySelector('#ce-method').dataset.value,
          status: cval('ce-status'),
          decimals: isQuant ? Number(cval('ce-dec') || 2) : null,
          unit_code: isQuant ? document.querySelector('#ce-unit').dataset.value : '',
          reference_value: isQuant ? cval('ce-ref') : null,
          lower_limit: isQuant ? cval('ce-lo') : null,
          upper_limit: isQuant ? cval('ce-hi') : null
        };
        if (!d.item_id) throw new Error('Selecione o Item.');
        id ? await API.put('/api/characteristics/' + id, d) : await API.post('/api/characteristics', d);
        UI.toast('Característica salva.');
        await this.render();
      }
    });
  },
  bulkEdit() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!this.selected.size) return;
    UI.modal('Editar Características em Massa', `<div class="form-section"><div class="form-section-title">Marque os campos a alterar</div><div class="form-grid modern"><div class="fg-4"><label><input type="checkbox" id="bc-type-on"> Tipo</label><select class="control" id="bc-type"><option value="QUALITAT">QUALITATIVA</option><option value="QUANTITA">QUANTITATIVA</option></select></div><div class="fg-4"><label><input type="checkbox" id="bc-method-on"> Método</label><input class="control" id="bc-method"></div><div class="fg-4"><label><input type="checkbox" id="bc-unit-on"> Unidade</label><input class="control" id="bc-unit"></div><div class="fg-4"><label><input type="checkbox" id="bc-status-on"> Status</label><select class="control" id="bc-status"><option value="ACTIVE">ATIVO</option><option value="INACTIVE">INATIVO</option></select></div></div></div>`, {
      onSave: async () => {
        const u = {};
        if (document.querySelector('#bc-type-on').checked) u.characteristic_type = cval('bc-type');
        if (document.querySelector('#bc-method-on').checked) u.method_code = cval('bc-method');
        if (document.querySelector('#bc-unit-on').checked) u.unit_code = cval('bc-unit');
        if (document.querySelector('#bc-status-on').checked) u.status = cval('bc-status');
        await API.post('/api/characteristics/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: u });
        this.selected.clear();
        await this.render();
      }
    });
  },
  async savePattern() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const itemIds = [...new Set(this.rows.filter(x => this.selected.has(x.id)).map(x => x.item_id))];
    if (itemIds.length !== 1) return UI.toast('Selecione Características de um único Item para salvar o padrão completo desse Item.', 'warn');
    const name = prompt('Nome do padrão de Características:');
    if (!name) return;
    await API.post('/api/templates/characteristics/save-from-item', { project_id: App.projectId, item_id: itemIds[0], name, category: 'CARACTERÍSTICAS' });
    UI.toast('Padrão salvo na Biblioteca.');
  },
  bulkColor() {
    const API = window.PM11.API, App = window.PM11.App;
    const c = prompt('Cor: yellow, green, blue, red, purple ou vazio', 'yellow');
    if (c === null) return;
    API.post('/api/characteristics/bulk-update', { project_id: App.projectId, ids: [...this.selected], updates: { row_color: c } }).then(() => {
      this.selected.clear();
      this.render();
    });
  },
  async del(ids) {
    const API = window.PM11.API, App = window.PM11.App;
    if (!ids.length || !confirm(`Excluir ${ids.length} Característica(s)?`)) return;
    await API.post('/api/characteristics/bulk-delete', { project_id: App.projectId, ids });
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
      UI.toast('Característica copiada. Selecione destinos e pressione Ctrl+V.');
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v' && this.copied && this.selected.size) {
      e.preventDefault();
      const u = { characteristic_type: this.copied.characteristic_type, description: this.copied.description, method_code: this.copied.method_code, decimals: this.copied.decimals, unit_code: this.copied.unit_code, reference_value: this.copied.reference_value, lower_limit: this.copied.lower_limit, upper_limit: this.copied.upper_limit, status: this.copied.status };
      window.PM11.API.post('/api/characteristics/bulk-update', { project_id: window.PM11.App.projectId, ids: [...this.selected].filter(x => x !== this.copied.id), updates: u }).then(() => {
        window.PM11.UI.toast('Colado nas linhas selecionadas.');
        this.render();
      });
    }
  }
};
function cval(id) { return document.querySelector('#' + id)?.value ?? ''; }
