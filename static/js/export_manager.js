/**
 * PM13 Export Manager - Custom export modal with item filtering & selection
 */
window.ExportManager = {
    scope: 'full',
    selectedItemIds: new Set(),
    allItems: [],
    allPlans: [],
    filteredItems: [],

    init() {
        this.ensureModals();
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
                                    <p style="font-size:12px; color:#1E40AF; line-height:1.4; margin:0;">Escolha itens específicos via busca/filtros. As abas de planos, operações e textos longos serão filtradas para estes itens.</p>
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
                    <div class="modal modal-lg" style="max-width:960px;">
                        <div class="modal-header" style="background:#F8FAFC; border-bottom:1px solid #E2E8F0; padding:16px 20px;">
                            <div>
                                <h2>🎯 Selecionar Itens para Exportação</h2>
                                <small style="color:#64748B;">Selecione os itens que serão incluídos na exportação. Todas as abas vinculadas serão filtradas automaticamente.</small>
                            </div>
                            <button class="btn-icon" onclick="ExportManager.closeSelectModal()">✕</button>
                        </div>
                        <div class="modal-body" style="padding:16px 20px;">
                            <!-- BARRA DE FILTROS -->
                            <div style="background:#F1F5F9; border:1px solid #CBD5E1; border-radius:8px; padding:12px; margin-bottom:14px; display:grid; grid-template-columns: 2fr 1fr 1fr 1.2fr auto; gap:10px; align-items:center;">
                                <div>
                                    <label style="font-size:11px; font-weight:700; color:#475569; display:block; margin-bottom:3px;">Busca rápida</label>
                                    <input type="text" id="export-filter-search" placeholder="Buscar por descrição, equipamento, ID ou plano..." style="width:100%; padding:6px 8px; font-size:12px; border-radius:6px; border:1px solid #CBD5E1;" oninput="ExportManager.renderItemList()">
                                </div>
                                <div>
                                    <label style="font-size:11px; font-weight:700; color:#475569; display:block; margin-bottom:3px;">Centro de Trabalho (CT)</label>
                                    <select id="export-filter-wc" style="width:100%; padding:6px; font-size:12px; border-radius:6px; border:1px solid #CBD5E1;" onchange="ExportManager.renderItemList()">
                                        <option value="">Todos os CTs</option>
                                    </select>
                                </div>
                                <div>
                                    <label style="font-size:11px; font-weight:700; color:#475569; display:block; margin-bottom:3px;">GPM</label>
                                    <select id="export-filter-gpm" style="width:100%; padding:6px; font-size:12px; border-radius:6px; border:1px solid #CBD5E1;" onchange="ExportManager.renderItemList()">
                                        <option value="">Todos os GPMs</option>
                                    </select>
                                </div>
                                <div>
                                    <label style="font-size:11px; font-weight:700; color:#475569; display:block; margin-bottom:3px;">Plano Vinculado</label>
                                    <select id="export-filter-plan" style="width:100%; padding:6px; font-size:12px; border-radius:6px; border:1px solid #CBD5E1;" onchange="ExportManager.renderItemList()">
                                        <option value="">Todos os Planos</option>
                                    </select>
                                </div>
                                <div style="padding-top:16px;">
                                    <button class="btn btn-xs btn-outline" style="white-space:nowrap;" onclick="ExportManager.clearFilters()">Limpar Filtros</button>
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
                                            <th style="width:80px;">CT</th>
                                            <th style="width:65px;">GPM</th>
                                        </tr>
                                    </thead>
                                    <tbody id="export-items-tbody">
                                        <tr><td colspan="7" class="text-center py-12">Carregando itens do projeto...</td></tr>
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
        const wcSelect = document.getElementById('export-filter-wc');
        const gpmSelect = document.getElementById('export-filter-gpm');
        const planSelect = document.getElementById('export-filter-plan');

        const wcs = [...new Set(this.allItems.map(i => i.work_center).filter(Boolean))].sort();
        const gpms = [...new Set(this.allItems.map(i => i.gpm).filter(Boolean))].sort();
        const plans = this.allPlans.map(p => ({ id: p.id, label: `${p.legacy_code} - ${p.description || ''}` })).sort((a,b) => a.label.localeCompare(b.label));

        if (wcSelect) {
            wcSelect.innerHTML = '<option value="">Todos os CTs</option>' + wcs.map(wc => `<option value="${UI.escapeHTML(wc)}">${UI.escapeHTML(wc)}</option>`).join('');
        }
        if (gpmSelect) {
            gpmSelect.innerHTML = '<option value="">Todos os GPMs</option>' + gpms.map(gpm => `<option value="${UI.escapeHTML(gpm)}">${UI.escapeHTML(gpm)}</option>`).join('');
        }
        if (planSelect) {
            planSelect.innerHTML = '<option value="">Todos os Planos</option>' + plans.map(p => `<option value="${p.id}">${UI.escapeHTML(p.label)}</option>`).join('');
        }

        document.getElementById('export-filter-search').value = '';
    },

    clearFilters() {
        document.getElementById('export-filter-search').value = '';
        document.getElementById('export-filter-wc').value = '';
        document.getElementById('export-filter-gpm').value = '';
        document.getElementById('export-filter-plan').value = '';
        this.renderItemList();
    },

    renderItemList() {
        const tbody = document.getElementById('export-items-tbody');
        if (!tbody) return;

        const q = (document.getElementById('export-filter-search')?.value || '').toLowerCase().trim();
        const selectedWc = document.getElementById('export-filter-wc')?.value || '';
        const selectedGpm = document.getElementById('export-filter-gpm')?.value || '';
        const selectedPlanId = document.getElementById('export-filter-plan')?.value || '';

        this.filteredItems = this.allItems.filter(item => {
            if (selectedWc && item.work_center !== selectedWc) return false;
            if (selectedGpm && item.gpm !== selectedGpm) return false;
            if (selectedPlanId && String(item.plan_id) !== String(selectedPlanId)) return false;
            if (q) {
                const searchStr = `${item.legacy_identifier} ${item.object_code} ${item.description} ${item.plan_code} ${item.plan_description} ${item.work_center} ${item.gpm}`.toLowerCase();
                if (!searchStr.includes(q)) return false;
            }
            return true;
        });

        if (!this.filteredItems.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center py-12 muted">Nenhum item encontrado com os filtros selecionados.</td></tr>';
            this.updateCounter();
            return;
        }

        const allFilteredSelected = this.filteredItems.length > 0 && this.filteredItems.every(i => this.selectedItemIds.has(i.id));
        const selectAllChk = document.getElementById('export-select-all-visible');
        if (selectAllChk) selectAllChk.checked = allFilteredSelected;

        tbody.innerHTML = this.filteredItems.map(item => {
            const isChecked = this.selectedItemIds.has(item.id);
            return `
                <tr style="background:${isChecked ? '#F0FDF4' : 'transparent'}; cursor:pointer;" onclick="ExportManager.handleRowClick(event, ${item.id})">
                    <td style="text-align:center;">
                        <input type="checkbox" class="export-item-checkbox" data-id="${item.id}" ${isChecked ? 'checked' : ''} onclick="event.stopPropagation(); ExportManager.toggleItem(${item.id})">
                    </td>
                    <td><strong>${UI.escapeHTML(item.legacy_identifier || item.id)}</strong></td>
                    <td>${UI.escapeHTML(item.object_code || '-')}</td>
                    <td style="font-weight:600; color:#1E293B;">${UI.escapeHTML(item.description || '')}</td>
                    <td><small style="color:#475569;">${UI.escapeHTML(item.plan_code ? `${item.plan_code} - ${item.plan_description || ''}` : 'Sem plano')}</small></td>
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
            submitBtn.disabled = count === 0;
            submitBtn.textContent = `📥 Exportar Itens Selecionados (${count})`;
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

