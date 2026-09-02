/**
 * StandardsManager.js - Módulo de Gerenciamento da Biblioteca de Padrões Compartilhados.
 * Gerencia Textos Longos Padrão, Modelos de Itens com Operações SAP e Blocos Padrão Reutilizáveis.
 */

window.StandardsManager = {
    standardLongTexts: [],
    standardItems: [],
    standardBlocks: [],

    async init() {
        await this.loadAll();
    },

    async loadAll() {
        await Promise.all([
            this.loadLongTexts(),
            this.loadItems(),
            this.loadBlocks()
        ]);
    },

    async loadLongTexts() {
        try {
            const list = await API.get('/api/standards/long-texts');
            this.standardLongTexts = Array.isArray(list) ? list : (list?.long_texts || list?.standards || []);
            this.populateLongTextSelectors();
            this.renderViewTables();
        } catch (err) {
            console.warn('Erro ao carregar textos padrão:', err);
        }
    },

    async loadItems() {
        try {
            const list = await API.get('/api/standards/items');
            this.standardItems = list || [];
            this.populateItemSelectors();
            this.renderViewTables();
        } catch (err) {
            console.warn('Erro ao carregar itens padrão:', err);
        }
    },

    async loadBlocks() {
        try {
            const list = await API.get('/api/long-text-blocks');
            this.standardBlocks = list || [];
            this.renderViewTables();
        } catch (err) {
            console.warn('Erro ao carregar blocos padrão:', err);
        }
    },

    switchViewTab(tabName) {
        document.querySelectorAll('.standards-view-tab').forEach(btn => {
            const isActive = btn.id === `tab-btn-${tabName}`;
            btn.classList.toggle('active', isActive);
        });
        document.querySelectorAll('.standards-view-content').forEach(content => {
            content.classList.toggle('hidden', content.id !== `view-tab-${tabName}`);
        });
        this.renderViewTables();
    },

    getCategoryBadgeHTML(catName) {
        const cat = String(catName || 'GERAL').trim().toUpperCase();
        const slug = cat.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
        const validClass = ['alinhamento', 'motores', 'redutores', 'valvulas', 'bombas', 'geral'].includes(slug) ? `std-badge-cat-${slug}` : 'std-badge-cat-geral';
        return `<span class="std-badge-cat ${validClass}">${UI.escapeHTML(cat)}</span>`;
    },

    populateCategoryFilters() {
        const catSet = new Set();
        this.standardLongTexts.forEach(t => { if (t.category) catSet.add(t.category.trim().toUpperCase()); });
        this.standardItems.forEach(i => { if (i.category) catSet.add(i.category.trim().toUpperCase()); });
        this.standardBlocks.forEach(b => { if (b.category) catSet.add(b.category.trim().toUpperCase()); });

        const categories = Array.from(catSet).sort();

        ['filter-std-lt-cat', 'filter-std-item-cat', 'filter-std-block-cat'].forEach(selectId => {
            const select = document.getElementById(selectId);
            if (!select) return;
            const currentVal = select.value;
            let optionsHtml = '<option value="">Todas as Categorias</option>';
            categories.forEach(cat => {
                const selected = cat === currentVal ? 'selected' : '';
                optionsHtml += `<option value="${UI.escapeHTML(cat)}" ${selected}>${UI.escapeHTML(cat)}</option>`;
            });
            select.innerHTML = optionsHtml;
        });
    },

    renderViewTables() {
        this.populateCategoryFilters();
        this.renderLongTextsTable();
        this.renderItemsTable();
        this.renderBlocksTable();
        
        const countLt = document.getElementById('count-std-long-texts');
        if (countLt) countLt.textContent = this.standardLongTexts.length;
        const countItem = document.getElementById('count-std-items');
        if (countItem) countItem.textContent = this.standardItems.length;
        const countBlock = document.getElementById('count-std-blocks');
        if (countBlock) countBlock.textContent = this.standardBlocks.length;

        // Update KPIs
        const kpiLt = document.getElementById('std-kpi-long-texts');
        if (kpiLt) kpiLt.textContent = this.standardLongTexts.length;

        const kpiItem = document.getElementById('std-kpi-items');
        if (kpiItem) kpiItem.textContent = this.standardItems.length;

        const catSet = new Set();
        this.standardLongTexts.forEach(t => { if (t.category) catSet.add(t.category.trim().toUpperCase()); });
        this.standardItems.forEach(i => { if (i.category) catSet.add(i.category.trim().toUpperCase()); });
        this.standardBlocks.forEach(b => { if (b.category) catSet.add(b.category.trim().toUpperCase()); });
        const kpiCat = document.getElementById('std-kpi-categories');
        if (kpiCat) kpiCat.textContent = catSet.size;

        const totalOps = this.standardItems.reduce((acc, item) => acc + (parseInt(item.operations_count) || 0), 0);
        const kpiOps = document.getElementById('std-kpi-operations');
        if (kpiOps) kpiOps.textContent = totalOps;
    },

    renderLongTextsTable(filteredList = null) {
        const list = filteredList || this.standardLongTexts;
        const tbodySection = document.getElementById('tbody-std-long-texts');
        const tbodyModal = document.getElementById('standards-long-texts-tbody');

        const html = list.length === 0 
            ? '<tr><td colspan="4" class="text-center text-muted" style="padding: 24px; font-size: 13px;">Nenhum texto longo padrão encontrado na biblioteca.</td></tr>'
            : list.map(t => `
                <tr>
                    <td style="font-weight:600; color:#1E293B;">${UI.escapeHTML(t.title)}</td>
                    <td class="text-center">${this.getCategoryBadgeHTML(t.category)}</td>
                    <td>
                        <div class="standards-procedure-card" title="Procedimento técnico em texto longo">${UI.escapeHTML(t.text)}</div>
                    </td>
                    <td class="text-center">
                        <div class="standards-actions-row" style="display:flex; gap:4px; justify-content:center; flex-wrap:wrap;">
                            <button class="btn btn-xs btn-outline" title="Clonar este modelo" onclick="StandardsManager.cloneLongText(${t.id})">📋 Clonar</button>
                            <button class="btn btn-xs btn-outline" title="Editar modelo" onclick="StandardsManager.openEditLongTextModal(${t.id})">✏️ Editar</button>
                            <button class="btn btn-xs btn-danger" title="Excluir modelo" onclick="StandardsManager.deleteLongText(${t.id})">🗑️ Excluir</button>
                        </div>
                    </td>
                </tr>
            `).join('');

        if (tbodySection) tbodySection.innerHTML = html;
        if (tbodyModal) tbodyModal.innerHTML = html;
    },

    renderItemsTable(filteredList = null) {
        const list = filteredList || this.standardItems;
        const tbodySection = document.getElementById('tbody-std-items');
        const tbodyModal = document.getElementById('standards-items-tbody');

        const html = list.length === 0
            ? '<tr><td colspan="5" class="text-center text-muted" style="padding: 24px; font-size: 13px;">Nenhum modelo de item padrão cadastrado na biblioteca.</td></tr>'
            : list.map(item => `
                <tr>
                    <td style="font-weight:600; color:#1E293B;">${UI.escapeHTML(item.title)}</td>
                    <td class="text-center">${this.getCategoryBadgeHTML(item.category)}</td>
                    <td style="font-weight:500; color:#334155;">${UI.escapeHTML(item.description)}</td>
                    <td class="text-center"><span class="badge badge-outline" style="color:#0F766E; border-color:#99F6E4; font-weight:700;">${item.operations_count || 0} op. SAP</span></td>
                    <td class="text-center">
                        <div class="standards-actions-row" style="display:flex; gap:4px; justify-content:center; flex-wrap:wrap;">
                            <button class="btn btn-xs btn-outline" title="Visualizar detalhes do modelo" onclick="StandardsManager.openViewItemModal(${item.id})">👁️ Ver</button>
                            <button class="btn btn-xs btn-outline" title="Editar modelo de item" onclick="StandardsManager.openEditItemModal(${item.id})">✏️ Editar</button>
                            <button class="btn btn-xs btn-outline" title="Duplicar modelo" onclick="StandardsManager.duplicateItem(${item.id})">📋 Clonar</button>
                            <button class="btn btn-xs btn-success" title="Instanciar modelo no projeto ativo" onclick="StandardsManager.instantiateItemInProject(${item.id})">⚡ Usar</button>
                            <button class="btn btn-xs btn-danger" title="Excluir modelo" onclick="StandardsManager.deleteItem(${item.id})">🗑️ Excluir</button>
                        </div>
                    </td>
                </tr>
            `).join('');

        if (tbodySection) tbodySection.innerHTML = html;
        if (tbodyModal) tbodyModal.innerHTML = html;
    },

    renderBlocksTable(filteredList = null) {
        const list = filteredList || this.standardBlocks;
        const tbody = document.getElementById('tbody-std-blocks');
        if (!tbody) return;

        const html = list.length === 0
            ? '<tr><td colspan="5" class="text-center text-muted" style="padding: 24px; font-size: 13px;">Nenhum bloco padrão de texto longo cadastrado na biblioteca.</td></tr>'
            : list.map(b => `
                <tr>
                    <td style="font-weight:600; color:#1E293B;">${UI.escapeHTML(b.title)}</td>
                    <td class="text-center">${this.getCategoryBadgeHTML(b.category)}</td>
                    <td style="font-size:12px; color:#64748B;">${UI.escapeHTML(b.tags || '-')}</td>
                    <td>
                        <div class="standards-procedure-card" title="Prévia do bloco">${UI.escapeHTML(b.text || '')}</div>
                    </td>
                    <td class="text-center">
                        <div class="standards-actions-row" style="display:flex; gap:4px; justify-content:center; flex-wrap:wrap;">
                            <button class="btn btn-xs btn-outline" title="Editar bloco padrão" onclick="StandardsManager.openEditBlockModal(${b.id})">✏️ Editar</button>
                            <button class="btn btn-xs btn-outline" title="Duplicar bloco" onclick="StandardsManager.duplicateBlock(${b.id})">📋 Clonar</button>
                            <button class="btn btn-xs btn-danger" title="Excluir bloco" onclick="StandardsManager.deleteBlock(${b.id})">🗑️ Excluir</button>
                        </div>
                    </td>
                </tr>
            `).join('');

        tbody.innerHTML = html;
    },

    filterLongTexts() {
        const queryEl = document.getElementById('filter-std-lt-search');
        const catEl = document.getElementById('filter-std-lt-cat');
        const q = String(queryEl ? queryEl.value : '').toLowerCase().trim();
        const catFilter = String(catEl ? catEl.value : '').toUpperCase().trim();

        const filtered = this.standardLongTexts.filter(t => {
            const matchesQuery = !q || (
                String(t.title || '').toLowerCase().includes(q) ||
                String(t.category || '').toLowerCase().includes(q) ||
                String(t.text || '').toLowerCase().includes(q)
            );
            const matchesCat = !catFilter || String(t.category || '').toUpperCase().trim() === catFilter;
            return matchesQuery && matchesCat;
        });

        this.renderLongTextsTable(filtered);
    },

    filterItems() {
        const queryEl = document.getElementById('filter-std-item-search');
        const catEl = document.getElementById('filter-std-item-cat');
        const q = String(queryEl ? queryEl.value : '').toLowerCase().trim();
        const catFilter = String(catEl ? catEl.value : '').toUpperCase().trim();

        const filtered = this.standardItems.filter(item => {
            const matchesQuery = !q || (
                String(item.title || '').toLowerCase().includes(q) ||
                String(item.category || '').toLowerCase().includes(q) ||
                String(item.description || '').toLowerCase().includes(q)
            );
            const matchesCat = !catFilter || String(item.category || '').toUpperCase().trim() === catFilter;
            return matchesQuery && matchesCat;
        });

        this.renderItemsTable(filtered);
    },

    filterBlocks() {
        const queryEl = document.getElementById('filter-std-block-search');
        const catEl = document.getElementById('filter-std-block-cat');
        const q = String(queryEl ? queryEl.value : '').toLowerCase().trim();
        const catFilter = String(catEl ? catEl.value : '').toUpperCase().trim();

        const filtered = this.standardBlocks.filter(b => {
            const matchesQuery = !q || (
                String(b.title || '').toLowerCase().includes(q) ||
                String(b.category || '').toLowerCase().includes(q) ||
                String(b.tags || '').toLowerCase().includes(q) ||
                String(b.text || '').toLowerCase().includes(q)
            );
            const matchesCat = !catFilter || String(b.category || '').toUpperCase().trim() === catFilter;
            return matchesQuery && matchesCat;
        });

        this.renderBlocksTable(filtered);
    },

    // --------------------------------------------------
    // VIEW / EDIT / DUPLICATE ITEM MODELS
    // --------------------------------------------------

    async openViewItemModal(standardId) {
        try {
            UI.showLoader('Carregando detalhes do modelo...');
            const detail = await API.get(`/api/standards/items/${standardId}`);
            if (!detail) return UI.showToast('Modelo não encontrado.', 'error');

            const opsHtml = (detail.operations || []).length === 0
                ? '<p class="text-muted">Nenhuma operação SAP cadastrada neste modelo.</p>'
                : (detail.operations || []).map(op => {
                    const ltText = op.long_text || (op.long_texts && op.long_texts[0] ? op.long_texts[0].text : '') || '';
                    return `
                        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:12px; margin-bottom:10px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                                <strong style="color:#0F172A; font-size:13px;">Op. ${UI.escapeHTML(op.operation_code || '0010')} | CT: ${UI.escapeHTML(op.work_center || '-')}</strong>
                                <span class="badge badge-outline" style="font-size:11px;">👥 ${op.headcount || 1} H. • ⏱️ ${op.hours || 1}h (${op.unit || 'H'})</span>
                            </div>
                            <div style="font-size:13px; font-weight:600; color:#334155; margin-bottom:6px;">${UI.escapeHTML(op.short_text || '')}</div>
                            ${ltText ? `<pre style="background:#FFFFFF; border:1px solid #CBD5E1; padding:8px 10px; border-radius:6px; font-size:11.5px; color:#475569; white-space:pre-wrap; font-family:inherit; margin:0;">${UI.escapeHTML(ltText)}</pre>` : '<small class="muted">Sem texto longo</small>'}
                        </div>
                    `;
                }).join('');

            const modalHtml = `
                <div id="modal-view-std-item" class="modal-overlay" style="z-index:2500">
                    <div class="modal modal-lg">
                        <div class="modal-header">
                            <div>
                                <h2>📦 Modelo: ${UI.escapeHTML(detail.title)}</h2>
                                <small>Categoria: <b>${UI.escapeHTML(detail.category || 'GERAL')}</b></small>
                            </div>
                            <button class="btn-icon" onclick="document.getElementById('modal-view-std-item').remove()">✕</button>
                        </div>
                        <div class="modal-body">
                            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:16px; background:#F1F5F9; padding:12px; border-radius:8px;">
                                <div><strong>Descrição:</strong> ${UI.escapeHTML(detail.description || '-')}</div>
                                <div><strong>Equipamento:</strong> ${UI.escapeHTML(detail.equipment_code || '-')}</div>
                                <div><strong>GPM:</strong> ${UI.escapeHTML(detail.gpm || '-')}</div>
                                <div><strong>Centro de Trabalho:</strong> ${UI.escapeHTML(detail.work_center || '-')}</div>
                            </div>
                            <h3 style="font-size:14px; margin-bottom:10px;">Operações SAP (${(detail.operations || []).length}):</h3>
                            <div style="max-height:360px; overflow-y:auto; padding-right:4px;">
                                ${opsHtml}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-outline" onclick="document.getElementById('modal-view-std-item').remove()">Fechar</button>
                            <button class="btn btn-primary" onclick="document.getElementById('modal-view-std-item').remove(); StandardsManager.openEditItemModal(${detail.id});">✏️ Editar Modelo</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        } catch (e) {
            UI.showToast(`Erro ao carregar modelo: ${e.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    openOperationLongTextEditor(triggerEl) {
        const row = triggerEl.closest('.edit-std-op-row');
        if (!row) return;

        const opCode = row.querySelector('.op-code')?.value || '0010';
        const shortText = row.querySelector('.op-short')?.value || '';
        
        const currentText = row.dataset.ltText || row.querySelector('.op-lt')?.value || '';
        const currentMode = row.dataset.ltMode || 'FREE';
        const currentJson = row.dataset.ltJson || '';
        const currentSource = row.dataset.ltSource || '';

        const modal = document.getElementById('modal-long-text');
        if (!modal) return;

        modal.style.zIndex = '2600';

        const titleEl = document.getElementById('modal-long-text-title');
        if (titleEl) titleEl.textContent = `Editar Texto Longo / Blocos — Op. ${opCode} ${shortText ? '(' + shortText + ')' : ''}`;

        document.querySelectorAll('#modal-long-text .lt-context-panel').forEach(p => p.style.display = 'none');

        if (window.LongTextEditor) {
            LongTextEditor.loadRecord({
                text: currentText,
                structure_mode: currentMode,
                structure_json: currentJson,
                source_text_original: currentSource
            }, true);
        }

        const saveBtn = document.getElementById('btn-save-long-text');
        const savePatternBtn = document.getElementById('btn-save-pattern-long-text');
        
        if (saveBtn) {
            saveBtn.onclick = () => {
                const payload = window.LongTextEditor ? LongTextEditor.getPayload() : { text: document.getElementById('form-lt-text')?.value || '' };
                
                row.dataset.ltText = payload.text || '';
                row.dataset.ltMode = payload.structure_mode || 'FREE';
                row.dataset.ltJson = typeof payload.structure_json === 'object' ? JSON.stringify(payload.structure_json) : (payload.structure_json || '');
                row.dataset.ltSource = payload.source_text_original || '';
                
                const textarea = row.querySelector('.op-lt');
                if (textarea) textarea.value = payload.text || '';
                
                const badge = row.querySelector('.op-lt-badge');
                if (badge) {
                    const hasLt = Boolean((payload.text || '').trim());
                    badge.style.display = hasLt ? 'inline-block' : 'none';
                }

                modal.classList.add('hidden');
                modal.style.zIndex = '2050';
                document.querySelectorAll('#modal-long-text .lt-context-panel').forEach(p => p.style.display = '');
                UI.showToast('Texto longo gravado na operação do modelo!', 'success');
            };
        }

        if (savePatternBtn) {
            savePatternBtn.onclick = async () => {
                const title = prompt('Digite um título para o Texto Padrão (Modelo):', shortText || `Texto Op ${opCode}`);
                if (!title || !title.trim()) return;
                const category = prompt('Digite a Categoria:', 'GERAL') || 'GERAL';
                const payload = window.LongTextEditor ? LongTextEditor.getPayload() : { text: document.getElementById('form-lt-text')?.value || '' };
                
                await StandardsManager.saveCurrentLongTextAsStandard(title.trim(), category.trim(), payload.text, payload);
            };
        }

        modal.classList.remove('hidden');
    },

    async openEditItemModal(standardId) {
        try {
            UI.showLoader('Carregando modelo para edição...');
            const detail = await API.get(`/api/standards/items/${standardId}`);
            if (!detail) return UI.showToast('Modelo não encontrado.', 'error');

            const opsHtml = (detail.operations || []).map((op, idx) => {
                const ltText = op.long_text || (op.long_texts && op.long_texts[0] ? op.long_texts[0].text : '') || '';
                const ltMode = op.long_text_structure_mode || (op.long_texts && op.long_texts[0] ? op.long_texts[0].structure_mode : 'FREE') || 'FREE';
                const ltJson = op.long_text_structure_json || (op.long_texts && op.long_texts[0] ? op.long_texts[0].structure_json : '') || '';
                const ltSource = op.long_text_source_original || (op.long_texts && op.long_texts[0] ? op.long_texts[0].source_text_original : '') || '';
                const hasLt = Boolean(ltText.trim());
                const hcVal = (op.headcount !== null && op.headcount !== undefined && op.headcount !== '') ? op.headcount : '';
                const hVal = (op.hours !== null && op.hours !== undefined && op.hours !== '') ? op.hours : '';

                return `
                    <div class="edit-std-op-row" style="background:#F8FAFC; border:1px solid #CBD5E1; padding:12px; border-radius:8px;"
                         data-lt-text="${UI.escapeHTML(ltText)}"
                         data-lt-mode="${UI.escapeHTML(ltMode)}"
                         data-lt-json="${UI.escapeHTML(typeof ltJson === 'object' ? JSON.stringify(ltJson) : ltJson)}"
                         data-lt-source="${UI.escapeHTML(ltSource)}">
                        <div style="display:grid; grid-template-columns: 72px 82px 92px 1fr 64px 64px 30px; gap:8px; align-items:center; margin-bottom:8px;">
                            <input type="text" class="op-code" value="${UI.escapeHTML(op.operation_code || '0010')}" placeholder="Op" style="padding:6px; font-weight:700;">
                            <input type="text" class="op-subcode" value="${UI.escapeHTML(op.suboperation_code || '')}" placeholder="Subop." style="padding:6px; font-weight:700;">
                            <input type="text" class="op-wc" value="${UI.escapeHTML(op.work_center || '')}" placeholder="CT" style="padding:6px;">
                            <input type="text" class="op-short" value="${UI.escapeHTML(op.short_text || '')}" placeholder="Texto breve da operação" style="padding:6px;" required>
                            <input type="number" class="op-hc" value="${hcVal}" placeholder="Hc" style="padding:6px;" min="0">
                            <input type="number" step="0.1" class="op-hours" value="${hVal}" placeholder="Horas" style="padding:6px;" min="0">
                            <button type="button" class="btn btn-xs btn-danger" onclick="this.closest('.edit-std-op-row').remove()" title="Remover operação">✕</button>
                        </div>
                        <div style="display:flex; flex-direction:column; gap:6px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <label style="font-size:11px; font-weight:700; color:#475569;">
                                    Texto Longo Técnico / Blocos:
                                    <span class="op-lt-badge badge badge-outline" style="font-size:10px; color:#059669; border-color:#A7F3D0; margin-left:6px; display:${hasLt ? 'inline-block' : 'none'};">✓ Texto Longo Configurado</span>
                                </label>
                                <button type="button" class="btn btn-xs btn-outline" style="color:#0284C7; border-color:#BAE6FD; background:#F0F9FF; font-weight:600;" onclick="StandardsManager.openOperationLongTextEditor(this)">
                                    📝 Abrir Editor Estruturado de Texto Longo / Blocos
                                </button>
                            </div>
                            <textarea class="op-lt" placeholder="Texto longo técnico da operação (dê dois cliques para abrir o editor padrão)..." style="width:100%; height:55px; padding:6px 8px; font-size:12px; font-family:inherit; border-radius:6px; border:1px solid #CBD5E1;" ondblclick="StandardsManager.openOperationLongTextEditor(this)" onfocus="StandardsManager.openOperationLongTextEditor(this)">${UI.escapeHTML(ltText)}</textarea>
                        </div>
                    </div>
                `;
            }).join('');

            const modalHtml = `
                <div id="modal-edit-std-item" class="modal-overlay" style="z-index:2500">
                    <div class="modal modal-lg">
                        <div class="modal-header">
                            <h2>✏️ Editar Modelo de Item Padrão</h2>
                            <button class="btn-icon" onclick="document.getElementById('modal-edit-std-item').remove()">✕</button>
                        </div>
                        <div class="modal-body" style="max-height:75vh; overflow-y:auto;">
                            <div class="form-group mb-12">
                                <label>Título do Modelo *</label>
                                <input type="text" id="edit-std-title" value="${UI.escapeHTML(detail.title || '')}" style="width:100%; padding:8px;" required>
                            </div>
                            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;" class="mb-12">
                                <div class="form-group">
                                    <label>Categoria</label>
                                    <input type="text" id="edit-std-category" value="${UI.escapeHTML(detail.category || 'GERAL')}" style="width:100%; padding:8px;">
                                </div>
                                <div class="form-group">
                                    <label>Centro de Trabalho Padrão</label>
                                    <input type="text" id="edit-std-wc" value="${UI.escapeHTML(detail.work_center || '')}" style="width:100%; padding:8px;">
                                </div>
                            </div>
                            <div class="form-group mb-12">
                                <label>Descrição / Equipamento Padrão</label>
                                <input type="text" id="edit-std-description" value="${UI.escapeHTML(detail.description || '')}" style="width:100%; padding:8px;">
                            </div>
                            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;" class="mb-16">
                                <div class="form-group">
                                    <label>Código do Equipamento</label>
                                    <input type="text" id="edit-std-equipment" value="${UI.escapeHTML(detail.equipment_code || '')}" style="width:100%; padding:8px;">
                                </div>
                                <div class="form-group">
                                    <label>GPM</label>
                                    <input type="text" id="edit-std-gpm" value="${UI.escapeHTML(detail.gpm || '')}" style="width:100%; padding:8px;">
                                </div>
                            </div>

                            <h3 style="font-size:14px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                                Operações SAP do Modelo
                                <button type="button" class="btn btn-xs btn-outline" onclick="StandardsManager.addEditItemOpRow()">+ Adicionar Operação</button>
                            </h3>

                            <div id="edit-std-ops-container" style="display:flex; flex-direction:column; gap:10px;">
                                ${opsHtml}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-outline" onclick="document.getElementById('modal-edit-std-item').remove()">Cancelar</button>
                            <button class="btn btn-primary" onclick="StandardsManager.saveEditedItem(${detail.id})">Salvar Alterações</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        } catch (e) {
            UI.showToast(`Erro ao abrir edição: ${e.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    addEditItemOpRow() {
        const container = document.getElementById('edit-std-ops-container');
        if (!container) return;
        const count = container.querySelectorAll('.edit-std-op-row').length;
        const nextOp = String((count + 1) * 10).padStart(4, '0');
        const rowHtml = `
            <div class="edit-std-op-row" style="background:#F8FAFC; border:1px solid #CBD5E1; padding:12px; border-radius:8px;"
                 data-lt-text="" data-lt-mode="FREE" data-lt-json="" data-lt-source="">
                <div style="display:grid; grid-template-columns: 72px 82px 92px 1fr 64px 64px 30px; gap:8px; align-items:center; margin-bottom:8px;">
                    <input type="text" class="op-code" value="${nextOp}" placeholder="Op" style="padding:6px; font-weight:700;">
                    <input type="text" class="op-subcode" value="" placeholder="Subop." style="padding:6px; font-weight:700;">
                    <input type="text" class="op-wc" value="" placeholder="CT" style="padding:6px;">
                    <input type="text" class="op-short" value="" placeholder="Texto breve da operação" style="padding:6px;" required>
                    <input type="number" class="op-hc" value="" placeholder="Hc" style="padding:6px;" min="0">
                    <input type="number" step="0.1" class="op-hours" value="" placeholder="Horas" style="padding:6px;" min="0">
                    <button type="button" class="btn btn-xs btn-danger" onclick="this.closest('.edit-std-op-row').remove()" title="Remover operação">✕</button>
                </div>
                <div style="display:flex; flex-direction:column; gap:6px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <label style="font-size:11px; font-weight:700; color:#475569;">
                            Texto Longo Técnico / Blocos:
                            <span class="op-lt-badge badge badge-outline" style="font-size:10px; color:#059669; border-color:#A7F3D0; margin-left:6px; display:none;">✓ Texto Longo Configurado</span>
                        </label>
                        <button type="button" class="btn btn-xs btn-outline" style="color:#0284C7; border-color:#BAE6FD; background:#F0F9FF; font-weight:600;" onclick="StandardsManager.openOperationLongTextEditor(this)">
                            📝 Abrir Editor Estruturado de Texto Longo / Blocos
                        </button>
                    </div>
                    <textarea class="op-lt" placeholder="Texto longo técnico da operação (clique para abrir o editor estruturado)..." style="width:100%; height:55px; padding:6px 8px; font-size:12px; font-family:inherit; border-radius:6px; border:1px solid #CBD5E1;" onfocus="StandardsManager.openOperationLongTextEditor(this)"></textarea>
                </div>
            </div>
        `;
        container.insertAdjacentHTML('beforeend', rowHtml);
    },

    async saveEditedItem(standardId) {
        const title = document.getElementById('edit-std-title')?.value.trim();
        if (!title) return UI.showToast('Informe o título do modelo.', 'warning');

        const rows = document.querySelectorAll('.edit-std-op-row');
        const operations = Array.from(rows).map(row => {
            const ltText = row.dataset.ltText || row.querySelector('.op-lt')?.value.trim() || '';
            const ltMode = row.dataset.ltMode || 'FREE';
            const ltJson = row.dataset.ltJson || '';
            const ltSource = row.dataset.ltSource || '';
            const hcRaw = row.querySelector('.op-hc')?.value.trim();
            const hRaw = row.querySelector('.op-hours')?.value.trim();

            return {
                operation_code: row.querySelector('.op-code')?.value.trim() || '0010',
                suboperation_code: row.querySelector('.op-subcode')?.value.trim() || '',
                work_center: row.querySelector('.op-wc')?.value.trim() || '',
                short_text: row.querySelector('.op-short')?.value.trim() || '',
                headcount: (hcRaw !== undefined && hcRaw !== '' && !isNaN(hcRaw)) ? parseFloat(hcRaw) : null,
                hours: (hRaw !== undefined && hRaw !== '' && !isNaN(hRaw)) ? parseFloat(hRaw) : null,
                long_text: ltText,
                long_text_structure_mode: ltMode,
                long_text_structure_json: ltJson,
                long_text_source_original: ltSource
            };
        }).filter(op => Boolean(op.short_text));

        try {
            UI.showLoader('Salvando modelo...');
            await API.put(`/api/standards/items/${standardId}`, {
                title,
                category: document.getElementById('edit-std-category')?.value.trim().toUpperCase() || 'GERAL',
                description: document.getElementById('edit-std-description')?.value.trim() || '',
                equipment_code: document.getElementById('edit-std-equipment')?.value.trim() || '',
                gpm: document.getElementById('edit-std-gpm')?.value.trim() || '',
                work_center: document.getElementById('edit-std-wc')?.value.trim() || '',
                operations
            });
            document.getElementById('modal-edit-std-item')?.remove();
            UI.showToast(`Modelo "${title}" atualizado com sucesso!`, 'success');
            await this.loadItems();
        } catch (e) {
            UI.showToast(`Erro ao salvar: ${e.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async duplicateItem(standardId) {
        const match = this.standardItems.find(i => i.id === standardId);
        if (!match) return;
        const newTitle = prompt('Digite o título para o novo modelo clonado:', `${match.title} (Cópia)`);
        if (!newTitle || !newTitle.trim()) return;

        try {
            UI.showLoader('Duplicando modelo...');
            await API.post(`/api/standards/items/${standardId}/duplicate`, { title: newTitle.trim() });
            UI.showToast(`Modelo "${newTitle}" duplicado com sucesso!`, 'success');
            await this.loadItems();
        } catch (e) {
            UI.showToast(`Erro ao duplicar: ${e.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    // --------------------------------------------------
    // VIEW / EDIT / DUPLICATE LONG TEXT BLOCKS
    // --------------------------------------------------

    async openEditBlockModal(blockId) {
        const b = this.standardBlocks.find(item => item.id === blockId);
        if (!b) return UI.showToast('Bloco não encontrado.', 'error');

        const title = prompt('Editar nome do bloco padrão:', b.title);
        if (title === null) return;
        const category = prompt('Editar categoria do bloco:', b.category || 'GERAL');
        if (category === null) return;
        const tags = prompt('Editar tags (separadas por vírgula):', b.tags || '');
        if (tags === null) return;
        const text = prompt('Editar prévia / texto do bloco:', b.text || '');
        if (text === null) return;

        try {
            await API.put(`/api/long-text-blocks/${blockId}`, {
                title: title.trim(),
                category: category.trim().toUpperCase(),
                tags: tags.trim(),
                structure_json: b.structure_json,
                text: text.trim()
            });
            UI.showToast('Bloco padrão atualizado!', 'success');
            await this.loadBlocks();
        } catch (e) {
            UI.showToast(`Erro ao atualizar bloco: ${e.message}`, 'error');
        }
    },

    async duplicateBlock(blockId) {
        const b = this.standardBlocks.find(item => item.id === blockId);
        if (!b) return;
        const newTitle = prompt('Digite o nome para o bloco clonado:', `${b.title} (Cópia)`);
        if (!newTitle || !newTitle.trim()) return;

        try {
            await API.post('/api/long-text-blocks', {
                title: newTitle.trim(),
                category: b.category || 'GERAL',
                tags: b.tags || '',
                structure_json: b.structure_json
            });
            UI.showToast('Bloco padrão duplicado com sucesso!', 'success');
            await this.loadBlocks();
        } catch (e) {
            UI.showToast(`Erro ao duplicar bloco: ${e.message}`, 'error');
        }
    },

    async deleteBlock(blockId) {
        if (!confirm('Deseja realmente excluir este bloco padrão da biblioteca?')) return;
        try {
            await API.delete(`/api/long-text-blocks/${blockId}`);
            UI.showToast('Bloco padrão removido!', 'success');
            await this.loadBlocks();
        } catch (e) {
            UI.showToast(`Erro ao remover: ${e.message}`, 'error');
        }
    },

    async cloneLongText(id) {
        const match = this.standardLongTexts.find(t => t.id === id);
        if (!match) return;
        const newTitle = prompt('Digite o título para o modelo clonado:', `${match.title} (Cópia)`);
        if (!newTitle || !newTitle.trim()) return;

        await this.saveCurrentLongTextAsStandard(newTitle.trim(), match.category || 'GERAL', match.text);
    },

    async openCreateLongTextModal() {
        const title = prompt('Digite o Título do Modelo Padrão:');
        if (!title || !title.trim()) return;
        const category = prompt('Digite a Categoria (ex: Motores, Válvulas, Redutores):', 'GERAL') || 'GERAL';
        const text = prompt('Digite o procedimento / texto longo detalhado:');
        if (!text || !text.trim()) return;

        await this.saveCurrentLongTextAsStandard(title.trim(), category.trim(), text.trim());
    },

    async openEditLongTextModal(id) {
        const match = this.standardLongTexts.find(t => t.id === id);
        if (!match) return;
        const title = prompt('Editar Título do Modelo Padrão:', match.title);
        if (title === null) return;
        const category = prompt('Editar Categoria do Modelo:', match.category || 'GERAL');
        if (category === null) return;
        const text = prompt('Editar Procedimento / Texto Longo:', match.text);
        if (text === null) return;

        try {
            await API.put(`/api/standards/long-texts/${id}`, {
                title: title.trim(),
                category: category.trim(),
                text: text.trim()
            });
            UI.showToast('Modelo padrão atualizado!', 'success');
            await this.loadLongTexts();
            this.renderViewTables();
        } catch (err) {
            UI.showToast(`Erro ao atualizar: ${err.message}`, 'error');
        }
    },

    async instantiateItemInProject(standardId) {
        const projectId = window.App ? App.getValidProjectId() : null;
        if (!projectId) {
            UI.showToast('Selecione um projeto ativo primeiro.', 'warning');
            return;
        }
        const match = this.standardItems.find(i => i.id === standardId);
        const name = match ? match.title : 'Modelo Padrão';

        if (!confirm(`Deseja instanciar o modelo de item "${name}" no projeto ativo? Todas as operações e textos longos serão criados automaticamente!`)) return;

        try {
            UI.showLoader('Instanciando item padrão no projeto...');
            await API.post(`/api/items/from-standard/${standardId}?project_id=${projectId}`, {});
            UI.showToast(`Item "${name}" criado com sucesso no projeto ativo!`, 'success');
            if (window.Operations) {
                await Operations.loadOperations();
            }
        } catch (err) {
            UI.showToast(`Erro ao instanciar modelo: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async applySelectedLongTextStandard() {
        const selectModal = document.getElementById('select-standard-long-text');
        if (!selectModal) return;
        const selectedId = parseInt(selectModal.value);
        if (!selectedId) {
            UI.showToast('Selecione um modelo de texto padrão na lista.', 'warning');
            return;
        }
        const match = this.standardLongTexts.find(t => t.id === selectedId);
        if (!match) return;

        const textEl = document.getElementById('form-lt-text');
        const currentText = window.LongTextEditor ? LongTextEditor.getPayload().text : (textEl?.value || '');
        
        if (currentText && currentText.trim() !== '') {
            const confirmMsg = `⚠️ ATENÇÃO: Substituir Texto Longo Atual?\n\nEste texto longo já possui conteúdo gravado.\n\nDeseja substituir TODO o texto atual pelo modelo padrão:\n" ${match.title} "?\n\n(Ação irreversível, o texto existente será sobrescrito pelo modelo)`;
            if (!window.confirm(confirmMsg)) {
                selectModal.value = '';
                return;
            }
        }

        if (window.LongTextEditor) {
            await LongTextEditor.loadRecord(match, false);
        } else if (textEl) {
            textEl.value = match.text;
        }
        UI.showToast(`Texto padrão "${match.title}" aplicado com sucesso!`, 'success', 2500);
    },

    populateLongTextSelectors() {
        const selectModal = document.getElementById('select-standard-long-text');
        if (selectModal) {
            let html = '<option value="">📋 Importar de Texto Padrão (Modelo)...</option>';
            const categories = {};
            this.standardLongTexts.forEach(t => {
                const cat = t.category || 'GERAL';
                if (!categories[cat]) categories[cat] = [];
                categories[cat].push(t);
            });

            Object.keys(categories).sort().forEach(cat => {
                html += `<optgroup label="${UI.escapeHTML(cat)}">`;
                categories[cat].forEach(t => {
                    html += `<option value="${t.id}">${UI.escapeHTML(t.title)}</option>`;
                });
                html += `</optgroup>`;
            });

            selectModal.innerHTML = html;
            selectModal.onchange = async () => {
                const selectedId = parseInt(selectModal.value);
                if (!selectedId) return;
                await this.applySelectedLongTextStandard();
            };
        }
    },

    populateItemSelectors() {
        const selectModal = document.getElementById('select-standard-item');
        if (selectModal) {
            let html = '<option value="">📦 Criar a partir de Item Padrão (Modelo)...</option>';
            const categories = {};
            this.standardItems.forEach(item => {
                const cat = item.category || 'GERAL';
                if (!categories[cat]) categories[cat] = [];
                categories[cat].push(item);
            });

            Object.keys(categories).sort().forEach(cat => {
                html += `<optgroup label="${UI.escapeHTML(cat)}">`;
                categories[cat].forEach(item => {
                    html += `<option value="${item.id}">${UI.escapeHTML(item.title)} (${item.operations_count || 0} op.)</option>`;
                });
                html += `</optgroup>`;
            });

            selectModal.innerHTML = html;
            selectModal.onchange = async () => {
                const selectedId = parseInt(selectModal.value);
                if (!selectedId) return;
                try {
                    const detail = await API.get(`/api/standards/items/${selectedId}`);
                    if (detail) {
                        const setValue = (id, value) => {
                            const element = document.getElementById(id);
                            if (element) element.value = value ?? '';
                        };
                        setValue('form-item-obj-type', detail.object_type || 'EQUIPAMENTO');
                        setValue('form-item-obj-code', detail.object_code || '');
                        setValue('form-item-desc', detail.description || detail.title || '');
                        setValue('form-item-gpm', detail.gpm || '');
                        setValue('form-item-wc', detail.work_center || '');
                          setValue('form-item-condition', detail.condition_code || 'P');
                          setValue('form-item-priority', detail.priority ?? 3);
                          let mecHc = Number(detail.mec_headcount) || 0;
                          let mecHours = Number(detail.mec_hours) || 0;
                          let eleHc = Number(detail.ele_headcount) || 0;
                          let eleHours = Number(detail.ele_hours) || 0;
                          let solHc = Number(detail.sol_headcount) || 0;
                          let solHours = Number(detail.sol_hours) || 0;

                          if ((mecHc + eleHc + solHc) === 0 && Number(detail.headcount) > 0) {
                              const trade = `${detail.gpm || ''} ${detail.work_center || ''}`.toUpperCase();
                              const legacyHc = Number(detail.headcount) || 0;
                              const legacyHours = Number(detail.duration_hours) || 0;
                              if (trade.includes('ELE')) {
                                  eleHc = legacyHc;
                                  eleHours = legacyHours;
                              } else if (trade.includes('SOL') || trade.includes('CALD')) {
                                  solHc = legacyHc;
                                  solHours = legacyHours;
                              } else {
                                  mecHc = legacyHc;
                                  mecHours = legacyHours;
                              }
                          }
                          setValue('form-item-mec-hc', mecHc);
                          setValue('form-item-mec-hours', mecHours);
                          setValue('form-item-ele-hc', eleHc);
                          setValue('form-item-ele-hours', eleHours);
                          setValue('form-item-sol-hc', solHc);
                          setValue('form-item-sol-hours', solHours);
                        setValue('form-item-notes', detail.notes || '');
                        if (window.Items) Items.updateModalTradePreviews();
                        document.getElementById('form-item-desc')?.oninput?.();
                        
                        selectModal.dataset.selectedStandardId = selectedId;
                        const operationCount = (detail.operations || []).length;
                        const textCount = (detail.operations || []).reduce((sum, op) => sum + (op.long_texts || []).length, 0);
                        UI.showToast(`Modelo "${detail.title}" carregado: ${operationCount} operações e ${textCount} textos longos serão copiados ao salvar.`, 'success', 4000);
                    }
                } catch (err) {
                    UI.showToast(`Erro ao carregar detalhes do modelo: ${err.message}`, 'error');
                }
            };
        }
    },

    openLibraryModal(defaultTab = 'long-texts') {
        const modal = document.getElementById('modal-standards-library');
        if (!modal) return;
        
        this.switchTab(defaultTab);
        this.renderLibraryContent();
        modal.classList.remove('hidden');
    },

    switchTab(tabName) {
        this.currentTab = tabName;
        document.querySelectorAll('.standards-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        document.querySelectorAll('.standards-tab-content').forEach(content => {
            content.classList.toggle('hidden', content.id !== `standards-tab-${tabName}`);
        });
        this.renderLibraryContent();
    },

    renderLibraryContent() {
        if (this.currentTab === 'long-texts') {
            this.renderLongTextsTable();
        } else {
            this.renderItemsTable();
        }
    },

    async saveCurrentLongTextAsStandard(title, category, text, editorPayload = null) {
        if (!title || !text) {
            UI.showToast('Preencha o título e o texto para criar o padrão.', 'error');
            return;
        }
        try {
            const payload = editorPayload || (window.LongTextEditor ? LongTextEditor.getPayload() : { text, structure_mode:'FREE', structure_json:null });
            await API.post('/api/standards/long-texts', { title, category, text: payload.text || text, structure_mode: payload.structure_mode, structure_json: payload.structure_json });
            UI.showToast(`Texto padrão "${title}" criado na biblioteca!`, 'success');
            await this.loadLongTexts();
        } catch (err) {
            UI.showToast(`Erro ao criar texto padrão: ${err.message}`, 'error');
        }
    },

    async saveItemAsStandard(itemId) {
        const title = prompt('Digite um nome para o modelo de item padrão:');
        if (!title || !title.trim()) return;
        const category = prompt('Digite uma categoria (ex: Motores, Redutores, Válvulas):', 'GERAL') || 'GERAL';
        
        try {
            UI.showLoader('Salvando item na biblioteca de padrões...');
            await API.post(`/api/standards/items/from-item/${itemId}`, { title: title.trim(), category: category.trim() });
            UI.showToast(`Item "${title}" salvo na biblioteca de padrões com sucesso!`, 'success');
            await this.loadItems();
        } catch (err) {
            UI.showToast(`Erro ao salvar modelo: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async deleteLongText(id) {
        if (!confirm('Deseja realmente excluir este texto longo padrão da biblioteca?')) return;
        try {
            await API.delete(`/api/standards/long-texts/${id}`);
            UI.showToast('Texto padrão removido!', 'success');
            await this.loadLongTexts();
        } catch (err) {
            UI.showToast(`Erro ao remover: ${err.message}`, 'error');
        }
    },

    async deleteItem(id) {
        if (!confirm('Deseja realmente excluir este modelo de item padrão da biblioteca?')) return;
        try {
            await API.delete(`/api/standards/items/${id}`);
            UI.showToast('Modelo de item removido!', 'success');
            await this.loadItems();
        } catch (err) {
            UI.showToast(`Erro ao remover: ${err.message}`, 'error');
        }
    }
};
