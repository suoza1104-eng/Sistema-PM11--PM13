/**
 * Custom visual components (SVG Charts, Heatmap, Toasts, Loader)
 */

// Colors for stacked groupings (Centro de trabalho, GPM, Prioridade, etc.)
const PALETTE = [
    '#84BD00', // Primary Green
    '#3182CE', // Blue
    '#DD6B20', // Orange
    '#805AD5', // Purple
    '#E53E3E', // Red
    '#319795', // Teal
    '#D69E2E', // Yellow
    '#4A5568', // Slate Gray
    '#1A2312', // Dark Green
    '#D53F8C', // Pink
    '#2B6CB0', // Dark Blue
    '#9C4221'  // Dark Orange
];

const UI = {
    escapeHTML(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    },
    esc(str) {
        return this.escapeHTML(str);
    },

    // 1. Toast Notifications
    showToast(message, type = 'success', duration = 4000) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        let iconSvg = '';
        if (type === 'success') {
            iconSvg = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>`;
        } else if (type === 'error') {
            iconSvg = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>`;
        } else {
            iconSvg = `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>`;
        }

        toast.innerHTML = `${iconSvg} <span>${message}</span>`;
        container.appendChild(toast);

        // Auto-remove after duration — use a simple opacity fade then remove
        setTimeout(() => {
            toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(60px)';
            setTimeout(() => toast.remove(), 320);
        }, duration);
    },

    // 2. Loading Overlay
    showLoader(text = 'Carregando dados...') {
        const loader = document.getElementById('loading-overlay');
        const loaderText = document.getElementById('loading-text');
        if (loader && loaderText) {
            loaderText.innerText = text;
            loader.classList.remove('hidden');
        }
    },

    hideLoader() {
        const loader = document.getElementById('loading-overlay');
        if (loader) {
            loader.classList.add('hidden');
        }
    },

    // 3. SVG Bar Chart Engine (renders stacked/simple workload bar charts)
    renderBarChart(containerId, stopsData, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        container.innerHTML = ''; // Clear previous

        const valueKey = options.valueKey || 'total_hh'; // total_hh, headcount_needed, total_orders
        const labelText = options.labelText || 'Carga (HH)';
        const onClick = options.onClick || null;
        // SVG IDs are global across hidden SPA sections. Give each chart its
        // own paint servers so navigation cannot resolve a fill in another SVG.
        const patternSuffix = `-${String(containerId).replace(/[^a-zA-Z0-9_-]/g, '-')}`;

        if (!stopsData || stopsData.length === 0) {
            container.innerHTML = `<div class="empty-state">Nenhum dado disponível para renderizar o gráfico.</div>`;
            return;
        }

        // SVG Dimensions
        const isBalanceChart = containerId === 'balance-main-chart-wrapper';
        const leftCol = isBalanceChart ? document.querySelector('.balance-left-col') : null;
        const usableWidth = (leftCol && leftCol.clientWidth > 0) ? (leftCol.clientWidth - 48) : container.clientWidth;
        const baseWidth = Math.max(300, usableWidth || 600);
        const height = container.clientHeight || 300;
        const defaultLeftMargin = isBalanceChart ? 140 : 45;
        const margins = options.margins || { top: 25, right: 15, bottom: 45, left: defaultLeftMargin };
        
        // For 18 stops or fewer, scale bars dynamically to fit 100% of baseWidth without overflow or clipping
        let width = baseWidth;
        if (stopsData.length > 18) {
            const minWidthPerBar = 25;
            const calculatedWidth = margins.left + margins.right + (stopsData.length * minWidthPerBar);
            width = Math.max(baseWidth, calculatedWidth);
        }

        container.style.overflowX = width > baseWidth ? 'auto' : 'hidden';
        
        const chartWidth = width - margins.left - margins.right;
        const chartHeight = height - margins.top - margins.bottom;

        // Determine Max Value for Scaling
        let maxVal = 0;
        stopsData.forEach(s => {
            const val = parseFloat(s[valueKey]) || 0;
            if (val > maxVal) maxVal = val;
        });
        
        // Pad max val slightly
        maxVal = maxVal > 0 ? maxVal * 1.15 : 10;
        if (valueKey === 'headcount_needed' || valueKey === 'total_orders') {
            maxVal = Math.ceil(maxVal);
        }

        // Color mapping for groups
        const uniqueGroups = new Set();
        stopsData.forEach(s => {
            const groupData = (valueKey === 'total_hh' ? s.grouped_hh : s.grouped_headcount) || {};
            Object.keys(groupData).forEach(g => uniqueGroups.add(g));
        });
        const SPECIALTY_COLORS = {
            'Mecânica': '#2563EB',
            'Mecanica': '#2563EB',
            'Elétrica': '#EAB308',
            'Eletrica': '#EAB308',
            'Solda': '#DC2626',
            'Soldador': '#DC2626'
        };
        const groupsList = Array.from(uniqueGroups).sort();
        const groupColors = {};
        groupsList.forEach((g, idx) => {
            groupColors[g] = SPECIALTY_COLORS[g] || PALETTE[idx % PALETTE.length];
        });

        // Start SVG Building
        let svg = `<svg width="${width}px" height="100%" viewBox="0 0 ${width} ${height}" style="display: block; overflow: visible;">
            <defs>
                <pattern id="overflow-ele${patternSuffix}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#EAB308"/><line x1="0" y1="0" x2="0" y2="10" stroke="#FFFFFF" stroke-width="3.5"/></pattern>
                <pattern id="overflow-mec${patternSuffix}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#2563EB"/><line x1="0" y1="0" x2="0" y2="10" stroke="#FFFFFF" stroke-width="3.5"/></pattern>
                <pattern id="overflow-sol${patternSuffix}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#DC2626"/><line x1="0" y1="0" x2="0" y2="10" stroke="#FFFFFF" stroke-width="3.5"/></pattern>
                <pattern id="overflow-generic${patternSuffix}" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#EF4444"/><line x1="0" y1="0" x2="0" y2="10" stroke="#FFFFFF" stroke-width="3.5"/></pattern>
            </defs>`;

        // 1. Grid Y-Lines & Y-Axis Labels
        const yLinesCount = 5;
        for (let i = 0; i <= yLinesCount; i++) {
            const val = (maxVal / yLinesCount) * i;
            const y = margins.top + chartHeight - (chartHeight / yLinesCount) * i;
            
            // Grid line
            svg += `<line x1="${margins.left}" y1="${y}" x2="${width - margins.right}" y2="${y}" stroke="#E2E8F0" stroke-width="1" stroke-dasharray="2 2" />`;
            // Label
            const formattedVal = valueKey === 'total_hh' ? val.toFixed(1).replace('.', ',') : Math.round(val);
            svg += `<text x="${margins.left - 10}" y="${y + 4}" font-family="var(--font-sans)" font-size="10px" font-weight="500" fill="var(--text-muted)" text-anchor="end">${formattedVal}</text>`;
        }

        // Y-Axis title
        svg += `<text x="${margins.left - 10}" y="${margins.top - 10}" font-family="var(--font-sans)" font-size="9px" font-weight="700" fill="var(--text-muted)" text-anchor="end">${labelText.toUpperCase()}</text>`;

        // 2. Render Bars and overlays
        const barCount = stopsData.length;
        const totalBarWidthSpace = chartWidth / barCount;
        const barWidth = totalBarWidthSpace * 0.65; // 65% width, 35% gap
        const barGap = totalBarWidthSpace * 0.35;

        // Draw Column highlights first (so they render behind everything else)
        stopsData.forEach((stop, idx) => {
            const highlightX = margins.left + idx * totalBarWidthSpace;
            svg += `<rect class="chart-col-highlight" id="col-highlight-${stop.counter}" x="${highlightX + 2}" y="${margins.top}" width="${totalBarWidthSpace - 4}" height="${chartHeight + 25}" fill="rgba(132, 189, 0, 0.05)" style="pointer-events: none; opacity: 0; transition: opacity 0.15s ease; rx: 4px;" />`;
        });

        // Draw actual bars
        stopsData.forEach((stop, idx) => {
            const x = margins.left + idx * totalBarWidthSpace + barGap / 2;
            const stopVal = parseFloat(stop[valueKey]) || 0;
            
            // X-Axis Labels
            const labelX = x + barWidth / 2;
            const labelY = margins.top + chartHeight + 15;
            
            // Show Stop Counter underneath
            svg += `<text x="${labelX}" y="${labelY}" font-family="var(--font-sans)" font-size="11px" font-weight="600" fill="var(--text-color)" text-anchor="middle">P${stop.stop_num}</text>`;
            svg += `<text x="${labelX}" y="${labelY + 12}" font-family="var(--font-sans)" font-size="9px" font-weight="500" fill="var(--text-muted)" text-anchor="middle">(${stop.counter})</text>`;

            if (stopVal === 0) {
                // Render empty tick dot
                svg += `<circle cx="${labelX}" cy="${margins.top + chartHeight}" r="3" fill="#CBD5E0" />`;
            } else {
                // Draw Bar (Check if stacked group is enabled)
                const hasGrouping = options.groupBy && options.groupBy !== 'none';
                const capacities = options.capacities || {};
                
                // Check if stop exceeds any capacity
                let isExceeded = false;
                const targetMeta = options.targetMeta ? parseFloat(options.targetMeta) : null;
                if (targetMeta && stopVal > targetMeta) isExceeded = true;
                if (capacities.mec !== null && (stop.mec_headcount_needed || 0) > capacities.mec) isExceeded = true;
                if (capacities.ele !== null && (stop.ele_headcount_needed || 0) > capacities.ele) isExceeded = true;
                if (capacities.sol !== null && (stop.sol_headcount_needed || 0) > capacities.sol) isExceeded = true;
                if (capacities.total !== null && (stop.headcount_needed || 0) > capacities.total) isExceeded = true;

                const strokeAttr = isExceeded ? 'stroke="#B91C1C" stroke-width="2.5"' : '';
                const barFill = isExceeded ? `url(#overflow-generic${patternSuffix})` : 'var(--primary-color)';

                if (hasGrouping && (valueKey === 'total_hh' || valueKey === 'headcount_needed')) {
                    // Stacked rendering (for HH or headcount)
                    let currentYOffset = 0;
                    const groups = (valueKey === 'total_hh' ? stop.grouped_hh : stop.grouped_headcount) || {};
                    
                    Object.keys(groups).forEach(g => {
                        const gVal = parseFloat(groups[g]) || 0;
                        if (gVal === 0) return;
                        
                        const gHeight = (gVal / maxVal) * chartHeight;
                        const barY = margins.top + chartHeight - currentYOffset - gHeight;
                        const color = groupColors[g] || 'var(--primary-color)';

                        // Check trade-specific capacity
                        let segExceeded = false;
                        if ((g === 'Mecânica' || g === 'Mecanica') && capacities.mec !== null && (stop.mec_headcount_needed || 0) > capacities.mec) segExceeded = true;
                        if ((g === 'Elétrica' || g === 'Eletrica') && capacities.ele !== null && (stop.ele_headcount_needed || 0) > capacities.ele) segExceeded = true;
                        if ((g === 'Solda' || g === 'Soldador') && capacities.sol !== null && (stop.sol_headcount_needed || 0) > capacities.sol) segExceeded = true;

                        let patternId = 'overflow-generic';
                        if (g === 'Mecânica' || g === 'Mecanica') patternId = 'overflow-mec';
                        else if (g === 'Elétrica' || g === 'Eletrica') patternId = 'overflow-ele';
                        else if (g === 'Solda' || g === 'Soldador') patternId = 'overflow-sol';

                        const segStroke = segExceeded ? 'stroke="#B91C1C" stroke-width="2.5"' : '';
                        const segmentFill = segExceeded ? `url(#${patternId}${patternSuffix})` : color;
                        
                        svg += `<rect class="chart-bar${segExceeded ? ' chart-bar-overflow' : ''}" x="${x}" y="${barY}" width="${barWidth}" height="${gHeight}" fill="${segmentFill}" ${segStroke} rx="2" 
                                    data-stop='${JSON.stringify(stop)}' 
                                    data-group="${g}" 
                                    data-val="${gVal}" 
                                    data-exceeded="${segExceeded ? '1' : '0'}"
                                    data-type="stacked" />`;
                        
                        // Data Label inside segment (rotulo de dados por cor/classe)
                        if (gHeight >= 13) {
                            let segLabel = '';
                            if (valueKey === 'total_hh') {
                                segLabel = gVal.toFixed(1).replace('.', ',');
                            } else if (valueKey === 'headcount_needed') {
                                segLabel = Math.round(gVal).toString();
                            } else {
                                segLabel = gVal.toString();
                            }
                            const fontSize = barWidth < 28 ? '8.5px' : '10px';
                            svg += `<text x="${x + barWidth / 2}" y="${barY + gHeight / 2 + 3.5}" font-family="var(--font-sans)" font-size="${fontSize}" font-weight="700" fill="#FFFFFF" text-anchor="middle" style="pointer-events: none; text-shadow: 0 1px 3px rgba(0,0,0,0.85);">${segLabel}</text>`;
                        }

                        currentYOffset += gHeight;
                    });
                } else {
                    // Simple Single Bar
                    const barHeight = (stopVal / maxVal) * chartHeight;
                    const barY = margins.top + chartHeight - barHeight;
                    
                    svg += `<rect class="chart-bar${isExceeded ? ' chart-bar-overflow' : ''}" x="${x}" y="${barY}" width="${barWidth}" height="${barHeight}" fill="${barFill}" ${strokeAttr} rx="3" 
                                data-stop='${JSON.stringify(stop)}' 
                                data-val="${stopVal}" 
                                data-exceeded="${isExceeded ? '1' : '0'}"
                                data-type="simple" />`;
                }

                // Data Label on top of bar column
                const totalBarHeight = (stopVal / maxVal) * chartHeight;
                const barTopY = margins.top + chartHeight - totalBarHeight;
                let formattedLabel = '';
                if (valueKey === 'total_hh') {
                    formattedLabel = stopVal.toFixed(1).replace('.', ',');
                } else {
                    formattedLabel = Math.round(stopVal).toString();
                }
                const labelTopY = Math.max(margins.top + 10, barTopY - 6);
                const labelColor = isExceeded ? '#DC2626' : 'var(--text-color)';
                const labelPrefix = isExceeded ? '⚠️ ' : '';
                svg += `<text x="${labelX}" y="${labelTopY}" font-family="var(--font-sans)" font-size="11px" font-weight="700" fill="${labelColor}" text-anchor="middle">${labelPrefix}${formattedLabel}</text>`;
            }

            // Draw interaction overlay on top of everything in the column
            const overlayX = margins.left + idx * totalBarWidthSpace;
            svg += `<rect class="chart-col-interaction-overlay" x="${overlayX}" y="${margins.top - 10}" width="${totalBarWidthSpace}" height="${chartHeight + 45}" fill="transparent" style="cursor: pointer;" 
                        data-stop='${JSON.stringify(stop)}' />`;
        });

        // 3. Render Target Meta Line if specified
        if (options.targetMeta && parseFloat(options.targetMeta) > 0) {
            const metaVal = parseFloat(options.targetMeta);
            if (maxVal > 0) {
                const metaY = margins.top + chartHeight - Math.min((metaVal / maxVal) * chartHeight, chartHeight);
                const tagText = options.targetMetaLabel || `META: ${metaVal}`;
                const textWidth = Math.max(110, tagText.length * 6.5 + 16);
                const rectX = margins.left + chartWidth - textWidth;

                svg += `<g class="chart-meta-line" style="pointer-events: none;">`;
                svg += `<line x1="${margins.left}" y1="${metaY}" x2="${margins.left + chartWidth}" y2="${metaY}" stroke="#C83A3A" stroke-width="2" stroke-dasharray="6,4" />`;
                svg += `<rect x="${rectX}" y="${metaY - 18}" width="${textWidth}" height="18" fill="#C83A3A" rx="4" />`;
                svg += `<text x="${rectX + textWidth / 2}" y="${metaY - 5}" font-family="var(--font-sans)" font-size="10px" font-weight="700" fill="#FFFFFF" text-anchor="middle">${tagText}</text>`;
                svg += `</g>`;
            }
        }

        // 4. Render Legend (only if grouped)
        if (options.groupBy && options.groupBy !== 'none' && (valueKey === 'total_hh' || valueKey === 'headcount_needed')) {
            let legendSvg = `<g transform="translate(${margins.left}, ${margins.top - 20})">`;
            let xOffset = 0;
            groupsList.forEach(g => {
                const color = groupColors[g];
                legendSvg += `<rect x="${xOffset}" y="0" width="10" height="10" fill="${color}" rx="2" />`;
                legendSvg += `<text x="${xOffset + 14}" y="9" font-family="var(--font-sans)" font-size="10px" font-weight="500" fill="var(--text-muted)">${g}</text>`;
                xOffset += g.length * 6.5 + 30; // offset spacing
            });
            if (options.capacities?.hasAny) {
                legendSvg += `<rect x="${xOffset}" y="-1" width="14" height="12" fill="url(#overflow-generic${patternSuffix})" stroke="#B91C1C" stroke-width="2" rx="2" />`;
                legendSvg += `<text x="${xOffset + 19}" y="9" font-family="var(--font-sans)" font-size="10px" font-weight="700" fill="#B91C1C">Efetivo estourado</text>`;
            }
            legendSvg += `</g>`;
            svg += legendSvg;
        }

        svg += `</svg>`;
        container.innerHTML = svg;

        // 5. Attach Events (Tooltip, Clicks, and Drag-and-Drop)
        const bars = container.querySelectorAll('.chart-bar');
        const overlays = container.querySelectorAll('.chart-col-interaction-overlay');
        
        // Custom Tooltip element inside body if not exists
        let tooltip = document.getElementById('chart-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'chart-tooltip';
            tooltip.style.position = 'absolute';
            tooltip.style.backgroundColor = '#2D3748';
            tooltip.style.color = '#FFFFFF';
            tooltip.style.padding = '8px 12px';
            tooltip.style.borderRadius = 'var(--radius-sm)';
            tooltip.style.fontSize = '11px';
            tooltip.style.pointerEvents = 'none';
            tooltip.style.display = 'none';
            tooltip.style.zIndex = '500';
            tooltip.style.boxShadow = 'var(--shadow-lg)';
            document.body.appendChild(tooltip);
        }

        // Bar hover tooltips
        bars.forEach(bar => {
            bar.addEventListener('mouseover', (e) => {
                const stop = JSON.parse(bar.getAttribute('data-stop'));
                const val = parseFloat(bar.getAttribute('data-val'));
                const isStacked = bar.getAttribute('data-type') === 'stacked';
                const group = bar.getAttribute('data-group');
                const isOverflow = bar.getAttribute('data-exceeded') === '1';
                
                let unitText = 'HH';
                if (valueKey === 'headcount_needed') unitText = 'pessoas';
                if (valueKey === 'total_orders') unitText = 'ordens';
                
                let valFormatted = valueKey === 'total_hh' ? val.toFixed(1).replace('.', ',') : val;
                
                let tooltipContent = `
                    <strong>Parada ${stop.stop_num} (Contador ${stop.counter})</strong><br>
                `;
                
                if (isStacked) {
                    const totalVal = valueKey === 'total_hh' ? stop.total_hh : stop.headcount_needed;
                    const totalFormatted = valueKey === 'total_hh' ? totalVal.toFixed(1).replace('.', ',') : totalVal;
                    const valFormattedStr = valueKey === 'total_hh' ? val.toFixed(1).replace('.', ',') : val;
                    tooltipContent += `
                        Agrupamento: ${group}<br>
                        Quantidade: <strong>${valFormattedStr} ${unitText}</strong><br>
                        Total da Parada: <strong>${totalFormatted} ${unitText}</strong>
                    `;
                } else {
                    tooltipContent += `Carga: <strong>${valFormatted} ${unitText}</strong>`;
                }
                if (isOverflow) tooltipContent += `<br><strong style="color:#FCA5A5;">⚠ Efetivo estourado</strong>`;
                
                tooltip.innerHTML = tooltipContent;
                tooltip.style.display = 'block';
            });

            bar.addEventListener('mousemove', (e) => {
                tooltip.style.left = (e.pageX + 15) + 'px';
                tooltip.style.top = (e.pageY - 15) + 'px';
            });

            bar.addEventListener('mouseout', () => {
                tooltip.style.display = 'none';
            });
        });

        // Overlay interaction events (Clicks & Drag-and-Drop)
        overlays.forEach(overlay => {
            const stopData = JSON.parse(overlay.getAttribute('data-stop'));
            const highlightRect = container.querySelector(`#col-highlight-${stopData.counter}`);

            // Clicks
            if (onClick) {
                overlay.addEventListener('click', () => {
                    tooltip.style.display = 'none';
                    onClick(stopData);
                });
            }

            // Hover columns
            overlay.addEventListener('mouseenter', () => {
                if (highlightRect) highlightRect.style.opacity = '1';
            });
            overlay.addEventListener('mouseleave', () => {
                if (highlightRect) highlightRect.style.opacity = '0';
            });

            // Drag and Drop
            overlay.addEventListener('dragenter', (e) => {
                e.preventDefault();
            });

            overlay.addEventListener('dragover', (e) => {
                e.preventDefault();
                if (highlightRect) {
                    highlightRect.style.fill = 'rgba(132, 189, 0, 0.15)'; // light green
                    highlightRect.style.opacity = '1';
                }
            });

            overlay.addEventListener('dragleave', () => {
                if (highlightRect) {
                    highlightRect.style.fill = 'rgba(132, 189, 0, 0.05)';
                    highlightRect.style.opacity = '0';
                }
            });

            overlay.addEventListener('drop', (e) => {
                e.preventDefault();
                if (highlightRect) {
                    highlightRect.style.fill = 'rgba(132, 189, 0, 0.05)';
                    highlightRect.style.opacity = '0';
                }

                try {
                    let dragData = window.pendingDraggedItem;
                    try {
                        const rawText = e.dataTransfer.getData('text/plain');
                        if (rawText) {
                            const parsed = JSON.parse(rawText);
                            if (parsed && parsed.itemId) dragData = parsed;
                        }
                    } catch (parseErr) {}

                    API.log("drop event triggered on stop counter " + stopData.counter + ". dragData=" + JSON.stringify(dragData), "components.js");

                    if (dragData && dragData.itemId) {
                        if (window.Balance && typeof window.Balance.handleItemDrop === 'function') {
                            window.Balance.handleItemDrop(dragData.itemId, dragData.planId, dragData.planCode, stopData.stop_num, stopData.counter);
                        } else {
                            API.log("ERROR: window.Balance.handleItemDrop function is not available!", "components.js");
                        }
                    } else {
                        API.log("WARNING: drop triggered but no valid dragData/itemId found!", "components.js");
                    }
                } catch (err) {
                    API.log("ERROR in drop listener: " + err.message, "components.js");
                } finally {
                    window.pendingDraggedItem = null;
                }
            });
        });
    },

    // 4. Heatmap Matrix rendering
    renderHeatmap(containerId, balanceData, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = '';
        const valueKey = options.valueKey || 'hh'; // hh, orders, headcount
        const rowGrouping = options.rowGrouping || 'work_center';
        
        const stops = balanceData.stops;
        if (!stops || stops.length === 0) {
            container.innerHTML = `<div class="empty-state">Sem dados de paradas para projetar o mapa de calor.</div>`;
            return;
        }

        // Gather all unique rows (CTs, GPMs or Plans)
        const rowKeys = new Set();
        stops.forEach(s => {
            const grouped = s.grouped_hh || {};
            Object.keys(grouped).forEach(k => rowKeys.add(k));
        });
        
        const rowsList = Array.from(rowKeys).sort();
        if (rowsList.length === 0) {
            container.innerHTML = `<div class="empty-state">Nenhum agrupamento encontrado para plotar o mapa de calor.</div>`;
            return;
        }

        // Determine widths and alignment styling
        let tableStyle = '';
        let firstColStyle = '';
        let colStyle = '';
        let lastColStyle = '';
        let hasRightMargin = false;

        if (options.alignWithChart) {
            // Align columns with the SVG bar chart
            const leftCol = document.querySelector('.balance-left-col');
            const usableWidth = leftCol ? (leftCol.clientWidth - 48) : container.clientWidth;
            const baseWidth = Math.max(300, usableWidth || 700);
            const margins = { top: 25, right: 15, bottom: 45, left: 140 };
            let width = baseWidth;
            if (stops.length > 18) {
                const minWidthPerBar = 25;
                const calculatedWidth = margins.left + margins.right + (stops.length * minWidthPerBar);
                width = Math.max(baseWidth, calculatedWidth);
            }
            const chartWidth = width - margins.left - margins.right;
            const totalBarWidthSpace = chartWidth / stops.length;

            tableStyle = `style="width: ${width}px; table-layout: fixed;"`;
            firstColStyle = `style="width: ${margins.left}px; min-width: ${margins.left}px; max-width: ${margins.left}px; padding: 8px 8px; font-weight: 700; text-align: left; white-space: nowrap; overflow: visible;"`;
            colStyle = `style="width: ${totalBarWidthSpace}px; min-width: ${totalBarWidthSpace}px; max-width: ${totalBarWidthSpace}px; text-align: center;"`;
            lastColStyle = `style="width: ${margins.right}px; min-width: ${margins.right}px; padding: 0; border: none; background: transparent;"`;
            hasRightMargin = true;
        }

        // Build Heatmap table structure
        let table = `<table class="heatmap-table" ${tableStyle}>`;
        const capacities = options.capacities || {};
        const legacyProdHours = Number(balanceData.productive_hours) || 9.1;
        const hoursMap = balanceData.capacity_hours_per_person;
        const ambiguousMap = balanceData.capacity_hours_ambiguous || {};
        const hasCapacityContext = hoursMap && typeof hoursMap === 'object';

        const getTradeCapacityHH = (trade) => {
            const people = capacities[trade];
            if (people === null || people === undefined || people <= 0) return null;

            if (!hasCapacityContext) return people * legacyProdHours;

            const hours = Number(hoursMap[trade]);
            if (ambiguousMap[trade] || !Number.isFinite(hours) || hours <= 0) return null;
            return people * hours;
        };

        const getTotalCapacityHH = () => {
            let total = 0;
            let hasConfigured = false;
            for (const trade of ['ele', 'mec', 'sol']) {
                const people = capacities[trade];
                if (people === null || people === undefined || people <= 0) continue;
                hasConfigured = true;
                const tradeHH = getTradeCapacityHH(trade);
                if (tradeHH === null) return null;
                total += tradeHH;
            }
            return hasConfigured ? total : null;
        };
        
        // Header (Stops)
        table += `<thead><tr><th ${firstColStyle}>${options.rowHeader || 'Especialidades'}</th>`;
        stops.forEach(s => {
            table += `<th ${colStyle}>P${s.stop_num}<br><span style="font-size:9px; font-weight:500; color:var(--text-muted)">(${s.counter})</span></th>`;
        });
        if (hasRightMargin) {
            table += `<th ${lastColStyle}></th>`;
        }
        table += `</tr></thead><tbody>`;

        if (rowGrouping === 'specialty') {
            // Explicit structured 4-row layout: Total, ELE, MEC, SOL
            const specialtyRows = [
                { key: 'total', label: (valueKey === 'headcount' ? '📊 Efetivo Total' : (valueKey === 'orders' ? '📊 Ordens Total' : '📊 HH Total')), css: 'heatmap-row-total', capKey: 'total' },
                { key: 'ele', label: '⚡ Elétrica (ELE)', css: 'heatmap-row-ele', capKey: 'ele' },
                { key: 'mec', label: '🔧 Mecânica (MEC)', css: 'heatmap-row-mec', capKey: 'mec' },
                { key: 'sol', label: '🔥 Solda (SOL)', css: 'heatmap-row-sol', capKey: 'sol' }
            ];

            specialtyRows.forEach(row => {
                const cellHeaderStyle = options.alignWithChart ? firstColStyle : 'style="font-weight: 700;"';
                table += `<tr class="${row.css}"><td ${cellHeaderStyle} title="${row.label}">${row.label}</td>`;

                stops.forEach(s => {
                    let val = 0;
                    if (row.key === 'total') {
                        if (valueKey === 'hh') val = parseFloat(s.total_hh) || 0;
                        else if (valueKey === 'headcount') val = parseInt(s.headcount_needed) || 0;
                        else val = parseInt(s.total_orders) || 0;
                    } else if (row.key === 'ele') {
                        if (valueKey === 'hh') val = parseFloat(s.ele_hh) || 0;
                        else if (valueKey === 'headcount') val = parseInt(s.ele_headcount_needed) || 0;
                        else val = parseInt(s.grouped_orders?.['Elétrica']) || 0;
                    } else if (row.key === 'sol') {
                        if (valueKey === 'hh') val = parseFloat(s.sol_hh) || 0;
                        else if (valueKey === 'headcount') val = parseInt(s.sol_headcount_needed) || 0;
                        else val = parseInt(s.grouped_orders?.['Solda']) || 0;
                    } else if (row.key === 'mec') {
                        if (valueKey === 'hh') val = parseFloat(s.mec_hh) || 0;
                        else if (valueKey === 'headcount') val = parseInt(s.mec_headcount_needed) || 0;
                        else val = parseInt(s.grouped_orders?.['Mecânica']) || 0;
                    }

                    // Check capacity limit. For HH, each discipline uses the
                    // project-level productive hours per person.
                    let isExceeded = false;
                    const capLimit = capacities[row.capKey];
                    let capHH = null;
                    if (valueKey === 'headcount') {
                        if (capLimit !== null && capLimit !== undefined && capLimit > 0 && val > capLimit) {
                            isExceeded = true;
                        }
                    } else if (valueKey === 'hh') {
                        capHH = row.key === 'total' ? getTotalCapacityHH() : getTradeCapacityHH(row.key);
                        if (capHH !== null && val > capHH) isExceeded = true;
                    }

                    let intensityClass = 'heat-empty';
                    if (isExceeded) {
                        intensityClass = 'heat-exceeded';
                    } else if (val > 0) {
                        if (valueKey === 'hh') {
                            if (val <= 10) intensityClass = 'heat-low';
                            else if (val <= 40) intensityClass = 'heat-medium';
                            else if (val <= 80) intensityClass = 'heat-high';
                            else intensityClass = 'heat-critical';
                        } else {
                            if (val <= 1) intensityClass = 'heat-low';
                            else if (val <= 3) intensityClass = 'heat-medium';
                            else if (val <= 6) intensityClass = 'heat-high';
                            else intensityClass = 'heat-critical';
                        }
                    }

                    const displayedVal = val === 0 ? '-' : (valueKey === 'hh' ? val.toFixed(1).replace('.', ',') : val);
                    const cellExtraStyle = options.alignWithChart ? colStyle : '';
                    let capInfo = '';
                    if (valueKey === 'hh' && capHH !== null) {
                        capInfo = ` (Limite: ${capHH.toFixed(1).replace('.', ',')} HH)`;
                    } else if (valueKey === 'headcount' && capLimit) {
                        capInfo = ` (Limite: ${capLimit} pess.)`;
                    }

                    table += `<td class="heatmap-cell ${intensityClass}" ${cellExtraStyle} title="${row.label} na Parada ${s.stop_num}: ${displayedVal} ${valueKey.toUpperCase()}${capInfo}">${displayedVal}</td>`;
                });

                if (hasRightMargin) {
                    table += `<td ${lastColStyle}></td>`;
                }
                table += `</tr>`;
            });
        } else {
            // Body rows for dynamic groupings
            rowsList.forEach(rowKey => {
                if (options.alignWithChart) {
                    table += `<tr><td ${firstColStyle} title="${rowKey}">${rowKey}</td>`;
                } else {
                    table += `<tr><td style="font-weight: 600;">${rowKey}</td>`;
                }
                
                stops.forEach(s => {
                    let val = 0;
                    if (valueKey === 'hh') {
                        val = parseFloat(s.grouped_hh[rowKey]) || 0;
                    } else if (valueKey === 'orders') {
                        val = parseInt(s.grouped_orders[rowKey]) || 0;
                    } else if (valueKey === 'headcount') {
                        val = parseInt(s.grouped_headcount[rowKey]) || 0;
                    }

                    let intensityClass = 'heat-empty';
                    if (val > 0) {
                        if (valueKey === 'hh') {
                            if (val <= 10) intensityClass = 'heat-low';
                            else if (val <= 50) intensityClass = 'heat-medium';
                            else if (val <= 150) intensityClass = 'heat-high';
                            else intensityClass = 'heat-critical';
                        } else {
                            if (val <= 2) intensityClass = 'heat-low';
                            else if (val <= 5) intensityClass = 'heat-medium';
                            else if (val <= 10) intensityClass = 'heat-high';
                            else intensityClass = 'heat-critical';
                        }
                    }

                    const displayedVal = val === 0 ? '-' : (valueKey === 'hh' ? val.toFixed(1).replace('.', ',') : val);
                    
                    if (options.alignWithChart) {
                        table += `<td class="heatmap-cell ${intensityClass}" ${colStyle} title="${rowKey} na Parada ${s.stop_num}: ${displayedVal} ${valueKey.toUpperCase()}">${displayedVal}</td>`;
                    } else {
                        table += `<td class="heatmap-cell ${intensityClass}" title="${rowKey} na Parada ${s.stop_num}: ${displayedVal} ${valueKey.toUpperCase()}">${displayedVal}</td>`;
                    }
                });
                if (hasRightMargin) {
                    table += `<td ${lastColStyle}></td>`;
                }
                table += `</tr>`;
            });
        }

        table += `</tbody></table>`;
        container.innerHTML = table;
    }
};

/**
 * Google Sheets / Excel style interactive column filtering component
 */
const ColumnFilter = {
    activeFilters: {}, // tableId -> { colKey: Set of allowed values }
    openPopover: null,
    _hasDocListener: false,

    normalizeSearchText(value) {
        return String(value ?? '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLocaleLowerCase('pt-BR')
            .trim();
    },

    getValuesContaining(values, filterText) {
        const normalizedFilter = this.normalizeSearchText(filterText);
        if (!normalizedFilter) return Array.from(values || []);
        return Array.from(values || []).filter(value =>
            this.normalizeSearchText(value).includes(normalizedFilter)
        );
    },

    resolveSelectedValues(candidateValues, currentSelected, filterText, selectionOverrides) {
        const hasSearch = Boolean(this.normalizeSearchText(filterText));
        return new Set(Array.from(candidateValues || []).filter(value => {
            if (!hasSearch) return currentSelected.has(value);
            return !selectionOverrides.has(value) || selectionOverrides.get(value);
        }));
    },

    init(tableId, getRowsDataFn, onFilterApplyFn, columnOptions = {}) {
        const table = document.getElementById(tableId);
        if (!table) return;

        if (!this.activeFilters[tableId]) {
            this.activeFilters[tableId] = {};
        }

        // Global click listener to close popover
        if (!this._hasDocListener) {
            document.addEventListener('click', (e) => {
                if (this.openPopover && !this.openPopover.contains(e.target) && !e.target.closest('.col-filter-btn')) {
                    this.closePopover();
                }
            });
            this._hasDocListener = true;
        }

        // Decorate table headers with filter buttons
        const ths = table.querySelectorAll('thead th');
        ths.forEach(th => {
            const col = th.getAttribute('data-col');
            if (!col) return; // Skip non-data columns (like checkbox or actions)

            let btn = th.querySelector('.col-filter-btn');
            if (!btn) {
                btn = document.createElement('button');
                btn.className = 'col-filter-btn';
                btn.type = 'button';
                btn.title = `Filtrar coluna ${th.innerText.replace(/[▼▲]/g, '').trim()}`;
                btn.setAttribute('data-col', col);
                btn.innerHTML = `<svg class="col-filter-icon" viewBox="0 0 24 24"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>`;
                th.appendChild(btn);
            }

            // Update active state visual
            if (this.hasActiveFilter(tableId, col)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }

            btn.onclick = (e) => {
                e.stopPropagation();
                this.toggleFilterPopover(tableId, col, th, getRowsDataFn, onFilterApplyFn, columnOptions);
            };
        });
    },

    hasActiveFilter(tableId, col) {
        return Boolean(
            this.activeFilters[tableId]
            && Object.prototype.hasOwnProperty.call(this.activeFilters[tableId], col)
        );
    },

    closePopover() {
        if (this.openPopover) {
            this.openPopover.remove();
            this.openPopover = null;
        }
    },

    toggleFilterPopover(tableId, col, thElement, getRowsDataFn, onFilterApplyFn, columnOptions = {}) {
        if (this.openPopover && this.openPopover._targetCol === col && this.openPopover._targetTable === tableId) {
            this.closePopover();
            return;
        }
        this.closePopover();

        const allRows = getRowsDataFn() || [];
        const optionConfig = columnOptions[col] || {};
        const colTitle = thElement.innerText.replace(/[▼▲]/g, '').trim();

        // Count unique values in current dataset
        const valCounts = new Map();
        const valMetadata = new Map();
        allRows.forEach(row => {
            let val = row[col];
            if (val === null || val === undefined || val === '') val = '(Vazio)';
            else val = String(val).trim();
            valCounts.set(val, (valCounts.get(val) || 0) + 1);
            if (!valMetadata.has(val) && typeof optionConfig.getOptionMeta === 'function') {
                valMetadata.set(val, optionConfig.getOptionMeta(row, val) || {});
            }
        });

        // Sorted unique values list
        const distinctValues = Array.from(valCounts.keys()).sort((a, b) => {
            if (a === '(Vazio)') return 1;
            if (b === '(Vazio)') return -1;
            const numA = parseFloat(a.replace(',', '.'));
            const numB = parseFloat(b.replace(',', '.'));
            if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
            return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
        });

        // Working set for checkboxes (cloned from active or all)
        const hasStoredFilter = Object.prototype.hasOwnProperty.call(this.activeFilters[tableId], col);
        const currentSelected = new Set(
            hasStoredFilter ? this.activeFilters[tableId][col] : distinctValues
        );
        // Search results start selected, even when a previous filter did not
        // contain them. Explicit checkbox changes override that default.
        const searchSelectionOverrides = new Map();

        // Build floating popover
        const popover = document.createElement('div');
        popover.className = 'col-filter-popover';
        if (optionConfig.popoverClass) popover.classList.add(optionConfig.popoverClass);
        popover._targetCol = col;
        popover._targetTable = tableId;

        popover.innerHTML = `
            <div class="col-filter-popover-header">
                <span class="col-filter-popover-title">Filtrar: ${colTitle}</span>
                <button type="button" class="btn-icon" style="width:20px;height:20px;font-size:11px;" id="col-filter-close-btn">✕</button>
            </div>
            <div class="col-filter-sort-actions">
                <button type="button" class="col-filter-sort-btn" id="col-sort-asc">
                    <span>▲</span> Classificar de A a Z / Menor para Maior
                </button>
                <button type="button" class="col-filter-sort-btn" id="col-sort-desc">
                    <span>▼</span> Classificar de Z a A / Maior para Menor
                </button>
            </div>
            <div class="col-filter-search-box">
                <input type="search" class="col-filter-search-input" id="col-filter-search" placeholder="${optionConfig.searchPlaceholder || 'Pesquisar nesta coluna...'}">
            </div>
            <div class="col-filter-selection-helpers">
                <button type="button" class="col-filter-link-btn" id="col-filter-select-all">Selecionar Todos</button>
                <button type="button" class="col-filter-link-btn" id="col-filter-clear-all">Limpar</button>
            </div>
            <div class="col-filter-checklist" id="col-filter-checklist">
            </div>
            <div class="col-filter-popover-footer">
                <button type="button" class="btn btn-outline btn-xs" id="col-filter-reset-btn">Limpar Filtro</button>
                <button type="button" class="btn btn-primary btn-xs" id="col-filter-apply-btn">OK</button>
            </div>
        `;

        document.body.appendChild(popover);
        this.openPopover = popover;

        // Position popover right under thElement
        const thRect = thElement.getBoundingClientRect();
        // The popover is position:fixed, so viewport coordinates from
        // getBoundingClientRect must not receive the page scroll offset.
        let top = thRect.bottom + 4;
        let left = thRect.left;

        const popoverWidth = Math.min(popover.getBoundingClientRect().width || 240, window.innerWidth - 20);
        if (left + popoverWidth > window.innerWidth - 10) {
            left = window.innerWidth - popoverWidth - 10;
        }
        if (left < 10) left = 10;

        const estimatedHeight = Math.min(popover.scrollHeight || 420, window.innerHeight - 20);
        if (top + estimatedHeight > window.innerHeight - 10) {
            top = Math.max(10, thRect.top - estimatedHeight - 4);
        }

        popover.style.top = `${top}px`;
        popover.style.left = `${left}px`;

        const checklistEl = popover.querySelector('#col-filter-checklist');
        const searchInput = popover.querySelector('#col-filter-search');

        const getVisibleValues = (filterText = '') => {
            const normalizedFilter = this.normalizeSearchText(filterText);
            if (!normalizedFilter) return distinctValues;
            return distinctValues.filter(value => {
                const meta = valMetadata.get(value) || {};
                const searchable = [value, meta.primary, meta.secondary, meta.badge, meta.searchText]
                    .filter(part => part !== null && part !== undefined)
                    .join(' ');
                return this.normalizeSearchText(searchable).includes(normalizedFilter);
            });
        };

        const renderChecklist = (filterText = '') => {
            checklistEl.innerHTML = '';
            const visibleValues = getVisibleValues(filterText);

            visibleValues.forEach(val => {
                const count = valCounts.get(val);
                const hasSearch = Boolean(this.normalizeSearchText(filterText));
                const isChecked = hasSearch
                    ? (searchSelectionOverrides.has(val) ? searchSelectionOverrides.get(val) : true)
                    : currentSelected.has(val);
                const itemDiv = document.createElement('label');
                itemDiv.className = 'col-filter-check-item';
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = isChecked;
                itemDiv.appendChild(checkbox);
                const meta = valMetadata.get(val);
                if (meta) {
                    itemDiv.classList.add('col-filter-check-item-rich');
                    const content = document.createElement('span');
                    content.className = 'col-filter-option-content';
                    const primary = document.createElement('strong');
                    primary.className = 'col-filter-option-primary';
                    primary.textContent = meta.primary || val;
                    content.appendChild(primary);
                    if (meta.secondary) {
                        const secondary = document.createElement('span');
                        secondary.className = 'col-filter-option-secondary';
                        secondary.textContent = meta.secondary;
                        secondary.title = meta.secondary;
                        content.appendChild(secondary);
                    }
                    itemDiv.appendChild(content);
                    if (meta.badge) {
                        const badge = document.createElement('span');
                        badge.className = 'col-filter-option-cycle';
                        badge.textContent = meta.badge;
                        badge.title = 'Ciclo do plano';
                        itemDiv.appendChild(badge);
                    }
                } else {
                    const valueText = document.createElement('span');
                    valueText.textContent = val;
                    itemDiv.appendChild(valueText);
                }
                const countBadge = document.createElement('span');
                countBadge.className = 'col-filter-count-badge';
                countBadge.textContent = count;
                countBadge.title = `${count} item(ns)`;
                itemDiv.appendChild(countBadge);
                checkbox.onchange = (e) => {
                    searchSelectionOverrides.set(val, e.target.checked);
                    if (e.target.checked) currentSelected.add(val);
                    else currentSelected.delete(val);
                };
                checklistEl.appendChild(itemDiv);
            });

            if (visibleValues.length === 0) {
                checklistEl.innerHTML = `<div style="font-size:11px;color:var(--text-muted);padding:8px 6px;">Nenhum valor correspondente.</div>`;
            }
        };

        renderChecklist();

        searchInput.oninput = () => renderChecklist(searchInput.value.trim());

        popover.querySelector('#col-filter-select-all').onclick = () => {
            getVisibleValues(searchInput.value.trim()).forEach(v => {
                searchSelectionOverrides.set(v, true);
                currentSelected.add(v);
            });
            renderChecklist(searchInput.value.trim());
        };

        popover.querySelector('#col-filter-clear-all').onclick = () => {
            getVisibleValues(searchInput.value.trim()).forEach(v => {
                searchSelectionOverrides.set(v, false);
                currentSelected.delete(v);
            });
            renderChecklist(searchInput.value.trim());
        };

        popover.querySelector('#col-sort-asc').onclick = () => {
            this.closePopover();
            onFilterApplyFn(col, 'ASC', this.activeFilters[tableId]);
        };

        popover.querySelector('#col-sort-desc').onclick = () => {
            this.closePopover();
            onFilterApplyFn(col, 'DESC', this.activeFilters[tableId]);
        };

        popover.querySelector('#col-filter-close-btn').onclick = () => this.closePopover();

        popover.querySelector('#col-filter-reset-btn').onclick = () => {
            delete this.activeFilters[tableId][col];
            this.closePopover();
            this.updateHeaderFilterBadges(tableId);
            onFilterApplyFn(null, null, this.activeFilters[tableId]);
        };

        const applyCurrentFilter = () => {
            const searchText = searchInput.value.trim();
            const candidateValues = searchText ? getVisibleValues(searchText) : distinctValues;
            const selectedValues = this.resolveSelectedValues(
                candidateValues, currentSelected, searchText, searchSelectionOverrides
            );

            // With a search term, OK applies only the matching, checked values.
            // Without a term, preserve the original Excel-style checklist behavior.
            if (!searchText && selectedValues.size === distinctValues.length) {
                delete this.activeFilters[tableId][col]; // All selected = clear filter
            } else {
                // An empty Set is intentional: a search with no matches must
                // produce an empty table instead of silently clearing a filter.
                this.activeFilters[tableId][col] = selectedValues;
            }
            this.closePopover();
            this.updateHeaderFilterBadges(tableId);
            onFilterApplyFn(col, null, this.activeFilters[tableId]);
        };

        popover.querySelector('#col-filter-apply-btn').onclick = applyCurrentFilter;
        searchInput.onkeydown = event => {
            if (event.key !== 'Enter') return;
            event.preventDefault();
            applyCurrentFilter();
        };
    },

    updateHeaderFilterBadges(tableId) {
        const table = document.getElementById(tableId);
        if (!table) return;
        const ths = table.querySelectorAll('thead th');
        ths.forEach(th => {
            const col = th.getAttribute('data-col');
            const btn = th.querySelector('.col-filter-btn');
            if (btn && col) {
                if (this.hasActiveFilter(tableId, col)) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            }
        });
    },

    applyFiltersToDataset(tableId, dataset) {
        const filters = this.activeFilters[tableId];
        if (!filters || Object.keys(filters).length === 0) return dataset;

        return dataset.filter(row => {
            for (const [col, allowedSet] of Object.entries(filters)) {
                if (!allowedSet) continue;
                if (allowedSet.size === 0) return false;
                let val = row[col];
                if (val === null || val === undefined || val === '') val = '(Vazio)';
                else val = String(val).trim();
                if (!allowedSet.has(val)) return false;
            }
            return true;
        });
    },

    clearAllFilters(tableId) {
        if (this.activeFilters[tableId]) {
            this.activeFilters[tableId] = {};
            this.updateHeaderFilterBadges(tableId);
        }
    }
};

window.ColumnFilter = ColumnFilter;

const RowTools = {
    colors: [['red','#EF4444','Vermelho'],['green','#22C55E','Verde'],['light_blue','#38BDF8','Azul claro'],['dark_blue','#1D4ED8','Azul escuro'],['purple','#9333EA','Roxo'],['pink','#EC4899','Rosa'],['orange','#F97316','Laranja'],['yellow','#EAB308','Amarelo'],['black','#111827','Preto'],['','#FFF','Remover cor']],
    initHeaderPin(tableId, buttonId) {
        const button = document.getElementById(buttonId);
        if (!button) return;
        const key = `pm13_${tableId}_header_pinned`;
        const apply = (pinned) => {
            const table = document.getElementById(tableId);
            const toolbarId = tableId === 'plans-table' ? 'bulk-actions-toolbar-plans'
                : tableId === 'items-table' ? 'bulk-actions-toolbar'
                : `bulk-actions-toolbar-${tableId.replace('-table', '')}`;
            table?.classList.toggle('header-pinned', pinned);
            document.getElementById(toolbarId)?.classList.toggle('header-context-pinned', pinned);
            table?.closest('.table-responsive-container')?.classList.toggle('items-header-scroll-pinned', pinned);
            table?.closest('.table-card')?.classList.toggle('items-header-card-pinned', pinned);
            button.textContent = pinned ? '📌 Cabeçalho Fixo' : '📌 Fixar Cabeçalho';
            localStorage.setItem(key, pinned ? '1' : '0');
        };
        apply(localStorage.getItem(key) === '1');
        button.onclick = () => apply(!document.getElementById(tableId)?.classList.contains('header-pinned'));
    },
    open(event, entity, id, reloadExpression) {
        event.stopPropagation(); document.getElementById('entity-row-color-palette')?.remove();
        const palette = document.createElement('div'); palette.id='entity-row-color-palette'; palette.className='item-row-color-palette';
        palette.innerHTML=this.colors.map(([key,hex,label])=>`<button title="${label}" style="--swatch:${hex}" onclick="RowTools.set(event,'${entity}',${id},'${key}',${reloadExpression})">${key?'':'×'}</button>`).join('');
        document.body.appendChild(palette); const rect=event.currentTarget.getBoundingClientRect();
        palette.style.left=`${Math.min(rect.left,window.innerWidth-190)}px`; palette.style.top=`${rect.bottom+5}px`;
        setTimeout(()=>document.addEventListener('click',()=>palette.remove(),{once:true}),0);
    },
    async set(event, entity, id, color, reload) {
        event.stopPropagation();
        await API.post(`/api/${entity}/${id}/row-color`,{project_id:window.App.currentProjectId,row_color:color});
        document.getElementById('entity-row-color-palette')?.remove(); if (reload) await reload();
    }
};
window.RowTools = RowTools;

const TableColumnResizer = {
    init(tableId) {
        const table = document.getElementById(tableId);
        if (!table || table.dataset.columnResizeReady === '1') return;
        const headers = Array.from(table.querySelectorAll('thead tr:first-child > th'));
        if (!headers.length) return;
        table.dataset.columnResizeReady = '1';
        table.classList.add('resizable-data-table');

        let colgroup = table.querySelector(':scope > colgroup');
        if (!colgroup) {
            colgroup = document.createElement('colgroup');
            headers.forEach((header, index) => {
                const col = document.createElement('col');
                col.dataset.colKey = header.dataset.col || `column-${index}`;
                colgroup.appendChild(col);
            });
            table.insertBefore(colgroup, table.firstChild);
        }

        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(`pm13_table_widths_${tableId}`) || '{}'); } catch (_) {}
        const columns = Array.from(colgroup.children);
        headers.forEach((header, index) => {
            const col = columns[index];
            const key = col.dataset.colKey;
            const storedWidth = Number(saved[key]);
            const declaredWidth = Number(header.dataset.defaultWidth);
            const initialWidth = storedWidth || declaredWidth || Math.max(44, Math.round(header.getBoundingClientRect().width));
            col.style.width = `${initialWidth}px`;

            const handle = document.createElement('i');
            handle.className = 'column-resizer table-column-resizer';
            handle.title = 'Arraste para ajustar a largura; duplo clique para restaurar';
            header.appendChild(handle);
            handle.onmousedown = event => this.startResize(event, table, header, col);
            handle.ondblclick = event => {
                event.preventDefault();
                event.stopPropagation();
                col.style.width = '';
                delete saved[key];
                localStorage.setItem(`pm13_table_widths_${tableId}`, JSON.stringify(saved));
            };
        });
    },

    startResize(event, table, header, col) {
        event.preventDefault();
        event.stopPropagation();
        const startX = event.clientX;
        const startWidth = header.getBoundingClientRect().width;
        document.body.classList.add('resizing-table-column');
        const move = moveEvent => {
            col.style.width = `${Math.max(44, Math.round(startWidth + moveEvent.clientX - startX))}px`;
        };
        const up = () => {
            document.body.classList.remove('resizing-table-column');
            window.removeEventListener('mousemove', move);
            window.removeEventListener('mouseup', up);
            const widths = {};
            table.querySelectorAll(':scope > colgroup > col').forEach(column => {
                widths[column.dataset.colKey] = Math.round(column.getBoundingClientRect().width);
            });
            try { localStorage.setItem(`pm13_table_widths_${table.id}`, JSON.stringify(widths)); } catch (_) {}
        };
        window.addEventListener('mousemove', move);
        window.addEventListener('mouseup', up);
    }
};

window.TableColumnResizer = TableColumnResizer;
