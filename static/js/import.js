/**
 * Excel Import Wizard Controller
 */

const ImportWizard = {
    currentStep: 1,
    selectedFile: null,
    previewData: null,

    headersData: null,
    importScope: 'full',

    getSelectedEntities() {
        return Array.from(document.querySelectorAll('.import-entity-check:checked')).map(el => el.value);
    },

    updateEntitySelectionUI() {
        const selected = new Set(this.getSelectedEntities());
        const idsByEntity = {
            plans: ['select-plan-sheet', 'mapping-fields-plans'],
            items: ['select-item-sheet', 'mapping-fields-items'],
            operations: ['select-op-sheet', 'mapping-fields-ops'],
            long_texts: ['select-lt-sheet', 'mapping-fields-lts']
        };
        Object.entries(idsByEntity).forEach(([entity, ids]) => ids.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            const wrapper = id.startsWith('mapping-fields-') ? el.closest('.card') : el.closest('.form-group');
            (wrapper || el).style.opacity = selected.has(entity) ? '1' : '0.45';
            if ('disabled' in el) el.disabled = !selected.has(entity);
        }));
        this.updateWizardButtons();
    },

    exportScope(scope = 'full') {
        const projectId = window.App ? window.App.getValidProjectId() : null;
        if (!projectId) return UI.showToast('Selecione um projeto.', 'warning');
        if (window.ExportManager) {
            window.ExportManager.openModal(scope);
        } else {
            UI.showToast('Carregando gerenciador de exportação...', 'info');
            setTimeout(() => window.ExportManager && window.ExportManager.openModal(scope), 300);
        }
    },

    exportSystems() {
        const projectId = window.App ? window.App.getValidProjectId() : null;
        if (!projectId) return UI.showToast('Selecione um projeto.', 'warning');
        if (window.ExportManager) {
            window.ExportManager.openModal('systems');
        } else {
            UI.showToast('Carregando gerenciador de exportação...', 'info');
            setTimeout(() => window.ExportManager && window.ExportManager.openModal('systems'), 300);
        }
    },

    downloadTemplate(scope = 'full') {
        const projectId = window.App.getValidProjectId();
        if (!projectId) return UI.showToast('Selecione um projeto.', 'warning');
        window.open(`/api/export?type=template&scope=${encodeURIComponent(scope)}&project_id=${projectId}`, '_blank');
    },

    openForScope(scope) {
        this.importScope = scope || 'full';
        this.reset();
        window.location.hash = '#import';
        const title = document.querySelector('#section-import h1');
        const labels = {plans:'Planos', items:'Itens', operations:'Operações', long_texts:'Textos longos', full:'Carga completa'};
        if (title) title.textContent = `Importar / Exportar Excel — ${labels[this.importScope] || labels.full}`;
    },

    init() {
        const dropzone = document.getElementById('upload-dropzone');
        const fileInput = document.getElementById('import-file-input');

        // Drag & drop events on the dropzone area
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        // File selected via native dialog
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });

        // "Alterar Arquivo" button
        const changeFileBtn = document.getElementById('btn-change-file');
        if (changeFileBtn) {
            changeFileBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.selectedFile = null;
                this.headersData = null;
                document.getElementById('file-details-box').classList.add('hidden');
                document.getElementById('upload-dropzone').classList.remove('hidden');
                fileInput.value = '';
                this.updateWizardButtons();
                fileInput.click();
            });
        }

        // Radio toggle between creating new or using existing project
        const radios = document.querySelectorAll('input[name="import-target-mode"]');
        radios.forEach(r => {
            r.onchange = () => {
                const newForm = document.getElementById('import-new-proj-form');
                const existForm = document.getElementById('import-existing-proj-form');
                if (r.value === 'new') {
                    newForm.classList.remove('disabled');
                    existForm.classList.add('disabled');
                } else {
                    newForm.classList.add('disabled');
                    existForm.classList.remove('disabled');
                    this.showExistingDataChoice();
                }
            };
        });

        // Wizard footer buttons
        document.getElementById('btn-import-prev').onclick = () => this.navigate(-1);
        document.getElementById('btn-import-next').onclick = () => this.navigate(1);
        document.getElementById('btn-import-confirm').onclick = () => this.confirm();
        document.querySelectorAll('.import-entity-check').forEach(check => {
            check.addEventListener('change', () => this.updateEntitySelectionUI());
        });

        // Diagnosis table filter change
        document.getElementById('diag-filter-severity').onchange = () => {
            this.renderDiagnosisTable();
        };

        // Final finish button redirecting to dashboard
        document.getElementById('btn-import-finish-go-dash').onclick = () => {
            window.location.hash = '#dashboard';
        };
    },

    showExistingDataChoice() {
        document.getElementById('import-mode-choice-popup')?.remove();
        const overlay = document.createElement('div');
        overlay.id = 'import-mode-choice-popup';
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal modal-container" style="max-width:580px; background:#FFFFFF; border-radius:12px; box-shadow:0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04); overflow:hidden; border:1px solid #CBD5E1;">
                <div class="modal-header" style="background:#F8FAFC; border-bottom:1px solid #E2E8F0; padding:18px 24px;">
                    <h2 style="font-size:16px; font-weight:700; color:#0F172A; display:flex; align-items:center; gap:8px; margin:0;">
                        <span>📦</span> Tratamento dos Dados Existentes
                    </h2>
                </div>
                <div class="modal-body" style="padding:24px; background:#FFFFFF;">
                    <p style="font-size:13px; color:#475569; margin:0 0 18px 0; line-height:1.5;">
                        O projeto selecionado já pode conter planos, itens, operações e textos longos cadastrados. Como deseja prosseguir?
                    </p>
                    <div style="display:flex; flex-direction:column; gap:14px;">
                        <div style="border:1px solid #E2E8F0; border-radius:8px; padding:14px 16px; background:#F8FAFC; transition:all 0.15s ease;" onmouseover="this.style.borderColor='#84BD00'; this.style.background='#F7FEE7'" onmouseout="this.style.borderColor='#E2E8F0'; this.style.background='#F8FAFC'">
                            <button type="button" class="btn btn-primary" data-mode="merge" style="width:100%; font-weight:700; padding:10px; font-size:13px; margin-bottom:6px; border-radius:6px;">
                                ➕ Adicionar e Unificar Dados (Recomendado)
                            </button>
                            <span style="font-size:11.5px; color:#64748B; display:block; line-height:1.4;">
                                Preserva os dados existentes no projeto, ignora planos repetidos e insere os novos itens e operações mantendo a integridade.
                            </span>
                        </div>
                        
                        <div style="border:1px solid #FEF2F2; border-radius:8px; padding:14px 16px; background:#FEF2F2;">
                            <button type="button" class="btn btn-outline" data-mode="replace" style="width:100%; font-weight:700; padding:10px; font-size:13px; color:#DC2626; border-color:#FCA5A5; background:#FFFFFF; margin-bottom:6px; border-radius:6px;">
                                ⚠️ Substituir Todos os Dados (Sobrescrever)
                            </button>
                            <span style="font-size:11.5px; color:#991B1B; display:block; line-height:1.4;">
                                Apaga completamente os planos e itens atuais deste projeto e importa os dados da nova planilha.
                            </span>
                        </div>
                    </div>
                </div>
                <div class="modal-footer" style="background:#F8FAFC; border-top:1px solid #E2E8F0; padding:14px 24px; display:flex; justify-content:flex-end;">
                    <button type="button" class="btn btn-outline" data-mode="cancel" style="padding:8px 18px; font-weight:600; font-size:12px; border-radius:6px; background:#FFFFFF;">Cancelar</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        overlay.querySelectorAll('[data-mode]').forEach(button => button.onclick = () => {
            const mode = button.dataset.mode;
            if (mode === 'cancel') {
                const newRadio = document.querySelector('input[name="import-target-mode"][value="new"]');
                if (newRadio) newRadio.click();
            } else {
                const existRadio = document.querySelector('input[name="import-target-mode"][value="existing"]');
                if (existRadio && !existRadio.checked) {
                    existRadio.checked = true;
                    existRadio.dispatchEvent(new Event('change'));
                }
                const mergeSelect = document.getElementById('import-merge-mode');
                if (mergeSelect) {
                    mergeSelect.value = mode;
                    mergeSelect.dispatchEvent(new Event('change'));
                }
                if (mode === 'replace') {
                    UI.showToast('Opção selecionada: Substituir todos os dados do projeto (sobrescrever)', 'warning', 6000);
                } else if (mode === 'merge') {
                    UI.showToast('Opção selecionada: Adicionar e unificar dados (preservar existentes)', 'info', 5000);
                }
            }
            overlay.remove();
        });
    },

    async handleFileSelect(file) {
        if (!file.name.toLowerCase().endsWith('.xlsx')) {
            UI.showToast("Por favor, selecione apenas arquivos Excel (.xlsx)", "error");
            return;
        }

        this.selectedFile = file;

        document.getElementById('selected-file-name').innerText = file.name;
        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        document.getElementById('selected-file-size').innerText = `${sizeMb} MB`;

        document.getElementById('upload-dropzone').classList.add('hidden');
        document.getElementById('file-details-box').classList.remove('hidden');

        UI.showToast("Arquivo selecionado: " + file.name);
        this.updateWizardButtons();

        // Inspect headers for smart mapping
        const formData = new FormData();
        formData.append('file', file);
        try {
            Logger?.log?.(`Inspeção de cabeçalhos iniciada: ${file.name} (${sizeMb} MB)`, 'IMPORT');
            const response = await fetch('/api/import/headers', { method: 'POST', body: formData });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.error || `Falha ao analisar cabeçalhos (HTTP ${response.status}).`);
            }
            this.headersData = payload;
            this.renderMappingControls();
            const entities = this.headersData.detected_entities || {};
            const body = document.getElementById('mapping-body-container');
            let status = document.getElementById('detected-entities-status');
            if (!status && body) {
                status = document.createElement('div'); status.id = 'detected-entities-status';
                status.style.cssText = 'padding:10px;margin-bottom:12px;background:#F0FDF4;border:1px solid #86EFAC;border-radius:6px;font-size:12px;font-weight:600;';
                body.prepend(status);
            }
            if (status) status.textContent = `Detectado: Planos ${entities.plans?'✓':'—'} · Itens ${entities.items?'✓':'—'} · Operações ${entities.operations?'✓':'—'} · Textos longos ${entities.long_texts?'✓':'—'}`;
            Logger?.log?.(`Cabeçalhos analisados com sucesso: ${file.name}`, 'IMPORT');
        } catch (e) {
            this.headersData = null;
            console.warn("Não foi possível inspecionar cabeçalhos:", e);
            Logger?.log?.(`Falha na inspeção de cabeçalhos: ${e.message}`, 'IMPORT');
            UI.showToast(`Arquivo não pôde ser preparado para importação: ${e.message}`, 'error', 14000);
        }
    },

    toggleMapping(forceShow = null) {
        const body = document.getElementById('mapping-body-container');
        const icon = document.getElementById('mapping-toggle-icon');
        if (!body || !icon) return;

        if (forceShow === true) {
            body.classList.remove('hidden');
            icon.innerText = '▲';
        } else if (forceShow === false) {
            body.classList.add('hidden');
            icon.innerText = '▼';
        } else {
            body.classList.toggle('hidden');
            icon.innerText = body.classList.contains('hidden') ? '▼' : '▲';
        }
    },

    onSheetSelectChange() {
        this.renderMappingControls(false);
    },

    renderMappingControls(initSheetSelects = true) {
        if (!this.headersData) return;

        if (this.headersData.standard_match) {
            const durationUnit = document.getElementById('import-duration-unit');
            if (durationUnit) durationUnit.value = 'HOURS';
            UI.showToast('Modelo padrão reconhecido: abas e colunas configuradas automaticamente.', 'success', 6000);
        }

        // Auto-open mapping panel
        this.toggleMapping(true);

        const planSheetSelect = document.getElementById('select-plan-sheet');
        const itemSheetSelect = document.getElementById('select-item-sheet');
        const opSheetSelect = document.getElementById('select-op-sheet');
        const ltSheetSelect = document.getElementById('select-lt-sheet');

        if (initSheetSelects && this.headersData.sheet_names) {
            const names = this.headersData.sheet_names;
            [
                { el: planSheetSelect, detected: this.headersData.detected_plan_sheet, defaultIdx: 0, required: true },
                { el: itemSheetSelect, detected: this.headersData.detected_item_sheet, defaultIdx: 1, required: true },
                { el: opSheetSelect, detected: this.headersData.detected_operation_sheet, defaultIdx: -1, required: false },
                { el: ltSheetSelect, detected: this.headersData.detected_long_text_sheet, defaultIdx: -1, required: false }
            ].forEach(cfg => {
                if (!cfg.el) return;
                let html = cfg.required ? '' : '<option value="">-- Nenhuma (Opcional) --</option>';
                names.forEach(s => {
                    html += `<option value="${s}">${s}</option>`;
                });
                cfg.el.innerHTML = html;
                if (cfg.detected) {
                    cfg.el.value = cfg.detected;
                } else if (cfg.defaultIdx >= 0 && names[cfg.defaultIdx]) {
                    cfg.el.value = names[cfg.defaultIdx];
                } else if (!cfg.required) {
                    cfg.el.value = '';
                }
            });
        }

        const selectedPlanSheet = planSheetSelect ? planSheetSelect.value : '';
        const selectedItemSheet = itemSheetSelect ? itemSheetSelect.value : '';
        const selectedOpSheet = opSheetSelect ? opSheetSelect.value : '';
        const selectedLtSheet = ltSheetSelect ? ltSheetSelect.value : '';

        if (document.getElementById('map-plan-sheet-name')) document.getElementById('map-plan-sheet-name').innerText = selectedPlanSheet || '-';
        if (document.getElementById('map-item-sheet-name')) document.getElementById('map-item-sheet-name').innerText = selectedItemSheet || '-';
        if (document.getElementById('map-op-sheet-name')) document.getElementById('map-op-sheet-name').innerText = selectedOpSheet || 'Nenhuma';
        if (document.getElementById('map-lt-sheet-name')) document.getElementById('map-lt-sheet-name').innerText = selectedLtSheet || 'Nenhuma';

        const planHeaders = (this.headersData.sheets_headers && selectedPlanSheet && this.headersData.sheets_headers[selectedPlanSheet]) || [];
        const itemHeaders = (this.headersData.sheets_headers && selectedItemSheet && this.headersData.sheets_headers[selectedItemSheet]) || [];
        const opHeaders = (this.headersData.sheets_headers && selectedOpSheet && this.headersData.sheets_headers[selectedOpSheet]) || [];
        const ltHeaders = (this.headersData.sheets_headers && selectedLtSheet && this.headersData.sheets_headers[selectedLtSheet]) || [];

        const planFields = [
            { key: 'legacy_code', label: 'Código do Plano', candidates: ['plano', 'codigo', 'código', 'code'] },
            { key: 'description', label: 'Descrição do Plano', candidates: ['descrição', 'descricao', 'desc', 'nome'] },
            { key: 'cycle', label: 'Ciclo', candidates: ['ciclo', 'cycle'] },
            { key: 'unit', label: 'Unidade', candidates: ['unid', 'unidade', 'unit', 'und'] },
            { key: 'cycle_text', label: 'Texto do Ciclo', candidates: ['texto ciclo', 'texto'] },
            { key: 'opening_horizon', label: 'Horizonte Abertura', candidates: ['horizonte', 'horiz'] },
            { key: 'reference_counter', label: 'Contador Ref.', candidates: ['contador', 'parada', 'ref'] }
        ];

        const itemFields = [
            { key: 'legacy_identifier', label: 'Identificador / ID', candidates: ['identificador', 'id', 'numero', 'número', 'num'], allowAuto: true },
            { key: 'object_code', label: 'Equipamento / Local', candidates: ['local', 'equipamento', 'objeto', 'floc'] },
            { key: 'gpm', label: 'GPM (Técnico Resp.)', candidates: ['gpm', 'tecnico', 'técnico', 'resp'] },
            { key: 'work_center', label: 'Centro de Trabalho', candidates: ['centro', 'equipe', 'work center', 'ct'] },
            { key: 'condition_code', label: 'Condição (P/Q/F/M)', candidates: ['condição', 'condicao', 'cond'] },
            { key: 'priority', label: 'Prioridade (0 a 3)', candidates: ['prioridade', 'prio'] },
            { key: 'plan_code', label: 'Plano de Reparo / Inspeção', candidates: ['inspeção', 'inspecao', 'plano', 'plan', 'cod plano'] },
            { key: 'description', label: 'Descrição do Item', candidates: ['descrição', 'descricao', 'desc', 'titulo'] },
            { key: 'duration_hours', label: 'Horas da Atividade', candidates: ['t(h)', 'duracao', 'duração', 'horas', 'tempo'] },
            { key: 'headcount', label: 'Homens / Efetivo', candidates: ['homem', 'homens', 'efetivo', 'headcount', 'pessoas', 'qtd pessoas'] }
        ];

        const opFields = [
            { key: 'legacy_identifier', label: 'ID do Item Vinculado', candidates: ['identificador', 'id', 'item', 'num', 'numero', 'nro'] },
            { key: 'operation_code', label: 'Código Operação', candidates: ['operacao', 'oper', 'codigo', 'code'] },
            { key: 'suboperation_code', label: 'Suboperação', candidates: ['suboperacao', 'suboper', 'sub'] },
            { key: 'work_center', label: 'Centro de Trabalho', candidates: ['centrodetrabalho', 'centro', 'ct', 'workcenter', 'equipe'] },
            { key: 'short_text', label: 'Texto Breve / Descrição', candidates: ['textobreve', 'descricao', 'desc', 'texto', 'titulo'] },
            { key: 'headcount', label: 'Efetivo (Homens)', candidates: ['efetivo', 'homens', 'headcount', 'pessoas', 'homem', 'qtd'] },
            { key: 'hours', label: 'Horas da Operação', candidates: ['horas', 'duracao', 'duration', 'dura', 'th', 'tempo'] },
            { key: 'unit', label: 'Unidade', candidates: ['unidade', 'unit', 'unid'] }
        ];

        const ltFields = [
            { key: 'legacy_identifier', label: 'ID do Item Vinculado', candidates: ['identificador', 'id', 'item', 'num', 'numero', 'nro'] },
            { key: 'operation_code', label: 'Código Operação (OPER)', candidates: ['oper', 'operacao', 'operação', 'code'] },
            { key: 'suboperation_code', label: 'Suboperação (SUB OPER)', candidates: ['suboper', 'sub oper', 'suboperacao', 'suboperação', 'sub'] },
            { key: 'text', label: 'Texto Longo / Procedimento', candidates: ['descricaodaoperacao', 'descricaodaoperacao', 'textolongo', 'procedimentotecnico', 'procedimento', 'texto', 'desc'] }
        ];

        const normText = str => (str || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');

        const buildDropdown = (fieldObj, headers, sheetType) => {
            let html = `<div style="display:flex; justify-content:space-between; align-items:center; font-size:11.5px;">`;
            html += `<span style="font-weight:600; color:var(--text-color);">${fieldObj.label}:</span>`;
            html += `<select class="map-select" data-sheet="${sheetType}" data-field="${fieldObj.key}" style="padding:3px 6px; font-size:11px; max-width:175px; border-radius:4px; border:1px solid var(--border-color);">`;
            if (fieldObj.allowAuto) {
                html += `<option value="-1">⚡ Auto-gerar (1, 2, 3...)</option>`;
            } else {
                html += `<option value="-1">-- Selecione --</option>`;
            }
            let bestIdx = -1;
            const normalizedCandidates = fieldObj.candidates.map(normText).filter(Boolean);
            // Prefer an exact normalized header match across the whole row.
            // This disambiguates OPERAÇÃO (description) from oper (code), and
            // Texto breve from Texto (long-text content).
            for (const candidate of normalizedCandidates) {
                const exactIdx = headers.findIndex(header => normText(header) === candidate);
                if (exactIdx !== -1) {
                    bestIdx = exactIdx;
                    break;
                }
            }
            if (bestIdx === -1) {
                for (let idx = 0; idx < headers.length && bestIdx === -1; idx++) {
                    const hNorm = normText(headers[idx]);
                    if (normalizedCandidates.some(candNorm => hNorm.includes(candNorm) || candNorm.includes(hNorm))) {
                        bestIdx = idx;
                    }
                }
            }
            headers.forEach((h, idx) => {
                html += `<option value="${idx}">${h}</option>`;
            });
            html += `</select></div>`;
            return { html, bestIdx };
        };

        const planContainer = document.getElementById('mapping-fields-plans');
        const itemContainer = document.getElementById('mapping-fields-items');
        const opContainer = document.getElementById('mapping-fields-ops');
        const ltContainer = document.getElementById('mapping-fields-lts');

        if (planContainer) planContainer.innerHTML = '';
        if (itemContainer) itemContainer.innerHTML = '';
        if (opContainer) opContainer.innerHTML = selectedOpSheet ? '' : '<p style="font-size:11px; color:var(--text-muted); font-style:italic;">Aba não selecionada (opcional).</p>';
        if (ltContainer) ltContainer.innerHTML = selectedLtSheet ? '' : '<p style="font-size:11px; color:var(--text-muted); font-style:italic;">Aba não selecionada (opcional).</p>';

        if (planContainer) {
            planFields.forEach(f => {
                const { html, bestIdx } = buildDropdown(f, planHeaders, 'plans');
                planContainer.insertAdjacentHTML('beforeend', html);
                const sel = planContainer.querySelector(`select[data-field="${f.key}"]`);
                if (bestIdx !== -1) sel.value = bestIdx;
            });
        }

        if (itemContainer) {
            itemFields.forEach(f => {
                const { html, bestIdx } = buildDropdown(f, itemHeaders, 'items');
                itemContainer.insertAdjacentHTML('beforeend', html);
                const sel = itemContainer.querySelector(`select[data-field="${f.key}"]`);
                if (bestIdx !== -1) sel.value = bestIdx;
                else if (f.allowAuto) sel.value = "-1";
            });
        }

        if (opContainer && selectedOpSheet) {
            opFields.forEach(f => {
                const { html, bestIdx } = buildDropdown(f, opHeaders, 'operations');
                opContainer.insertAdjacentHTML('beforeend', html);
                const sel = opContainer.querySelector(`select[data-field="${f.key}"]`);
                if (bestIdx !== -1) sel.value = bestIdx;
            });
        }

        if (ltContainer && selectedLtSheet) {
            ltFields.forEach(f => {
                const { html, bestIdx } = buildDropdown(f, ltHeaders, 'long_texts');
                ltContainer.insertAdjacentHTML('beforeend', html);
                const sel = ltContainer.querySelector(`select[data-field="${f.key}"]`);
                if (bestIdx !== -1) sel.value = bestIdx;
            });
        }
    },

    async loadExistingProjectsList() {
        try {
            const list = await API.get('/api/projects');
            const select = document.getElementById('import-select-existing-project');
            select.innerHTML = '';
            
            if (list.length === 0) {
                // Force "new project" if none exists
                document.querySelector('input[name="import-target-mode"][value="new"]').click();
                document.querySelector('input[name="import-target-mode"][value="existing"]').disabled = true;
                select.innerHTML = '<option value="">Nenhum projeto cadastrado</option>';
            } else {
                document.querySelector('input[name="import-target-mode"][value="existing"]').disabled = false;
                const activeProjectId = window.App?.getValidProjectId();
                list.forEach(p => {
                    const locked = Boolean(p.is_locked);
                    const selected = Number(p.id) === Number(activeProjectId) && !locked;
                    select.innerHTML += `<option value="${p.id}" ${locked ? 'disabled' : ''} ${selected ? 'selected' : ''}>${p.name} (${p.area || 'Sem Área'})${locked ? ' — TRANCADO' : ''}</option>`;
                });
                if (activeProjectId && select.value !== String(activeProjectId)) {
                    const activeProject = list.find(p => Number(p.id) === Number(activeProjectId));
                    if (activeProject?.is_locked) {
                        UI.showToast('O projeto ativo está trancado. Destranque-o antes de importar.', 'warning', 7000);
                    }
                }
            }
        } catch (err) {
            console.error("Falha ao buscar projetos existentes:", err);
        }
    },

    navigate(dir) {
        const nextStep = this.currentStep + dir;
        
        if (nextStep === 2 && dir === 1) {
            // Load existing projects list for step 2
            this.loadExistingProjectsList();
        }

        if (nextStep === 3 && dir === 1) {
            // Trigger preview calculation when entering the diagnosis step
            this.fetchPreviewData();
            return; // Navigation will be completed in callback
        }

        this.goToStep(nextStep);
    },

    goToStep(stepNum) {
        // Hide all panes
        for (let i = 1; i <= 4; i++) {
            document.getElementById(`import-pane-${i}`).classList.add('hidden');
            const indicator = document.querySelector(`.step-indicator[data-step="${i}"]`);
            if (indicator) {
                indicator.classList.remove('active', 'completed');
                if (i < stepNum) indicator.classList.add('completed');
                if (i === stepNum) indicator.classList.add('active');
            }
        }

        // Show target pane
        document.getElementById(`import-pane-${stepNum}`).classList.remove('hidden');
        this.currentStep = stepNum;
        this.updateWizardButtons();
    },

    updateWizardButtons() {
        const prevBtn = document.getElementById('btn-import-prev');
        const nextBtn = document.getElementById('btn-import-next');
        const confirmBtn = document.getElementById('btn-import-confirm');

        // Reset
        prevBtn.classList.remove('hidden');
        nextBtn.classList.remove('hidden');
        confirmBtn.classList.add('hidden');

        // Step 1
        if (this.currentStep === 1) {
            prevBtn.disabled = true;
            nextBtn.disabled = this.selectedFile === null || this.getSelectedEntities().length === 0;
        } 
        // Step 2
        else if (this.currentStep === 2) {
            prevBtn.disabled = false;
            nextBtn.disabled = false;
        }
        // Step 3: diagnosis
        else if (this.currentStep === 3) {
            prevBtn.disabled = false;
            nextBtn.classList.add('hidden');
            confirmBtn.classList.remove('hidden');
            
            // Enable confirm only if we parsed successfully and there are no fatal problems (or let user confirm despite warnings)
            confirmBtn.disabled = !this.previewData;
        }
        // Step 4: conclusion
        else if (this.currentStep === 4) {
            prevBtn.classList.add('hidden');
            nextBtn.classList.add('hidden');
            confirmBtn.classList.add('hidden');
        }
    },

    reset() {
        this.currentStep = 1;
        this.selectedFile = null;
        this.previewData = null;
        this.headersData = null;
        document.querySelectorAll('.import-entity-check').forEach(check => {
            check.checked = this.importScope === 'full' || check.value === this.importScope;
        });
        this.updateEntitySelectionUI();

        const fileInput = document.getElementById('import-file-input');
        if (fileInput) fileInput.value = '';

        const fileBox = document.getElementById('file-details-box');
        if (fileBox) fileBox.classList.add('hidden');

        const dropzone = document.getElementById('upload-dropzone');
        if (dropzone) dropzone.classList.remove('hidden');

        this.goToStep(1);
    },

    async fetchPreviewData() {
        if (!this.selectedFile) return;

        // Collect visual column mapping + explicit sheet selection + duration unit
        const planSheetEl = document.getElementById('select-plan-sheet');
        const itemSheetEl = document.getElementById('select-item-sheet');
        const opSheetEl = document.getElementById('select-op-sheet');
        const ltSheetEl = document.getElementById('select-lt-sheet');
        const durationUnitEl = document.getElementById('import-duration-unit');
        const colMapping = {
            plan_sheet_name: planSheetEl ? planSheetEl.value : null,
            item_sheet_name: itemSheetEl ? itemSheetEl.value : null,
            op_sheet_name: opSheetEl ? opSheetEl.value : null,
            lt_sheet_name: ltSheetEl ? ltSheetEl.value : null,
            duration_unit: durationUnitEl ? durationUnitEl.value : 'MINUTES',
            selected_entities: this.getSelectedEntities(),
            plans: {},
            items: {},
            operations: {},
            long_texts: {}
        };
        document.querySelectorAll('.map-select').forEach(sel => {
            const sheet = sel.getAttribute('data-sheet');
            const field = sel.getAttribute('data-field');
            const val = parseInt(sel.value);
            if (colMapping[sheet] && !isNaN(val) && val >= 0) {
                colMapping[sheet][field] = val;
            }
        });

        const formData = new FormData();
        formData.append('file', this.selectedFile);
        formData.append('column_mapping', JSON.stringify(colMapping));

        UI.showLoader("Analisando planilha Excel (extraindo dados e validando)...");
        Logger?.log?.(`Prévia iniciada: ${this.selectedFile.name}; entidades=${this.getSelectedEntities().join(',')}`, 'IMPORT');
        try {
            // Note: Since API.request handles JSON wrapping, we call raw fetch here for Multipart uploading
            const response = await fetch('/api/import/preview', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errJson = await response.json();
                throw new Error(errJson.error || "Erro na análise da planilha.");
            }

            this.previewData = await response.json();
            
            // Update preview summaries
            const s = this.previewData.summary;
            document.getElementById('diag-total-plans').innerText = s.total_plans;
            document.getElementById('diag-total-items').innerText = s.total_items;
            document.getElementById('diag-total-operations').innerText = s.total_operations || 0;
            document.getElementById('diag-total-long-texts').innerText = s.total_long_texts || 0;
            document.getElementById('diag-error-count').innerText = s.error_count;
            document.getElementById('diag-warning-count').innerText = s.warning_count;

            UI.showToast("Análise concluída. Diagnóstico gerado com sucesso!");
            Logger?.log?.(`Prévia concluída: planos=${s.total_plans}, itens=${s.total_items}, operações=${s.total_operations || 0}, textos=${s.total_long_texts || 0}, erros=${s.error_count}`, 'IMPORT');
            
            // Go to step 4
            this.goToStep(3);
            this.renderDiagnosisTable();

        } catch (err) {
            Logger?.log?.(`Falha na prévia: ${err.message}`, 'IMPORT');
            UI.showToast(`Erro na análise do arquivo: ${err.message}`, 'error', 14000);
        } finally {
            UI.hideLoader();
        }
    },

    renderDiagnosisTable() {
        if (!this.previewData) return;

        const tbody = document.getElementById('diag-errors-table-body');
        tbody.innerHTML = '';

        const severityFilter = document.getElementById('diag-filter-severity').value;
        const errors = this.previewData.errors;

        const filteredErrors = errors.filter(e => {
            if (severityFilter === 'all') return true;
            return e.severity === severityFilter;
        });

        if (filteredErrors.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-table-cell" style="color:var(--primary-dark);">Nenhuma inconsistência encontrada para esta categoria! Tudo limpo.</td></tr>`;
            return;
        }

        filteredErrors.forEach(e => {
            const tr = document.createElement('tr');
            tr.className = e.severity === 'ERROR' ? 'diag-row-error' : 'diag-row-warning';
            tr.innerHTML = `
                <td>${e.sheet_name}</td>
                <td>Linha ${e.row_number}</td>
                <td><strong>${e.field_name}</strong></td>
                <td><span class="badge ${e.severity === 'ERROR' ? 'badge-danger' : 'badge-warning'}">${e.severity}</span></td>
                <td>${e.message}</td>
                <td style="font-family:monospace; font-size:11px;">${e.original_value !== null ? e.original_value : ''}</td>
            `;
            tbody.appendChild(tr);
        });
    },

    async loadExistingProjectsList() {
        try {
            const list = await API.get('/api/projects');
            this.existingProjectsList = list || [];
            const select = document.getElementById('import-select-existing-project');
            select.innerHTML = '';
            
            if (list.length === 0) {
                // Force "new project" if none exists
                document.querySelector('input[name="import-target-mode"][value="new"]').click();
                document.querySelector('input[name="import-target-mode"][value="existing"]').disabled = true;
                select.innerHTML = '<option value="">Nenhum projeto cadastrado</option>';
            } else {
                document.querySelector('input[name="import-target-mode"][value="existing"]').disabled = false;
                const activeProjectId = window.App?.getValidProjectId();
                list.forEach(p => {
                    const locked = Boolean(p.is_locked);
                    const selected = Number(p.id) === Number(activeProjectId) && !locked;
                    select.innerHTML += `<option value="${p.id}" ${locked ? 'disabled' : ''} ${selected ? 'selected' : ''}>${p.name} (${p.area || 'Sem Área'})${locked ? ' — TRANCADO' : ''}</option>`;
                });
                if (activeProjectId && select.value !== String(activeProjectId)) {
                    const activeProject = list.find(p => Number(p.id) === Number(activeProjectId));
                    if (activeProject?.is_locked) {
                        UI.showToast('O projeto ativo está trancado. Destranque-o antes de importar.', 'warning', 7000);
                    }
                }
            }
        } catch (err) {
            console.error("Falha ao buscar projetos existentes:", err);
        }
    },

    async confirm() {
        if (!this.previewData) return;
        const selectedEntities = this.getSelectedEntities();
        if (!selectedEntities.length) return UI.showToast('Selecione pelo menos um tipo de dado para importar.', 'warning');
        const importSummary = { ...this.previewData.summary };

        const mode = document.querySelector('input[name="import-target-mode"]:checked').value;
        const mergeMode = document.getElementById('import-merge-mode').value;
        
        let projectId = null;
        
        // 1. Create project if "new"
        if (mode === 'new') {
            const selected = new Set(selectedEntities);
            const missingDependency =
                (selected.has('long_texts') && !selected.has('operations')) ||
                (selected.has('operations') && !selected.has('items')) ||
                (selected.has('items') && !selected.has('plans'));
            if (missingDependency) {
                UI.showToast('Em um projeto novo, marque também as dependências anteriores: Planos → Itens → Operações → Textos longos.', 'warning', 9000);
                return;
            }
            const name = document.getElementById('import-new-proj-name').value.trim();
            const area = document.getElementById('import-new-proj-area').value.trim();
            
            if (!name) {
                UI.showToast("Nome do novo projeto é obrigatório.", "error");
                return;
            }

            // Check if name already exists to give friendly user feedback
            if (this.existingProjectsList && this.existingProjectsList.some(p => p.name.trim().toLowerCase() === name.toLowerCase())) {
                UI.showToast(`Já existe um projeto cadastrado com o nome "${name}". Volte na etapa 2 e informe outro nome ou escolha "Mesclar em Projeto Existente".`, 'warning', 9000);
                return;
            }

            UI.showLoader("Criando novo projeto de destino...");
            try {
                const res = await API.post('/api/projects', {
                    name: name,
                    description: `Criado a partir da importação da planilha: ${importSummary.filename}`,
                    area: area,
                    current_counter: 106,
                    default_horizon: 12,
                    utilization_factor: 1.0
                });
                projectId = res.id;
            } catch (err) {
                UI.showToast(`Erro ao criar projeto: ${err.message}`, 'error');
                UI.hideLoader();
                return;
            }
        } else {
            // Existing project
            projectId = parseInt(document.getElementById('import-select-existing-project').value);
            if (!projectId) {
                UI.showToast("Selecione um projeto de destino válido.", "error");
                return;
            }
            const targetProject = (this.existingProjectsList || []).find(p => Number(p.id) === Number(projectId));
            if (targetProject?.is_locked) {
                UI.showToast(`O projeto de destino "${targetProject.name}" está trancado. Selecione o projeto ativo ou destranque o destino.`, 'warning', 8000);
                return;
            }
            if (mergeMode === 'replace') {
                const labels = {plans:'planos', items:'itens', operations:'operações', long_texts:'textos longos'};
                const scopeText = selectedEntities.map(key => labels[key]).join(', ');
                const dependencySafety = selectedEntities.length < 4
                    ? ' Se algum registro extra possuir dependentes fora da seleção, a importação será recusada com rollback e o sistema informará quais tipos também devem ser marcados.'
                    : '';
                if (!window.confirm(`SUBSTITUIR: ${scopeText} ficarão exatamente como na planilha. Registros extras desses tipos serão excluídos.${dependencySafety} Deseja continuar?`)) return;
                if (!window.confirm('Confirmação final: um backup será criado antes da substituição. Deseja prosseguir?')) return;
            }
        }

        // 2. confirm import on database
        UI.showLoader("Importando dados do plano (executando transação)...");
        Logger?.log?.(`Gravação iniciada: projeto=${projectId}; modo=${mode === 'new' ? 'replace' : mergeMode}; entidades=${selectedEntities.join(',')}`, 'IMPORT');
        try {
            const res = await API.post('/api/import/confirm', {
                project_id: projectId,
                preview_data: this.previewData,
                merge_mode: mode === 'new' ? 'replace' : mergeMode,
                selected_entities: selectedEntities
            });
            
            // Successfully imported!
            UI.showToast("Gravação concluída com sucesso!");
            Logger?.log?.(`Gravação concluída: projeto=${projectId}; import_id=${res.import_id}`, 'IMPORT');
            
            // Set active project state
            const projName = mode === 'new' 
                ? document.getElementById('import-new-proj-name').value.trim()
                : document.getElementById('import-select-existing-project').options[document.getElementById('import-select-existing-project').selectedIndex].text;
                
            window.App.setActiveProject(projectId, projName, 106);
            
            // Update step finished info
            document.getElementById('import-success-msg').innerHTML = `
                Foram inseridos com sucesso:<br>
                <strong>${importSummary.valid_plans} planos</strong>, <strong>${importSummary.valid_items} itens</strong>,
                <strong>${importSummary.total_operations || 0} operações</strong> e
                <strong>${importSummary.total_long_texts || 0} textos longos</strong> no projeto "${projName}".<br>
                <small>Tipos processados: ${selectedEntities.join(', ')}. Os demais foram preservados.</small>
            `;
            
            this.goToStep(4);
        } catch (err) {
            Logger?.log?.(`Falha ao gravar importação: ${err.message}`, 'IMPORT');
            UI.showToast(`Erro ao gravar importação: ${err.message}`, 'error', 14000);
        } finally {
            UI.hideLoader();
        }
    }
};

window.ImportWizard = ImportWizard;
