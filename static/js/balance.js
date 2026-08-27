/**
 * Balance View & Chart Controller
 */

window.Balance = {
    data: null,
    currentChartType: 'hh', // hh, headcount, orders
    selectedIdentifiers: new Set(),
    selectedPlanIds: new Set(),
    selectedItemIds: new Set(),
    manualSession: null,
    manualSelectedIds: new Set(),
    manualSelectedCycles: new Set(),
    manualBookItems: [],
    dragInProgress: false,

    init() {
        // Grouping & Horizon selectors
        const groupSel = document.getElementById('balance-groupby');
        if (groupSel) groupSel.onchange = () => this.load();
        const horizSel = document.getElementById('balance-filter-horizon');
        if (horizSel) horizSel.onchange = () => this.load();
        const heatSel = document.getElementById('heatmap-rows-by');
        if (heatSel) heatSel.onchange = () => this.load();

        // Filters selectors
        const wcSel = document.getElementById('balance-filter-wc');
        if (wcSel) wcSel.onchange = () => this.load();
        const gpmSel = document.getElementById('balance-filter-gpm');
        if (gpmSel) gpmSel.onchange = () => this.load();
        const condSel = document.getElementById('balance-filter-condition');
        if (condSel) condSel.onchange = () => this.load();
        const headcountStatusSel = document.getElementById('balance-filter-headcount-status');
        if (headcountStatusSel) headcountStatusSel.onchange = () => {
            this.updateKPIs();
            this.renderChart();
            this.renderHeatmap();
        };
        const idTrigger = document.getElementById('balance-id-filter-trigger');
        const idPanel = document.getElementById('balance-id-filter-panel');
        if (idTrigger && idPanel) idTrigger.onclick = (event) => { event.stopPropagation(); idPanel.classList.toggle('hidden'); };
        const idSearch = document.getElementById('balance-id-filter-search');
        if (idSearch) idSearch.oninput = () => this.filterIdentifierOptions(idSearch.value);
        const selectAllIds = document.getElementById('balance-id-select-all');
        if (selectAllIds) selectAllIds.onclick = () => this.selectAllVisibleIdentifiers();
        const clearIds = document.getElementById('balance-id-clear');
        if (clearIds) clearIds.onclick = () => { this.selectedIdentifiers.clear(); this.syncIdentifierChecks(); this.updateIdentifierTrigger(); this.load(); };
        document.addEventListener('click', (event) => {
            if (idPanel && !idPanel.contains(event.target) && event.target !== idTrigger) idPanel.classList.add('hidden');
        });
        this.setupEntityMultiFilter('plan', this.selectedPlanIds, 'Todos os planos');
        this.setupEntityMultiFilter('item', this.selectedItemIds, 'Todos os itens');

        // Trade Capacity inputs
        ['mec', 'ele', 'sol'].forEach(t => {
            const input = document.getElementById(`balance-cap-${t}`);
            if (input) {
                input.oninput = () => {
                    this.updateMetaKPIs();
                    this.renderChart();
                    this.renderHeatmap();
                };
                input.onchange = () => {
                    this.saveProjectCapacities();
                };
            }
        });

        // Heatmap rows selector
        const heatmapRowSelect = document.getElementById('heatmap-rows-by');
        if (heatmapRowSelect) {
            heatmapRowSelect.onchange = () => this.renderHeatmap();
        }

        // Chart type toggles
        const btnHh = document.getElementById('btn-chart-toggle-hh');
        if (btnHh) {
            btnHh.classList.add('active');
            btnHh.onclick = () => this.setChartType('hh');
        }
        const btnHc = document.getElementById('btn-chart-toggle-hc');
        if (btnHc) btnHc.onclick = () => this.setChartType('headcount');
        const btnOrders = document.getElementById('btn-chart-toggle-orders');
        if (btnOrders) btnOrders.onclick = () => this.setChartType('orders');

        // Drawer close events
        const btnCloseDrawer = document.getElementById('btn-close-drawer');
        if (btnCloseDrawer) {
            btnCloseDrawer.onclick = () => {
                document.getElementById('stop-details-drawer').classList.add('hidden');
            };
        }
        const drawerEl = document.getElementById('stop-details-drawer');
        if (drawerEl) {
            drawerEl.onclick = (e) => {
                if (e.target === drawerEl) {
                    drawerEl.classList.add('hidden');
                }
            };
        }

        // Export button in drawer
        const btnDrawerExp = document.getElementById('btn-drawer-export');
        if (btnDrawerExp) {
            btnDrawerExp.onclick = () => {
                const stopCounter = parseInt(document.getElementById('drawer-stop-counter').innerText);
                this.exportStopOrders(stopCounter);
            };
        }

        // Close inline details (split screen column)
        const btnCloseInline = document.getElementById('btn-close-inline-details');
        if (btnCloseInline) {
            btnCloseInline.onclick = () => {
                const rightCol = document.querySelector('.balance-right-col');
                const leftCol = document.querySelector('.balance-left-col');
                const handle = document.getElementById('balance-splitter-handle');
                if (rightCol) rightCol.classList.add('hidden');
                if (handle) handle.classList.add('hidden');
                if (leftCol) { leftCol.style.flex = ''; leftCol.style.width = ''; }
                if (rightCol) { rightCol.style.flex = ''; rightCol.style.width = ''; }
                this.activeStopCounter = null;
                
                // Restore sidebar width
                const sidebar = document.getElementById('sidebar');
                if (sidebar) sidebar.classList.remove('collapsed');

                setTimeout(() => {
                    this.renderChart(); // Re-render to expand chart to 100% after transition
                }, 50);
            };
        }

        // Export inline stop details to CSV
        const btnInlineExport = document.getElementById('btn-inline-export');
        if (btnInlineExport) {
            btnInlineExport.onclick = () => {
                if (this.activeStopCounter) {
                    this.exportStopOrders(this.activeStopCounter);
                }
            };
        }

        // Undo & Redo balancing actions
        const btnUndo = document.getElementById('btn-undo-balance');
        if (btnUndo) {
            btnUndo.onclick = () => this.undoLastAction();
        }
        const btnRedo = document.getElementById('btn-redo-balance');
        if (btnRedo) {
            btnRedo.onclick = () => this.redoLastAction();
        }
        const btnRestorePre = document.getElementById('btn-restore-pre-balance');
        if (btnRestorePre) {
            btnRestorePre.onclick = () => this.restorePreBalance();
        }
        const btnExportBalance = document.getElementById('btn-export-balance');
        if (btnExportBalance) btnExportBalance.onclick = () => this.exportManagerialWorkbook();

        // Balance reassignment modal close buttons
        const btnCloseModal = document.getElementById('btn-close-balance-modal');
        if (btnCloseModal) {
            btnCloseModal.onclick = () => this.closeConfirmModal();
        }
        const modalOverlay = document.getElementById('balance-confirm-modal');
        if (modalOverlay) {
            modalOverlay.onclick = (e) => {
                if (e.target === modalOverlay) {
                    this.closeConfirmModal();
                }
            };
        }

        // Automatic balance modal
        const btnAuto = document.getElementById('btn-auto-balance');
        if (btnAuto) btnAuto.onclick = () => this.openAutoBalance();
        const btnManual = document.getElementById('btn-manual-balance');
        if (btnManual) btnManual.onclick = () => this.openManualBalance();
        document.getElementById('btn-open-manual-book')?.addEventListener('click', () => this.openManualBook());
        document.getElementById('btn-panel-book')?.addEventListener('click', () => this.openManualBook());
        document.getElementById('btn-manual-return-all-to-book')?.addEventListener('click', () => this.promptPM13ReturnToBookModal());
        document.getElementById('btn-panel-stop')?.addEventListener('click', () => {
            if (this.activeStopCounter) this.openStopDetails(this.activeStopCounter);
        });
        document.getElementById('manual-only-pending')?.addEventListener('change', () => this.loadManualBook());
        document.getElementById('manual-book-search')?.addEventListener('input', () => this.debounceManualBook());
        document.getElementById('manual-plan-search')?.addEventListener('input', () => this.debounceManualBook());
        document.getElementById('btn-manual-select-visible')?.addEventListener('click', () => {
            this.manualBookItems
                .filter(item => item.balance_state !== 'FIXED')
                .forEach(item => this.manualSelectedIds.add(Number(item.id)));
            this.renderManualBookRows();
        });
        document.getElementById('btn-manual-clear-selection')?.addEventListener('click', () => {
            this.manualSelectedIds.clear(); this.renderManualBookRows();
        });
        document.getElementById('btn-manual-restart')?.addEventListener('click', () => this.restartManualBalance());
        document.getElementById('btn-manual-complete')?.addEventListener('click', () => this.completeManualBalance());
        document.getElementById('btn-manual-discard')?.addEventListener('click', () => this.discardManualBalance());
        ['manual-return-dropzone', 'manual-stop-return-dropzone'].forEach(zoneId => {
            const returnZone = document.getElementById(zoneId);
            if (!returnZone) return;
            returnZone.addEventListener('dragover', event => {
                event.preventDefault(); returnZone.classList.add('drag-visible');
            });
            returnZone.addEventListener('dragleave', () => returnZone.classList.remove('drag-visible'));
            returnZone.addEventListener('drop', event => {
                event.preventDefault();
                let payload = window.pendingDraggedItem || {};
                try { payload = JSON.parse(event.dataTransfer.getData('text/plain') || '{}') || payload; } catch (_) {}
                returnZone.classList.remove('drag-visible');
                this.returnManualItems(payload.itemIds || (payload.itemId ? [payload.itemId] : []));
            });
        });
        const btnCloseAuto = document.getElementById('btn-close-auto-balance');
        if (btnCloseAuto) btnCloseAuto.onclick = () => this.closeAutoBalance();
        const btnCancelAuto = document.getElementById('btn-cancel-auto-balance');
        if (btnCancelAuto) btnCancelAuto.onclick = () => this.closeAutoBalance();
        const btnAddRule = document.getElementById('btn-add-auto-rule');
        if (btnAddRule) btnAddRule.onclick = () => this.addAutoRule();
        const btnRunAuto = document.getElementById('btn-run-auto-balance');
        if (btnRunAuto) btnRunAuto.onclick = () => this.runAutoBalance();
        const btnCompareAuto = document.getElementById('btn-compare-auto-strategies');
        if (btnCompareAuto) btnCompareAuto.onclick = () => this.compareAutoStrategies();
        const btnFinishAuto = document.getElementById('btn-finish-auto-balance');
        if (btnFinishAuto) btnFinishAuto.onclick = () => this.finishAutoBalance();
        const autoSearch = document.getElementById('auto-item-search');
        if (autoSearch) autoSearch.oninput = () => this.renderAutoItems();
        const autoOverlay = document.getElementById('auto-balance-modal');
        if (autoOverlay) autoOverlay.onclick = (e) => {
            if (e.target === autoOverlay) this.closeAutoBalance();
        };

        // Initialize Draggable Splitter handle
        this.initSplitterResizer();
    },

    cleanFilterVal(val) {
        if (!val) return '';
        const v = String(val).trim();
        const low = v.toLowerCase();
        if (low === 'undefined' || low === 'null' || low === 'none' || low === 'all' || low === 'todas' || low === 'todos' || low.startsWith('todos') || low.startsWith('todas')) {
            return '';
        }
        return v;
    },

    getIdentifierFilter() { return Array.from(this.selectedIdentifiers).join(','); },
    getPlanFilter() { return Array.from(this.selectedPlanIds).join(','); },
    getItemFilter() { return Array.from(this.selectedItemIds).join(','); },

    setupEntityMultiFilter(prefix, selection, emptyLabel) {
        const trigger = document.getElementById(`balance-${prefix}-filter-trigger`);
        const panel = document.getElementById(`balance-${prefix}-filter-panel`);
        const search = document.getElementById(`balance-${prefix}-filter-search`);
        if (trigger && panel) trigger.onclick = event => { event.stopPropagation(); panel.classList.toggle('hidden'); };
        if (search) search.oninput = () => {
            const term = search.value.trim().toLowerCase();
            document.querySelectorAll(`#balance-${prefix}-filter-options label`).forEach(label => label.style.display = !term || label.dataset.search.includes(term) ? '' : 'none');
        };
        document.getElementById(`balance-${prefix}-select-all`)?.addEventListener('click', () => {
            document.querySelectorAll(`#balance-${prefix}-filter-options label`).forEach(label => { if (label.style.display !== 'none') selection.add(label.querySelector('input').value); });
            this.syncEntityFilter(prefix, selection, emptyLabel); this.load();
        });
        document.getElementById(`balance-${prefix}-clear`)?.addEventListener('click', () => { selection.clear(); this.syncEntityFilter(prefix, selection, emptyLabel); this.load(); });
        document.addEventListener('click', event => { if (panel && !panel.contains(event.target) && event.target !== trigger) panel.classList.add('hidden'); });
    },

    syncEntityFilter(prefix, selection, emptyLabel) {
        document.querySelectorAll(`#balance-${prefix}-filter-options input`).forEach(cb => cb.checked = selection.has(cb.value));
        const trigger = document.getElementById(`balance-${prefix}-filter-trigger`);
        if (trigger) trigger.textContent = selection.size ? `${selection.size} selecionado(s)` : emptyLabel;
    },

    renderEntityOptions(prefix, entries, selection, emptyLabel) {
        const container = document.getElementById(`balance-${prefix}-filter-options`); if (!container) return;
        container.innerHTML = '';
        entries.forEach(entry => {
            const label=document.createElement('label'); label.dataset.search=entry.label.toLowerCase();
            const checkbox=document.createElement('input'); checkbox.type='checkbox'; checkbox.value=String(entry.value); checkbox.checked=selection.has(checkbox.value);
            checkbox.onchange=()=>{ if(checkbox.checked) selection.add(checkbox.value); else selection.delete(checkbox.value); this.syncEntityFilter(prefix,selection,emptyLabel); this.load(); };
            const text=document.createElement('span'); text.textContent=entry.label; label.append(checkbox,text); container.appendChild(label);
        });
        this.syncEntityFilter(prefix, selection, emptyLabel);
    },

    updateIdentifierTrigger() {
        const trigger = document.getElementById('balance-id-filter-trigger');
        if (!trigger) return;
        const ids = Array.from(this.selectedIdentifiers);
        trigger.textContent = ids.length ? `${ids.length} ID(s): ${ids.slice(0, 3).join(', ')}${ids.length > 3 ? '…' : ''}` : 'Todos os IDs';
        trigger.title = ids.join(', ');
    },

    syncIdentifierChecks() {
        document.querySelectorAll('#balance-id-filter-options input[type="checkbox"]').forEach(cb => cb.checked = this.selectedIdentifiers.has(cb.value));
    },

    filterIdentifierOptions(term) {
        const normalized = String(term || '').trim().toLowerCase();
        document.querySelectorAll('#balance-id-filter-options label').forEach(label => {
            label.style.display = !normalized || label.dataset.search.includes(normalized) ? '' : 'none';
        });
    },

    selectAllVisibleIdentifiers() {
        document.querySelectorAll('#balance-id-filter-options label').forEach(label => {
            if (label.style.display !== 'none') this.selectedIdentifiers.add(label.querySelector('input').value);
        });
        this.syncIdentifierChecks(); this.updateIdentifierTrigger(); this.load();
    },

    async load() {
        const projId = window.App.getValidProjectId();
        if (window.Logger) window.Logger.log(`Balance.load() called. projId=${projId}`, 'BALANCE');
        if (!projId) {
            if (window.Logger) window.Logger.log('Balance.load() aborted: projId is missing or invalid', 'BALANCE');
            return;
        }

        UI.showLoader("Carregando balanceamento...");
        try {
            try {
                const sessionData = await API.get('/api/manual-balance/session', { project_id: projId });
                this.manualSession = sessionData.session || null;
                this.updateManualToolbar();
            } catch (_) { this.manualSession = null; this.updateManualToolbar(); }
            // Load saved project capacities
            try {
                await this.loadProjectCapacities(projId);
            } catch (cErr) {
                if (window.Logger) window.Logger.log(`loadProjectCapacities warning: ${cErr.message}`, 'BALANCE');
            }

            // Load unique lists for filter options if not loaded
            try {
                await this.loadFiltersList(projId);
            } catch (fErr) {
                if (window.Logger) window.Logger.log(`loadFiltersList warning: ${fErr.message}`, 'BALANCE');
            }

            // Prepare filters
            const wcVal = this.cleanFilterVal(document.getElementById('balance-filter-wc') ? document.getElementById('balance-filter-wc').value : '');
            const gpmVal = this.cleanFilterVal(document.getElementById('balance-filter-gpm') ? document.getElementById('balance-filter-gpm').value : '');
            const condVal = this.cleanFilterVal(document.getElementById('balance-filter-condition') ? document.getElementById('balance-filter-condition').value : '');
            const groupVal = document.getElementById('balance-groupby') ? document.getElementById('balance-groupby').value : 'none';
            const horizVal = document.getElementById('balance-filter-horizon') ? document.getElementById('balance-filter-horizon').value : '12';

            const filters = {
                project_id: projId,
                work_center: wcVal,
                gpm: gpmVal,
                condition_code: condVal,
                item_identifiers: this.getIdentifierFilter(),
                plan_ids: this.getPlanFilter(),
                item_ids: this.getItemFilter(),
                grouping: groupVal,
                horizon: horizVal,
                manual_session_id: this.manualSession?.id || ''
            };

            if (window.Logger) window.Logger.log(`Fetching balance data with filters: ${JSON.stringify(filters)}`, 'BALANCE');
            this.data = await API.get('/api/balance', filters);
            if (window.Logger) window.Logger.log(`Fetched balance data: stops=${this.data?.stops?.length}, total_hh=${this.data?.kpis?.total_hh}`, 'BALANCE');
            
            // Update KPIs
            this.updateKPIs();

            // Render Graph
            this.renderChart();

            // Render Heatmap
            await this.renderHeatmap();

        } catch (err) {
            if (window.Logger) window.Logger.log(`ERROR in Balance.load: ${err.message}\n${err.stack}`, 'BALANCE');
            UI.showToast(`Erro ao carregar dados do balanceamento: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async renderHeatmap() {
        if (!this.data || !this.data.stops) return;
        const rowByEl = document.getElementById('heatmap-rows-by');
        const rowBy = rowByEl ? rowByEl.value : 'specialty';
        let rowHeader = 'Especialidades';
        if (rowBy === 'work_center') rowHeader = 'Centro de Trabalho';
        if (rowBy === 'gpm') rowHeader = 'GPM';
        if (rowBy === 'plans') rowHeader = 'Plano';
        
        let heatmapData = { ...this.data, stops: this.getVisibleStops() };
        if (rowBy !== 'specialty') {
            heatmapData = await API.get('/api/balance', {
                project_id: window.App.currentProjectId,
                work_center: this.cleanFilterVal(document.getElementById('balance-filter-wc')?.value || ''),
                gpm: this.cleanFilterVal(document.getElementById('balance-filter-gpm')?.value || ''),
                condition_code: this.cleanFilterVal(document.getElementById('balance-filter-condition')?.value || ''),
                item_identifiers: this.getIdentifierFilter(),
                plan_ids: this.getPlanFilter(),
                item_ids: this.getItemFilter(),
                horizon: document.getElementById('balance-filter-horizon')?.value || '12',
                grouping: rowBy,
                manual_session_id: this.manualSession?.id || ''
            });
        }

        UI.renderHeatmap('balance-heatmap-wrapper', heatmapData, {
            valueKey: this.currentChartType,
            rowGrouping: rowBy,
            rowHeader: rowHeader,
            capacities: this.getEffectiveCapacities(),
            alignWithChart: true
        });

        const subtitleEl = document.getElementById('heatmap-subtitle');
        if (subtitleEl) subtitleEl.innerText = `Intensidade de ${this.currentChartType.toUpperCase()} por ${rowHeader} ao longo das paradas.`;
    },

    updateKPIs() {
        if (!this.data || !this.data.kpis) return;
        const k = this.data.kpis;
        const numStops = this.data.stops ? this.data.stops.length : 0;
        
        const elTotalHH = document.getElementById('b-kpi-total-hh');
        if (elTotalHH) elTotalHH.innerText = `${(k.total_hh || 0).toFixed(1).replace('.', ',')} HH`;
        const elSubTotalHH = document.getElementById('b-kpi-sub-total-hh');
        if (elSubTotalHH) elSubTotalHH.innerText = `Horizonte de ${numStops} paradas`;

        const elAvgHH = document.getElementById('b-kpi-avg-hh');
        if (elAvgHH) elAvgHH.innerText = `${(k.avg_hh || 0).toFixed(1).replace('.', ',')} HH`;
        const elSubAvgHH = document.getElementById('b-kpi-sub-avg-hh');
        if (elSubAvgHH) elSubAvgHH.innerText = `Média por parada`;

        const elAvgHC = document.getElementById('b-kpi-avg-hc');
        if (elAvgHC) elAvgHC.innerText = `${Math.ceil(k.avg_headcount || 0)} pessoas`;
        const elSubAvgHC = document.getElementById('b-kpi-sub-avg-hc');
        if (elSubAvgHC) elSubAvgHC.innerText = `Teto médio por parada`;

        const elMaxHC = document.getElementById('b-kpi-max-hc');
        if (elMaxHC) elMaxHC.innerText = `${k.max_headcount || 0} pessoas`;
        const elSubMaxHC = document.getElementById('b-kpi-sub-max-hc');
        if (elSubMaxHC) elSubMaxHC.innerText = `Pico na Parada (Cont. ${k.busy_stop || '-'})`;

        // Calculate Variação Máxima (Pico Máx - Pico Mín)
        let maxV = 0, minV = 0, unitStr = '';
        if (this.currentChartType === 'hh') {
            const hhVals = (this.data.stops || []).map(s => parseFloat(s.total_hh) || 0);
            maxV = hhVals.length ? Math.max(...hhVals) : 0;
            minV = hhVals.length ? Math.min(...hhVals) : 0;
            unitStr = 'HH';
        } else if (this.currentChartType === 'headcount') {
            const hcVals = (this.data.stops || []).map(s => parseInt(s.headcount_needed) || 0);
            maxV = hcVals.length ? Math.max(...hcVals) : 0;
            minV = hcVals.length ? Math.min(...hcVals) : 0;
            unitStr = 'pess.';
        } else {
            const ordVals = (this.data.stops || []).map(s => parseInt(s.total_orders) || 0);
            maxV = ordVals.length ? Math.max(...ordVals) : 0;
            minV = ordVals.length ? Math.min(...ordVals) : 0;
            unitStr = 'ordens';
        }

        const diff = maxV - minV;
        const pct = minV > 0 ? Math.round((diff / minV) * 100) : (maxV > 0 ? 100 : 0);
        const formattedDiff = this.currentChartType === 'hh' ? diff.toFixed(1).replace('.', ',') : diff;
        const fmtMax = this.currentChartType === 'hh' ? maxV.toFixed(1).replace('.', ',') : maxV;
        const fmtMin = this.currentChartType === 'hh' ? minV.toFixed(1).replace('.', ',') : minV;

        const varEl = document.getElementById('b-kpi-variation');
        if (varEl) varEl.innerText = `${formattedDiff} ${unitStr} (+${pct}%)`;
        const subVarEl = document.getElementById('b-kpi-sub-variation');
        if (subVarEl) subVarEl.innerText = `Pico Máx (${fmtMax}) — Mín (${fmtMin})`;

        this.updateMetaKPIs();
    },

    updateCapacityUtilizationKPI() {
        const valueEl = document.getElementById('b-kpi-capacity-utilization');
        const descEl = document.getElementById('b-kpi-sub-capacity-utilization');
        const iconEl = document.getElementById('b-kpi-utilization-icon');
        if (!valueEl || !descEl) return;

        const avgHH = Number(this.data?.kpis?.avg_hh) || 0;
        const capacity = this.getCapacityHHContext();
        if (!capacity.valid || capacity.totalHH <= 0) {
            valueEl.innerText = 'Sem capacidade';
            valueEl.className = 'kpi-value';
            descEl.innerText = 'Preencha o efetivo disponível por parada';
            if (iconEl) iconEl.className = 'kpi-icon bg-blue-light';
            return;
        }

        const utilization = (avgHH / capacity.totalHH) * 100;
        const fmt = value => Number(value).toFixed(1).replace('.', ',');
        valueEl.innerText = `${fmt(utilization)}%`;
        valueEl.className = `kpi-value${utilization > 100 ? ' txt-danger' : ''}`;
        descEl.innerText = `${fmt(avgHH)} HH utilizados ÷ ${fmt(capacity.totalHH)} HH disponíveis`;
        if (iconEl) iconEl.className = `kpi-icon ${utilization > 100 ? 'bg-red-light' : 'bg-blue-light'}`;
    },

    getEffectiveCapacities() {
        const mecVal = parseFloat(document.getElementById('balance-cap-mec')?.value);
        const eleVal = parseFloat(document.getElementById('balance-cap-ele')?.value);
        const solVal = parseFloat(document.getElementById('balance-cap-sol')?.value);

        const capMec = !isNaN(mecVal) && mecVal > 0 ? mecVal : null;
        const capEle = !isNaN(eleVal) && eleVal > 0 ? eleVal : null;
        const capSol = !isNaN(solVal) && solVal > 0 ? solVal : null;

        const hasAny = capMec !== null || capEle !== null || capSol !== null;
        const capTotal = (capMec || 0) + (capEle || 0) + (capSol || 0);

        return {
            hasAny: hasAny,
            mec: capMec,
            ele: capEle,
            sol: capSol,
            total: hasAny && capTotal > 0 ? capTotal : null
        };
    },

    getCapacityHHContext() {
        const caps = this.getEffectiveCapacities();
        const result = {
            valid: false, totalHH: 0, totalPeople: 0,
            hhByTrade: { ele: null, mec: null, sol: null },
            hoursByTrade: { ele: null, mec: null, sol: null },
            configuredTrades: [], unresolvedTrades: [],
            baseHours: Number(this.data?.hours_per_person) || 9.1,
            toolTimePercent: Number(this.data?.tool_time_percent ?? 100),
            productiveHoursPerPerson: Number(this.data?.productive_hours) || 9.1
        };
        if (!caps.hasAny || !this.data) return result;

        const effectiveHours = result.productiveHoursPerPerson;
        if (!Number.isFinite(effectiveHours) || effectiveHours <= 0) return result;
        ['ele', 'mec', 'sol'].forEach(trade => {
            const people = caps[trade];
            if (people === null) return;
            result.configuredTrades.push(trade);
            result.totalPeople += people;
            result.hoursByTrade[trade] = effectiveHours;
            result.hhByTrade[trade] = people * effectiveHours;
            result.totalHH += people * effectiveHours;
        });
        result.valid = result.configuredTrades.length > 0;
        return result;
    },

    getEffectiveStopCapacities() {
        // Efetivo informado já é o total de toda a parada (dia 1 + dia 2 + ...).
        return this.getEffectiveCapacities();
    },

    async loadProjectCapacities(projId) {
        const id = projId || window.App?.currentProjectId;
        if (!id) return;
        const res = await API.get(`/api/projects/${id}/capacities`);
        if (!res) return;
        
        const eleInput = document.getElementById('balance-cap-ele');
        const mecInput = document.getElementById('balance-cap-mec');
        const solInput = document.getElementById('balance-cap-sol');

        if (eleInput) eleInput.value = res.ele !== null && res.ele !== undefined ? res.ele : '';
        if (mecInput) mecInput.value = res.mec !== null && res.mec !== undefined ? res.mec : '';
        if (solInput) solInput.value = res.sol !== null && res.sol !== undefined ? res.sol : '';
    },

    async saveProjectCapacities() {
        const id = window.App?.currentProjectId;
        if (!id) return;
        const eleVal = document.getElementById('balance-cap-ele')?.value;
        const mecVal = document.getElementById('balance-cap-mec')?.value;
        const solVal = document.getElementById('balance-cap-sol')?.value;

        try {
            await API.put(`/api/projects/${id}/capacities`, {
                ele: eleVal !== '' ? parseFloat(eleVal) : null,
                mec: mecVal !== '' ? parseFloat(mecVal) : null,
                sol: solVal !== '' ? parseFloat(solVal) : null
            });
        } catch (err) {
            if (window.Logger) window.Logger.log(`saveProjectCapacities error: ${err.message}`, 'BALANCE');
        }
    },

    getVisibleStops() {
        const stops = this.data?.stops || [];
        const mode = document.getElementById('balance-filter-headcount-status')?.value || '';
        if (!mode) return stops;
        const caps = this.getEffectiveCapacities();
        const exceeded = (stop, trade) => caps[trade] !== null && (Number(stop[`${trade}_headcount_needed`]) || 0) > caps[trade];
        return stops.filter(stop => {
            const ele = exceeded(stop, 'ele');
            const mec = exceeded(stop, 'mec');
            const sol = exceeded(stop, 'sol');
            if (mode === 'any_exceeded') return ele || mec || sol;
            if (mode === 'ele_exceeded') return ele;
            if (mode === 'mec_exceeded') return mec;
            if (mode === 'sol_exceeded') return sol;
            if (mode === 'within') return !ele && !mec && !sol;
            return true;
        });
    },

    getEffectiveTargetMeta() {
        const caps = this.getEffectiveCapacities();
        if (!caps.hasAny || !this.data) return null;

        const rawVal = caps.total || 0;
        if (rawVal <= 0) return null;

        if (this.currentChartType === 'hh') {
            const ctx = this.getCapacityHHContext();

            // One project-level productive-hours rule applies to every discipline.
            if (!ctx.valid) return null;

            const hhTarget = ctx.totalHH;
            const fmt = (v) => Number(v).toFixed(1).replace('.', ',');
            const formula = `${ctx.totalPeople} pess. × ${fmt(ctx.baseHours)} h × ${fmt(ctx.toolTimePercent)}%`;
            let labelText = `CAPACIDADE TOTAL: ${fmt(hhTarget)} HH (${formula})`;

            if (ctx.configuredTrades.length === 1) {
                const trade = ctx.configuredTrades[0];
                const tradeLabel = trade.toUpperCase();
                labelText = `CAPACIDADE ${tradeLabel}: ${fmt(hhTarget)} HH (${formula})`;
            }

            return {
                targetVal: hhTarget,
                unitLabel: 'HH',
                headcountMeta: ctx.totalPeople,
                labelText
            };
        } else if (this.currentChartType === 'headcount') {
            return {
                targetVal: rawVal,
                unitLabel: 'pessoas',
                headcountMeta: rawVal,
                labelText: `CAPACIDADE TOTAL: ${rawVal} pessoas`
            };
        }
        return null;
    },

    updateMetaKPIs() {
        if (!this.data || !this.data.stops) return;
        this.updateCapacityUtilizationKPI();
        const caps = this.getEffectiveCapacities();
        const statusVal = document.getElementById('b-kpi-meta-status');
        const statusSub = document.getElementById('b-kpi-sub-meta-status');
        const metaIcon = document.getElementById('b-kpi-meta-icon');

        if (!statusVal || !statusSub) return;

        if (!caps.hasAny) {
            statusVal.innerText = 'Sem Capacidade';
            statusVal.className = 'kpi-value';
            statusSub.innerText = 'Preencha os limites (MEC, ELE, SOL)';
            if (metaIcon) metaIcon.className = 'kpi-icon bg-green-light';
            return;
        }

        const stops = this.getVisibleStops();
        let maxMec = 0, maxEle = 0, maxSol = 0, maxTot = 0;
        stops.forEach(s => {
            if ((s.mec_headcount_needed || 0) > maxMec) maxMec = s.mec_headcount_needed || 0;
            if ((s.ele_headcount_needed || 0) > maxEle) maxEle = s.ele_headcount_needed || 0;
            if ((s.sol_headcount_needed || 0) > maxSol) maxSol = s.sol_headcount_needed || 0;
            if ((s.headcount_needed || 0) > maxTot) maxTot = s.headcount_needed || 0;
        });

        const exceededTrades = [];
        if (caps.mec !== null && maxMec > caps.mec) exceededTrades.push(`MEC +${maxMec - caps.mec}`);
        if (caps.ele !== null && maxEle > caps.ele) exceededTrades.push(`ELE +${maxEle - caps.ele}`);
        if (caps.sol !== null && maxSol > caps.sol) exceededTrades.push(`SOL +${maxSol - caps.sol}`);

        const subDetails = `MEC: max ${maxMec}/${caps.mec ?? '-'} | ELE: max ${maxEle}/${caps.ele ?? '-'} | SOL: max ${maxSol}/${caps.sol ?? '-'}`;

        if (exceededTrades.length > 0) {
            statusVal.innerText = `Excede (${exceededTrades.join(', ')})`;
            statusVal.className = 'kpi-value txt-danger';
            statusSub.innerText = subDetails;
            if (metaIcon) metaIcon.className = 'kpi-icon bg-red-light';
        } else {
            statusVal.innerText = 'Dentro da Capacidade';
            statusVal.className = 'kpi-value';
            statusSub.innerText = `100% das paradas dentro dos limites • ${subDetails}`;
            if (metaIcon) metaIcon.className = 'kpi-icon bg-green-light';
        }
    },

    setChartType(type) {
        this.currentChartType = type;
        
        // Update toggles styling
        ['hh', 'hc', 'orders'].forEach(t => {
            const btn = document.getElementById(`btn-chart-toggle-${t}`);
            if (btn) btn.classList.remove('active');
        });
        
        let targetId = 'btn-chart-toggle-hh';
        if (type === 'headcount') targetId = 'btn-chart-toggle-hc';
        if (type === 'orders') targetId = 'btn-chart-toggle-orders';
        const targetBtn = document.getElementById(targetId);
        if (targetBtn) targetBtn.classList.add('active');

        this.updateMetaKPIs();
        this.renderChart();
        this.renderHeatmap();
    },

    renderChart() {
        if (!this.data) return;

        let valKey = 'total_hh';
        let lbl = 'HH Projetado';
        
        if (this.currentChartType === 'headcount') {
            valKey = 'headcount_needed';
            lbl = 'Efetivo Total';
        } else if (this.currentChartType === 'orders') {
            valKey = 'total_orders';
            lbl = 'Quantidade Ordens';
        }

        const groupEl = document.getElementById('balance-groupby');
        const groupby = groupEl ? groupEl.value : 'specialty';
        const targetObj = this.getEffectiveTargetMeta();
        const capacities = this.getEffectiveCapacities();

        const visibleStops = this.getVisibleStops();
        UI.renderBarChart('balance-main-chart-wrapper', visibleStops, {
            valueKey: valKey,
            labelText: lbl,
            groupBy: groupby,
            capacities: capacities,
            targetMeta: targetObj ? targetObj.targetVal : null,
            targetMetaLabel: targetObj ? targetObj.labelText : null,
            overflowX: 'visible',
            onClick: (stop) => {
                window.App.openStopDetailsDrawer(stop.counter);
            },
            onDrop: (itemData, targetStop) => {
                if (this.manualSession && itemData.manual) {
                    this.moveManualItems(itemData.itemIds || [itemData.itemId], targetStop.counter);
                    return;
                }
                this.handleItemDrop(
                    itemData.itemId,
                    itemData.planId,
                    itemData.planCode,
                    targetStop.stop_num,
                    targetStop.counter
                );
            }
        });

        const chartCardBody = document.querySelector('#balance-chart-card .card-body');
        if (chartCardBody) chartCardBody.scrollLeft = 0;
        const chartWrapper = document.getElementById('balance-main-chart-wrapper');
        if (chartWrapper) chartWrapper.scrollLeft = 0;

        const totalStops = this.data.stops?.length || 0;
        document.getElementById('balance-chart-title').innerText = `${lbl} por Parada (${visibleStops.length}/${totalStops})`;
    },

    async openStopDetails(stopCounter) {
        const projId = window.App.currentProjectId;
        API.log("openStopDetails entry. stopCounter=" + stopCounter + " projId=" + projId, "balance.js");
        if (!projId) return;

        UI.showLoader(`Carregando detalhes da parada ${stopCounter}...`);
        try {
            // Apply current filters to drill-down list
            const params = {
                project_id: projId,
                work_center: document.getElementById('balance-filter-wc').value,
                gpm: document.getElementById('balance-filter-gpm').value,
                condition_code: document.getElementById('balance-filter-condition').value,
                horizon: document.getElementById('balance-filter-horizon')?.value || '12',
                item_identifiers: this.getIdentifierFilter()
                ,plan_ids: this.getPlanFilter(), item_ids: this.getItemFilter(),
                manual_session_id: this.manualSession?.id || ''
            };

            API.log("Calling API.get for stop " + stopCounter + " with params=" + JSON.stringify(params), "balance.js");
            const data = await API.get(`/api/balance/stop/${stopCounter}`, params);
            API.log("API.get response: orders=" + data.orders.length + " stop_info=" + JSON.stringify(data.stop_info), "balance.js");
            
            const info = data.stop_info;
            document.getElementById('manual-book-controls')?.classList.add('hidden');
            document.getElementById('manual-stop-return-dropzone')?.classList.toggle('hidden', !this.manualSession);
            document.getElementById('btn-panel-book')?.classList.remove('active');
            document.getElementById('btn-panel-stop')?.classList.add('active');
            const listTitle = document.getElementById('inline-list-title');
            if (listTitle) listTitle.innerText = 'Lista de Ordens';
            const subtitle = document.getElementById('inline-panel-subtitle');
            if (subtitle) subtitle.innerHTML = `Contador <span id="inline-stop-counter">${stopCounter}</span>`;
            
            // Compute distributions within stop
            const wcDist = {};
            const gpmDist = {};
            
            data.orders.forEach(o => {
                const wc = o.work_center || 'Sem Centro';
                const gpm = o.gpm || 'Sem GPM';
                const hc = o.headcount !== null ? o.headcount : 1;
                const hh = o.duration_hours * hc;
                
                wcDist[wc] = (wcDist[wc] || 0) + hh;
                gpmDist[gpm] = (gpmDist[gpm] || 0) + hh;
            });

            // Check if we are on the Balance page
            const balanceSection = document.getElementById('section-balance');
            const isBalancePage = (window.location.hash === '#balance') || (balanceSection && !balanceSection.classList.contains('hidden'));
            API.log("Page check: isBalancePage=" + isBalancePage + " hash=" + window.location.hash, "balance.js");

            if (isBalancePage) {
                // Populate Inline (split-screen) Details
                try {
                    const elStopNum = document.getElementById('inline-stop-num');
                    const elStopCounter = document.getElementById('inline-stop-counter');
                    const elSumOrders = document.getElementById('inline-sum-orders');
                    const elSumHh = document.getElementById('inline-sum-hh');
                    const elSumHc = document.getElementById('inline-sum-hc');

                    if (!elStopNum || !elStopCounter || !elSumOrders || !elSumHh || !elSumHc) {
                        throw new Error(`Elementos do resumo inline não encontrados: Num=${!!elStopNum}, Counter=${!!elStopCounter}, Orders=${!!elSumOrders}, HH=${!!elSumHh}, HC=${!!elSumHc}`);
                    }

                    elStopNum.innerText = info.stop_num;
                    elStopCounter.innerText = info.counter;
                    elSumOrders.innerText = info.total_orders;
                    elSumHh.innerText = Math.round(info.total_hh) + ' HH';
                    elSumHc.innerText = `${info.headcount_needed} pessoas na parada`;
                } catch (domErr) {
                    alert("Erro ao preencher resumo inline: " + domErr.message);
                    throw domErr;
                }

                // Trades & WC/GPM distribution chips (compact)
                try {
                    const tradeContainer = document.getElementById('inline-dist-trades');
                    if (tradeContainer) {
                        tradeContainer.innerHTML = '';
                        const mecHh = Math.round(info.mec_hh || 0);
                        const eleHh = Math.round(info.ele_hh || 0);
                        const solHh = Math.round(info.sol_hh || 0);
                        const mecHc = info.mec_headcount_needed || 0;
                        const eleHc = info.ele_headcount_needed || 0;
                        const solHc = info.sol_headcount_needed || 0;

                        const tradeChips = [];
                        if (mecHh > 0 || mecHc > 0) {
                            tradeChips.push(`<span style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:4px; padding:2px 6px; font-weight:700; color:#1E40AF; display:inline-flex; align-items:center; gap:3px;"><span>🔧</span> MEC: ${mecHc}p (${mecHh}h)</span>`);
                        }
                        if (eleHh > 0 || eleHc > 0) {
                            tradeChips.push(`<span style="background:#FEFCE8; border:1px solid #FEF08A; border-radius:4px; padding:2px 6px; font-weight:700; color:#854D0E; display:inline-flex; align-items:center; gap:3px;"><span>⚡</span> ELE: ${eleHc}p (${eleHh}h)</span>`);
                        }
                        if (solHh > 0 || solHc > 0) {
                            tradeChips.push(`<span style="background:#FFF1F2; border:1px solid #FECDD3; border-radius:4px; padding:2px 6px; font-weight:700; color:#9F1239; display:inline-flex; align-items:center; gap:3px;"><span>🔥</span> SOL: ${solHc}p (${solHh}h)</span>`);
                        }
                        tradeContainer.innerHTML = tradeChips.length > 0 ? tradeChips.join('') : '<span style="color:#94A3B8;">Sem especialidades definidas</span>';
                    }

                    const wcContainer = document.getElementById('inline-dist-wc');
                    if (wcContainer) {
                        wcContainer.innerHTML = '';
                        const topWcs = Object.keys(wcDist).sort((a,b) => wcDist[b] - wcDist[a]).slice(0, 3);
                        topWcs.forEach(wc => {
                            wcContainer.innerHTML += `<span style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:4px; padding:1px 5px; font-weight:600; color:#334155;">${wc}: ${Math.round(wcDist[wc])}h</span>`;
                        });
                        if (topWcs.length === 0) wcContainer.innerHTML = '<span style="color:#94A3B8;">-</span>';
                    }

                    const gpmContainer = document.getElementById('inline-dist-gpm');
                    if (gpmContainer) {
                        gpmContainer.innerHTML = '';
                        const topGpms = Object.keys(gpmDist).sort((a,b) => gpmDist[b] - gpmDist[a]).slice(0, 3);
                        topGpms.forEach(gpm => {
                            gpmContainer.innerHTML += `<span style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:4px; padding:1px 5px; font-weight:600; color:#334155;">GPM ${gpm}: ${Math.round(gpmDist[gpm])}h</span>`;
                        });
                        if (topGpms.length === 0) gpmContainer.innerHTML = '<span style="color:#94A3B8;">-</span>';
                    }
                } catch (distErr) {
                    console.error("Dist chips error:", distErr);
                }

                // Orders Table (simplified & tailored rows: Mover, Item/ID, Plano Atrelado, Ciclo, Carga HH)
                try {
                    const tbody = document.getElementById('inline-orders-tbody');
                    if (!tbody) {
                        throw new Error("Elemento inline-orders-tbody não encontrado!");
                    }
                    tbody.innerHTML = '';
                    this.inlineOrdersData = [...data.orders];

                    if (data.orders.length === 0) {
                        tbody.innerHTML = `<tr><td colspan="5" class="empty-table-cell" style="padding: 15px; text-align: center; color: var(--text-muted);">Nenhuma ordem programada para esta parada.</td></tr>`;
                    } else {
                        data.orders.forEach(o => {
                            const isLocked = String(o.balance_state || '').toUpperCase() === 'FIXED';
                            const mecHc = o.mec_headcount || 0;
                            const mecH = o.mec_hours || 0.0;
                            const eleHc = o.ele_headcount || 0;
                            const eleH = o.ele_hours || 0.0;
                            const solHc = o.sol_headcount || 0;
                            const solH = o.sol_hours || 0.0;

                            const tradeHh = (mecHc * mecH) + (eleHc * eleH) + (solHc * solH);
                            const tradeHc = mecHc + eleHc + solHc;
                            
                            const hc = tradeHc > 0 ? tradeHc : (o.headcount !== null && o.headcount !== undefined ? parseInt(o.headcount) : 1);
                            const hh = tradeHh > 0 ? tradeHh : ((parseFloat(o.duration_hours) || 0) * hc);

                            // Trade badges
                            const tradeBadges = [];
                            if (mecHc > 0 || mecH > 0) tradeBadges.push(`<span style="background:#EFF6FF; color:#1E40AF; padding:1px 4px; border-radius:3px; font-weight:700; font-size:8px;">🔧 ${mecHc}H/${mecH}h</span>`);
                            if (eleHc > 0 || eleH > 0) tradeBadges.push(`<span style="background:#FEFCE8; color:#854D0E; padding:1px 4px; border-radius:3px; font-weight:700; font-size:8px;">⚡ ${eleHc}H/${eleH}h</span>`);
                            if (solHc > 0 || solH > 0) tradeBadges.push(`<span style="background:#FFF1F2; color:#9F1239; padding:1px 4px; border-radius:3px; font-weight:700; font-size:8px;">🔥 ${solHc}H/${solH}h</span>`);

                            const cycleStr = o.cycle ? `${o.cycle} ${o.unit || 'PRD'}` : 'Avulso';
                            const planCodeStr = o.plan_code || 'Sem Plano';
                            const planDescStr = o.plan_description || 'Item sem plano atrelado';

                            const tr = document.createElement('tr');
                            tr.className = `draggable-row${isLocked ? ' order-locked' : ''}`;
                            tr.setAttribute('draggable', !isLocked ? 'true' : 'false');
                            tr.setAttribute('data-item-id', o.id);
                            tr.setAttribute('data-plan-id', o.plan_id || '');
                            tr.setAttribute('data-plan-code', o.plan_code || '');
                            tr.dataset.sortItem = String(o.legacy_identifier || '');
                            tr.dataset.sortPlan = String(o.plan_code || '');
                            tr.dataset.sortCycle = String(Number(o.cycle) || 0);
                            tr.dataset.sortHh = String(hh);
                            
                            tr.innerHTML = `
                                <td style="text-align: center; padding: 5px 2px; vertical-align: middle; width: 54px;">
                                    <div class="inline-order-controls">
                                        <div class="drag-handle" title="${isLocked ? 'Ordem trancada' : 'Arraste esta ordem para uma coluna do gráfico'}">
                                            <svg viewBox="0 0 24 24" style="width: 14px; height: 14px; color: var(--text-muted);"><path fill="currentColor" d="M20 9H4v2h16V9zM4 15h16v-2H4v2z"/></svg>
                                        </div>
                                        <button type="button" class="inline-order-lock${isLocked ? ' locked' : ''}"
                                            title="${isLocked ? 'Destrancar ordem' : 'Trancar nesta parada e neste plano'}"
                                            onclick="event.stopPropagation(); Balance.toggleItemLock(${Number(o.id)}, ${isLocked ? 'false' : 'true'}, ${Number(stopCounter)})">${isLocked ? '🔒' : '🔓'}</button>
                                    </div>
                                </td>
                                <td style="padding: 5px 4px; vertical-align: middle; min-width: 0; overflow: hidden;">
                                    <div style="font-weight: 700; color: #0F172A; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${o.legacy_identifier}">${o.legacy_identifier}</div>
                                    <div style="font-size: 10px; color: #64748B; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${o.description || ''}">${o.description || '-'}</div>
                                    ${tradeBadges.length > 0 ? `<div style="display:flex; gap:2px; flex-wrap:wrap; margin-top:2px;">${tradeBadges.join('')}</div>` : ''}
                                </td>
                                <td style="padding: 5px 4px; vertical-align: middle; min-width: 0; overflow: hidden;">
                                    <div style="font-weight: 700; color: #0284C7; font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${planCodeStr}">${planCodeStr}</div>
                                    <div style="font-size: 10px; color: #64748B; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${planDescStr}">${planDescStr}</div>
                                </td>
                                <td style="padding: 5px 2px; text-align: center; vertical-align: middle; white-space: nowrap;">
                                    <span style="font-size: 9px; font-weight: 600; color: #334155; background: #F1F5F9; border: 1px solid #E2E8F0; padding: 1px 4px; border-radius: 4px; display: inline-block;">${cycleStr}</span>
                                </td>
                                <td style="padding: 5px 4px; text-align: right; vertical-align: middle; white-space: nowrap;">
                                    <strong style="color: #0F172A; font-size: 10.5px;">${hh.toFixed(1).replace('.', ',')} HH</strong>
                                </td>
                            `;
                            
                            // Setup Drag events
                            tr.addEventListener('dragstart', (e) => {
                                if (isLocked) { e.preventDefault(); return; }
                                tr.classList.add('dragging');
                                e.dataTransfer.effectAllowed = 'move';
                                const dragPayload = {
                                    itemId: o.id,
                                    planId: o.plan_id,
                                    planCode: o.plan_code,
                                    manual: Boolean(this.manualSession),
                                    itemIds: [Number(o.id)]
                                };
                                window.pendingDraggedItem = dragPayload;
                                API.log("dragstart fired: " + JSON.stringify(dragPayload), "balance.js");
                                e.dataTransfer.setData('text/plain', JSON.stringify(dragPayload));
                                if (this.manualSession && Number(o.cycle) > 1) {
                                    document.getElementById('manual-stop-return-dropzone')?.classList.add('drag-visible');
                                }
                            });
                            
                            tr.addEventListener('dragend', () => {
                                tr.classList.remove('dragging');
                                document.getElementById('manual-return-dropzone')?.classList.remove('drag-visible');
                                document.getElementById('manual-stop-return-dropzone')?.classList.remove('drag-visible');
                            });

                            tbody.appendChild(tr);
                        });
                    }
                    this.setupInlineTableInteractions();
                } catch (tableErr) {
                    alert("Erro ao preencher tabela de ordens inline: " + tableErr.message);
                    throw tableErr;
                }

                // Show the right col and splitter handle
                const rightCol = document.querySelector('.balance-right-col');
                const handle = document.getElementById('balance-splitter-handle');
                if (rightCol) {
                    API.log("Showing rightCol: current class list=" + rightCol.className, "balance.js");
                    rightCol.classList.remove('hidden');
                    if (handle) handle.classList.remove('hidden');
                    this.activeStopCounter = stopCounter;

                    // Automatically collapse sidebar menu to maximize workspace width
                    const sidebar = document.getElementById('sidebar');
                    if (sidebar) sidebar.classList.add('collapsed');

                    rightCol.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    setTimeout(() => {
                        API.log("Re-rendering chart after rightCol display...", "balance.js");
                        this.renderChart(); // Re-render to adapt width to the new split-screen (2/3 left) after layout updates
                    }, 50);
                } else {
                    API.log("ERROR: Element .balance-right-col not found in DOM!", "balance.js");
                    alert("Elemento balance-right-col não encontrado no DOM!");
                }
            } else {
                document.getElementById('drawer-stop-num').innerText = info.stop_num;
                document.getElementById('drawer-stop-counter').innerText = info.counter;

                // Summaries
                document.getElementById('drawer-sum-orders').innerText = info.total_orders;
                document.getElementById('drawer-sum-hh').innerText = Math.round(info.total_hh) + ' HH';
                document.getElementById('drawer-sum-hc').innerText = `${info.headcount_needed} pessoas`;

                // WC Distribution
                const wcContainer = document.getElementById('drawer-dist-wc');
                wcContainer.innerHTML = '';
                Object.keys(wcDist).sort((a,b) => wcDist[b] - wcDist[a]).forEach(wc => {
                    wcContainer.innerHTML += `<div class="dist-item"><span class="dist-lbl">${wc}</span><span class="dist-val">${Math.round(wcDist[wc])} HH</span></div>`;
                });
                if (Object.keys(wcDist).length === 0) wcContainer.innerHTML = '<span class="subtitle">Sem dados</span>';

                // GPM Distribution
                const gpmContainer = document.getElementById('drawer-dist-gpm');
                gpmContainer.innerHTML = '';
                Object.keys(gpmDist).sort((a,b) => gpmDist[b] - gpmDist[a]).forEach(gpm => {
                    gpmContainer.innerHTML += `<div class="dist-item"><span class="dist-lbl">GPM ${gpm}</span><span class="dist-val">${Math.round(gpmDist[gpm])} HH</span></div>`;
                });
                if (Object.keys(gpmDist).length === 0) gpmContainer.innerHTML = '<span class="subtitle">Sem dados</span>';

                // Render Orders Table
                const tbody = document.getElementById('drawer-orders-tbody');
                tbody.innerHTML = '';

                if (data.orders.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="11" class="empty-table-cell">Nenhuma ordem programada para esta parada.</td></tr>`;
                } else {
                    data.orders.forEach(o => {
                        const hc = o.headcount !== null ? o.headcount : 1;
                        const hh = o.duration_hours * hc;
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td><strong>${o.legacy_identifier}</strong></td>
                            <td>${o.object_code}</td>
                            <td title="${o.description}" style="max-width:200px; overflow:hidden; text-overflow:ellipsis;">${o.description}</td>
                            <td><strong>${o.plan_code}</strong></td>
                            <td>${o.work_center}</td>
                            <td>${o.gpm}</td>
                            <td>${o.condition_code}</td>
                            <td>${o.priority}</td>
                            <td>${o.duration_hours}</td>
                            <td>${o.headcount !== null ? o.headcount : '<span class="badge badge-warning">Pendente</span>'}</td>
                            <td><strong>${hh.toFixed(1).replace('.', ',')}</strong></td>
                        `;
                        tbody.appendChild(tr);
                    });
                }

                // Open Drawer
                document.getElementById('stop-details-drawer').classList.remove('hidden');
            }
        } catch (err) {
            API.log("FATAL EXCEPTION in openStopDetails: " + err.message + " | stack: " + err.stack, "balance.js");
            alert("Erro fatal em openStopDetails: " + err.message + "\nStack: " + err.stack);
            UI.showToast(`Erro ao carregar detalhes da parada: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    inlineSortState: { key: 'item', direction: 'asc' },

    setupInlineTableInteractions() {
        const table = document.getElementById('inline-orders-table');
        const tbody = document.getElementById('inline-orders-tbody');
        if (!table || !tbody) return;

        // Restore user-adjusted widths for this browser if stored and sane
        try {
            const saved = JSON.parse(localStorage.getItem('pm13_inline_order_widths_v2') || '{}');
            table.querySelectorAll('col[data-col-key]').forEach(col => {
                const key = col.dataset.colKey;
                const width = Number(saved[key]);
                if (width >= 20) {
                    col.style.width = `${width}px`;
                }
            });
        } catch (_) {}

        const sortRows = (key, direction) => {
            const rows = Array.from(tbody.querySelectorAll('tr.draggable-row'));
            rows.sort((a, b) => {
                const av = a.dataset[`sort${key[0].toUpperCase()}${key.slice(1)}`] || '';
                const bv = b.dataset[`sort${key[0].toUpperCase()}${key.slice(1)}`] || '';
                if (key === 'cycle' || key === 'hh') return (Number(av) - Number(bv)) * (direction === 'asc' ? 1 : -1);
                return av.localeCompare(bv, 'pt-BR', { numeric: true, sensitivity: 'base' }) * (direction === 'asc' ? 1 : -1);
            });
            rows.forEach(row => tbody.appendChild(row));
        };

        table.querySelectorAll('th[data-inline-sort]').forEach(th => {
            const key = th.dataset.inlineSort;
            th.onclick = (event) => {
                if (event.target.closest('.column-resizer')) return;
                const direction = this.inlineSortState.key === key && this.inlineSortState.direction === 'asc' ? 'desc' : 'asc';
                this.inlineSortState = { key, direction };
                sortRows(key, direction);
                table.querySelectorAll('th[data-inline-sort]').forEach(header => {
                    const active = header.dataset.inlineSort === key;
                    header.classList.toggle('sort-active', active);
                    const indicator = header.querySelector('.sort-indicator');
                    if (indicator) indicator.innerText = active ? (direction === 'asc' ? '▲' : '▼') : '';
                });
            };
        });

        // Apply the current ordering again when another stop is opened.
        sortRows(this.inlineSortState.key, this.inlineSortState.direction);
        const activeHeader = table.querySelector(`th[data-inline-sort="${this.inlineSortState.key}"]`);
        if (activeHeader) {
            activeHeader.classList.add('sort-active');
            const indicator = activeHeader.querySelector('.sort-indicator');
            if (indicator) indicator.innerText = this.inlineSortState.direction === 'asc' ? '▲' : '▼';
        }

        table.querySelectorAll('.column-resizer').forEach(handle => {
            handle.onmousedown = (event) => {
                event.preventDefault();
                event.stopPropagation();
                const th = handle.closest('th');
                const headerCells = Array.from(th.parentElement.children);
                const index = headerCells.indexOf(th);
                const col = table.querySelectorAll('col')[index];
                if (!col) return;
                const startX = event.clientX;
                const startWidth = th.getBoundingClientRect().width;
                document.body.classList.add('resizing-table-column');

                const onMove = (moveEvent) => {
                    const colKey = col.dataset.colKey;
                    const minW = colKey === 'move' ? 26 : (colKey === 'cycle' || colKey === 'hh' ? 40 : 50);
                    const newWidth = Math.max(minW, Math.round(startWidth + moveEvent.clientX - startX));
                    col.style.width = `${newWidth}px`;
                };
                const onUp = () => {
                    document.body.classList.remove('resizing-table-column');
                    window.removeEventListener('mousemove', onMove);
                    window.removeEventListener('mouseup', onUp);
                    try {
                        const widths = {};
                        table.querySelectorAll('col[data-col-key]').forEach(c => {
                            widths[c.dataset.colKey] = Math.round(c.getBoundingClientRect().width);
                        });
                        localStorage.setItem('pm13_inline_order_widths_v2', JSON.stringify(widths));
                    } catch (_) {}
                };
                window.addEventListener('mousemove', onMove);
                window.addEventListener('mouseup', onUp);
            };
        });
    },

    exportStopOrders(stopCounter) {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        const params = {
            type: 'orders',
            format: 'xlsx',
            project_id: projId,
            stop_counter: stopCounter,
            work_center: document.getElementById('balance-filter-wc').value,
            gpm: document.getElementById('balance-filter-gpm').value,
            condition_code: document.getElementById('balance-filter-condition').value,
            horizon: document.getElementById('balance-filter-horizon')?.value || '12',
            item_identifiers: this.getIdentifierFilter()
            ,plan_ids: this.getPlanFilter(), item_ids: this.getItemFilter()
        };

        const query = Object.keys(params)
            .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
            .join('&');
            
        window.open(`/api/export?${query}`, '_blank');
    },

    exportManagerialWorkbook() {
        const projId = window.App.currentProjectId;
        if (!projId || !this.data) return;
        const caps = this.getEffectiveCapacities();
        const params = {
            type: 'balance-report', format: 'xlsx', project_id: projId,
            grouping: document.getElementById('balance-groupby')?.value || 'none',
            horizon: document.getElementById('balance-filter-horizon')?.value || '12',
            work_center: document.getElementById('balance-filter-wc')?.value || '',
            gpm: document.getElementById('balance-filter-gpm')?.value || '',
            condition_code: document.getElementById('balance-filter-condition')?.value || '',
            headcount_status: document.getElementById('balance-filter-headcount-status')?.value || '',
            item_identifiers: this.getIdentifierFilter(),
            plan_ids: this.getPlanFilter(), item_ids: this.getItemFilter(),
            manual_session_id: this.manualSession?.id || '',
            cap_ele: caps.ele ?? '', cap_mec: caps.mec ?? '', cap_sol: caps.sol ?? ''
        };
        const query = new URLSearchParams(params).toString();
        window.open(`/api/export?${query}`, '_blank');
    },

    filtersLoadedProjId: null,

    async loadFiltersList(projId) {
        if (this.filtersLoadedProjId === projId) return;
        if (this.filtersLoadedProjId !== null && this.filtersLoadedProjId !== projId) {
            this.selectedIdentifiers.clear(); this.selectedPlanIds.clear(); this.selectedItemIds.clear();
        }
        this.filtersLoadedProjId = projId;
        // Fetch items to find unique wc and gpm
        const allItemsData = await API.get('/api/items', { project_id: projId, limit: 100000 });
        const allPlansData = await API.get('/api/plans', { project_id: projId, status: 'ACTIVE', limit: 100000 });
        const gpms = new Set();
        const wcs = new Set();
        allItemsData.items.forEach(item => {
            if (item.gpm) gpms.add(item.gpm);
            if (item.work_center) wcs.add(item.work_center);
        });

        const wcSelect = document.getElementById('balance-filter-wc');
        const gpmSelect = document.getElementById('balance-filter-gpm');
        const idOptions = document.getElementById('balance-id-filter-options');

        if (!wcSelect || !gpmSelect) return;

        const prevWc = wcSelect.value;
        const prevGpm = gpmSelect.value;

        wcSelect.innerHTML = '<option value="">Todos os CTs</option>';
        gpmSelect.innerHTML = '<option value="">Todos os GPMs</option>';

        Array.from(wcs).sort().forEach(w => {
            wcSelect.innerHTML += `<option value="${w}">${w}</option>`;
        });
        Array.from(gpms).sort().forEach(g => {
            gpmSelect.innerHTML += `<option value="${g}">${g}</option>`;
        });

        wcSelect.value = prevWc;
        gpmSelect.value = prevGpm;
        if (idOptions) {
            idOptions.innerHTML = '';
            allItemsData.items.slice().sort((a, b) => String(a.legacy_identifier).localeCompare(String(b.legacy_identifier), undefined, { numeric: true })).forEach(item => {
                const identifier = String(item.legacy_identifier || '');
                const label = document.createElement('label');
                label.dataset.search = identifier.toLowerCase();
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox'; checkbox.value = identifier;
                checkbox.checked = this.selectedIdentifiers.has(identifier);
                checkbox.onchange = () => {
                    if (checkbox.checked) this.selectedIdentifiers.add(identifier); else this.selectedIdentifiers.delete(identifier);
                    this.updateIdentifierTrigger(); this.load();
                };
                const text = document.createElement('span'); text.textContent = identifier;
                label.append(checkbox, text); idOptions.appendChild(label);
            });
            this.updateIdentifierTrigger();
        }
        const plansWithItems = (allPlansData.plans || []).filter(plan => Number(plan.items_count || 0) > 0);
        const availablePlanIds = new Set(plansWithItems.map(plan => String(plan.id)));
        Array.from(this.selectedPlanIds).forEach(id => { if (!availablePlanIds.has(String(id))) this.selectedPlanIds.delete(id); });
        this.renderEntityOptions('plan', plansWithItems.map(plan => ({
            value: plan.id, label: `${plan.legacy_code} — ${plan.description} (${plan.items_count} ${Number(plan.items_count) === 1 ? 'item' : 'itens'})`
        })), this.selectedPlanIds, 'Todos os planos com itens');
        this.renderEntityOptions('item', (allItemsData.items || []).map(item => ({
            value: item.id, label: `${item.legacy_identifier} — ${item.description}`
        })), this.selectedItemIds, 'Todos os itens');
    },

    // --- MANUAL BALANCING DRAFT & BOOK ---
    updateManualToolbar() {
        const bookButton = document.getElementById('btn-open-manual-book');
        const manualButton = document.getElementById('btn-manual-balance');
        const badge = document.getElementById('manual-pending-badge');
        if (bookButton) bookButton.classList.toggle('hidden', !this.manualSession);
        if (manualButton) manualButton.innerText = this.manualSession ? 'Continuar Manual' : 'Balanceamento Manual';
        if (badge) badge.innerText = String(this.manualSession?.pending_items || 0);
    },

    async toggleItemLock(itemId, locked, stopCounter) {
        const projectId = window.App.getValidProjectId();
        if (!projectId) return;
        UI.showLoader(locked ? 'Trancando ordem...' : 'Destrancando ordem...');
        try {
            // A lock is persisted in the manual draft. Create a draft from the
            // current official scenario transparently when none exists yet.
            if (!this.manualSession) {
                const started = await API.post('/api/manual-balance/start', {
                    project_id: projectId,
                    base_mode: 'current',
                    horizon: Number(document.getElementById('balance-filter-horizon')?.value || 12)
                });
                this.manualSession = started.session;
            }
            const response = await API.post('/api/manual-balance/lock', {
                project_id: projectId,
                session_id: this.manualSession.id,
                item_id: Number(itemId),
                locked: Boolean(locked),
                target_stop: Number(stopCounter)
            });
            this.manualSession = response.session;
            this.updateManualToolbar();
            await this.load();
            await this.openStopDetails(stopCounter);
            UI.showToast(locked
                ? 'Ordem trancada: o balanceamento manual e automático não poderão movê-la.'
                : 'Ordem destrancada e liberada para balanceamento.', 'success', 4500);
        } catch (error) {
            UI.showToast(`Não foi possível ${locked ? 'trancar' : 'destrancar'} a ordem: ${error.message}`, 'error', 6000);
        } finally { UI.hideLoader(); }
    },

    async openManualBalance() {
        const projectId = window.App.getValidProjectId();
        if (!projectId) return;
        if (this.manualSession) {
            await this.openManualBook();
            return;
        }
        if (!window.confirm('Iniciar uma sessão de balanceamento manual? O trabalho será salvo automaticamente como rascunho.')) return;
        const fromCurrent = window.confirm('Deseja partir do cenário atual?\n\nOK: manter itens posicionados.\nCancelar: iniciar do zero com itens >1P no Book.');
        UI.showLoader('Criando rascunho manual...');
        try {
            const response = await API.post('/api/manual-balance/start', {
                project_id: projectId,
                base_mode: fromCurrent ? 'current' : 'zero',
                horizon: Number(document.getElementById('balance-filter-horizon')?.value || 12)
            });
            this.manualSession = response.session;
            this.manualSelectedIds.clear(); this.manualSelectedCycles.clear();
            this.updateManualToolbar();
            await this.load();
            await this.openManualBook();
            UI.showToast('Rascunho manual iniciado e salvo.', 'success');
        } catch (error) {
            UI.showToast(`Erro ao iniciar balanceamento manual: ${error.message}`, 'error');
        } finally { UI.hideLoader(); }
    },

    showManualPanel() {
        const right = document.querySelector('.balance-right-col');
        const handle = document.getElementById('balance-splitter-handle');
        if (right) right.classList.remove('hidden');
        if (handle) handle.classList.remove('hidden');
        document.getElementById('sidebar')?.classList.add('collapsed');
        document.getElementById('btn-panel-book')?.classList.add('active');
        document.getElementById('btn-panel-stop')?.classList.remove('active');
        document.getElementById('manual-book-controls')?.classList.remove('hidden');
        document.getElementById('manual-stop-return-dropzone')?.classList.add('hidden');
        document.getElementById('inline-panel-subtitle').innerText = 'Rascunho salvo automaticamente';
        document.getElementById('inline-list-title').innerText = 'Book de itens / ordens';
        setTimeout(() => { if (!this.dragInProgress) this.renderChart(); }, 30);
    },

    async openManualBook() {
        if (!this.manualSession) return this.openManualBalance();
        this.showManualPanel();
        await this.loadManualBook();
    },

    debounceManualBook() {
        clearTimeout(this._manualBookTimer);
        this._manualBookTimer = setTimeout(() => this.loadManualBook(), 180);
    },

    async loadManualBook() {
        if (!this.manualSession) return;
        const projectId = window.App.getValidProjectId();
        try {
            const data = await API.get('/api/manual-balance/book', {
                project_id: projectId, session_id: this.manualSession.id,
                search: document.getElementById('manual-book-search')?.value || '',
                plan_query: document.getElementById('manual-plan-search')?.value || '',
                only_pending: document.getElementById('manual-only-pending')?.checked ? 'true' : '',
                cycles: Array.from(this.manualSelectedCycles).join(',')
            });
            this.manualSession = data.session; this.manualBookItems = data.items || [];
            this.updateManualToolbar(); this.renderManualCycleChips(data.cycle_counts || {});
            this.renderManualProgress(); this.renderManualBookRows();
        } catch (error) { UI.showToast(`Erro ao carregar Book: ${error.message}`, 'error'); }
    },

    renderManualProgress() {
        const percent = Number(this.manualSession?.progress_percent || 0);
        const text = document.getElementById('manual-progress-text');
        const fill = document.getElementById('manual-progress-fill');
        if (text) text.innerText = `${percent.toFixed(1)}% balanceado · ${this.manualSession.pending_items} pendente(s)`;
        if (fill) fill.style.width = `${percent}%`;
        const save = document.getElementById('manual-save-status');
        if (save) save.innerText = 'Salvo agora';
    },

    renderManualCycleChips(counts) {
        const container = document.getElementById('manual-cycle-chips'); if (!container) return;
        container.innerHTML = Object.keys(counts).map(Number).sort((a,b) => a-b).map(cycle =>
            `<button class="manual-cycle-chip ${this.manualSelectedCycles.has(cycle) ? 'active' : ''}" data-manual-cycle="${cycle}">${cycle}P (${counts[cycle]})</button>`
        ).join('');
        container.querySelectorAll('[data-manual-cycle]').forEach(button => button.onclick = () => {
            const cycle = Number(button.dataset.manualCycle);
            if (this.manualSelectedCycles.has(cycle)) this.manualSelectedCycles.delete(cycle); else this.manualSelectedCycles.add(cycle);
            this.loadManualBook();
        });
    },

    renderManualBookRows() {
        const tbody = document.getElementById('inline-orders-tbody'); if (!tbody) return;
        this.inlineOrdersData = [...this.manualBookItems]; tbody.innerHTML = '';
        if (!this.manualBookItems.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-table-cell">Nenhum item corresponde aos filtros.</td></tr>'; return;
        }
        this.manualBookItems.forEach(item => {
            const selected = this.manualSelectedIds.has(Number(item.id));
            const state = String(item.balance_state || 'PENDING').toLowerCase();
            const movable = item.balance_state !== 'FIXED' && Number(item.cycle) > 1;
            const tr = document.createElement('tr');
            tr.className = `draggable-row ${selected ? 'manual-book-row-selected' : ''}`;
            tr.draggable = movable;
            tr.dataset.itemId = String(item.id);
            tr.dataset.sortItem = item.legacy_identifier || '';
            tr.dataset.sortPlan = item.plan_code || '';
            tr.dataset.sortCycle = String(item.cycle || 0); tr.dataset.sortHh = String(item.hh || 0);
            tr.innerHTML = `<td style="text-align:center"><span class="manual-book-drag-handle" draggable="${movable}" title="${movable ? 'Arraste para uma parada' : 'Ordem protegida'}">&#x2630;</span><input type="checkbox" data-manual-select="${item.id}" ${selected ? 'checked' : ''} ${movable ? '' : 'disabled'}></td>
                <td><strong>${this.autoEscape(item.legacy_identifier)}</strong><div title="${this.autoEscape(item.description)}">${this.autoEscape(item.description || '-')}</div><span class="manual-state manual-state-${state}">${state.toUpperCase()}</span></td>
                <td><strong style="color:#0284c7">${this.autoEscape(item.plan_code)}</strong><div>${this.autoEscape(item.family9)}</div></td>
                <td style="text-align:center"><span class="auto-cycle-tag">${item.cycle}P</span></td>
                <td style="text-align:right"><strong>${Number(item.hh || 0).toFixed(1).replace('.', ',')} HH</strong></td>`;
            tr.querySelector('[data-manual-select]').onchange = event => {
                const id = Number(event.target.dataset.manualSelect);
                if (event.target.checked && movable) this.manualSelectedIds.add(id); else this.manualSelectedIds.delete(id);
                this.renderManualBookRows();
            };
            const beginDrag = event => {
                if (!movable) { event.preventDefault(); return; }
                const movableIds = new Set(this.manualBookItems
                    .filter(row => row.balance_state !== 'FIXED' && Number(row.cycle) > 1)
                    .map(row => Number(row.id)));
                const selectedIds = Array.from(this.manualSelectedIds).filter(id => movableIds.has(Number(id)));
                const ids = selectedIds.includes(Number(item.id)) ? selectedIds : [Number(item.id)];
                const payload = {manual:true,itemId:Number(item.id),itemIds:ids,planId:item.target_plan_id,planCode:item.plan_code};
                this.dragInProgress = true;
                tr.classList.add('dragging');
                window.pendingDraggedItem = payload;
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', JSON.stringify(payload));
                document.getElementById('manual-return-dropzone')?.classList.add('drag-visible');
            };
            tr.addEventListener('dragstart', beginDrag);
            tr.querySelector('.manual-book-drag-handle')?.addEventListener('dragstart', event => {
                event.stopPropagation(); beginDrag(event);
            });
            tr.addEventListener('dragend', () => {
                this.dragInProgress = false;
                tr.classList.remove('dragging');
                window.pendingDraggedItem = null;
                document.getElementById('manual-return-dropzone')?.classList.remove('drag-visible');
            });
            tbody.appendChild(tr);
        });
        this.setupInlineTableInteractions();
    },

    async moveManualItems(itemIds, targetStop) {
        if (!this.manualSession) return;
        const wasStopPanel = document.getElementById('btn-panel-stop')?.classList.contains('active');
        const sourceStop = this.activeStopCounter;
        UI.showLoader(`Posicionando ${itemIds.length} item(ns) na parada...`);
        try {
            const result = await API.post('/api/manual-balance/move', {
                project_id: window.App.currentProjectId, session_id: this.manualSession.id,
                item_ids: itemIds, target_stop: targetStop
            });
            this.manualSession = result.session; this.manualSelectedIds.clear();
            await this.load();
            if (wasStopPanel && sourceStop) {
                await this.openStopDetails(sourceStop);
            } else {
                await this.openManualBook();
            }
            UI.showToast(`${result.moved} item(ns) posicionados. Rascunho salvo.`, 'success');
        } catch (error) { UI.showToast(`Movimento não permitido: ${error.message}`, 'error'); }
        finally { UI.hideLoader(); }
    },

    async returnManualItems(itemIds) {
        if (!this.manualSession || !itemIds.length) return;
        if (!window.confirm(`Retornar ${itemIds.length} item(ns) ao Book como pendentes?`)) return;
        try {
            const result = await API.post('/api/manual-balance/return', {
                project_id: window.App.currentProjectId, session_id: this.manualSession.id, item_ids: itemIds
            });
            this.manualSession = result.session; this.manualSelectedIds.clear();
            await this.load(); await this.openManualBook(); UI.showToast('Itens retornados ao Book.', 'success');
        } catch (error) { UI.showToast(`Erro ao retornar ao Book: ${error.message}`, 'error'); }
    },

    async completeManualBalance() {
        if (!this.manualSession) return;
        let allowPending = false;
        if (this.manualSession.pending_items > 0) {
            allowPending = window.confirm(`Ainda existem ${this.manualSession.pending_items} item(ns) pendentes.\nConcluir preservando seus planos originais?`);
            if (!allowPending) return;
        } else if (!window.confirm('Publicar este rascunho como cenário oficial?')) return;
        try {
            await API.post('/api/manual-balance/complete', {project_id:window.App.currentProjectId,
                session_id:this.manualSession.id,allow_pending:allowPending});
            this.manualSession=null; this.manualSelectedIds.clear(); this.updateManualToolbar();
            await this.load(); UI.showToast('Balanceamento manual concluído.', 'success');
        } catch (error) { UI.showToast(`Não foi possível concluir: ${error.message}`, 'error'); }
    },

    async restartManualBalance() {
        if (!this.manualSession) return this.openManualBalance();
        const counts = this.manualSession.counts || {};
        const positionedCount = Number(counts.MANUAL || 0) + Number(counts.AUTOMATIC || 0);
        if (!window.confirm(
            `Rebalancear do zero?\n\n${positionedCount} item(ns) posicionado(s) voltarão ao Book. ` +
            `Os itens 1P continuarão fixos. O cenário oficial não será alterado até você concluir.`
        )) return;
        UI.showLoader('Devolvendo as ordens ao Book...');
        try {
            const response = await API.post('/api/manual-balance/start', {
                project_id: window.App.currentProjectId,
                base_mode: 'zero',
                horizon: Number(document.getElementById('balance-filter-horizon')?.value || 12),
                restart: true
            });
            this.manualSession = response.session;
            this.manualSelectedIds.clear(); this.manualSelectedCycles.clear();
            document.getElementById('manual-only-pending').checked = true;
            await this.load(); await this.openManualBook();
            UI.showToast(`${this.manualSession.pending_items} item(ns) devolvidos ao Book para rebalancear.`, 'success');
        } catch (error) {
            UI.showToast(`Não foi possível reiniciar: ${error.message}`, 'error');
        } finally { UI.hideLoader(); }
    },

    promptPM13ReturnToBookModal() {
        document.getElementById('modal-pm13-return-to-book')?.remove();

        const modal = document.createElement('div');
        modal.id = 'modal-pm13-return-to-book';
        modal.className = 'modal-backdrop';
        modal.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(15,23,42,0.5); z-index:99999; display:flex; align-items:center; justify-content:center;';

        modal.innerHTML = `
          <div class="card" style="width:100%; max-width:460px; padding:24px; border-radius:12px; background:#fff; box-shadow:0 20px 40px rgba(0,0,0,0.25);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid #E2E8F0; padding-bottom:10px;">
              <h3 style="font-size:16px; font-weight:700; color:#0F172A; margin:0;">↩️ Retornar Ordens ao Book</h3>
              <button type="button" class="btn-icon" id="close-modal-pm13-return-book" style="border:0; background:transparent; font-size:20px; cursor:pointer;">×</button>
            </div>
            <div style="text-align:center; margin-bottom:20px;">
              <p style="font-size:14px; font-weight:600; color:#1E293B; margin-bottom:8px;">
                Deseja remover as ordens do gráfico e retorná-las para o Book de Ordens?
              </p>
              <p class="subtitle" style="font-size:12px; color:#64748B; line-height:1.4;">
                Escolha se deseja retornar todas as ordens posicionadas ou apenas aquelas que não estão trancadas.
              </p>
            </div>
            <div style="display:flex; flex-direction:column; gap:10px;">
              <button type="button" class="btn btn-primary" id="btn-pm13-modal-return-all" style="width:100%; padding:10px; font-weight:700;">
                📦 Retornar TODAS as Ordens
              </button>
              <button type="button" class="btn btn-warning" id="btn-pm13-modal-return-unlocked" style="width:100%; padding:10px; font-weight:700; background-color:#F59E0B; border-color:#D97706; color:#FFF;">
                🔓 Retornar APENAS Destrancadas
              </button>
              <button type="button" class="btn btn-outline" id="btn-pm13-modal-cancel-return" style="width:100%; padding:8px;">
                ❌ Cancelar
              </button>
            </div>
          </div>
        `;

        document.body.appendChild(modal);

        const closeModal = () => modal.remove();
        modal.querySelector('#close-modal-pm13-return-book').onclick = closeModal;
        modal.querySelector('#btn-pm13-modal-cancel-return').onclick = closeModal;

        modal.querySelector('#btn-pm13-modal-return-all').onclick = async () => {
          closeModal();
          await this.executePM13ReturnToBook(false);
        };

        modal.querySelector('#btn-pm13-modal-return-unlocked').onclick = async () => {
          closeModal();
          await this.executePM13ReturnToBook(true);
        };
    },

    async executePM13ReturnToBook(onlyUnlocked) {
        UI.showLoader(onlyUnlocked ? 'Retornando ordens destrancadas ao Book...' : 'Retornando todas as ordens ao Book...');
        try {
            await API.post('/api/manual-balance/return-all', {
                project_id: window.App.currentProjectId,
                session_id: (this.manualSession || {}).id,
                only_unlocked: onlyUnlocked
            });
            UI.showToast(
                onlyUnlocked ? 'Ordens destrancadas retornadas ao Book!' : 'Todas as ordens retornadas ao Book!',
                'success'
            );
            await this.load();
            await this.openManualBook();
        } catch (err) {
            UI.showToast(`Erro ao retornar ordens ao Book: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async discardManualBalance() {
        if (!this.manualSession || !window.confirm('Descartar o rascunho manual? O cenário oficial será preservado.')) return;
        await API.post('/api/manual-balance/discard', {project_id:window.App.currentProjectId,session_id:this.manualSession.id});
        this.manualSession=null; this.manualSelectedIds.clear(); this.updateManualToolbar(); await this.load();
        UI.showToast('Rascunho descartado.', 'success');
    },

    // --- AUTOMATIC BALANCING ---
    autoItems: [],
    autoRules: [],
    autoSelectedIds: [],
    autoRunning: false,

    autoEscape(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;').replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    },

    async openAutoBalance() {
        const projId = window.App.getValidProjectId();
        if (!projId) return;
        UI.showLoader('Preparando balanceamento automático...');
        try {
            const [itemsData, rulesData] = await Promise.all([
                API.get('/api/items', { project_id: projId, limit: 5000, status: 'ACTIVE' }),
                API.get('/api/auto-balance/rules', { project_id: projId })
            ]);
            this.autoItems = (itemsData?.items || []).filter(i => i.plan_id && Number(i.plan_cycle) > 1);
            this.autoRules = rulesData?.rules || [];
            const preferences = rulesData?.preferences || {};
            const strategySelect = document.getElementById('auto-distribution-strategy');
            const geographySelect = document.getElementById('auto-geography-mode');
            const toleranceInput = document.getElementById('auto-vertical-tolerance');
            const similarityInput = document.getElementById('auto-balance-similarity-check');
            const passesInput = document.getElementById('auto-balance-max-passes');
            if (strategySelect) strategySelect.value = preferences.distribution_strategy || 'horizontal';
            if (geographySelect) geographySelect.value = preferences.geography_mode || 'preferred';
            if (toleranceInput) toleranceInput.value = preferences.vertical_tolerance ?? 10;
            if (similarityInput) similarityInput.checked = preferences.similarity_enabled !== false;
            if (passesInput) passesInput.value = preferences.max_passes || 50;
            this.autoSelectedIds = [];
            this.autoRunning = false;
            this.autoFinished = false;
            document.getElementById('auto-balance-config-view').classList.remove('hidden');
            document.getElementById('auto-balance-progress-view').classList.add('hidden');
            document.getElementById('auto-balance-result').classList.add('hidden');
            document.getElementById('auto-strategy-comparison')?.classList.add('hidden');
            document.getElementById('btn-run-auto-balance').classList.remove('hidden');
            document.getElementById('btn-finish-auto-balance').classList.add('hidden');
            document.getElementById('btn-cancel-auto-balance').classList.remove('hidden');
            document.getElementById('btn-cancel-auto-balance').innerText = 'Cancelar';
            document.getElementById('btn-close-auto-balance').disabled = false;
            document.getElementById('auto-engine-orbit').classList.remove('complete');
            document.getElementById('auto-item-search').value = '';
            this.renderAutoItems();
            this.renderAutoRules();
            document.getElementById('auto-balance-modal').classList.remove('hidden');
        } catch (err) {
            UI.showToast(`Erro ao preparar balanceamento: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async closeAutoBalance() {
        if (this.autoRunning) {
            UI.showToast('Aguarde a conclusão do balanceamento.', 'warning');
            return;
        }
        const modal = document.getElementById('auto-balance-modal');
        if (modal) modal.classList.add('hidden');
        if (this.autoFinished) {
            this.autoFinished = false;
            await this.load();
        }
    },

    renderAutoItems() {
        const container = document.getElementById('auto-items-list');
        if (!container) return;
        const term = (document.getElementById('auto-item-search')?.value || '').trim().toLowerCase();
        const visible = this.autoItems.filter(item => {
            const haystack = `${item.legacy_identifier} ${item.description} ${item.plan_code}`.toLowerCase();
            return !term || haystack.includes(term);
        });
        if (!visible.length) {
            container.innerHTML = '<div class="auto-empty-rules">Nenhum item balanceável encontrado.</div>';
            return;
        }
        container.innerHTML = visible.map(item => {
            const checked = this.autoSelectedIds.includes(Number(item.id)) ? 'checked' : '';
            return `<label class="auto-item-row">
                <input type="checkbox" data-auto-item-id="${item.id}" ${checked}>
                <span class="auto-item-main"><strong>${this.autoEscape(item.legacy_identifier)} · ${this.autoEscape(item.plan_code)}</strong><span>${this.autoEscape(item.description || 'Sem descrição')}</span></span>
                <span class="auto-cycle-tag">${Number(item.plan_cycle)}P</span>
            </label>`;
        }).join('');
        container.querySelectorAll('[data-auto-item-id]').forEach(input => {
            input.onchange = () => {
                const id = Number(input.dataset.autoItemId);
                if (input.checked && !this.autoSelectedIds.includes(id)) this.autoSelectedIds.push(id);
                if (!input.checked) this.autoSelectedIds = this.autoSelectedIds.filter(x => x !== id);
                this.updateAutoSelectionHint();
            };
        });
        this.updateAutoSelectionHint();
    },

    updateAutoSelectionHint() {
        const count = document.getElementById('auto-selected-count');
        if (count) count.innerText = `${this.autoSelectedIds.length} selecionado${this.autoSelectedIds.length === 1 ? '' : 's'}`;
        const selected = this.autoSelectedIds.map(id => this.autoItems.find(i => Number(i.id) === id)).filter(Boolean);
        const cycles = [...new Set(selected.map(i => Number(i.plan_cycle)))];
        const hint = document.getElementById('auto-rule-hint');
        if (!hint) return;
        hint.innerText = selected.length
            ? `Ciclos selecionados: ${cycles.map(c => `${c}P`).join(', ')}. O sistema calculará as ocorrências comuns ou proibidas.`
            : 'Ciclos diferentes podem coincidir conforme suas fases.';
        hint.style.color = '';
    },

    addAutoRule() {
        const name = (document.getElementById('auto-rule-name').value || '').trim();
        const type = document.getElementById('auto-rule-type').value;
        const enforcement = document.getElementById('auto-rule-enforcement')?.value || 'mandatory';
        if (this.autoSelectedIds.length < 2) {
            UI.showToast('Selecione pelo menos dois itens para criar a regra.', 'warning');
            return;
        }
        const selected = this.autoSelectedIds.map(id => this.autoItems.find(i => Number(i.id) === id)).filter(Boolean);
        const cycles = [...new Set(selected.map(i => Number(i.plan_cycle)))];
        if (type === 'sequence' && (cycles.length !== 1 || selected.length > cycles[0])) {
            UI.showToast('Executar em sequência exige o mesmo ciclo e posições suficientes.', 'error');
            return;
        }
        if (type === 'separate' && cycles.includes(1)) {
            UI.showToast('Itens 1P não podem usar “Não executar juntos”, pois aparecem em todas as paradas.', 'error');
            return;
        }
        this.autoRules.push({
            name: name || `Regra ${this.autoRules.length + 1}`,
            type, enforcement, item_ids: [...this.autoSelectedIds]
        });
        this.autoSelectedIds = [];
        document.getElementById('auto-rule-name').value = '';
        this.renderAutoItems();
        this.renderAutoRules();
    },

    renderAutoRules() {
        const container = document.getElementById('auto-rules-list');
        const badge = document.getElementById('auto-rules-count');
        if (badge) badge.innerText = `${this.autoRules.length} regra${this.autoRules.length === 1 ? '' : 's'}`;
        if (!container) return;
        if (!this.autoRules.length) {
            container.innerHTML = '<div class="auto-empty-rules">Nenhuma regra adicionada.<br>O balanceamento será orientado apenas pelo HH.</div>';
            return;
        }
        container.innerHTML = this.autoRules.map((rule, index) => {
            const names = (rule.item_ids || []).map(id => {
                const item = this.autoItems.find(i => Number(i.id) === Number(id));
                return item ? `${item.legacy_identifier} (${item.plan_code})` : `Item ${id}`;
            });
            return `<div class="auto-rule-card">
                <button class="auto-rule-remove" data-remove-rule="${index}" title="Remover">×</button>
                <strong>${this.autoEscape(rule.name)}</strong>
                <span>${rule.type === 'sequence' ? 'Executar em sequência' : rule.type === 'separate' ? 'Não executar juntos' : 'Executar juntos'} · ${rule.enforcement === 'preferred' ? 'Preferencial' : 'Obrigatória'} · ${names.length} itens</span>
                <ol>${names.map(n => `<li>${this.autoEscape(n)}</li>`).join('')}</ol>
            </div>`;
        }).join('');
        container.querySelectorAll('[data-remove-rule]').forEach(btn => {
            btn.onclick = () => {
                this.autoRules.splice(Number(btn.dataset.removeRule), 1);
                this.renderAutoRules();
            };
        });
    },

    getAutoPreviewPayload(strategy) {
        const passesInput = document.getElementById('auto-balance-max-passes');
        return {
            project_id: window.App.getValidProjectId(),
            horizon: Number(document.getElementById('balance-filter-horizon')?.value || 12),
            rules: this.autoRules,
            similarity_enabled: document.getElementById('auto-balance-similarity-check')?.checked !== false,
            max_passes: Math.min(2000, Math.max(1, parseInt(passesInput?.value || 50))),
            distribution_strategy: strategy,
            geography_mode: document.getElementById('auto-geography-mode')?.value || 'off',
            vertical_tolerance: Number(document.getElementById('auto-vertical-tolerance')?.value || 10),
            capacities: this.getEffectiveCapacities(),
            manual_session_id: this.manualSession?.id || null,
            preserve_manual: true
        };
    },

    async compareAutoStrategies() {
        const box = document.getElementById('auto-strategy-comparison');
        const button = document.getElementById('btn-compare-auto-strategies');
        if (!box || !button || this.autoRunning) return;
        button.disabled = true; button.innerText = 'Calculando prévias...';
        box.classList.remove('hidden');
        box.innerHTML = '<strong>Calculando os dois cenários sem alterar o projeto...</strong>';
        try {
            const [horizontal, vertical] = await Promise.all([
                API.post('/api/auto-balance/preview', this.getAutoPreviewPayload('horizontal'), { timeoutMs: 45000 }),
                API.post('/api/auto-balance/preview', this.getAutoPreviewPayload('vertical'), { timeoutMs: 45000 })
            ]);
            const h = horizontal.result || horizontal;
            const v = vertical.result || vertical;
            const row = (label, hValue, vValue, lowerIsBetter=true) => {
                const hn = parseFloat(hValue); const vn = parseFloat(vValue);
                const hBest = hn !== vn && (lowerIsBetter ? hn < vn : hn > vn) ? 'comparison-best' : '';
                const vBest = hn !== vn && (lowerIsBetter ? vn < hn : vn > hn) ? 'comparison-best' : '';
                return `<tr><td>${label}</td><td class="${hBest}">${hValue}</td><td class="${vBest}">${vValue}</td></tr>`;
            };
            box.innerHTML = `<table><thead><tr><th>Indicador</th><th>Horizontal</th><th>Vertical</th></tr></thead><tbody>
                ${row('GAP máximo', `${h.after.range_hh.toFixed(1)} HH`, `${v.after.range_hh.toFixed(1)} HH`)}
                ${row('Desvio-padrão', `${h.after.std_dev.toFixed(2)} HH`, `${v.after.std_dev.toFixed(2)} HH`)}
                ${row('Pico de HH', `${h.after.max_hh.toFixed(1)} HH`, `${v.after.max_hh.toFixed(1)} HH`)}
                ${row('Pares geográficos preservados', h.geographic_pairs_preserved || 0, v.geographic_pairs_preserved || 0, false)}
                ${row('Saltos na sequência', h.sequence_skips || 0, v.sequence_skips || 0)}
                ${row('Regras obrigatórias violadas', (h.rule_diagnostics || []).filter(x => x.enforcement === 'mandatory' && !x.satisfied).length, (v.rule_diagnostics || []).filter(x => x.enforcement === 'mandatory' && !x.satisfied).length)}
            </tbody></table><div style="margin-top:7px;color:#64748b;font-size:10px">Prévia somente leitura. Se houver rascunho manual, os itens manuais são preservados.</div>`;
        } catch (error) {
            box.innerHTML = `<strong>Não foi possível comparar:</strong> ${this.autoEscape(error.message)}`;
        } finally {
            button.disabled = false; button.innerText = 'Comparar Horizontal × Vertical';
        }
    },

    async runAutoBalance() {
        if (this.autoRunning) return;
        const projId = window.App.getValidProjectId();
        const horizon = Number(document.getElementById('balance-filter-horizon')?.value || 12);
        const simCheck = document.getElementById('auto-balance-similarity-check');
        const similarityEnabled = simCheck ? simCheck.checked : true;
        const passesInput = document.getElementById('auto-balance-max-passes');
        const maxPasses = Math.min(2000, Math.max(1, parseInt(passesInput?.value || 50)));
        let preserveManual = true;
        if (this.manualSession) {
            preserveManual = window.confirm('Existe um rascunho manual.\n\nOK: manter itens manuais e balancear somente pendentes.\nCancelar: rebalancear tudo no rascunho.');
            if (!preserveManual) {
                const rebalanceAll = window.confirm(
                    'Rebalancear todo o rascunho do zero?\n\nOK: substituir também as posições manuais.\nCancelar: voltar sem executar.'
                );
                if (!rebalanceAll) return;
            }
        }
        const payload = {
            project_id: projId,
            horizon,
            rules: this.autoRules,
            similarity_enabled: similarityEnabled,
            max_passes: maxPasses,
            distribution_strategy: document.getElementById('auto-distribution-strategy')?.value || 'horizontal',
            geography_mode: document.getElementById('auto-geography-mode')?.value || 'off',
            vertical_tolerance: Number(document.getElementById('auto-vertical-tolerance')?.value || 10),
            capacities: this.getEffectiveCapacities(),
            manual_session_id: this.manualSession?.id || null,
            preserve_manual: preserveManual
        };

        this.autoRunning = true;
        document.getElementById('auto-balance-config-view').classList.add('hidden');
        document.getElementById('auto-balance-progress-view').classList.remove('hidden');
        document.getElementById('btn-run-auto-balance').classList.add('hidden');
        document.getElementById('btn-cancel-auto-balance').classList.add('hidden');
        document.getElementById('btn-close-auto-balance').disabled = true;
        const resultBox = document.getElementById('auto-balance-result');
        resultBox.classList.add('hidden');

        const steps = [
            ['Validando periodicidades', 'Conferindo ciclos, fases e paradas de referência.'],
            ['Analisando similaridade de títulos', similarityEnabled ? 'Agrupando planos com títulos/máquinas similares na mesma parada.' : 'Otimização padrão por nivelamento de HH.'],
            ['Protegendo planos 1P', 'Fixando as cargas obrigatórias de todas as paradas.'],
            ['Aplicando regras conjuntas', 'Agrupando itens que devem executar na mesma parada.'],
            ['Ordenando sequências', 'Preservando a ordem operacional definida no cenário.'],
            ['Distribuindo ciclos longos', 'Posicionando 12P, 10P e 6P nas menores cargas.'],
            ['Preenchendo vales de carga', 'Ajustando 3P e 2P para reduzir os picos remanescentes.'],
            [`Executando varreduras e convergência (${maxPasses} máx)`, 'Localizando a varredura campeã de menor GAP global.'],
            ['Gravando cenário seguro', 'Registrando alterações e histórico de auditoria.']
        ];
        const stepsEl = document.getElementById('auto-progress-steps');
        stepsEl.innerHTML = steps.map((s, i) => `<div class="auto-progress-step" data-progress-step="${i}">${s[0]}</div>`).join('');
        const bar = document.getElementById('auto-progress-bar');
        const percent = document.getElementById('auto-progress-percent');
        bar.style.width = '0%'; percent.innerText = '0%';

        // Launch backend optimization immediately
        Logger.log(`Balanceamento iniciado: projeto=${projId}, estratégia=${payload.distribution_strategy}, varreduras=${maxPasses}`, 'AUTO_BALANCE');
        const applyPromise = API.post('/api/auto-balance/apply', payload, { timeoutMs: 45000 })
            .then(value => ({ value }))
            .catch(error => ({ error }));

        try {
            for (let i = 0; i < steps.length; i++) {
                document.getElementById('auto-progress-title').innerText = steps[i][0];
                document.getElementById('auto-progress-detail').innerText = steps[i][1];
                stepsEl.querySelectorAll('.auto-progress-step').forEach((el, idx) => {
                    el.classList.toggle('active', idx === i);
                    if (idx < i) el.classList.add('done');
                });
                const pct = Math.round(((i + 1) / steps.length) * 92);
                bar.style.width = `${pct}%`; percent.innerText = `${pct}%`;
                await new Promise(resolve => setTimeout(resolve, 260));
            }

            const applyOutcome = await applyPromise;
            if (applyOutcome.error) throw applyOutcome.error;
            const response = applyOutcome.value;
            const result = response.result || response;
            Logger.log(`Balanceamento concluído: projeto=${projId}, tempo=${result.elapsed_seconds || 0}s, varreduras=${result.total_passes_run || 1}`, 'AUTO_BALANCE');

            stepsEl.querySelectorAll('.auto-progress-step').forEach(el => { el.classList.remove('active'); el.classList.add('done'); });
            bar.style.width = '100%'; percent.innerText = '100%';
            document.getElementById('auto-progress-title').innerText = 'Cenário otimizado e aplicado com sucesso!';
            document.getElementById('auto-progress-detail').innerText = `Otimização concluída em ${result.total_passes_run || 1} varreduras (${result.elapsed_seconds || 0}s). Cenário campeão selecionado na Varredura ${result.champion_pass || 1}.`;
            document.getElementById('auto-engine-orbit').classList.add('complete');
            document.getElementById('auto-result-before').innerText = `${result.before.std_dev.toFixed(2)} HH (GAP ${result.before_gap || result.before.range_hh} HH)`;
            document.getElementById('auto-result-after').innerText = `${result.after.std_dev.toFixed(2)} HH (GAP ${result.after_gap || result.after.range_hh} HH)`;
            document.getElementById('auto-result-improvement').innerText = `${result.improvement_percent.toFixed(1)}%`;
            document.getElementById('auto-result-changes').innerText = `${result.plans_changed || 0} planos, ${result.items_reassigned || 0} itens`;
            document.getElementById('auto-result-summary').innerText = `Melhor cenário na Varredura ${result.champion_pass || 1} de ${result.total_passes_run || 1} (${result.plans_analyzed} planos analisados em ${result.horizon} paradas).`;
            resultBox.classList.remove('hidden');
            this.pushHistory({
                type: 'auto_balance',
                changes: result.changes || [],
                item_changes: result.item_changes || []
            });
            this.autoRunning = false;
            this.autoFinished = true;
            document.getElementById('btn-close-auto-balance').disabled = false;
            document.getElementById('btn-finish-auto-balance').classList.remove('hidden');
        } catch (err) {
            Logger.log(`Balanceamento falhou: projeto=${projId}, erro=${err.message || 'Erro desconhecido'}`, 'AUTO_BALANCE');
            this.autoRunning = false;
            document.getElementById('btn-close-auto-balance').disabled = false;
            document.getElementById('btn-cancel-auto-balance').classList.remove('hidden');
            document.getElementById('btn-cancel-auto-balance').innerText = 'Fechar';
            document.getElementById('auto-progress-title').innerText = 'Balanceamento interrompido';
            document.getElementById('auto-progress-detail').innerText = err.message || 'Erro desconhecido';
            UI.showToast(`Erro no balanceamento: ${err.message || 'Erro desconhecido'}`, 'error');
        }
    },

    async finishAutoBalance() {
        this.closeAutoBalance();
        await this.load();
        UI.showToast('Novo cenário de balanceamento carregado.', 'success');
    },

    // --- REBALANCING DRAG-AND-DROP & HISTORIC UNDO/REDO ---
    history: [],
    redoStack: [],
    pendingDrop: null,

    pushHistory(action) {
        this.history.push(action);
        this.redoStack = []; // Clear redo stack on new action
        this.updateUndoRedoButtons();
    },

    updateUndoRedoButtons() {
        const btnUndo = document.getElementById('btn-undo-balance');
        const btnRedo = document.getElementById('btn-redo-balance');
        if (btnUndo) btnUndo.disabled = this.history.length === 0;
        if (btnRedo) btnRedo.disabled = this.redoStack.length === 0;
    },

    async undoLastAction() {
        if (this.history.length === 0) return;
        const action = this.history.pop();
        this.redoStack.push(action);
        this.updateUndoRedoButtons();

        UI.showLoader("Desfazendo último ajuste...");
        try {
            if (action.type === 'shift_plan') {
                await API.post('/api/balance/move', { plan_id: action.planId, target_stop: action.oldRefCnt });
            } else if (action.type === 'reassign_item') {
                await API.post('/api/balance/reassign-item', { item_id: action.itemId, plan_id: action.oldPlanId, allow_family_mismatch: true });
            } else if (action.type === 'auto_balance') {
                for (const change of (action.changes || [])) {
                    await API.post('/api/balance/move', { plan_id: change.plan_id, target_stop: change.old_reference });
                }
                for (const ic of (action.item_changes || [])) {
                    await API.post('/api/balance/reassign-item', { item_id: ic.item_id, plan_id: ic.old_plan_id, allow_family_mismatch: true });
                }
            }
            UI.showToast("Ajuste desfeito com sucesso!", "success");
            await this.load();
            if (this.activeStopCounter) {
                await this.openStopDetails(this.activeStopCounter);
            }
        } catch (err) {
            UI.showToast(`Erro ao desfazer ajuste: ${err.message}`, "error");
        } finally {
            UI.hideLoader();
        }
    },

    async redoLastAction() {
        if (this.redoStack.length === 0) return;
        const action = this.redoStack.pop();
        this.history.push(action);
        this.updateUndoRedoButtons();

        UI.showLoader("Refazendo ajuste...");
        try {
            if (action.type === 'shift_plan') {
                await API.post('/api/balance/move', { plan_id: action.planId, target_stop: action.newRefCnt });
            } else if (action.type === 'reassign_item') {
                await API.post('/api/balance/reassign-item', { item_id: action.itemId, plan_id: action.newPlanId, allow_family_mismatch: true });
            } else if (action.type === 'auto_balance') {
                for (const change of (action.changes || [])) {
                    await API.post('/api/balance/move', { plan_id: change.plan_id, target_stop: change.new_reference });
                }
                for (const ic of (action.item_changes || [])) {
                    await API.post('/api/balance/reassign-item', { item_id: ic.item_id, plan_id: ic.new_plan_id, allow_family_mismatch: true });
                }
            }
            UI.showToast("Ajuste refeito com sucesso!", "success");
            await this.load();
            if (this.activeStopCounter) {
                await this.openStopDetails(this.activeStopCounter);
            }
        } catch (err) {
            UI.showToast(`Erro ao refazer ajuste: ${err.message}`, "error");
        } finally {
            UI.hideLoader();
        }
    },

    async restorePreBalance() {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        if (!window.confirm("Deseja restaurar o banco de dados para o estado inicial anterior ao balanceamento automático? Todas as paradas dos itens retornarão ao estado de quando a planilha foi carregada.")) {
            return;
        }

        UI.showLoader("Restaurando carga inicial pré-balanceamento...");
        try {
            const res = await API.post('/api/auto-balance/restore-pre-balance', { project_id: projId });
            this.manualSession = null;
            this.manualSelectedIds.clear(); this.manualSelectedCycles.clear();
            this.updateManualToolbar();
            UI.showToast(res.message || "Cenário inicial restaurado com sucesso!", "success");
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao restaurar cenário pré-balanceamento: ${err.message}`, "error");
        } finally {
            UI.hideLoader();
        }
    },

    async handleItemDrop(itemId, planId, planCode, stopNum, stopCounter) {
        const projId = window.App.currentProjectId;
        API.log(`handleItemDrop entry: itemId=${itemId}, planId=${planId}, planCode=${planCode}, stopNum=${stopNum}, stopCounter=${stopCounter}`, "balance.js");
        if (!projId) return;
        if (this.manualSession) {
            const dragged = window.pendingDraggedItem || {};
            const itemIds = (dragged.itemIds && dragged.itemIds.length)
                ? dragged.itemIds
                : (this.manualSelectedIds.has(Number(itemId)) ? Array.from(this.manualSelectedIds) : [Number(itemId)]);
            await this.moveManualItems(itemIds, stopCounter);
            return;
        }

        // Show loading indicator
        UI.showLoader("Buscando planos da família...");
        try {
            // Extract the first 9 characters of the source plan
            const fullPlanCode = (planCode || '').trim();
            const prefix9 = fullPlanCode.length >= 9 ? fullPlanCode.substring(0, 9).toUpperCase() : fullPlanCode.toUpperCase();

            // Fetch all plans in project (regardless of items or whether they are scheduled in this stop)
            const plansData = await API.get('/api/plans', {
                project_id: projId,
                limit: 100000
            });
            const allPlans = plansData.plans || [];
            let origPlan = null;
            if (planId) origPlan = await API.get(`/api/plans/${planId}`);
            const sourceCycle = Number(origPlan?.cycle || 0);
            const occursOnTarget = plan => {
                const cycle = Number(plan.cycle || 0);
                const reference = Number(plan.reference_counter);
                return cycle > 0 && Number.isFinite(reference) &&
                    ((Number(stopCounter) - reference) % cycle + cycle) % cycle === 0;
            };
            // Manual selection may show another family, but never another
            // cycle. Compatible family rows are ordered first; incompatible
            // rows require an explicit warning confirmation before the API
            // accepts the exception.
            let candidatePlans = allPlans.filter(plan =>
                (!sourceCycle || Number(plan.cycle) === sourceCycle) && occursOnTarget(plan)
            ).map(plan => ({
                ...plan,
                _familyCompatible: !prefix9 || (plan.legacy_code || '').substring(0, 9).toUpperCase() === prefix9
            })).sort((a, b) => Number(b._familyCompatible) - Number(a._familyCompatible) ||
                String(a.legacy_code || '').localeCompare(String(b.legacy_code || ''), undefined, {numeric:true}));
            UI.hideLoader();

            // Populate Modal Header & Info Card
            document.getElementById('balance-modal-item-id').innerText = itemId;
            document.getElementById('balance-modal-target-p').innerText = stopNum;
            document.getElementById('balance-modal-target-counter').innerText = stopCounter;
            
            const elCodeLbl = document.getElementById('modal-shift-plan-code-lbl');
            if (elCodeLbl) elCodeLbl.innerText = planCode || 'Plano Original';

            const badge = document.getElementById('balance-modal-prefix-badge');
            if (badge) {
                badge.innerText = prefix9 ? `Família de origem: ${prefix9}` : 'Item sem família de origem';
            }

            // Update creation button labels
            const prefixLbl = document.getElementById('modal-create-plan-code-prefix');
            const stopLbl = document.getElementById('modal-create-plan-stop-lbl');
            if (prefixLbl) prefixLbl.innerText = prefix9 || 'Novo';
            if (stopLbl) stopLbl.innerText = `Parada ${stopNum} (Contador ${stopCounter})`;

            // Original Plan Info
            const elOrigCode = document.getElementById('modal-orig-plan-code');
            const elOrigDesc = document.getElementById('modal-orig-plan-desc');
            const elOrigCycle = document.getElementById('modal-orig-plan-cycle');
            
            if (elOrigCode) elOrigCode.innerText = planCode || 'Sem Plano';

            if (planId) {
                if (elOrigDesc) elOrigDesc.innerText = 'Buscando...';
                if (elOrigCycle) elOrigCycle.innerText = 'Buscando...';
                try {
                    if (elOrigDesc) elOrigDesc.innerText = origPlan.description || 'Sem Descrição';
                    if (elOrigCycle) elOrigCycle.innerText = `${origPlan.cycle || 1} ${origPlan.unit || 'PRD'}`;
                } catch (pErr) {
                    if (elOrigDesc) elOrigDesc.innerText = 'Plano indisponível';
                    if (elOrigCycle) elOrigCycle.innerText = '-';
                }
            } else {
                if (elOrigDesc) elOrigDesc.innerText = 'Item Avulso (Sem Plano)';
                if (elOrigCycle) elOrigCycle.innerText = 'Sem Ciclo';
            }

            // Save variables for confirmation handlers
            this.pendingDrop = {
                itemId: parseInt(itemId),
                oldPlanId: planId ? parseInt(planId) : null,
                sourcePrefix9: prefix9,
                targetStopCounter: parseInt(stopCounter),
                targetStopNum: parseInt(stopNum)
            };

            // Render plans list in modal
            const tbody = document.getElementById('balance-modal-plans-tbody');
            const renderTableList = (list) => {
                tbody.innerHTML = '';
                if (!list || list.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="4" class="empty-table-cell" style="padding: 12px; color: var(--text-muted); text-align: center;">Nenhum plano do mesmo ciclo ocorre nesta parada.</td></tr>`;
                    return;
                }
                list.forEach(plan => {
                    const tr = document.createElement('tr');
                    tr.className = `plan-row-option ${plan._familyCompatible ? '' : 'plan-family-warning-row'}`;
                    tr.innerHTML = `
                        <td style="padding: 8px 10px; border-bottom: 1px solid var(--border-color); font-weight: 600;"><strong>${plan.legacy_code}</strong></td>
                        <td style="padding: 8px 10px; border-bottom: 1px solid var(--border-color);" title="${plan.description}">
                            <div style="max-width: 230px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${plan.description}</div>
                        </td>
                        <td style="padding: 8px 10px; border-bottom: 1px solid var(--border-color); text-align: center;">${plan.cycle} ${plan.unit}</td>
                        <td style="padding: 8px 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
                            ${plan._familyCompatible ? '' : '<span class="badge badge-warning" title="Família diferente: exige confirmação manual">⚠ Família diferente</span> '}
                            <button class="btn btn-xs ${plan._familyCompatible ? 'btn-primary' : 'btn-outline'} btn-select-plan">Selecionar</button>
                        </td>
                    `;
                    
                    tr.addEventListener('click', () => {
                        this.confirmReassignItem(plan.id, plan.legacy_code);
                    });

                    tbody.appendChild(tr);
                });
            };

            renderTableList(candidatePlans);

            // Search filter within candidate plans
            const searchInput = document.getElementById('balance-modal-plan-search');
            if (searchInput) {
                searchInput.value = '';
                searchInput.oninput = () => {
                    const term = searchInput.value.trim().toLowerCase();
                    const filtered = candidatePlans.filter(p =>
                        (p.legacy_code && p.legacy_code.toLowerCase().includes(term)) ||
                        (p.description && p.description.toLowerCase().includes(term))
                    );
                    renderTableList(filtered);
                };
            }

            // Wire up "Criar Novo Plano" button with 9-digit prefix and target stop prefilled
            const btnCreatePlan = document.getElementById('btn-modal-create-plan');
            if (btnCreatePlan) {
                btnCreatePlan.onclick = () => {
                    this.closeConfirmModal();
                    if (window.Plans) {
                        window.Plans.onPlanCreatedCallback = async (newPlan) => {
                            UI.showLoader("Vinculando ordem ao novo plano criado...");
                            try {
                                await API.post('/api/balance/reassign-item', { item_id: itemId, plan_id: newPlan.id });
                                this.pushHistory({
                                    type: 'reassign_item',
                                    itemId: itemId,
                                    oldPlanId: planId ? parseInt(planId) : null,
                                    newPlanId: newPlan.id
                                });
                                UI.showToast(`Ordem vinculada com sucesso ao plano ${newPlan.legacy_code} na parada ${stopCounter}!`, "success");
                                await this.load();
                                if (this.activeStopCounter) {
                                    await this.openStopDetails(this.activeStopCounter);
                                }
                            } catch (err) {
                                UI.showToast(`Erro ao vincular ordem: ${err.message}`, "error");
                            } finally {
                                UI.hideLoader();
                            }
                        };

                        window.Plans.openCreateModal({
                            code: prefix9,
                            counter: stopCounter
                        });
                    }
                };
            }

            // Wire up other action buttons
            const btnShift = document.getElementById('btn-modal-shift-original');
            if (btnShift) {
                if (!planId) {
                    btnShift.disabled = true;
                    btnShift.style.opacity = '0.5';
                } else {
                    btnShift.disabled = false;
                    btnShift.style.opacity = '1';
                    btnShift.onclick = () => this.confirmShiftOriginalPlan(planId, planCode, stopCounter);
                }
            }

            const btnCreateInd = document.getElementById('btn-modal-create-independent');
            if (btnCreateInd) {
                btnCreateInd.onclick = () => this.confirmCreateIndependentPlan(itemId, stopCounter);
            }

            // Show Modal
            const modal = document.getElementById('balance-confirm-modal');
            if (modal) {
                modal.classList.remove('hidden');
                API.log("Modal balance-confirm-modal displayed successfully!", "balance.js");
            }

        } catch (err) {
            API.log("ERROR in handleItemDrop: " + err.message, "balance.js");
            UI.hideLoader();
            UI.showToast(`Erro ao buscar planos: ${err.message}`, 'error');
        }
    },

    closeConfirmModal() {
        document.getElementById('balance-confirm-modal').classList.add('hidden');
        this.pendingDrop = null;
    },

    async confirmReassignItem(targetPlanId, targetPlanCode) {
        if (!this.pendingDrop) return;
        const { itemId, oldPlanId, sourcePrefix9 } = this.pendingDrop;
        const targetPrefix9 = String(targetPlanCode || '').trim().substring(0, 9).toUpperCase();
        const familyMismatch = Boolean(sourcePrefix9 && targetPrefix9 && sourcePrefix9 !== targetPrefix9);
        const confirmation = familyMismatch
            ? `ATENÇÃO: esta troca quebra a família geográfica do item.\n\n` +
              `Origem: ${sourcePrefix9}\nDestino: ${targetPrefix9}\nPlano: ${targetPlanCode}\n\n` +
              `O balanceamento automático jamais fará esta troca. Deseja registrar esta exceção manual?`
            : `Tem certeza de que deseja mover esta ordem para o plano ${targetPlanCode}?`;

        if (confirm(confirmation)) {
            this.closeConfirmModal();
            UI.showLoader("Reassociando ordem ao plano...");
            try {
                const response = await API.post('/api/balance/reassign-item', {
                    item_id: itemId, plan_id: targetPlanId,
                    allow_family_mismatch: familyMismatch
                });
                
                // Push action to undo stack
                this.pushHistory({
                    type: 'reassign_item',
                    itemId: itemId,
                    oldPlanId: oldPlanId,
                    newPlanId: targetPlanId
                });

                UI.showToast(response.warning || "Ordem reassociada e balanceada com sucesso!",
                    response.warning ? "warning" : "success");
                await this.load();
                if (this.activeStopCounter) {
                    await this.openStopDetails(this.activeStopCounter);
                }
            } catch (err) {
                UI.showToast(`Erro ao balancear: ${err.message}`, "error");
            } finally {
                UI.hideLoader();
            }
        }
    },

    async confirmShiftOriginalPlan(planId, planCode, targetStopCounter) {
        if (!this.pendingDrop) return;
        const { oldPlanId } = this.pendingDrop;
        
        UI.showLoader("Buscando dados do plano original...");
        try {
            const planDetails = await API.get(`/api/plans/${planId}`);
            UI.hideLoader();
            
            const oldRefCnt = planDetails.reference_counter;

            if (confirm(`Isso alterará a parada de referência do plano ${planCode} e deslocará TODOS os itens dele para a parada ${targetStopCounter}. Confirmar?`)) {
                this.closeConfirmModal();
                UI.showLoader("Deslocando plano...");
                try {
                    await API.post('/api/balance/move', { plan_id: planId, target_stop: targetStopCounter });
                    
                    // Push action to undo stack
                    this.pushHistory({
                        type: 'shift_plan',
                        planId: planId,
                        oldRefCnt: oldRefCnt,
                        newRefCnt: targetStopCounter
                    });

                    UI.showToast("Plano deslocado e balanceado com sucesso!", "success");
                    await this.load();
                    if (this.activeStopCounter) {
                        await this.openStopDetails(this.activeStopCounter);
                    }
                } catch (err) {
                    UI.showToast(`Erro ao balancear plano: ${err.message}`, "error");
                } finally {
                    UI.hideLoader();
                }
            }
        } catch (err) {
            UI.hideLoader();
            UI.showToast(`Erro ao buscar dados do plano original: ${err.message}`, "error");
        }
    },

    async confirmCreateIndependentPlan(itemId, targetStopCounter) {
        if (!this.pendingDrop) return;
        const { oldPlanId } = this.pendingDrop;

        if (confirm("Deseja criar um plano exclusivo para esta ordem para que ela aconteça nesta parada de forma independente?")) {
            this.closeConfirmModal();
            UI.showLoader("Criando plano independente...");
            try {
                const res = await API.post('/api/balance/create-independent-plan', { item_id: itemId, target_stop: targetStopCounter });
                
                // Push action to undo stack
                this.pushHistory({
                    type: 'reassign_item',
                    itemId: itemId,
                    oldPlanId: oldPlanId,
                    newPlanId: res.new_plan_id
                });

                UI.showToast("Plano independente criado e ordem balanceada!", "success");
                await this.load();
                if (this.activeStopCounter) {
                    await this.openStopDetails(this.activeStopCounter);
                }
            } catch (err) {
                UI.showToast(`Erro ao criar plano independente: ${err.message}`, "error");
            } finally {
                UI.hideLoader();
            }
        }
    },

    initSplitterResizer() {
        const handle = document.getElementById('balance-splitter-handle');
        const container = document.querySelector('.balance-split-container');
        const leftCol = document.querySelector('.balance-left-col');
        const rightCol = document.querySelector('.balance-right-col');

        if (!handle || !container || !leftCol || !rightCol) return;

        let isDragging = false;

        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            isDragging = true;
            handle.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        window.addEventListener('mousemove', (e) => {
            if (!isDragging) return;

            const containerRect = container.getBoundingClientRect();
            const mouseX = e.clientX - containerRect.left;
            const containerWidth = containerRect.width;

            if (containerWidth <= 0) return;

            // Calculate left percentage clamped between 30% and 75%
            let leftPercent = (mouseX / containerWidth) * 100;
            if (leftPercent < 30) leftPercent = 30;
            if (leftPercent > 75) leftPercent = 75;

            const rightPercent = 100 - leftPercent;

            leftCol.style.flex = 'none';
            leftCol.style.width = `calc(${leftPercent}% - 10px)`;

            rightCol.style.flex = 'none';
            rightCol.style.width = `calc(${rightPercent}% - 10px)`;

            // Re-render chart dynamically so SVG & Heatmap adapt to new width!
            this.renderChart();
        });

        window.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                handle.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                this.renderChart();
            }
        });
    }
};
