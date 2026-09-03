/**
 * operations.js - Full Management of SAP Maintenance Operations & Long Texts
 * Includes: working buttons, column filters (ColumnFilter), general search filters,
 * and proper modal open/close (no UI.openModal dependency).
 */

const Operations = {
    // --- Operations State ---
    opFilters: {
        search: '',
        work_center: '',
        item_id: '',
        limit: 100000,
        offset: 0,
        order_by: 'legacy_identifier',
        order_dir: 'ASC'
        ,row_color: ''
    },
    currentOperations: [],
    selectedOperationIds: new Set(),

    // --- Long Texts State ---
    ltFilters: {
        search: '',
        operation_id: '',
        limit: 100000,
        offset: 0,
        order_by: 'legacy_identifier',
        order_dir: 'ASC'
        ,row_color: ''
    },
    currentLongTexts: [],
    selectedLongTextIds: new Set(),
    itemDescriptions: new Map(),
    modalItems: [],
    modalOperations: [],
    sapOrder: null,
    sapItemId: null,

    async loadItemDescriptions(projectId) {
        try {
            const response = await API.get('/api/items', { project_id: projectId, limit: 100000, offset: 0 });
            this.itemDescriptions = new Map((response.items || []).map(item => [
                String(item.legacy_identifier), item.description || ''
            ]));
        } catch (_) {
            this.itemDescriptions = new Map();
        }
    },

    // ==========================================
    // MODAL HELPERS (no dependency on UI.openModal)
    // ==========================================

    _openModal(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('hidden');
    },

    _closeModal(id) {
        const el = document.getElementById(id);
        if (el) el.classList.add('hidden');
    },

    esc(v) {
        const d = document.createElement('div');
        d.textContent = v ?? '';
        return d.innerHTML;
    },

    toggleCustomDropdown(dropdownId, searchInputId) {
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;
        const willOpen = !dropdown.classList.contains('open');
        document.querySelectorAll('.custom-select-dropdown.open').forEach(el => {
            if (el !== dropdown) el.classList.remove('open');
        });
        document.querySelectorAll('.custom-select-trigger.open').forEach(el => el.classList.remove('open'));
        dropdown.classList.toggle('open', willOpen);
        dropdown.previousElementSibling?.classList.toggle('open', willOpen);
        if (willOpen) window.setTimeout(() => document.getElementById(searchInputId)?.focus(), 0);
    },

    closeCustomDropdown(dropdownId) {
        const dropdown = document.getElementById(dropdownId);
        dropdown?.classList.remove('open');
        dropdown?.previousElementSibling?.classList.remove('open');
    },

    closeLongTextModal() {
        this.refreshSapOrderAfterLtSave = null;
        this._closeModal('modal-long-text');
    },

    // ==========================================
    // INIT
    // ==========================================

    init() {
        try {
            if (window.LongTextEditor) LongTextEditor.init();
            if (window.RowTools) {
                RowTools.initHeaderPin('operations-table', 'btn-toggle-operations-header-pin');
                RowTools.initHeaderPin('long-texts-table', 'btn-toggle-long-texts-header-pin');
            }
            // These management tables use responsive percentage widths so they fit at 100% zoom.
            // Bind operations search
            const opSearchInput = document.getElementById('filter-ops-search');
            if (opSearchInput) {
                opSearchInput.onkeydown = (e) => { if (e.key === 'Enter') this.applyOpFilters(); };
            }
            const opApplyBtn = document.getElementById('btn-apply-ops-filters');
            if (opApplyBtn) opApplyBtn.onclick = () => this.applyOpFilters();
            const opClearBtn = document.getElementById('btn-clear-ops-filters');
            if (opClearBtn) opClearBtn.onclick = () => this.clearOpFilters();

            // Bind long texts search
            const ltSearchInput = document.getElementById('filter-lt-search');
            if (ltSearchInput) {
                ltSearchInput.onkeydown = (e) => { if (e.key === 'Enter') this.applyLtFilters(); };
            }
            const ltApplyBtn = document.getElementById('btn-apply-lt-filters');
            if (ltApplyBtn) ltApplyBtn.onclick = () => this.applyLtFilters();
            const ltClearBtn = document.getElementById('btn-clear-lt-filters');
            if (ltClearBtn) ltClearBtn.onclick = () => this.clearLtFilters();

            // Modal close buttons (data-close)
            document.querySelectorAll('[data-close="modal-operation"]').forEach(btn => {
                btn.onclick = () => this._closeModal('modal-operation');
            });
            document.querySelectorAll('[data-close="modal-long-text"]').forEach(btn => {
                btn.onclick = () => this.closeLongTextModal();
            });
            document.querySelectorAll('[data-close="modal-spell-review"]').forEach(btn => {
                btn.onclick = () => this._closeModal('modal-spell-review');
            });
            document.querySelectorAll('[data-close="modal-save-standard-lt"]').forEach(btn => {
                btn.onclick = () => this._closeModal('modal-save-standard-lt');
            });

            // Modal overlay click-outside to close
            ['modal-operation', 'modal-long-text', 'modal-spell-review', 'modal-save-standard-lt'].forEach(id => {
                const overlay = document.getElementById(id);
                if (overlay) {
                    overlay.onclick = (e) => {
                        if (e.target !== overlay) return;
                        if (id === 'modal-long-text') this.closeLongTextModal();
                        else this._closeModal(id);
                    };
                }
            });

            // Save buttons
            const saveOpBtn = document.getElementById('btn-save-operation');
            if (saveOpBtn) saveOpBtn.onclick = () => this.saveOperation();
            const saveLtBtn = document.getElementById('btn-save-long-text');
            if (saveLtBtn) saveLtBtn.onclick = () => this.saveLongText();
            const opItemFilter = document.getElementById('form-op-item-filter');
            if (opItemFilter) opItemFilter.oninput = () => this.renderOperationItemOptions();

            // Click outside to close custom select dropdowns
            document.addEventListener('click', (e) => {
                if (!e.target.closest('.custom-select-container')) {
                    document.querySelectorAll('.custom-select-dropdown').forEach(d => d.classList.remove('open'));
                    document.querySelectorAll('.custom-select-trigger').forEach(t => t.classList.remove('open'));
                }
            });

            // Item and Operation search listeners inside custom dropdowns
            const ltItemSearchInput = document.getElementById('form-lt-item-search');
            if (ltItemSearchInput) {
                ltItemSearchInput.oninput = () => this.renderLongTextItemOptions(ltItemSearchInput.value);
            }
            const ltOpSearchInput = document.getElementById('form-lt-op-search');
            if (ltOpSearchInput) {
                ltOpSearchInput.oninput = () => this.renderLongTextOperationOptions(null, ltOpSearchInput.value);
            }

            document.querySelectorAll('[data-close="modal-sap-order"]').forEach(btn => btn.onclick = () => this._closeModal('modal-sap-order'));
            document.querySelectorAll('[data-close="modal-sap-add-operation"]').forEach(btn => btn.onclick = () => this._closeModal('modal-sap-add-operation'));
            document.getElementById('btn-sap-print').onclick = () => this.printSapOrder();
            document.getElementById('btn-sap-add-operation').onclick = () => this.openSapAddOperation();
            document.getElementById('btn-sap-create-operation').onclick = () => this.createSapOperation();

            this._bindBulkControls('operations', this.selectedOperationIds, '.operation-row-checkbox');
            this._bindBulkControls('long-texts', this.selectedLongTextIds, '.long-text-row-checkbox');
            document.getElementById('btn-bulk-edit-operations').onclick = () => this.openBulkEditOperations();
            document.getElementById('btn-bulk-edit-long-texts').onclick = () => this.openBulkEditLongTexts();
            document.getElementById('btn-bulk-clone-operations').onclick = () => this.bulkClone('operations');
            document.getElementById('btn-bulk-clone-long-texts').onclick = () => this.bulkClone('long-texts');
            const btnDeleteOps = document.getElementById('btn-bulk-delete-operations');
            if (btnDeleteOps) btnDeleteOps.onclick = () => this.bulkDelete('operations');
            const btnDeleteLts = document.getElementById('btn-bulk-delete-long-texts');
            if (btnDeleteLts) btnDeleteLts.onclick = () => this.bulkDelete('long-texts');
            document.getElementById('btn-bulk-edit-operations-confirm').onclick = () => this.bulkEditOperationsConfirm();
            document.getElementById('btn-bulk-edit-long-texts-confirm').onclick = () => this.bulkEditLongTextsConfirm();
            ['operations', 'long-texts'].forEach(kind => {
                document.querySelectorAll(`[data-close="modal-bulk-edit-${kind}"]`).forEach(btn => {
                    btn.onclick = () => this._closeModal(`modal-bulk-edit-${kind}`);
                });
            });
            [['op', ['wc','short-text','unit','headcount','hours']], ['lt', ['group-code','group-counter','text']]].forEach(([prefix, fields]) => {
                fields.forEach(field => {
                    const cb = document.getElementById(`bulk-${prefix}-enable-${field}`);
                    const input = document.getElementById(`bulk-${prefix}-input-${field}`);
                    if (cb && input) cb.onchange = () => { input.disabled = !cb.checked; };
                });
            });

            // Char counter for short text
            const shortTextInput = document.getElementById('form-op-short-text');
            const charCount = document.getElementById('form-op-short-text-chars');
            if (shortTextInput && charCount) {
                shortTextInput.oninput = () => {
                    charCount.textContent = `${shortTextInput.value.length} / 40`;
                };
            }

            // Operations table header sorting
            const opsTable = document.getElementById('operations-table');
            if (opsTable) {
                opsTable.querySelectorAll('thead th.sortable').forEach(th => {
                    th.onclick = (e) => {
                        if (e.target.closest('.col-filter-btn') || e.target.closest('.column-resizer')) return;
                        const col = th.getAttribute('data-col');
                        if (this.opFilters.order_by === col) {
                            this.opFilters.order_dir = this.opFilters.order_dir === 'ASC' ? 'DESC' : 'ASC';
                        } else {
                            this.opFilters.order_by = col;
                            this.opFilters.order_dir = 'ASC';
                        }
                        this.loadOperations();
                    };
                });
            }

            // Long texts table header sorting
            const ltTable = document.getElementById('long-texts-table');
            if (ltTable) {
                ltTable.querySelectorAll('thead th.sortable').forEach(th => {
                    th.onclick = (e) => {
                        if (e.target.closest('.col-filter-btn') || e.target.closest('.column-resizer')) return;
                        const col = th.getAttribute('data-col');
                        if (this.ltFilters.order_by === col) {
                            this.ltFilters.order_dir = this.ltFilters.order_dir === 'ASC' ? 'DESC' : 'ASC';
                        } else {
                            this.ltFilters.order_by = col;
                            this.ltFilters.order_dir = 'ASC';
                        }
                        this.loadLongTexts();
                    };
                });
            }

        } catch (e) {
            console.error('[Operations.init] Error:', e);
        }
    },

    // ==========================================
    // 1. OPERATIONS MANAGEMENT
    // ==========================================

    applyOpFilters() {
        const s = document.getElementById('filter-ops-search');
        const wc = document.getElementById('filter-ops-wc');
        const issue = document.getElementById('filter-ops-issues');
        this.opFilters.search = s ? s.value.trim() : '';
        this.opFilters.work_center = wc ? wc.value : '';
        this.opFilters.issue_status = issue ? issue.value : '';
        this.opFilters.row_color = document.getElementById('filter-ops-row-color')?.value || '';
        this.opFilters.offset = 0;
        if (window.ColumnFilter) window.ColumnFilter.clearAllFilters('operations-table');
        this.loadOperations();
    },

    clearOpFilters() {
        const s = document.getElementById('filter-ops-search');
        const wc = document.getElementById('filter-ops-wc');
        const issue = document.getElementById('filter-ops-issues');
        if (s) s.value = '';
        if (wc) wc.value = '';
        if (issue) issue.value = '';
        if (document.getElementById('filter-ops-row-color')) document.getElementById('filter-ops-row-color').value = '';
        this.opFilters.search = '';
        this.opFilters.work_center = '';
        this.opFilters.issue_status = '';
        this.opFilters.row_color = '';
        this.opFilters.offset = 0;
        if (window.ColumnFilter) window.ColumnFilter.clearAllFilters('operations-table');
        this.loadOperations();
    },

    async loadOperations(options = {}) {
        const tbody = document.getElementById('operations-table-body');
        const countLbl = document.getElementById('operations-total-count');
        if (!tbody) return;

        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) {
            tbody.innerHTML = '<tr><td colspan="10" class="empty-table-cell">Nenhum projeto selecionado.</td></tr>';
            if (countLbl) countLbl.textContent = '0 operações';
            return;
        }

        const isSilent = options.silent || (tbody.children.length > 0 && !tbody.querySelector('.empty-table-cell'));
        if (!isSilent) {
            tbody.innerHTML = '<tr><td colspan="10" class="empty-table-cell">Carregando operações...</td></tr>';
        }

        const runTask = async () => {
            try {
                await this.loadItemDescriptions(projectId);
                const res = await API.get('/api/operations', {
                    project_id: projectId,
                    search: this.opFilters.search,
                    work_center: this.opFilters.work_center,
                    order_by: this.opFilters.order_by,
                    order_dir: this.opFilters.order_dir,
                    limit: this.opFilters.limit,
                    offset: this.opFilters.offset
                });

                let ops = res.operations || [];
                if (this.opFilters.row_color) ops = ops.filter(o => o.row_color === this.opFilters.row_color);

                // Filter by issue status
                if (this.opFilters.issue_status) {
                    const st = this.opFilters.issue_status;
                    if (st === 'issues') ops = ops.filter(o => (o.validation_issues || []).length > 0);
                    else if (st === 'ERROR') ops = ops.filter(o => (o.validation_issues || []).some(x => x.severity === 'ERROR'));
                    else if (st === 'WARNING') ops = ops.filter(o => (o.validation_issues || []).some(x => x.severity === 'WARNING'));
                    else if (st === 'OK') ops = ops.filter(o => !o.validation_issues || o.validation_issues.length === 0);
                }

                const total = res.total || ops.length;
                this.currentOperations = ops;

                // Apply column filters client-side
                if (window.ColumnFilter) {
                    ops = window.ColumnFilter.applyFiltersToDataset('operations-table', ops);
                }

                if (countLbl) {
                    countLbl.textContent = `${total} ${total === 1 ? 'operação cadastrada' : 'operações cadastradas'}`;
                }

                // Update WC filter options dynamically
                const wcSel = document.getElementById('filter-ops-wc');
                if (wcSel) {
                    const allWcs = [...new Set(this.currentOperations.map(o => o.work_center).filter(Boolean))].sort();
                    const curVal = wcSel.value;
                    wcSel.innerHTML = '<option value="">Todos os C.T.</option>' +
                        allWcs.map(wc => `<option value="${this.esc(wc)}" ${wc === curVal ? 'selected' : ''}>${this.esc(wc)}</option>`).join('');
                }

                if (ops.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="10" class="empty-table-cell">${this.opFilters.search || this.opFilters.work_center || this.opFilters.issue_status ? 'Nenhuma operação encontrada para os filtros aplicados.' : 'Nenhuma operação cadastrada neste projeto.'}</td></tr>`;
                    return;
                }

                tbody.innerHTML = ops.map(o => {
                    const safeIdent = this.esc(o.legacy_identifier);
                    const safeItemDescription = this.esc(o.item_description || this.itemDescriptions.get(String(o.legacy_identifier)) || '-');
                    const safeCode = this.esc(o.operation_code);
                    const safeSub = this.esc(o.suboperation_code);
                    const safeWc = this.esc(o.work_center);
                    const safeShort = this.esc(o.short_text);
                    const safeHc = o.headcount !== null && o.headcount !== undefined ? o.headcount : '';
                    const rawHours = o.hours !== null && o.hours !== undefined ? o.hours : '';
                    const safeHours = rawHours !== '' ? Number(rawHours).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) : '';
                    const safeObj = this.esc(o.object_code || '');

                    const validationIssues = o.validation_issues || [];
                    const issueMessages = [...new Set(validationIssues.map(x => x.message))];
                    const isError = validationIssues.some(x => x.severity === 'ERROR');
                    const isWarning = validationIssues.length > 0 && !isError;

                    let rowClass = '';
                    if (isError) rowClass = 'table-alert-red';
                    else if (isWarning) rowClass = 'table-alert-yellow';

                    const issuesText = issueMessages.map(m => `• ${m}`).join('\n');
                    const indicator = validationIssues.length > 0
                        ? `<span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" style="cursor:pointer;" onclick="event.stopPropagation(); App.openIssueFixModal('operation', ${o.id})" title="Clique para abrir o diagnóstico e aplicar a correção automática: ${this.esc(issuesText)}">${isError ? '⛔' : '⚠️'}</span>`
                        : '';

                    if (o.row_color) rowClass += ` item-row-marked item-row-color-${o.row_color}`;
                    const shownIdentifier = this.esc(o.pending_item_identifier || o.legacy_identifier);
                    return `<tr class="${rowClass}" ${validationIssues.length ? `title="${this.esc(issuesText)}"` : ''}>
                        <td class="text-center" style="display:flex; align-items:center; justify-content:center; gap:4px; height:100%; padding: 8px 4px;">
                            ${indicator}<button class="row-color-brush" onclick="RowTools.open(event,'operations',${o.id},'()=>Operations.loadOperations()')">🖌️</button><input type="checkbox" class="operation-row-checkbox" data-id="${o.id}" ${this.selectedOperationIds.has(o.id) ? 'checked' : ''} onchange="Operations.toggleBulkSelection('operations',this,${o.id})">
                        </td>
                        <td class="text-center">
                            <span class="badge badge-neutral" title="${safeObj}">${shownIdentifier}</span>
                        </td>
                        <td class="management-description-cell" style="font-weight: 500;">${safeItemDescription}</td>
                        <td class="text-center editable-cell" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'operation_code','${o.operation_code || ''}','op','text',4)">
                            <strong>${safeCode || '-'}</strong>
                        </td>
                        <td class="text-center editable-cell" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'suboperation_code','${o.suboperation_code || ''}','op','text',4)">
                            <span style="color:var(--text-muted);">${safeSub || '-'}</span>
                        </td>
                        <td class="text-center editable-cell" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'work_center','${o.work_center || ''}','op','text',8)">
                            <span class="badge badge-active">${safeWc || '-'}</span>
                        </td>
                        <td class="editable-cell" style="font-weight:500;" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'short_text','${(o.short_text||'').replace(/'/g,"\\'").replace(/"/g,'&quot;')}','op','text',40)">
                            ${safeShort}
                        </td>
                        <td class="text-center editable-cell" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'headcount','${safeHc}','op','number',4)">
                            ${safeHc !== '' ? safeHc : '<span style="color:var(--text-muted);">-</span>'}
                        </td>
                        <td class="text-center editable-cell" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${o.id},'hours','${rawHours}','op','number',8)">
                            ${safeHours !== '' ? safeHours : '<span style="color:var(--text-muted);">-</span>'}
                        </td>
                        <td class="text-center">
                            <div class="actions-cell" style="justify-content: center; gap: 4px;">
                                <button class="btn btn-xs btn-primary" title="Pré-visualizar ordem no modelo SAP" onclick="Operations.openSapOrder(${o.item_id})">SAP</button>
                                ${((String(o.operation_code) === '0010' || String(o.operation_code) === '10') && (!o.suboperation_code || o.suboperation_code === '' || o.suboperation_code === '-'))
                                    ? ''
                                    : ((o.long_text_count || 0) > 0 
                                        ? `<button class="btn btn-xs btn-success" title="Ver / Editar texto longo desta operação" onclick="Operations.openEditLongTextModalForOp(${o.id})">📝 Texto Longo</button>` 
                                        : `<button class="btn btn-xs btn-outline" style="color:#0284C7; border-color:#38BDF8;" title="Criar texto longo / procedimento para esta operação" onclick="Operations.openCreateLongTextModalForOp(${o.id}, ${o.item_id})">+ Texto Longo</button>`
                                    )
                                }
                                ${((String(o.operation_code) === '0010' || String(o.operation_code) === '10') && (!o.suboperation_code || o.suboperation_code === '' || o.suboperation_code === '-')) ? '' : `<button class="btn btn-xs btn-outline" style="color:#6B4E00;border-color:#E6C85C;" title="Inserir um bloco padrão diretamente no texto longo desta operação" onclick="Operations.openBlockLibraryForOp(${o.id},${o.item_id})">🧩 + Bloco</button>`}
                                <button class="btn btn-xs btn-outline" title="Editar operação" onclick="Operations.openEditModal(${o.id})">Editar</button>
                                <button class="btn btn-xs btn-outline" title="Clonar como cópia pendente" onclick="Operations.cloneOperation(${o.id})">Clonar</button>
                                <button class="btn btn-xs btn-danger" title="Excluir operação" onclick="Operations.deleteOperation(${o.id})">Excluir</button>
                            </div>
                        </td>
                    </tr>`;
                }).join('');

                // Init / refresh column filters
                if (window.ColumnFilter) {
                    window.ColumnFilter.init('operations-table', () => this.currentOperations, (sortCol, sortDir) => {
                        if (sortCol && sortDir) {
                            this.opFilters.order_by = sortCol;
                            this.opFilters.order_dir = sortDir;
                        }
                        this.loadOperations();
                    });
                }

            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="10" class="empty-table-cell" style="color:var(--color-danger);">Erro ao carregar operações: ${this.esc(err.message)}</td></tr>`;
                UI.showToast(err.message, 'error');
            }
        };

        if (window.App && typeof App.preserveScroll === 'function') {
            return App.preserveScroll(tbody, runTask);
        } else {
            return runTask();
        }
    },

    _filterRowsByItemId(rows, query) {
        const value = String(query || '').trim();
        if (!value) return rows;
        const exact = rows.filter(row => String(row.legacy_identifier) === value);
        return exact.length ? exact : rows.filter(row => String(row.legacy_identifier).startsWith(value));
    },

    renderOperationItemOptions() {
        const select = document.getElementById('form-op-item-id');
        const filter = document.getElementById('form-op-item-filter');
        if (!select || select.disabled) return;
        const previous = select.value;
        const items = this._filterRowsByItemId(this.modalItems, filter ? filter.value : '');
        select.innerHTML = '<option value="">Selecione o item / ordem...</option>' +
            items.map(item => `<option value="${item.id}">[ID ${this.esc(item.legacy_identifier)}] ${this.esc(item.description || item.object_code)}</option>`).join('');
        if (items.some(item => String(item.id) === previous)) select.value = previous;
        else if (items.length === 1) select.value = String(items[0].id);
        if (!items.length) select.innerHTML = '<option value="">Nenhum item encontrado para este ID</option>';
    },

    renderLongTextOperationOptions() {
        const select = document.getElementById('form-lt-op-id');
        const filter = document.getElementById('form-lt-item-filter');
        if (!select || select.disabled) return;
        const previous = select.value;
        const operations = this._filterRowsByItemId(this.modalOperations, filter ? filter.value : '');
        select.innerHTML = '<option value="">Selecione a operação...</option>' +
            operations.map(operation => `<option value="${operation.id}">[ID ${this.esc(operation.legacy_identifier)}] Op. ${this.esc(operation.operation_code)}${operation.suboperation_code ? `/${this.esc(operation.suboperation_code)}` : ''} – ${this.esc(operation.short_text)}</option>`).join('');
        if (operations.some(operation => String(operation.id) === previous)) select.value = previous;
        if (!operations.length) select.innerHTML = '<option value="">Nenhuma operação encontrada para este ID</option>';
    },

    async openCreateModal() {
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) { UI.showToast('Selecione um projeto primeiro.', 'warning'); return; }

        document.getElementById('modal-operation-title').textContent = 'Nova Operação';
        document.getElementById('form-op-id').value = '';
        document.getElementById('form-op-code').value = '0010';
        document.getElementById('form-op-subcode').value = '';
        document.getElementById('form-op-wc').value = '';
        document.getElementById('form-op-short-text').value = '';
        document.getElementById('form-op-unit').value = 'H';
        document.getElementById('form-op-headcount').value = '';
        document.getElementById('form-op-hours').value = '';
        const itemFilter = document.getElementById('form-op-item-filter');
        itemFilter.value = '';
        itemFilter.disabled = false;

        const charCount = document.getElementById('form-op-short-text-chars');
        if (charCount) charCount.textContent = '0 / 40';

        const select = document.getElementById('form-op-item-id');
        select.disabled = false;
        select.innerHTML = '<option value="">Carregando itens...</option>';
        this.modalItems = [];

        try {
            const res = await API.get('/api/items', { project_id: projectId, limit: 2000 });
            this.modalItems = res.items || [];
            this.renderOperationItemOptions();
        } catch (e) {
            select.innerHTML = '<option value="">Erro ao carregar itens</option>';
        }

        this._openModal('modal-operation');
    },

    async openEditModal(opId) {
        const op = this.currentOperations.find(o => o.id === opId);
        if (!op) {
            UI.showToast('Operação não encontrada. Recarregue a lista.', 'warning');
            return;
        }

        document.getElementById('modal-operation-title').textContent = 'Editar Operação';
        document.getElementById('form-op-id').value = op.id;
        document.getElementById('form-op-code').value = op.operation_code || '';
        document.getElementById('form-op-subcode').value = op.suboperation_code || '';
        document.getElementById('form-op-wc').value = op.work_center || '';
        document.getElementById('form-op-short-text').value = op.short_text || '';
        document.getElementById('form-op-unit').value = op.unit || 'H';
        document.getElementById('form-op-headcount').value = op.headcount ?? '';
        document.getElementById('form-op-hours').value = op.hours ?? '';

        const charCount = document.getElementById('form-op-short-text-chars');
        if (charCount) charCount.textContent = `${(op.short_text || '').length} / 40`;

        const select = document.getElementById('form-op-item-id');
        select.innerHTML = `<option value="${op.item_id}" selected>[ID ${op.legacy_identifier}] ${this.esc(op.item_description || op.object_code)}</option>`;
        select.disabled = true;
        const itemFilter = document.getElementById('form-op-item-filter');
        itemFilter.value = op.legacy_identifier || '';
        itemFilter.disabled = true;

        this._openModal('modal-operation');
    },

    async saveOperation() {
        const id = document.getElementById('form-op-id').value;
        const projectId = window.App ? App.getValidProjectId() : null;
        const itemId = document.getElementById('form-op-item-id').value;
        const code = document.getElementById('form-op-code').value.trim();
        const subcode = document.getElementById('form-op-subcode').value.trim();
        const wc = document.getElementById('form-op-wc').value.trim();
        const shortText = document.getElementById('form-op-short-text').value.trim();
        const unit = document.getElementById('form-op-unit').value.trim() || 'H';
        const hc = document.getElementById('form-op-headcount').value;
        const hours = document.getElementById('form-op-hours').value;

        if (!id && !itemId) { UI.showToast('Selecione o item de manutenção.', 'warning'); return; }
        if (!code) { UI.showToast('Informe o código da operação (ex: 0010).', 'warning'); return; }
        if (!shortText) { UI.showToast('Informe o texto breve da operação.', 'warning'); return; }

        const payload = {
            project_id: projectId,
            item_id: id ? undefined : parseInt(itemId),
            operation_code: code,
            suboperation_code: subcode,
            work_center: wc,
            short_text: shortText,
            unit: unit,
            headcount: hc ? parseInt(hc) : null,
            hours: hours ? parseFloat(hours) : null
        };
        if (id) {
            const current = this.currentOperations.find(operation => Number(operation.id) === Number(id));
            payload.resolve_import_placeholder = Boolean(
                current?.validation_issues?.some(issue => issue.code === 'long_text_without_operation')
            );
        }

        try {
            if (id) {
                await API.put(`/api/operations/${id}`, payload);
                UI.showToast('Operação atualizada com sucesso!', 'success');
            } else {
                await API.post('/api/operations', payload);
                UI.showToast('Operação criada com sucesso!', 'success');
            }
            this._closeModal('modal-operation');
            await this.loadOperations();
        } catch (err) {
            UI.showToast(err.message, 'error');
        }
    },

    async cloneOperation(opId) {
        try {
            await API.post(`/api/operations/${opId}/clone`, {project_id: App.getValidProjectId()});
            UI.showToast('Operação clonada como [COPIA] 1111. Corrija o item vinculado.', 'warning', 4500);
            await this.loadOperations();
        } catch (err) { UI.showToast(`Erro ao clonar operação: ${err.message}`, 'error'); }
    },

    async deleteOperation(opId) {
        if (!confirm('Tem certeza que deseja excluir esta operação? Todos os textos longos vinculados também serão removidos.')) return;
        try {
            await API.delete(`/api/operations/${opId}`);
            UI.showToast('Operação excluída com sucesso!', 'success');
            await this.loadOperations();
        } catch (err) {
            UI.showToast(err.message, 'error');
        }
    },

    // ==========================================
    // 2. LONG TEXTS MANAGEMENT
    // ==========================================

    applyLtFilters() {
        const s = document.getElementById('filter-lt-search');
        const issue = document.getElementById('filter-lt-issues');
        this.ltFilters.search = s ? s.value.trim() : '';
        this.ltFilters.issue_status = issue ? issue.value : '';
        this.ltFilters.row_color = document.getElementById('filter-lt-row-color')?.value || '';
        this.ltFilters.offset = 0;
        if (window.ColumnFilter) window.ColumnFilter.clearAllFilters('long-texts-table');
        this.loadLongTexts();
    },

    clearLtFilters() {
        const s = document.getElementById('filter-lt-search');
        const issue = document.getElementById('filter-lt-issues');
        if (s) s.value = '';
        if (issue) issue.value = '';
        if (document.getElementById('filter-lt-row-color')) document.getElementById('filter-lt-row-color').value = '';
        this.ltFilters.search = '';
        this.ltFilters.issue_status = '';
        this.ltFilters.row_color = '';
        this.ltFilters.offset = 0;
        if (window.ColumnFilter) window.ColumnFilter.clearAllFilters('long-texts-table');
        this.loadLongTexts();
    },

    async loadLongTexts(options = {}) {
        const tbody = document.getElementById('long-texts-table-body');
        const countLbl = document.getElementById('long-texts-total-count');
        if (!tbody) return;

        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-table-cell">Nenhum projeto selecionado.</td></tr>';
            if (countLbl) countLbl.textContent = '0 textos longos';
            return;
        }

        const isSilent = options.silent || (tbody.children.length > 0 && !tbody.querySelector('.empty-table-cell'));
        if (!isSilent) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-table-cell">Carregando textos longos...</td></tr>';
        }

        const runTask = async () => {
            try {
                await this.loadItemDescriptions(projectId);
                const res = await API.get('/api/long-texts', {
                    project_id: projectId,
                    search: this.ltFilters.search,
                    limit: this.ltFilters.limit,
                    offset: this.ltFilters.offset,
                    order_by: this.ltFilters.order_by || 'legacy_identifier',
                    order_dir: this.ltFilters.order_dir || 'asc'
                });

                let texts = res.long_texts || [];
                if (this.ltFilters.row_color) texts = texts.filter(t => t.row_color === this.ltFilters.row_color);

                texts.forEach(t => {
                    const issues = Array.isArray(t.validation_issues) ? [...t.validation_issues] : [];
                    if (!t.operation_id) {
                        issues.push({ severity: 'ERROR', message: 'Texto longo sem correspondência com nenhuma operação.' });
                    }
                    if (t.validation_status === 'ERROR' && !issues.some(issue => issue.severity === 'ERROR')) {
                        issues.push({ severity: 'ERROR', message: 'Inconsistência no texto longo ou vínculo.' });
                    }
                    t.computed_issues = issues;
                });

                if (this.ltFilters.issue_status) {
                    const st = this.ltFilters.issue_status;
                    if (st === 'issues') texts = texts.filter(t => t.computed_issues.length > 0);
                    else if (st === 'ERROR') texts = texts.filter(t => t.computed_issues.some(x => x.severity === 'ERROR'));
                    else if (st === 'WARNING') texts = texts.filter(t => t.computed_issues.some(x => x.severity === 'WARNING'));
                    else if (st === 'OK') texts = texts.filter(t => t.computed_issues.length === 0);
                }

                const total = res.total || texts.length;
                this.currentLongTexts = texts;

                // Apply column filters client-side
                if (window.ColumnFilter) {
                    texts = window.ColumnFilter.applyFiltersToDataset('long-texts-table', texts);
                }

                if (countLbl) {
                    countLbl.textContent = `${total} ${total === 1 ? 'texto longo cadastrado' : 'textos longos cadastrados'}`;
                }

                if (texts.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="7" class="empty-table-cell">${this.ltFilters.search || this.ltFilters.issue_status ? 'Nenhum texto longo encontrado para a busca.' : 'Nenhum texto longo cadastrado neste projeto.'}</td></tr>`;
                    return;
                }

                tbody.innerHTML = texts.map(t => {
                    const safeIdent = this.esc(t.pending_item_identifier || t.legacy_identifier || '-');
                    const safeObj = this.esc(t.object_code || '');
                    const safeOp = this.esc(t.operation_code || '');
                    const safeSub = this.esc(t.suboperation_code || '-');
                    const safeItemDescription = this.esc(t.item_description || this.itemDescriptions.get(String(t.legacy_identifier)) || '-');
                    const safeOpShortText = this.esc(t.op_short_text || '-');

                    const rawTxt = String(t.text || '').replace(/^[ \t]+/, '');
                    const subStr = str => str === null || str === undefined ? '' : String(str).trim();
                    const cleanSub = subStr(t.suboperation_code);
                    const isFirst0010 = (safeOp === '0010' && ['', '0000', '-', 'None'].includes(cleanSub));

                    let safeText = '';
                    if (rawTxt !== '') {
                        safeText = this.esc(rawTxt);
                    } else if (isFirst0010) {
                        safeText = '<span style="color: var(--text-muted); font-style: italic;">(vazio)</span>';
                    } else {
                        safeText = '<span style="color: var(--text-muted); font-style: italic;">(vazio)</span>';
                    }

                    const validationIssues = t.computed_issues || [];
                    const issueMessages = [...new Set(validationIssues.map(x => x.message))];
                    const isError = validationIssues.some(x => x.severity === 'ERROR');
                    const isWarning = validationIssues.length > 0 && !isError;
                    const rowId = t.id;

                    let rowClass = '';
                    if (isError) rowClass = 'table-alert-red';
                    else if (isWarning) rowClass = 'table-alert-yellow';

                    const issuesText = issueMessages.map(m => `• ${m}`).join('\n');
                    const indicator = validationIssues.length > 0
                        ? `<span class="row-issue-indicator issue-${isError ? 'error' : 'warning'}" style="cursor:pointer;" onclick="event.stopPropagation(); App.openIssueFixModal('long-text', ${rowId})" title="Clique para abrir o diagnóstico e aplicar a correção automática: ${this.esc(issuesText)}">${isError ? '⛔' : '⚠️'}</span>`
                        : '';

                    if (t.row_color) rowClass += ` item-row-marked item-row-color-${t.row_color}`;
                    return `<tr class="${rowClass}" ${validationIssues.length ? `title="${this.esc(issuesText)}"` : ''}>
                        <td class="text-center" style="display:flex; align-items:center; justify-content:center; gap:4px; height:100%; padding: 8px 4px;">
                            ${indicator}<button class="row-color-brush" onclick="RowTools.open(event,'long-texts',${rowId},'()=>Operations.loadLongTexts()')">🖌️</button><input type="checkbox" class="long-text-row-checkbox" data-id="${rowId}" ${this.selectedLongTextIds.has(rowId) ? 'checked' : ''} onchange="Operations.toggleBulkSelection('long-texts',this,${rowId})">
                        </td>
                        <td class="text-center">
                            <span class="badge badge-neutral" title="${safeObj}">${safeIdent}</span>
                        </td>
                        <td class="text-center"><strong>${safeOp}</strong></td>
                        <td class="text-center"><span style="color:var(--text-muted);">${safeSub}</span></td>
                        <td class="management-description-cell" style="font-weight: 500;">${safeItemDescription}</td>
                        <td class="management-description-cell">${safeOpShortText}</td>
                        <td class="editable-cell" style="white-space: pre-wrap; font-family: inherit; font-size: 0.85rem; line-height: 1.45;" title="2x para editar" ondblclick="Operations.makeCellEditable(this,${rowId},'text','${(t.text||'').replace(/'/g,"\\'").replace(/"/g,'&quot;')}','lt','text',4000)">${safeText}</td>
                        <td class="text-center">
                            <div class="actions-cell" style="justify-content: center; gap: 4px; flex-wrap:wrap;">
                                <button class="btn btn-xs btn-outline" style="color:#0F766E;border-color:#5EEAD4;" title="Abrir editor estruturado de tópicos, subtópicos e blocos" onclick="Operations.openEditLongTextModal(${rowId})">🧩 Editar blocos</button>
                                <button class="btn btn-xs btn-outline" title="Clonar como cópia pendente" onclick="Operations.cloneLongText(${rowId})">Clonar</button>
                                <button class="btn btn-xs btn-danger" title="Excluir texto" onclick="Operations.deleteLongText(${rowId})">Excluir</button>
                            </div>
                        </td>
                    </tr>`;
                }).join('');

                // Init / refresh column filters
                if (window.ColumnFilter) {
                    window.ColumnFilter.init('long-texts-table', () => this.currentLongTexts, (sortCol, sortDir) => {
                        if (sortCol && sortDir) {
                            this.ltFilters.order_by = sortCol;
                            this.ltFilters.order_dir = sortDir;
                        }
                        this.loadLongTexts();
                    });
                }

            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="7" class="empty-table-cell" style="color:var(--color-danger);">Erro ao carregar textos longos: ${this.esc(err.message)}</td></tr>`;
                UI.showToast(err.message, 'error');
            }
        };

        if (window.App && typeof App.preserveScroll === 'function') {
            return App.preserveScroll(tbody, runTask);
        } else {
            return runTask();
        }
    },

    async openCreateLongTextModal(presetOpId = null, presetItemId = null) {
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) { UI.showToast('Selecione um projeto primeiro.', 'warning'); return; }

        document.getElementById('modal-long-text-title').textContent = 'Novo Texto Longo';
        document.getElementById('form-lt-id').value = '';
        document.getElementById('form-lt-text').value = '';
        if (window.LongTextEditor) LongTextEditor.startBlank();

        const itemSearch = document.getElementById('form-lt-item-search');
        if (itemSearch) itemSearch.value = '';
        const opSearch = document.getElementById('form-lt-op-search');
        if (opSearch) opSearch.value = '';

        const itemSelect = document.getElementById('form-lt-item-id');
        const opSelect = document.getElementById('form-lt-op-id');
        if (itemSelect) itemSelect.value = '';
        if (opSelect) opSelect.value = '';
        document.getElementById('custom-lt-item-trigger-text').textContent = 'Selecione o item de manutenção...';
        document.getElementById('custom-lt-op-trigger-text').textContent = 'Selecione a operação...';

        try {
            const [itemsRes, opsRes] = await Promise.all([
                API.get('/api/items', { project_id: projectId, limit: 5000 }),
                API.get('/api/operations', { project_id: projectId, limit: 10000 })
            ]);

            this.modalItems = itemsRes.items || [];
            this.modalOperations = opsRes.operations || [];

            this.renderLongTextItemOptions();

            if (presetItemId) {
                this.selectLongTextItem(presetItemId);
                if (presetOpId) this.selectLongTextOperation(presetOpId);
            } else if (presetOpId) {
                const opMatch = this.modalOperations.find(o => o.id === presetOpId);
                if (opMatch && opMatch.item_id) {
                    this.selectLongTextItem(opMatch.item_id);
                    this.selectLongTextOperation(presetOpId);
                } else {
                    this.renderLongTextOperationOptions();
                    this.selectLongTextOperation(presetOpId);
                }
            } else {
                this.renderLongTextOperationOptions();
            }

            if (window.StandardsManager) {
                await window.StandardsManager.loadLongTexts();
            }
        } catch (e) {
            document.getElementById('custom-lt-item-options').innerHTML = '<div class="custom-select-option no-results">Erro ao carregar itens.</div>';
            document.getElementById('custom-lt-op-options').innerHTML = '<div class="custom-select-option no-results">Erro ao carregar operações.</div>';
        }

        this._openModal('modal-long-text');
    },

    async openCreateLongTextModalForOp(opId, itemId) {
        await this.openCreateLongTextModal(opId, itemId);
    },

    async openEditLongTextModalForOp(opId) {
        try {
            const projectId = window.App ? App.getValidProjectId() : null;
            const res = await API.get('/api/long-texts', { project_id: projectId, limit: 5000 });
            const match = (res.long_texts || []).find(t => t.operation_id === opId);
            if (match) {
                await this.populateAndOpenEditLongTextModal(match);
            } else {
                const op = (this.currentOperations || []).find(o => o.id === opId);
                await this.openCreateLongTextModal(opId, op ? op.item_id : null);
            }
        } catch (e) {
            UI.showToast('Erro ao abrir texto longo da operação.', 'error');
        }
    },

    async openBlockLibraryForOp(opId, itemId) {
        try {
            const projectId = window.App ? App.getValidProjectId() : null;
            const res = await API.get('/api/long-texts', { project_id: projectId, operation_id: opId, limit: 100 });
            const match = (res.long_texts || [])[0];
            if (match) {
                await this.populateAndOpenEditLongTextModal(match);
            } else {
                await this.openCreateLongTextModal(opId, itemId);
                if (window.LongTextEditor) {
                    LongTextEditor.mode = 'STRUCTURED';
                    LongTextEditor.nodes = [];
                    LongTextEditor.render();
                }
            }
            if (window.LongTextEditor) await LongTextEditor.openBlockLibrary();
        } catch (e) {
            UI.showToast(`Erro ao abrir biblioteca de blocos: ${e.message}`, 'error');
        }
    },

    renderLongTextItemOptions(searchTerm = '') {
        const itemSelect = document.getElementById('form-lt-item-id');
        const options = document.getElementById('custom-lt-item-options');
        if (!itemSelect || !options) return;

        let filtered = this.modalItems || [];
        if (searchTerm) {
            const term = searchTerm.toLowerCase().trim();
            filtered = filtered.filter(i => 
                String(i.legacy_identifier || '').toLowerCase().includes(term) ||
                String(i.description || '').toLowerCase().includes(term) ||
                String(i.object_code || '').toLowerCase().includes(term)
            );
        }

        options.innerHTML = filtered.length
            ? filtered.map(i => `<div class="custom-select-option${String(i.id) === String(itemSelect.value) ? ' selected' : ''}" onclick="Operations.selectLongTextItem('${this.esc(i.id)}')">[ID ${this.esc(i.legacy_identifier)}] ${this.esc(i.description || i.object_code || '')}</div>`).join('')
            : '<div class="custom-select-option no-results">Nenhum item encontrado.</div>';
    },

    selectLongTextItem(itemId) {
        const item = (this.modalItems || []).find(i => String(i.id) === String(itemId));
        document.getElementById('form-lt-item-id').value = itemId;
        document.getElementById('custom-lt-item-trigger-text').textContent = item
            ? `[ID ${item.legacy_identifier}] ${item.description || item.object_code || ''}`
            : 'Selecione o item de manutenção...';
        document.getElementById('form-lt-op-id').value = '';
        document.getElementById('custom-lt-op-trigger-text').textContent = 'Selecione a operação...';
        this.renderLongTextItemOptions(document.getElementById('form-lt-item-search')?.value || '');
        this.renderLongTextOperationOptions(itemId);
        this.closeCustomDropdown('custom-lt-item-dropdown');
    },

    renderLongTextOperationOptions(selectedItemId = null, searchTerm = '') {
        const opSelect = document.getElementById('form-lt-op-id');
        const options = document.getElementById('custom-lt-op-options');
        if (!opSelect || !options) return;

        const itemId = selectedItemId || document.getElementById('form-lt-item-id')?.value;
        let filtered = this.modalOperations || [];

        if (itemId) {
            filtered = filtered.filter(o => String(o.item_id) === String(itemId));
        }

        if (searchTerm) {
            const term = searchTerm.toLowerCase().trim();
            filtered = filtered.filter(o => 
                String(o.operation_code || '').toLowerCase().includes(term) ||
                String(o.short_text || '').toLowerCase().includes(term) ||
                String(o.legacy_identifier || '').toLowerCase().includes(term)
            );
        }

        if (filtered.length === 0) {
            options.innerHTML = `<div class="custom-select-option no-results">${itemId ? 'Nenhuma operação encontrada neste item.' : 'Selecione um item primeiro.'}</div>`;
            return;
        }

        options.innerHTML = filtered.map(o => {
            const opLabel = `Op. ${o.operation_code}${o.suboperation_code ? ' / ' + o.suboperation_code : ''} – ${o.short_text || ''}`;
            return `<div class="custom-select-option${String(o.id) === String(opSelect.value) ? ' selected' : ''}" onclick="Operations.selectLongTextOperation('${this.esc(o.id)}')">${this.esc(opLabel)}</div>`;
        }).join('');
    },

    selectLongTextOperation(operationId) {
        const operation = (this.modalOperations || []).find(o => String(o.id) === String(operationId));
        document.getElementById('form-lt-op-id').value = operationId;
        document.getElementById('custom-lt-op-trigger-text').textContent = operation
            ? `Op. ${operation.operation_code}${operation.suboperation_code ? ' / ' + operation.suboperation_code : ''} – ${operation.short_text || ''}`
            : 'Selecione a operação...';
        this.renderLongTextOperationOptions(null, document.getElementById('form-lt-op-search')?.value || '');
        this.closeCustomDropdown('custom-lt-op-dropdown');
    },

    async openEditLongTextModal(textId) {
        let txt = (this.currentLongTexts || []).find(t => t.id === textId);
        if (!txt) {
            try {
                const projectId = window.App ? App.getValidProjectId() : null;
                const res = await API.get('/api/long-texts', { project_id: projectId, limit: 5000 });
                txt = (res.long_texts || []).find(t => t.id === textId);
            } catch (_) {}
        }
        if (!txt) {
            UI.showToast('Texto longo não encontrado. Recarregue a lista.', 'warning');
            return;
        }
        this.populateAndOpenEditLongTextModal(txt);
    },

    async populateAndOpenEditLongTextModal(txt) {
        document.getElementById('modal-long-text-title').textContent = 'Editar Texto Longo / Blocos';
        document.getElementById('form-lt-id').value = txt.id;
        document.getElementById('form-lt-text').value = txt.text || '';
        if (window.LongTextEditor) await LongTextEditor.loadRecord(txt);

        const itemSearch = document.getElementById('form-lt-item-search');
        if (itemSearch) itemSearch.value = '';
        const opSearch = document.getElementById('form-lt-op-search');
        if (opSearch) opSearch.value = '';

        const projectId = window.App ? App.getValidProjectId() : null;
        try {
            const [itemsRes, opsRes] = await Promise.all([
                API.get('/api/items', { project_id: projectId || undefined, limit: 5000 }),
                API.get('/api/operations', { project_id: projectId || undefined, limit: 10000 })
            ]);
            this.modalItems = itemsRes.items || itemsRes || [];
            this.modalOperations = opsRes.operations || opsRes || [];
        } catch (_) {}

        // Older long-text responses did not expose item_id. Resolve the item
        // through the linked operation, with the item identifier as fallback.
        const linkedOperation = (this.modalOperations || []).find(operation =>
            String(operation.id) === String(txt.operation_id)
        );
        const linkedItem = linkedOperation?.item_id
            ? (this.modalItems || []).find(item => String(item.id) === String(linkedOperation.item_id))
            : (this.modalItems || []).find(item =>
                String(item.legacy_identifier) === String(txt.legacy_identifier)
            );
        const resolvedItemId = txt.item_id || linkedOperation?.item_id || linkedItem?.id || '';

        this.renderLongTextItemOptions();
        const itemSelect = document.getElementById('form-lt-item-id');
        if (itemSelect) {
            if (resolvedItemId) itemSelect.value = resolvedItemId;
        }

        this.renderLongTextOperationOptions(resolvedItemId || itemSelect?.value);
        const opSelect = document.getElementById('form-lt-op-id');
        if (opSelect) {
            if (txt.operation_id) opSelect.value = txt.operation_id;
        }
        if (resolvedItemId) this.selectLongTextItem(resolvedItemId);
        if (txt.operation_id) this.selectLongTextOperation(txt.operation_id);

        if (window.StandardsManager) {
            await window.StandardsManager.loadLongTexts();
        }

        this._openModal('modal-long-text');
    },

    async checkLongTextSpell() {
        const textarea = document.getElementById('form-lt-text');
        if (!textarea) return;
        const payload = window.LongTextEditor ? LongTextEditor.getPayload() : { text: textarea.value };
        const text = payload.text || '';
        if (!text.trim()) {
            UI.showToast('Digite algum texto para revisar a ortografia.', 'info');
            return;
        }
        if (!window.SpellChecker) {
            UI.showToast('Revisor ortográfico não carregado.', 'warning');
            return;
        }
        const analysis = SpellChecker.analyze(text);
        if (analysis.hasSuggestions) {
            if (window.LongTextEditor) await LongTextEditor.setFromText(analysis.correctedText, true);
            else textarea.value = analysis.correctedText;
            const count = analysis.changesCount || 1;
            UI.showToast(`Ortografia revisada: ${count} ajuste(s) de acentuação/grafia aplicado(s)!`, 'success');
        } else {
            UI.showToast('Nenhum erro ortográfico ou acentuação pendente detectado.', 'success');
        }
    },

    async openCreateLongTextModalForOpFromSap(opId, itemId) {
        this.refreshSapOrderAfterLtSave = itemId;
        await this.openCreateLongTextModal(opId, itemId);
    },

    async openEditLongTextFromSap(textId, itemId) {
        this.refreshSapOrderAfterLtSave = itemId;
        const textRow = (this.sapOrder?.operations || [])
            .flatMap(row => row.long_texts || [])
            .find(row => Number(row.id) === Number(textId));
        if (textRow) {
            await this.populateAndOpenEditLongTextModal(textRow);
            return;
        }
        await this.openEditLongTextModal(Number(textId));
    },

    async saveLongText(skipSpellCheck = false) {
        const button = document.getElementById('btn-save-long-text');
        if (button?.dataset.saving === 'true') return;
        const originalLabel = button?.textContent || 'Salvar Texto Longo';
        if (button) {
            button.dataset.saving = 'true';
            button.disabled = true;
            button.textContent = 'Salvando...';
        }
        try {
            await this._saveLongText(skipSpellCheck);
        } catch (err) {
            console.error('[Operations.saveLongText] Erro inesperado:', err);
            UI.showToast(err?.message || 'Nao foi possivel salvar o Texto Longo.', 'error', 7000);
        } finally {
            if (button) {
                button.dataset.saving = 'false';
                button.disabled = false;
                button.textContent = originalLabel;
            }
        }
    },

    async _saveLongText(skipSpellCheck = false) {
        const id = document.getElementById('form-lt-id').value;
        const projectId = window.App ? App.getValidProjectId() : null;
        const opId = document.getElementById('form-lt-op-id').value;
        const editorPayload = window.LongTextEditor ? LongTextEditor.getPayload() : {
            text: document.getElementById('form-lt-text').value.trim(), structure_mode: 'FREE', structure_json: null
        };
        let text = String(editorPayload.text || '').trim();

        if (!id && !opId) { UI.showToast('Selecione a operação vinculada.', 'warning'); return; }

        // A Texto Longo record cannot be useful as an empty placeholder. When editing an
        // existing record, clearing all content is therefore treated as an explicit request
        // to delete that Texto Longo. New records still require content.
        if (!text) {
            if (id) {
                const confirmed = confirm('O conteúdo deste Texto Longo ficou vazio.\n\nDeseja excluir o Texto Longo desta operação?\n\nA operação e o título breve NÃO serão excluídos.');
                if (!confirmed) return;
                try {
                    await API.delete(`/api/long-texts/${id}`);
                    UI.showToast('Texto Longo removido da operação com sucesso!', 'success');
                    this._closeModal('modal-long-text');
                    await Promise.all([this.loadLongTexts(), this.loadOperations()]);
                    if (this.refreshSapOrderAfterLtSave) {
                        const targetItemId = this.refreshSapOrderAfterLtSave;
                        this.refreshSapOrderAfterLtSave = null;
                        await this.openSapOrder(targetItemId);
                    }
                } catch (err) {
                    UI.showToast(err.message, 'error');
                }
                return;
            }
            UI.showToast('Digite o conteúdo do texto longo.', 'warning');
            return;
        }

        if (!skipSpellCheck && window.SpellChecker) {
            const analysis = SpellChecker.analyze(text);
            if (analysis.hasSuggestions) {
                this.promptSpellReview(analysis, async (finalText) => {
                    if (window.LongTextEditor) await LongTextEditor.setFromText(finalText, true);
                    else document.getElementById('form-lt-text').value = finalText;
                    this.saveLongText(true);
                });
                return;
            }
        }

        const finalPayload = window.LongTextEditor ? LongTextEditor.getPayload() : editorPayload;
        const payload = {
            project_id: projectId,
            operation_id: parseInt(opId),
            text: finalPayload.text,
            structure_mode: finalPayload.structure_mode,
            structure_json: finalPayload.structure_json,
            source_text_original: finalPayload.source_text_original
        };

        try {
            if (id && String(id) !== '0') {
                await API.put(`/api/long-texts/${id}`, payload);
                UI.showToast('Texto longo atualizado com sucesso!', 'success');
            } else {
                await API.post('/api/long-texts', payload);
                UI.showToast('Texto longo cadastrado com sucesso!', 'success');
            }
            this._closeModal('modal-long-text');
            await Promise.all([this.loadLongTexts(), this.loadOperations()]);
            if (this.refreshSapOrderAfterLtSave || this.sapItemId) {
                const targetItemId = this.refreshSapOrderAfterLtSave || this.sapItemId;
                this.refreshSapOrderAfterLtSave = null;
                await this.openSapOrder(targetItemId);
            }
        } catch (err) { UI.showToast(err.message, 'error'); }
    },

    openSaveStandardPopup() {
        const text = window.LongTextEditor ? LongTextEditor.getPayload().text.trim() : document.getElementById('form-lt-text').value.trim();
        if (!text) {
            UI.showToast('Digite o conteúdo do texto longo antes de criar o padrão.', 'warning');
            return;
        }
        document.getElementById('form-std-lt-title').value = '';
        document.getElementById('form-std-lt-category').value = 'GERAL';
        this._openModal('modal-save-standard-lt');
    },

    async confirmSaveStandardLongText() {
        const title = document.getElementById('form-std-lt-title').value.trim();
        const category = document.getElementById('form-std-lt-category').value.trim() || 'GERAL';
        const editorPayload = window.LongTextEditor ? LongTextEditor.getPayload() : { text: document.getElementById('form-lt-text').value.trim(), structure_mode:'FREE', structure_json:null };
        const text = editorPayload.text.trim();

        if (!title) {
            UI.showToast('Digite um título para o modelo padrão.', 'warning');
            return;
        }

        if (window.StandardsManager) {
            await window.StandardsManager.saveCurrentLongTextAsStandard(title, category, text, editorPayload);
        }

        this._closeModal('modal-save-standard-lt');
        await this.saveLongText();
    },

    promptSpellReview(analysis, onConfirm) {
        const modal = document.getElementById('modal-spell-review');
        const origEl = document.getElementById('spell-review-original');
        const suggEl = document.getElementById('spell-review-suggested');
        const diffEl = document.getElementById('spell-review-diff-details');
        const badgeEl = document.getElementById('spell-review-badge');
        
        if (!modal || !origEl || !suggEl) {
            onConfirm(analysis.correctedText);
            return;
        }

        badgeEl.innerText = `${analysis.changesCount} correção(ões) sugerida(s):`;
        origEl.innerText = analysis.originalText;
        suggEl.innerText = analysis.correctedText;

        if (diffEl) {
            if (analysis.diffList && analysis.diffList.length > 0) {
                const uniqueDiffs = Array.from(new Set(analysis.diffList.map(d => `"${d.original}" ➔ "${d.suggested}"`)));
                diffEl.innerHTML = `<strong>Ajustes identificados:</strong> ` + uniqueDiffs.join(' • ');
            } else {
                diffEl.innerHTML = `<strong>Ajustes identificados:</strong> Ajustes de espaçamento e acentuação técnica.`;
            }
        }

        const btnApply = document.getElementById('btn-spell-apply-suggested');
        const btnKeep = document.getElementById('btn-spell-keep-original');
        const btnCancel = document.getElementById('btn-spell-cancel');

        const closeModal = () => {
            modal.classList.add('hidden');
        };

        modal.querySelectorAll('.modal-close, [data-close]').forEach(btn => {
            btn.onclick = () => closeModal();
        });

        modal.onclick = (e) => {
            if (e.target === modal) closeModal();
        };

        btnApply.onclick = () => {
            closeModal();
            onConfirm(analysis.correctedText);
        };

        btnKeep.onclick = () => {
            closeModal();
            onConfirm(analysis.originalText);
        };

        btnCancel.onclick = () => {
            closeModal();
        };

        modal.classList.remove('hidden');
    },

    async cloneLongText(textId) {
        try {
            await API.post(`/api/long-texts/${textId}/clone`, {project_id: App.getValidProjectId()});
            UI.showToast('Texto clonado como [COPIA] 1111. Corrija o item/operação vinculados.', 'warning', 4500);
            await this.loadLongTexts();
        } catch (err) { UI.showToast(`Erro ao clonar texto longo: ${err.message}`, 'error'); }
    },

    async deleteLongText(textId) {
        if (!confirm('Tem certeza que deseja excluir este texto longo?')) return;
        try {
            await API.delete(`/api/long-texts/${textId}`);
            UI.showToast('Texto longo excluído com sucesso!', 'success');
            await this.loadLongTexts();
        } catch (err) {
            UI.showToast(err.message, 'error');
        }
    },

    async openSapOrder(itemId) {
        this.sapItemId = itemId;
        this._openModal('modal-sap-order');
        document.getElementById('sap-order-document').innerHTML = '<div class="empty-state">Carregando ordem de manutenção...</div>';
        try {
            this.sapOrder = await API.get(`/api/items/${itemId}/sap-order`, { _t: Date.now() });
            if (!this.sapOrder?.item || !Array.isArray(this.sapOrder?.operations)) {
                this.sapOrder = await this.loadSapOrderFallback(itemId);
            }
            this.renderSapOrder();
        } catch (err) {
            document.getElementById('sap-order-document').innerHTML = `<div class="empty-state">Erro ao carregar a ordem: ${this.esc(err.message)}</div>`;
        }
    },

    async loadSapOrderFallback(itemId) {
        const projectId = App.getValidProjectId();
        const [item, operationResponse] = await Promise.all([
            API.get(`/api/items/${itemId}`),
            API.get('/api/operations', { project_id: projectId, item_id: itemId, limit: 2000 })
        ]);
        const operations = operationResponse?.operations || [];
        await Promise.all(operations.map(async operation => {
            const response = await API.get('/api/long-texts', {
                project_id: projectId, operation_id: operation.id, limit: 2000
            });
            operation.long_texts = response?.long_texts || [];
        }));
        item.project_name = document.getElementById('active-project-name')?.textContent?.trim() || '';
        return { item, operations };
    },

    _sapEditable(value, entity, id, field, type = 'text') {
        const shown = value === null || value === undefined || value === '' ? '-' : value;
        return `<span class="sap-order-value sap-editable" data-entity="${entity}" data-id="${id}" data-field="${field}" data-type="${type}" title="Duplo clique para editar">${this.esc(shown)}</span>`;
    },

    _sapLongTextHtml(value) {
        // Use explicit HTML breaks instead of relying on whitespace rendering.
        // Consecutive newlines become consecutive <br> elements, so every blank
        // line saved in a spreadsheet/model remains visible in the SAP order.
        return this.esc(String(value ?? '').replace(/\r\n?/g, '\n')).replace(/\n/g, '<br>');
    },

    renderSapOrder() {
        const target = document.getElementById('sap-order-document');
        if (!target || !this.sapOrder) return;
        const item = this.sapOrder.item;
        const operations = this.sapOrder.operations || [];
        const field = (label, value, cls = '') => `<div class="sap-order-field ${cls}"><span class="sap-order-label">${label}</span>${value}</div>`;
        const operationRows = operations.map(operation => {
            const texts = operation.long_texts || [];
            const isTitleRow = operation.operation_code === '0010' && !operation.suboperation_code;
            const longTexts = texts.length
                ? texts.map(textRow => `<div class="sap-long-text-entry">
                    <div class="sap-long-text sap-editable" data-entity="long-text" data-id="${textRow.id}" data-field="text" data-type="structured" title="Duplo clique para abrir o editor estruturado">${this._sapLongTextHtml(textRow.text)}</div>
                    <div class="sap-screen-only" style="display:flex;justify-content:flex-end;gap:6px;margin:3px 8px 7px 8px;">
                        <button type="button" class="btn btn-xs btn-outline" style="color:#0F766E;border-color:#5EEAD4;" title="Editar tópicos, subtópicos, parágrafos livres e blocos deste texto longo" onclick="Operations.openEditLongTextFromSap(${textRow.id},${item.id})">🧩 Editar blocos</button>
                    </div>
                </div>`).join('')
                : (isTitleRow ? '' : '<div class="sap-long-text sap-no-long-text">Sem texto longo cadastrado.</div>');
            const addTextAction = isTitleRow
                ? '<span class="sap-order-label sap-screen-only" style="display:block;padding:6px 10px;">Cabeçalho da ordem — não recebe texto longo.</span>'
                : `${texts.length === 0 ? `<button class="btn btn-xs btn-outline sap-screen-only" style="margin:6px 5px 6px 10px; color:#0284C7; border-color:#38BDF8;" onclick="Operations.openCreateLongTextModalForOpFromSap(${operation.id}, ${item.id})">+ Inserir texto longo</button>` : ''}<button class="btn btn-xs btn-outline sap-screen-only" style="margin:6px 10px 6px 5px;color:#6B4E00;border-color:#E6C85C;" onclick="Operations.openBlockLibraryForOp(${operation.id},${item.id})">🧩 + Bloco padrão</button>`;
            return `<tbody class="sap-operation-group">
                <tr>
                    <td>${this._sapEditable(operation.operation_code, 'operation', operation.id, 'operation_code')}</td>
                    <td>${this._sapEditable(operation.suboperation_code || '-', 'operation', operation.id, 'suboperation_code')}</td>
                    <td>${this._sapEditable(operation.work_center || '-', 'operation', operation.id, 'work_center')}</td>
                    <td>${this._sapEditable(operation.headcount ?? '-', 'operation', operation.id, 'headcount', 'number')}</td>
                    <td>${this._sapEditable(operation.hours ?? '-', 'operation', operation.id, 'hours', 'number')}</td>
                    <td>${this.esc(operation.headcount && operation.hours ? operation.headcount * operation.hours : '-')}</td>
                    <td>${this._sapEditable(operation.unit || 'H', 'operation', operation.id, 'unit')}</td>
                </tr>
                <tr class="sap-op-text-row"><td colspan="7"><span class="sap-order-label">DESCRIÇÃO</span>${this._sapEditable(operation.short_text, 'operation', operation.id, 'short_text')}${longTexts}${addTextAction}</td></tr>
            </tbody>`;
        }).join('');
        const sim = 'Simulação';
        const orderNumber = item.order_number || item.legacy_identifier || sim;
        const printedAt = new Date().toLocaleString('pt-BR', {dateStyle:'short', timeStyle:'short'});
        target.innerHTML = `
            <div class="sap-order-brand">
                <div class="sap-order-brand-logo">USIMINAS <span>U</span></div>
                <div class="sap-order-brand-title">ORDEM DE MANUTENÇÃO</div>
                <div class="sap-order-brand-meta">Nº ${this.esc(orderNumber)}</div>
            </div>
            <div class="sap-order-warning">EXECUÇÃO NÃO AUTORIZADA</div>
            <div class="sap-order-critical">CRITICIDADE: ***COMPLEXA REPETITIVA***</div>
            <div class="sap-order-grid sap-order-summary">
                ${field('Texto breve', this._sapEditable(item.description, 'item', item.id, 'description'), 'wide')}
                ${field('TAM', this.esc(item.object_type || sim))} ${field('Tipo', this.esc(item.condition_code || sim))}
                ${field('ST.SIS', sim)} ${field('ST.US', this.esc(item.status || sim))}
                ${field('Total HH Prev', this.esc(item.hh ?? item.duration_hours ?? sim))}
                ${field('C.Trab.', this._sapEditable(item.work_center, 'item', item.id, 'work_center'))}
                ${field('Resp. C. Trab.', sim, 'wide')} ${field('Revisão', sim)}
                ${field('Prior.', this._sapEditable(item.priority, 'item', item.id, 'priority', 'number'))}
                ${field('Data prev.', sim)} ${field('Plano', this.esc(item.plan_code || sim))}
                ${field('Item', this.esc(item.legacy_identifier || sim))} ${field('Utiliz.', sim)}
                ${field('Status', this.esc(item.status || sim))}
                ${field('Loc. instal.', this._sapEditable(item.object_code, 'item', item.id, 'object_code'), 'wide')}
                ${field('Resp. GPM', sim)} ${field('Equip.', this.esc(item.object_code || sim), 'wide')}
            </div>
            <div class="sap-order-section"><b>CHAVES A BLOQUEAR</b><div>Nº bloqueio: ${sim} &nbsp;&nbsp; Pos. bloq.: ${sim}</div><div><b>TOTAL DE CHAVES A BLOQUEAR:</b> ${sim}</div></div>
            <div class="sap-order-section"><b>PONTOS DE COMPLEXIDADE DA ATIVIDADE</b><div>Fator de Criticidade: ${sim}</div><div>Manutenção em sistemas elétricos energizados e/ou próximos (Zona de Risco e NR10).</div></div>
            <div class="sap-order-section"><b>INFORMAÇÕES GERAIS</b><div>PONTO DE URGÊNCIA: ${sim} &nbsp;&nbsp;&nbsp; PONTO DE SOLDA: ${sim}</div></div>
            <div class="sap-order-section-title">ATIVIDADES</div>
            <table class="sap-operations-table"><thead><tr><th>OP</th><th>S.OP</th><th>C.TRAB</th><th>EFT</th><th>DUR</th><th>HH PREV</th><th></th></tr></thead>${operationRows || '<tbody><tr><td colspan="7">Nenhuma operação cadastrada.</td></tr></tbody>'}</table>
            <div class="sap-order-footer"><span>CRIADO POR: ${sim}</span><span>RG: ${sim}</span><span>IMPRESSO POR: ${sim}</span><span>${printedAt}</span><span>ORDEM: ${this.esc(orderNumber)}</span><span>PÁGINA 1 / 1</span><span>CLASSIFICAÇÃO DA INFORMAÇÃO: USO INTERNO</span></div>
            <div class="sap-order-hint sap-screen-only">Campos em amarelo ao passar o mouse podem ser alterados com duplo clique.</div>`;
        target.querySelectorAll('.sap-editable').forEach(element => {
            element.ondblclick = event => this.startSapInlineEdit(event.currentTarget);
        });
    },

    startSapInlineEdit(element) {
        if (element.dataset.entity === 'long-text') {
            this.openEditLongTextFromSap(Number(element.dataset.id), this.sapItemId);
            return;
        }
        if (element.classList.contains('editing')) return;
        element.classList.add('editing');
        const original = element.textContent === '-' ? '' : element.textContent;
        const multiline = element.dataset.type === 'multiline';
        const input = document.createElement(multiline ? 'textarea' : 'input');
        input.className = multiline ? 'sap-edit-textarea' : 'sap-edit-input';
        if (!multiline && element.dataset.type === 'number') input.type = 'number';
        input.value = original;
        element.textContent = '';
        element.appendChild(input);
        input.focus();
        if (multiline) {
            const height = Math.max(element.getBoundingClientRect().height, input.scrollHeight, 110);
            input.style.height = `${height}px`;
            input.oninput = () => { input.style.height = 'auto'; input.style.height = `${Math.max(input.scrollHeight, 110)}px`; };
        }
        if (input.select) input.select();
        let finished = false;
        const save = async (skipSpell = false) => {
            if (finished) return;
            const val = input.value;
            const field = element.dataset.field;

            if (!skipSpell && (field === 'text' || field === 'short_text' || field === 'description') && window.SpellChecker) {
                const analysis = SpellChecker.analyze(val);
                if (analysis.hasSuggestions) {
                    this.promptSpellReview(analysis, (finalText) => {
                        input.value = finalText;
                        save(true);
                    });
                    return;
                }
            }

            finished = true;
            await this.saveSapInlineField(element.dataset.entity, Number(element.dataset.id), field, val);
        };
        input.onkeydown = event => {
            if (event.key === 'Escape') { finished = true; this.renderSapOrder(); }
            if ((!multiline && event.key === 'Enter') || (multiline && event.ctrlKey && event.key === 'Enter')) { event.preventDefault(); save(); }
        };
        input.onblur = () => save();
    },

    async saveSapInlineField(entity, id, field, rawValue) {
        const value = ['headcount','hours','priority','duration_hours'].includes(field)
            ? (rawValue === '' ? null : Number(rawValue)) : rawValue;
        try {
            if (entity === 'operation') {
                const operation = this.sapOrder.operations.find(row => row.id === id);
                const payload = { ...operation, [field]: value, project_id: this.sapOrder.item.project_id, item_id: operation.item_id };
                await API.put(`/api/operations/${id}`, payload);
            } else if (entity === 'long-text') {
                const textRow = this.sapOrder.operations.flatMap(row => row.long_texts || []).find(row => row.id === id);
                if (field === 'text' && !String(value).trim()) throw new Error('O texto longo não pode ficar vazio.');
                await API.put(`/api/long-texts/${id}`, {
                    ...textRow,
                    [field]: value,
                    structure_mode: 'FREE',
                    structure_json: null,
                    source_text_original: value
                });
            } else if (entity === 'item') {
                const item = this.sapOrder.item;
                const payload = { ...item, [field]: value, plan_id: item.plan_id, team_id: null };
                await API.put(`/api/items/${id}`, payload);
            }
            this._sapStatus('Salvo na base.');
            await this.openSapOrder(this.sapItemId);
            await this.loadOperations();
            await this.loadLongTexts();
        } catch (err) {
            UI.showToast(`Erro ao salvar: ${err.message}`, 'error');
            await this.openSapOrder(this.sapItemId);
        }
    },

    _sapStatus(message) {
        const status = document.getElementById('sap-order-save-status');
        if (!status) return;
        status.textContent = message;
        window.setTimeout(() => { status.textContent = ''; }, 2500);
    },

    openSapAddOperation() {
        if (!this.sapItemId) return;
        document.getElementById('sap-new-op-code').value = '';
        document.getElementById('sap-new-sub-code').value = '';
        document.getElementById('sap-new-work-center').value = '';
        document.getElementById('sap-new-short-text').value = '';
        document.getElementById('sap-new-headcount').value = '';
        document.getElementById('sap-new-hours').value = '';
        document.getElementById('sap-new-unit').value = 'H';
        document.getElementById('sap-new-long-text').value = '';
        this._openModal('modal-sap-add-operation');
    },

    async saveSapNewOperation() {
        const opCode = document.getElementById('sap-new-op-code').value.trim();
        const shortText = document.getElementById('sap-new-short-text').value.trim();
        if (!opCode || !shortText) { UI.showToast('Preencha ao menos a operação e o texto breve.', 'warning'); return; }
        const payload = {
            project_id: this.sapOrder.item.project_id,
            item_id: this.sapItemId,
            operation_code: opCode,
            suboperation_code: document.getElementById('sap-new-sub-code').value.trim() || null,
            work_center: document.getElementById('sap-new-work-center').value.trim() || null,
            short_text: shortText,
            unit: document.getElementById('sap-new-unit').value.trim() || 'H',
            headcount: document.getElementById('sap-new-headcount').value === '' ? null : Number(document.getElementById('sap-new-headcount').value),
            hours: document.getElementById('sap-new-hours').value === '' ? null : Number(document.getElementById('sap-new-hours').value)
        };
        try {
            const created = await API.post('/api/operations', payload);
            const longText = document.getElementById('sap-new-long-text').value.trim();
            if (longText) await API.post('/api/long-texts', { project_id: payload.project_id, operation_id: created.id, text: longText });
            this._closeModal('modal-sap-add-operation');
            await this.openSapOrder(this.sapItemId);
            await this.loadOperations();
            await this.loadLongTexts();
            UI.showToast('Operação inserida na ordem e salva nas abas correspondentes.', 'success');
        } catch (err) { UI.showToast(`Erro ao inserir: ${err.message}`, 'error'); }
    },

    async addSapLongText(operationId) {
        const textValue = window.prompt('Digite o texto longo / procedimento técnico:');
        if (!textValue || !textValue.trim()) return;
        let finalText = textValue.trim();
        if (window.SpellChecker) {
            const analysis = SpellChecker.analyze(finalText);
            if (analysis.hasSuggestions) {
                this.promptSpellReview(analysis, async (reviewedText) => {
                    try {
                        await API.post('/api/long-texts', { project_id: this.sapOrder.item.project_id, operation_id: operationId, text: reviewedText });
                        await this.openSapOrder(this.sapItemId);
                        await this.loadLongTexts();
                    } catch (err) { UI.showToast(`Erro ao inserir texto longo: ${err.message}`, 'error'); }
                });
                return;
            }
        }
        try {
            await API.post('/api/long-texts', { project_id: this.sapOrder.item.project_id, operation_id: operationId, text: finalText });
            await this.openSapOrder(this.sapItemId);
            await this.loadLongTexts();
        } catch (err) { UI.showToast(`Erro ao inserir texto longo: ${err.message}`, 'error'); }
    },

    printSapOrder() {
        document.body.classList.add('sap-printing');
        const modal = document.getElementById('modal-sap-order');
        if (modal) modal.classList.remove('hidden');

        const cleanup = () => {
            document.body.classList.remove('sap-printing');
        };

        window.addEventListener('afterprint', cleanup, { once: true });

        setTimeout(() => {
            window.print();
            setTimeout(cleanup, 2000);
        }, 150);
    },

    _bindBulkControls(kind, selectedSet, checkboxSelector) {
        const checkAll = document.getElementById(`check-all-${kind}`);
        if (!checkAll) return;
        checkAll.onchange = () => {
            document.querySelectorAll(checkboxSelector).forEach(cb => {
                cb.checked = checkAll.checked;
                const id = Number(cb.dataset.id);
                if (checkAll.checked) selectedSet.add(id); else selectedSet.delete(id);
            });
            this.updateBulkToolbar(kind);
        };
    },

    toggleBulkSelection(kind, checkbox, id) {
        const selectedSet = kind === 'operations' ? this.selectedOperationIds : this.selectedLongTextIds;
        if (checkbox.checked) selectedSet.add(id); else selectedSet.delete(id);
        const checkAll = document.getElementById(`check-all-${kind}`);
        if (checkAll && !checkbox.checked) checkAll.checked = false;
        this.updateBulkToolbar(kind);
    },

    updateBulkToolbar(kind) {
        const selectedSet = kind === 'operations' ? this.selectedOperationIds : this.selectedLongTextIds;
        const toolbar = document.getElementById(`bulk-actions-toolbar-${kind}`);
        const count = document.getElementById(`bulk-selection-count-${kind}`);
        if (count) count.textContent = kind === 'operations'
            ? `${selectedSet.size} operações selecionadas`
            : `${selectedSet.size} textos selecionados`;
        if (toolbar) toolbar.classList.toggle('hidden', selectedSet.size === 0);
    },

    async bulkClone(kind) {
        const selectedSet = kind === 'operations' ? this.selectedOperationIds : this.selectedLongTextIds;
        const ids = Array.from(selectedSet);
        const label = kind === 'operations' ? 'operações' : 'textos longos';
        if (!ids.length || !confirm(`Clonar ${ids.length} ${label} selecionados?`)) return;
        let cloned = 0;
        UI.showLoader(`Clonando ${label} selecionados...`);
        try {
            for (const id of ids) {
                await API.post(`/api/${kind}/${id}/clone`, { project_id: App.getValidProjectId() });
                cloned++;
            }
            selectedSet.clear();
            this.updateBulkToolbar(kind);
            UI.showToast(`${cloned} de ${ids.length} registros clonados com sucesso.`, 'success');
            if (kind === 'operations') await this.loadOperations(); else await this.loadLongTexts();
        } catch (err) {
            UI.showToast(`${cloned} de ${ids.length} registros clonados. Erro: ${err.message}`, 'error', 5000);
            if (kind === 'operations') await this.loadOperations(); else await this.loadLongTexts();
        } finally { UI.hideLoader(); }
    },

    async bulkDelete(kind) {
        const selectedSet = kind === 'operations' ? this.selectedOperationIds : this.selectedLongTextIds;
        const ids = Array.from(selectedSet);
        if (!ids.length) return;
        const projectId = App.getValidProjectId();

        if (kind === 'long-texts') {
            const modalChoice = document.getElementById('modal-delete-lt-choice');
            const msgEl = document.getElementById('delete-lt-choice-count-msg');
            if (msgEl) msgEl.innerHTML = `Você selecionou <strong>${ids.length} texto(s) longo(s)</strong>.`;
            if (modalChoice) modalChoice.classList.remove('hidden');

            const btnOnlyLt = document.getElementById('btn-delete-only-lt');
            const btnLtAndOps = document.getElementById('btn-delete-lt-and-ops');

            if (btnOnlyLt) {
                btnOnlyLt.onclick = async () => {
                    if (modalChoice) modalChoice.classList.add('hidden');
                    await this.executeBulkDeleteEndpoint('long-texts', ids, projectId, false);
                };
            }
            if (btnLtAndOps) {
                btnLtAndOps.onclick = async () => {
                    if (modalChoice) modalChoice.classList.add('hidden');
                    await this.executeBulkDeleteEndpoint('long-texts', ids, projectId, true);
                };
            }
            return;
        }

        // Deleting operations directly
        const impactMsg = `Tem certeza que deseja excluir em massa as <strong>${ids.length} operações</strong> selecionadas?<br><br><span style="color:var(--danger-color);font-size:12px;">⚠️ Os textos longos vinculados a estas operações também serão removidos.</span>`;
        window.App.confirm("Excluir Operações em Massa", impactMsg, async () => {
            await this.executeBulkDeleteEndpoint('operations', ids, projectId, false);
        });
    },

    async executeBulkDeleteEndpoint(kind, ids, projectId, deleteAssociatedOps = false) {
        const selectedSet = kind === 'operations' ? this.selectedOperationIds : this.selectedLongTextIds;
        const label = kind === 'operations' ? 'operações' : 'textos longos';
        
        App.showBulkProgressModal(`Excluindo ${label} em Massa...`, `Transmitindo solicitação para excluir <strong>${ids.length} ${label}</strong>...`);
        try {
            App.updateBulkProgressModal(60, "Processando remoção no banco de dados SQLite...");
            const endpoint = kind === 'operations' ? '/api/operations/bulk-delete' : '/api/long-texts/bulk-delete';
            const res = await API.post(endpoint, {
                project_id: projectId,
                ids: ids,
                delete_associated_operations: deleteAssociatedOps
            });
            selectedSet.clear();
            this.updateBulkToolbar(kind);
            App.finishBulkProgressModal(true, "Exclusão Concluída!", res.message || `${ids.length} ${label} excluído(s) com sucesso!`);
            await Promise.all([this.loadOperations(), this.loadLongTexts()]);
        } catch (err) {
            App.finishBulkProgressModal(false, `Erro na Exclusão (${label})`, `Falha ao processar exclusão no servidor: ${err.message}`);
            selectedSet.clear();
            this.updateBulkToolbar(kind);
            await Promise.all([this.loadOperations(), this.loadLongTexts()]);
        }
    },

    _resetBulkForm(prefix, fields) {
        fields.forEach(field => {
            const cb = document.getElementById(`bulk-${prefix}-enable-${field}`);
            const input = document.getElementById(`bulk-${prefix}-input-${field}`);
            if (cb) cb.checked = false;
            if (input) { input.value = ''; input.disabled = true; }
        });
    },

    openBulkEditOperations() {
        this._resetBulkForm('op', ['wc','short-text','unit','headcount','hours']);
        document.getElementById('bulk-edit-operations-count-text').textContent =
            `${this.selectedOperationIds.size} operações selecionadas serão alteradas em massa.`;
        this._openModal('modal-bulk-edit-operations');
    },

    async bulkEditOperationsConfirm() {
        const updates = {};
        const values = {
            'wc': ['work_center', 'bulk-op-input-wc'],
            'short-text': ['short_text', 'bulk-op-input-short-text'],
            'unit': ['unit', 'bulk-op-input-unit'],
            'headcount': ['headcount', 'bulk-op-input-headcount'],
            'hours': ['hours', 'bulk-op-input-hours']
        };
        Object.entries(values).forEach(([field, [key, inputId]]) => {
            if (!document.getElementById(`bulk-op-enable-${field}`).checked) return;
            const raw = document.getElementById(inputId).value.trim();
            updates[key] = ['headcount','hours'].includes(key) ? (raw === '' ? null : Number(raw)) : raw;
        });
        await this._submitBulkEdit('operations', Array.from(this.selectedOperationIds), updates);
    },

    openBulkEditLongTexts() {
        const countText = document.getElementById('bulk-edit-long-texts-count-text');
        if (countText) {
            countText.textContent = `${this.selectedLongTextIds.size} textos longos selecionados serão alterados em massa.`;
        }

        const cb = document.getElementById('bulk-lt-enable-text');
        const input = document.getElementById('bulk-lt-input-text');
        
        if (cb) cb.checked = false;
        if (input) {
            input.value = '';
            input.disabled = false;
        }

        if (input && !input._hasBulkListeners) {
            input._hasBulkListeners = true;
            input.addEventListener('focus', () => { if (cb) cb.checked = true; });
            input.addEventListener('input', () => { if (cb) cb.checked = true; });
            input.addEventListener('click', () => { if (cb) cb.checked = true; });
        }

        const clearBtn = document.getElementById('btn-bulk-lt-clear');
        if (clearBtn && !clearBtn._hasClickListener) {
            clearBtn._hasClickListener = true;
            clearBtn.addEventListener('click', () => {
                if (input) input.value = '';
                if (cb) cb.checked = true;
                UI.showToast('Marcado para limpar (Texto Vazio). Clique em Aplicar para confirmar.', 'info');
            });
        }

        this._openModal('modal-bulk-edit-long-texts');
    },

    async bulkEditLongTextsConfirm() {
        const cb = document.getElementById('bulk-lt-enable-text');
        const input = document.getElementById('bulk-lt-input-text');

        if (!cb || !cb.checked) {
            UI.showToast('Marque a caixa de seleção ou digite/limpe o campo para alterar em massa.', 'error');
            return;
        }

        const updates = {
            'text': input ? input.value : ''
        };

        await this._submitBulkEdit('long-texts', Array.from(this.selectedLongTextIds), updates);
    },

    async _submitBulkEdit(kind, ids, updates) {
        if (!Object.keys(updates).length) {
            UI.showToast('Marque pelo menos um campo para editar em massa.', 'error');
            return;
        }
        const label = kind === 'operations' ? 'operações' : 'textos longos';
        if (!window.confirm(`Aplicar as alterações em ${ids.length} ${label}?`)) return;
        UI.showLoader(`Atualizando ${label}...`);
        try {
            await API.post(`/api/${kind}/bulk-update`, {
                project_id: App.getValidProjectId(), ids, updates
            });
            UI.showToast(`${label} atualizados com sucesso!`, 'success');
            this._closeModal(`modal-bulk-edit-${kind}`);
            if (kind === 'operations') {
                this.selectedOperationIds.clear();
                await this.loadOperations();
            } else {
                this.selectedLongTextIds.clear();
                await this.loadLongTexts();
            }
            this.updateBulkToolbar(kind);
            const checkAll = document.getElementById(`check-all-${kind}`);
            if (checkAll) checkAll.checked = false;
        } catch (err) {
            UI.showToast(`Erro na edição em massa: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    // ==========================================
    // INLINE CELL EDITING (double-click)
    // ==========================================

    /**
     * makeCellEditable — single-line inline edit for Operations fields
     * @param {HTMLElement} cell  - the <td> element
     * @param {number}      recId - operation id
     * @param {string}      field - field name to update
     * @param {string}      currentValue - current raw value
     * @param {string}      type  - 'op' or 'lt'
     * @param {string}      inputType - 'text' or 'number'
     * @param {number}      maxLen - maxlength attribute
     */
    makeCellEditable(cell, recId, field, currentValue, type, inputType = 'text', maxLen = 40) {
        if (cell.classList.contains('editing')) return;
        cell.classList.add('editing', 'cell-editing');
        const originalHTML = cell.innerHTML;
        const displayVal = (currentValue || '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');

        const step = inputType === 'number' && field === 'hours' ? '0.1' : '1';
        cell.innerHTML = `<input type="${inputType}" class="table-inline-input" value="${displayVal.replace(/"/g, '&quot;')}" maxlength="${maxLen}" step="${step}" style="width:100%;min-width:60px;">`;
        const input = cell.querySelector('input');
        if (!input) return;
        input.focus();
        if (input.select) input.select();

        let saved = false;
        const saveChange = async (skipSpell = false) => {
            if (saved) return;
            let newValue = input.value.trim();

            if (newValue === displayVal) {
                saved = true;
                cell.classList.remove('editing', 'cell-editing');
                cell.innerHTML = originalHTML;
                return;
            }

            if (!skipSpell && (field === 'short_text' || field === 'description' || field === 'text') && window.SpellChecker) {
                const analysis = SpellChecker.analyze(newValue);
                if (analysis.hasSuggestions) {
                    this.promptSpellReview(analysis, (finalText) => {
                        input.value = finalText;
                        saveChange(true);
                    });
                    return;
                }
            }

            saved = true;
            cell.classList.remove('editing', 'cell-editing');

            try {
                if (type === 'op') {
                    // Build a minimal patch — fetch current then overwrite
                    const current = this.currentOperations.find(o => o.id === recId) || {};
                    const patch = { ...current };
                    if (inputType === 'number') {
                        patch[field] = newValue === '' ? null : (field === 'hours' ? parseFloat(newValue) : parseInt(newValue));
                    } else {
                        patch[field] = newValue || null;
                    }
                    await API.put(`/api/operations/${recId}`, patch);
                    UI.showToast('Operação atualizada!', 'success', 1500);
                    await this.loadOperations();
                } else {
                    const current = this.currentLongTexts.find(t => t.id === recId) || {};
                    const patch = { ...current, text: newValue };
                    if (!recId || String(recId) === '0') {
                        const projectId = window.App ? App.getValidProjectId() : null;
                        const payload = {
                            project_id: projectId,
                            operation_id: current.operation_id,
                            text: newValue
                        };
                        await API.post('/api/long-texts', payload);
                    } else {
                        await API.put(`/api/long-texts/${recId}`, patch);
                    }
                    UI.showToast('Texto atualizado!', 'success', 1500);
                    await this.loadLongTexts({ silent: true });
                }
            } catch (err) {
                UI.showToast(`Erro ao salvar: ${err.message}`, 'error');
                cell.innerHTML = originalHTML;
            }
        };

        input.onblur = () => saveChange();
        input.onkeydown = (e) => {
            if (e.key === 'Enter') { e.preventDefault(); saveChange(); }
            else if (e.key === 'Escape') {
                saved = true;
                cell.classList.remove('editing', 'cell-editing');
                cell.innerHTML = originalHTML;
            }
        };
    },

    /**
     * makeTextareaEditable — multi-line inline edit for Long Text cells
     */
    makeTextareaEditable(cell, textId, type) {
        if (cell.classList.contains('editing')) return;
        cell.classList.add('editing', 'cell-editing');
        const originalHTML = cell.innerHTML;
        const rawText = cell.textContent.trim();

        // Render textarea first with overflow hidden so scrollHeight measures correctly
        cell.innerHTML = `<textarea class="table-inline-input" spellcheck="true" lang="pt-BR" style="width:100%;height:auto;overflow:hidden;resize:vertical;font-family:var(--font-sans);font-size:12px;line-height:1.6;box-sizing:border-box;padding:6px 8px;">${this.esc(rawText)}</textarea>`;
        const ta = cell.querySelector('textarea');
        if (!ta) return;

        // Auto-size: expand to fit full content (min 80px, no max)
        const autoResize = () => {
            ta.style.height = 'auto';
            ta.style.height = Math.max(80, ta.scrollHeight + 4) + 'px';
        };
        autoResize(); // initial size
        ta.addEventListener('input', autoResize); // grow as user types

        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);

        let saved = false;
        const saveChange = async (skipSpell = false) => {
            if (saved) return;
            const newValue = ta.value.trim();

            if (newValue === rawText) {
                saved = true;
                cell.classList.remove('editing', 'cell-editing');
                cell.innerHTML = originalHTML;
                return;
            }

            if (!skipSpell && window.SpellChecker) {
                const analysis = SpellChecker.analyze(newValue);
                if (analysis.hasSuggestions) {
                    this.promptSpellReview(analysis, (finalText) => {
                        ta.value = finalText;
                        saveChange(true);
                    });
                    return;
                }
            }

            saved = true;
            cell.classList.remove('editing', 'cell-editing');

            try {
                const current = this.currentLongTexts.find(t => t.id === textId) || {};
                const patch = { ...current, text: newValue };
                await API.put(`/api/long-texts/${textId}`, patch);
                UI.showToast('Texto atualizado!', 'success', 1500);
                await this.loadLongTexts();
            } catch (err) {
                UI.showToast(`Erro ao salvar: ${err.message}`, 'error');
                cell.innerHTML = originalHTML;
            }
        };

        // blur saves; Ctrl+Enter or just Enter on single line saves; Shift+Enter = newline; Escape = cancel
        ta.onblur = () => saveChange();
        ta.onkeydown = (e) => {
            if ((e.key === 'Enter' && e.ctrlKey) || (e.key === 'Enter' && !e.shiftKey && ta.value.indexOf('\n') === -1)) {
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

window.Operations = Operations;
