window.PM11 = window.PM11 || {};

window.PM11.App = {
  projectId: Number(localStorage.getItem('pm11_project_id') || 0),
  view: 'dashboard',
  projects: [],
  async init() {
    try {
      document.querySelectorAll('.menu-item[data-view]').forEach(a => a.addEventListener('click', e => {
        if (window.currentMode && window.currentMode !== 'PM11') return;
        e.preventDefault();
        this.navigate(a.dataset.view);
      }));
      document.querySelector('#btn-global-undo')?.addEventListener('click', () => {
        if (window.currentMode === 'PM11') this.undo();
      });
      document.querySelector('#btn-global-redo')?.addEventListener('click', () => {
        if (window.currentMode === 'PM11') this.redo();
      });
      document.querySelector('#btn-switch-project-top')?.addEventListener('click', () => {
        if (window.currentMode === 'PM11') this.navigate('projects');
      });
      document.querySelector('#sidebar-toggle')?.addEventListener('click', () => document.querySelector('#sidebar')?.classList.toggle('collapsed'));
      document.querySelector('#menu-toggle-btn')?.addEventListener('click', () => document.querySelector('#sidebar')?.classList.toggle('mobile-open'));
      document.querySelector('#btn-shutdown')?.addEventListener('click', async () => {
        if (!confirm('Encerrar o servidor?')) return;
        try { await window.PM11.API.post('/api/shutdown', {}); } catch {}
        window.PM11.UI.toast('Servidor encerrado.', 'warn');
      });
      document.addEventListener('keydown', e => {
        if (window.currentMode !== 'PM11') return;
        const tag = document.activeElement?.tagName;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
          e.preventDefault();
          this.undo();
        }
        if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z')) && !['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
          e.preventDefault();
          this.redo();
        }
      });
      await this.loadProjects();
      if (!this.projectId && this.projects[0]) this.setProject(this.projects[0].id, false);
      const hash = (location.hash || '#dashboard').replace('#', '');
      const valid = ['dashboard', 'plans', 'items', 'characteristics', 'balance', 'templates', 'io', 'settings', 'projects'];
      await this.navigate(valid.includes(hash) ? hash : 'dashboard');
    } catch (e) {
      console.error('Falha ao iniciar PM11:', e);
      const v = document.querySelector('#view');
      if (v) v.innerHTML = `<div class="errorbox"><b>Erro ao iniciar PM11:</b> ${String(e?.message || e)}</div>`;
    }
  },
  async loadProjects() {
    this.projects = await window.PM11.API.get('/api/projects');
    if (this.projectId && !this.projects.some(p => p.id === this.projectId)) this.projectId = 0;
    this.updateProjectHeader();
  },
  setProject(id, navigate = true) {
    this.projectId = Number(id);
    localStorage.setItem('pm11_project_id', this.projectId);
    this.updateProjectHeader();
    if (navigate) this.navigate('dashboard');
  },
  updateProjectHeader() {
    if (window.currentMode && window.currentMode !== 'PM11') {
      if (window.App && typeof window.App.updateHeaderProjectBadge === 'function') {
        window.App.updateHeaderProjectBadge();
      }
      return;
    }
    const p = this.projects.find(x => x.id === this.projectId);
    const n = document.querySelector('#active-project-name'),
      c = document.querySelector('#active-project-items');
    if (n) n.textContent = p ? `PM11 - ${p.name}` : 'Nenhum projeto PM11';
    if (c) c.textContent = `${p?.items_count || 0} itens`;
  },
  async navigate(view) {
    if (window.currentMode && window.currentMode !== 'PM11') return;
    let loaderShown = false;
    try {
      if (!this.projectId && view !== 'projects') view = 'projects';
      this.view = view;
      location.hash = view;
      document.querySelectorAll('.menu-item[data-view]').forEach(a => a.classList.toggle('active', a.dataset.view === view));
      const modules = {
        dashboard: window.PM11.Dashboard,
        plans: window.PM11.Plans,
        items: window.PM11.Items,
        characteristics: window.PM11.Characteristics,
        balance: window.PM11.Balance,
        templates: window.PM11.Templates,
        io: window.PM11.IO,
        settings: window.PM11.Settings,
        projects: window.PM11.Projects
      };
      const mod = modules[view];
      if (!mod || typeof mod.render !== 'function') throw new Error(`Módulo da tela '${view}' não foi carregado.`);
      if (!window.PM11.UI || typeof window.PM11.UI.showLoader !== 'function') throw new Error('Módulo UI não foi carregado.');
      window.PM11.UI.showLoader('Carregando...');
      loaderShown = true;
      await mod.render();
      setTimeout(() => window.PM11.UI?.enhanceSelects?.(), 40);
    } catch (e) {
      console.error(`Erro na tela PM11 ${view}:`, e);
      const v = document.querySelector('#view');
      const msg = String(e?.message || e);
      if (v) v.innerHTML = `<div class="section-header-actions pm11-page-head"><div><h1>Erro</h1><p class="subtitle">Não foi possível carregar esta tela.</p></div></div><div class="errorbox"><b>Erro ao carregar:</b> ${window.PM11.UI?.esc ? window.PM11.UI.esc(msg) : msg}</div>`;
      window.PM11.UI?.toast?.(msg, 'error');
      window.PM11.API?.post?.('/api/logs', { context: view, message: `ERRO FRONTEND: ${e?.stack || msg}` }).catch(() => {});
    } finally {
      if (loaderShown) window.PM11.UI.hideLoader();
      await this.loadProjects().catch(() => {});
      await this.historyStatus();
    }
  },
  refresh() {
    return this.navigate(this.view);
  },
  async historyStatus() {
    if (window.currentMode && window.currentMode !== 'PM11') return;
    const u = document.querySelector('#btn-global-undo'),
      r = document.querySelector('#btn-global-redo');
    if (!this.projectId) {
      if (u) u.disabled = true;
      if (r) r.disabled = true;
      return;
    }
    try {
      const s = await window.PM11.API.get('/api/history/status');
      if (u) {
        u.disabled = !s.undo;
        u.title = s.undo ? `Desfazer: ${s.undo}` : 'Nada para desfazer';
      }
      if (r) {
        r.disabled = !s.redo;
        r.title = s.redo ? `Refazer: ${s.redo}` : 'Nada para refazer';
      }
    } catch {}
  },
  async undo() {
    if (!this.projectId) return;
    try {
      const r = await window.PM11.API.post('/api/history/undo', { project_id: this.projectId });
      window.PM11.UI.toast(r.ok ? `Desfeito: ${r.action}` : r.message, r.ok ? 'ok' : 'warn');
      await this.refresh();
    } catch (e) {
      window.PM11.UI.toast(e.message, 'error');
    }
  },
  async redo() {
    if (!this.projectId) return;
    try {
      const r = await window.PM11.API.post('/api/history/redo', { project_id: this.projectId });
      window.PM11.UI.toast(r.ok ? `Refeito: ${r.action}` : r.message, r.ok ? 'ok' : 'warn');
      await this.refresh();
    } catch (e) {
      window.PM11.UI.toast(e.message, 'error');
    }
  }
};
