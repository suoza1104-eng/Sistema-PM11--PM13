/**
 * Dashboard (Overview) View Controller
 */

const Dashboard = {
    data: null,

    async load() {
        const projId = window.App.getValidProjectId();
        if (window.Logger) window.Logger.log(`Dashboard.load() called. projId=${projId}`, 'DASHBOARD');
        if (!projId) return;

        UI.showLoader("Carregando painel gerencial...");
        try {
            this.data = await API.get('/api/dashboard', { project_id: projId });
            if (window.Logger) window.Logger.log(`Dashboard data fetched: total_plans=${this.data?.total_plans}, total_items=${this.data?.total_items}`, 'DASHBOARD');
            this.render();
            await this.loadChartAndStats(projId);
        } catch (error) {
            if (window.Logger) window.Logger.log(`ERROR in Dashboard.load: ${error.message}`, 'DASHBOARD');
            UI.showToast(`Erro ao carregar dados do painel: ${error.message}`, 'error');
        } finally {
            UI.hideLoader();
        }
    },

    render() {
        if (!this.data) return;

        const d = this.data;

        // Populate card values
        document.getElementById('dash-total-plans').innerText = d.total_plans;
        document.getElementById('dash-active-plans').innerText = `${d.active_plans} ativos`;

        document.getElementById('dash-total-items').innerText = d.total_items;
        document.getElementById('dash-active-items').innerText = `${d.active_items} ativos`;

        document.getElementById('dash-total-hh').innerText = Math.round(d.total_hh) + ' HH';
        document.getElementById('dash-avg-hh').innerText = `Média de ${Math.round(d.avg_hh)} HH / parada`;

        const incDisplay = document.getElementById('dash-inconsistencies');
        incDisplay.innerText = d.inconsistencies_count;
        if (d.inconsistencies_count > 0) {
            incDisplay.classList.add('txt-danger');
        } else {
            incDisplay.classList.remove('txt-danger');
        }

        this.renderManagerialInsights(d);

        // Render alert alerts list
        const alertsBox = document.getElementById('dash-alerts-box');
        const alertsList = document.getElementById('dash-alerts-list');
        alertsList.innerHTML = '';

        const alerts = [];
        if (d.plans_without_counter > 0) {
            alerts.push(`<a onclick="Dashboard.goToPlansFiltered('no_counter')">${d.plans_without_counter} planos sem contador de referência</a>`);
        }
        if (d.plans_without_items > 0) {
            alerts.push(`<a onclick="Dashboard.goToPlansFiltered('without_items')">${d.plans_without_items} planos sem itens vinculados</a>`);
        }
        if (d.items_without_plan > 0) {
            alerts.push(`<a onclick="Dashboard.goToItemsFiltered('without_plan')">${d.items_without_plan} itens sem plano cadastrado</a>`);
        }
        if (d.items_without_headcount > 0) {
            alerts.push(`<a onclick="Dashboard.goToItemsFiltered('without_headcount')">${d.items_without_headcount} itens sem efetivo definido</a>`);
        }
        if (d.items_duration_zero > 0) {
            alerts.push(`<a onclick="Dashboard.goToItemsFiltered('duration_zero')">${d.items_duration_zero} itens com duração igual a zero</a>`);
        }
        if (d.items_long_desc > 0) {
            alerts.push(`<a onclick="Dashboard.goToItemsFiltered('long_desc')">${d.items_long_desc} itens com descrição > 35 caracteres</a>`);
        }

        if (alerts.length > 0) {
            alertsBox.classList.remove('hidden');
            alertsList.innerHTML = alerts.join(' • ');
        } else {
            alertsBox.classList.add('hidden');
        }
    },

    renderManagerialInsights(d) {
        const quantitative = [
            { label: 'Ativos', value: Number(d.active_items || 0), color: '#72B900' },
            { label: 'Inativos', value: Number(d.inactive_items || 0), color: '#CBD5E1' }
        ];
        this.renderDonut('dash-quantitative-donut', 'dash-quantitative-legend', quantitative, 'itens');

        const quality = d.quality_distribution || {};
        const qualitative = [
            { label: 'Conformes', value: Number(quality.OK || 0), color: '#168A5B' },
            { label: 'Atenção', value: Number(quality.WARNING || 0), color: '#F2B84B' },
            { label: 'Críticos', value: Number(quality.ERROR || 0), color: '#D94B4B' }
        ];
        this.renderDonut('dash-quality-donut', 'dash-quality-legend', qualitative, 'conformes', qualitative[0].value);
        this.renderMethods(d.method_distribution || []);
    },

    renderDonut(donutId, legendId, segments, centerLabel, centerValue = null) {
        const donut = document.getElementById(donutId);
        const legend = document.getElementById(legendId);
        if (!donut || !legend) return;
        const total = segments.reduce((sum, item) => sum + item.value, 0);
        let cursor = 0;
        const stops = segments.map(item => {
            const start = cursor;
            cursor += total ? (item.value / total) * 100 : 0;
            return `${item.color} ${start}% ${cursor}%`;
        });
        donut.style.background = total ? `conic-gradient(${stops.join(',')})` : '#E2E8F0';
        donut.innerHTML = `<div><strong>${centerValue === null ? total : centerValue}</strong><span>${centerLabel}</span></div>`;
        legend.innerHTML = segments.map(item => {
            const pct = total ? Math.round(item.value * 100 / total) : 0;
            return `<div class="managerial-legend-row"><i style="background:${item.color}"></i><span>${item.label}</span><strong>${item.value}</strong><small>${pct}%</small></div>`;
        }).join('');
    },

    renderMethods(methods) {
        const host = document.getElementById('dash-method-distribution');
        if (!host) return;
        const total = methods.reduce((sum, item) => sum + Number(item.value || 0), 0);
        const palette = ['#72B900', '#1D8ACB', '#E59A2F', '#7557C7', '#0F766E'];
        if (!methods.length) {
            host.innerHTML = '<div class="managerial-empty">Nenhum método cadastrado.</div>';
            return;
        }
        host.innerHTML = methods.slice(0, 5).map((item, index) => {
            const value = Number(item.value || 0);
            const pct = total ? Math.round(value * 100 / total) : 0;
            return `<div class="managerial-method-row">
                <div><span>${UI.escapeHTML(item.label || 'Não definido')}</span><strong>${value} itens</strong></div>
                <div class="managerial-method-track"><i style="width:${pct}%;background:${palette[index % palette.length]}"></i></div>
                <small>${pct}%</small>
            </div>`;
        }).join('');
    },

    async loadChartAndStats(projId) {
        try {
            // Get balance data with work_center grouping to plot main graph and CT distribution
            const balanceData = await API.get('/api/balance', { project_id: projId, grouping: 'work_center' });
            
            // 1. Render Preview Chart
            UI.renderBarChart('dash-chart-container', balanceData.stops, {
                valueKey: 'total_hh',
                labelText: 'HH Projetado',
                groupBy: 'work_center',
                onClick: (stop) => {
                    // Open details drawer
                    window.App.openStopDetailsDrawer(stop.counter);
                }
            });

            // Update stats layout
            const kpis = balanceData.kpis;
            document.getElementById('dash-kpi-peak-hh').innerHTML = `<strong>${Math.round(kpis.max_hh)} HH</strong> (Parada ${kpis.busy_stop || '-'})`;
            document.getElementById('dash-kpi-peak-hc').innerText = `${kpis.max_headcount} pessoas`;
            document.getElementById('dash-kpi-orders-count').innerText = `${kpis.max_orders} ordens (pico)`;

            // 2. Compute Work center HH sums
            const wcTotals = {};
            let grandTotalHH = 0;
            
            balanceData.stops.forEach(s => {
                const grouped = s.grouped_hh || {};
                Object.keys(grouped).forEach(wc => {
                    const val = parseFloat(grouped[wc]) || 0;
                    wcTotals[wc] = (wcTotals[wc] || 0) + val;
                    grandTotalHH += val;
                });
            });

            // Render CT bars
            const distContainer = document.getElementById('dash-workcenter-distribution');
            distContainer.innerHTML = '<h4>Carga por Centro de Trabalho</h4>';
            
            const sortedWcs = Object.keys(wcTotals).sort((a,b) => wcTotals[b] - wcTotals[a]);
            
            if (sortedWcs.length === 0) {
                distContainer.innerHTML += `<p class="subtitle" style="padding:10px 0;">Sem dados de centros.</p>`;
                return;
            }

            sortedWcs.slice(0, 5).forEach(wc => {
                const total = wcTotals[wc];
                const pct = grandTotalHH > 0 ? (total / grandTotalHH) * 100 : 0;
                
                const wcItem = document.createElement('div');
                wcItem.className = 'stats-list-item';
                wcItem.innerHTML = `
                    <div class="stats-list-header">
                        <span>${wc}</span>
                        <strong>${Math.round(total)} HH (${Math.round(pct)}%)</strong>
                    </div>
                    <div class="stats-list-bar-bg">
                        <div class="stats-list-bar-fill" style="width: ${pct}%;"></div>
                    </div>
                `;
                distContainer.appendChild(wcItem);
            });
        } catch (err) {
            console.error("Erro ao carregar gráficos no dashboard:", err);
        }
    },

    goToPlansFiltered(filterKey) {
        // Clear all filters, apply this one, and redirect
        window.App.plansFilterPreset = filterKey;
        window.location.hash = '#plans';
    },

    goToItemsFiltered(filterKey) {
        // Clear all filters, apply this one, and redirect
        window.App.itemsFilterPreset = filterKey;
        window.location.hash = '#items';
    }
};

window.Dashboard = Dashboard;
