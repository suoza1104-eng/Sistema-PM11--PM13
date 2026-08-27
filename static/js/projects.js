/**
 * Projects View & Model Controller
 */

const Projects = {
    list: [],

    init() {
        // Save project button (Create or Edit modal)
        const saveBtn = document.getElementById('btn-save-project');
        if (saveBtn) saveBtn.onclick = () => this.save();

        // Create project button on projects page
        const createBtn = document.getElementById('btn-create-project');
        if (createBtn) createBtn.onclick = () => this.openCreateModal();

        // Close modal buttons
        document.querySelectorAll('[data-close="modal-project"]').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-project').classList.add('hidden');
        });
    },

    async load() {
        if (window.Logger) window.Logger.log("Projects.load() entry", "PROJECTS");
        UI.showLoader("Carregando projetos...");
        try {
            this.list = await API.get('/api/projects');
            if (window.Logger) window.Logger.log(`Projects.load() fetched ${this.list ? this.list.length : 0} projects`, "PROJECTS");
            this.render();
        } catch (error) {
            if (window.Logger) window.Logger.log(`ERROR in Projects.load: ${error.message}`, "PROJECTS");
            UI.showToast(`Erro ao carregar projetos: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    render() {
        const container = document.getElementById('project-cards-container');
        if (!container) return;

        container.innerHTML = '';
        const activeProjId = window.App.getValidProjectId();
        const projectList = Array.isArray(this.list) ? this.list : [];

        if (projectList.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
                    <h3>Nenhum projeto cadastrado</h3>
                    <p>Crie um novo projeto vazio ou importe de uma planilha para iniciar.</p>
                </div>
            `;
            return;
        }

        projectList.forEach(p => {
            const isActive = p.id === activeProjId;
            const isLocked = Boolean(p.is_locked);
            const statusLabel = `${p.status === 'ARCHIVED' ? '<span class="badge badge-inactive">Arquivado</span>' : '<span class="badge badge-active">Ativo</span>'}${isLocked ? '<span class="badge badge-inactive" style="margin-left:5px;">🔒 Trancado</span>' : ''}`;
            
            const card = document.createElement('div');
            card.className = `project-card ${isActive ? 'active-border' : ''}`;
            if (isActive) {
                card.style.borderColor = 'var(--primary-color)';
                card.style.borderWidth = '2px';
            }

            card.innerHTML = `
                <div class="project-card-header">
                    <div>
                        <h3>${p.name}</h3>
                        <span style="font-size: 11px; color: var(--text-muted);">${p.area || 'Sem Área'} ${p.system_name ? `• ${p.system_name}` : ''}</span>
                    </div>
                    ${statusLabel}
                </div>
                <div class="project-card-body">
                    <p>${p.description || 'Sem descrição cadastrada.'}</p>
                    <div class="project-stats-grid">
                        <div class="proj-stat-item">
                            <span class="proj-stat-lbl">Planos</span>
                            <span class="proj-stat-val">${p.plans_count}</span>
                        </div>
                        <div class="proj-stat-item">
                            <span class="proj-stat-lbl">Itens</span>
                            <span class="proj-stat-val">${p.items_count}</span>
                        </div>
                        <div class="proj-stat-item">
                            <span class="proj-stat-lbl">Área</span>
                            <span class="proj-stat-val" style="font-size:12px;">${p.area || '-'}</span>
                        </div>
                        <div class="proj-stat-item">
                            <span class="proj-stat-lbl">Sistema</span>
                            <span class="proj-stat-val" style="font-size:12px;">${p.system_name || '-'}</span>
                        </div>
                    </div>
                </div>
                <div class="project-card-footer">
                    ${isActive ? 
                        `<button class="btn btn-sm btn-secondary" disabled>Aberto</button>` : 
                        `<button class="btn btn-sm btn-primary" onclick="Projects.open(${p.id})">Abrir</button>`
                    }
                    <button class="btn btn-sm ${isLocked ? 'btn-secondary' : 'btn-outline'}" onclick="Projects.toggleLock(${p.id})" title="${isLocked ? 'Destrancar projeto e liberar edições' : 'Trancar projeto contra qualquer alteração'}">${isLocked ? '🔓 Destrancar' : '🔒 Trancar'}</button>
                    <button class="btn btn-sm btn-outline" onclick="Projects.openEditModal(${p.id})">Editar</button>
                    <button class="btn btn-sm btn-outline" onclick="Projects.openDuplicateModal(${p.id})">Duplicar</button>
                    <button class="btn btn-sm btn-danger" onclick="Projects.delete(${p.id})" ${isActive ? 'disabled title="Não é possível excluir o projeto ativo"' : ''}>Excluir</button>
                </div>
            `;
            container.appendChild(card);
        });
    },

    async toggleLock(projectId) {
        const project = this.list.find(p => p.id === projectId);
        if (!project) return;
        const locking = !Boolean(project.is_locked);
        const message = locking
            ? `Trancar "${project.name}"? Nenhuma edição, importação ou movimentação será permitida até o projeto ser destrancado.`
            : `Destrancar "${project.name}" e liberar novamente todas as alterações?`;
        if (!window.confirm(message)) return;
        try {
            UI.showLoader(locking ? 'Trancando projeto...' : 'Destrancando projeto...');
            await API.post(`/api/projects/${projectId}/lock`, { locked: locking });
            UI.showToast(locking ? 'Projeto trancado. Apenas consultas estão liberadas.' : 'Projeto destrancado. Edições liberadas.', 'success', 4000);
            await this.load();
        } catch (error) {
            UI.showToast(`Erro ao alterar cadeado: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    open(projectId) {
        const proj = this.list.find(x => x.id === projectId);
        if (proj) {
            window.App.setActiveProject(proj.id, proj.name, proj.current_counter || 0);
            UI.showToast(`Projeto "${proj.name}" aberto com sucesso!`);
            this.render();
            // Go to dashboard
            window.location.hash = '#dashboard';
        }
    },

    openCreateModal() {
        document.getElementById('modal-project-title').innerText = "Novo Projeto PM13";
        document.getElementById('form-project-id').value = "";
        document.getElementById('form-project-name').value = "";
        document.getElementById('form-project-desc').value = "";
        document.getElementById('form-project-area').value = "";
        const sysEl = document.getElementById('form-project-system');
        if (sysEl) sysEl.value = "";
        
        document.getElementById('modal-project').classList.remove('hidden');
    },

    openEditModal(projectId) {
        const proj = this.list.find(x => x.id === projectId);
        if (!proj) return;

        document.getElementById('modal-project-title').innerText = "Editar Projeto";
        document.getElementById('form-project-id').value = proj.id;
        document.getElementById('form-project-name').value = proj.name;
        document.getElementById('form-project-desc').value = proj.description || "";
        document.getElementById('form-project-area').value = proj.area || "";
        const sysEl = document.getElementById('form-project-system');
        if (sysEl) sysEl.value = proj.system_name || "";

        document.getElementById('modal-project').classList.remove('hidden');
    },

    openDuplicateModal(projectId) {
        const proj = this.list.find(x => x.id === projectId);
        if (!proj) return;

        const newName = prompt("Digite o nome para o novo projeto duplicado:", `${proj.name} (Simulação)`);
        if (newName === null) return; // Cancelled
        if (!newName.trim()) {
            UI.showToast("O nome do projeto é obrigatório.", "error");
            return;
        }

        this.duplicate(proj.id, newName.trim());
    },

    async duplicate(sourceId, newName) {
        UI.showLoader("Duplicando projeto...");
        try {
            const res = await API.post(`/api/projects/${sourceId}/duplicate`, { new_name: newName });
            UI.showToast(res.message);
            await this.load();
            // Automatically open the duplicated project
            this.open(res.id);
        } catch (error) {
            UI.showToast(`Erro ao duplicar projeto: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async delete(projectId) {
        const proj = this.list.find(x => x.id === projectId);
        if (!proj) {
            UI.showToast("Projeto não encontrado.", "error");
            return;
        }

        if (projectId === window.App.getValidProjectId()) {
            UI.showToast("Não é possível excluir o projeto que está aberto.", "warning");
            return;
        }

        const confirmed = window.confirm(
            `Excluir o projeto "${proj.name}"?\n\n` +
            "Os planos e itens vinculados deixarão de aparecer no sistema."
        );
        if (!confirmed) return;

        UI.showLoader("Excluindo projeto...");
        try {
            const res = await API.delete(`/api/projects/${projectId}`);
            UI.showToast(res?.message || "Projeto excluído com sucesso!");
            await this.load();
        } catch (error) {
            if (window.Logger) window.Logger.log(`ERROR in Projects.delete: ${error.message}`, "PROJECTS");
            UI.showToast(`Erro ao excluir projeto: ${error.message}`, "error");
        } finally {
            UI.hideLoader();
        }
    },

    async save() {
        const id = document.getElementById('form-project-id').value;
        const name = document.getElementById('form-project-name').value.trim();
        const desc = document.getElementById('form-project-desc').value.trim();
        const area = document.getElementById('form-project-area').value.trim();
        const sysEl = document.getElementById('form-project-system');
        const systemName = sysEl ? sysEl.value.trim() : "";

        if (!name) {
            UI.showToast("Nome do projeto é obrigatório.", 'error');
            return;
        }

        const data = {
            name: name,
            description: desc,
            area: area,
            system_name: systemName
        };

        UI.showLoader("Salvando projeto...");
        try {
            if (id) {
                // Edit
                const res = await API.put(`/api/projects/${id}`, data);
                UI.showToast("Projeto atualizado com sucesso!");
                if (parseInt(id) === window.App.currentProjectId) {
                    window.App.setActiveProject(id, name, 0);
                }
            } else {
                // Create
                const res = await API.post('/api/projects', data);
                UI.showToast("Projeto criado com sucesso!");
                window.App.setActiveProject(res.id, name, 0);
            }
            document.getElementById('modal-project').classList.add('hidden');
            await this.load();
        } catch (error) {
            UI.showToast(`Erro ao salvar projeto: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    }
};

window.Projects = Projects;
