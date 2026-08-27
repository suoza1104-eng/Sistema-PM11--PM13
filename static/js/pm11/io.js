window.PM11 = window.PM11 || {};

window.PM11.IO = {
  file: null, preview: null, mapping: null, step: 1,
  fieldLabels: {
    plans: { code: 'Código do Plano', description: 'Descrição do Plano', char_count: 'Qtd. Caracteres', cycle_value: 'Ciclo', unit: 'Unidade', text_cycle: 'Texto do Ciclo', horizon: 'Horizonte de Abertura', offset_days: 'Offset' },
    items: { equipment_code: 'Equipamento', gpm: 'GPM', work_center: 'Centro de Trabalho', condition_code: 'Condição', priority: 'Prioridade', plan_code: 'Plano de Inspeção', legacy_identifier: 'Identificador', route: 'Rota', description: 'Descrição do Item', char_count: 'Qtd. Caracteres', plan_description: 'Descrição do Plano', cycle_value: 'Ciclo', unit: 'Unidade', text_cycle: 'Texto do Ciclo', horizon: 'Horizonte', inspection_minutes: 't(min)', inspection_label: 'Itens_Inspeção', criticality: 'Criticidade', status: 'Status' },
    characteristics: { legacy_identifier: 'Identificador do Item', characteristic_type: 'Tipo Qualit./Quantit.', description: 'Característica de Controle', method_code: 'Método', decimals: 'Casas Decimais', unit_code: 'Unidade de Medida', reference_value: 'Valor de Referência', lower_limit: 'Limite Inferior', upper_limit: 'Limite Superior', status: 'Status' }
  },

  async render() {
    const UI = window.PM11.UI, App = window.PM11.App;
    document.querySelector('#view').innerHTML = UI.pageHead('Importar / Exportar', 'Importe a planilha de carga PM11 com reconhecimento automático, revise o mapeamento e exporte o Projeto Completo.') +
      `<div class="card wizard-container">
        <div class="wizard-steps-header">
          <div class="step-indicator active" id="ws1">1. Arquivo</div>
          <div class="step-indicator" id="ws2">2. Mapeamento</div>
          <div class="step-indicator" id="ws3">3. Diagnóstico</div>
          <div class="step-indicator" id="ws4">4. Conclusão</div>
        </div>
        <div class="wizard-steps-body">
          <div class="upload-dropzone" id="drop">
            <svg viewBox="0 0 24 24" class="upload-icon"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg>
            <h3>Arraste o arquivo Excel (.xlsx) aqui</h3>
            <p style="margin: 8px 0; color: var(--text-muted);">ou</p>
            <button class="btn btn-primary btn-sm" id="select-file" style="margin-top: 4px;">Clique aqui para selecionar</button>
            <input type="file" id="file" accept=".xlsx" class="hidden">
            <p class="subtitle" style="margin-top: 15px; font-size: 12px;">Reconhecimento inteligente por nome de aba, cabeçalhos e estrutura de dados.</p>
          </div>
          <div id="import-stage"></div>
        </div>
      </div>` +
      `<div class="card" style="margin-top: 20px;">
        <div class="card-header">
          <h3>Exportar / Backup do Projeto</h3>
        </div>
        <div class="card-body">
          <div class="dashboard-grid export-3cols-grid">
            <div class="form-group">
              <label>Planilha de Carga V1</label>
              <p class="subtitle" style="margin-bottom: 12px;">Modelo padronizado V1 para análise, carga, transporte entre projetos e reimportação.</p>
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button class="btn btn-primary" id="export-project">Exportar Projeto Completo XLSX</button>
                <button class="btn btn-outline" id="export-model">Baixar Modelo PM11 Vazio</button>
              </div>
            </div>
            <div class="form-group">
              <label>Planilha de Carga Sistemas</label>
              <p class="subtitle" style="margin-bottom: 12px;">Exportação estruturada por Sistemas e Subsistemas (Novo Modelo).</p>
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button class="btn btn-primary btn-outline" id="export-systems-project" style="border-color: var(--primary-color); color: var(--primary-dark);">Exportar Planilha Sistemas XLSX</button>
              </div>
            </div>
            <div class="form-group">
              <label>Backup do Banco de Dados</label>
              <p class="subtitle" style="margin-bottom: 12px;">Cópia de segurança integral de projetos, cadastros e relacionamentos.</p>
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <button class="btn btn-outline" id="backup">Baixar Backup (.zip)</button>
                <button class="btn btn-danger" id="restore-backup">Restaurar Backup</button>
                <input type="file" id="restore-file" accept=".zip" class="hidden">
              </div>
            </div>
          </div>
        </div>
      </div>`;

    const f = document.querySelector('#file'), drop = document.querySelector('#drop');
    document.querySelector('#select-file').onclick = () => f.click();
    f.onchange = () => this.choose(f.files[0]);
    drop.ondragover = e => { e.preventDefault(); drop.classList.add('dragover'); };
    drop.ondragleave = () => drop.classList.remove('dragover');
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove('dragover'); this.choose(e.dataTransfer.files[0]); };

    document.querySelector('#export-project').onclick = () => UI.download(`/api/pm11/export/project?project_id=${App.projectId}&days=90`);
    document.querySelector('#export-model').onclick = () => UI.download('/api/pm11/export/model');
    document.querySelector('#export-systems-project').onclick = () => UI.download(`/api/pm11/export/systems?project_id=${App.projectId}`);
    document.querySelector('#backup').onclick = () => UI.download('/api/pm11/backup');
    document.querySelector('#restore-backup').onclick = () => document.querySelector('#restore-file').click();
    document.querySelector('#restore-file').onchange = e => this.restoreBackup(e.target.files[0]);
  },

  setStep(n) {
    this.step = n;
    for (let i = 1; i <= 4; i++) {
      const el = document.querySelector('#ws' + i);
      if (el) {
        el.classList.toggle('active', i === n);
        el.classList.toggle('completed', i < n);
      }
    }
  },

  async choose(file, mapping = null) {
    const UI = window.PM11.UI, API = window.PM11.API;
    if (!file) return;
    this.file = file;
    this.mapping = mapping;
    this.setStep(1);
    UI.showLoader('Lendo arquivo e identificando abas...');
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (mapping) fd.append('mapping', JSON.stringify(mapping));
      this.preview = await API.request('/api/import/preview', { method: 'POST', body: fd });
      this.drawMapping();
    } catch (e) {
      UI.toast(e.message, 'error');
      document.querySelector('#import-stage').innerHTML = `<div class="errorbox" style="margin-top:15px;"><b>Falha na leitura:</b> ${UI.esc(e.message)}</div>`;
    } finally {
      UI.hideLoader();
    }
  },

  options(headers, selected = '') {
    const UI = window.PM11.UI;
    return `<option value="">— não mapear —</option>` + (headers || []).map(h => `<option value="${UI.esc(h)}" ${String(selected || '').toLowerCase() === String(h).toLowerCase() ? 'selected' : ''}>${UI.esc(h)}</option>`).join('');
  },

  mappingFields(entity, sheet) {
    const UI = window.PM11.UI;
    const p = this.preview, det = p.detection[entity] || {}, sugg = p.sheet_suggestions?.[entity]?.[sheet] || {}, headers = sugg.available_headers || det.available_headers || [], recognized = (sheet === det.sheet ? (det.fields || {}) : {}), saved = this.mapping?.[entity]?.fields || {}, labels = this.fieldLabels[entity] || {};
    return `<div class="mapping-fields-box" data-fields-for="${entity}">
      <div class="mapping-fields-header">
        <span>Campo do Sistema</span>
        <span>Coluna no Excel</span>
      </div>
      ${Object.keys(labels).map(k => `
        <div class="mapping-field-row">
          <span class="field-label">${UI.esc(labels[k])}</span>
          <select class="control map-field" data-entity="${entity}" data-field="${k}">
            ${this.options(headers, saved[k] || recognized[k] || '')}
          </select>
        </div>
      `).join('')}
    </div>`;
  },

  drawMapping() {
    const UI = window.PM11.UI;
    this.setStep(2);
    const p = this.preview;
    const labels = { plans: 'Planos', items: 'Itens de Inspeção', characteristics: 'Características de Controle' };
    
    let html = `<div style="margin-top: 20px; border-top: 1px solid var(--border-color); padding-top: 20px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
        <strong style="font-size:15px; color:var(--text-color);">Arquivo selecionado: ${UI.esc(p.file_name || this.file.name)}</strong>
        <span class="badge green">Leitura concluída</span>
      </div>
      <p class="subtitle" style="margin-bottom: 20px;">Verifique o alinhamento de abas e colunas antes de executar a importação.</p>
      <div class="mapping-grid">`;
      
    for (const e of ['plans', 'items', 'characteristics']) {
      const det = p.detection[e] || {}, sugg = p.sheet_suggestions[e] || {}, selected = this.mapping?.[e]?.sheet ?? det.sheet ?? '';
      html += `<div class="card p-15 mapping-entity" style="margin-bottom:15px;">
        <h4 style="font-size:13px; font-weight:700; color:var(--primary-dark); margin-bottom:10px;">${labels[e]}</h4>
        <div class="form-group">
          <label>Aba da Planilha Excel</label>
          <select class="control map-sheet" data-entity="${e}">
            <option value="">— não importar —</option>
            ${p.sheets.map(sh => `<option value="${UI.esc(sh)}" ${selected === sh ? 'selected' : ''}>${UI.esc(sh)}${sugg[sh]?.score ? ` · confiança ${sugg[sh].score}` : ''}</option>`).join('')}
          </select>
        </div>
        <p class="subtitle" style="font-size:11px; margin-bottom:10px;">Cabeçalho sugerido: linha ${sugg[selected]?.header_row || det.header_row || '?'} · ${Object.keys(det.fields || {}).length} campo(s) reconhecido(s)</p>
        ${this.mappingFields(e, selected)}
      </div>`;
    }
    
    html += `</div>
      <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:20px; border-top:1px solid var(--border-color); padding-top:15px;">
        <button class="btn btn-outline" id="map-back">Alterar Arquivo</button>
        <button class="btn btn-primary" id="map-next">Gerar Diagnóstico</button>
      </div>
    </div>`;
    
    document.querySelector('#import-stage').innerHTML = html;
    document.querySelectorAll('.map-sheet').forEach(s => s.onchange = () => {
      const holder = document.querySelector(`[data-fields-for="${s.dataset.entity}"]`);
      if (holder) holder.outerHTML = this.mappingFields(s.dataset.entity, s.value);
    });
    
    document.querySelector('#map-back').onclick = () => { this.preview = null; this.file = null; this.mapping = null; this.render(); };
    document.querySelector('#map-next').onclick = async () => {
      const m = {};
      for (const e of ['plans', 'items', 'characteristics']) m[e] = { sheet: document.querySelector(`.map-sheet[data-entity="${e}"]`)?.value || '', fields: {} };
      document.querySelectorAll('.map-field').forEach(f => { if (f.value) m[f.dataset.entity].fields[f.dataset.field] = f.value; });
      this.mapping = m;
      await this.choose(this.file, m);
      this.drawDiagnosis();
    };
  },

  drawDiagnosis() {
    const UI = window.PM11.UI;
    this.setStep(3);
    const p = this.preview;
    const sampleBlock = (title, key) => {
      const rows = p.samples?.[key] || [];
      if (!rows.length) return '';
      const keys = Object.keys(rows[0]).filter(x => x !== '_row').slice(0, 5);
      return `<details class="diag-sample" style="margin-top:10px;"><summary style="padding:10px; cursor:pointer; font-weight:600; background:#FAFCFA; border:1px solid var(--border-color); border-radius:6px;">${title}: visualizar prévia de registros</summary><div class="table-responsive-container" style="max-height:180px;"><table class="data-table"><thead><tr>${keys.map(k => `<th>${UI.esc(this.fieldLabels[key]?.[k] || k)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0, 3).map(r => `<tr>${keys.map(k => `<td>${UI.esc(r[k] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
    };
    
    document.querySelector('#import-stage').innerHTML = `
      <div style="margin-top:20px;">
        <div class="kpi-grid">
          <div class="kpi-card"><div class="kpi-content"><span class="kpi-title">Planos Identificados</span><h3 class="kpi-value">${p.counts.plans}</h3></div></div>
          <div class="kpi-card"><div class="kpi-content"><span class="kpi-title">Itens Identificados</span><h3 class="kpi-value">${p.counts.items}</h3></div></div>
          <div class="kpi-card"><div class="kpi-content"><span class="kpi-title">Características</span><h3 class="kpi-value">${p.counts.characteristics}</h3></div></div>
        </div>
        ${p.errors.length ? `<div class="errorbox" style="margin-top:15px;"><b>Erros de validação:</b><br>${p.errors.map(x => UI.esc(x)).join('<br>')}</div>` : ''}
        ${p.warnings.length ? `<div class="helpbox" style="margin-top:15px;"><b>Observações:</b><br>${p.warnings.map(x => UI.esc(x)).join('<br>')}</div>` : ''}
        ${sampleBlock('Planos', 'plans')}
        ${sampleBlock('Itens', 'items')}
        ${sampleBlock('Características', 'characteristics')}
        <div class="card" style="margin-top:15px; padding:15px;">
          <div class="form-group">
            <label>Ação no Banco de Dados</label>
            <select class="control" id="import-mode">
              <option value="MERGE">Adicionar e Unificar (Preserva o projeto e atualiza registros)</option>
              <option value="REPLACE">Substituir dados existentes do projeto</option>
            </select>
          </div>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:10px; margin-top:20px; border-top:1px solid var(--border-color); padding-top:15px;">
          <button class="btn btn-outline" id="diag-back">Voltar ao Mapeamento</button>
          <button class="btn btn-primary" id="confirm-import" ${p.errors.length ? 'disabled' : ''}>Confirmar Importação</button>
        </div>
      </div>`;
      
    document.querySelector('#diag-back').onclick = () => this.drawMapping();
    document.querySelector('#confirm-import').onclick = () => this.confirm();
  },

  async confirm() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const mode = document.querySelector('#import-mode').value;
    if (mode === 'REPLACE' && !confirm('Isso substituirá Planos, Itens e Características do projeto atual. Continuar?')) return;
    
    const fd = new FormData();
    fd.append('file', this.file);
    fd.append('project_id', String(App.projectId));
    fd.append('mode', mode);
    if (this.mapping) fd.append('mapping', JSON.stringify(this.mapping));
    
    this.setStep(4);
    UI.showLoader('Processando importação e gerando vínculos...');
    try {
      const r = await API.request('/api/import/confirm', { method: 'POST', body: fd });
      document.querySelector('#import-stage').innerHTML = `
        <div class="card" style="margin-top:20px; padding:20px; border-left:4px solid var(--primary-color);">
          <h3 style="color:var(--primary-dark); margin-bottom:10px;">✅ Importação Concluída com Sucesso!</h3>
          <p class="subtitle" style="margin-bottom:15px;">Estatísticas da carga efetuada:</p>
          <ul style="line-height:1.8; color:var(--text-color); padding-left:20px;">
            <li>Planos criados: <b>${r.stats.plans_created}</b> · atualizados: <b>${r.stats.plans_updated}</b></li>
            <li>Itens criados: <b>${r.stats.items_created}</b></li>
            <li>Características criadas: <b>${r.stats.characteristics_created}</b></li>
            <li>Características órfãs ignoradas: <b>${r.stats.orphan_characteristics}</b></li>
          </ul>
        </div>`;
      UI.toast('Importação concluída.');
      await App.loadProjects();
    } catch (e) {
      UI.toast(e.message, 'error');
      document.querySelector('#import-stage').innerHTML = `<div class="errorbox" style="margin-top:20px;"><b>Importação não concluída:</b> ${UI.esc(e.message)}</div>`;
    } finally {
      UI.hideLoader();
    }
  },

  async restoreBackup(file) {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    if (!file) return;
    if (!confirm('Restaurar este backup substituirá a base de dados atual. Continuar?')) return;
    const fd = new FormData();
    fd.append('file', file);
    UI.showLoader('Restaurando backup de dados...');
    try {
      await API.request('/api/backup/restore', { method: 'POST', body: fd });
      UI.toast('Backup restaurado com sucesso.');
      await App.loadProjects();
      await App.navigate('dashboard');
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      UI.hideLoader();
    }
  }
};
