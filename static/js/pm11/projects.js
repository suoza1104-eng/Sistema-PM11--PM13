window.PM11 = window.PM11 || {};

window.PM11.Projects = {
  async render() {
    const App = window.PM11.App, UI = window.PM11.UI;
    await App.loadProjects();

    const head = UI.pageHead(
      'Gerenciamento de Projetos',
      'Crie, abra, duplique e compare diferentes cenários de balanceamento.',
      '<button class="btn btn-primary" id="new-project">+ Novo Projeto Vazio</button>'
    );

    const cardsHtml = App.projects.map(p => {
      const isActive = p.id === App.projectId;
      const isLocked = Boolean(p.locked || p.is_locked);
      const statusLabel = `<span class="badge ${p.status === 'ARCHIVED' ? 'badge-inactive' : 'badge-active'}">ATIVO</span>${isLocked ? '<span class="badge badge-inactive" style="margin-left:5px;">🔒 TRANCADO</span>' : ''}`;
      
      return `
        <div class="project-card ${isActive ? 'active-border' : ''}" style="${isActive ? 'border-color: var(--primary-color); border-width: 2px;' : ''}">
          <div class="project-card-header">
            <div>
              <h3>${UI.esc(p.name)}</h3>
              <span style="font-size: 11px; color: var(--text-muted);">${UI.esc(p.area || 'Sem Área')} ${p.system_name ? `• ${UI.esc(p.system_name)}` : ''}</span>
            </div>
            <div style="display:flex; align-items:center; gap:4px;">
              ${statusLabel}
            </div>
          </div>
          <div class="project-card-body">
            <p>${UI.esc(p.description || 'Sem descrição cadastrada.')}</p>
            <div class="project-stats-grid">
              <div class="proj-stat-item">
                <span class="proj-stat-lbl">Planos</span>
                <span class="proj-stat-val">${p.plans_count || 0}</span>
              </div>
              <div class="proj-stat-item">
                <span class="proj-stat-lbl">Itens</span>
                <span class="proj-stat-val">${p.items_count || 0}</span>
              </div>
              <div class="proj-stat-item">
                <span class="proj-stat-lbl">Área</span>
                <span class="proj-stat-val" style="font-size:12px;">${UI.esc(p.area || '-')}</span>
              </div>
              <div class="proj-stat-item">
                <span class="proj-stat-lbl">Sistema</span>
                <span class="proj-stat-val" style="font-size:12px;">${UI.esc(p.system_name || '-')}</span>
              </div>
            </div>
          </div>
          <div class="project-card-footer">
            ${isActive ? 
              `<button class="btn btn-sm btn-secondary" disabled>Aberto</button>` : 
              `<button class="btn btn-sm btn-primary" onclick="window.PM11.App.setProject(${p.id})">Abrir</button>`
            }
            <button class="btn btn-sm ${isLocked ? 'btn-secondary' : 'btn-outline'}" onclick="window.PM11.Projects.lock(${p.id}, ${isLocked ? 0 : 1})" title="${isLocked ? 'Destrancar projeto e liberar edições' : 'Trancar projeto contra qualquer alteração'}">${isLocked ? '🔓 Destrancar' : '🔒 Trancar'}</button>
            <button class="btn btn-sm btn-outline" onclick="window.PM11.Projects.edit(${p.id})">Editar</button>
            <button class="btn btn-sm btn-outline" onclick="window.PM11.Projects.duplicate(${p.id})">Duplicar</button>
            <button class="btn btn-sm btn-danger" onclick="window.PM11.Projects.del(${p.id})" ${isActive ? 'disabled title="Não é possível excluir o projeto ativo"' : ''}>Excluir</button>
          </div>
        </div>
      `;
    }).join('');

    document.querySelector('#view').innerHTML = head + `<div class="project-cards-grid">${cardsHtml}</div>`;
    document.querySelector('#new-project').onclick = () => this.edit();
  },
  edit(id = null) {
    const App = window.PM11.App, UI = window.PM11.UI, API = window.PM11.API;
    const p = id ? App.projects.find(x => x.id === id) : {};
    UI.modal(id ? 'Editar Projeto' : 'Novo Projeto', `
      <div style="padding:4px;">
        <div class="form-group" style="margin-bottom:14px;">
          <label class="required" style="font-weight:600; margin-bottom:4px; display:block;">Nome do Projeto</label>
          <input type="text" class="control" name="name" value="${UI.esc(p?.name || '')}" placeholder="Ex.: PM11 Sinterização 3" required style="width:100%;">
        </div>
        <div class="form-row" style="display:flex; gap:12px; margin-bottom:14px;">
          <div class="form-group" style="flex:1;">
            <label style="font-weight:600; margin-bottom:4px; display:block;">Área / Subárea</label>
            <input type="text" class="control" name="area" value="${UI.esc(p?.area || '')}" placeholder="Ex.: Siderurgia" style="width:100%;">
          </div>
          <div class="form-group" style="flex:1;">
            <label style="font-weight:600; margin-bottom:4px; display:block;">Sistema / Linha</label>
            <input type="text" class="control" name="system_name" value="${UI.esc(p?.system_name || '')}" placeholder="Ex.: Linha 1, MS3..." style="width:100%;">
          </div>
        </div>
        <div class="form-group" style="margin-bottom:14px;">
          <label style="font-weight:600; margin-bottom:4px; display:block;">Descrição / Notas</label>
          <textarea class="control" name="description" rows="3" placeholder="Notas sobre este cenário de inspeção..." style="width:100%; min-height:70px;">${UI.esc(p?.description || '')}</textarea>
        </div>
        <div class="form-group" style="margin-bottom:6px;">
          <label style="font-weight:600; margin-bottom:4px; display:block;">Meta de inspeção diária (minutos)</label>
          <input type="number" class="control" name="daily_inspection_target_minutes" min="0" value="${p?.daily_inspection_target_minutes ?? 240}" style="width:200px;">
        </div>
      </div>
    `, {
      saveText: 'Salvar',
      onSave: async () => {
        const form = document.querySelector('#modal-body');
        const d = {
          name: form.querySelector('[name="name"]')?.value,
          area: form.querySelector('[name="area"]')?.value,
          system_name: form.querySelector('[name="system_name"]')?.value,
          description: form.querySelector('[name="description"]')?.value,
          daily_inspection_target_minutes: form.querySelector('[name="daily_inspection_target_minutes"]')?.value
        };
        if (!d.name) throw new Error('Informe o nome do Projeto.');
        d.daily_inspection_target_minutes = Number(d.daily_inspection_target_minutes || 240);
        const r = id ? await API.put('/api/projects/' + id, d) : await API.post('/api/projects', d);
        await App.loadProjects();
        if (!id) App.setProject(r.id, false);
        await this.render();
        UI.toast('Projeto salvo.');
      }
    });
  },
  async duplicate(id) {
    const App = window.PM11.App, UI = window.PM11.UI, API = window.PM11.API;
    const p = App.projects.find(x => x.id === id), name = prompt('Nome da cópia:', (p?.name || 'Projeto') + ' - CÓPIA');
    if (!name) return;
    UI.showLoader('Duplicando Projeto completo...');
    try {
      const r = await API.post('/api/projects/duplicate', { project_id: id, name });
      UI.toast('Projeto duplicado com Planos, Itens e Características.');
      await App.loadProjects();
      await this.render();
    } finally {
      UI.hideLoader();
    }
  },
  async lock(id, locked) {
    const App = window.PM11.App, UI = window.PM11.UI, API = window.PM11.API;
    await API.post('/api/projects/lock', { project_id: id, locked: !!locked });
    await App.loadProjects();
    await this.render();
    UI.toast(locked ? 'Projeto trancado.' : 'Projeto destrancado.');
  },
  async del(id) {
    const App = window.PM11.App, UI = window.PM11.UI, API = window.PM11.API;
    const p = App.projects.find(x => x.id === id);
    if (p?.locked) return UI.toast('Destranque o Projeto antes de excluir.', 'warn');
    if (!confirm(`Excluir o projeto “${p?.name || id}” e todos os dados vinculados?`)) return;
    await API.delete('/api/projects/' + id);
    if (App.projectId === id) {
      App.projectId = 0;
      localStorage.removeItem('pm11_project_id');
    }
    await App.loadProjects();
    await this.render();
  }
};
