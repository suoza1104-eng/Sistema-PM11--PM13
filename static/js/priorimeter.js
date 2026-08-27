/**
 * Priorímetro SAP
 * - Uma linha por item do projeto
 * - Edição célula a célula e em massa
 * - Ctrl+C / Ctrl+V de critérios completos entre itens
 * - Alterações integradas ao histórico global (Ctrl+Z / Ctrl+Y)
 */
window.Priorimeter = {
    initialized: false,
    rows: [],
    fields: {},
    selected: new Set(),
    activeItemId: null,
    clipboardSourceId: null,
    dragSelecting: false,
    dragSelectValue: true,
    pointerDown: null,
    suppressRowClick: false,
    loading: false,

    fieldOrder: [
        'failure_probability', 'maintenance_impact', 'events_over_one',
        'asymmetric_lifting', 'multi_lifting', 'thermal_overload', 'tanks_gases',
        'leak_exposure', 'pressurized_systems', 'energized_electrical', 'confined_spaces',
        'height_over_2m', 'hot_metal', 'difficult_technical', 'hydraulic_jack'
    ],

    fieldLabels: {
        failure_probability: 'Probabilidade de Falha',
        maintenance_impact: 'Impacto da Manutenção',
        events_over_one: 'Quantidade de Eventos em 1 ano > 1?',
        asymmetric_lifting: 'Elevação/movimentação de carga assimétrica',
        multi_lifting: 'Elevação/movimentação com talha/ponte rolante/guindaste',
        thermal_overload: 'Ambiente com sobrecarga térmica',
        tanks_gases: 'Tanques/gases asfixiantes e/ou inflamáveis',
        leak_exposure: 'Risco de vazamento/exposição',
        pressurized_systems: 'Risco em sistemas pressurizados',
        energized_electrical: 'Sistemas elétricos energizados',
        confined_spaces: 'Espaços confinados',
        height_over_2m: 'Desnível superior a 2 metros',
        hot_metal: 'Risco de metal quente',
        difficult_technical: 'Conhecimentos técnicos específicos de difícil realização',
        hydraulic_jack: 'Macaco hidráulico: acionamento simultâneo e/ou fora do centro de gravidade'
    },

    probabilityOptions: [
        ['1', '1 — Muito Baixo (>30 dias)'],
        ['2', '2 — Baixa (16 a 30 dias)'],
        ['3', '3 — Média (8 a 15 dias)'],
        ['4', '4 — Alta (3 a 7 dias)'],
        ['5', '5 — Muito Alta (0 a 2 dias)']
    ],

    impactOptions: [
        ['1', '1 — Não influencia a linha'],
        ['2', '2 — Stand By não crítico'],
        ['3', '3 — Stand By crítico'],
        ['4', '4 — Parada de circuito/perda'],
        ['6', '6 — Parada de processo produtivo'],
        ['8', '8 — Parada de usina (Crítico 1)']
    ],

    yesNoOptions: [['S', 'S — Sim'], ['N', 'N — Não']],

    init() {
        if (this.initialized) return;
        this.initialized = true;

        document.getElementById('btn-priorimeter-filter')?.addEventListener('click', () => this.load());
        document.getElementById('btn-priorimeter-clear')?.addEventListener('click', () => {
            const search = document.getElementById('priorimeter-search');
            const status = document.getElementById('priorimeter-status-filter');
            if (search) search.value = '';
            if (status) status.value = 'ACTIVE';
            this.selected.clear();
            this.activeItemId = null;
            this.load();
        });
        document.getElementById('priorimeter-search')?.addEventListener('keydown', event => {
            if (event.key === 'Enter') this.load();
        });
        document.getElementById('priorimeter-status-filter')?.addEventListener('change', () => this.load());
        document.getElementById('priorimeter-select-all')?.addEventListener('change', event => this.toggleSelectAll(event.target.checked));
        document.getElementById('btn-priorimeter-clear-selection')?.addEventListener('click', () => this.clearSelection());
        document.getElementById('btn-priorimeter-bulk-edit')?.addEventListener('click', () => this.openBulkEdit());
        document.getElementById('btn-priorimeter-legend')?.addEventListener('click', () => this.openLegend());
        document.getElementById('btn-priorimeter-export')?.addEventListener('click', () => this.exportXlsx());

        document.addEventListener('keydown', event => this.handleKeyboard(event), true);
        document.addEventListener('mousemove', event => this.handlePointerMove(event), true);
        document.addEventListener('mouseup', () => this.finishPointerInteraction(), true);
    },

    projectId() {
        return Number(window.App?.getValidProjectId?.() || window.App?.currentProjectId || 0);
    },

    async load() {
        this.init();
        const projectId = this.projectId();
        if (!projectId || this.loading) return;
        this.loading = true;
        const tbody = document.getElementById('priorimeter-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="19" class="empty-state">Carregando priorímetro...</td></tr>';
        try {
            const result = await API.get('/api/priorimeter', {
                project_id: projectId,
                search: document.getElementById('priorimeter-search')?.value?.trim() || '',
                status: document.getElementById('priorimeter-status-filter')?.value ?? 'ACTIVE'
            });
            this.rows = Array.isArray(result?.rows) ? result.rows : [];
            this.fields = result?.fields || this.fieldLabels;
            const visibleIds = new Set(this.rows.map(row => Number(row.item_id)));
            this.selected = new Set([...this.selected].filter(id => visibleIds.has(Number(id))));
            if (this.activeItemId && !visibleIds.has(Number(this.activeItemId))) this.activeItemId = null;
            this.render();
        } catch (error) {
            if (tbody) tbody.innerHTML = `<tr><td colspan="19" class="empty-state txt-error">Erro ao carregar o priorímetro: ${UI.escapeHTML(error.message)}</td></tr>`;
            UI.showToast(`Erro ao carregar priorímetro: ${error.message}`, 'error');
        } finally {
            this.loading = false;
        }
    },

    render() {
        const tbody = document.getElementById('priorimeter-tbody');
        if (!tbody) return;
        if (!this.rows.length) {
            tbody.innerHTML = '<tr><td colspan="19" class="empty-state">Nenhum item encontrado para os filtros atuais.</td></tr>';
            this.updateProgress();
            this.updateSelectionBar();
            return;
        }
        tbody.innerHTML = this.rows.map(row => this.renderRow(row)).join('');
        this.bindRows();
        this.updateProgress();
        this.updateSelectionBar();
        const selectAll = document.getElementById('priorimeter-select-all');
        if (selectAll) {
            const sourceId = Number(this.clipboardSourceId || 0);
            const visible = this.rows.map(row => Number(row.item_id)).filter(id => id !== sourceId);
            selectAll.checked = visible.length > 0 && visible.every(id => this.selected.has(id));
            selectAll.indeterminate = !selectAll.checked && visible.some(id => this.selected.has(id));
        }
    },

    renderRow(row) {
        const id = Number(row.item_id);
        const active = id === Number(this.activeItemId) ? ' priorimeter-active-row' : '';
        const copied = id === Number(this.clipboardSourceId) ? ' priorimeter-copy-source' : '';
        const selected = this.selected.has(id) ? ' priorimeter-selected-row' : '';
        const checked = this.selected.has(id) ? ' checked' : '';
        const select = (field) => this.renderSelect(id, field, row[field]);
        const complete = Boolean(row.complete);
        const statusBadge = complete
            ? '<span class="pm-status-badge complete">Completo</span>'
            : `<span class="pm-status-badge pending">${Number(row.filled_fields || 0)}/${Number(row.total_fields || this.fieldOrder.length)}</span>`;
        return `
            <tr data-item-id="${id}" class="${active}${copied}${selected}" tabindex="0">
                <td class="pm-col-check"><input class="priorimeter-row-check" type="checkbox" data-item-id="${id}"${checked}></td>
                <td class="pm-sticky pm-col-id"><strong>${UI.escapeHTML(row.legacy_identifier ?? '')}</strong></td>
                <td class="pm-sticky pm-col-description" title="${UI.escapeHTML(row.item_description || '')}">${UI.escapeHTML(row.item_description || '')}</td>
                ${select('failure_probability')}
                ${select('maintenance_impact')}
                ${select('events_over_one')}
                ${select('asymmetric_lifting')}
                ${select('multi_lifting')}
                ${select('thermal_overload')}
                ${select('tanks_gases')}
                ${select('leak_exposure')}
                ${select('pressurized_systems')}
                ${select('energized_electrical')}
                ${select('confined_spaces')}
                ${select('height_over_2m')}
                ${select('hot_metal')}
                ${select('difficult_technical')}
                ${select('hydraulic_jack')}
                <td class="pm-col-completion">${statusBadge}</td>
            </tr>`;
    },

    renderSelect(itemId, field, currentValue) {
        const options = field === 'failure_probability'
            ? this.probabilityOptions
            : field === 'maintenance_impact'
                ? this.impactOptions
                : this.yesNoOptions;
        const current = currentValue == null ? '' : String(currentValue);
        const optionHtml = ['<option value="">—</option>'].concat(options.map(([value, label]) =>
            `<option value="${UI.escapeHTML(value)}"${String(value) === current ? ' selected' : ''}>${UI.escapeHTML(label)}</option>`
        )).join('');
        const kindClass = field === 'failure_probability' ? ' pm-field-prob'
            : field === 'maintenance_impact' ? ' pm-field-impact' : ' pm-field-yn';
        return `<td class="pm-edit-cell${kindClass}" title="${UI.escapeHTML(this.fieldLabels[field] || field)}">
            <select class="priorimeter-cell-select" data-item-id="${itemId}" data-field="${field}" data-old="${UI.escapeHTML(current)}">${optionHtml}</select>
        </td>`;
    },

    bindRows() {
        document.querySelectorAll('#priorimeter-tbody tr[data-item-id]').forEach(tr => {
            const itemId = Number(tr.dataset.itemId);

            tr.addEventListener('click', event => {
                if (event.target.closest('input, select, button, a')) return;
                if (this.suppressRowClick) { this.suppressRowClick = false; return; }
                this.setActiveRow(itemId);
                // Depois do Ctrl+C, cliques simples funcionam como seleção de
                // destinos (sem exigir Ctrl), no mesmo fluxo de uma planilha.
                if (this.clipboardSourceId && itemId !== Number(this.clipboardSourceId)) {
                    this.setTargetSelection(itemId, !this.selected.has(itemId));
                }
            });
            tr.addEventListener('focus', () => this.setActiveRow(itemId));

            // Prepara seleção por arraste sem marcar a linha imediatamente.
            // Um clique normal seleciona somente aquela linha. O modo de arraste
            // só começa depois que o ponteiro realmente se desloca alguns pixels,
            // evitando que um clique simples selecione duas linhas por acidente.
            tr.addEventListener('mousedown', event => {
                if (!this.clipboardSourceId || event.button !== 0 || event.target.closest('input, select, button, a')) return;
                if (itemId === Number(this.clipboardSourceId)) return;
                this.pointerDown = {
                    itemId,
                    x: Number(event.clientX || 0),
                    y: Number(event.clientY || 0),
                    started: false
                };
                this.dragSelecting = false;
            });
        });
        document.querySelectorAll('.priorimeter-row-check').forEach(box => {
            box.addEventListener('change', event => {
                const id = Number(event.target.dataset.itemId);
                if (id === Number(this.clipboardSourceId)) { event.target.checked = false; return; }
                this.setTargetSelection(id, event.target.checked);
                this.setActiveRow(id, false);
            });
        });
        document.querySelectorAll('.priorimeter-cell-select').forEach(select => {
            select.addEventListener('focus', () => this.setActiveRow(Number(select.dataset.itemId), false));
            select.addEventListener('change', event => this.saveCell(event.target));
        });
    },


    handlePointerMove(event) {
        if (!this.pointerDown || !this.clipboardSourceId) return;
        if ((event.buttons & 1) !== 1) {
            this.finishPointerInteraction();
            return;
        }

        const dx = Number(event.clientX || 0) - Number(this.pointerDown.x || 0);
        const dy = Number(event.clientY || 0) - Number(this.pointerDown.y || 0);
        const distance = Math.hypot(dx, dy);

        // Só vira arraste depois de um deslocamento real do mouse.
        // Isso elimina a dupla seleção causada pelo mousedown de um clique comum.
        if (!this.pointerDown.started && distance < 7) return;

        if (!this.pointerDown.started) {
            this.pointerDown.started = true;
            this.dragSelecting = true;
            this.suppressRowClick = true;
            const startId = Number(this.pointerDown.itemId);
            this.setActiveRow(startId);
            this.setTargetSelection(startId, true);
        }

        const tr = event.target instanceof Element
            ? event.target.closest('#priorimeter-tbody tr[data-item-id]')
            : null;
        if (!tr) return;
        const itemId = Number(tr.dataset.itemId || 0);
        if (!itemId || itemId === Number(this.clipboardSourceId)) return;
        event.preventDefault();
        this.setTargetSelection(itemId, true);
    },

    finishPointerInteraction() {
        const wasDragging = Boolean(this.pointerDown?.started || this.dragSelecting);
        this.pointerDown = null;
        this.dragSelecting = false;
        if (!wasDragging) {
            this.suppressRowClick = false;
            return;
        }
        // O click gerado imediatamente após o mouseup do arraste deve ser ignorado.
        // O timeout evita deixar o próximo clique real bloqueado caso o navegador
        // não dispare click no fim de um arraste mais longo.
        window.setTimeout(() => { this.suppressRowClick = false; }, 250);
    },

    setTargetSelection(itemId, selected) {
        const id = Number(itemId);
        if (!id || id === Number(this.clipboardSourceId)) return;
        if (selected) this.selected.add(id); else this.selected.delete(id);
        const tr = document.querySelector(`#priorimeter-tbody tr[data-item-id="${id}"]`);
        tr?.classList.toggle('priorimeter-selected-row', selected);
        const box = tr?.querySelector('.priorimeter-row-check');
        if (box) box.checked = selected;
        this.updateSelectionBar();
        this.updateSelectAllState();
    },
    setActiveRow(itemId, repaint = true) {
        this.activeItemId = Number(itemId);
        if (repaint) {
            document.querySelectorAll('#priorimeter-tbody tr').forEach(tr => {
                tr.classList.toggle('priorimeter-active-row', Number(tr.dataset.itemId) === this.activeItemId);
            });
        }
    },

    async saveCell(select) {
        const itemId = Number(select.dataset.itemId);
        const field = select.dataset.field;
        const value = select.value;
        const oldValue = select.dataset.old ?? '';
        select.disabled = true;
        try {
            const result = await API.put(`/api/priorimeter/${itemId}`, {
                project_id: this.projectId(),
                updates: { [field]: value }
            });
            if (result?.row) this.replaceRow(result.row);
            select.dataset.old = value;
            await window.App?.refreshHistoryStatus?.({ silent: true });
        } catch (error) {
            select.value = oldValue;
            UI.showToast(`Erro ao salvar priorímetro: ${error.message}`, 'error');
        } finally {
            select.disabled = false;
            this.updateProgress();
            this.refreshRowStatus(itemId);
        }
    },

    replaceRow(newRow) {
        const idx = this.rows.findIndex(row => Number(row.item_id) === Number(newRow.item_id));
        if (idx >= 0) this.rows[idx] = newRow;
    },

    refreshRowStatus(itemId) {
        const row = this.rows.find(r => Number(r.item_id) === Number(itemId));
        const tr = document.querySelector(`#priorimeter-tbody tr[data-item-id="${Number(itemId)}"]`);
        if (!row || !tr) return;
        const statusCell = tr.querySelector('.pm-col-completion');
        if (!statusCell) return;
        statusCell.innerHTML = row.complete
            ? '<span class="pm-status-badge complete">Completo</span>'
            : `<span class="pm-status-badge pending">${Number(row.filled_fields || 0)}/${Number(row.total_fields || this.fieldOrder.length)}</span>`;
    },

    updateProgress() {
        const total = this.rows.length;
        const completed = this.rows.filter(row => row.complete).length;
        const pct = total ? Math.round(completed * 100 / total) : 0;
        const text = document.getElementById('priorimeter-progress-text');
        const bar = document.getElementById('priorimeter-progress-bar');
        if (text) text.textContent = `${completed} / ${total} (${pct}%)`;
        if (bar) bar.style.width = `${pct}%`;
    },

    updateSelectionBar() {
        const count = this.selected.size;
        document.getElementById('priorimeter-bulk-bar')?.classList.toggle('hidden', count === 0);
        const label = document.getElementById('priorimeter-selected-count');
        if (label) label.textContent = String(count);
    },

    updateSelectAllState() {
        const control = document.getElementById('priorimeter-select-all');
        if (!control) return;
        const sourceId = Number(this.clipboardSourceId || 0);
        const visible = this.rows.map(row => Number(row.item_id)).filter(id => id !== sourceId);
        control.checked = visible.length > 0 && visible.every(id => this.selected.has(id));
        control.indeterminate = !control.checked && visible.some(id => this.selected.has(id));
    },

    toggleSelectAll(checked) {
        this.rows.forEach(row => {
            const id = Number(row.item_id);
            if (id === Number(this.clipboardSourceId)) return;
            if (checked) this.selected.add(id); else this.selected.delete(id);
        });
        document.querySelectorAll('#priorimeter-tbody tr[data-item-id]').forEach(tr => {
            const id = Number(tr.dataset.itemId);
            const on = checked && id !== Number(this.clipboardSourceId);
            tr.classList.toggle('priorimeter-selected-row', on);
            const box = tr.querySelector('.priorimeter-row-check');
            if (box) box.checked = on;
        });
        this.updateSelectionBar();
        this.updateSelectAllState();
    },

    clearSelection() {
        this.selected.clear();
        document.querySelectorAll('.priorimeter-row-check').forEach(box => { box.checked = false; });
        document.querySelectorAll('#priorimeter-tbody tr').forEach(tr => tr.classList.remove('priorimeter-selected-row'));
        this.updateSelectionBar();
        this.updateSelectAllState();
    },

    handleKeyboard(event) {
        if ((window.location.hash || '').split('?')[0] !== '#priorimeter') return;
        const target = event.target;
        if (target instanceof Element && target.closest('input, textarea, select, [contenteditable="true"]')) return;
        if (event.key === 'Escape' && this.clipboardSourceId) {
            event.preventDefault();
            this.clearClipboard();
            return;
        }
        if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
        const key = String(event.key || '').toLowerCase();
        if (key === 'c') {
            event.preventDefault();
            event.stopImmediatePropagation();
            this.copyActiveRow();
        } else if (key === 'v') {
            event.preventDefault();
            event.stopImmediatePropagation();
            this.pasteClipboard();
        }
        // Ctrl+Z/Ctrl+Y intentionally remain with App's global history handler.
    },

    copyActiveRow() {
        let sourceId = Number(this.activeItemId || 0);
        if (!sourceId && this.selected.size === 1) sourceId = Number([...this.selected][0]);
        if (!sourceId) {
            UI.showToast('Clique em uma linha antes de usar Ctrl+C.', 'warning');
            return;
        }
        this.clipboardSourceId = sourceId;
        // Começa uma nova seleção de destinos. A origem permanece marcada pelo
        // tracejado e nunca é incluída na colagem.
        this.clearSelection();
        document.querySelectorAll('#priorimeter-tbody tr').forEach(tr => {
            tr.classList.toggle('priorimeter-copy-source', Number(tr.dataset.itemId) === sourceId);
        });
        const source = this.rows.find(row => Number(row.item_id) === sourceId);
        UI.showToast(`Linha ${source?.legacy_identifier || sourceId} copiada. Clique ou arraste sobre os destinos e pressione Ctrl+V.`, 'success');
    },

    clearClipboard() {
        this.clipboardSourceId = null;
        this.dragSelecting = false;
        this.pointerDown = null;
        this.suppressRowClick = false;
        document.querySelectorAll('.priorimeter-copy-source').forEach(el => el.classList.remove('priorimeter-copy-source'));
        UI.showToast('Cópia do priorímetro cancelada.', 'warning', 2200);
    },

    async pasteClipboard() {
        const sourceId = Number(this.clipboardSourceId || 0);
        if (!sourceId) {
            UI.showToast('Use Ctrl+C em uma linha antes de colar.', 'warning');
            return;
        }
        let targetIds = this.selected.size ? [...this.selected].map(Number) : (this.activeItemId ? [Number(this.activeItemId)] : []);
        if (targetIds.length > 1) targetIds = targetIds.filter(id => id !== sourceId);
        if (!targetIds.length || (targetIds.length === 1 && targetIds[0] === sourceId)) {
            UI.showToast('Selecione uma linha de destino diferente da origem.', 'warning');
            return;
        }
        UI.showLoader(`Colando critérios em ${targetIds.length} item(ns)...`);
        try {
            const result = await API.post('/api/priorimeter/copy', {
                project_id: this.projectId(),
                source_item_id: sourceId,
                target_item_ids: targetIds
            });
            UI.showToast(result?.message || 'Linha do priorímetro colada com sucesso.', 'success');
            await window.App?.refreshHistoryStatus?.({ silent: true });
            await this.load();
        } catch (error) {
            UI.showToast(`Erro ao colar priorímetro: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    ensureModal(id, html) {
        let modal = document.getElementById(id);
        if (!modal) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = html.trim();
            modal = wrapper.firstElementChild;
            document.body.appendChild(modal);
        }
        return modal;
    },

    openBulkEdit() {
        if (!this.selected.size) {
            UI.showToast('Selecione pelo menos um item.', 'warning');
            return;
        }
        const modal = this.ensureModal('modal-priorimeter-bulk', `
            <div id="modal-priorimeter-bulk" class="modal-overlay hidden">
                <div class="modal" style="max-width:560px;">
                    <div class="modal-header"><h2>Editar Priorímetro em Massa</h2><button class="modal-close btn-icon" data-pm-close>✕</button></div>
                    <div class="modal-body">
                        <p style="margin-bottom:14px;color:var(--text-muted);"><strong id="pm-bulk-count">0</strong> item(ns) selecionado(s). Escolha o critério e o valor que será aplicado a todos.</p>
                        <div class="form-group"><label>Critério</label><select id="pm-bulk-field"></select></div>
                        <div class="form-group mt-15"><label>Valor</label><select id="pm-bulk-value"></select></div>
                    </div>
                    <div class="modal-footer"><button class="btn btn-outline" data-pm-close>Cancelar</button><button class="btn btn-primary" id="pm-bulk-apply">Aplicar em Massa</button></div>
                </div>
            </div>`);
        modal.querySelectorAll('[data-pm-close]').forEach(btn => btn.onclick = () => modal.classList.add('hidden'));
        const fieldSelect = modal.querySelector('#pm-bulk-field');
        fieldSelect.innerHTML = this.fieldOrder.map(field => `<option value="${field}">${UI.escapeHTML(this.fieldLabels[field])}</option>`).join('');
        fieldSelect.onchange = () => this.populateBulkValue(fieldSelect.value);
        modal.querySelector('#pm-bulk-count').textContent = String(this.selected.size);
        modal.querySelector('#pm-bulk-apply').onclick = () => this.applyBulkEdit();
        this.populateBulkValue(fieldSelect.value);
        modal.classList.remove('hidden');
    },

    populateBulkValue(field) {
        const select = document.getElementById('pm-bulk-value');
        if (!select) return;
        const options = field === 'failure_probability'
            ? this.probabilityOptions
            : field === 'maintenance_impact' ? this.impactOptions : this.yesNoOptions;
        select.innerHTML = '<option value="">— Limpar valor —</option>' + options.map(([value, label]) =>
            `<option value="${UI.escapeHTML(value)}">${UI.escapeHTML(label)}</option>`
        ).join('');
    },

    async applyBulkEdit() {
        const modal = document.getElementById('modal-priorimeter-bulk');
        const field = document.getElementById('pm-bulk-field')?.value;
        const value = document.getElementById('pm-bulk-value')?.value ?? '';
        if (!field || !this.selected.size) return;
        UI.showLoader('Atualizando priorímetro em massa...');
        try {
            const result = await API.post('/api/priorimeter/bulk-update', {
                project_id: this.projectId(),
                item_ids: [...this.selected],
                updates: { [field]: value }
            });
            modal?.classList.add('hidden');
            UI.showToast(result?.message || 'Priorímetro atualizado em massa.', 'success');
            await window.App?.refreshHistoryStatus?.({ silent: true });
            await this.load();
        } catch (error) {
            UI.showToast(`Erro na edição em massa: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    openLegend() {
        const modal = this.ensureModal('modal-priorimeter-legend', `
            <div id="modal-priorimeter-legend" class="modal-overlay hidden">
                <div class="modal modal-lg" style="max-width:980px;">
                    <div class="modal-header"><h2>Legenda do Priorímetro</h2><button class="modal-close btn-icon" data-pm-legend-close>✕</button></div>
                    <div class="modal-body priorimeter-legend-body">
                        <div class="pm-legend-grid">
                            <div class="pm-legend-card"><h3>Probabilidade de Falha</h3>
                                <div><b>1</b> Muito Baixo — acima de 30 dias</div><div><b>2</b> Baixa — 16 a 30 dias</div><div><b>3</b> Média — 8 a 15 dias</div><div><b>4</b> Alta — 3 a 7 dias</div><div><b>5</b> Muito Alta — 0 a 2 dias</div>
                            </div>
                            <div class="pm-legend-card"><h3>Impacto da Manutenção</h3>
                                <div><b>1</b> Não influencia na linha de produção</div><div><b>2</b> Equipamento Stand By não crítico</div><div><b>3</b> Equipamento Stand By crítico</div><div><b>4</b> Parada de circuito e/ou perda</div><div><b>6</b> Parada de processo produtivo</div><div><b>8</b> Parada de usina (Crítico 1)</div>
                            </div>
                        </div>
                        <div class="pm-legend-card mt-15"><h3>Critérios S/N</h3><p><b>S = Sim</b> • <b>N = Não</b></p><ul id="pm-factor-list"></ul></div>
                        <div class="pm-info-note">A planilha de referência não contém fórmula de nota. Esta tela preserva e organiza os critérios; nenhum cálculo de score foi inventado.</div>
                    </div>
                    <div class="modal-footer"><button class="btn btn-primary" data-pm-legend-close>Fechar</button></div>
                </div>
            </div>`);
        modal.querySelectorAll('[data-pm-legend-close]').forEach(btn => btn.onclick = () => modal.classList.add('hidden'));
        const list = modal.querySelector('#pm-factor-list');
        if (list) list.innerHTML = this.fieldOrder.slice(2).map(field => `<li>${UI.escapeHTML(this.fieldLabels[field])}</li>`).join('');
        modal.classList.remove('hidden');
    },

    exportXlsx() {
        const projectId = this.projectId();
        if (!projectId) return;
        const params = new URLSearchParams({ project_id: String(projectId) });
        const search = document.getElementById('priorimeter-search')?.value?.trim();
        const status = document.getElementById('priorimeter-status-filter')?.value;
        if (search) params.set('search', search);
        if (status) params.set('status', status);
        window.location.href = `/api/priorimeter/export?${params.toString()}`;
    }
};
