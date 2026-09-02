/**
 * Plans Screen View & CRUD Controller
 */

const Plans = {
    filters: {
        search: '',
        cycle: '',
        status: 'ACTIVE',
        alert: '',
        row_color: '',
        limit: 100000,
        offset: 0,
        order_by: 'legacy_code',
        order_dir: 'ASC'
    },
    selectedIds: new Set(),
    rawPlansList: [],
    cycleCatalog: [],

    init() {
        try {
        if (window.RowTools) RowTools.initHeaderPin('plans-table', 'btn-toggle-plans-header-pin');
        // Toggle Filters body
        const toggle = document.getElementById('plans-filter-toggle');
        const body = document.getElementById('plans-filter-body');
        if (toggle) {
            const card = toggle.closest('.filter-card');
            toggle.onclick = () => card && card.classList.toggle('collapsed');
        }

        // Form character limit counter
        const descInput = document.getElementById('form-plan-desc');
        const descCount = document.getElementById('form-plan-desc-chars');
        const descWarn = document.getElementById('form-plan-desc-warning');

        if (descInput && descCount && descWarn) {
            descInput.oninput = () => {
                const len = descInput.value.trim().length;
                descCount.innerText = `${len} / 40 caracteres`;
                if (len > 40) {
                    descCount.style.color = 'var(--error-color)';
                    descWarn.classList.remove('hidden');
                } else {
                    descCount.style.color = 'var(--text-muted)';
                    descWarn.classList.add('hidden');
                }
            };
        }

        // Populate cycle fields upon selection
        const cycleSelect = document.getElementById('form-plan-cycle');
        if (cycleSelect) {
            cycleSelect.onchange = () => {
                const selectedVal = cycleSelect.value;
                if (!selectedVal) {
                    document.getElementById('form-plan-unit').value = '';
                    document.getElementById('form-plan-text').value = '';
                    document.getElementById('form-plan-horizon').value = '';
                    return;
                }
                const [cycle, unit] = selectedVal.split('|');
                const match = this.cycleCatalog.find(c => c.cycle == cycle && c.unit == unit);
                if (match) {
                    document.getElementById('form-plan-unit').value = match.unit;
                    document.getElementById('form-plan-text').value = match.cycle_text;
                    document.getElementById('form-plan-horizon').value = match.opening_horizon;
                }
            };
        }

        // Radio button code method selection
        const radioReady = document.getElementById('radio-code-ready');
        const radioBuild = document.getElementById('radio-code-build');
        const builderContainer = document.getElementById('plan-code-builder-container');
        const codeInput = document.getElementById('form-plan-code');

        const updateCodeMethodView = () => {
            if (radioBuild && radioBuild.checked) {
                if (builderContainer) builderContainer.classList.remove('hidden');
                if (codeInput) {
                    codeInput.readOnly = true;
                    codeInput.classList.add('bg-disabled');
                }
                this.buildCodeFromInputs();
            } else {
                if (builderContainer) builderContainer.classList.add('hidden');
                if (codeInput) {
                    codeInput.readOnly = false;
                    codeInput.classList.remove('bg-disabled');
                }
                const previewEl = document.getElementById('form-plan-code-preview');
                if (previewEl) previewEl.innerText = "";
            }
        };

        if (radioReady) radioReady.onchange = updateCodeMethodView;
        if (radioBuild) radioBuild.onchange = updateCodeMethodView;

        // Builder change listeners
        const buildIds = ['build-code-1', 'build-code-2', 'build-code-3', 'build-code-4', 'build-code-5', 'build-code-6', 'build-code-7'];
        buildIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                if (el.tagName === 'INPUT') {
                    el.oninput = () => this.buildCodeFromInputs();
                } else {
                    el.onchange = () => this.buildCodeFromInputs();
                }
            }
        });

        // Set table headers sort events
        const headers = document.querySelectorAll('#plans-table th.sortable');
        headers.forEach(th => {
            th.onclick = (e) => {
                if (e.target.closest('.col-filter-btn')) return;
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

        // Check all plans checkbox
        const checkAll = document.getElementById('check-all-plans');
        if (checkAll) {
            checkAll.onchange = () => {
                const checkboxes = document.querySelectorAll('.plan-row-checkbox');
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
        }

        // Trigger filters. The main search behaves like Excel's "contains"
        // filter and can be applied directly with Enter.
        const applyPlansFilters = () => {
            const searchInput = document.getElementById('filter-plans-search');
            this.filters.search = searchInput ? searchInput.value.trim() : '';
            this.filters.cycle = document.getElementById('filter-plans-cycle').value;
            this.filters.status = document.getElementById('filter-plans-status').value;
            this.filters.alert = document.getElementById('filter-plans-alert').value;
            this.filters.row_color = document.getElementById('filter-plans-row-color')?.value || '';

            this.filters.with_items = this.filters.alert === 'with_items' ? 'true' : '';
            this.filters.without_items = this.filters.alert === 'without_items' ? 'true' : '';
            this.filters.no_counter = this.filters.alert === 'no_counter' ? 'true' : '';
            this.filters.long_desc = this.filters.alert === 'long_desc' ? 'true' : '';

            this.filters.offset = 0;
            this.load();
        };

        const applyBtn = document.getElementById('btn-apply-plans-filters');
        if (applyBtn) applyBtn.onclick = applyPlansFilters;

        const plansSearchInput = document.getElementById('filter-plans-search');
        if (plansSearchInput) plansSearchInput.onkeydown = (event) => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            applyPlansFilters();
        };

        const clearBtn = document.getElementById('btn-clear-plans-filters');
        if (clearBtn) clearBtn.onclick = () => {
            document.getElementById('filter-plans-search').value = '';
            document.getElementById('filter-plans-cycle').value = '';
            document.getElementById('filter-plans-status').value = 'ACTIVE';
            document.getElementById('filter-plans-alert').value = '';
            document.getElementById('filter-plans-row-color').value = '';
            
            this.filters.search = '';
            this.filters.cycle = '';
            this.filters.status = 'ACTIVE';
            this.filters.alert = '';
            this.filters.row_color = '';
            this.filters.with_items = '';
            this.filters.without_items = '';
            this.filters.no_counter = '';
            this.filters.long_desc = '';
            
            this.filters.offset = 0;
            if (window.ColumnFilter) {
                window.ColumnFilter.clearAllFilters('plans-table');
            }
            this.load();
        };

        const pageSizeEl = document.getElementById('plans-page-size');
        if (pageSizeEl) pageSizeEl.onchange = (e) => {
            const val = e.target.value;
            this.filters.limit = val === 'all' ? 100000 : parseInt(val);
            this.filters.offset = 0;
            this.load();
        };

        // Create & Export buttons
        const createBtn = document.getElementById('btn-create-plan');
        if (createBtn) createBtn.onclick = () => this.openCreateModal();
        const saveBtn = document.getElementById('btn-save-plan');
        if (saveBtn) saveBtn.onclick = () => this.save();
        const saveAnotherBtn = document.getElementById('btn-save-plan-another');
        if (saveAnotherBtn) saveAnotherBtn.onclick = () => this.save(true);
        const exportBtn = document.getElementById('btn-export-plans');
        if (exportBtn) exportBtn.onclick = () => window.ImportWizard.exportScope('plans');

        // Plans Bulk buttons
        const bulkEditBtn = document.getElementById('btn-bulk-edit-plan-fields');
        if (bulkEditBtn) bulkEditBtn.onclick = () => this.openBulkEditFieldsModal();
        const bulkCloneBtn = document.getElementById('btn-bulk-clone-plans');
        if (bulkCloneBtn) bulkCloneBtn.onclick = () => this.bulkClone();
        const bulkActivateBtn = document.getElementById('btn-bulk-activate-plans');
        if (bulkActivateBtn) bulkActivateBtn.onclick = () => this.bulkUpdateStatus('ACTIVE');
        const bulkDeactivateBtn = document.getElementById('btn-bulk-deactivate-plans');
        if (bulkDeactivateBtn) bulkDeactivateBtn.onclick = () => this.bulkUpdateStatus('INACTIVE');
        const bulkDeleteBtn = document.getElementById('btn-bulk-delete-plans');
        if (bulkDeleteBtn) bulkDeleteBtn.onclick = () => this.bulkDelete();

        // Bulk edit modal enable checkboxes listeners
        ['cycle', 'unit', 'cycle-text', 'horizon', 'phase', 'status'].forEach(field => {
            const cb = document.getElementById(`bulk-plan-enable-${field}`);
            const input = document.getElementById(`bulk-plan-input-${field}`);
            if (cb && input) cb.onchange = () => { input.disabled = !cb.checked; };
        });
        const bulkEditConfirm = document.getElementById('btn-bulk-edit-plan-fields-confirm');
        if (bulkEditConfirm) bulkEditConfirm.onclick = () => this.bulkEditFieldsConfirm();

        // Modals close buttons
        document.querySelectorAll('[data-close="modal-plan"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-plan').classList.add('hidden');
        });
        document.querySelectorAll('[data-close="modal-bulk-edit-plan-fields"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-bulk-edit-plan-fields').classList.add('hidden');
        });

        } catch(e) {
            console.error('[Plans.init] Erro ao inicializar tela de planos:', e);
        }
    },

    toggleSelection(event, id) {
        if (event.target.checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
            const checkAll = document.getElementById('check-all-plans');
            if (checkAll) checkAll.checked = false;
        }
        this.updateBulkToolbar();
    },

    updateBulkToolbar() {
        const toolbar = document.getElementById('bulk-actions-toolbar-plans');
        const countSpan = document.getElementById('bulk-selection-count-plans');
        if (!toolbar || !countSpan) return;
        
        const count = this.selectedIds.size;
        if (count > 0) {
            countSpan.innerText = `${count} ${count === 1 ? 'plano selecionado' : 'planos selecionados'}`;
            toolbar.classList.remove('hidden');
        } else {
            toolbar.classList.add('hidden');
        }
    },

    openBulkEditFieldsModal() {
        const count = this.selectedIds.size;
        const textEl = document.getElementById('bulk-edit-plan-fields-count-text');
        if (textEl) textEl.innerText = `${count} ${count === 1 ? 'plano selecionado será alterado' : 'planos selecionados serão alterados'} em massa.`;
        
        ['cycle', 'unit', 'cycle-text', 'horizon', 'phase', 'status'].forEach(field => {
            const cb = document.getElementById(`bulk-plan-enable-${field}`);
            if (cb) cb.checked = false;
            const input = document.getElementById(`bulk-plan-input-${field}`);
            if (input) {
                if (input.tagName === 'SELECT') input.selectedIndex = 0;
                else input.value = '';
                input.disabled = true;
            }
        });

        const modal = document.getElementById('modal-bulk-edit-plan-fields');
        if (modal) modal.classList.remove('hidden');
    },

    async bulkEditFieldsConfirm() {
        const count = this.selectedIds.size;
        const updates = {};

        if (document.getElementById('bulk-plan-enable-cycle') && document.getElementById('bulk-plan-enable-cycle').checked) {
            const val = document.getElementById('bulk-plan-input-cycle').value.trim();
            if (val !== '') updates.cycle = parseInt(val);
        }
        if (document.getElementById('bulk-plan-enable-unit') && document.getElementById('bulk-plan-enable-unit').checked) {
            updates.unit = document.getElementById('bulk-plan-input-unit').value.trim();
        }
        if (document.getElementById('bulk-plan-enable-cycle-text') && document.getElementById('bulk-plan-enable-cycle-text').checked) {
            updates.cycle_text = document.getElementById('bulk-plan-input-cycle-text').value.trim();
        }
        if (document.getElementById('bulk-plan-enable-horizon') && document.getElementById('bulk-plan-enable-horizon').checked) {
            const val = document.getElementById('bulk-plan-input-horizon').value.trim();
            if (val !== '') updates.opening_horizon = parseFloat(val);
        }
        if (document.getElementById('bulk-plan-enable-phase') && document.getElementById('bulk-plan-enable-phase').checked) {
            const val = document.getElementById('bulk-plan-input-phase').value.trim();
            if (val !== '') {
                updates.phase = parseInt(val);
                updates.reference_counter = parseInt(val);
            }
        }
        if (document.getElementById('bulk-plan-enable-status') && document.getElementById('bulk-plan-enable-status').checked) {
            updates.status = document.getElementById('bulk-plan-input-status').value;
        }

        if (Object.keys(updates).length === 0) {
            UI.showToast("Marque e preencha pelo menos um campo para editar em massa.", "error");
            return;
        }

        const planIds = Array.from(this.selectedIds);
        window.App.confirm("Aplicar Alterações em Massa", `Tem certeza que deseja atualizar ${count} planos em massa?`, async () => {
            UI.showLoader("Atualizando planos em massa...");
            try {
                await API.post('/api/plans/bulk-update', {
                    project_id: window.App.currentProjectId,
                    plan_ids: planIds,
                    updates: updates
                });
                UI.showToast(`Campos atualizados com sucesso para ${count} planos!`);
                const modal = document.getElementById('modal-bulk-edit-plan-fields');
                if (modal) modal.classList.add('hidden');
                Plans.selectedIds.clear();
                await Plans.load();
            } catch (err) {
                UI.showToast(`Erro na atualização em massa de planos: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    bulkUpdateStatus(newStatus) {
        const planIds = Array.from(this.selectedIds);
        const actionLabel = newStatus === 'ACTIVE' ? 'ativar' : 'inativar';
        
        window.App.confirm("Alterar Status em Massa", `Deseja realmente ${actionLabel} os ${planIds.length} planos selecionados?`, async () => {
            UI.showLoader("Alterando status dos planos...");
            try {
                await API.post('/api/plans/bulk-update', {
                    project_id: window.App.currentProjectId,
                    plan_ids: planIds,
                    updates: { status: newStatus }
                });
                UI.showToast(`Status atualizado com sucesso para ${planIds.length} planos!`);
                Plans.selectedIds.clear();
                await Plans.load();
            } catch (err) {
                UI.showToast(`Erro ao alterar status: ${err.message}`, 'error');
            } finally {
                UI.hideLoader();
            }
        });
    },

    bulkDelete() {
        const planIds = Array.from(this.selectedIds);
        if (!planIds.length) return;
        window.App.confirm("Excluir Planos em Massa", `Tem certeza que deseja excluir em massa os <strong>${planIds.length} planos</strong> selecionados?<br><br><span style="color:var(--text-muted);font-size:12px;">Os itens de manutenção vinculados ficarão sem plano associado.</span>`, async () => {
            UI.showLoader("Excluindo planos em massa...");
            let deleted = 0;
            try {
                for (let id of planIds) {
                    await API.delete(`/api/plans/${id}`, { item_action: 'unbind' });
                    deleted++;
                }
                UI.showToast(`${deleted} plano(s) excluído(s) com sucesso!`, 'success');
                Plans.selectedIds.clear();
                this.updateBulkToolbar();
                await Plans.load();
            } catch (err) {
                UI.showToast(`${deleted} de ${planIds.length} planos excluídos. Erro: ${err.message}`, 'error', 5000);
                Plans.selectedIds.clear();
                this.updateBulkToolbar();
                await Plans.load();
            } finally {
                UI.hideLoader();
            }
        });
    },

    async load(options = {}) {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        // Check if there is a preset filter from Dashboard
        if (window.App.plansFilterPreset) {
            const preset = window.App.plansFilterPreset;
            window.App.plansFilterPreset = null; // Clear
            
            this.filters.alert = preset;
            this.filters.no_counter = preset === 'no_counter' ? 'true' : '';
            this.filters.long_desc = preset === 'long_desc' ? 'true' : '';
            this.filters.without_items = preset === 'without_items' ? 'true' : '';
            this.filters.with_items = preset === 'with_items' ? 'true' : '';
            
            const alertSelect = document.getElementById('filter-plans-alert');
            if (alertSelect) alertSelect.value = preset;
            
            // Expand filters card so user sees it is applied
            const filterCard = document.querySelector('#section-plans .filter-card');
            if (filterCard) filterCard.classList.remove('collapsed');
        }

        const tbody = document.getElementById('plans-table-body');
        const isSilent = options.silent || (tbody && tbody.children.length > 0 && !tbody.querySelector('.empty-table-cell'));
        if (!isSilent) {
            UI.showLoader("Carregando catálogo de planos...");
        }

        const runTask = async () => {
            try {
                // Load cycles catalog
                await this.loadCycleCatalog(projId);

                // Fetch plans list
                const queryParams = {
                    project_id: projId,
                    search: this.filters.search,
                    cycle: this.filters.cycle,
                    status: this.filters.status,
                    row_color: this.filters.row_color,
                    with_items: this.filters.with_items,
                    without_items: this.filters.without_items,
                    no_counter: this.filters.no_counter,
                    long_desc: this.filters.long_desc,
                    limit: this.filters.limit,
                    offset: this.filters.offset,
                    order_by: this.filters.order_by,
                    order_dir: this.filters.order_dir
                };

                const data = await API.get('/api/plans', queryParams);
                this.rawPlansList = data.plans || [];

                // Apply client-side column filters if present
                let displayPlans = this.rawPlansList;
                if (window.ColumnFilter) {
                    displayPlans = window.ColumnFilter.applyFiltersToDataset('plans-table', this.rawPlansList);
                }

                if (this.filters.alert === 'all_issues' || this.filters.alert === 'error' || this.filters.alert === 'warning') {
                    displayPlans = displayPlans.filter(plan => {
                        const issues = [];
                        if (plan.validation_issues && Array.isArray(plan.validation_issues)) issues.push(...plan.validation_issues);
                        if (!plan.reference_counter && plan.reference_counter !== 0) issues.push({ severity: 'WARNING', message: 'Sem parada inicial' });
                        if (plan.item_count === 0) issues.push({ severity: 'WARNING', message: 'Sem itens vinculados' });
                        if (plan.character_count > 35) issues.push({ severity: 'WARNING', message: 'Descrição extensa' });

                        const isError = issues.some(i => i.severity === 'ERROR');
                        const isWarning = issues.length > 0 && !isError;
                        if (this.filters.alert === 'all_issues') return issues.length > 0;
                        if (this.filters.alert === 'error') return isError;
                        if (this.filters.alert === 'warning') return isWarning;
                        return true;
                    });
                }

                this.renderTable(displayPlans, displayPlans.length !== this.rawPlansList.length ? displayPlans.length : data.total);

                // Initialize or update column filters on table headers
                if (window.ColumnFilter) {
                    window.ColumnFilter.init('plans-table', () => this.rawPlansList, (sortCol, sortDir, activeFilters) => {
                        if (sortCol && sortDir) {
                            this.filters.order_by = sortCol;
                            this.filters.order_dir = sortDir;
                        }
                        this.load();
                    });
                }

            } catch (err) {
                UI.showToast(`Erro ao carregar planos: ${err.message}`, 'error');
            } finally {
                if (!isSilent) UI.hideLoader();
            }
        };

        if (window.App && typeof App.preserveScroll === 'function') {
            return App.preserveScroll(tbody || 'plans-table-body', runTask);
        } else {
            return runTask();
        }
    },

    async loadCycleCatalog(projId) {
        try {
            const cycles = await API.get('/api/cycles', { project_id: projId });
            this.cycleCatalog = cycles || [];
            
            const formCycleSelect = document.getElementById('form-plan-cycle');
            const filterCycleSelect = document.getElementById('filter-plans-cycle');

            const prevFilterVal = filterCycleSelect ? filterCycleSelect.value : '';
            const prevFormVal = formCycleSelect ? formCycleSelect.value : '';

            if (formCycleSelect) {
                formCycleSelect.innerHTML = '<option value="">Selecione o ciclo cadastrado...</option>';
                this.cycleCatalog.forEach(c => {
                    formCycleSelect.innerHTML += `<option value="${c.cycle}|${c.unit}">${c.cycle} ${c.unit} (${c.cycle_text} — ${c.opening_horizon}h)</option>`;
                });
                formCycleSelect.value = prevFormVal;
            }

            if (filterCycleSelect) {
                filterCycleSelect.innerHTML = '<option value="">Todos</option>';
                this.cycleCatalog.forEach(c => {
                    filterCycleSelect.innerHTML += `<option value="${c.cycle}">${c.cycle} ${c.unit} (${c.cycle_text})</option>`;
                });
                filterCycleSelect.value = prevFilterVal;
            }

        } catch (e) {
            console.error("Erro ao carregar catálogo de ciclos:", e);
        }
    },

    renderTable(plans, total) {
        const tbody = document.getElementById('plans-table-body');
        tbody.innerHTML = '';

        document.getElementById('plans-count-display').innerText = `${plans.length === total ? total : plans.length + ' de ' + total} planos encontrados`;

        if (plans.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="13" class="empty-table-cell">Nenhum plano de manutenção encontrado.</td>
                </tr>
            `;
            this.renderPagination(total);
            return;
        }

        const checkAll = document.getElementById('check-all-plans');
        if (checkAll) {
            checkAll.checked = plans.length > 0 && plans.every(p => this.selectedIds.has(p.id));
        }

        plans.forEach(p => {
            const issues = [];
            if (p.character_count > 40) issues.push({ severity: 'WARNING', message: `Descrição do plano extensa (${p.character_count} caract. > 40).` });
            if (p.items_count === 0) issues.push({ severity: 'WARNING', message: 'Plano sem nenhum item de manutenção associado.' });
            if (!p.phase || p.phase <= 0) issues.push({ severity: 'WARNING', message: 'Plano sem parada de início / contador de referência configurado.' });
            if (p.validation_issues_json) {
                try {
                    const parsed = typeof p.validation_issues_json === 'string' ? JSON.parse(p.validation_issues_json) : p.validation_issues_json;
                    if (Array.isArray(parsed)) issues.push(...parsed);
                } catch(e) {}
            }
            if (p.validation_issues && Array.isArray(p.validation_issues)) {
                issues.push(...p.validation_issues);
            }
            const issueMessages = [...new Set(issues.map(i => i.message))];
            const isError = issues.some(i => i.severity === 'ERROR');
            const isWarning = issues.length > 0 && !isError;
            
            let rowClass = '';
            if (isError) rowClass = 'table-alert-red';
            else if (isWarning) rowClass = 'table-alert-yellow';

            const esc = str => (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            const issuesText = issueMessages.map(m => `• ${m}`).join('\n');
            const indicator = issues.length > 0 ? `
                <span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" style="cursor:pointer;" onclick="event.stopPropagation(); App.openIssueFixModal('plan', ${p.id})" title="Clique para abrir o diagnóstico e aplicar a correção automática: ${esc(issuesText)}">
                    ${isError ? '⛔' : '⚠️'}
                </span>
            ` : '';

            const statusBadge = p.status === 'ACTIVE'
                ? `<span class="badge badge-active">Ativo</span>`
                : `<span class="badge badge-inactive">Inativo</span>`;

            const nextStop = p.phase > 0 
                ? `P${p.phase}, P${p.phase + p.cycle}, P${p.phase + (2 * p.cycle)}...`
                : '<span class="txt-danger">Pendente</span>';

            const safeCode = (p.legacy_code || '').replace(/'/g, "\\'");
            const safeDesc = (p.description || '').replace(/'/g, "\\'");
            const safeUnit = (p.unit || '').replace(/'/g, "\\'");

            // Check if description has pattern like 6P1, 2P2
            let patternBadge = '';
            const match = (p.description || '').match(/(?:^|[\s\-_.,/])([0-9]+)\s*[Pp]\s*[-_.]?\s*([0-9]+)/);
            if (match) {
                const patCycle = parseInt(match[1]);
                const patStart = parseInt(match[2]);
                if (patCycle !== p.cycle || (p.phase && patStart !== p.phase)) {
                    patternBadge = `<span class="badge-divergence" title="Padrão '${match[1]}P${match[2]}' na descrição indica Ciclo ${patCycle} e Início ${patStart}">⚠️ ${match[1]}P${match[2]}</span>`;
                } else {
                    patternBadge = `<span class="badge-auto-fill" title="Identificado padrão '${match[1]}P${match[2]}'">✓ ${match[1]}P${match[2]}</span>`;
                }
            }

            const checked = this.selectedIds.has(p.id) ? 'checked' : '';

            const tr = document.createElement('tr');
            tr.className = rowClass;
            if (p.row_color) tr.classList.add('item-row-marked', `item-row-color-${p.row_color}`);
            if (issues.length) tr.title = issuesText;
            tr.innerHTML = `
                <td class="text-center" style="display:flex; align-items:center; justify-content:center; gap:2px; height:100%; padding:8px 4px;">
                    ${indicator}<button class="row-color-brush" title="Marcar linha" onclick="RowTools.open(event,'plans',${p.id},'()=>Plans.load()')">🖌️</button><input type="checkbox" class="plan-row-checkbox" data-id="${p.id}" ${checked} onchange="Plans.toggleSelection(event, ${p.id})">
                </td>
                <td class="editable-cell" title="Clique duas vezes para editar" ondblclick="Plans.makeCellEditable(this, ${p.id}, 'legacy_code', '${safeCode}')"><strong>${p.legacy_code}</strong></td>
                <td class="editable-cell" title="${p.description} (Clique 2x para editar)" ondblclick="Plans.makeCellEditable(this, ${p.id}, 'description', '${safeDesc}')">
                    ${p.description} ${patternBadge}
                </td>
                <td>${p.character_count}</td>
                <td class="editable-cell" title="Clique duas vezes para editar" ondblclick="Plans.makeCellEditable(this, ${p.id}, 'cycle', ${p.cycle})">${p.cycle}</td>
                <td class="editable-cell" title="Clique duas vezes para editar" ondblclick="Plans.makeCellEditable(this, ${p.id}, 'unit', '${safeUnit}')">${p.unit}</td>
                <td class="editable-cell" title="Clique duas vezes para editar" ondblclick="Plans.makeCellEditable(this, ${p.id}, 'start_stop', ${p.phase || 'null'})">
                    ${p.phase > 0 ? `<strong style="color: #0284C7;">P${p.phase}</strong>` : '<span class="txt-danger">Pendente</span>'}
                </td>
                <td>${nextStop}</td>
                <td>
                    <a href="#items" onclick="Plans.viewLinkedItems(${p.id})" style="font-weight:700; text-decoration:underline;">
                        ${p.items_count} itens
                    </a>
                </td>
                <td>${p.total_hh.toFixed(1).replace('.', ',')}</td>
                <td>${statusBadge}</td>
                <td>
                    <div class="actions-cell">
                        <button class="btn btn-xs btn-outline" title="Editar plano pelo formulário" onclick="Plans.openEditModal(${p.id})">Editar</button>
                        <button class="btn btn-xs btn-outline" title="Clonar este plano com o prefixo [copia]" onclick="Plans.clone(${p.id})">Clonar</button>
                        <button class="btn btn-xs btn-danger" title="Excluir plano" onclick="Plans.delete(${p.id})">Excluir</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

        this.renderPagination(total);
        this.updateHeaderSortClasses();
        this.updateBulkToolbar();
    },

    renderPagination(total) {
        const container = document.getElementById('plans-pagination-footer');
        if (!container) return;
        container.innerHTML = '';
        
        const limit = this.filters.limit;
        if (limit >= total) return; 

        const totalPages = Math.ceil(total / limit);
        const currentPage = Math.floor(this.filters.offset / limit) + 1;

        const prevBtn = document.createElement('button');
        prevBtn.className = 'btn-paginate';
        prevBtn.innerText = '«';
        prevBtn.disabled = currentPage === 1;
        prevBtn.onclick = () => {
            this.filters.offset -= limit;
            this.load();
        };
        container.appendChild(prevBtn);

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
        const headers = document.querySelectorAll('#plans-table th.sortable');
        headers.forEach(th => {
            const col = th.getAttribute('data-col');
            const iconSpan = th.querySelector('.sort-icon');
            if (iconSpan) {
                if (col === this.filters.order_by) {
                    iconSpan.innerText = this.filters.order_dir === 'ASC' ? '▲' : '▼';
                    th.style.color = 'var(--primary-dark)';
                } else {
                    iconSpan.innerText = '';
                    th.style.color = '';
                }
            }
        });
    },

    buildCodeFromInputs() {
        const c1 = document.getElementById('build-code-1') ? document.getElementById('build-code-1').value : 'U';
        const c2 = document.getElementById('build-code-2') ? document.getElementById('build-code-2').value : 'R';
        const c3 = document.getElementById('build-code-3') ? document.getElementById('build-code-3').value : 'R';
        const c4 = ((document.getElementById('build-code-4') ? document.getElementById('build-code-4').value : '') || '').toUpperCase().padEnd(3, '_');
        const c5 = ((document.getElementById('build-code-5') ? document.getElementById('build-code-5').value : '') || '').toUpperCase().padEnd(3, '_');
        const c6 = document.getElementById('build-code-6') ? document.getElementById('build-code-6').value : 'M';
        const c7 = ((document.getElementById('build-code-7') ? document.getElementById('build-code-7').value : '') || '').toUpperCase().padEnd(2, '_');

        const generated = `${c1}${c2}${c3}${c4}${c5}${c6}${c7}`;
        const codeInput = document.getElementById('form-plan-code');
        if (codeInput) {
            codeInput.value = generated;
        }
        
        const previewEl = document.getElementById('form-plan-code-preview');
        if (previewEl) {
            previewEl.innerText = `Preview: ${generated}`;
        }
    },

    onPlanCreatedCallback: null,

    openCreateModal(prefillData = null) {
        document.getElementById('modal-plan-title').innerText = "Novo Plano PM13";
        document.getElementById('form-plan-id').value = "";
        document.getElementById('form-plan-code').value = (prefillData && prefillData.code) || "";
        document.getElementById('form-plan-desc').value = (prefillData && prefillData.desc) || "";
        document.getElementById('form-plan-cycle').value = (prefillData && prefillData.cycle) || "";
        document.getElementById('form-plan-unit').value = (prefillData && prefillData.unit) || "";
        document.getElementById('form-plan-text').value = (prefillData && prefillData.cycle_text) || "";
        document.getElementById('form-plan-horizon').value = (prefillData && prefillData.opening_horizon) || "";
        document.getElementById('form-plan-counter').value = (prefillData && prefillData.counter !== undefined) ? prefillData.counter : "";
        document.getElementById('form-plan-status').value = (prefillData && prefillData.status) || "ACTIVE";
        document.getElementById('form-plan-notes').value = "";

        const descLen = (prefillData && prefillData.desc) ? prefillData.desc.length : 0;
        document.getElementById('form-plan-desc-chars').innerText = `${descLen} / 40 caracteres`;
        document.getElementById('form-plan-desc-chars').style.color = '';
        document.getElementById('form-plan-desc-warning').classList.add('hidden');
        document.getElementById('form-plan-code-preview').innerText = "";

        const radioReady = document.getElementById('radio-code-ready');
        if (radioReady) {
            radioReady.checked = true;
            const event = document.createEvent('HTMLEvents');
            event.initEvent('change', true, false);
            radioReady.dispatchEvent(event);
        }

        if (prefillData && prefillData.code) {
            const codeInput = document.getElementById('form-plan-code');
            if (codeInput) {
                codeInput.value = prefillData.code;
                codeInput.readOnly = false;
                codeInput.classList.remove('bg-disabled');
            }
        }

        const b1 = document.getElementById('build-code-1');
        const b2 = document.getElementById('build-code-2');
        const b3 = document.getElementById('build-code-3');
        const b4 = document.getElementById('build-code-4');
        const b5 = document.getElementById('build-code-5');
        const b6 = document.getElementById('build-code-6');
        const b7 = document.getElementById('build-code-7');
        if (b1) b1.value = "U";
        if (b2) b2.value = "R";
        if (b3) b3.value = "R";
        if (b4) b4.value = "";
        if (b5) b5.value = "";
        if (b6) b6.value = "M";
        if (b7) b7.value = "";

        document.getElementById('btn-save-plan-another').classList.remove('hidden');
        document.getElementById('modal-plan').classList.remove('hidden');
    },

    async openEditModal(planId) {
        UI.showLoader("Carregando plano...");
        try {
            const plan = await API.get(`/api/plans/${planId}`);
            
            document.getElementById('modal-plan-title').innerText = "Editar Plano PM13";
            document.getElementById('form-plan-id').value = plan.id;
            document.getElementById('form-plan-code').value = plan.legacy_code;
            document.getElementById('form-plan-desc').value = plan.description;
            
            // Prefill cycle select
            const optionVal = `${plan.cycle}|${plan.unit}`;
            document.getElementById('form-plan-cycle').value = optionVal;
            document.getElementById('form-plan-unit').value = plan.unit;
            document.getElementById('form-plan-text').value = plan.cycle_text;
            document.getElementById('form-plan-horizon').value = plan.opening_horizon;
            
            document.getElementById('form-plan-counter').value = plan.phase || '';
            document.getElementById('form-plan-status').value = plan.status;
            document.getElementById('form-plan-notes').value = plan.notes || '';

            // Reset code builder to ready mode when editing existing
            const radioReady = document.getElementById('radio-code-ready');
            if (radioReady) {
                radioReady.checked = true;
                const event = document.createEvent('HTMLEvents');
                event.initEvent('change', true, false);
                radioReady.dispatchEvent(event);
            }

            const len = plan.description.length;
            document.getElementById('form-plan-desc-chars').innerText = `${len} / 40 caracteres`;
            if (len > 40) {
                document.getElementById('form-plan-desc-chars').style.color = 'var(--error-color)';
                document.getElementById('form-plan-desc-warning').classList.remove('hidden');
            } else {
                document.getElementById('form-plan-desc-chars').style.color = 'var(--text-muted)';
                document.getElementById('form-plan-desc-warning').classList.add('hidden');
            }

            document.getElementById('btn-save-plan-another').classList.add('hidden');
            document.getElementById('modal-plan').classList.remove('hidden');
        } catch (err) {
            UI.showToast(`Erro ao carregar plano: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async save(createAnother = false) {
        const id = document.getElementById('form-plan-id').value;
        const code = document.getElementById('form-plan-code').value.trim();
        const desc = document.getElementById('form-plan-desc').value.trim();
        const cycleVal = document.getElementById('form-plan-cycle').value;
        const unit = document.getElementById('form-plan-unit').value.trim();
        const text = document.getElementById('form-plan-text').value.trim();
        const horiz = document.getElementById('form-plan-horizon').value;
        const counter = document.getElementById('form-plan-counter').value;
        const status = document.getElementById('form-plan-status').value;
        const notes = document.getElementById('form-plan-notes').value.trim();

        if (!code) {
            UI.showToast("O código do plano é obrigatório.", "error");
            return;
        }
        if (!desc) {
            UI.showToast("A descrição do plano é obrigatória.", "error");
            return;
        }
        if (!cycleVal || !unit) {
            UI.showToast("Selecione o ciclo e unidade.", "error");
            return;
        }

        const [cycle] = cycleVal.split('|');

        const payload = {
            project_id: window.App.currentProjectId,
            legacy_code: code,
            description: desc,
            cycle: parseInt(cycle),
            unit: unit,
            cycle_text: text,
            opening_horizon: parseFloat(horiz) || 0.0,
            start_stop: counter !== '' ? parseInt(counter) : null,
            status: status,
            notes: notes
        };

        UI.showLoader("Salvando plano...");
        try {
            let savedPlanId = id;
            if (id) {
                await API.put(`/api/plans/${id}`, payload);
                UI.showToast("Plano atualizado com sucesso!");
            } else {
                const res = await API.post('/api/plans', payload);
                savedPlanId = res.id;
                UI.showToast("Plano criado com sucesso!");
            }

            if (this.onPlanCreatedCallback) {
                const cb = this.onPlanCreatedCallback;
                this.onPlanCreatedCallback = null;
                await cb({ id: savedPlanId, ...payload });
            }

            if (createAnother && !id) {
                this.openCreateModal();
            } else {
                document.getElementById('modal-plan').classList.add('hidden');
            }

            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao salvar plano: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async delete(planId) {
        try {
            UI.showLoader("Verificando plano...");
            const plan = await API.get(`/api/plans/${planId}`);
            
            const linkedItems = await API.get('/api/items', { project_id: window.App.currentProjectId, plan_id: planId, limit: 1 });
            const itemsCount = linkedItems.total;

            UI.hideLoader();

            if (itemsCount === 0) {
                window.App.confirm("Excluir Plano", `Deseja realmente excluir o plano "${plan.legacy_code}"?`, async () => {
                    UI.showLoader("Excluindo plano...");
                    try {
                        await API.delete(`/api/plans/${planId}`, { item_action: 'unbind' });
                        UI.showToast("Plano excluído com sucesso!");
                        await Plans.load();
                    } catch (err) {
                        UI.showToast(`Erro ao excluir plano: ${err.message}`, 'error');
                    } finally {
                        UI.hideLoader();
                    }
                });
            } else {
                const otherPlans = await API.get('/api/plans', { project_id: window.App.currentProjectId, limit: 1000 });
                const filteredOtherPlans = otherPlans.plans.filter(p => p.id !== planId && p.status === 'ACTIVE');

                let optionsHtml = '';
                filteredOtherPlans.forEach(p => {
                    optionsHtml += `<option value="${p.id}">${p.legacy_code} — ${p.description}</option>`;
                });

                const confirmExtra = document.getElementById('confirm-extra-content');
                confirmExtra.innerHTML = `
                    <div style="background-color: #FCE8E8; padding: 15px; border-radius: var(--radius-sm); border: 1px solid #F8B4B4; margin-bottom:15px;">
                        <p style="color:var(--error-color); font-weight:700;">Atenção: Existem ${itemsCount} itens de manutenção vinculados a este plano!</p>
                    </div>
                    <div class="form-group">
                        <label>Escolha o destino para esses itens:</label>
                        <div style="margin-top:8px;">
                            <label style="display:block; margin-bottom:6px; text-transform:none; font-weight:500;">
                                <input type="radio" name="plan-del-action" value="unbind" checked> Deixar os itens sem plano (desvincular)
                            </label>
                            <label style="display:block; text-transform:none; font-weight:500;">
                                <input type="radio" name="plan-del-action" value="transfer"> Transferir os itens para outro plano
                            </label>
                        </div>
                    </div>
                    <div class="form-group mt-10 hidden" id="plan-del-transfer-form">
                        <label>Plano de Destino</label>
                        <select id="plan-del-target-select">
                            <option value="">Selecione o plano...</option>
                            ${optionsHtml}
                        </select>
                    </div>
                `;

                confirmExtra.querySelectorAll('input[name="plan-del-action"]').forEach(r => {
                    r.onchange = () => {
                        const selectForm = document.getElementById('plan-del-transfer-form');
                        if (r.value === 'transfer') {
                            selectForm.classList.remove('hidden');
                        } else {
                            selectForm.classList.add('hidden');
                        }
                    };
                });

                window.App.confirm("Excluir Plano com Itens Vinculados", `Deseja realmente excluir o plano "${plan.legacy_code}"? Escolha a ação para os itens abaixo.`, async () => {
                    const action = confirmExtra.querySelector('input[name="plan-del-action"]:checked').value;
                    const targetPlanId = document.getElementById('plan-del-target-select').value;

                    if (action === 'transfer' && !targetPlanId) {
                        UI.showToast("Selecione um plano de destino para transferir os itens.", "error");
                        return false;
                    }

                    UI.showLoader("Excluindo plano...");
                    try {
                        const params = { item_action: action };
                        if (action === 'transfer') {
                            params.target_plan_id = targetPlanId;
                        }

                        await API.delete(`/api/plans/${planId}`, params);
                        UI.showToast("Plano excluído com sucesso!");
                        confirmExtra.innerHTML = '';
                        await Plans.load();
                        return true;
                    } catch (err) {
                        UI.showToast(`Erro ao excluir plano: ${err.message}`, 'error');
                        return false;
                    } finally {
                        UI.hideLoader();
                    }
                });
            }
        } catch (err) {
            UI.hideLoader();
            UI.showToast(`Erro ao obter detalhes do plano: ${err.message}`, 'error');
        }
    },

    viewLinkedItems(planId) {
        window.App.itemsFilterPreset = `plan_${planId}`;
    },

    export() {
        const projId = window.App.currentProjectId;
        if (!projId) return;
        
        const params = {
            type: 'plans',
            project_id: projId,
            search: this.filters.search,
            cycle: this.filters.cycle,
            status: this.filters.status,
            with_items: this.filters.with_items,
            without_items: this.filters.without_items,
            no_counter: this.filters.no_counter,
            long_desc: this.filters.long_desc
        };
        
        const query = Object.keys(params)
            .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
            .join('&');
            
        window.open(`/api/export?${query}`, '_blank');
    },

    async clone(id) {
        try {
            UI.showLoader("Clonando plano...");
            const plan = await API.get(`/api/plans/${id}`);
            const newCode = `[copia] ${plan.legacy_code || ''}`.trim();
            const newDesc = `[copia] ${plan.description || ''}`.trim();
            const payload = {
                project_id: plan.project_id,
                legacy_code: newCode,
                description: newDesc,
                cycle: plan.cycle,
                unit: plan.unit,
                cycle_text: plan.cycle_text,
                opening_horizon: plan.opening_horizon,
                start_stop: plan.phase || null,
                notes: plan.notes
            };
            await API.post('/api/plans', payload);
            UI.showToast(`Plano "${newCode}" clonado com sucesso!`, 'success');
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao clonar plano: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async bulkClone() {
        const ids = Array.from(this.selectedIds);
        if (!ids.length || !confirm(`Clonar ${ids.length} ${ids.length === 1 ? 'plano selecionado' : 'planos selecionados'}?`)) return;
        let cloned = 0;
        UI.showLoader('Clonando planos selecionados...');
        try {
            for (const id of ids) {
                const plan = await API.get(`/api/plans/${id}`);
                await API.post('/api/plans', {
                    project_id: plan.project_id,
                    legacy_code: `[copia] ${plan.legacy_code || ''}`.trim(),
                    description: `[copia] ${plan.description || ''}`.trim(),
                    cycle: plan.cycle,
                    unit: plan.unit,
                    cycle_text: plan.cycle_text,
                    opening_horizon: plan.opening_horizon,
                    start_stop: plan.phase || null,
                    notes: plan.notes
                });
                cloned++;
            }
            this.selectedIds.clear();
            this.updateBulkToolbar();
            UI.showToast(`${cloned} ${cloned === 1 ? 'plano clonado' : 'planos clonados'} com sucesso.`, 'success');
            await this.load();
        } catch (err) {
            UI.showToast(`${cloned} de ${ids.length} planos clonados. Erro: ${err.message}`, 'error', 5000);
            await this.load();
        } finally { UI.hideLoader(); }
    },

    makeCellEditable(cell, planId, field, currentValue) {
        if (cell.classList.contains('editing')) return;
        cell.classList.add('editing', 'cell-editing');
        const originalHTML = cell.innerHTML;

        let inputHtml = '';
        if (field === 'unit') {
            const units = ['PRD', 'DIA', 'SEMANA', 'MES', 'ANO'];
            inputHtml = `<select class="table-inline-input">` + 
                units.map(u => `<option value="${u}" ${u === currentValue ? 'selected' : ''}>${u}</option>`).join('') +
                `</select>`;
        } else if (field === 'cycle' || field === 'start_stop') {
            inputHtml = `<input type="number" class="table-inline-input" value="${currentValue !== null && currentValue !== undefined ? currentValue : ''}">`;
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
            if (field === 'cycle' || field === 'start_stop') {
                newValue = newValue === '' ? null : parseInt(newValue);
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
                const plan = await API.get(`/api/plans/${planId}`);
                plan[field] = newValue;
                if (field === 'cycle' && newValue !== null) {
                    const match = this.cycleCatalog.find(c => c.cycle == newValue && c.unit == plan.unit);
                    if (match) {
                        plan.cycle_text = match.cycle_text;
                        plan.opening_horizon = match.opening_horizon;
                    }
                }
                try {
                    await API.put(`/api/plans/${planId}`, plan);
                } catch (requestError) {
                    if (/failed to fetch/i.test(requestError.message || '')) {
                        await new Promise(resolve => setTimeout(resolve, 300));
                        await API.put(`/api/plans/${planId}`, plan);
                    } else {
                        throw requestError;
                    }
                }
                UI.showToast(`Plano atualizado com sucesso!`, 'success');
                await this.load();
            } catch (err) {
                UI.showToast(`Erro ao atualizar plano: ${err.message}`, 'error');
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
    }
};

window.Plans = Plans;

/**
 * Calculates next stop counter occurrence in front-end
 */
function calculations_occurrence_display(reference_counter, cycle, current_counter) {
    if (reference_counter === null || !cycle) return '-';
    
    const S_next = calculations_next_occurrence(reference_counter, cycle, current_counter);
    return `Parada ${S_next - current_counter} (Cont. ${S_next})`;
}

function calculations_next_occurrence(reference_counter, cycle, current_counter) {
    if (reference_counter >= current_counter) {
        return reference_counter;
    }
    const rem = (current_counter - reference_counter) % cycle;
    if (rem === 0) {
        return current_counter;
    } else {
        return current_counter + (cycle - rem);
    }
}
