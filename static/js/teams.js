/**
 * Work Teams (Equipes de Trabalho) View & CRUD Controller
 */

const Teams = {
    teams: [],

    init() {
        // New Team Button
        const btnNew = document.getElementById('btn-new-team');
        if (btnNew) {
            btnNew.onclick = () => this.openModal();
        }

        // Form Submit
        const form = document.getElementById('form-team');
        if (form) {
            form.onsubmit = (e) => {
                e.preventDefault();
                this.saveTeam();
            };
        }

        // Real-time preview calculation listeners in modal
        ['team-num-shifts', 'team-shift-hours', 'team-tool-time', 'team-stop-days'].forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                input.oninput = () => this.updateModalPreview();
                input.onchange = () => this.updateModalPreview();
            }
        });
    },

    async load() {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        UI.showLoader("Carregando equipes de trabalho...");
        try {
            this.teams = await API.get('/api/teams', { project_id: projId });
            this.renderTable();
            this.renderKPIs();
        } catch (err) {
            UI.showToast(`Erro ao carregar equipes: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    renderKPIs() {
        const totalTeams = this.teams.length;
        let totalDailyProdHours = 0;
        let totalToolTimeSum = 0;

        this.teams.forEach(t => {
            const prodHoursShift = t.shift_hours * (t.tool_time_percent / 100.0);
            const dailyProdHours = t.num_shifts * prodHoursShift;

            totalDailyProdHours += dailyProdHours;
            totalToolTimeSum += t.tool_time_percent;
        });

        const avgToolTime = totalTeams > 0 ? Math.round(totalToolTimeSum / totalTeams) : 90;

        document.getElementById('t-kpi-total-teams').innerText = totalTeams;
        document.getElementById('t-kpi-daily-hh').innerText = `${totalDailyProdHours.toFixed(1).replace('.', ',')} h/pess`;
        document.getElementById('t-kpi-avg-tooltime').innerText = `${avgToolTime}%`;
    },

    renderTable() {
        const tbody = document.getElementById('teams-table-body');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (this.teams.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center p-20 text-muted">Nenhuma equipe de trabalho cadastrada neste projeto. Clique em "+ Nova Equipe" para adicionar.</td></tr>`;
            return;
        }

        this.teams.forEach(t => {
            const prodHoursShift = t.shift_hours * (t.tool_time_percent / 100.0);
            const stopProdHours = t.num_shifts * prodHoursShift * t.stop_days;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><strong>${t.name}</strong></td>
                <td class="text-center">${t.work_center ? `<code>${t.work_center}</code>` : '<span class="text-muted">-</span>'}</td>
                <td class="text-center"><span class="badge badge-info">${t.num_shifts} Turno${t.num_shifts > 1 ? 's' : ''}</span></td>
                <td class="text-center">${t.shift_hours.toFixed(1).replace('.', ',')}h</td>
                <td class="text-center"><span class="badge badge-success">${Math.round(t.tool_time_percent)}%</span></td>
                <td class="text-center"><strong>${prodHoursShift.toFixed(2).replace('.', ',')}h</strong></td>
                <td class="text-center">${t.stop_days} dia${t.stop_days > 1 ? 's' : ''}</td>
                <td class="text-center"><strong class="txt-primary">${stopProdHours.toFixed(1).replace('.', ',')} h/pess</strong></td>
                <td class="text-center">
                    <button class="btn btn-xs btn-outline" onclick="Teams.openModal(${t.id})">Editar</button>
                    <button class="btn btn-xs btn-outline" onclick="Teams.duplicateTeam(${t.id})">Duplicar</button>
                    <button class="btn btn-xs btn-danger" onclick="Teams.deleteTeam(${t.id})">Excluir</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    },

    openModal(teamId = null) {
        const modal = document.getElementById('modal-team');
        const title = document.getElementById('modal-team-title');
        const form = document.getElementById('form-team');
        if (!modal || !form) return;

        form.reset();
        document.getElementById('team-id').value = '';

        if (teamId) {
            const t = this.teams.find(item => item.id === teamId);
            if (t) {
                title.innerText = 'Editar Equipe de Trabalho';
                document.getElementById('team-id').value = t.id;
                document.getElementById('team-name').value = t.name;
                document.getElementById('team-wc').value = t.work_center || '';
                document.getElementById('team-num-shifts').value = t.num_shifts;
                document.getElementById('team-shift-hours').value = t.shift_hours;
                document.getElementById('team-tool-time').value = t.tool_time_percent;
                document.getElementById('team-stop-days').value = t.stop_days;
                document.getElementById('team-notes').value = t.notes || '';
            }
        } else {
            title.innerText = 'Cadastrar Equipe de Trabalho';
            document.getElementById('team-num-shifts').value = '1';
            document.getElementById('team-shift-hours').value = '9.0';
            document.getElementById('team-tool-time').value = '90';
            document.getElementById('team-stop-days').value = '1';
        }

        this.updateModalPreview();
        modal.classList.remove('hidden');
    },

    updateModalPreview() {
        const numShifts = parseInt(document.getElementById('team-num-shifts').value) || 1;
        const shiftHours = parseFloat(document.getElementById('team-shift-hours').value) || 9.0;
        const toolTime = parseFloat(document.getElementById('team-tool-time').value) || 90.0;
        const stopDays = parseInt(document.getElementById('team-stop-days').value) || 1;

        const prodHoursShift = shiftHours * (toolTime / 100.0);
        const stopProdHours = numShifts * prodHoursShift * stopDays;

        const elProd = document.getElementById('team-preview-prod-hours');
        if (elProd) elProd.innerText = `${prodHoursShift.toFixed(2).replace('.', ',')}h`;

        const elStop = document.getElementById('team-preview-stop-hh');
        if (elStop) elStop.innerText = `${stopProdHours.toFixed(1).replace('.', ',')}h / pess`;
    },

    async saveTeam() {
        const projId = window.App.currentProjectId;
        if (!projId) return;

        const teamId = document.getElementById('team-id').value;
        const data = {
            project_id: projId,
            name: document.getElementById('team-name').value,
            work_center: document.getElementById('team-wc').value,
            num_shifts: document.getElementById('team-num-shifts').value,
            shift_hours: document.getElementById('team-shift-hours').value,
            tool_time_percent: document.getElementById('team-tool-time').value,
            stop_days: document.getElementById('team-stop-days').value,
            notes: document.getElementById('team-notes').value
        };

        UI.showLoader("Salvando equipe...");
        try {
            if (teamId) {
                await API.put(`/api/teams/${teamId}`, data);
                UI.showToast("Equipe de trabalho atualizada com sucesso!");
            } else {
                await API.post('/api/teams', data);
                UI.showToast("Equipe de trabalho cadastrada com sucesso!");
            }
            document.getElementById('modal-team').classList.add('hidden');
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao salvar equipe: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async deleteTeam(teamId) {
        const t = this.teams.find(item => item.id === teamId);
        const name = t ? t.name : 'esta equipe';

        if (!confirm(`Deseja realmente excluir a equipe "${name}"?`)) return;

        UI.showLoader("Excluindo equipe...");
        try {
            await API.delete(`/api/teams/${teamId}`);
            UI.showToast("Equipe excluída com sucesso!");
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao excluir equipe: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    async duplicateTeam(teamId) {
        const source = this.teams.find(item => item.id === teamId);
        if (!source) {
            UI.showToast('Equipe de origem não encontrada.', 'error');
            return;
        }

        const existingNames = new Set(this.teams.map(team => String(team.name || '').trim().toLowerCase()));
        const baseName = `${source.name} - Cópia`;
        let copyName = baseName;
        let copyNumber = 2;
        while (existingNames.has(copyName.toLowerCase())) {
            copyName = `${baseName} ${copyNumber++}`;
        }

        const data = {
            project_id: window.App.currentProjectId,
            name: copyName,
            work_center: source.work_center || '',
            num_shifts: source.num_shifts,
            shift_hours: source.shift_hours,
            headcount_per_shift: source.headcount_per_shift || 1,
            tool_time_percent: source.tool_time_percent,
            stop_days: source.stop_days,
            notes: source.notes || ''
        };

        UI.showLoader('Duplicando equipe...');
        try {
            await API.post('/api/teams', data);
            UI.showToast(`Equipe "${copyName}" duplicada com sucesso!`);
            await this.load();
        } catch (err) {
            UI.showToast(`Erro ao duplicar equipe: ${err.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    }
};

window.Teams = Teams;
