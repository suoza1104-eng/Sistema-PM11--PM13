/**
 * Central SPA Router and Application Controller
 */

window.App = {
    currentProjectId: null,
    currentProjectName: '',
    currentCounter: 0,
    historyState: {
        canUndo: false,
        canRedo: false,
        undoLabel: '',
        redoLabel: '',
        undoCreatedAt: null,
        redoCreatedAt: null
    },
    historyBusy: false,
    historyStatusRequestId: 0,
    historyRefreshTimer: null,
    historyControlsInitialized: false,

    getValidProjectId() {
        if (this.currentProjectId && !isNaN(this.currentProjectId) && this.currentProjectId > 0) {
            return this.currentProjectId;
        }
        const stored = localStorage.getItem('currentProjectId');
        if (stored && stored !== 'null' && stored !== 'undefined') {
            const parsed = parseInt(stored, 10);
            if (!isNaN(parsed) && parsed > 0) {
                this.currentProjectId = parsed;
                return parsed;
            }
        }
        return null;
    },

    clearActiveProject() {
        this.currentProjectId = null;
        this.currentProjectName = '';
        this.currentCounter = 0;
        localStorage.removeItem('currentProjectId');
        localStorage.removeItem('currentProjectName');
        localStorage.removeItem('currentCounter');
        this.updateHeaderProjectBadge();
    },

    async validateStoredProject() {
        const projectId = this.getValidProjectId();
        if (!projectId) {
            this.clearActiveProject();
            return false;
        }

        try {
            const response = await fetch(`/api/projects/${projectId}`);
            if (!response.ok) {
                this.clearActiveProject();
                return false;
            }

            const project = await response.json();
            this.currentProjectName = project.name || '';
            this.currentCounter = Number.parseInt(project.current_counter, 10) || 0;
            localStorage.setItem('currentProjectName', this.currentProjectName);
            localStorage.setItem('currentCounter', String(this.currentCounter));
            this.updateHeaderProjectBadge();
            return true;
        } catch (error) {
            console.warn('Não foi possível validar o projeto armazenado.', error);
            this.clearActiveProject();
            return false;
        }
    },

    async init() {
        console.log("Inicializando SPA...");
        
        // 1. Restore only an explicitly selected project. There is no default project.
        let storedId = localStorage.getItem('currentProjectId');
        let parsedId = storedId && storedId !== 'null' && storedId !== 'undefined' ? parseInt(storedId, 10) : null;
        if (isNaN(parsedId) || parsedId <= 0) parsedId = null;
        
        this.currentProjectId = parsedId;
        this.currentProjectName = localStorage.getItem('currentProjectName') || '';
        
        let storedCounter = localStorage.getItem('currentCounter');
        this.currentCounter = storedCounter ? (parseInt(storedCounter, 10) || 0) : 0;

        this.updateHeaderProjectBadge();
        await this.validateStoredProject();
        this.initGlobalHistoryControls();

        // Initialize Standards Manager
        if (window.StandardsManager) {
            window.StandardsManager.init();
        }

        // Ensure all modal overlays are hidden on startup
        document.querySelectorAll('.modal-overlay').forEach(m => {
            m.classList.add('hidden');
            m.style.display = 'none';
        });

        // 2. Setup menu navigations and router
        window.addEventListener('hashchange', () => this.route());
        
        document.addEventListener('click', (e) => {
            const menuItem = e.target.closest('.menu-item');
            if (menuItem) {
                const targetHash = menuItem.getAttribute('href');
                if (targetHash && window.location.hash === targetHash) {
                    this.route();
                }
            }
        });
        
        // Collapsible Sidebar handlers
        const sidebar = document.getElementById('sidebar');
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const menuToggleBtn = document.getElementById('menu-toggle-btn');
        
        const toggleSidebar = () => {
            if (sidebar) sidebar.classList.toggle('collapsed');
        };
        if (sidebarToggle) sidebarToggle.onclick = toggleSidebar;
        if (menuToggleBtn) menuToggleBtn.onclick = toggleSidebar;

        // Header Switch Project button
        const btnSwitch = document.getElementById('btn-switch-project-top');
        if (btnSwitch) {
            btnSwitch.onclick = () => { window.location.hash = '#projects'; };
        }

        // Modal Confirmation Close triggers
        const btnClose = document.getElementById('btn-confirm-close');
        if (btnClose) btnClose.onclick = () => this.closeConfirmModal();
        const btnCancel = document.getElementById('btn-confirm-cancel');
        if (btnCancel) btnCancel.onclick = () => this.closeConfirmModal();

        // Global delegate listener for any modal close button (data-close or .modal-close)
        document.addEventListener('click', (e) => {
            const closeBtn = e.target.closest('[data-close], .modal-close');
            if (closeBtn) {
                const targetId = closeBtn.getAttribute('data-close');
                if (targetId) {
                    const targetModal = document.getElementById(targetId);
                    if (targetModal) targetModal.classList.add('hidden');
                } else {
                    const overlay = closeBtn.closest('.modal-overlay');
                    if (overlay) overlay.classList.add('hidden');
                }
            }
        });

        // Shutdown button
        const btnShutdown = document.getElementById('btn-shutdown');
        if (btnShutdown) {
            btnShutdown.onclick = () => {
                this.confirm("Encerrar Sistema", "Deseja realmente encerrar o servidor local?", async () => {
                    UI.showLoader("Encerrando servidor local...");
                    try {
                        const res = await API.post('/api/shutdown');
                        UI.showToast(res.message, "success", 10000);
                        setTimeout(() => {
                            document.body.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;"><h1>Sistema Encerrado</h1></div>`;
                        }, 1500);
                    } catch (err) {
                        UI.showToast("Falha ao encerrar o servidor.", "error");
                    } finally {
                        UI.hideLoader();
                    }
                });
            };
        }

        // Initialize CRUD views with try/catch blocks to ensure router NEVER fails
        try { if (window.Projects && window.Projects.init) window.Projects.init(); } catch (e) { console.warn("Projects.init:", e); }
        try { if (window.Plans && window.Plans.init) window.Plans.init(); } catch (e) { console.warn("Plans.init:", e); }
        try { if (window.Items && window.Items.init) window.Items.init(); } catch (e) { console.warn("Items.init:", e); }
        try { if (window.Balance && window.Balance.init) window.Balance.init(); } catch (e) { console.warn("Balance.init:", e); }
        try { if (window.ImportWizard && window.ImportWizard.init) window.ImportWizard.init(); } catch (e) { console.warn("ImportWizard.init:", e); }
        try { this.initSettingsAndBackupEvents(); } catch (e) { console.warn("initSettingsAndBackupEvents:", e); }

        // 3. Start routing immediately
        if (!window.location.hash) {
            window.location.hash = '#dashboard';
        } else {
            this.route();
        }

        // Periodically verify database status (heartbeat check)
        setInterval(() => {
            this.checkDatabaseHeartbeat();
            this.refreshHistoryStatus({ silent: true });
        }, 10000);
    },

    route() {
        if (window.currentMode === 'PM11') return;
        const hash = window.location.hash || '#dashboard';
        const projId = this.getValidProjectId();
        if (window.Logger) window.Logger.log(`route() called. hash=${hash}, projId=${projId}`, 'APP');
        
        // Navigation security: if no project is active, redirect to projects or import
        if (!projId && hash !== '#projects' && hash !== '#import' && hash !== '#backup') {
            window.location.hash = '#projects';
            UI.showToast("Por favor, abra ou crie um projeto para acessar esta tela.", "warning");
            return;
        }

        // Hide all modal overlays on route navigation or start
        document.querySelectorAll('.modal-overlay').forEach(m => {
            m.classList.add('hidden');
            m.style.display = '';
        });
        this.currentIssueContext = null;

        // Hide all sections
        const sections = document.querySelectorAll('.content-section');
        sections.forEach(s => s.classList.add('hidden'));

        // Toggle active menu items
        const menuItems = document.querySelectorAll('.menu-item');
        menuItems.forEach(item => item.classList.remove('active'));

        // Find active target menu item
        const baseHash = hash.split('?')[0];
        const routeMap = {
            '#dashboard': 'section-dashboard',
            '#plans': 'section-plans',
            '#items': 'section-items',
            '#operations': 'section-operations',
            '#long-texts': 'section-long-texts',
            '#balance': 'section-balance',
            '#standards': 'section-standards',
            '#priorimeter': 'section-priorimeter',
            '#projects': 'section-projects',
            '#import': 'section-import',
            '#history': 'section-history',
            '#backup': 'section-backup',
            '#settings': 'section-settings'
        };
        
        const activeMenu = Array.from(menuItems).find(item => item.getAttribute('href') === baseHash);
        if (activeMenu) {
            activeMenu.classList.add('active');
        }

        const targetId = (activeMenu && activeMenu.getAttribute('data-target')) || routeMap[baseHash] || 'section-dashboard';
        const section = document.getElementById(targetId);
        if (section) {
            section.classList.remove('hidden');
        }

        // Close sidebar drawer if open on navigation
        const drawer = document.getElementById('stop-details-drawer');
        if (drawer) drawer.classList.add('hidden');

        // Execute view-specific loaders safely
        if (baseHash === '#dashboard') {
            if (window.Dashboard && window.Dashboard.load) window.Dashboard.load();
        } else if (baseHash === '#plans') {
            if (window.Plans && window.Plans.load) window.Plans.load();
        } else if (baseHash === '#items') {
            if (window.Items && window.Items.load) window.Items.load();
        } else if (baseHash === '#operations') {
            if (window.Operations) { Operations.init(); window.Operations.loadOperations(); }
        } else if (baseHash === '#long-texts') {
            if (window.Operations) { Operations.init(); window.Operations.loadLongTexts(); }
        } else if (baseHash === '#balance') {
            if (window.Logger) window.Logger.log(`Routing to #balance: window.Balance exists? ${!!window.Balance}, load exists? ${!!(window.Balance && window.Balance.load)}`, 'APP');
            if (window.Balance && window.Balance.load) {
                window.Balance.load();
            } else {
                if (window.Logger) window.Logger.log("ERROR: window.Balance is not defined or has no load() method!", 'APP');
            }
        } else if (baseHash === '#priorimeter') {
            if (window.Priorimeter && window.Priorimeter.load) window.Priorimeter.load();
        } else if (baseHash === '#projects') {
            if (window.Projects && window.Projects.load) window.Projects.load();
        } else if (baseHash === '#import') {
            if (typeof ImportWizard !== 'undefined' && ImportWizard.currentStep === 5) {
                ImportWizard.reset();
            }
        } else if (baseHash === '#history') {
            this.loadHistoryLog();
        } else if (baseHash === '#backup') {
            this.loadBackupsList();
        } else if (baseHash === '#settings') {
            this.loadProjectSettings();
        }

        this.refreshHistoryStatus({ silent: true });
    },

    setActiveProject(id, name, counter) {
        const parsedId = parseInt(id, 10);
        if (isNaN(parsedId) || parsedId <= 0) return;

        this.currentProjectId = parsedId;
        this.currentProjectName = name || '';
        this.currentCounter = parseInt(counter, 10) || 0;

        localStorage.setItem('currentProjectId', this.currentProjectId);
        localStorage.setItem('currentProjectName', this.currentProjectName);
        localStorage.setItem('currentCounter', this.currentCounter);

        this.updateHeaderProjectBadge();
        this.refreshHistoryStatus({ silent: true });
        
        // Reset import wizard for the new active project
        if (typeof ImportWizard !== 'undefined' && ImportWizard.reset) {
            ImportWizard.reset();
        }
        
        // Reload current view
        this.route();
    },

    updateHeaderProjectBadge() {
        if (window.currentMode === 'PM11') {
            if (window.PM11 && window.PM11.App && typeof window.PM11.App.updateProjectHeader === 'function') {
                window.PM11.App.updateProjectHeader();
            }
            return;
        }
        const nameEl = document.getElementById('active-project-name');
        const counterEl = document.getElementById('active-project-counter');
        
        const pName = this.currentProjectName || localStorage.getItem('currentProjectName');
        const pCounter = (this.currentCounter != null && this.currentCounter !== '') ? this.currentCounter : (localStorage.getItem('currentCounter') || '-');

        if (nameEl) {
            nameEl.innerText = pName ? pName : "Nenhum Projeto PM13";
        }
        if (counterEl) {
            counterEl.innerText = pCounter;
        }
    },

    async checkDatabaseHeartbeat() {
        const dot = document.getElementById('db-status-dot');
        const text = document.getElementById('db-status-text');
        
        try {
            const res = await fetch('/api/health');
            if (res.ok) {
                if (dot) dot.className = 'status-dot green';
                if (text) text.innerText = 'Conectado';
            } else {
                if (dot) dot.className = 'status-dot red';
                if (text) text.innerText = 'Desconectado';
            }
        } catch (e) {
            if (dot) dot.className = 'status-dot red';
            if (text) text.innerText = 'Desconectado';
        }
    },

    // --- GLOBAL UNDO / REDO ---

    initGlobalHistoryControls() {
        if (this.historyControlsInitialized) return;
        this.historyControlsInitialized = true;

        const undoButton = document.getElementById('btn-global-undo');
        const redoButton = document.getElementById('btn-global-redo');
        if (undoButton) undoButton.addEventListener('click', () => this.performHistoryAction('undo'));
        if (redoButton) redoButton.addEventListener('click', () => this.performHistoryAction('redo'));

        document.addEventListener('keydown', event => {
            if (!(event.ctrlKey || event.metaKey) || event.altKey || this.isEditableHistoryTarget(event.target)) return;

            const key = String(event.key || '').toLowerCase();
            const wantsUndo = key === 'z' && !event.shiftKey;
            const wantsRedo = key === 'y' || (key === 'z' && event.shiftKey);
            if (!wantsUndo && !wantsRedo) return;

            event.preventDefault();
            this.performHistoryAction(wantsUndo ? 'undo' : 'redo');
        });

        this.installHistoryMutationObserver();
        this.updateGlobalHistoryControls();
        this.refreshHistoryStatus({ silent: true });
    },

    isEditableHistoryTarget(target) {
        if (!(target instanceof Element)) return false;
        if (target.isContentEditable) return true;
        return Boolean(target.closest('input, textarea, select, [contenteditable], [role="textbox"]'));
    },

    installHistoryMutationObserver() {
        if (typeof API === 'undefined' || API.__historyObserverInstalled) return;

        const app = this;
        const originalRequest = API.request.bind(API);
        API.__historyObserverInstalled = true;
        API.request = async function historyAwareRequest(url, options = {}) {
            const method = String(options.method || 'GET').toUpperCase();
            let succeeded = false;
            try {
                const result = await originalRequest(url, options);
                succeeded = true;
                return result;
            } finally {
                const path = String(url || '').split('?')[0];
                const isMutation = !['GET', 'HEAD', 'OPTIONS'].includes(method);
                const ignored = path.startsWith('/api/history/') || path === '/api/logs' || path === '/api/shutdown';
                if (succeeded && isMutation && !ignored) app.scheduleHistoryStatusRefresh();
            }
        };
    },

    scheduleHistoryStatusRefresh(delay = 180) {
        window.clearTimeout(this.historyRefreshTimer);
        this.historyRefreshTimer = window.setTimeout(() => {
            this.refreshHistoryStatus({ silent: true });
        }, delay);
    },

    normalizeHistoryStatus(payload) {
        const source = payload?.status || payload || {};
        return {
            canUndo: Boolean(source.can_undo ?? source.canUndo ?? source.undo?.available),
            canRedo: Boolean(source.can_redo ?? source.canRedo ?? source.redo?.available),
            undoLabel: String(source.undo_label ?? source.undo_action ?? source.undoLabel ?? source.undo?.label ?? ''),
            redoLabel: String(source.redo_label ?? source.redo_action ?? source.redoLabel ?? source.redo?.label ?? ''),
            undoCreatedAt: source.undo_created_at ?? source.undoCreatedAt ?? source.undo?.created_at ?? null,
            redoCreatedAt: source.redo_created_at ?? source.redoCreatedAt ?? source.redo?.created_at ?? null
        };
    },

    async refreshHistoryStatus({ silent = true } = {}) {
        const projectId = this.getValidProjectId();
        if (!projectId) {
            this.historyState = this.normalizeHistoryStatus(null);
            this.updateGlobalHistoryControls();
            return this.historyState;
        }

        const requestId = ++this.historyStatusRequestId;
        try {
            const result = await API.get('/api/history/status', { project_id: projectId });
            if (requestId !== this.historyStatusRequestId) return this.historyState;
            this.historyState = this.normalizeHistoryStatus(result);
            this.updateGlobalHistoryControls();
            return this.historyState;
        } catch (error) {
            if (requestId !== this.historyStatusRequestId) return this.historyState;
            this.historyState = this.normalizeHistoryStatus(null);
            this.updateGlobalHistoryControls();
            if (!silent) UI.showToast(`Não foi possível consultar o histórico: ${error.message}`, 'error');
            return this.historyState;
        }
    },

    updateGlobalHistoryControls() {
        const undoButton = document.getElementById('btn-global-undo');
        const redoButton = document.getElementById('btn-global-redo');
        const state = this.historyState || {};

        const configure = (button, action, available, label, shortcut) => {
            if (!button) return;
            const disabled = this.historyBusy || !available;
            button.disabled = disabled;
            button.setAttribute('aria-disabled', String(disabled));
            button.classList.toggle('is-busy', this.historyBusy);
            if (this.historyBusy) {
                button.title = action === 'undo' ? 'Desfazendo alteração...' : 'Refazendo alteração...';
            } else if (available) {
                button.title = `${action === 'undo' ? 'Desfazer' : 'Refazer'}${label ? `: ${label}` : ''} (${shortcut})`;
            } else {
                button.title = `Nada para ${action === 'undo' ? 'desfazer' : 'refazer'} (${shortcut})`;
            }
        };

        configure(undoButton, 'undo', state.canUndo, state.undoLabel, 'Ctrl+Z');
        configure(redoButton, 'redo', state.canRedo, state.redoLabel, 'Ctrl+Y');
    },

    async performHistoryAction(action) {
        const isUndo = action === 'undo';
        const available = isUndo ? this.historyState.canUndo : this.historyState.canRedo;
        if (this.historyBusy || !available) return;

        this.historyBusy = true;
        this.updateGlobalHistoryControls();
        UI.showLoader(isUndo ? 'Desfazendo a última alteração...' : 'Refazendo a alteração...');

        try {
            const result = await API.post(`/api/history/${action}`, { project_id: this.getValidProjectId() });
            if (result?.status) {
                this.historyState = this.normalizeHistoryStatus(result.status);
            } else {
                await this.refreshHistoryStatus({ silent: true });
            }
            await this.reloadActiveViewAfterHistory(action, result);
            UI.showToast(result?.message || (isUndo ? 'Alteração desfeita com sucesso.' : 'Alteração refeita com sucesso.'), 'success');
        } catch (error) {
            UI.showToast(`Erro ao ${isUndo ? 'desfazer' : 'refazer'}: ${error.message}`, 'error');
            await this.refreshHistoryStatus({ silent: true });
        } finally {
            this.historyBusy = false;
            this.updateGlobalHistoryControls();
            UI.hideLoader();
        }
    },

    async reloadActiveViewAfterHistory(action, result) {
        document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(modal => modal.classList.add('hidden'));

        // Project name/counter also belong to the restored snapshot. Refresh
        // the cached header state before repainting the active screen.
        const activeProjectId = this.getValidProjectId();
        if (activeProjectId) {
            try {
                const project = await API.get(`/api/projects/${activeProjectId}`);
                this.currentProjectName = project?.name || this.currentProjectName;
                this.currentCounter = Number.parseInt(project?.current_counter, 10) || 0;
                localStorage.setItem('currentProjectName', this.currentProjectName);
                localStorage.setItem('currentCounter', String(this.currentCounter));
                this.updateHeaderProjectBadge();
            } catch (error) {
                console.warn('Não foi possível atualizar o cabeçalho após restaurar o histórico.', error);
            }
        }

        if (window.Balance) {
            if (Array.isArray(window.Balance.history)) window.Balance.history = [];
            if (Array.isArray(window.Balance.undoStack)) window.Balance.undoStack = [];
            if (Array.isArray(window.Balance.redoStack)) window.Balance.redoStack = [];
            if (typeof window.Balance.updateUndoRedoButtons === 'function') window.Balance.updateUndoRedoButtons();
        }

        const baseHash = (window.location.hash || '#dashboard').split('?')[0];
        this.route();
        if (baseHash === '#standards' && window.StandardsManager?.loadAll) {
            await window.StandardsManager.loadAll();
        }

        window.dispatchEvent(new CustomEvent('app:history-restored', {
            detail: { action, result, projectId: this.getValidProjectId() }
        }));
    },

    // --- GLOBAL DIALOG HELPERS ---
    
    confirm(title, message, okCallback) {
        document.getElementById('confirm-title').innerText = title;
        document.getElementById('confirm-message').innerHTML = message;
        
        const confirmModal = document.getElementById('modal-confirm');
        confirmModal.classList.remove('hidden');

        const okBtn = document.getElementById('btn-confirm-ok');
        
        // Remove existing listener by replacing button (standard JS trick)
        const newOkBtn = okBtn.cloneNode(true);
        okBtn.parentNode.replaceChild(newOkBtn, okBtn);

        newOkBtn.onclick = async () => {
            const shouldClose = await okCallback();
            if (shouldClose !== false) {
                this.closeConfirmModal();
            }
        };
    },

    closeConfirmModal() {
        document.getElementById('modal-confirm').classList.add('hidden');
        document.getElementById('confirm-extra-content').innerHTML = ''; // Clean
    },

    showBulkProgressModal(title, statusMsg) {
        const modal = document.getElementById('modal-bulk-progress');
        if (!modal) return;
        document.getElementById('bulk-progress-spinner-container')?.classList.remove('hidden');
        document.getElementById('bulk-progress-icon-success')?.classList.add('hidden');
        document.getElementById('bulk-progress-icon-error')?.classList.add('hidden');
        document.getElementById('bulk-progress-actions')?.classList.add('hidden');
        
        const titleEl = document.getElementById('bulk-progress-title');
        const statusEl = document.getElementById('bulk-progress-status');
        const barFill = document.getElementById('bulk-progress-bar-fill');
        
        if (titleEl) titleEl.textContent = title;
        if (statusEl) statusEl.innerHTML = statusMsg;
        if (barFill) {
            barFill.style.width = '35%';
            barFill.style.background = 'linear-gradient(90deg, #3b82f6, #6366f1)';
        }
        modal.classList.remove('hidden');
    },

    updateBulkProgressModal(percent, statusMsg) {
        const statusEl = document.getElementById('bulk-progress-status');
        const barFill = document.getElementById('bulk-progress-bar-fill');
        if (statusEl && statusMsg) statusEl.innerHTML = statusMsg;
        if (barFill) barFill.style.width = `${percent}%`;
    },

    finishBulkProgressModal(isSuccess, title, resultMsg) {
        const spinner = document.getElementById('bulk-progress-spinner-container');
        const iconSuccess = document.getElementById('bulk-progress-icon-success');
        const iconError = document.getElementById('bulk-progress-icon-error');
        const titleEl = document.getElementById('bulk-progress-title');
        const statusEl = document.getElementById('bulk-progress-status');
        const barFill = document.getElementById('bulk-progress-bar-fill');
        const actions = document.getElementById('bulk-progress-actions');

        if (spinner) spinner.classList.add('hidden');
        if (isSuccess) {
            if (iconSuccess) iconSuccess.classList.remove('hidden');
            if (barFill) {
                barFill.style.width = '100%';
                barFill.style.background = 'var(--success-color, #10b981)';
            }
        } else {
            if (iconError) iconError.classList.remove('hidden');
            if (barFill) {
                barFill.style.width = '100%';
                barFill.style.background = 'var(--danger-color, #ef4444)';
            }
        }
        if (titleEl) titleEl.textContent = title;
        if (statusEl) statusEl.innerHTML = resultMsg;
        if (actions) actions.classList.remove('hidden');
    },

    async preserveScroll(targetElementOrId, asyncTask) {
        let container = typeof targetElementOrId === 'string'
            ? document.getElementById(targetElementOrId)
            : targetElementOrId;
        
        const scrollTarget = container?.closest('.table-responsive-container') || container || document.documentElement;
        const savedScrollTop = scrollTarget ? scrollTarget.scrollTop : 0;
        const savedWindowScrollY = window.scrollY;

        try {
            return await asyncTask();
        } finally {
            requestAnimationFrame(() => {
                if (scrollTarget && savedScrollTop > 0) {
                    scrollTarget.scrollTop = savedScrollTop;
                }
                if (savedWindowScrollY > 0) {
                    window.scrollTo(0, savedWindowScrollY);
                }
            });
        }
    },

    openStopDetailsDrawer(stopCounter) {
        // Delegate to Balance controller
        Balance.openStopDetails(stopCounter);
    },

    // --- AUDIT HISTORY LOADER ---
    async loadHistoryLog() {
        UI.showLoader("Carregando histórico de auditoria...");
        try {
            const logs = await API.get('/api/audit', { project_id: this.currentProjectId, limit: 100 });
            const tbody = document.getElementById('audit-table-body');
            tbody.innerHTML = '';

            if (logs.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="empty-table-cell">Nenhuma alteração registrada no histórico deste projeto.</td></tr>`;
                return;
            }

            logs.forEach(l => {
                const date = new Date(l.created_at + 'Z').toLocaleString('pt-BR');
                const prev = l.previous_data_json ? JSON.stringify(JSON.parse(l.previous_data_json), null, 2) : '';
                const next = l.new_data_json ? JSON.stringify(JSON.parse(l.new_data_json), null, 2) : '';
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${date}</td>
                    <td><span class="badge badge-active">${l.entity_type}</span></td>
                    <td>${l.entity_id}</td>
                    <td><strong>${l.action}</strong></td>
                    <td style="font-family:monospace; font-size:11px; max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:pre-wrap;">${prev}</td>
                    <td style="font-family:monospace; font-size:11px; max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:pre-wrap;">${next}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            UI.showToast(`Erro ao carregar histórico: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    // --- SETTINGS AND BACKUPS LOADER ---
    initSettingsAndBackupEvents() {
        const btnAddCycle = document.getElementById('btn-add-cycle-setting');
        if (btnAddCycle) btnAddCycle.onclick = () => this.addCycleRowInput('', 'PRD', '', 35);

        const btnSaveSet = document.getElementById('btn-save-project-settings');
        if (btnSaveSet) btnSaveSet.onclick = () => this.saveProjectSettings();
        ['settings-hours-per-person', 'settings-tool-time'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.oninput = () => this.updateCapacityPreview();
        });

        const btnCreateBackup = document.getElementById('btn-create-backup');
        if (btnCreateBackup) {
            btnCreateBackup.onclick = () => {
                const suffix = prompt("Digite um nome/descrição curta para este backup (opcional):");
                if (suffix === null) return;
                this.createBackup(suffix.trim());
            };
        }
    },

    async loadProjectSettings() {
        UI.showLoader("Carregando configurações...");
        try {
            const capacity = await API.get(`/api/projects/${this.currentProjectId}/work-capacity`);
            const hoursInput = document.getElementById('settings-hours-per-person');
            const toolInput = document.getElementById('settings-tool-time');
            if (hoursInput) hoursInput.value = Number(capacity.hours_per_person ?? 9.1).toFixed(1);
            if (toolInput) toolInput.value = Number(capacity.tool_time_percent ?? 100).toFixed(1);
            this.updateCapacityPreview();

            const cycles = await API.get('/api/cycles', { project_id: this.currentProjectId });
            const tbody = document.getElementById('settings-cycles-tbody');
            tbody.innerHTML = '';
            cycles.forEach(c => this.addCycleRowInput(c.cycle, c.unit, c.cycle_text, c.opening_horizon));
            if (cycles.length === 0) {
                for (let i = 1; i <= 20; i++) {
                    const text = i === 1 ? 'PARADA' : `${i} PARADAS`;
                    this.addCycleRowInput(i, 'PRD', text, 100);
                }
            }
        } catch (err) {
            UI.showToast(`Erro ao carregar configurações: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    updateCapacityPreview() {
        const hours = parseFloat(String(document.getElementById('settings-hours-per-person')?.value || '9.1').replace(',', '.'));
        const tool = parseFloat(String(document.getElementById('settings-tool-time')?.value || '100').replace(',', '.'));
        const productive = (Number.isFinite(hours) ? hours : 9.1) * ((Number.isFinite(tool) ? tool : 100) / 100);
        const out = document.getElementById('settings-productive-hours-preview');
        if (out) out.textContent = `${productive.toFixed(2).replace('.', ',')} HH/pessoa`;
    },

    addCycleRowInput(cycle, unit, text, horizon) {
        const tbody = document.getElementById('settings-cycles-tbody');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input type="number" class="cycle-input-val" value="${cycle}" style="width:70px;" required></td>
            <td><input type="text" class="cycle-input-unit" value="${unit}" style="width:60px;" required></td>
            <td><input type="text" class="cycle-input-text" value="${text}" required></td>
            <td><input type="number" step="0.1" class="cycle-input-horizon" value="${horizon}" style="width:80px;" required></td>
            <td><button class="btn btn-icon" onclick="this.closest('tr').remove()">✕</button></td>
        `;
        tbody.appendChild(tr);
    },

    async saveProjectSettings() {
        const projId = this.currentProjectId;
        if (!projId) return;

        const hoursRaw = String(document.getElementById('settings-hours-per-person')?.value || '').replace(',', '.');
        const toolRaw = String(document.getElementById('settings-tool-time')?.value || '').replace(',', '.');
        const hours = parseFloat(hoursRaw);
        const toolTime = parseFloat(toolRaw);
        if (!Number.isFinite(hours) || hours <= 0 || hours > 24) {
            UI.showToast('Horas trabalhadas por pessoa deve ser maior que 0 e no máximo 24.', 'error');
            return;
        }
        if (!Number.isFinite(toolTime) || toolTime <= 0 || toolTime > 100) {
            UI.showToast('Tool Time deve ser maior que 0% e no máximo 100%.', 'error');
            return;
        }

        const cycleRows = document.querySelectorAll('#settings-cycles-tbody tr');
        const cycles = [];
        for (let tr of cycleRows) {
            const cycleVal = parseInt(tr.querySelector('.cycle-input-val').value);
            const unit = tr.querySelector('.cycle-input-unit').value.trim();
            const text = tr.querySelector('.cycle-input-text').value.trim();
            const horiz = parseFloat(tr.querySelector('.cycle-input-horizon').value);
            if (isNaN(cycleVal) || !unit || !text || isNaN(horiz)) {
                UI.showToast("Preencha todos os campos do catálogo de ciclos.", "error");
                return;
            }
            cycles.push({ cycle: cycleVal, unit: unit, cycle_text: text, opening_horizon: horiz });
        }

        UI.showLoader("Gravando configurações...");
        try {
            await API.put(`/api/projects/${projId}/work-capacity`, {
                hours_per_person: hours,
                tool_time_percent: toolTime
            });
            await API.put('/api/cycles', { project_id: projId, cycles: cycles });
            this.updateCapacityPreview();
            UI.showToast("Configurações do projeto salvas com sucesso!");
        } catch (err) {
            UI.showToast(`Erro ao gravar configurações: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    // --- BACKUP ACTIONS ---
    async loadBackupsList() {
        UI.showLoader("Carregando backups...");
        try {
            const backups = await API.get('/api/backups');
            const tbody = document.getElementById('backup-table-body');
            tbody.innerHTML = '';

            if (backups.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="empty-table-cell">Nenhum arquivo de backup encontrado na pasta backups/.</td></tr>`;
                return;
            }

            backups.forEach(b => {
                const date = new Date(b.created_at).toLocaleString('pt-BR');
                const sizeMb = (b.size_bytes / (1024 * 1024)).toFixed(2);
                
                // Format projects summary list in metadata
                let projSummary = '-';
                if (b.metadata && b.metadata.projects) {
                    projSummary = b.metadata.projects.map(p => `${p.name} (${p.plans_count} planos, ${p.items_count} itens)`).join('<br>');
                }

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${b.filename}</strong></td>
                    <td>${date}</td>
                    <td>${sizeMb} MB</td>
                    <td style="font-size:11px; line-height:1.4;">${projSummary}</td>
                    <td>
                        <div class="actions-cell">
                            <button class="btn btn-xs btn-primary" onclick="window.App.restoreBackup('${b.filename}')">Restaurar</button>
                            <button class="btn btn-xs btn-danger" onclick="window.App.deleteBackup('${b.filename}')">Excluir</button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) {
            UI.showToast(`Erro ao carregar backups: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async createBackup(suffix) {
        UI.showLoader("Criando arquivo de backup...");
        try {
            await API.post('/api/backups', { suffix: suffix });
            UI.showToast("Backup criado com sucesso e salvo em backups/ !");
            await this.loadBackupsList();
        } catch (err) {
            UI.showToast(`Erro ao criar backup: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    restoreBackup(filename) {
        this.confirm("Restaurar Backup", `Tem certeza que deseja restaurar o backup "${filename}"?<br><br><span class="txt-danger" style="font-weight:700;">Atenção: A base de dados atual será completamente sobrescrita!</span><br><br>Um backup automático de segurança será criado antes da restauração. O servidor e a página serão recarregados após o término.`, async () => {
            UI.showLoader("Restaurando banco de dados...");
            try {
                await API.post('/api/backups/restore', { filename: filename });
                UI.showToast("Backup restaurado com sucesso! Recarregando aplicação...");
                setTimeout(() => {
                    // Reset localStorage state as database projects may have changed IDs
                    localStorage.clear();
                    window.location.reload();
                }, 2000);
            } catch (err) {
                UI.showToast(`Erro ao restaurar backup: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    deleteBackup(filename) {
        this.confirm("Excluir Backup", `Tem certeza que deseja deletar permanentemente o arquivo de backup "${filename}"?`, async () => {
            UI.showLoader("Excluindo backup...");
            try {
                await API.delete('/api/backups', { filename: filename });
                UI.showToast("Backup excluído com sucesso!");
                await window.App.loadBackupsList();
            } catch (err) {
                UI.showToast(`Erro ao excluir backup: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    // ==========================================
    // DIAGNOSTIC & AUTOMATIC ISSUE FIX MODAL
    // ==========================================
    currentIssueContext: null,

    async openIssueFixModal(type, id) {
        const modal = document.getElementById('modal-issue-fix');
        if (!modal) return;

        const iconEl = document.getElementById('issue-modal-icon');
        const titleEl = document.getElementById('issue-modal-title');
        const subtitleEl = document.getElementById('issue-modal-subtitle');
        const typeEl = document.getElementById('issue-modal-entity-type');
        const nameEl = document.getElementById('issue-modal-entity-name');
        const msgsContainer = document.getElementById('issue-modal-messages-container');
        const fixBox = document.getElementById('issue-modal-fix-box');
        const fixDesc = document.getElementById('issue-modal-fix-description');
        const applyBtn = document.getElementById('btn-apply-issue-fix');

        msgsContainer.innerHTML = '<div style="color:var(--text-muted); font-size:12px;">Carregando diagnóstico...</div>';
        fixBox.style.display = 'none';
        applyBtn.disabled = true;

        modal.classList.remove('hidden');
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');

        try {
            let entity = null;
            let issues = [];
            let fixAction = null;

            if (type === 'operation') {
                const ops = window.Operations ? window.Operations.currentOperations : [];
                entity = ops.find(o => Number(o.id) === Number(id));
                if (entity) {
                    typeEl.textContent = 'OPERAÇÃO SAP';
                    nameEl.textContent = `[ID ${entity.legacy_identifier}] OP ${entity.operation_code}${entity.suboperation_code ? '/' + entity.suboperation_code : ''} — ${entity.short_text || entity.item_description || ''}`;
                    issues = entity.validation_issues || [];

                    // 1. Check for standard 0010 title mismatch fix (e.g. MECÂNICOS SOLDADORES OU SOLDADOR)
                    const code = String(entity.operation_code || '').padStart(4, '0');
                    const sub = String(entity.suboperation_code || '').padStart(4, '0');
                    const STANDARD_TITLES = {
                        '0010': 'MECÂNICO SOLDADOR OU SOLDADOR',
                        '0011': 'SUPERVISOR OU LIDER DE GRUPO',
                        '0012': 'RECOMENDAÇÕES SEGURANÇA E MEIO AMBIENTE',
                        '0013': 'ATIVIDADES DE PREPARAÇÃO',
                        '0014': 'DOCUMENTOS TÉCNICOS'
                    };

                    if (code === '0010' && STANDARD_TITLES[sub]) {
                        const expected = STANDARD_TITLES[sub];
                        const norm = s => (s || '').toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
                        if (norm(entity.short_text) !== norm(expected)) {
                            fixAction = {
                                label: `Alterar Título Breve de "${entity.short_text}" para o Padrão Corporativo SAP "${expected}"`,
                                execute: async () => {
                                    await API.put(`/api/operations/${entity.id}`, { short_text: expected });
                                    UI.showToast(`Título breve atualizado com sucesso para "${expected}"!`);
                                    if (window.Operations) window.Operations.loadOperations();
                                }
                            };
                        }
                    }

                    // 2. Header 0010 must be only the operation title. If an imported/legacy
                    // long text exists there, the compliant correction is to REMOVE the long-text
                    // record(s), not to leave an empty placeholder.
                    if (!fixAction && issues.some(i => i.code === 'header_has_long_text')) {
                        fixAction = {
                            label: 'Remover o(s) Texto(s) Longo(s) indevidamente vinculados ao 0010 principal (o título da operação será preservado)',
                            execute: async () => {
                                const projectId = this.getValidProjectId();
                                const response = await API.get(`/api/long-texts?project_id=${projectId}&operation_id=${entity.id}&limit=all`);
                                const texts = Array.isArray(response) ? response : (response.long_texts || []);
                                const ids = texts.map(t => Number(t.id)).filter(Number.isFinite);
                                if (!ids.length) {
                                    UI.showToast('Nenhum Texto Longo existente foi encontrado para remover.', 'info');
                                } else {
                                    for (const textId of ids) {
                                        await API.delete(`/api/long-texts/${textId}`);
                                    }
                                    UI.showToast(`${ids.length} Texto(s) Longo(s) removido(s). O 0010 principal ficou somente como título.`, 'success');
                                }
                                if (window.Operations) {
                                    await Promise.all([window.Operations.loadOperations(), window.Operations.loadLongTexts()]);
                                    if (window.Operations.sapItemId && !document.getElementById('modal-sap-order')?.classList.contains('hidden')) {
                                        await window.Operations.openSapOrder(window.Operations.sapItemId);
                                    }
                                }
                            }
                        };
                    }

                    // 3. Check for missing long text
                    if (!fixAction && issues.some(i => i.code === 'missing_long_text')) {
                        fixAction = {
                            label: `Revalidar o Texto Longo e, se estiver realmente vazio, abrir a ordem para preenchimento`,
                            execute: async () => {
                                const projectId = this.getValidProjectId();
                                const result = await API.post('/api/validation/revalidate', {
                                    project_id: projectId,
                                    item_id: entity.item_id
                                });
                                if (window.Operations) {
                                    await Promise.all([window.Operations.loadOperations(), window.Operations.loadLongTexts()]);
                                }
                                if (result.missing_long_text_resolved) {
                                    UI.showToast('Texto Longo confirmado. O alerta incorreto foi removido.', 'success');
                                } else {
                                    UI.showToast('O Texto Longo continua vazio. A ordem foi aberta para preenchimento.', 'warning');
                                    if (window.Operations && entity.item_id) {
                                        await window.Operations.openSapOrder(entity.item_id);
                                    }
                                }
                            }
                        };
                    }
                    if (!fixAction && issues.some(i => i.code === 'long_text_without_operation')) {
                        fixAction = {
                            label: 'Editar e confirmar esta operação provisória como vínculo válido',
                            execute: async () => {
                                this.closeIssueFixModal();
                                if (window.Operations) window.Operations.openEditModal(entity.id);
                            }
                        };
                    }
                }
            } else if (type === 'item') {
                const items = window.Items ? window.Items.currentItems : [];
                entity = items.find(i => Number(i.id) === Number(id));
                if (entity) {
                    typeEl.textContent = 'ITEM DE MANUTENÇÃO';
                    nameEl.textContent = `[ID ${entity.legacy_identifier}] ${entity.description || entity.object_code || ''}`;
                    
                    if (entity.validation_issues_json) {
                        try {
                            const parsed = typeof entity.validation_issues_json === 'string' ? JSON.parse(entity.validation_issues_json) : entity.validation_issues_json;
                            if (Array.isArray(parsed)) issues.push(...parsed);
                        } catch(_) {}
                    }
                    if (entity.plan_id === null) issues.push({ severity: 'WARNING', message: 'Item sem plano de reparo associado.' });
                    if (entity.headcount === null || entity.headcount === 0) issues.push({ severity: 'WARNING', message: 'Item sem efetivo/homens definido.' });
                    if (entity.character_count > 35) issues.push({ severity: 'WARNING', message: `Descrição extensa (${entity.character_count} caract. > 35).` });

                    const updates = {};
                    const labels = [];

                    const hasMissingLongText = issues.some(i => i.code === 'missing_long_text');
                    const hasRule5Prd = issues.some(i => (i.message || '').includes('PRD exige condição M'));
                    const hasRule5Sms = issues.some(i => (i.message || '').includes('SMS exige condição'));
                    const hasRule6Prio = issues.some(i => (i.message || '').includes('Regra 6') || (i.field === 'priority' && (!i.priority || Number(i.priority) === 0)));

                    if (hasRule5Prd) {
                        updates.condition_code = 'M';
                        labels.push("Condição Operacional = 'M'");
                    } else if (hasRule5Sms) {
                        updates.condition_code = 'P';
                        labels.push("Condição Operacional = 'P'");
                    }

                    if (hasRule6Prio || entity.priority === null || entity.priority === undefined || Number(entity.priority) === 0) {
                        updates.priority = 1;
                        labels.push("Prioridade PM13 = 1");
                    }

                    if (entity.headcount === null || entity.headcount === 0) {
                        updates.headcount = 1;
                        labels.push("Efetivo = 1");
                    }

                    if (entity.character_count > 35) {
                        const trimmed = (entity.description || '').substring(0, 35).trim();
                        updates.description = trimmed;
                        labels.push(`Descrição cortada para 35 caract. ("${trimmed}")`);
                    }

                    if (Object.keys(updates).length > 0) {
                        fixAction = {
                            label: `Aplicar correções de conformidade SAP: ${labels.join(', ')}`,
                            execute: async () => {
                                await API.put(`/api/items/${entity.id}`, updates);
                                UI.showToast('Item corrigido com sucesso para a conformidade SAP!', 'success');
                                if (window.Items) await window.Items.load();
                            }
                        };
                    } else if (hasMissingLongText) {
                        fixAction = {
                            label: 'Revalidar os Textos Longos deste item e remover o alerta caso o conteúdo já esteja preenchido',
                            execute: async () => {
                                const projectId = this.getValidProjectId();
                                const result = await API.post('/api/validation/revalidate', {
                                    project_id: projectId,
                                    item_id: entity.id
                                });
                                if (window.Items) await window.Items.load();
                                if (!result.missing_long_text_resolved) {
                                    throw new Error('A revalidacao confirmou que ainda existe Texto Longo obrigatorio sem conteudo.');
                                }
                                UI.showToast('Texto Longo confirmado. O alerta incorreto foi removido.', 'success');
                            }
                        };
                    } else if (entity.plan_id === null) {
                        fixAction = {
                            label: `Abrir popup para selecionar e vincular um plano a este item`,
                            execute: async () => {
                                this.closeIssueFixModal();
                                if (window.Items) window.Items.openPlanPicker(null, entity.id, null);
                            }
                        };
                    }
                }
            } else if (type === 'plan') {
                const plans = window.Plans ? window.Plans.currentPlans : [];
                entity = plans.find(p => Number(p.id) === Number(id));
                if (entity) {
                    typeEl.textContent = 'PLANO DE REPARO';
                    nameEl.textContent = `[${entity.legacy_code}] ${entity.description || ''}`;

                    if (entity.character_count > 40) issues.push({ severity: 'WARNING', message: `Descrição do plano extensa (${entity.character_count} caract. > 40).` });
                    if (entity.items_count === 0) issues.push({ severity: 'WARNING', message: 'Plano sem nenhum item de manutenção associado.' });
                    if (!entity.phase || entity.phase <= 0) issues.push({ severity: 'WARNING', message: 'Plano sem parada de início / contador de referência configurado.' });

                    if (entity.character_count > 40) {
                        const trimmed = (entity.description || '').substring(0, 40).trim();
                        fixAction = {
                            label: `Ajustar descrição do plano para limite de 40 caracteres: "${trimmed}"`,
                            execute: async () => {
                                await API.put(`/api/plans/${entity.id}`, { description: trimmed });
                                UI.showToast('Descrição do plano ajustada para 40 caracteres!');
                                if (window.Plans) window.Plans.load();
                            }
                        };
                    } else if (!entity.phase || entity.phase <= 0) {
                        fixAction = {
                            label: `Definir Parada de Início Inicial Padrão = P1`,
                            execute: async () => {
                                await API.put(`/api/plans/${entity.id}`, { phase: 1 });
                                UI.showToast('Parada de início do plano configurada para P1!');
                                if (window.Plans) window.Plans.load();
                            }
                        };
                    }
                }
            } else if (type === 'long-text') {
                const lts = window.Operations ? window.Operations.currentLongTexts : [];
                entity = lts.find(t => t.id === id || t.long_text_id === id);
                if (entity) {
                    typeEl.textContent = 'TEXTO LONGO';
                    nameEl.textContent = `[ID ${entity.legacy_identifier || entity.id}] OP ${entity.operation_code || '-'} — ${entity.item_description || entity.op_short_text || ''}`;
                    issues = Array.isArray(entity.validation_issues) && entity.validation_issues.length ? entity.validation_issues : (entity.computed_issues || []);

                    const isFirst0010 = (entity.operation_code === '0010' && (!entity.suboperation_code || ['','0000','-','None'].includes(String(entity.suboperation_code).trim())));

                    if (isFirst0010 && String(entity.text || '').trim() !== '') {
                        fixAction = {
                            label: 'Limpar texto longo da operação 0010 (deixar em branco conforme regra PM13)',
                            execute: async () => {
                                const ltId = entity.long_text_id || entity.id;
                                if (ltId) {
                                    await API.put(`/api/long-texts/${ltId}`, { text: '' });
                                } else if (entity.operation_id) {
                                    const projectId = this.getValidProjectId();
                                    const response = await API.get(`/api/long-texts?project_id=${projectId}&operation_id=${entity.operation_id}&limit=all`);
                                    const texts = Array.isArray(response) ? response : (response.long_texts || []);
                                    for (const t of texts) {
                                        if (t.id) await API.put(`/api/long-texts/${t.id}`, { text: '' });
                                    }
                                }
                                UI.showToast('Texto longo limpo com sucesso!', 'success');
                                if (window.Operations) await window.Operations.loadLongTexts();
                            }
                        };
                    } else if (!isFirst0010 && (!entity.text || String(entity.text).trim() === '')) {
                        fixAction = {
                            label: 'Abrir editor para preencher o texto longo obrigatório desta operação',
                            execute: async () => {
                                this.closeIssueFixModal();
                                if (window.Operations) window.Operations.openEditLongTextModal(entity.long_text_id || entity.id);
                            }
                        };
                    } else if (!entity.operation_id) {
                        fixAction = {
                            label: `Abrir modal de edição para re-vincular a operação correta`,
                            execute: async () => {
                                this.closeIssueFixModal();
                                if (window.Operations) window.Operations.openEditLongTextModal(entity.id);
                            }
                        };
                    } else if (issues.some(i => i.code === 'long_text_without_operation')) {
                        fixAction = {
                            label: 'Editar e confirmar a operação provisória deste texto',
                            execute: async () => {
                                this.closeIssueFixModal();
                                if (window.Operations) window.Operations.openEditModal(entity.operation_id);
                            }
                        };
                    }
                }
            }

            this.currentIssueContext = { type, id, fixAction };

            if (!issues || issues.length === 0) {
                msgsContainer.innerHTML = '<div style="color:var(--text-muted); font-size:13px;">Nenhuma inconsistência ativa detectada para este registro.</div>';
            } else {
                msgsContainer.innerHTML = issues.map(i => {
                    const isErr = i.severity === 'ERROR';
                    return `
                        <div style="background: ${isErr ? '#FEF2F2' : '#FFFBEB'}; border: 1px solid ${isErr ? '#FCA5A5' : '#FDE68A'}; border-radius: 6px; padding: 10px 12px; display: flex; align-items: flex-start; gap: 8px;">
                            <span style="font-size: 14px;">${isErr ? '⛔' : '⚠️'}</span>
                            <div style="font-size: 12px; color: ${isErr ? '#991B1B' : '#92400E'}; font-weight: 500; line-height: 1.4;">
                                ${i.message}
                            </div>
                        </div>
                    `;
                }).join('');
            }

            if (fixAction) {
                fixBox.style.display = 'block';
                fixDesc.textContent = fixAction.label;
                applyBtn.disabled = false;
            } else {
                fixBox.style.display = 'none';
                applyBtn.disabled = true;
            }

        } catch (err) {
            msgsContainer.innerHTML = `<div style="color:var(--danger-color); font-size:12px;">Erro ao carregar diagnósticos: ${err.message}</div>`;
        }
    },

    closeIssueFixModal() {
        const modal = document.getElementById('modal-issue-fix');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
            modal.setAttribute('aria-hidden', 'true');
        }
        document.querySelectorAll('#modal-issue-fix, .modal-overlay[data-transient="true"]').forEach(m => {
            m.classList.add('hidden');
            m.style.display = 'none';
        });
        this.currentIssueContext = null;
    },

    async applyIssueFix() {
        if (!this.currentIssueContext || !this.currentIssueContext.fixAction) {
            this.closeIssueFixModal();
            return;
        }
        const fix = this.currentIssueContext.fixAction;
        UI.showLoader('Aplicando correção automática...');
        try {
            await fix.execute();
        } catch (err) {
            UI.showToast(`Erro ao aplicar correção: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
            this.closeIssueFixModal();
        }
    }
};

// Global Escape Key Listener to close any open modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        App.closeIssueFixModal();
        document.querySelectorAll('.modal-overlay:not(.hidden)').forEach(overlay => {
            const closeBtn = overlay.querySelector('.modal-close, .btn-close-modal, [data-close]');
            if (closeBtn) closeBtn.click();
            else overlay.classList.add('hidden');
        });
    }
});

// Global error listeners for frontend logging
window.onerror = function(msg, url, line, col, error) {
    if (window.Logger) {
        window.Logger.log(`GLOBAL ERROR: ${msg} at ${url}:${line}:${col} - ${error ? error.stack : ''}`, 'UNCAUGHT_ERR');
    }
};
window.onunhandledrejection = function(event) {
    if (window.Logger) {
        window.Logger.log(`UNHANDLED PROMISE REJECTION: ${event.reason}`, 'UNHANDLED_REJ');
    }
};

// Universal Searchable Select Component for PM13 and PM11
window.makeSearchableSelect = function(selectEl) {
    if (!selectEl || selectEl.dataset.searchableEnhanced === 'true') return;
    if (selectEl.closest('.searchable-select-wrapper')) return;
    if (selectEl.classList.contains('no-searchable')) return;

    selectEl.dataset.searchableEnhanced = 'true';
    selectEl.style.display = 'none';

    const wrapper = document.createElement('div');
    wrapper.className = 'searchable-select-wrapper';
    selectEl.parentNode.insertBefore(wrapper, selectEl);
    wrapper.appendChild(selectEl);

    const trigger = document.createElement('div');
    trigger.className = 'searchable-select-trigger';
    trigger.tabIndex = 0;
    trigger.innerHTML = `<span class="searchable-select-label"></span><span class="searchable-select-arrow">▼</span>`;
    wrapper.appendChild(trigger);

    const dropdown = document.createElement('div');
    dropdown.className = 'searchable-select-dropdown hidden';
    dropdown.innerHTML = `
      <div class="searchable-select-search-box">
        <input type="text" class="searchable-select-input" placeholder="🔍 Digite para buscar...">
      </div>
      <div class="searchable-select-options"></div>
    `;
    wrapper.appendChild(dropdown);

    const labelEl = trigger.querySelector('.searchable-select-label');
    const inputEl = dropdown.querySelector('.searchable-select-input');
    const optionsContainer = dropdown.querySelector('.searchable-select-options');

    const norm = str => String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

    const updateTriggerLabel = () => {
      const selectedOpt = selectEl.options[selectEl.selectedIndex];
      labelEl.textContent = selectedOpt ? selectedOpt.textContent : (selectEl.options[0]?.textContent || '');
    };

    const renderOptions = (filterQuery = '') => {
      const q = norm(filterQuery);
      const opts = Array.from(selectEl.options);
      optionsContainer.innerHTML = '';
      let matchCount = 0;

      opts.forEach(opt => {
        const text = opt.textContent || opt.innerText || '';
        const val = opt.value;
        const matches = !q || norm(text).includes(q) || norm(val).includes(q);

        if (matches) {
          matchCount++;
          const optDiv = document.createElement('div');
          const isSelected = opt.selected || String(val) === String(selectEl.value);
          optDiv.className = `searchable-select-option ${isSelected ? 'selected' : ''}`;
          optDiv.textContent = text;
          optDiv.dataset.value = val;
          optDiv.onclick = (e) => {
            e.stopPropagation();
            selectEl.value = val;
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            updateTriggerLabel();
            closeDropdown();
          };
          optionsContainer.appendChild(optDiv);
        }
      });

      if (matchCount === 0) {
        optionsContainer.innerHTML = `<div class="searchable-select-no-results">Nenhum resultado encontrado</div>`;
      }
    };

    const openDropdown = () => {
      document.querySelectorAll('.searchable-select-wrapper.open').forEach(w => {
        if (w !== wrapper) {
          w.classList.remove('open');
          w.querySelector('.searchable-select-dropdown')?.classList.add('hidden');
        }
      });
      wrapper.classList.add('open');
      dropdown.classList.remove('hidden');
      inputEl.value = '';
      renderOptions('');
      setTimeout(() => inputEl.focus(), 30);
    };

    const closeDropdown = () => {
      wrapper.classList.remove('open');
      dropdown.classList.add('hidden');
    };

    trigger.onclick = (e) => {
      e.stopPropagation();
      if (wrapper.classList.contains('open')) {
        closeDropdown();
      } else {
        openDropdown();
      }
    };

    inputEl.onclick = (e) => e.stopPropagation();
    inputEl.oninput = (e) => {
      renderOptions(e.target.value);
    };

    inputEl.onkeydown = (e) => {
      if (e.key === 'Escape') {
        closeDropdown();
      }
    };

    if (!window._searchableSelectGlobalClickListener) {
      window._searchableSelectGlobalClickListener = true;
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.searchable-select-wrapper')) {
          document.querySelectorAll('.searchable-select-wrapper.open').forEach(w => {
            w.classList.remove('open');
            w.querySelector('.searchable-select-dropdown')?.classList.add('hidden');
          });
        }
      });
    }

    const observer = new MutationObserver(() => {
      updateTriggerLabel();
      if (wrapper.classList.contains('open')) {
        renderOptions(inputEl.value);
      }
    });
    observer.observe(selectEl, { childList: true, subtree: true, attributes: true });

    selectEl.addEventListener('change', () => {
      updateTriggerLabel();
    });

    updateTriggerLabel();
};

window.enhanceAllSelects = function(parentEl) {
    const root = parentEl || document;
    root.querySelectorAll('select.control, .filters-grid select, .filter-card select, .form-group select, .filter-bar select, .card select').forEach(sel => {
      window.makeSearchableSelect(sel);
    });
};

if (window.MutationObserver) {
    const globalSelectObserver = new MutationObserver((mutations) => {
        let shouldEnhance = false;
        for (const mut of mutations) {
            if (mut.addedNodes.length) {
                shouldEnhance = true;
                break;
            }
        }
        if (shouldEnhance) {
            window.enhanceAllSelects();
        }
    });
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            globalSelectObserver.observe(document.body, { childList: true, subtree: true });
            window.enhanceAllSelects();
        });
    } else {
        globalSelectObserver.observe(document.body, { childList: true, subtree: true });
        window.enhanceAllSelects();
    }
}

// Global initializer - bulletproof against DOM readyState race conditions
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.App.init());
} else {
    window.App.init();
}
