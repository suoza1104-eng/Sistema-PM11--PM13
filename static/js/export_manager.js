/**
 * PM13 Export Manager - Custom export modal with item filtering & selection
 */
window.ExportManager = {
    scope: 'full',
    selectedItemIds: new Set(),
    allItems: [],
    allPlans: [],
    filteredItems: [],

    // Multi-select filters state
    selectedFilters: {
        wc: new Set(),
        gpm: new Set(),
        parada: new Set(),
        plan: new Set()
    },
    optionsData: {
        wc: [],
        gpm: [],
        parada: [],
        plan: []
    },
    searchQueries: {
        wc: '',
        gpm: '',
        parada: '',
        plan: ''
    },

    init() {
        this.ensureModals();
        this.bindClickOutside();
    },

    bindClickOutside() {
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.export-multiselect-container')) {
                this.closeAllMultiSelectDropdowns();
            }
        });
    },

    closeAllMultiSelectDropdowns() {
        document.querySelectorAll('.export-ms-dropdown').forEach(d => d.classList.add('hidden'));
        document.querySelectorAll('.export-ms-trigger').forEach(t => t.classList.remove('open'));
    },

    toggleMultiSelectDropdown(type, event) {
        if (event) event.stopPropagation();
        const dropdown = document.getElementById(`export-ms-dropdown-${type}`);
        const trigger = dropdown?.previousElementSibling;
        const willOpen = dropdown?.classList.contains('hidden');

        this.closeAllMultiSelectDropdowns();

        if (willOpen && dropdown && trigger) {
            dropdown.classList.remove('hidden');
            trigger.classList.add('open');
            const searchInput = dropdown.querySelector('.export-ms-search-input');
            if (searchInput) searchInput.focus();
        }
    },

    getItemParada(item) {
        if (item.plan_phase) return `P${item.plan_phase}`;
        if (item.plan_cycle_phase) {
            const match = item.plan_cycle_phase.match(/P(\d+)/i);
            if (match) return `P${match[1]}`;
            return item.plan_cycle_phase;
        }
        const text = `${item.plan_code || ''} ${item.plan_description || ''} ${item.description || ''}`;
        const match = text.match(/\bP(\d+)\b/i) || text.match(/\d+P(\d+)\b/i);
        if (match) return `P${match[1]}`;
        return '(Sem Parada)';
    },

    ensureModals() {
        if (!document.getElementById('modal-export-choose-scope')) {
            const scopeModalHtml = `
                <div id="modal-export-choose-scope" class="modal-overlay hidden" style="z-index:2600">
                    <div class="modal modal-md">
                        <div class="modal-header" style="background:#F8FAFC; border-bottom:1px solid #E2E8F0; padding:16px 20px;">
                            <h2>📤 Exportar Dados do Projeto PM13</h2>
                            <button class="btn-icon" onclick="ExportManager.closeScopeModal()">✕</button>
                        </div>
                        <div class="modal-body" style="padding:24px 20px;">
                            <p style="margin-bottom:16px; color:#475569; font-size:13.5px;">Escolha como você deseja exportar a planilha do projeto:</p>
                            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px;">
                                <div class="export-scope-card" onclick="ExportManager.downloadFullProject()" style="background:#F0FDF4; border:2px solid #86EFAC; border-radius:10px; padding:18px; cursor:pointer; transition:all 0.2s;" onmouseover="this.style.borderColor='#22C55E'; this.style.transform='translateY(-2px)'" onmouseout="this.style.borderColor='#86EFAC'; this.style.transform='none'">
                                    <div style="font-size:28px; margin-bottom:8px;">🌐</div>
                                    <h3 style="font-size:15px; font-weight:700; color:#15803D; margin-bottom:6px;">Projeto Completo</h3>
                                    <p style="font-size:12px; color:#166534; line-height:1.4; margin:0;">Exporta 100% dos planos, itens, operações e textos longos cadastrados no projeto sem filtros.</p>
                                    <span class="badge" style="background:#DCFCE7; color:#15803D; margin-top:12px; display:inline-block; font-size:11px;">100% dos Dados</span>
                                </div>
                                <div class="export-scope-card" onclick="ExportManager.openItemSelectionModal()" style="background:#F0F9FF; border:2px solid #BAE6FD; border-radius:10px; padding:18px; cursor:pointer; transition:all 0.2s;" onmouseover="this.style.borderColor='#0284C7'; this.style.transform='translateY(-2px)'" onmouseout="this.style.borderColor='#BAE6FD'; this.style.transform='none'">
                                    <div style="font-size:28px; margin-bottom:8px;">🎯</div>
                                    <h3 style="font-size:15px; font-weight:700; color:#0369A1; margin-bottom:6px;">Itens Específicos</h3>
                                    <p style="font-size:12px; color:#1E40AF; line-height:1.4; margin:0;">Escolha itens específicos via busca/filtros múltiplos. As abas vinculadas serão filtradas automaticamente.</p>
                                    <span class="badge" style="background:#E0F2FE; color:#0369A1; margin-top:12px; display:inline-block; font-size:11px;">Seleção com Filtros</span>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer" style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:12px 20px;">
                            <button class="btn btn-outline" onclick="ExportManager.closeScopeModal()">Cancelar</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', scopeModalHtml);
        }

        if (!document.getElementById('modal-export-select-items')) {
            const selectModalHtml = `
                <div id="modal-export-select-items" class="modal-overlay hidden" style="z-index:2650">
                    <div class="modal modal-lg" style="max-width:1080px;">
                        <div class="modal-header" style="background:#F8FAFC; border-bottom:1px solid #E2E8F0; padding:16px 20px;">
                            <div>
                                <h2>🎯 Selecionar Itens para Exportação</h2>
                                <small style="color:#64748B;">Selecione os itens que serão incluídos na exportação. Todas as abas vinculadas serão filtradas automaticamente.</small>
                            </div>
                            <button class="btn-icon" onclick="ExportManager.closeSelectModal()">✕</button>
                        </div>
                        <div class="modal-body" style="padding:16px 20px; overflow:visible;">
                            <!-- BARRA DE FILTROS COM MULTI-SELECT E PARADA -->
                            <div style="background:#F1F5F9; border:1px solid #CBD5E1; border-radius:8px; padding:12px; margin-bottom:14px; display:grid; grid-template-columns: 1.8fr 1fr 1fr 1fr 1.4fr auto; gap:10px; align-items:flex-end; overflow:visible; position:relative; z-index:10;">
                                <div>
                                    <label class="export-filter-label">Busca rápida</label>
                                    <input type="text" id="export-filter-search" placeholder="Buscar por descrição, equipamento, ID ou plano..." style="width:100%; padding:7px 10px; font-size:12px; border-radius:6px; border:1px solid #CBD5E1;" oninput="ExportManager.renderItemList()">
                                </div>

                                <!-- CT Multi-Select -->
                                <div class="export-multiselect-container" id="export-ms-container-wc">
                                    <label class="export-filter-label">Centro de Trabalho (CT)</label>
                                    <button type="button" class="export-ms-trigger" onclick="ExportManager.toggleMultiSelectDropdown('wc', event)">
                                        <span class="export-ms-label" id="export-ms-label-wc">Todos os CTs</span>
                                        <span class="export-ms-arrow">▼</span>
                                    </button>
                                    <div class="export-ms-dropdown hidden" id="export-ms-dropdown-wc">
                                        <div class="export-ms-search-wrap">
                                            <input type="text" class="export-ms-search-input" placeholder="🔍 Digite para buscar CT..." oninput="ExportManager.filterMultiSelectOptions('wc', this.value)">
                                        </div>
                                        <div class="export-ms-actions">
                                            <label class="export-ms-select-all">
                                                <input type="checkbox" id="export-ms-chk-all-wc" onchange="ExportManager.toggleMultiSelectAll('wc', this.checked)">
                                                <span>Selecionar Todos</span>
                                            </label>
                                            <span class="export-ms-count" id="export-ms-count-wc">0 selec.</span>
                                        </div>
                                        <div class="export-ms-options-list" id="export-ms-options-wc"></div>
                                    </div>
                                </div>

                                <!-- GPM Multi-Select -->
                                <div class="export-multiselect-container" id="export-ms-container-gpm">
                                    <label class="export-filter-label">GPM</label>
                                    <button type="button" class="export-ms-trigger" onclick="ExportManager.toggleMultiSelectDropdown('gpm', event)">
                                        <span class="export-ms-label" id="export-ms-label-gpm">Todos os GPMs</span>
                                        <span class="export-ms-arrow">▼</span>
                                    </button>
                                    <div class="export-ms-dropdown hidden" id="export-ms-dropdown-gpm">
                                        <div class="export-ms-search-wrap">
                                            <input type="text" class="export-ms-search-input" placeholder="🔍 Digite para buscar GPM..." oninput="ExportManager.filterMultiSelectOptions('gpm', this.value)">
                                        </div>
                                        <div class="export-ms-actions">
                                            <label class="export-ms-select-all">
                                                <input type="checkbox" id="export-ms-chk-all-gpm" onchange="ExportManager.toggleMultiSelectAll('gpm', this.checked)">
                                                <span>Selecionar Todos</span>
                                            </label>
                                            <span class="export-ms-count" id="export-ms-count-gpm">0 selec.</span>
                                        </div>
                                        <div class="export-ms-options-list" id="export-ms-options-gpm"></div>
                                    </div>
                                </div>

                                <!-- Parada Multi-Select (NOVO!) -->
                                <div class="export-multiselect-container" id="export-ms-container-parada">
                                    <label class="export-filter-label">Parada (Fase)</label>
                                    <button type="button" class="export-ms-trigger" onclick="ExportManager.toggleMultiSelectDropdown('parada', event)">
                                        <span class="export-ms-label" id="export-ms-label-parada">Todas as Paradas</span>
                                        <span class="export-ms-arrow">▼</span>
                                    </button>
                                    <div class="export-ms-dropdown hidden" id="export-ms-dropdown-parada">
                                        <div class="export-ms-search-wrap">
                                            <input type="text" class="export-ms-search-input" placeholder="🔍 Buscar P1, P2, P3..." oninput="ExportManager.filterMultiSelectOptions('parada', this.value)">
                                        </div>
                                        <div class="export-ms-actions">
                                            <label class="export-ms-select-all">
                                                <input type="checkbox" id="export-ms-chk-all-parada" onchange="ExportManager.toggleMultiSelectAll('parada', this.checked)">
                                                <span>Selecionar Todos</span>
                                            </label>
                                            <span class="export-ms-count" id="export-ms-count-parada">0 selec.</span>
                                        </div>
                                        <div class="export-ms-options-list" id="export-ms-options-parada"></div>
                                    </div>
                                </div>

                                <!-- Plano Multi-Select -->
                                <div class="export-multiselect-container" id="export-ms-container-plan">
                                    <label class="export-filter-label">Plano Vinculado</label>
                                    <button type="button" class="export-ms-trigger" onclick="ExportManager.toggleMultiSelectDropdown('plan', event)">
                                        <span class="export-ms-label" id="export-ms-label-plan">Todos os Planos</span>
                                        <span class="export-ms-arrow">▼</span>
                                    </button>
                                    <div class="export-ms-dropdown hidden" id="export-ms-dropdown-plan">
                                        <div class="export-ms-search-wrap">
                                            <input type="text" class="export-ms-search-input" placeholder="🔍 Buscar por código/nome do plano..." oninput="ExportManager.filterMultiSelectOptions('plan', this.value)">
                                        </div>
                                        <div class="export-ms-actions">
                                            <label class="export-ms-select-all">
                                                <input type="checkbox" id="export-ms-chk-all-plan" onchange="ExportManager.toggleMultiSelectAll('plan', this.checked)">
                                                <span>Selecionar Todos</span>
                                            </label>
                                            <span class="export-ms-count" id="export-ms-count-plan">0 selec.</span>
                                        </div>
                                        <div class="export-ms-options-list" id="export-ms-options-plan"></div>
                                    </div>
                                </div>

                                <div>
                                    <button class="btn btn-xs btn-outline" style="white-space:nowrap; padding:7px 10px; font-weight:600;" onclick="ExportManager.clearFilters()">Limpar Filtros</button>
                                </div>
                            </div>

                            <!-- CONTROLE DE SELEÇÃO DA TABELA -->
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding:4px 2px;">
                                <label style="font-size:12px; font-weight:600; cursor:pointer; color:#334155; user-select:none;">
                                    <input type="checkbox" id="export-select-all-visible" onchange="ExportManager.toggleSelectAllVisible(this.checked)" style="margin-right:6px;">
                                    Marcar / Desmarcar todos os visíveis no filtro
                                </label>
                                <span id="export-item-counter-badge" style="font-size:12px; font-weight:700; color:#0284C7; background:#E0F2FE; border:1px solid #BAE6FD; padding:4px 10px; border-radius:12px;">
                                    0 de 0 itens selecionados
                                </span>
                            </div>

                            <!-- TABELA DE ITENS COM SCROLL -->
                            <div style="max-height:360px; overflow-y:auto; border:1px solid #E2E8F0; border-radius:8px;">
                                <table class="table" style="width:100%; font-size:12px; margin:0;">
                                    <thead style="position:sticky; top:0; background:#F8FAFC; z-index:2; border-bottom:2px solid #E2E8F0;">
                                        <tr>
                                            <th style="width:36px; text-align:center;"></th>
                                            <th style="width:70px;">ID / Pos</th>
                                            <th style="width:150px;">Equipamento / Nota</th>
                                            <th>Descrição do Item</th>
                                            <th>Plano Vinculado</th>
                                            <th style="width:75px;">Parada</th>
                                            <th style="width:80px;">CT</th>
                                            <th style="width:65px;">GPM</th>
                                        </tr>
                                    </thead>
                                    <tbody id="export-items-tbody">
                                        <tr><td colspan="8" class="text-center py-12">Carregando itens do projeto...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        <div class="modal-footer" style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:12px 20px; display:flex; justify-content:space-between;">
                            <div>
                                <button class="btn btn-outline" onclick="ExportManager.backToScopeChoice()">← Voltar</button>
                                <button class="btn btn-outline" onclick="ExportManager.closeSelectModal()">Cancelar</button>
                            </div>
                            <button id="btn-submit-export-selected" class="btn btn-primary" style="background:#15803D; border-color:#15803D; font-weight:700;" onclick="ExportManager.submitSelectedExport()" disabled>
                                📥 Exportar Itens Selecionados (0)
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', selectModalHtml);
        }
    },

    openModal(exportKind = 'full') {
        this.exportKind = exportKind || 'full';
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) return UI.showToast('Selecione um projeto para exportar.', 'warning');
        this.ensureModals();
        
        const titleEl = document.querySelector('#modal-export-choose-scope h2');
        if (titleEl) {
            titleEl.textContent = this.exportKind === 'systems' 
                ? '📤 Exportar Planilha Sistemas (SAP 5 Abas)' 
                : '📤 Exportar Dados do Projeto PM13';
        }

        const scopeModal = document.getElementById('modal-export-choose-scope');
        if (scopeModal) {
            scopeModal.classList.remove('hidden');
            scopeModal.style.display = 'flex';
        }
    },

    closeScopeModal() {
        const scopeModal = document.getElementById('modal-export-choose-scope');
        if (scopeModal) {
            scopeModal.classList.add('hidden');
            scopeModal.style.display = 'none';
        }
    },

    closeSelectModal() {
        this.closeAllMultiSelectDropdowns();
        const selectModal = document.getElementById('modal-export-select-items');
        if (selectModal) {
            selectModal.classList.add('hidden');
            selectModal.style.display = 'none';
        }
    },

    backToScopeChoice() {
        this.closeSelectModal();
        const scopeModal = document.getElementById('modal-export-choose-scope');
        if (scopeModal) {
            scopeModal.classList.remove('hidden');
            scopeModal.style.display = 'flex';
        }
    },

    downloadFullProject() {
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) return UI.showToast('Selecione um projeto para exportar.', 'warning');
        this.closeScopeModal();
        if (this.exportKind === 'systems') {
            window.open(`/api/export/systems?project_id=${projectId}`, '_blank');
            UI.showToast('Gerando download da planilha Sistemas completa...', 'info');
        } else {
            window.open(`/api/export?type=full&scope=full&project_id=${projectId}`, '_blank');
            UI.showToast('Gerando download do projeto completo...', 'info');
        }
    },

    async openItemSelectionModal() {
        this.closeScopeModal();
        this.ensureModals();
        const selectModal = document.getElementById('modal-export-select-items');
        if (selectModal) {
            selectModal.classList.remove('hidden');
            selectModal.style.display = 'flex';
        }
        this.selectedItemIds.clear();
        
        try {
            UI.showLoader('Carregando itens para exportação...');
            const projectId = window.App ? App.getValidProjectId() : null;
            const [itemsRes, plansRes] = await Promise.all([
                API.get('/api/items', { project_id: projectId, limit: 10000 }),
                API.get('/api/plans', { project_id: projectId, limit: 5000 })
            ]);
            
            this.allItems = itemsRes.items || itemsRes || [];
            this.allPlans = plansRes.plans || plansRes || [];
            
            this.populateFilterDropdowns();
            this.renderItemList();
        } catch (err) {
            UI.showToast(`Erro ao carregar itens: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    populateFilterDropdowns() {
        const wcs = [...new Set(this.allItems.map(i => i.work_center).filter(Boolean))].sort();
        const gpms = [...new Set(this.allItems.map(i => i.gpm).filter(Boolean))].sort();

        // Extract unique paradas (P1, P2, P3, P4...)
        const paradasSet = new Set();
        this.allItems.forEach(i => {
            const p = this.getItemParada(i);
            if (p) paradasSet.add(p);
        });
        const paradas = [...paradasSet].sort((a, b) => {
            const numA = parseInt(a.replace(/\D/g, '') || '0', 10);
            const numB = parseInt(b.replace(/\D/g, '') || '0', 10);
            return numA - numB || a.localeCompare(b);
        });

        // Unique plans
        const plans = this.allPlans.map(p => ({
            id: String(p.id),
            label: `${p.legacy_code} - ${p.description || ''}`
        })).sort((a, b) => a.label.localeCompare(b.label));

        this.optionsData = {
            wc: wcs.map(v => ({ id: v, label: v })),
            gpm: gpms.map(v => ({ id: v, label: v })),
            parada: paradas.map(v => ({ id: v, label: v })),
            plan: plans
        };

        // Reset filter selections
        this.selectedFilters.wc.clear();
        this.selectedFilters.gpm.clear();
        this.selectedFilters.parada.clear();
        this.selectedFilters.plan.clear();

        this.searchQueries = { wc: '', gpm: '', parada: '', plan: '' };

        ['wc', 'gpm', 'parada', 'plan'].forEach(type => {
            const searchInput = document.querySelector(`#export-ms-dropdown-${type} .export-ms-search-input`);
            if (searchInput) searchInput.value = '';
            this.renderMultiSelectOptions(type);
        });

        document.getElementById('export-filter-search').value = '';
    },

    renderMultiSelectOptions(type) {
        const container = document.getElementById(`export-ms-options-${type}`);
        if (!container) return;

        const options = this.optionsData[type] || [];
        const selectedSet = this.selectedFilters[type];
        const query = (this.searchQueries[type] || '').toLowerCase().trim();

        const filteredOpts = options.filter(opt => opt.label.toLowerCase().includes(query));

        if (filteredOpts.length === 0) {
            container.innerHTML = '<div style="padding:10px; font-size:11.5px; color:#94A3B8; text-align:center;">Nenhuma opção encontrada</div>';
        } else {
            container.innerHTML = filteredOpts.map(opt => {
                const isChecked = selectedSet.has(opt.id);
                return `
                    <label class="export-ms-option ${isChecked ? 'selected' : ''}" onclick="event.stopPropagation();">
                        <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="ExportManager.toggleMultiSelectOption('${type}', '${UI.escapeHTML(opt.id)}')">
                        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${UI.escapeHTML(opt.label)}</span>
                    </label>
                `;
            }).join('');
        }

        // Update select all checkbox state
        const chkAll = document.getElementById(`export-ms-chk-all-${type}`);
        if (chkAll) {
            chkAll.checked = filteredOpts.length > 0 && filteredOpts.every(o => selectedSet.has(o.id));
        }

        // Update count badge & trigger label
        const countBadge = document.getElementById(`export-ms-count-${type}`);
        if (countBadge) {
            countBadge.textContent = `${selectedSet.size} selec.`;
        }

        this.updateTriggerLabel(type);
    },

    updateTriggerLabel(type) {
        const labelEl = document.getElementById(`export-ms-label-${type}`);
        if (!labelEl) return;

        const selectedSet = this.selectedFilters[type];
        const count = selectedSet.size;
        const total = (this.optionsData[type] || []).length;

        const titles = {
            wc: 'Todos os CTs',
            gpm: 'Todos os GPMs',
            parada: 'Todas as Paradas',
            plan: 'Todos os Planos'
        };

        const unitNames = {
            wc: 'CT(s)',
            gpm: 'GPM(s)',
            parada: 'Parada(s)',
            plan: 'Plano(s)'
        };

        if (count === 0 || count === total) {
            labelEl.textContent = titles[type] || 'Todos';
        } else if (count === 1) {
            const singleId = Array.from(selectedSet)[0];
            const opt = (this.optionsData[type] || []).find(o => String(o.id) === String(singleId));
            labelEl.textContent = opt ? opt.label : `1 ${unitNames[type]}`;
        } else {
            labelEl.textContent = `${count} ${unitNames[type]} selec.`;
        }
    },

    filterMultiSelectOptions(type, query) {
        this.searchQueries[type] = query;
        this.renderMultiSelectOptions(type);
    },

    toggleMultiSelectOption(type, value) {
        const selectedSet = this.selectedFilters[type];
        if (selectedSet.has(value)) {
            selectedSet.delete(value);
        } else {
            selectedSet.add(value);
        }
        this.renderMultiSelectOptions(type);
        this.renderItemList();
    },

    toggleMultiSelectAll(type, checked) {
        const options = this.optionsData[type] || [];
        const query = (this.searchQueries[type] || '').toLowerCase().trim();
        const visibleOpts = options.filter(opt => opt.label.toLowerCase().includes(query));

        visibleOpts.forEach(opt => {
            if (checked) {
                this.selectedFilters[type].add(opt.id);
            } else {
                this.selectedFilters[type].delete(opt.id);
            }
        });

        this.renderMultiSelectOptions(type);
        this.renderItemList();
    },

    clearFilters() {
        document.getElementById('export-filter-search').value = '';
        this.selectedFilters.wc.clear();
        this.selectedFilters.gpm.clear();
        this.selectedFilters.parada.clear();
        this.selectedFilters.plan.clear();

        ['wc', 'gpm', 'parada', 'plan'].forEach(type => {
            this.searchQueries[type] = '';
            const searchInput = document.querySelector(`#export-ms-dropdown-${type} .export-ms-search-input`);
            if (searchInput) searchInput.value = '';
            this.renderMultiSelectOptions(type);
        });

        this.renderItemList();
    },

    renderItemList() {
        const tbody = document.getElementById('export-items-tbody');
        if (!tbody) return;

        const q = (document.getElementById('export-filter-search')?.value || '').toLowerCase().trim();
        const selWcs = this.selectedFilters.wc;
        const selGpms = this.selectedFilters.gpm;
        const selParadas = this.selectedFilters.parada;
        const selPlans = this.selectedFilters.plan;

        this.filteredItems = this.allItems.filter(item => {
            if (selWcs.size > 0 && (!item.work_center || !selWcs.has(item.work_center))) return false;
            if (selGpms.size > 0 && (!item.gpm || !selGpms.has(item.gpm))) return false;
            if (selParadas.size > 0 && !selParadas.has(this.getItemParada(item))) return false;
            if (selPlans.size > 0 && (!item.plan_id || !selPlans.has(String(item.plan_id)))) return false;

            if (q) {
                const searchStr = `${item.legacy_identifier} ${item.object_code} ${item.description} ${item.plan_code} ${item.plan_description} ${item.work_center} ${item.gpm} ${this.getItemParada(item)}`.toLowerCase();
                if (!searchStr.includes(q)) return false;
            }
            return true;
        });

        if (!this.filteredItems.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center py-12 muted">Nenhum item encontrado com os filtros selecionados.</td></tr>';
            this.updateCounter();
            return;
        }

        const allFilteredSelected = this.filteredItems.length > 0 && this.filteredItems.every(i => this.selectedItemIds.has(i.id));
        const selectAllChk = document.getElementById('export-select-all-visible');
        if (selectAllChk) selectAllChk.checked = allFilteredSelected;

        tbody.innerHTML = this.filteredItems.map(item => {
            const isChecked = this.selectedItemIds.has(item.id);
            const paradaLabel = this.getItemParada(item);
            return `
                <tr style="background:${isChecked ? '#F0FDF4' : 'transparent'}; cursor:pointer;" onclick="ExportManager.handleRowClick(event, ${item.id})">
                    <td style="text-align:center;">
                        <input type="checkbox" class="export-item-checkbox" data-id="${item.id}" ${isChecked ? 'checked' : ''} onclick="event.stopPropagation(); ExportManager.toggleItem(${item.id})">
                    </td>
                    <td><strong>${UI.escapeHTML(item.legacy_identifier || item.id)}</strong></td>
                    <td>${UI.escapeHTML(item.object_code || '-')}</td>
                    <td style="font-weight:600; color:#1E293B;">${UI.escapeHTML(item.description || '')}</td>
                    <td><small style="color:#475569;">${UI.escapeHTML(item.plan_code ? `${item.plan_code} - ${item.plan_description || ''}` : 'Sem plano')}</small></td>
                    <td><span class="badge" style="background:#F1F5F9; color:#334155; font-size:10.5px;">${UI.escapeHTML(paradaLabel)}</span></td>
                    <td>${UI.escapeHTML(item.work_center || '-')}</td>
                    <td>${UI.escapeHTML(item.gpm || '-')}</td>
                </tr>
            `;
        }).join('');

        this.updateCounter();
    },

    handleRowClick(event, itemId) {
        if (event.target.tagName === 'INPUT') return;
        this.toggleItem(itemId);
    },

    toggleItem(itemId) {
        if (this.selectedItemIds.has(itemId)) {
            this.selectedItemIds.delete(itemId);
        } else {
            this.selectedItemIds.add(itemId);
        }
        this.renderItemList();
    },

    toggleSelectAllVisible(checked) {
        this.filteredItems.forEach(item => {
            if (checked) {
                this.selectedItemIds.add(item.id);
            } else {
                this.selectedItemIds.delete(item.id);
            }
        });
        this.renderItemList();
    },

    updateCounter() {
        const counterBadge = document.getElementById('export-item-counter-badge');
        const submitBtn = document.getElementById('btn-submit-export-selected');
        const count = this.selectedItemIds.size;
        const total = this.allItems.length;
        const visible = this.filteredItems.length;

        if (counterBadge) {
            counterBadge.textContent = `${count} de ${total} itens selecionados (${visible} visíveis)`;
        }
        if (submitBtn) {
            submitBtn.disabled = count === 0 && visible === 0;
            submitBtn.textContent = `📥 Exportar Itens Selecionados (${count || visible})`;
        }
    },

    submitSelectedExport() {
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) return UI.showToast('Selecione um projeto para exportar.', 'warning');
        
        let targetIds = Array.from(this.selectedItemIds);
        if (targetIds.length === 0 && this.filteredItems.length > 0) {
            targetIds = this.filteredItems.map(i => i.id);
        }
        if (targetIds.length === 0) {
            return UI.showToast('Selecione ao menos 1 item para exportar.', 'warning');
        }

        const itemIdsArray = targetIds.join(',');
        this.closeSelectModal();
        if (this.exportKind === 'systems') {
            window.open(`/api/export/systems?project_id=${projectId}&item_ids=${encodeURIComponent(itemIdsArray)}`, '_blank');
        } else {
            window.open(`/api/export?type=full&scope=full&project_id=${projectId}&item_ids=${encodeURIComponent(itemIdsArray)}`, '_blank');
        }
        UI.showToast(`Gerando exportação de ${targetIds.length} item(ns) selecionado(s)...`, 'info');
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.ExportManager.init());
} else {
    window.ExportManager.init();
}
