window.PM11 = window.PM11 || {};

window.PM11.Settings = {
  async render() {
    const UI = window.PM11.UI, API = window.PM11.API, App = window.PM11.App;
    const [cats, proj] = await Promise.all([API.get('/api/catalogs'), API.get('/api/projects/' + App.projectId)]);
    this.cats = cats;
    document.querySelector('#view').innerHTML = UI.pageHead('Configurações do Projeto', 'Gerencie padrões de código, ciclos, linhas de produção, subáreas e catálogos corporativos.') +
      `<div class="dashboard-grid"><div class="card"><div class="card-header"><h3>Padrões do Projeto</h3></div><div class="card-body"><div class="form-row"><div class="form-group"><label>Centro padrão</label><select class="control" id="st-center">${UI.selectOptions(cats.centers, 'code', x => `${x.code} — ${x.description}`, proj.default_center_code)}</select></div><div class="form-group"><label>Processo padrão</label><select class="control" id="st-process">${UI.selectOptions(cats.processes, 'code', x => `${x.code} — ${x.description}`, proj.default_process_code)}</select></div><div class="form-group"><label>Tipo padrão</label><select class="control" id="st-type">${UI.selectOptions(cats.types, 'code', x => `${x.code} — ${x.description}`, proj.default_type_code)}</select></div></div><button class="btn btn-primary" id="st-save" style="margin-top:15px">Salvar padrões</button></div></div><div class="card"><div class="card-header"><h3>Catálogo de Ciclos PM11</h3><span class="card-subtitle">base corporativa</span></div><div class="card-body no-padding"><div class="table-responsive-container" style="max-height:330px"><table class="data-table"><thead><tr><th>Cód.</th><th>Ciclo</th><th>Unid.</th><th>Texto</th><th>Horiz.</th></tr></thead><tbody>${cats.cycles.map(c => `<tr><td><b>${c.code}</b></td><td>${c.cycle_value}</td><td>${c.unit}</td><td>${UI.esc(c.text_cycle)}</td><td>${c.horizon}%</td></tr>`).join('')}</tbody></table></div></div></div></div>` +
      `<div class="dashboard-grid" style="margin-top:20px"><div class="card"><div class="card-header"><h3>Linhas de Produção</h3><button class="btn btn-xs btn-outline" onclick="window.PM11.Settings.add('lines')">+ Adicionar</button></div><div class="card-body">${cats.lines.map(x => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px dashed #e2e8f0"><span><b>${x.code}</b> — ${UI.esc(x.description)}</span><button class="btn btn-xs btn-outline" onclick="window.PM11.Settings.remove('lines','${x.code}')">Excluir</button></div>`).join('')}</div></div><div class="card"><div class="card-header"><h3>Subáreas</h3><button class="btn btn-xs btn-outline" onclick="window.PM11.Settings.add('subareas')">+ Adicionar</button></div><div class="card-body">${cats.subareas.map(x => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px dashed #e2e8f0"><span><b>${x.code}</b> — ${UI.esc(x.description)}</span><button class="btn btn-xs btn-outline" onclick="window.PM11.Settings.remove('subareas','${x.code}')">Excluir</button></div>`).join('')}</div></div></div>` +
      `<div class="card" style="margin-top:20px"><div class="card-header"><h3>Catálogos corporativos carregados</h3></div><div class="card-body"><p><b>486 Métodos de inspeção</b> e <b>461 Unidades de medida</b> foram carregados a partir da planilha de referência fornecida. A busca é feita por código, descrição e sugestão contextual.</p></div></div>`;
    document.querySelector('#st-save').onclick = async () => {
      await API.put('/api/projects/' + App.projectId, { default_center_code: document.querySelector('#st-center').value, default_process_code: document.querySelector('#st-process').value, default_type_code: document.querySelector('#st-type').value });
      UI.toast('Configurações salvas.');
    };
  },
  add(kind) {
    const UI = window.PM11.UI, API = window.PM11.API;
    UI.modal(kind === 'lines' ? 'Adicionar Linha de Produção' : 'Adicionar Subárea', `<div class="form-row"><div class="form-group"><label>Código (3 caracteres)</label><input class="control" id="cat-code" maxlength="3"></div><div class="form-group"><label>Descrição</label><input class="control" id="cat-desc"></div></div>`, {
      onSave: async () => {
        await API.post('/api/catalogs/upsert', { kind, code: document.querySelector('#cat-code').value, description: document.querySelector('#cat-desc').value });
        UI.toast('Catálogo atualizado.');
        await this.render();
      }
    });
  },
  async remove(kind, code) {
    const API = window.PM11.API;
    if (!confirm(`Excluir ${code} do catálogo?`)) return;
    await API.delete('/api/catalogs', { kind, code });
    await this.render();
  }
};
