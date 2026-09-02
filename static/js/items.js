/**
 * Items View & CRUD Controller
 */

const Items = {
    filters: {
        search: '',
        gpm: '',
        work_center: '',
        condition_code: '',
        priority: '',
        plan_id: '',
        alert: '',
        status: 'ACTIVE',
        row_color: '',
        limit: 100000, // Default to all
        offset: 0,
        order_by: 'display_order',
        order_dir: 'ASC'
    },
    selectedIds: new Set(),
    inlineTradeQueues: new Map(),
    rawItemsList: [],
    plansList: [],
    bulkStandardModels: [],
    bulkStandardPreview: null,
    bulkStandardDraftOperations: [],
    bulkStandardSelectedId: null,

    init() {
        try {
        if (localStorage.getItem('pm13_items_compact_layout_v1') !== '1') {
            localStorage.removeItem('pm13_table_widths_items-table');
            localStorage.setItem('pm13_items_compact_layout_v1', '1');
        }
        if (window.TableColumnResizer) window.TableColumnResizer.init('items-table');
        const pinActionsBtn = document.getElementById('btn-toggle-items-actions-pin');
        if (pinActionsBtn) {
            pinActionsBtn.onclick = () => this.toggleActionsPin();
            this.setActionsPinned(localStorage.getItem('pm13_items_actions_pinned') === '1');
        }
        const pinHeaderBtn = document.getElementById('btn-toggle-items-header-pin');
        if (pinHeaderBtn) {
            pinHeaderBtn.onclick = () => this.setHeaderPinned(!document.getElementById('items-table')?.classList.contains('header-pinned'));
            this.setHeaderPinned(localStorage.getItem('pm13_items_header_pinned') === '1');
        }
        document.getElementById('items-filter-body')?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                document.getElementById('btn-apply-items-filters')?.click();
            }
        });
        // Toggle filters accordion
        const toggle = document.getElementById('items-filter-toggle');
        if (toggle) {
            const card = toggle.closest('.filter-card');
            toggle.onclick = () => card && card.classList.toggle('collapsed');
        }

        // Real-time character counter for creation form
        const descInput = document.getElementById('form-item-desc');
        const descCount = document.getElementById('form-item-desc-chars');
        const descWarn = document.getElementById('form-item-desc-warning');
        if (descInput && descCount && descWarn) {
            descInput.oninput = () => {
                const len = descInput.value.trim().length;
                descCount.innerText = `${len} / 35 caracteres`;
                if (len > 35) {
                    descCount.style.color = 'var(--error-color)';
                    descWarn.classList.remove('hidden');
                } else {
                    descCount.style.color = 'var(--text-muted)';
                    descWarn.classList.add('hidden');
                }
            };
        }

        // Populate form plan details summary upon selection
        const planSelect = document.getElementById('form-item-plan');
        if (planSelect) {
            planSelect.onchange = () => {
                const selectedVal = planSelect.value;
                const summaryBox = document.getElementById('item-plan-details-summary');
                if (!selectedVal) {
                    if (summaryBox) summaryBox.classList.add('hidden');
                    return;
                }
                const match = this.plansList.find(p => p.id == selectedVal);
                if (match && summaryBox) {
                    summaryBox.classList.remove('hidden');
                    const nextOcc = match.reference_counter !== null
                        ? calculations_occurrence_display(match.reference_counter, match.cycle, window.App.currentCounter)
                        : 'Pendente';
                    summaryBox.innerHTML = `
                        <span>Ciclo: <strong>${match.cycle} ${match.unit} (${match.cycle_text})</strong></span>
                        <span>Horizonte: <strong>${match.opening_horizon}h</strong></span>
                        <span>Contador Ref: <strong>${match.reference_counter !== null ? match.reference_counter : 'Pendente'}</strong></span>
                        <span>Próxima Parada: <strong>${nextOcc}</strong></span>
                    `;
                }
            };
        }

        // Table headers sort events
        const headers = document.querySelectorAll('#items-table th.sortable');
        headers.forEach(th => {
            th.onclick = (e) => {
                if (e.target.closest('.col-filter-btn') || e.target.closest('.column-resizer')) return;
                const col = th.getAttribute('data-col');
                if (this.filters.order_by === col) {
                    this.filters.order_dir = this.filters.order_dir === 'ASC' ? 'DESC' : 'ASC';
                } else {
                    this.filters.order_by = col;
                    this.filters.order_dir = 'ASC';
                }
                this.load();
            };
        });

        // Apply filters
        const applyBtn = document.getElementById('btn-apply-items-filters');
        if (applyBtn) applyBtn.onclick = () => {
            this.applyFiltersFromInputs();
            this.filters.offset = 0;
            this.load();
        };

        // Clear filters
        const clearBtn = document.getElementById('btn-clear-items-filters');
        if (clearBtn) clearBtn.onclick = () => {
            const els = ['filter-items-search','filter-items-wc','filter-items-gpm','filter-items-condition','filter-items-priority','filter-items-plan','filter-items-alert','filter-items-row-color'];
            els.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
            const statusEl = document.getElementById('filter-items-status');
            if (statusEl) statusEl.value = 'ACTIVE';

            this.filters.search = '';
            this.filters.work_center = '';
            this.filters.gpm = '';
            this.filters.condition_code = '';
            this.filters.priority = '';
            this.filters.plan_id = '';
            this.filters.alert = '';
            this.filters.status = 'ACTIVE';
            this.filters.row_color = '';
            this.filters.without_plan = '';
            this.filters.without_headcount = '';
            this.filters.duration_zero = '';
            this.filters.long_desc = '';
            this.filters.offset = 0;
            if (window.ColumnFilter) {
                window.ColumnFilter.clearAllFilters('items-table');
            }
            this.load();
        };

        const pageSizeEl = document.getElementById('items-page-size');
        if (pageSizeEl) pageSizeEl.onchange = (e) => {
            const val = e.target.value;
            this.filters.limit = val === 'all' ? 100000 : parseInt(val);
            this.filters.offset = 0;
            this.load();
        };

        // Check All items checkbox toggler
        const checkAll = document.getElementById('check-all-items');
        if (checkAll) checkAll.onchange = () => {
            const checkboxes = document.querySelectorAll('.item-row-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = checkAll.checked;
                const id = parseInt(cb.getAttribute('data-id'));
                if (checkAll.checked) {
                    this.selectedIds.add(id);
                } else {
                    this.selectedIds.delete(id);
                }
            });
            this.updateBulkToolbar();
        };

        // Create buttons
        const createBtn = document.getElementById('btn-create-item');
        if (createBtn) createBtn.onclick = () => this.openCreateModal();
        const reorderBtn = document.getElementById('btn-reorder-item-ids');
        if (reorderBtn) reorderBtn.onclick = () => this.reorderIdentifiers();
        const saveBtn = document.getElementById('btn-save-item');
        if (saveBtn) saveBtn.onclick = () => this.save();
        const generateStandardBtn = document.getElementById('btn-generate-item-standard');
        if (generateStandardBtn) generateStandardBtn.onclick = () => {
            const itemId = Number(document.getElementById('form-item-id')?.value || 0);
            if (itemId && window.StandardsManager) window.StandardsManager.saveItemAsStandard(itemId);
        };
        const exportBtn = document.getElementById('btn-export-items');
        if (exportBtn) exportBtn.onclick = () => window.ImportWizard.exportScope('items');

        // Bulk buttons actions
        const bulkAssignBtn = document.getElementById('btn-bulk-assign-plan');
        if (bulkAssignBtn) bulkAssignBtn.onclick = () => this.openBulkAssignPlanModal();
        const bulkEditBtn = document.getElementById('btn-bulk-edit-fields');
        if (bulkEditBtn) bulkEditBtn.onclick = () => this.openBulkEditFieldsModal();
        const bulkApplyStandardBtn = document.getElementById('btn-bulk-apply-standard');
        if (bulkApplyStandardBtn) bulkApplyStandardBtn.onclick = () => this.openBulkApplyStandardModal();
        const bulkCloneBtn = document.getElementById('btn-bulk-clone-items');
        if (bulkCloneBtn) bulkCloneBtn.onclick = () => this.bulkClone();
        const bulkActivateBtn = document.getElementById('btn-bulk-activate');
        if (bulkActivateBtn) bulkActivateBtn.onclick = () => this.bulkUpdateStatus('ACTIVE');
        const bulkDeactivateBtn = document.getElementById('btn-bulk-deactivate');
        if (bulkDeactivateBtn) bulkDeactivateBtn.onclick = () => this.bulkUpdateStatus('INACTIVE');
        const bulkDeleteBtn = document.getElementById('btn-bulk-delete');
        if (bulkDeleteBtn) bulkDeleteBtn.onclick = () => this.bulkDelete();

        // Bulk assign plan modal select change preview
        const bulkPlanSelect = document.getElementById('bulk-assign-select-plan');
        if (bulkPlanSelect) bulkPlanSelect.onchange = () => this.updateBulkAssignPreview();
        const bulkAssignConfirm = document.getElementById('btn-bulk-assign-confirm');
        if (bulkAssignConfirm) bulkAssignConfirm.onclick = () => this.bulkAssignPlanConfirm();

        // Bulk edit modal enable checkboxes listeners
        ['gpm', 'wc', 'condition', 'priority', 'headcount', 'ele-headcount', 'ele-hours',
         'mec-headcount', 'mec-hours', 'sol-headcount', 'sol-hours'].forEach(field => {
            const cb = document.getElementById(`bulk-enable-${field}`);
            const input = document.getElementById(`bulk-input-${field}`);
            if (cb && input) cb.onchange = () => { input.disabled = !cb.checked; };
        });
        const bulkEditConfirm = document.getElementById('btn-bulk-edit-fields-confirm');
        if (bulkEditConfirm) bulkEditConfirm.onclick = () => this.bulkEditFieldsConfirm();

        // Trade inputs real-time calculation in modal
        ['mec-hc', 'mec-hours', 'ele-hc', 'ele-hours', 'sol-hc', 'sol-hours'].forEach(f => {
            const inp = document.getElementById(`form-item-${f}`);
            if (inp) inp.oninput = () => this.updateModalTradePreviews();
        });

        // Modals close events
        document.querySelectorAll('[data-close="modal-item"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-item').classList.add('hidden');
        });
        document.querySelectorAll('[data-close="modal-bulk-assign-plan"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-bulk-assign-plan').classList.add('hidden');
        });
        document.querySelectorAll('[data-close="modal-bulk-edit-fields"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-bulk-edit-fields').classList.add('hidden');
        });
        document.querySelectorAll('[data-close="modal-bulk-apply-standard"]').forEach(btn => {
            btn.onclick = () => this.closeBulkApplyStandardModal();
        });
        const bulkStandardSearch = document.getElementById('bulk-standard-search');
        if (bulkStandardSearch) bulkStandardSearch.oninput = () => this.renderBulkStandardLibrary();
        const bulkStandardCategory = document.getElementById('bulk-standard-category');
        if (bulkStandardCategory) bulkStandardCategory.onchange = () => this.renderBulkStandardLibrary();
        const bulkStandardPreviewItem = document.getElementById('bulk-standard-preview-item');
        if (bulkStandardPreviewItem) bulkStandardPreviewItem.onchange = () => this.renderBulkStandardOrderHeader();
        const bulkStandardAddOperation = document.getElementById('btn-bulk-standard-add-operation');
        if (bulkStandardAddOperation) bulkStandardAddOperation.onclick = () => this.addBulkStandardOperation();
        const bulkStandardApply = document.getElementById('btn-bulk-standard-apply');
        if (bulkStandardApply) bulkStandardApply.onclick = () => this.applyBulkStandard();
        const bulkStandardEditor = document.getElementById('bulk-standard-operations-editor');
        if (bulkStandardEditor) bulkStandardEditor.addEventListener('input', () => this.updateBulkStandardFooterSummary());
        document.querySelectorAll('input[name="bulk-standard-conflict-policy"]').forEach(radio => {
            radio.onchange = () => this.handleBulkStandardConflictPolicyChange();
        });

        } catch(e) {
            console.error('[Items.init] Erro ao inicializar tela de itens:', e);
        }
    },

    toggleActionsPin() {
        const table = document.getElementById('items-table');
        this.setActionsPinned(!table?.classList.contains('actions-column-pinned'));
    },

    setActionsPinned(pinned) {
        const table = document.getElementById('items-table');
        const button = document.getElementById('btn-toggle-items-actions-pin');
        if (!table) return;
        table.classList.toggle('actions-column-pinned', pinned);
        localStorage.setItem('pm13_items_actions_pinned', pinned ? '1' : '0');
        if (button) {
            button.classList.toggle('btn-secondary', pinned);
            button.classList.toggle('btn-outline', !pinned);
            button.innerHTML = pinned ? '📌 Ações Fixas' : '📌 Fixar Ações';
            button.title = pinned ? 'Desafixar a coluna Ações' : 'Fixar a coluna Ações no lado direito';
        }
    },

    setHeaderPinned(pinned) {
        const table = document.getElementById('items-table');
        const button = document.getElementById('btn-toggle-items-header-pin');
        table?.classList.toggle('header-pinned', pinned);
        document.getElementById('bulk-actions-toolbar')?.classList.toggle('header-context-pinned', pinned);
        table?.closest('.table-responsive-container')?.classList.toggle('items-header-scroll-pinned', pinned);
        table?.closest('.table-card')?.classList.toggle('items-header-card-pinned', pinned);
        localStorage.setItem('pm13_items_header_pinned', pinned ? '1' : '0');
        if (button) {
            button.classList.toggle('btn-secondary', pinned);
            button.classList.toggle('btn-outline', !pinned);
            button.textContent = pinned ? '📌 Cabeçalho Fixo' : '📌 Fixar Cabeçalho';
        }
    },

    applyFiltersFromInputs() {
        this.filters.search = document.getElementById('filter-items-search').value.trim();
        this.filters.work_center = document.getElementById('filter-items-wc').value;
        this.filters.gpm = document.getElementById('filter-items-gpm').value;
        this.filters.condition_code = document.getElementById('filter-items-condition').value;
        this.filters.priority = document.getElementById('filter-items-priority').value;
        this.filters.plan_id = document.getElementById('filter-items-plan').value;
        this.filters.alert = document.getElementById('filter-items-alert').value;
        this.filters.status = document.getElementById('filter-items-status').value;
        this.filters.row_color = document.getElementById('filter-items-row-color')?.value || '';

        // Map alert select keys
        this.filters.without_plan = this.filters.alert === 'without_plan' ? 'true' : '';
        this.filters.without_headcount = this.filters.alert === 'without_headcount' ? 'true' : '';
        this.filters.duration_zero = this.filters.alert === 'duration_zero' ? 'true' : '';
        this.filters.long_desc = this.filters.alert === 'long_desc' ? 'true' : '';
    },

    async load(options = {}) {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        // Check if there is preset filters (e.g. from dashboard or plans view linked items)
        if (window.App.itemsFilterPreset) {
            const preset = window.App.itemsFilterPreset;
            window.App.itemsFilterPreset = null; // Clear

            // Reset all filters in inputs first
            document.getElementById('btn-clear-items-filters').click();

            if (preset === 'without_plan') {
                this.filters.alert = 'without_plan';
                this.filters.without_plan = 'true';
                document.getElementById('filter-items-alert').value = 'without_plan';
            } else if (preset === 'without_headcount') {
                this.filters.alert = 'without_headcount';
                this.filters.without_headcount = 'true';
                document.getElementById('filter-items-alert').value = 'without_headcount';
            } else if (preset === 'duration_zero') {
                this.filters.alert = 'duration_zero';
                this.filters.duration_zero = 'true';
                document.getElementById('filter-items-alert').value = 'duration_zero';
            } else if (preset === 'long_desc') {
                this.filters.alert = 'long_desc';
                this.filters.long_desc = 'true';
                document.getElementById('filter-items-alert').value = 'long_desc';
            } else if (preset.startsWith('plan_')) {
                const planId = preset.split('_')[1];
                this.filters.plan_id = planId;
                document.getElementById('filter-items-plan').value = planId;
            }
        }

        const tbody = document.getElementById('tbody-items');
        const isSilent = options.silent || (tbody && tbody.children.length > 0 && !tbody.querySelector('.empty-table-cell'));
        if (!isSilent) {
            UI.showLoader("Carregando itens de manutenção...");
        }

        return window.App ? App.preserveScroll(tbody || 'tbody-items', async () => {
            try {
                // Load unique lists for filter select options
                await this.loadUniqueLists(projId);

                // Load items
                const params = {
                    project_id: projId,
                    search: this.filters.search,
                    work_center: this.filters.work_center,
                    gpm: this.filters.gpm,
                    condition_code: this.filters.condition_code,
                    priority: this.filters.priority,
                    plan_id: this.filters.plan_id,
                    status: this.filters.status,
                    row_color: this.filters.row_color,
                    without_plan: this.filters.without_plan,
                    without_headcount: this.filters.without_headcount,
                    duration_zero: this.filters.duration_zero,
                    long_desc: this.filters.long_desc,
                    limit: this.filters.limit,
                    offset: this.filters.offset,
                    order_by: this.filters.order_by,
                    order_dir: this.filters.order_dir
                };

                const data = await API.get('/api/items', params);
                this.rawItemsList = data.items || [];

                // Apply client-side column filters if present
                let displayItems = this.rawItemsList;
                if (window.ColumnFilter) {
                    displayItems = window.ColumnFilter.applyFiltersToDataset('items-table', this.rawItemsList);
                }

                if (this.filters.alert === 'all_issues' || this.filters.alert === 'error' || this.filters.alert === 'warning') {
                    displayItems = displayItems.filter(item => {
                        const issues = [];
                        if (item.validation_issues_json) {
                            try {
                                const parsed = typeof item.validation_issues_json === 'string' ? JSON.parse(item.validation_issues_json) : item.validation_issues_json;
                                if (Array.isArray(parsed)) issues.push(...parsed);
                            } catch(e) {}
                        }
                        if (item.validation_issues && Array.isArray(item.validation_issues)) issues.push(...item.validation_issues);
                        if (item.plan_id === null) issues.push({ severity: 'WARNING', message: 'Item sem plano' });
                        if (item.headcount === null || item.headcount === 0) issues.push({ severity: 'WARNING', message: 'Item sem efetivo' });
                        if (item.duration_hours === 0) issues.push({ severity: 'WARNING', message: 'Duração zerada' });
                        if (item.character_count > 35) issues.push({ severity: 'WARNING', message: 'Descrição extensa' });

                        const isError = issues.some(i => i.severity === 'ERROR');
                        const isWarning = issues.length > 0 && !isError;
                        if (this.filters.alert === 'all_issues') return issues.length > 0;
                        if (this.filters.alert === 'error') return isError;
                        if (this.filters.alert === 'warning') return isWarning;
                        return true;
                    });
                }

                this.renderTable(displayItems, displayItems.length !== this.rawItemsList.length ? displayItems.length : data.total);

                // Initialize or update column filters on table headers
                if (window.ColumnFilter) {
                    window.ColumnFilter.init('items-table', () => this.rawItemsList, (sortCol, sortDir, activeFilters) => {
                        if (sortCol && sortDir) {
                            this.filters.order_by = sortCol;
                            this.filters.order_dir = sortDir;
                        }
                        this.load();
                    }, {
                        plan_code: {
                            popoverClass: 'col-filter-popover-plan',
                            searchPlaceholder: 'Pesquisar código, título ou ciclo...',
                            getOptionMeta: (item, value) => ({
                                primary: value,
                                secondary: item.plan_description || (value === '(Vazio)' ? 'Item sem plano' : 'Plano sem título'),
                                badge: item.plan_cycle ? `${item.plan_cycle}P` : '',
                                searchText: `${item.plan_cycle || ''} ${item.plan_cycle_text || ''} ${item.plan_unit || ''}`
                            })
                        }
                    });
                }
                
                // Sync check all state
                const checkAll = document.getElementById('check-all-items');
                if (checkAll) {
                    checkAll.checked = displayItems.length > 0 && displayItems.every(i => this.selectedIds.has(i.id));
                }
                this.updateBulkToolbar();

            } catch (err) {
                UI.showToast(`Erro ao carregar itens: ${err.message}`, 'error');
            } finally {
                if (!isSilent) UI.hideLoader();
            }
        }) : null;
    },

    async reorderIdentifiers() {
        const projectId = window.App.getValidProjectId();
        if (!projectId) return;
        if (!window.confirm('Reordenar todos os IDs dos itens de 1 até N? Os vínculos com operações e textos longos serão preservados e um backup será criado antes da alteração.')) return;
        UI.showLoader('Criando backup e reordenando identificadores...');
        try {
            const result = await API.post('/api/items/reorder-identifiers', { project_id: projectId });
            UI.showToast(result.message, 'success', 6000);
            this.filters.offset = 0;
            await this.load();
        } catch (error) {
            UI.showToast(`Erro ao reordenar IDs: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async loadUniqueLists(projId) {
        const pData = await API.get('/api/plans', { project_id: projId, limit: 1000 });
        this.plansList = pData.plans;

        const allItemsData = await API.get('/api/items', { project_id: projId, limit: 100000 });
        const gpms = new Set();
        const wcs = new Set();
        allItemsData.items.forEach(item => {
            if (item.gpm) gpms.add(item.gpm);
            if (item.work_center) wcs.add(item.work_center);
        });

        const wcSelect = document.getElementById('filter-items-wc');
        const gpmSelect = document.getElementById('filter-items-gpm');
        const planSelect = document.getElementById('filter-items-plan');
        const prevWc = wcSelect?.value || '';
        const prevGpm = gpmSelect?.value || '';
        const prevPlan = planSelect?.value || '';
        if (wcSelect) wcSelect.innerHTML = '<option value="">Todos</option>';
        if (gpmSelect) gpmSelect.innerHTML = '<option value="">Todos</option>';
        if (planSelect) planSelect.innerHTML = '<option value="">Todos</option>';
        Array.from(wcs).sort().forEach(w => { if (wcSelect) wcSelect.innerHTML += `<option value="${w}">${w}</option>`; });
        Array.from(gpms).sort().forEach(g => { if (gpmSelect) gpmSelect.innerHTML += `<option value="${g}">${g}</option>`; });
        this.plansList.forEach(plan => { if (planSelect) planSelect.innerHTML += `<option value="${plan.id}">${plan.legacy_code} (${plan.description})</option>`; });

        const formPlanSelect = document.getElementById('form-item-plan');
        const prevFormPlan = formPlanSelect?.value || '';
        if (formPlanSelect) {
            formPlanSelect.innerHTML = '<option value="">Selecione o plano...</option>';
            this.plansList.forEach(plan => formPlanSelect.innerHTML += `<option value="${plan.id}">${plan.legacy_code} — ${plan.description}</option>`);
            formPlanSelect.value = prevFormPlan;
        }

        const bulkAssignSelect = document.getElementById('bulk-assign-select-plan');
        if (bulkAssignSelect) {
            bulkAssignSelect.innerHTML = '<option value="">Selecione o plano...</option>';
            this.plansList.forEach(plan => bulkAssignSelect.innerHTML += `<option value="${plan.id}">${plan.legacy_code} — ${plan.description}</option>`);
        }
        if (wcSelect) wcSelect.value = prevWc;
        if (gpmSelect) gpmSelect.value = prevGpm;
        if (planSelect) planSelect.value = prevPlan;
    },

    renderTable(items, total) {
        this.currentItems = items;
        const tbody = document.getElementById('items-table-body');
        tbody.innerHTML = '';

        document.getElementById('items-count-display').innerText = `${total} itens encontrados`;

        if (items.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="18" class="empty-table-cell">Nenhum item de manutenção encontrado.</td>
                </tr>
            `;
            this.renderPagination(total);
            return;
        }

        items.forEach(item => {
            const issues = [];
            if (item.validation_issues_json) {
                try {
                    const parsed = typeof item.validation_issues_json === 'string' ? JSON.parse(item.validation_issues_json) : item.validation_issues_json;
                    if (Array.isArray(parsed)) issues.push(...parsed);
                } catch(e) {}
            }
            if (item.validation_issues && Array.isArray(item.validation_issues)) {
                issues.push(...item.validation_issues);
            }

            if (item.plan_id === null) issues.push({ severity: 'WARNING', message: 'Item sem plano de reparo associado.' });
            if (item.headcount === null || item.headcount === 0) issues.push({ severity: 'WARNING', message: 'Item sem efetivo/homens definido.' });
            if (item.duration_hours === 0) issues.push({ severity: 'WARNING', message: 'Duração zerada.' });
            if (item.character_count > 35) issues.push({ severity: 'WARNING', message: `Descrição extensa (${item.character_count} caract. > 35).` });

            const issueMessages = [...new Set(issues.map(i => i.message))];
            const isError = issues.some(i => i.severity === 'ERROR');
            const isWarning = issues.length > 0 && !isError;
            
            let rowClass = '';
            if (isError) rowClass = 'table-alert-red';
            else if (isWarning) rowClass = 'table-alert-yellow';

            const esc = str => (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            const issuesText = issueMessages.map(m => `• ${m}`).join('\n');
            const indicator = issues.length > 0 ? `
                <span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" style="cursor:pointer;" onclick="event.stopPropagation(); App.openIssueFixModal('item', ${item.id})" title="Clique para abrir o diagnóstico e aplicar a correção automática: ${esc(issuesText)}">
                    ${isError ? '⛔' : '⚠️'}
                </span>
            ` : '';

            const statusBadge = item.status === 'ACTIVE'
                ? `<span class="badge badge-active">Ativo</span>`
                : `<span class="badge badge-inactive">Inativo</span>`;

            const checked = this.selectedIds.has(item.id) ? 'checked' : '';

            const safeIdent = (item.legacy_identifier || '').replace(/'/g, "\\'");
            const safeObjCode = (item.object_code || '').replace(/'/g, "\\'");
            const safeDesc = (item.description || '').replace(/'/g, "\\'");
            const safeGpm = (item.gpm || '').replace(/'/g, "\\'");
            const safeWc = (item.work_center || '').replace(/'/g, "\\'");
            const safeCond = (item.condition_code || '').replace(/'/g, "\\'");

            const tr = document.createElement('tr');
            tr.className = rowClass;
            if (item.row_color) tr.classList.add('item-row-marked', `item-row-color-${item.row_color}`);
            if (issues.length) tr.title = issuesText;
            tr.innerHTML = `
                <td class="text-center" style="height:100%; padding:8px 3px;"><div style="display:flex; align-items:center; justify-content:center; gap:3px;">${indicator}<button type="button" class="row-color-brush" title="Marcar linha com uma cor" onclick="Items.openColorPalette(event, ${item.id})">🖌️</button><input type="checkbox" class="item-row-checkbox" data-id="${item.id}" ${checked} onchange="Items.toggleSelection(event, ${item.id})"></div></td>
                <td class="editable-cell text-center" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'legacy_identifier', '${safeIdent}')"><strong>${item.legacy_identifier}</strong></td>
                <td class="editable-cell" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'object_code', '${safeObjCode}')">${item.object_code}</td>
                <td><span style="font-size:10px; color:var(--text-muted); font-weight:600;">${item.object_type.split(' ')[0]}</span></td>
                <td class="editable-cell item-description-cell" title="${item.description} (Clique 2x para editar)" ondblclick="Items.makeCellEditable(this, ${item.id}, 'description', '${safeDesc}')"><span class="item-description-text">${item.description}</span></td>
                <td class="text-center">
                    <div class="plan-cell-picker" title="Selecione o código para copiar; use a seta para alterar o plano">
                        ${item.plan_code ? `<span class="plan-code-badge" onclick="event.stopPropagation()">${item.plan_code}</span>` : '<span class="plan-code-none" onclick="event.stopPropagation()">Sem Plano</span>'}
                        <button type="button" class="plan-arrow-button" onclick="Items.openPlanPicker(event, ${item.id}, this)" title="Selecionar ou alterar o plano"><span class="plan-arrow-icon">▼</span></button>
                    </div>
                </td>
                <td class="text-center" title="Ciclo ${item.plan_cycle || '-'}; parada inicial ${item.plan_phase || '-'}">
                    ${item.plan_cycle_phase ? `<span class="plan-cycle-phase-badge">${item.plan_cycle_phase}</span>` : '<span class="text-muted">-</span>'}
                </td>
                <td class="editable-cell text-center" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'gpm', '${safeGpm}')">${item.gpm}</td>
                <td class="editable-cell text-center" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'work_center', '${safeWc}')">${item.work_center}</td>
                <td class="editable-cell text-center" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'condition_code', '${safeCond}')">${item.condition_code}</td>
                <td class="editable-cell text-center" title="Clique duas vezes para editar" ondblclick="Items.makeCellEditable(this, ${item.id}, 'priority', ${item.priority})">${item.priority}</td>
                <!-- ELE: Homens / Horas -->
                <td class="text-center" style="background: rgba(254, 252, 232, 0.4);">
                    <div style="display:flex; gap:2px; justify-content:center; align-items:center;">
                        <input type="number" min="0" placeholder="0" class="table-inline-input" style="width:32px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.ele_headcount || 0}" 
                               title="Elétrica: Quantidade de Homens" onchange="Items.inlineTradeEdit(${item.id}, 'ele_headcount', this.value)">
                        <span style="color:#94A3B8; font-size:10px;">/</span>
                        <input type="number" step="0.1" min="0" placeholder="0" class="table-inline-input" style="width:38px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.ele_hours || 0}" 
                               title="Elétrica: Duração (Horas)" onchange="Items.inlineTradeEdit(${item.id}, 'ele_hours', this.value)">
                    </div>
                </td>
                <!-- MEC: Homens / Horas -->
                <td class="text-center" style="background: rgba(239, 246, 255, 0.4);">
                    <div style="display:flex; gap:2px; justify-content:center; align-items:center;">
                        <input type="number" min="0" placeholder="0" class="table-inline-input" style="width:32px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.mec_headcount || 0}" 
                               title="Mecânica: Quantidade de Homens" onchange="Items.inlineTradeEdit(${item.id}, 'mec_headcount', this.value)">
                        <span style="color:#94A3B8; font-size:10px;">/</span>
                        <input type="number" step="0.1" min="0" placeholder="0" class="table-inline-input" style="width:38px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.mec_hours || 0}" 
                               title="Mecânica: Duração (Horas)" onchange="Items.inlineTradeEdit(${item.id}, 'mec_hours', this.value)">
                    </div>
                </td>
                <!-- SOL: Homens / Horas -->
                <td class="text-center" style="background: rgba(255, 241, 242, 0.4);">
                    <div style="display:flex; gap:2px; justify-content:center; align-items:center;">
                        <input type="number" min="0" placeholder="0" class="table-inline-input" style="width:32px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.sol_headcount || 0}" 
                               title="Solda: Quantidade de Homens" onchange="Items.inlineTradeEdit(${item.id}, 'sol_headcount', this.value)">
                        <span style="color:#94A3B8; font-size:10px;">/</span>
                        <input type="number" step="0.1" min="0" placeholder="0" class="table-inline-input" style="width:38px; text-align:center; font-weight:600; padding:2px 3px;" value="${item.sol_hours || 0}" 
                               title="Solda: Duração (Horas)" onchange="Items.inlineTradeEdit(${item.id}, 'sol_hours', this.value)">
                    </div>
                </td>
                <td class="text-center" id="hh-cell-${item.id}"><strong>${item.hh.toFixed(1).replace('.', ',')}</strong></td>
                <td class="text-center">${statusBadge}</td>
                <td class="text-center">
                    <div class="actions-cell">
                        <button class="btn btn-xs btn-primary" title="Pré-visualizar e editar a ordem no modelo SAP" onclick="Operations.openSapOrder(${item.id})">SAP</button>
                        <button class="btn btn-xs btn-outline" title="Editar item pelo formulário" onclick="Items.openEditModal(${item.id})">Editar</button>
                        <button class="btn btn-xs btn-outline" style="color:#0F766E; border-color:#0D9488;" title="Salvar este item e suas operações como modelo padrão compartilhado" onclick="StandardsManager.saveItemAsStandard(${item.id})">⭐ Padrão</button>
                        <button class="btn btn-xs btn-outline" title="Clonar somente os dados do item usando o próximo ID" onclick="Items.clone(${item.id})">Clonar</button>
                        <button class="btn btn-xs btn-danger" title="Excluir item" onclick="Items.delete(${item.id})">Excluir</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

        this.renderPagination(total);
        this.updateHeaderSortClasses();
    },

    renderPagination(total) {
        const container = document.getElementById('items-pagination-footer');
        container.innerHTML = '';
        
        const limit = this.filters.limit;
        if (limit >= total) return;

        const totalPages = Math.ceil(total / limit);
        const currentPage = Math.floor(this.filters.offset / limit) + 1;

        // Prev page
        const prevBtn = document.createElement('button');
        prevBtn.className = 'btn-paginate';
        prevBtn.innerText = '«';
        prevBtn.disabled = currentPage === 1;
        prevBtn.onclick = () => {
            this.filters.offset -= limit;
            this.load();
        };
        container.appendChild(prevBtn);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
                const pageBtn = document.createElement('button');
                pageBtn.className = `btn-paginate ${i === currentPage ? 'active' : ''}`;
                pageBtn.innerText = i;
                pageBtn.onclick = () => {
                    this.filters.offset = (i - 1) * limit;
                    this.load();
                };
                container.appendChild(pageBtn);
            } else if (i === currentPage - 3 || i === currentPage + 3) {
                const el = document.createElement('span');
                el.innerText = '...';
                el.style.padding = '0 5px';
                container.appendChild(el);
            }
        }

        // Next page
        const nextBtn = document.createElement('button');
        nextBtn.className = 'btn-paginate';
        nextBtn.innerText = '»';
        nextBtn.disabled = currentPage === totalPages;
        nextBtn.onclick = () => {
            this.filters.offset += limit;
            this.load();
        };
        container.appendChild(nextBtn);
    },

    updateHeaderSortClasses() {
        const headers = document.querySelectorAll('#items-table th.sortable');
        headers.forEach(th => {
            const col = th.getAttribute('data-col');
            const iconSpan = th.querySelector('.sort-icon');
            if (col === this.filters.order_by) {
                iconSpan.innerText = this.filters.order_dir === 'ASC' ? '▲' : '▼';
                th.style.color = 'var(--primary-dark)';
            } else {
                iconSpan.innerText = '';
                th.style.color = '';
            }
        });
    },

    toggleSelection(event, id) {
        if (event.target.checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
            document.getElementById('check-all-items').checked = false;
        }
        this.updateBulkToolbar();
    },

    openColorPalette(event, itemId) {
        event.stopPropagation();
        document.getElementById('item-row-color-palette')?.remove();
        const colors = [
            ['red','#EF4444','Vermelho'], ['green','#22C55E','Verde'],
            ['light_blue','#38BDF8','Azul claro'], ['dark_blue','#1D4ED8','Azul escuro'],
            ['purple','#9333EA','Roxo'], ['pink','#EC4899','Rosa'],
            ['orange','#F97316','Laranja'], ['yellow','#EAB308','Amarelo'],
            ['black','#111827','Preto'], ['','#FFFFFF','Remover cor']
        ];
        const palette = document.createElement('div');
        palette.id = 'item-row-color-palette';
        palette.className = 'item-row-color-palette';
        palette.innerHTML = colors.map(([key, hex, label]) =>
            `<button type="button" title="${label}" style="--swatch:${hex}" onclick="Items.setRowColor(event,${itemId},'${key}')">${key === '' ? '×' : ''}</button>`
        ).join('');
        document.body.appendChild(palette);
        const rect = event.currentTarget.getBoundingClientRect();
        palette.style.left = `${Math.min(rect.left, window.innerWidth - 190)}px`;
        palette.style.top = `${rect.bottom + 5}px`;
        setTimeout(() => document.addEventListener('click', () => palette.remove(), { once: true }), 0);
    },

    async setRowColor(event, itemId, color) {
        event.stopPropagation();
        try {
            await API.post(`/api/items/${itemId}/row-color`, { project_id: window.App.currentProjectId, row_color: color });
            document.getElementById('item-row-color-palette')?.remove();
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao marcar linha: ${err.message}`, 'error');
        }
    },

    updateBulkToolbar() {
        const toolbar = document.getElementById('bulk-actions-toolbar');
        const countSpan = document.getElementById('bulk-selection-count');
        
        const count = this.selectedIds.size;
        if (count > 0) {
            countSpan.innerText = `${count} itens selecionados`;
            toolbar.classList.remove('hidden');
        } else {
            toolbar.classList.add('hidden');
        }
    },

    async inlineTradeEdit(itemId, field, value) {
        const previous = this.inlineTradeQueues.get(itemId) || Promise.resolve();
        const queued = previous.catch(() => {}).then(() => this._saveInlineTradeEdit(itemId, field, value));
        this.inlineTradeQueues.set(itemId, queued);
        try {
            await queued;
        } finally {
            if (this.inlineTradeQueues.get(itemId) === queued) this.inlineTradeQueues.delete(itemId);
        }
    },

    async _saveInlineTradeEdit(itemId, field, value) {
        const valNum = field.includes('hours') ? (parseFloat(value) || 0.0) : (parseInt(value) || 0);
        
        try {
            const item = await API.get(`/api/items/${itemId}`);
            item[field] = valNum;
            
            // Recompute consolidated HH and headcount
            const mec_hc = item.mec_headcount || 0;
            const mec_h = item.mec_hours || 0.0;
            const ele_hc = item.ele_headcount || 0;
            const ele_h = item.ele_hours || 0.0;
            const sol_hc = item.sol_headcount || 0;
            const sol_h = item.sol_hours || 0.0;
            
            const trade_hh = (mec_hc * mec_h) + (ele_hc * ele_h) + (sol_hc * sol_h);
            const trade_hc = mec_hc + ele_hc + sol_hc;
            
            if (trade_hc > 0 || trade_hh > 0) {
                item.headcount = trade_hc;
                item.duration_hours = Math.max(mec_h, ele_h, sol_h);
                item.hh = trade_hh;
            } else {
                item.hh = (item.duration_hours || 0.0) * (item.headcount || 1);
            }
            
            await API.put(`/api/items/${itemId}`, item);
            const savedItem = await API.get(`/api/items/${itemId}`);
            const cellHh = document.getElementById(`hh-cell-${itemId}`);
            if (cellHh) cellHh.innerHTML = `<strong>${Number(savedItem.hh || 0).toFixed(1).replace('.', ',')}</strong>`;
            UI.showToast("Recurso atualizado!", "success", 1200);
        } catch (err) {
            UI.showToast(`Erro ao salvar recurso: ${err.message}`, 'error');
            this.load();
        }
    },

    updateModalTradePreviews() {
        const mecHc = parseInt(document.getElementById('form-item-mec-hc')?.value || 0) || 0;
        const mecH = parseFloat(document.getElementById('form-item-mec-hours')?.value || 0.0) || 0.0;
        const eleHc = parseInt(document.getElementById('form-item-ele-hc')?.value || 0) || 0;
        const eleH = parseFloat(document.getElementById('form-item-ele-hours')?.value || 0.0) || 0.0;
        const solHc = parseInt(document.getElementById('form-item-sol-hc')?.value || 0) || 0;
        const solH = parseFloat(document.getElementById('form-item-sol-hours')?.value || 0.0) || 0.0;

        const mecHh = mecHc * mecH;
        const eleHh = eleHc * eleH;
        const solHh = solHc * solH;
        const totalHc = mecHc + eleHc + solHc;
        const totalHh = mecHh + eleHh + solHh;

        const elMecHh = document.getElementById('form-item-mec-hh-preview');
        if (elMecHh) elMecHh.innerText = mecHh.toFixed(1).replace('.', ',');
        const elEleHh = document.getElementById('form-item-ele-hh-preview');
        if (elEleHh) elEleHh.innerText = eleHh.toFixed(1).replace('.', ',');
        const elSolHh = document.getElementById('form-item-sol-hh-preview');
        if (elSolHh) elSolHh.innerText = solHh.toFixed(1).replace('.', ',');

        const elTotalHc = document.getElementById('form-item-total-hc-preview');
        if (elTotalHc) elTotalHc.innerText = `${totalHc} pessoa${totalHc !== 1 ? 's' : ''}`;
        const elTotalHh = document.getElementById('form-item-total-hh-preview');
        if (elTotalHh) elTotalHh.innerText = `${totalHh.toFixed(1).replace('.', ',')} HH`;

        // Update hidden inputs for fallback
        const elDur = document.getElementById('form-item-duration');
        if (elDur) elDur.value = Math.max(mecH, eleH, solH) || 0.0;
        const elHc = document.getElementById('form-item-headcount');
        if (elHc) elHc.value = totalHc || 0;
    },

    openCreateModal() {
        document.getElementById('modal-item-title').innerText = "Novo Item de Manutenção";
        document.getElementById('form-item-id').value = "";
        document.getElementById('form-item-identifier').value = "";
        document.getElementById('form-item-obj-type').value = "EQUIPAMENTO";
        document.getElementById('form-item-obj-code').value = "";
        document.getElementById('form-item-desc').value = "";
        document.getElementById('form-item-plan').value = "";
        const formTeamEl = document.getElementById('form-item-team');
        if (formTeamEl) formTeamEl.value = "";
        document.getElementById('form-item-gpm').value = "";
        document.getElementById('form-item-wc').value = "";
        document.getElementById('form-item-condition').value = "P";
        document.getElementById('form-item-priority').value = "3";
        
        // Trades inputs
        document.getElementById('form-item-mec-hc').value = "";
        document.getElementById('form-item-mec-hours').value = "";
        document.getElementById('form-item-ele-hc').value = "";
        document.getElementById('form-item-ele-hours').value = "";
        document.getElementById('form-item-sol-hc').value = "";
        document.getElementById('form-item-sol-hours').value = "";
        this.updateModalTradePreviews();

        document.getElementById('form-item-start').value = "";
        document.getElementById('form-item-status').value = "ACTIVE";
        document.getElementById('form-item-notes').value = "";
        const standardSelect = document.getElementById('select-standard-item');
        if (standardSelect) {
            standardSelect.value = '';
            standardSelect.disabled = false;
            delete standardSelect.dataset.selectedStandardId;
            standardSelect.closest('.form-group')?.classList.remove('hidden');
        }
        document.getElementById('btn-generate-item-standard')?.classList.add('hidden');

        document.getElementById('form-item-desc-chars').innerText = "0 / 35 caracteres";
        document.getElementById('form-item-desc-chars').style.color = '';
        document.getElementById('form-item-desc-warning').classList.add('hidden');
        document.getElementById('item-plan-details-summary').classList.add('hidden');

        document.getElementById('modal-item').classList.remove('hidden');
    },

    async openEditModal(itemId) {
        UI.showLoader("Carregando item...");
        try {
            const item = await API.get(`/api/items/${itemId}`);
            
            document.getElementById('modal-item-title').innerText = "Editar Item de Manutenção";
            document.getElementById('form-item-id').value = item.id;
            document.getElementById('form-item-identifier').value = item.legacy_identifier;
            document.getElementById('form-item-obj-type').value = item.object_type;
            document.getElementById('form-item-obj-code').value = item.object_code;
            document.getElementById('form-item-desc').value = item.description;
            document.getElementById('form-item-plan').value = item.plan_id || "";
            document.getElementById('form-item-gpm').value = item.gpm;
            document.getElementById('form-item-wc').value = item.work_center;
            document.getElementById('form-item-condition').value = item.condition_code;
            document.getElementById('form-item-priority').value = item.priority;
            
            // Trade inputs
            document.getElementById('form-item-mec-hc').value = item.mec_headcount || 0;
            document.getElementById('form-item-mec-hours').value = item.mec_hours || 0.0;
            document.getElementById('form-item-ele-hc').value = item.ele_headcount || 0;
            document.getElementById('form-item-ele-hours').value = item.ele_hours || 0.0;
            document.getElementById('form-item-sol-hc').value = item.sol_headcount || 0;
            document.getElementById('form-item-sol-hours').value = item.sol_hours || 0.0;
            this.updateModalTradePreviews();

            document.getElementById('form-item-start').value = item.legacy_start !== null ? item.legacy_start : "";
            document.getElementById('form-item-status').value = item.status;
            document.getElementById('form-item-notes').value = item.notes || '';
            const standardSelect = document.getElementById('select-standard-item');
            if (standardSelect) {
                standardSelect.value = '';
                standardSelect.disabled = false;
                delete standardSelect.dataset.selectedStandardId;
                standardSelect.closest('.form-group')?.classList.remove('hidden');
            }
            document.getElementById('btn-generate-item-standard')?.classList.remove('hidden');

            // Run checks
            document.getElementById('form-item-desc').oninput();
            document.getElementById('form-item-plan').onchange();

            document.getElementById('modal-item').classList.remove('hidden');
        } catch (err) {
            UI.showToast(`Erro ao carregar dados do item: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async save() {
        const id = document.getElementById('form-item-id').value;
        const identifier = document.getElementById('form-item-identifier').value.trim();
        const objType = document.getElementById('form-item-obj-type').value;
        const objCode = document.getElementById('form-item-obj-code').value.trim();
        const desc = document.getElementById('form-item-desc').value.trim();
        const planId = document.getElementById('form-item-plan').value;
        const gpm = document.getElementById('form-item-gpm').value.trim();
        const wc = document.getElementById('form-item-wc').value.trim();
        const cond = document.getElementById('form-item-condition').value;
        const priority = document.getElementById('form-item-priority').value;
        
        // Trades values
        const mecHc = parseInt(document.getElementById('form-item-mec-hc')?.value || 0) || 0;
        const mecH = parseFloat(document.getElementById('form-item-mec-hours')?.value || 0.0) || 0.0;
        const eleHc = parseInt(document.getElementById('form-item-ele-hc')?.value || 0) || 0;
        const eleH = parseFloat(document.getElementById('form-item-ele-hours')?.value || 0.0) || 0.0;
        const solHc = parseInt(document.getElementById('form-item-sol-hc')?.value || 0) || 0;
        const solH = parseFloat(document.getElementById('form-item-sol-hours')?.value || 0.0) || 0.0;

        const totalHc = mecHc + eleHc + solHc;
        const duration = Math.max(mecH, eleH, solH) || 0.0;

        const start = document.getElementById('form-item-start').value.trim();
        const status = document.getElementById('form-item-status').value;
        const notes = document.getElementById('form-item-notes').value.trim();

        if ((id && !identifier) || !objCode || !desc || !planId || !gpm || !wc || !cond || priority === "") {
            UI.showToast("Preencha todos os campos obrigatórios (*).", 'error');
            return;
        }

        const data = {
            project_id: window.App.currentProjectId,
            legacy_identifier: identifier,
            plan_id: parseInt(planId),
            object_type: objType,
            object_code: objCode,
            gpm: gpm,
            work_center: wc,
            condition_code: cond,
            priority: parseInt(priority),
            legacy_start: start !== '' ? parseInt(start) : null,
            description: desc,
            duration_hours: duration,
            headcount: totalHc,
            mec_headcount: mecHc,
            mec_hours: mecH,
            ele_headcount: eleHc,
            ele_hours: eleH,
            sol_headcount: solHc,
            sol_hours: solH,
            status: status,
            notes: notes
        };

        UI.showLoader("Salvando item...");
        try {
            const selectStdEl = document.getElementById('select-standard-item');
            const stdId = selectStdEl ? selectStdEl.dataset.selectedStandardId : null;

            if (id && stdId) {
                const operations = await API.get('/api/operations', {
                    project_id: window.App.currentProjectId, item_id: parseInt(id), limit: 10000
                });
                const hasStructure = (operations.operations || []).some(op => String(op.item_id) === String(id));
                if (hasStructure && !window.confirm('Este item já possui operações e possivelmente textos longos. Ao continuar, toda essa estrutura será substituída pela estrutura do modelo. Deseja continuar?')) {
                    return;
                }
                await API.post(`/api/items/${id}/apply-standard/${stdId}`, {
                    ...data, replace_existing: hasStructure
                });
                UI.showToast("Modelo aplicado: dados, operações e textos longos foram substituídos!", "success", 4500);
            } else if (id) {
                await API.put(`/api/items/${id}`, data);
                UI.showToast("Item de manutenção atualizado com sucesso!");
            } else if (stdId) {
                await API.post(`/api/items/from-standard/${stdId}`, data);
                UI.showToast("Item criado a partir do modelo padrão com operações e procedimentos!", "success", 4000);
                if (selectStdEl) delete selectStdEl.dataset.selectedStandardId;
            } else {
                await API.post('/api/items', data);
                UI.showToast("Item de manutenção criado com sucesso!");
            }
            document.getElementById('modal-item').classList.add('hidden');
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao salvar item: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    delete(itemId) {
        const item = this.plansList; // loaded via populate
        const cascadeRelated = window.confirm(
            "Ao confirmar a exclusão do item, deseja excluir também suas OPERAÇÕES e TEXTOS LONGOS?\n\n" +
            "OK = excluir todo o pacote.\nCancelar = manter relacionados e marcá-los como erro."
        );
        window.App.confirm("Excluir Item", "Tem certeza que deseja excluir este item de manutenção? Esta ação é irreversível.", async () => {
            UI.showLoader("Excluindo item...");
            try {
                await API.delete(`/api/items/${itemId}`, { cascade_related: cascadeRelated });
                UI.showToast("Item de manutenção excluído com sucesso!");
                await Items.load();
            } catch (err) {
                UI.showToast(`Erro ao excluir item: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    // --- BULK OPERATIONS ---
    
    openBulkAssignPlanModal() {
        const count = this.selectedIds.size;
        document.getElementById('bulk-assign-count-text').innerText = `${count} itens selecionados serão vinculados a um novo plano de reparo.`;
        document.getElementById('bulk-assign-select-plan').value = "";
        document.getElementById('bulk-assign-plan-summary').classList.add('hidden');
        document.getElementById('bulk-assign-impact-box').classList.add('hidden');
        
        document.getElementById('modal-bulk-assign-plan').classList.remove('hidden');
    },

    async updateBulkAssignPreview() {
        const planId = document.getElementById('bulk-assign-select-plan').value;
        const summaryBox = document.getElementById('bulk-assign-plan-summary');
        const impactBox = document.getElementById('bulk-assign-impact-box');
        const impactList = document.getElementById('bulk-assign-impact-list');
        
        if (!planId) {
            summaryBox.classList.add('hidden');
            impactBox.classList.add('hidden');
            return;
        }

        const plan = this.plansList.find(p => p.id == planId);
        if (plan) {
            summaryBox.classList.remove('hidden');
            const nextOcc = plan.reference_counter !== null
                ? calculations_occurrence_display(plan.reference_counter, plan.cycle, window.App.currentCounter)
                : 'Pendente';
            
            summaryBox.innerHTML = `
                <span>Plano Escolhido: <strong>${plan.legacy_code}</strong></span>
                <span>Ciclo: <strong>${plan.cycle} ${plan.unit}</strong></span>
                <span>Próxima Parada: <strong>${nextOcc}</strong></span>
            `;

            // Calculate estimated HH sum of selected items
            let totalSelectedHH = 0;
            // Get selected items info from loaded list
            const allItemsData = await API.get('/api/items', { project_id: window.App.currentProjectId, limit: 100000 });
            let unassignedCount = 0;
            let overwrittenCount = 0;
            
            allItemsData.items.forEach(item => {
                if (this.selectedIds.has(item.id)) {
                    const hc = item.headcount !== null ? item.headcount : 1;
                    totalSelectedHH += item.duration_hours * hc;
                    if (item.plan_id === null) {
                        unassignedCount++;
                    } else if (item.plan_id != planId) {
                        overwrittenCount++;
                    }
                }
            });

            impactBox.classList.remove('hidden');
            impactList.innerHTML = `
                <li>Itens sem plano que serão vinculados: <strong>${unassignedCount}</strong></li>
                <li>Itens que terão o plano substituído: <strong>${overwrittenCount}</strong></li>
                <li>Carga total de HH recalculada: <strong>+ ${totalSelectedHH.toFixed(1).replace('.', ',')} HH</strong></li>
                <li>Faseamento planejado: <strong>Parada inicial ${plan.reference_counter !== null ? plan.reference_counter : 'Pendente'} com ciclo de ${plan.cycle}</strong></li>
            `;
        }
    },

    async bulkAssignPlanConfirm() {
        const planId = document.getElementById('bulk-assign-select-plan').value;
        if (!planId) {
            UI.showToast("Selecione um plano de destino.", "error");
            return;
        }

        const itemIds = Array.from(this.selectedIds);
        UI.showLoader("Vinculando itens...");
        try {
            await API.post('/api/items/bulk-assign-plan', {
                project_id: window.App.currentProjectId,
                item_ids: itemIds,
                plan_id: parseInt(planId)
            });
            UI.showToast(`Plano atribuído com sucesso a ${itemIds.length} itens!`);
            document.getElementById('modal-bulk-assign-plan').classList.add('hidden');
            this.selectedIds.clear();
            await this.load();
        } catch (err) {
            UI.showToast(`Erro na atribuição em massa: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    openBulkEditFieldsModal() {
        const count = this.selectedIds.size;
        document.getElementById('bulk-edit-fields-count-text').innerText = `${count} itens selecionados serão alterados em massa.`;
        
        // Reset form checkboxes and fields
        ['gpm', 'wc', 'condition', 'priority', 'headcount', 'ele-headcount', 'ele-hours',
         'mec-headcount', 'mec-hours', 'sol-headcount', 'sol-hours'].forEach(field => {
            const cb = document.getElementById(`bulk-enable-${field}`);
            if (cb) cb.checked = false;
            const input = document.getElementById(`bulk-input-${field}`);
            if (input) {
                input.value = "";
                input.disabled = true;
            }
        });


        // Set default values inside selects
        document.getElementById('bulk-input-condition').value = 'P';
        document.getElementById('bulk-input-priority').value = '3';

        document.getElementById('modal-bulk-edit-fields').classList.remove('hidden');
    },

    async bulkEditFieldsConfirm() {
        const count = this.selectedIds.size;
        const updates = {};

        if (document.getElementById('bulk-enable-gpm').checked) {
            updates.gpm = document.getElementById('bulk-input-gpm').value.trim();
        }
        if (document.getElementById('bulk-enable-wc').checked) {
            updates.work_center = document.getElementById('bulk-input-wc').value.trim();
        }
        if (document.getElementById('bulk-enable-condition').checked) {
            updates.condition_code = document.getElementById('bulk-input-condition').value;
        }
        if (document.getElementById('bulk-enable-priority').checked) {
            updates.priority = parseInt(document.getElementById('bulk-input-priority').value);
        }
        if (document.getElementById('bulk-enable-headcount').checked) {
            const hc = document.getElementById('bulk-input-headcount').value.trim();
            updates.headcount = hc !== '' ? parseInt(hc) : null;
        }
        const tradeFields = [
            ['ele-headcount', 'ele_headcount', true],
            ['ele-hours', 'ele_hours', false],
            ['mec-headcount', 'mec_headcount', true],
            ['mec-hours', 'mec_hours', false],
            ['sol-headcount', 'sol_headcount', true],
            ['sol-hours', 'sol_hours', false]
        ];
        for (const [elementField, updateField, integerValue] of tradeFields) {
            if (!document.getElementById(`bulk-enable-${elementField}`).checked) continue;
            const rawValue = document.getElementById(`bulk-input-${elementField}`).value.trim().replace(',', '.');
            if (rawValue === '') {
                UI.showToast(`Preencha o campo ${updateField.replace('_', ' ')}.`, 'error');
                return;
            }
            const value = integerValue ? Number.parseInt(rawValue, 10) : Number.parseFloat(rawValue);
            if (!Number.isFinite(value) || value < 0 || (integerValue && !Number.isInteger(Number(rawValue)))) {
                UI.showToast('Efetivos e horas devem ser valores numéricos maiores ou iguais a zero.', 'error');
                return;
            }
            updates[updateField] = value;
        }


        if (Object.keys(updates).length === 0) {
            UI.showToast("Ative e preencha pelo menos um campo para editar em massa.", "error");
            return;
        }

        const itemIds = Array.from(this.selectedIds);
        window.App.confirm("Aplicar Alterações em Massa", `Tem certeza que deseja atualizar ${count} itens em massa? Esta ação irá recalcular as cargas de trabalho.`, async () => {
            UI.showLoader("Atualizando itens em massa...");
            try {
                await API.post('/api/items/bulk-update', {
                    project_id: window.App.currentProjectId,
                    item_ids: itemIds,
                    updates: updates
                });
                UI.showToast(`Campos atualizados com sucesso para ${count} itens!`);
                document.getElementById('modal-bulk-edit-fields').classList.add('hidden');
                Items.selectedIds.clear();
                await Items.load();
            } catch (err) {
                UI.showToast(`Erro na atualização em massa: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    bulkUpdateStatus(newStatus) {
        const itemIds = Array.from(this.selectedIds);
        const actionLabel = newStatus === 'ACTIVE' ? 'ativar' : 'inativar';
        
        window.App.confirm("Alterar Status em Massa", `Deseja realmente ${actionLabel} os ${itemIds.length} itens selecionados?`, async () => {
            UI.showLoader("Alterando status...");
            try {
                await API.post('/api/items/bulk-update', {
                    project_id: window.App.currentProjectId,
                    item_ids: itemIds,
                    updates: { status: newStatus }
                });
                UI.showToast(`Status atualizado com sucesso!`);
                Items.selectedIds.clear();
                await Items.load();
            } catch (err) {
                UI.showToast(`Erro ao alterar status: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    bulkDelete() {
        const itemIds = Array.from(this.selectedIds);
        if (!itemIds.length) {
            UI.showToast('Selecione pelo menos um item para excluir.', 'warning');
            return;
        }

        const projectId = App.getValidProjectId();
        const msg = `Tem certeza que deseja excluir permanentemente os <strong>${itemIds.length} itens</strong> selecionados?<br><br>` +
            `<span style="color:var(--danger-color);font-size:12px;">⚠️ Todas as operações e textos longos vinculados aos itens selecionados também serão excluídos.</span>`;

        window.App.confirm("Excluir Itens em Massa", msg, async () => {
            App.showBulkProgressModal("Excluindo Itens em Massa...", `Transmitindo solicitação para excluir <strong>${itemIds.length} itens</strong>...`);
            try {
                App.updateBulkProgressModal(65, "Processando exclusão no banco de dados SQLite...");
                const res = await API.post('/api/items/bulk-delete', {
                    project_id: projectId,
                    ids: itemIds,
                    cascade_related: true
                });
                App.finishBulkProgressModal(true, "Exclusão Concluída!", res.message || `${itemIds.length} itens excluídos com sucesso!`);
                Items.selectedIds.clear();
                Items.updateBulkToolbar();
                await Items.load();
            } catch (err) {
                App.finishBulkProgressModal(false, "Erro na Exclusão dos Itens", `Falha ao processar exclusão no servidor: ${err.message}`);
            }
        });
    },


    async openBulkApplyStandardModal() {
        const ids = Array.from(this.selectedIds);
        if (!ids.length) {
            UI.showToast('Selecione pelo menos um item para aplicar o modelo.', 'warning');
            return;
        }

        this.bulkStandardPreview = null;
        this.bulkStandardDraftOperations = [];
        this.bulkStandardSelectedId = null;

        const modal = document.getElementById('modal-bulk-apply-standard');
        const countEl = document.getElementById('bulk-standard-selected-count');
        const empty = document.getElementById('bulk-standard-empty-preview');
        const content = document.getElementById('bulk-standard-preview-content');
        const applyBtn = document.getElementById('btn-bulk-standard-apply');
        const footer = document.getElementById('bulk-standard-footer-summary');
        const search = document.getElementById('bulk-standard-search');
        const auth = document.getElementById('bulk-standard-replace-authorization');
        if (countEl) countEl.textContent = `${ids.length} ${ids.length === 1 ? 'item selecionado' : 'itens selecionados'}`;
        if (empty) empty.classList.remove('hidden');
        if (content) content.classList.add('hidden');
        if (applyBtn) applyBtn.classList.add('hidden');
        if (footer) footer.textContent = 'Selecione um modelo para continuar.';
        if (search) search.value = '';
        if (auth) auth.checked = false;
        document.querySelector('input[name="bulk-standard-conflict-policy"][value="skip"]')?.click();
        modal?.classList.remove('hidden');

        try {
            const models = await API.get('/api/standards/items');
            this.bulkStandardModels = Array.isArray(models) ? models : [];
            this.populateBulkStandardCategories();
            this.renderBulkStandardLibrary();
        } catch (err) {
            UI.showToast(`Erro ao carregar biblioteca de modelos: ${err.message}`, 'error');
            const list = document.getElementById('bulk-standard-library-list');
            if (list) list.innerHTML = `<div class="txt-error" style="padding:18px; text-align:center;">${UI.escapeHTML(err.message)}</div>`;
        }
    },

    closeBulkApplyStandardModal() {
        document.getElementById('modal-bulk-apply-standard')?.classList.add('hidden');
        this.bulkStandardPreview = null;
        this.bulkStandardDraftOperations = [];
        this.bulkStandardSelectedId = null;
    },

    populateBulkStandardCategories() {
        const select = document.getElementById('bulk-standard-category');
        if (!select) return;
        const current = select.value;
        const categories = [...new Set(this.bulkStandardModels.map(m => String(m.category || 'GERAL').trim()).filter(Boolean))]
            .sort((a, b) => a.localeCompare(b, 'pt-BR'));
        select.innerHTML = '<option value="">Todas as categorias</option>' + categories.map(cat =>
            `<option value="${UI.escapeHTML(cat)}">${UI.escapeHTML(cat)}</option>`
        ).join('');
        if (categories.includes(current)) select.value = current;
    },

    renderBulkStandardLibrary() {
        const listEl = document.getElementById('bulk-standard-library-list');
        const countEl = document.getElementById('bulk-standard-library-count');
        if (!listEl) return;
        const q = String(document.getElementById('bulk-standard-search')?.value || '').trim().toLocaleLowerCase('pt-BR');
        const category = String(document.getElementById('bulk-standard-category')?.value || '').trim();
        const filtered = this.bulkStandardModels.filter(model => {
            if (category && String(model.category || 'GERAL') !== category) return false;
            if (!q) return true;
            const haystack = `${model.title || ''} ${model.category || ''} ${model.description || ''} ${model.object_code || ''}`.toLocaleLowerCase('pt-BR');
            return haystack.includes(q);
        });
        if (countEl) countEl.textContent = `${filtered.length}/${this.bulkStandardModels.length}`;
        if (!filtered.length) {
            listEl.innerHTML = '<div class="text-muted" style="padding:18px; text-align:center;">Nenhum modelo encontrado.</div>';
            return;
        }
        listEl.innerHTML = filtered.map(model => {
            const active = Number(model.id) === Number(this.bulkStandardSelectedId) ? ' active' : '';
            const desc = String(model.description || '').trim();
            const clipped = desc.length > 90 ? `${desc.slice(0, 90)}…` : desc;
            return `<button type="button" class="bulk-standard-model-card${active}" data-standard-id="${model.id}">
                <span class="model-title">${UI.escapeHTML(model.title || `Modelo ${model.id}`)}</span>
                <span class="model-meta">
                    <span>${UI.escapeHTML(model.category || 'GERAL')}</span>
                    <span>•</span>
                    <span>${Number(model.operations_count || 0)} op.</span>
                    ${model.work_center ? `<span>• ${UI.escapeHTML(model.work_center)}</span>` : ''}
                </span>
                ${clipped ? `<span class="model-description">${UI.escapeHTML(clipped)}</span>` : ''}
            </button>`;
        }).join('');
        listEl.querySelectorAll('.bulk-standard-model-card').forEach(card => {
            card.onclick = () => this.selectBulkStandardModel(Number(card.dataset.standardId));
        });
    },

    async selectBulkStandardModel(standardId) {
        const ids = Array.from(this.selectedIds);
        if (!ids.length) return;
        this.bulkStandardSelectedId = Number(standardId);
        this.renderBulkStandardLibrary();
        const empty = document.getElementById('bulk-standard-empty-preview');
        const content = document.getElementById('bulk-standard-preview-content');
        if (empty) {
            empty.classList.remove('hidden');
            empty.innerHTML = '<div style="font-size:28px;">⏳</div><strong>Carregando pré-visualização...</strong>';
        }
        if (content) content.classList.add('hidden');
        try {
            const preview = await API.post('/api/items/bulk-standard-preview', {
                project_id: window.App.currentProjectId,
                item_ids: ids,
                standard_id: Number(standardId)
            });
            this.bulkStandardPreview = preview;
            this.bulkStandardDraftOperations = JSON.parse(JSON.stringify(preview.standard?.operations || []));
            this.renderBulkStandardPreview();
        } catch (err) {
            this.bulkStandardPreview = null;
            this.bulkStandardDraftOperations = [];
            if (empty) {
                empty.classList.remove('hidden');
                empty.innerHTML = `<div style="font-size:30px;">⚠️</div><strong>Não foi possível carregar o modelo</strong><span>${UI.escapeHTML(err.message)}</span>`;
            }
            UI.showToast(`Erro ao preparar aplicação do modelo: ${err.message}`, 'error');
        }
    },

    renderBulkStandardPreview() {
        const preview = this.bulkStandardPreview;
        if (!preview) return;
        const empty = document.getElementById('bulk-standard-empty-preview');
        const content = document.getElementById('bulk-standard-preview-content');
        if (empty) empty.classList.add('hidden');
        if (content) content.classList.remove('hidden');

        const title = document.getElementById('bulk-standard-preview-model-title');
        if (title) title.textContent = preview.standard?.title || 'Modelo técnico';
        const summary = preview.summary || {};
        const chips = document.getElementById('bulk-standard-summary-chips');
        if (chips) chips.innerHTML = `
            <span class="bulk-standard-summary-chip"><strong>${summary.selected_items || 0}</strong> itens</span>
            <span class="bulk-standard-summary-chip"><strong>${summary.operations_per_item || 0}</strong> op./item</span>
            <span class="bulk-standard-summary-chip"><strong>${summary.long_texts_per_item || 0}</strong> textos/item</span>
            ${summary.conflicting_items ? `<span class="bulk-standard-summary-chip" style="border-color:#E7B75D;background:#FFF8E8;"><strong>${summary.conflicting_items}</strong> com estrutura</span>` : ''}`;

        this.renderBulkStandardConflicts();
        this.populateBulkStandardPreviewItems();
        this.renderBulkStandardOrderHeader();
        this.renderBulkStandardOperationsEditor();
        document.getElementById('btn-bulk-standard-apply')?.classList.remove('hidden');
        this.updateBulkStandardFooterSummary();
    },

    renderBulkStandardConflicts() {
        const preview = this.bulkStandardPreview;
        const box = document.getElementById('bulk-standard-conflict-box');
        const summaryEl = document.getElementById('bulk-standard-conflict-summary');
        const itemsEl = document.getElementById('bulk-standard-conflict-items');
        const conflicts = preview?.conflicts || [];
        if (!box) return;
        const skipRadio = document.querySelector('input[name="bulk-standard-conflict-policy"][value="skip"]');
        if (skipRadio) skipRadio.checked = true;
        const auth = document.getElementById('bulk-standard-replace-authorization');
        if (auth) auth.checked = false;
        document.getElementById('bulk-standard-replace-authorization-wrap')?.classList.add('hidden');
        if (!conflicts.length) {
            box.classList.add('hidden');
            return;
        }
        box.classList.remove('hidden');
        if (summaryEl) summaryEl.innerHTML = `<strong>${conflicts.length}</strong> ${conflicts.length === 1 ? 'item já possui' : 'itens já possuem'} operações e/ou textos longos. Escolha abaixo o que fazer com eles.`;
        if (itemsEl) itemsEl.innerHTML = conflicts.map(item => `
            <div class="bulk-standard-conflict-item">
                <span><strong>ID ${UI.escapeHTML(String(item.legacy_identifier || item.id))}</strong> — ${UI.escapeHTML(item.description || item.object_code || '')}</span>
                <span>${Number(item.operations_count || 0)} op. / ${Number(item.long_texts_count || 0)} textos</span>
            </div>`).join('');
    },

    handleBulkStandardConflictPolicyChange() {
        const policy = document.querySelector('input[name="bulk-standard-conflict-policy"]:checked')?.value || 'skip';
        const authWrap = document.getElementById('bulk-standard-replace-authorization-wrap');
        const auth = document.getElementById('bulk-standard-replace-authorization');
        if (policy === 'replace' && (this.bulkStandardPreview?.conflicts || []).length) {
            authWrap?.classList.remove('hidden');
        } else {
            authWrap?.classList.add('hidden');
            if (auth) auth.checked = false;
        }
        this.updateBulkStandardFooterSummary();
    },

    populateBulkStandardPreviewItems() {
        const select = document.getElementById('bulk-standard-preview-item');
        if (!select || !this.bulkStandardPreview) return;
        select.innerHTML = (this.bulkStandardPreview.items || []).map(item =>
            `<option value="${item.id}">ID ${UI.escapeHTML(String(item.legacy_identifier || item.id))} — ${UI.escapeHTML(item.description || item.object_code || '')}</option>`
        ).join('');
    },

    renderBulkStandardOrderHeader() {
        const preview = this.bulkStandardPreview;
        const container = document.getElementById('bulk-standard-order-header');
        if (!preview || !container) return;
        const selectedId = Number(document.getElementById('bulk-standard-preview-item')?.value || preview.items?.[0]?.id || 0);
        const item = (preview.items || []).find(row => Number(row.id) === selectedId) || preview.items?.[0];
        if (!item) return;
        const field = (label, value, wide=false) => `<div class="bulk-standard-order-field${wide ? ' wide' : ''}"><span class="label">${UI.escapeHTML(label)}</span><span class="value" title="${UI.escapeHTML(String(value ?? ''))}">${UI.escapeHTML(String(value ?? '—'))}</span></div>`;
        container.innerHTML = [
            field('Identificador / ID', item.legacy_identifier || item.id),
            field('Tipo de objeto', item.object_type),
            field('Equipamento / Local', item.object_code),
            field('Tipo de ordem', item.order_type || 'PM13'),
            field('Descrição da ordem', item.description, true),
            field('Plano', item.plan_code || 'Sem plano'),
            field('GPM', item.gpm),
            field('Centro de trabalho do item', item.work_center),
            field('Condição / Prioridade', `${item.condition_code || '—'} / ${item.priority ?? '—'}`),
        ].join('');
    },

    renderBulkStandardOperationsEditor() {
        const container = document.getElementById('bulk-standard-operations-editor');
        if (!container) return;
        const ops = this.bulkStandardDraftOperations || [];
        if (!ops.length) {
            container.innerHTML = '<div class="text-muted" style="padding:18px;text-align:center;border:1px dashed #CBD5C6;border-radius:8px;">Nenhuma operação na aplicação. Adicione uma operação para continuar.</div>';
            return;
        }
        const val = value => UI.escapeHTML(String(value ?? ''));
        container.innerHTML = ops.map((op, opIndex) => {
            const texts = op.long_texts || [];
            return `<div class="bulk-standard-operation-card" data-op-index="${opIndex}">
                <div class="bulk-standard-operation-card-header">
                    <strong>Operação ${opIndex + 1} — ${val(op.operation_code || 'sem código')}</strong>
                    <button type="button" class="btn btn-danger btn-xs" onclick="Items.removeBulkStandardOperation(${opIndex})">Remover operação</button>
                </div>
                <div class="bulk-standard-operation-grid">
                    <div class="form-group"><label>Código *</label><input class="bulk-std-op-code" value="${val(op.operation_code)}" placeholder="0010"></div>
                    <div class="form-group"><label>Subop.</label><input class="bulk-std-op-subcode" value="${val(op.suboperation_code)}"></div>
                    <div class="form-group"><label>C.T.</label><input class="bulk-std-op-wc" value="${val(op.work_center)}" placeholder="Vazio = C.T. do item"></div>
                    <div class="form-group bulk-standard-short-text"><label>Texto breve *</label><input class="bulk-std-op-short" maxlength="40" value="${val(op.short_text)}"></div>
                    <div class="form-group"><label>Unidade</label><input class="bulk-std-op-unit" maxlength="10" value="${val(op.unit || 'H')}"></div>
                    <div class="form-group"><label>Efetivo</label><input type="number" min="0" step="1" class="bulk-std-op-hc" value="${val(op.headcount)}"></div>
                    <div class="form-group"><label>Horas</label><input type="number" min="0" step="0.01" class="bulk-std-op-hours" value="${val(op.hours)}"></div>
                </div>
                <div class="bulk-standard-long-texts">
                    <div class="bulk-standard-long-text-title">
                        <span>Textos longos (${texts.length})</span>
                        <button type="button" class="btn btn-outline btn-xs" onclick="Items.addBulkStandardLongText(${opIndex})">+ Texto longo</button>
                    </div>
                    <div class="bulk-standard-long-text-list">
                        ${texts.length ? texts.map((lt, textIndex) => `<div class="bulk-standard-long-text-row" data-text-index="${textIndex}">
                            <div class="bulk-standard-long-text-grid">
                                <div class="form-group" style="grid-column: 1;">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                        <label style="font-weight:600; color:#334155;">Texto longo / Procedimento técnico (duplo clique para abrir editor)</label>
                                        <button type="button" class="btn btn-xs btn-outline" style="color:#0284C7; border-color:#BAE6FD; padding:1px 6px; font-size:10px;" onclick="Items.openBulkLongTextEditor(this.parentElement.parentElement.querySelector('textarea'))" title="Abrir Editor Estruturado de Texto Longo">📝 Abrir Editor Estruturado</button>
                                    </div>
                                    <textarea class="bulk-std-lt-text" placeholder="Digite o procedimento ou dê dois cliques para abrir o editor padrão..." ondblclick="Items.openBulkLongTextEditor(this)" style="width:100%; min-height:60px;">${val(lt.text)}</textarea>
                                </div>
                                <button type="button" class="btn btn-danger btn-xs" title="Remover texto" onclick="Items.removeBulkStandardLongText(${opIndex},${textIndex})" style="margin-top:22px;">×</button>
                            </div>
                        </div>`).join('') : '<div class="text-muted" style="font-size:10.5px;padding:4px 0 7px;">Esta operação não possui texto longo.</div>'}
                    </div>
                </div>
            </div>`;
        }).join('');
    },

    openBulkLongTextEditor(triggerEl) {
        const modal = document.getElementById('modal-long-text');
        if (!modal) return;

        modal.style.zIndex = '2600';

        const titleEl = document.getElementById('modal-long-text-title');
        if (titleEl) titleEl.textContent = 'Editar Texto Longo / Procedimento Técnico';

        document.querySelectorAll('#modal-long-text .lt-context-panel').forEach(p => p.style.display = 'none');

        const initialText = triggerEl ? triggerEl.value || '' : '';

        if (window.LongTextEditor) {
            LongTextEditor.loadRecord({
                text: initialText,
                structure_mode: 'FREE'
            }, true);
        } else {
            const formText = document.getElementById('form-lt-text');
            if (formText) formText.value = initialText;
        }

        modal.classList.remove('hidden');

        const saveBtn = document.getElementById('btn-save-long-text');
        if (saveBtn) {
            const prevOnClick = saveBtn.onclick;
            saveBtn.onclick = () => {
                const payload = window.LongTextEditor ? LongTextEditor.getPayload() : { text: document.getElementById('form-lt-text')?.value || '' };
                if (triggerEl) {
                    triggerEl.value = payload.text || '';
                    triggerEl.dispatchEvent(new Event('input', { bubbles: true }));
                    triggerEl.dispatchEvent(new Event('change', { bubbles: true }));
                }
                modal.classList.add('hidden');
                saveBtn.onclick = prevOnClick;
                if (window.App && window.App.showToast) window.App.showToast('Texto longo atualizado no modelo.');
            };
        }
    },

    collectBulkStandardOperationsFromDom(strict=true) {
        const cards = Array.from(document.querySelectorAll('#bulk-standard-operations-editor .bulk-standard-operation-card'));
        const operations = cards.map((card, index) => {
            const code = card.querySelector('.bulk-std-op-code')?.value.trim() || '';
            const shortText = card.querySelector('.bulk-std-op-short')?.value.trim() || '';
            if (strict && !code) throw new Error(`Informe o código da operação ${index + 1}.`);
            if (strict && !shortText) throw new Error(`Informe o texto breve da operação ${code || index + 1}.`);
            const longTexts = Array.from(card.querySelectorAll('.bulk-standard-long-text-row')).map(row => ({
                group_code: '',
                group_counter: '',
                text: row.querySelector('.bulk-std-lt-text')?.value || ''
            })).filter(lt => !strict || lt.text.trim());
            return {
                operation_code: code,
                suboperation_code: card.querySelector('.bulk-std-op-subcode')?.value.trim() || '',
                work_center: card.querySelector('.bulk-std-op-wc')?.value.trim() || '',
                short_text: shortText,
                unit: card.querySelector('.bulk-std-op-unit')?.value.trim() || 'H',
                headcount: card.querySelector('.bulk-std-op-hc')?.value ?? '',
                hours: card.querySelector('.bulk-std-op-hours')?.value ?? '',
                long_texts: longTexts
            };
        });
        if (strict && !operations.length) throw new Error('Adicione pelo menos uma operação antes de aplicar o modelo.');
        return operations;
    },

    syncBulkStandardDraftFromDom() {
        const cards = document.querySelectorAll('#bulk-standard-operations-editor .bulk-standard-operation-card');
        if (cards.length) this.bulkStandardDraftOperations = this.collectBulkStandardOperationsFromDom(false);
    },

    addBulkStandardOperation() {
        this.syncBulkStandardDraftFromDom();
        const numericCodes = (this.bulkStandardDraftOperations || []).map(op => parseInt(op.operation_code, 10)).filter(Number.isFinite);
        const nextCode = String((numericCodes.length ? Math.max(...numericCodes) : 0) + 10).padStart(4, '0');
        this.bulkStandardDraftOperations.push({
            operation_code: nextCode,
            suboperation_code: '',
            work_center: '',
            short_text: '',
            unit: 'H',
            headcount: null,
            hours: null,
            long_texts: []
        });
        this.renderBulkStandardOperationsEditor();
        this.updateBulkStandardFooterSummary();
        const cards = document.querySelectorAll('#bulk-standard-operations-editor .bulk-standard-operation-card');
        cards[cards.length - 1]?.scrollIntoView({behavior:'smooth', block:'nearest'});
    },

    removeBulkStandardOperation(index) {
        this.syncBulkStandardDraftFromDom();
        this.bulkStandardDraftOperations.splice(index, 1);
        this.renderBulkStandardOperationsEditor();
        this.updateBulkStandardFooterSummary();
    },

    addBulkStandardLongText(opIndex) {
        this.syncBulkStandardDraftFromDom();
        const op = this.bulkStandardDraftOperations[opIndex];
        if (!op) return;
        if (!Array.isArray(op.long_texts)) op.long_texts = [];
        op.long_texts.push({group_code: '', group_counter: '', text: ''});
        this.renderBulkStandardOperationsEditor();
        this.updateBulkStandardFooterSummary();
        const rows = document.querySelectorAll(`#bulk-standard-operations-editor .bulk-standard-operation-card[data-op-index="${opIndex}"] .bulk-standard-long-text-row`);
        rows[rows.length - 1]?.querySelector('textarea')?.focus();
    },

    removeBulkStandardLongText(opIndex, textIndex) {
        this.syncBulkStandardDraftFromDom();
        const op = this.bulkStandardDraftOperations[opIndex];
        if (!op || !Array.isArray(op.long_texts)) return;
        op.long_texts.splice(textIndex, 1);
        this.renderBulkStandardOperationsEditor();
        this.updateBulkStandardFooterSummary();
    },

    updateBulkStandardFooterSummary() {
        const footer = document.getElementById('bulk-standard-footer-summary');
        const applyBtn = document.getElementById('btn-bulk-standard-apply');
        const preview = this.bulkStandardPreview;
        if (!footer || !preview) return;
        let ops = [];
        try {
            const cards = document.querySelectorAll('#bulk-standard-operations-editor .bulk-standard-operation-card');
            ops = cards.length ? this.collectBulkStandardOperationsFromDom(false) : (this.bulkStandardDraftOperations || []);
        } catch (_) {
            ops = this.bulkStandardDraftOperations || [];
        }
        const textCount = ops.reduce((sum, op) => sum + (op.long_texts || []).filter(lt => String(lt.text || '').trim()).length, 0);
        const conflicts = (preview.conflicts || []).length;
        const selected = Number(preview.summary?.selected_items || 0);
        const policy = document.querySelector('input[name="bulk-standard-conflict-policy"]:checked')?.value || 'skip';
        const target = policy === 'replace' ? selected : Math.max(0, selected - conflicts);
        footer.innerHTML = `<strong>${target}</strong> item(ns) receberão <strong>${target * ops.length}</strong> operações e <strong>${target * textCount}</strong> textos longos.${policy === 'skip' && conflicts ? ` <strong>${conflicts}</strong> item(ns) serão ignorados.` : ''}`;
        if (applyBtn) {
            applyBtn.textContent = `Aplicar em ${target} item${target === 1 ? '' : 's'}`;
            applyBtn.disabled = target <= 0 || ops.length <= 0;
        }
    },

    async applyBulkStandard() {
        const preview = this.bulkStandardPreview;
        if (!preview || !this.bulkStandardSelectedId) return;
        const ids = Array.from(this.selectedIds);
        if (!ids.length) return;
        let operations;
        try {
            operations = this.collectBulkStandardOperationsFromDom(true);
        } catch (err) {
            UI.showToast(err.message, 'error');
            return;
        }

        const conflicts = (preview.conflicts || []).length;
        const policy = document.querySelector('input[name="bulk-standard-conflict-policy"]:checked')?.value || 'skip';
        if (policy === 'replace' && conflicts && !document.getElementById('bulk-standard-replace-authorization')?.checked) {
            UI.showToast('Marque a autorização de substituição para continuar.', 'error');
            document.getElementById('bulk-standard-replace-authorization-wrap')?.scrollIntoView({behavior:'smooth', block:'center'});
            return;
        }
        const target = policy === 'replace' ? ids.length : ids.length - conflicts;
        if (target <= 0) {
            UI.showToast('Todos os itens selecionados já possuem estrutura. Autorize a substituição ou altere a seleção.', 'warning', 4500);
            return;
        }
        const textCount = operations.reduce((sum, op) => sum + (op.long_texts || []).filter(lt => String(lt.text || '').trim()).length, 0);
        const modelTitle = preview.standard?.title || `Modelo ${this.bulkStandardSelectedId}`;
        const replacementWarning = policy === 'replace' && conflicts
            ? `<br><br><strong style="color:#B42318;">⚠ ${conflicts} item(ns) terão as operações e textos longos atuais substituídos.</strong>`
            : (conflicts ? `<br><br>${conflicts} item(ns) com estrutura existente serão ignorados.` : '');
        window.App.confirm(
            'Confirmar Aplicação do Modelo',
            `Aplicar <strong>${UI.escapeHTML(modelTitle)}</strong> em <strong>${target}</strong> item(ns)?<br><br>` +
            `Serão criadas <strong>${target * operations.length}</strong> operações e aproximadamente <strong>${target * textCount}</strong> textos longos.` +
            replacementWarning,
            async () => {
                UI.showLoader('Aplicando operações e textos longos aos itens selecionados...');
                try {
                    const result = await API.post('/api/items/bulk-apply-standard', {
                        project_id: window.App.currentProjectId,
                        item_ids: ids,
                        standard_id: Number(this.bulkStandardSelectedId),
                        conflict_policy: policy,
                        operations
                    });
                    const skippedText = result.skipped_items ? ` ${result.skipped_items} item(ns) com estrutura existente foram ignorados.` : '';
                    const replacedText = result.replaced_items ? ` ${result.replaced_items} item(ns) tiveram a estrutura anterior substituída.` : '';
                    UI.showToast(
                        `Modelo aplicado em ${result.applied_items} item(ns): ${result.operations_created} operações e ${result.long_texts_created} textos longos criados.${skippedText}${replacedText}`,
                        'success', 6500
                    );
                    this.closeBulkApplyStandardModal();
                    this.selectedIds.clear();
                    this.updateBulkToolbar();
                    await this.load();
                    return true;
                } catch (err) {
                    UI.showToast(`Erro ao aplicar modelo em massa: ${err.message}`, 'error', 6000);
                    return false;
                } finally {
                    UI.hideLoader();
                }
            }
        );
    },

    export() {
        const projId = window.App.currentProjectId;
        if (!projId) return;
        
        // Build query params
        this.applyFiltersFromInputs();
        const params = {
            type: 'items',
            project_id: projId,
            search: this.filters.search,
            gpm: this.filters.gpm,
            work_center: this.filters.work_center,
            condition_code: this.filters.condition_code,
            priority: this.filters.priority,
            plan_id: this.filters.plan_id,
            status: this.filters.status,
            without_plan: this.filters.without_plan,
            without_headcount: this.filters.without_headcount,
            duration_zero: this.filters.duration_zero,
            long_desc: this.filters.long_desc
        };
        
        // If selection exists, export only selected? 
        // We can pass selection list in CSV? The API supports filters.
        const query = Object.keys(params)
            .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
            .join('&');
            
        window.open(`/api/export?${query}`, '_blank');
    },

    async clone(id) {
        const confirmExtra = document.getElementById('confirm-extra-content');
        if (!confirmExtra || !window.App?.confirm) return;
        confirmExtra.innerHTML = `
            <div class="form-group" style="margin-top: 8px;">
                <label style="margin-bottom:8px;">O que deseja clonar?</label>
                <label style="display:block; margin-bottom:10px; text-transform:none; font-weight:500; cursor:pointer;">
                    <input type="radio" name="item-clone-mode" value="item" checked>
                    <strong>Somente o item</strong><br>
                    <span style="margin-left:22px; color:var(--text-muted); font-size:12px;">Cria um novo identificador sem copiar operações ou textos longos.</span>
                </label>
                <label style="display:block; text-transform:none; font-weight:500; cursor:pointer;">
                    <input type="radio" name="item-clone-mode" value="complete">
                    <strong>Item + operações + textos longos</strong><br>
                    <span style="margin-left:22px; color:var(--text-muted); font-size:12px;">Copia toda a estrutura e vincula tudo automaticamente ao novo identificador.</span>
                </label>
            </div>`;

        window.App.confirm('Clonar Item', 'Será criado um novo item com o próximo identificador disponível.', async () => {
            const includeStructure = confirmExtra.querySelector('input[name="item-clone-mode"]:checked')?.value === 'complete';
            try {
                UI.showLoader(includeStructure ? 'Clonando item, operações e textos longos...' : 'Clonando item...');
                const result = await API.post(`/api/items/${id}/clone`, {
                    project_id: window.App.currentProjectId,
                    include_structure: includeStructure
                });
                this.filters.order_by = 'display_order';
                this.filters.order_dir = 'ASC';
                const detail = includeStructure
                    ? ` ${result.operations_created || 0} operações e ${result.long_texts_created || 0} textos longos também foram copiados.`
                    : '';
                UI.showToast(`Item clonado com o novo ID ${result.legacy_identifier}.${detail}`, 'success', 5000);
                await this.load();
                return true;
            } catch (err) {
                UI.showToast(`Erro ao clonar item: ${err.message}`, 'error');
                return false;
            } finally {
                UI.hideLoader();
            }
        });
    },

    async bulkClone() {
        const ids = Array.from(this.selectedIds);
        if (!ids.length) return;
        const confirmExtra = document.getElementById('confirm-extra-content');
        if (!confirmExtra || !window.App?.confirm) return;
        confirmExtra.innerHTML = `
            <div class="form-group" style="margin-top: 8px;">
                <label style="margin-bottom:8px;">Aplicar a todos os ${ids.length} itens selecionados:</label>
                <label style="display:block; margin-bottom:10px; text-transform:none; font-weight:500; cursor:pointer;">
                    <input type="radio" name="bulk-item-clone-mode" value="item" checked>
                    <strong>Clonar somente os itens</strong>
                </label>
                <label style="display:block; text-transform:none; font-weight:500; cursor:pointer;">
                    <input type="radio" name="bulk-item-clone-mode" value="complete">
                    <strong>Clonar itens + operações + textos longos</strong>
                </label>
            </div>`;

        window.App.confirm('Clonar Itens Selecionados', `Serão criados ${ids.length} novos itens com novos identificadores.`, async () => {
            const includeStructure = confirmExtra.querySelector('input[name="bulk-item-clone-mode"]:checked')?.value === 'complete';
            let cloned = 0;
            let operationsCreated = 0;
            let longTextsCreated = 0;
            UI.showLoader(includeStructure ? 'Clonando itens e estruturas relacionadas...' : 'Clonando itens selecionados...');
            try {
                for (const id of ids) {
                    const result = await API.post(`/api/items/${id}/clone`, {
                        project_id: window.App.currentProjectId,
                        include_structure: includeStructure
                    });
                    cloned++;
                    operationsCreated += Number(result.operations_created || 0);
                    longTextsCreated += Number(result.long_texts_created || 0);
                }
                this.selectedIds.clear();
                this.updateBulkToolbar();
                const detail = includeStructure
                    ? ` Foram copiadas ${operationsCreated} operações e ${longTextsCreated} textos longos.`
                    : '';
                UI.showToast(`${cloned} ${cloned === 1 ? 'item clonado' : 'itens clonados'} com sucesso.${detail}`, 'success', 5000);
                await this.load();
                return true;
            } catch (err) {
                UI.showToast(`${cloned} de ${ids.length} itens clonados. Erro: ${err.message}`, 'error', 5000);
                await this.load();
                return true;
            } finally { UI.hideLoader(); }
        });
    },

    makeCellEditable(cell, itemId, field, currentValue) {
        if (cell.classList.contains('editing')) return;
        cell.classList.add('editing', 'cell-editing');
        const originalHTML = cell.innerHTML;

        let inputHtml = '';
        if (field === 'condition_code') {
            const conds = ['OPERANDO', 'PARADO'];
            inputHtml = `<select class="table-inline-input">` +
                conds.map(c => `<option value="${c}" ${c === currentValue ? 'selected' : ''}>${c}</option>`).join('') +
                `</select>`;
        } else if (field === 'priority') {
            const prios = [1, 2, 3, 4, 5];
            inputHtml = `<select class="table-inline-input">` +
                prios.map(p => `<option value="${p}" ${p == currentValue ? 'selected' : ''}>${p}</option>`).join('') +
                `</select>`;
        } else {
            inputHtml = `<input type="text" class="table-inline-input" value="${(currentValue || '').replace(/"/g, '&quot;')}" maxlength="35">`;
        }

        cell.innerHTML = inputHtml;
        const input = cell.querySelector('input, select');
        if (!input) return;
        input.focus();
        if (input.select) input.select();

        let saved = false;
        const saveChange = async (skipSpell = false) => {
            if (saved) return;
            let newValue = input.value.trim();
            if (field === 'priority') {
                newValue = parseInt(newValue);
            }

            if (newValue === currentValue) {
                saved = true;
                cell.classList.remove('editing', 'cell-editing');
                cell.innerHTML = originalHTML;
                return;
            }

            if (!skipSpell && field === 'description' && window.SpellChecker && window.Operations?.promptSpellReview) {
                const analysis = SpellChecker.analyze(newValue);
                if (analysis.hasSuggestions) {
                    window.Operations.promptSpellReview(analysis, (finalText) => {
                        input.value = finalText;
                        saveChange(true);
                    });
                    return;
                }
            }

            saved = true;
            cell.classList.remove('editing', 'cell-editing');

            try {
                const item = await API.get(`/api/items/${itemId}`);
                item[field] = newValue;
                await API.put(`/api/items/${itemId}`, item);
                UI.showToast(`Item atualizado com sucesso!`, 'success');
                await this.load();
            } catch (err) {
                UI.showToast(`Erro ao atualizar item: ${err.message}`, 'error');
                cell.innerHTML = originalHTML;
            }
        };

        input.onblur = () => saveChange();
        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveChange();
            } else if (e.key === 'Escape') {
                saved = true;
                cell.classList.remove('editing', 'cell-editing');
                cell.innerHTML = originalHTML;
            }
        };
    },

    openPlanPicker(e, itemId, triggerEl) {
        if (e) e.stopPropagation();

        // Close existing dropdown
        this.closePlanPicker();

        // Create floating dropdown container
        const dropdown = document.createElement('div');
        dropdown.id = 'plan-picker-dropdown';
        dropdown.className = 'plan-picker-dropdown';

        // Position relative to trigger element
        const rect = triggerEl.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

        dropdown.style.top = `${rect.bottom + scrollTop + 4}px`;
        dropdown.style.left = `${Math.min(rect.left + scrollLeft, window.innerWidth - 360)}px`;

        dropdown.innerHTML = `
            <div class="plan-picker-search-bar">
                <input type="text" id="plan-picker-search-input" placeholder="🔍 Digitar código ou descrição..." autocomplete="off">
            </div>
            <div class="plan-picker-options" id="plan-picker-options-container"></div>
        `;

        document.body.appendChild(dropdown);

        const input = document.getElementById('plan-picker-search-input');
        const container = document.getElementById('plan-picker-options-container');

        // Focus search input immediately
        setTimeout(() => input && input.focus(), 30);

        // Render initial options list
        this.renderPlanPickerOptions(itemId, container, '');

        // Real-time filter on typing
        input.oninput = () => {
            this.renderPlanPickerOptions(itemId, container, input.value.trim());
        };

        // Keyboard events (Enter selects top option, Escape closes)
        input.onkeydown = (ev) => {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                const firstOpt = container.querySelector('.plan-picker-option');
                if (firstOpt) firstOpt.click();
            } else if (ev.key === 'Escape') {
                this.closePlanPicker();
            }
        };

        // Click outside listener
        setTimeout(() => {
            const handleOutsideClick = (event) => {
                const drop = document.getElementById('plan-picker-dropdown');
                if (drop && !drop.contains(event.target) && !triggerEl.contains(event.target)) {
                    this.closePlanPicker();
                    document.removeEventListener('click', handleOutsideClick);
                }
            };
            document.addEventListener('click', handleOutsideClick);
        }, 10);
    },

    renderPlanPickerOptions(itemId, container, filterText) {
        container.innerHTML = '';
        const query = filterText.toLowerCase();

        // Option: Sem Plano
        if (!query || 'sem plano'.includes(query)) {
            const noneDiv = document.createElement('div');
            noneDiv.className = 'plan-picker-option option-none';
            noneDiv.innerHTML = `
                <div class="opt-plan-code">Sem Plano</div>
                <div class="opt-plan-desc">(Remover associação com plano)</div>
            `;
            noneDiv.onclick = () => this.selectPlanForPicker(itemId, null);
            container.appendChild(noneDiv);
        }

        const filtered = (this.plansList || []).filter(p => {
            if (!query) return true;
            return (p.legacy_code && p.legacy_code.toLowerCase().includes(query)) ||
                   (p.description && p.description.toLowerCase().includes(query));
        });

        if (filtered.length === 0 && query && !('sem plano'.includes(query))) {
            container.innerHTML += `<div style="padding:12px; font-size:12px; color:var(--text-muted); text-align:center;">Nenhum plano encontrado</div>`;
            return;
        }

        filtered.forEach(p => {
            const div = document.createElement('div');
            div.className = 'plan-picker-option';
            div.innerHTML = `
                <div class="opt-plan-code">${p.legacy_code} — ${p.description}</div>
            `;
            div.onclick = () => this.selectPlanForPicker(itemId, p.id);
            container.appendChild(div);
        });
    },

    async selectPlanForPicker(itemId, newPlanId) {
        this.closePlanPicker();
        UI.showLoader("Atualizando plano do item...");
        try {
            const item = await API.get(`/api/items/${itemId}`);
            item.plan_id = newPlanId;
            await API.put(`/api/items/${itemId}`, item);
            UI.showToast("Plano do item atualizado com sucesso!", "success");
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao atualizar plano: ${err.message}`, "error");
        } finally {
            UI.hideLoader();
        }
    },

    closePlanPicker() {
        const existing = document.getElementById('plan-picker-dropdown');
        if (existing) existing.remove();
    },

};

window.Items = Items;
