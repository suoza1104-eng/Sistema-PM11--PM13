/**
 * Hierarchical long-text editor for PM13.
 * Keeps SAP/export output as ordinary numbered plain text while editing it as
 * movable blocks/topics. Free text remains free text unless numbering is detected.
 */
window.LongTextEditor = {
    mode: 'FREE',
    nodes: [],
    selectedIndex: null,
    dragIndex: null,
    blocks: [],
    sourceOriginal: '',
    history: [],
    historyIndex: -1,
    historyTimer: null,
    historyLimit: 100,
    restoringHistory: false,
    fullscreen: false,

    esc(value) {
        const d = document.createElement('div');
        d.textContent = value == null ? '' : String(value);
        return d.innerHTML;
    },

    uid() {
        return 'n' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
    },

    cloneNodes(nodes = this.nodes) {
        return (Array.isArray(nodes) ? nodes : []).map(n => ({
            id: String(n?.id || this.uid()),
            type: n?.type === 'free' ? 'free' : 'topic',
            level: Number(n?.level || 0),
            text: String(n?.text ?? ''),
            restart_numbering: n?.type === 'free' ? false : Boolean(n?.restart_numbering),
            resume_numbering: n?.type === 'free' ? false : Boolean(n?.resume_numbering)
        }));
    },

    captureState(syncDom = true) {
        if (syncDom && this.mode !== 'FREE') this.syncAllFromDom();
        const textarea = document.getElementById('form-lt-text');
        return {
            mode: this.mode,
            nodes: this.cloneNodes(),
            selectedIndex: this.selectedIndex,
            sourceOriginal: this.sourceOriginal || '',
            freeText: textarea?.value || ''
        };
    },

    stateKey(state) {
        return JSON.stringify({
            mode: state.mode,
            nodes: state.nodes.map(n => ({ type:n.type, level:n.level, text:n.text, restart_numbering:Boolean(n.restart_numbering), resume_numbering:Boolean(n.resume_numbering) })),
            freeText: state.mode === 'FREE' ? state.freeText : ''
        });
    },

    resetHistory() {
        if (this.historyTimer) clearTimeout(this.historyTimer);
        this.historyTimer = null;
        const initial = this.captureState(false);
        this.history = [initial];
        this.historyIndex = 0;
        this.updateHistoryButtons();
    },

    pushHistory(syncDom = true) {
        if (this.restoringHistory) return;
        if (this.historyTimer) clearTimeout(this.historyTimer);
        this.historyTimer = null;
        const state = this.captureState(syncDom);
        const key = this.stateKey(state);
        const current = this.history[this.historyIndex];
        if (current && this.stateKey(current) === key) {
            this.updateHistoryButtons();
            return;
        }
        if (this.historyIndex < this.history.length - 1) this.history = this.history.slice(0, this.historyIndex + 1);
        this.history.push(state);
        if (this.history.length > this.historyLimit) this.history.shift();
        this.historyIndex = this.history.length - 1;
        this.updateHistoryButtons();
    },

    scheduleHistory(delay = 450) {
        if (this.restoringHistory) return;
        if (this.historyTimer) clearTimeout(this.historyTimer);
        this.historyTimer = setTimeout(() => this.pushHistory(true), delay);
    },

    commitPendingHistory() {
        if (!this.historyTimer) return;
        clearTimeout(this.historyTimer);
        this.historyTimer = null;
        this.pushHistory(true);
    },

    restoreHistoryState(state) {
        if (!state) return;
        this.restoringHistory = true;
        this.mode = state.mode || 'FREE';
        this.nodes = this.cloneNodes(state.nodes || []);
        this.selectedIndex = state.selectedIndex ?? null;
        this.sourceOriginal = state.sourceOriginal || '';
        const textarea = document.getElementById('form-lt-text');
        if (textarea) textarea.value = state.freeText || '';
        this.render();
        this.restoringHistory = false;
        this.updateHistoryButtons();
    },

    undo() {
        this.commitPendingHistory();
        if (this.historyIndex <= 0) return;
        this.historyIndex -= 1;
        this.restoreHistoryState(this.history[this.historyIndex]);
    },

    redo() {
        this.commitPendingHistory();
        if (this.historyIndex < 0 || this.historyIndex >= this.history.length - 1) return;
        this.historyIndex += 1;
        this.restoreHistoryState(this.history[this.historyIndex]);
    },

    updateHistoryButtons() {
        const undoBtn = document.getElementById('btn-lt-undo');
        const redoBtn = document.getElementById('btn-lt-redo');
        if (undoBtn) undoBtn.disabled = this.historyIndex <= 0;
        if (redoBtn) redoBtn.disabled = this.historyIndex < 0 || this.historyIndex >= this.history.length - 1;
    },

    setFullscreen(enabled) {
        const modal = document.querySelector('#modal-long-text .modal-long-text-editor');
        const btn = document.getElementById('btn-lt-fullscreen');
        this.fullscreen = Boolean(enabled);
        if (modal) {
            modal.classList.toggle('lt-modal-fullscreen', this.fullscreen);
            modal.classList.toggle('lt-mode-free', this.mode === 'FREE');
            modal.classList.toggle('lt-mode-structured', this.mode !== 'FREE');
        }
        if (btn) {
            btn.textContent = this.fullscreen ? '✕' : '⛶';
            btn.title = this.fullscreen ? 'Sair da tela cheia' : 'Abrir tela cheia';
            btn.setAttribute('aria-label', btn.title);
            btn.classList.toggle('is-exit-fullscreen', this.fullscreen);
        }
    },

    toggleFullscreen() {
        this.setFullscreen(!this.fullscreen);
    },

    init() {
        const textarea = document.getElementById('form-lt-text');
        if (textarea && !textarea.dataset.ltHistoryBound) {
            textarea.dataset.ltHistoryBound = '1';
            textarea.addEventListener('input', () => {
                if (this.mode === 'FREE') {
                    this.sourceOriginal = textarea.value;
                    this.scheduleHistory();
                }
            });
            textarea.addEventListener('paste', event => {
                const pasted = event.clipboardData?.getData('text/plain') || '';
                if (!pasted.includes('\n')) return;
                setTimeout(async () => {
                    if (this.mode !== 'FREE') return;
                    await this.setFromText(textarea.value, true, false);
                    if (this.mode !== 'FREE') {
                        UI.showToast(`${this.nodes.filter(node => node.type === 'topic').length} topico(s) reconhecido(s) ao colar.`, 'success');
                    }
                }, 0);
            });
            textarea.addEventListener('keydown', event => {
                const mod = event.ctrlKey || event.metaKey;
                if (!mod) return;
                const key = String(event.key || '').toLowerCase();
                if (key === 'z') {
                    event.preventDefault();
                    if (event.shiftKey) this.redo(); else this.undo();
                } else if (key === 'y') {
                    event.preventDefault();
                    this.redo();
                }
            });
        }
        this.updateHistoryButtons();
        this.setFullscreen(false);
    },

    startBlank() {
        this.mode = 'FREE';
        this.nodes = [];
        this.selectedIndex = null;
        this.sourceOriginal = '';
        const ta = document.getElementById('form-lt-text');
        if (ta) ta.value = '';
        this.setFullscreen(false);
        this.render();
        this.resetHistory();
    },

    async loadRecord(record = {}, resetHistory = true) {
        if (resetHistory) this.setFullscreen(false);
        this.sourceOriginal = record.source_text_original || record.text || '';
        const mode = String(record.structure_mode || '').toUpperCase();
        if ((mode === 'STRUCTURED' || mode === 'MIXED') && record.structure_json) {
            try {
                const parsed = typeof record.structure_json === 'string' ? JSON.parse(record.structure_json) : record.structure_json;
                if (Array.isArray(parsed) && parsed.length) {
                    this.mode = mode;
                    this.nodes = this.normalizeNodes(parsed);
                    this.selectedIndex = null;
                    this.render();
                    if (resetHistory) this.resetHistory(); else this.pushHistory(false);
                    return;
                }
            } catch (_) {}
        }
        await this.setFromText(record.text || '', true, resetHistory);
    },

    async setFromText(text, detect = true, resetHistory = false) {
        const raw = String(text || '').replace(/\r\n?/g, '\n');
        this.sourceOriginal = raw;
        if (detect && raw.trim()) {
            try {
                const parsed = await API.post('/api/long-texts/normalize', { text: raw });
                if (parsed && parsed.mode !== 'FREE' && Array.isArray(parsed.nodes) && parsed.nodes.length) {
                    this.mode = parsed.mode;
                    this.nodes = this.normalizeNodes(parsed.nodes);
                    this.selectedIndex = null;
                    this.render();
                    if (resetHistory) this.resetHistory(); else this.pushHistory(false);
                    return;
                }
            } catch (e) {
                console.warn('Falha ao detectar estrutura de texto:', e);
            }
        }
        this.mode = 'FREE';
        this.nodes = [];
        this.selectedIndex = null;
        const ta = document.getElementById('form-lt-text');
        if (ta) ta.value = raw;
        this.render();
        if (resetHistory) this.resetHistory(); else this.pushHistory(false);
    },

    normalizeNodes(nodes) {
        let previousTopicLevel = 0;
        return (Array.isArray(nodes) ? nodes : []).map(raw => {
            const type = String(raw?.type || 'topic').toLowerCase() === 'free' ? 'free' : 'topic';
            let level = type === 'topic' ? Math.max(1, Math.min(8, parseInt(raw?.level || 1, 10))) : 0;
            if (type === 'topic' && previousTopicLevel && level > previousTopicLevel + 1) level = previousTopicLevel + 1;
            if (type === 'topic') previousTopicLevel = level;
            return { id: String(raw?.id || this.uid()), type, level, text: String(raw?.text ?? ''), restart_numbering: type === 'topic' && Boolean(raw?.restart_numbering), resume_numbering: type === 'topic' && Boolean(raw?.resume_numbering) };
        });
    },

    numberedNodes() {
        const counters = [];
        const suspendedCounters = [];
        return this.nodes.map(node => {
            if (node.type !== 'topic') return { ...node, number: '' };
            let level = Math.max(1, Math.min(8, Number(node.level || 1)));
            if (node.restart_numbering) {
                if (counters.length) suspendedCounters.push([...counters]);
                counters.splice(0, counters.length, ...Array(level).fill(1));
            } else if (node.resume_numbering && suspendedCounters.length) {
                const previous = suspendedCounters.pop();
                counters.splice(0, counters.length, ...previous);
                level = counters.length;
                counters[counters.length - 1] += 1;
            } else if (!counters.length) {
                while (counters.length < level) counters.push(1);
            } else if (level > counters.length) {
                while (counters.length < level) counters.push(1);
            } else if (level === counters.length) {
                counters[counters.length - 1] += 1;
            } else {
                counters.splice(level);
                counters[counters.length - 1] += 1;
            }
            return { ...node, level, number: counters.join('.') };
        });
    },

    renderedText() {
        const lines = this.numberedNodes().map(node => node.type === 'topic'
            ? `${node.number} ${String(node.text || '').trim()}`.trimEnd()
            : String(node.text || ''));
        return lines.join('\n');
    },

    getPayload() {
        if (this.mode === 'FREE') {
            const text = document.getElementById('form-lt-text')?.value || '';
            return { text, structure_mode: 'FREE', structure_json: null, source_text_original: this.sourceOriginal || text };
        }
        this.syncAllFromDom();
        const hasFree = this.nodes.some(n => n.type === 'free' && String(n.text || '').trim());
        const hasTopic = this.nodes.some(n => n.type === 'topic');
        const mode = hasTopic ? (hasFree ? 'MIXED' : 'STRUCTURED') : 'FREE';
        if (mode === 'FREE') {
            const text = this.nodes.map(n => n.text || '').join('\n');
            return { text, structure_mode: 'FREE', structure_json: null, source_text_original: this.sourceOriginal || text };
        }
        const text = this.renderedText();
        const ta = document.getElementById('form-lt-text');
        if (ta) ta.value = text;
        return { text, structure_mode: mode, structure_json: JSON.stringify(this.nodes), source_text_original: this.sourceOriginal || text };
    },

    render() {
        const host = document.getElementById('lt-structured-editor');
        const textarea = document.getElementById('form-lt-text');
        const modeBadge = document.getElementById('lt-structure-mode-badge');
        const structuredToolbar = document.getElementById('lt-structured-toolbar');
        if (!host || !textarea) return;

        const isFree = this.mode === 'FREE';
        const modal = document.querySelector('#modal-long-text .modal-long-text-editor');
        if (modal) {
            modal.classList.toggle('lt-mode-free', isFree);
            modal.classList.toggle('lt-mode-structured', !isFree);
        }
        textarea.classList.toggle('hidden', !isFree);
        host.classList.toggle('hidden', isFree);
        if (structuredToolbar) structuredToolbar.classList.toggle('hidden', isFree);
        if (modeBadge) {
            modeBadge.textContent = isFree ? 'Texto livre' : (this.mode === 'MIXED' ? 'Estruturado + livre' : 'Estruturado');
            modeBadge.className = `lt-mode-badge ${isFree ? 'free' : 'structured'}`;
        }
        const detectBtn = document.getElementById('btn-lt-detect-structure');
        if (detectBtn) detectBtn.textContent = isFree ? '🔎 Reconhecer tópicos' : '↩ Converter para texto livre';
        this.updateHistoryButtons();
        if (isFree) return;

        const numbered = this.numberedNodes();
        const selectedSet = new Set(this.getBlockIndices(this.selectedIndex));
        host.innerHTML = numbered.length ? numbered.map((node, index) => {
            const isSelected = selectedSet.has(index);
            const indent = node.type === 'topic' ? Math.max(0, node.level - 1) * 24 : 0;
            return `<div class="lt-node-row ${node.type === 'free' ? 'free-line' : 'topic-line'} ${isSelected ? 'block-selected' : ''}" data-index="${index}" draggable="true" ondragstart="LongTextEditor.onDragStart(event,${index})" ondragover="LongTextEditor.onDragOver(event)" ondrop="LongTextEditor.onDrop(event,${index})">
                <div class="lt-node-indent" style="width:${indent}px"></div>
                ${node.type === 'topic'
                    ? `<button type="button" class="lt-node-number" title="Selecionar este bloco" onclick="LongTextEditor.selectBlock(${index})">${this.esc(node.number)}</button>`
                    : `<span class="lt-free-marker" title="Parágrafo livre">¶</span>`}
                <div class="lt-node-text" contenteditable="true" spellcheck="true" lang="pt-BR" data-index="${index}" oninput="LongTextEditor.onNodeInput(${index},this)" onkeydown="LongTextEditor.onNodeKeydown(event,${index},this)" onpaste="LongTextEditor.onNodePaste(event,${index},this)" onfocus="LongTextEditor.focusNode(${index})">${this.esc(node.text)}</div>
                <span class="lt-node-more" title="Clique e arraste para mover esta linha ou bloco" style="cursor:grab; user-select:none; padding:2px 6px;">⋮⋮</span>
            </div>`;
        }).join('') : `<div class="lt-editor-empty">Nenhum tópico. Use <strong>+ Tópico</strong> ou volte para Texto livre.</div>`;
        this.updateBlockActionState();
    },

    syncAllFromDom() {
        document.querySelectorAll('#lt-structured-editor .lt-node-text[data-index]').forEach(el => {
            const idx = Number(el.dataset.index);
            if (this.nodes[idx]) this.nodes[idx].text = (el.innerText || '').replace(/\n/g, ' ').trimEnd();
        });
    },

    onNodeInput(index, el) {
        if (this.nodes[index]) this.nodes[index].text = (el.innerText || '').replace(/\n/g, ' ');
        const ta = document.getElementById('form-lt-text');
        if (ta) ta.value = this.renderedText();
        this.scheduleHistory();
    },

    async onNodePaste(event, index, el) {
        const pasted = event.clipboardData?.getData('text/plain') || '';
        if (!pasted.includes('\n')) return;
        event.preventDefault();
        try {
            const parsed = await API.post('/api/long-texts/normalize', { text: pasted });
            if (parsed?.mode !== 'FREE' && Array.isArray(parsed?.nodes) && parsed.nodes.length) {
                this.syncAllFromDom();
                const incoming = this.normalizeNodes(parsed.nodes);
                const currentIsEmpty = !String(this.nodes[index]?.text || '').trim();
                this.nodes.splice(currentIsEmpty ? index : index + 1, currentIsEmpty ? 1 : 0, ...incoming);
                this.mode = this.nodes.some(n => n.type === 'free' && String(n.text || '').trim()) ? 'MIXED' : 'STRUCTURED';
                this.selectedIndex = null;
                this.render();
                this.pushHistory(false);
                UI.showToast(`${parsed.topic_count || incoming.filter(n => n.type === 'topic').length} topico(s) reconhecido(s) ao colar.`, 'success');
                return;
            }
        } catch (error) {
            console.warn('Falha ao reconhecer topicos colados:', error);
        }
        el.focus();
        document.execCommand('insertText', false, pasted);
        this.onNodeInput(index, el);
    },

    focusNode(index) {
        this.lastFocusedIndex = index;
        if (this.selectedIndex != null && !this.getBlockIndices(this.selectedIndex).includes(index)) {
            this.selectedIndex = null;
            this.updateBlockActionState();
        }
    },

    getActiveNodeIndex() {
        if (this.selectedIndex != null && this.selectedIndex >= 0 && this.selectedIndex < this.nodes.length) {
            return this.selectedIndex;
        }
        const activeEl = document.activeElement;
        if (activeEl && activeEl.classList && activeEl.classList.contains('lt-node-text')) {
            const idxAttr = activeEl.getAttribute('data-index');
            if (idxAttr != null && !isNaN(parseInt(idxAttr))) {
                return parseInt(idxAttr, 10);
            }
        }
        if (this.lastFocusedIndex != null && this.lastFocusedIndex >= 0 && this.lastFocusedIndex < this.nodes.length) {
            return this.lastFocusedIndex;
        }
        return null;
    },

    caretAtStart(el) {
        const sel = window.getSelection();
        if (!sel || !sel.rangeCount) return false;
        const range = sel.getRangeAt(0);
        if (!el.contains(range.startContainer)) return false;
        const test = range.cloneRange();
        test.selectNodeContents(el);
        test.setEnd(range.startContainer, range.startOffset);
        return test.toString().length === 0;
    },

    onNodeKeydown(event, index, el) {
        const mod = event.ctrlKey || event.metaKey;
        const key = String(event.key || '').toLowerCase();
        if (mod && key === 'z') {
            event.preventDefault();
            if (event.shiftKey) this.redo(); else this.undo();
            return;
        }
        if (mod && key === 'y') {
            event.preventDefault();
            this.redo();
            return;
        }
        const node = this.nodes[index];
        if (!node) return;
        if (event.key === 'Enter') {
            event.preventDefault();
            this.onNodeInput(index, el);
            const newNode = { id: this.uid(), type: node.type, level: node.type === 'topic' ? node.level : 0, text: '' };
            this.nodes.splice(index + 1, 0, newNode);
            this.selectedIndex = null;
            this.render();
            this.pushHistory(false);
            this.focusEditable(index + 1);
            return;
        }
        if (event.key === 'Tab' && node.type === 'topic') {
            event.preventDefault();
            this.onNodeInput(index, el);
            if (event.shiftKey) this.outdent(index); else this.indent(index);
            return;
        }
        if (event.key === 'Backspace' && this.caretAtStart(el)) {
            if (node.type === 'topic') {
                event.preventDefault();
                this.onNodeInput(index, el);
                if (node.level > 1) {
                    node.level -= 1;
                } else {
                    node.type = 'free';
                    node.level = 0;
                    this.mode = 'MIXED';
                }
                this.render();
                this.pushHistory(false);
                this.focusEditable(index, true);
                return;
            }
            if (node.type === 'free') {
                if (!String(node.text || '').trim() && this.nodes.length > 1) {
                    event.preventDefault();
                    this.nodes.splice(index, 1);
                    this.render();
                    this.pushHistory(false);
                    this.focusEditable(Math.max(0, index - 1), true);
                    return;
                }
            }
        }
    },

    focusEditable(index, end = false) {
        setTimeout(() => {
            const el = document.querySelector(`#lt-structured-editor .lt-node-text[data-index="${index}"]`);
            if (!el) return;
            el.focus();
            if (end) {
                const range = document.createRange(); const sel = window.getSelection();
                range.selectNodeContents(el); range.collapse(false); sel.removeAllRanges(); sel.addRange(range);
            }
        }, 0);
    },

    previousTopicIndex(index) {
        for (let i = index - 1; i >= 0; i--) if (this.nodes[i]?.type === 'topic') return i;
        return -1;
    },

    indent(index) {
        const node = this.nodes[index]; if (!node || node.type !== 'topic') return;
        const prevIdx = this.previousTopicIndex(index);
        if (prevIdx < 0) return UI.showToast('Não há tópico anterior para criar um subitem.', 'info');
        const prev = this.nodes[prevIdx];
        const maxLevel = Math.min(8, prev.level + 1);
        if (node.level < maxLevel) node.level += 1;
        this.render(); this.pushHistory(false); this.focusEditable(index, true);
    },

    outdent(index) {
        const node = this.nodes[index]; if (!node || node.type !== 'topic') return;
        if (node.level > 1) {
            node.level -= 1;
        } else {
            node.type = 'free';
            node.level = 0;
            this.mode = 'MIXED';
        }
        this.render();
        this.pushHistory(false);
        this.focusEditable(index, true);
    },

    addTopic() {
        this.syncAllFromDom();
        if (this.mode === 'FREE') {
            const text = document.getElementById('form-lt-text')?.value || '';
            if (text.trim()) return UI.showToast('Use “Reconhecer tópicos” primeiro ou mantenha este texto como livre.', 'info');
            this.mode = 'STRUCTURED';
        }
        
        const activeIdx = this.getActiveNodeIndex();
        if (activeIdx != null && activeIdx >= 0 && activeIdx < this.nodes.length) {
            const activeNode = this.nodes[activeIdx];
            
            if (activeNode.type === 'free' && !String(activeNode.text || '').trim()) {
                const prevTopicIdx = this.previousTopicIndex(activeIdx);
                const level = prevTopicIdx >= 0 ? this.nodes[prevTopicIdx].level : 1;
                activeNode.type = 'topic';
                activeNode.level = level;
                this.selectedIndex = null;
                this.render();
                this.pushHistory(false);
                this.focusEditable(activeIdx, true);
                return;
            }

            let level = 1;
            if (activeNode.type === 'topic') {
                level = activeNode.level;
            } else {
                const prevTopicIdx = this.previousTopicIndex(activeIdx);
                if (prevTopicIdx >= 0) level = this.nodes[prevTopicIdx].level;
            }

            const insertAt = activeIdx + 1;
            this.nodes.splice(insertAt, 0, { id: this.uid(), type: 'topic', level, text: '' });
            this.selectedIndex = null;
            this.render();
            this.pushHistory(false);
            this.focusEditable(insertAt);
        } else {
            const level = this.nodes.length ? (this.nodes[this.nodes.length - 1].level || 1) : 1;
            const insertAt = this.nodes.length;
            this.nodes.splice(insertAt, 0, { id: this.uid(), type: 'topic', level, text: '' });
            this.selectedIndex = null;
            this.render();
            this.pushHistory(false);
            this.focusEditable(insertAt);
        }
    },

    addFreeLine() {
        if (this.mode === 'FREE') return UI.showToast('Você já está no modo Texto livre.', 'info');
        this.syncAllFromDom();
        
        const activeIdx = this.getActiveNodeIndex();
        const insertAt = activeIdx != null ? activeIdx + 1 : this.nodes.length;
        
        this.nodes.splice(insertAt, 0, { id: this.uid(), type: 'free', level: 0, text: '' });
        this.mode = 'MIXED';
        this.selectedIndex = null;
        this.render();
        this.pushHistory(false);
        this.focusEditable(insertAt);
    },

    async toggleDetection() {
        if (this.mode !== 'FREE') {
            const text = this.getPayload().text;
            if (!confirm('Converter para texto livre? A numeração atual será materializada como texto normal.')) return;
            this.mode = 'FREE'; this.nodes = []; this.selectedIndex = null;
            const ta = document.getElementById('form-lt-text'); if (ta) ta.value = text;
            this.render();
            this.pushHistory(false);
            return;
        }
        const text = document.getElementById('form-lt-text')?.value || '';
        if (!text.trim()) return UI.showToast('Digite ou cole um texto primeiro.', 'info');
        try {
            const parsed = await API.post('/api/long-texts/normalize', { text });
            if (!parsed || parsed.mode === 'FREE') {
                UI.showToast('Não identifiquei uma sequência de tópicos com segurança. O texto foi mantido livre.', 'info', 4500);
                return;
            }
            this.mode = parsed.mode; this.nodes = this.normalizeNodes(parsed.nodes || []); this.sourceOriginal = text;
            this.render();
            this.pushHistory(false);
            UI.showToast(`${parsed.topic_count || 0} tópico(s) reconhecido(s) e normalizado(s).`, 'success');
        } catch (e) { UI.showToast(e.message, 'error'); }
    },

    isSectionHeaderFreeLine(node, nextNode) {
        if (!node || node.type !== 'free') return false;
        const text = String(node.text || '').trim();
        if (!text) return false;
        if (nextNode && nextNode.type === 'topic' && nextNode.restart_numbering) {
            return true;
        }
        const upper = text.toUpperCase();
        if (upper.includes('RECOMENDAÇÕES DE SEGURANÇA') || upper.includes('RECOMENDACOES DE SEGURANCA') || upper.includes('CUIDADOS DE SEGURANÇA') || upper.includes('EQUIPAMENTOS DE PROTEÇÃO')) {
            return true;
        }
        if (nextNode && nextNode.type === 'topic' && nextNode.level === 1 && text === upper && text.length > 5 && !/[.:!?]$/.test(text)) {
            return true;
        }
        return false;
    },

    getBlockEnd(index) {
        if (index == null || index < 0 || index >= this.nodes.length) return this.nodes.length;
        const root = this.nodes[index];
        if (!root || root.type !== 'topic') return index + 1;
        let end = index + 1;
        while (end < this.nodes.length) {
            const node = this.nodes[end];
            const nextNode = end + 1 < this.nodes.length ? this.nodes[end + 1] : null;

            if (node.type === 'topic') {
                if (node.level <= root.level || node.restart_numbering) break;
            } else if (node.type === 'free') {
                if (this.isSectionHeaderFreeLine(node, nextNode)) break;
            }
            end++;
        }
        return end;
    },

    getBlockIndices(index) {
        if (index == null || index < 0 || index >= this.nodes.length || this.nodes[index]?.type !== 'topic') return [];
        const end = this.getBlockEnd(index);
        return Array.from({ length: end - index }, (_, i) => index + i);
    },

    selectBlock(index) {
        this.syncAllFromDom();
        this.selectedIndex = this.selectedIndex === index ? null : index;
        if (this.selectedIndex != null) {
            this.lastFocusedIndex = this.selectedIndex;
        }
        this.render();
    },

    updateBlockActionState() {
        const activeIdx = this.getActiveNodeIndex();
        const active = activeIdx != null && this.nodes[activeIdx]?.type === 'topic';
        ['btn-lt-delete-block','btn-lt-duplicate-block','btn-lt-save-block','btn-lt-restart-numbering','btn-lt-resume-numbering'].forEach(id => {
            const el = document.getElementById(id); if (el) el.disabled = !active;
        });
        const restartBtn = document.getElementById('btn-lt-restart-numbering');
        const restarting = active && Boolean(this.nodes[activeIdx]?.restart_numbering);
        const resuming = active && Boolean(this.nodes[activeIdx]?.resume_numbering);
        if (restartBtn) {
            restartBtn.classList.toggle('btn-primary', restarting);
            restartBtn.classList.toggle('btn-outline', !restarting);
            restartBtn.textContent = restarting ? '↩ Continuar contagem' : '↪ Reiniciar em 1';
        }
        const resumeBtn = document.getElementById('btn-lt-resume-numbering');
        if (resumeBtn) {
            resumeBtn.classList.toggle('btn-primary', resuming);
            resumeBtn.classList.toggle('btn-outline', !resuming);
            resumeBtn.textContent = resuming ? '✓ Retomando anterior' : '↩ Retomar anterior';
        }
        const label = document.getElementById('lt-selected-block-label');
        if (label) label.textContent = active ? `Tópico ativo: ${this.numberedNodes()[activeIdx]?.number || ''}` : 'Clique em qualquer linha de tópico para ver as opções.';
    },

    toggleRestartNumbering() {
        let activeIdx = this.getActiveNodeIndex();
        if (activeIdx == null || activeIdx < 0 || activeIdx >= this.nodes.length) {
            return UI.showToast('Clique em uma linha de tópico para reiniciar a numeração em 1.', 'info');
        }
        this.syncAllFromDom();
        
        let targetIdx = activeIdx;
        while (targetIdx > 0 && this.nodes[targetIdx]?.type !== 'topic') {
            targetIdx--;
        }

        const node = this.nodes[targetIdx];
        if (!node || node.type !== 'topic') {
            return UI.showToast('Selecione um tópico para reiniciar a numeração.', 'warning');
        }

        node.restart_numbering = !node.restart_numbering;
        if (node.restart_numbering) node.resume_numbering = false;
        
        this.selectedIndex = targetIdx;
        this.lastFocusedIndex = targetIdx;
        this.render();
        this.pushHistory(false);
        UI.showToast(node.restart_numbering ? 'A numeração deste bloco recomeçará em 1.' : 'O bloco continuará a numeração anterior.', 'success');
    },

    toggleResumeNumbering() {
        let activeIdx = this.getActiveNodeIndex();
        if (activeIdx == null || activeIdx < 0 || activeIdx >= this.nodes.length) {
            return UI.showToast('Clique em uma linha de tópico para gerenciar a numeração.', 'info');
        }
        this.syncAllFromDom();
        
        let targetIdx = activeIdx;
        while (targetIdx > 0 && this.nodes[targetIdx]?.type !== 'topic') {
            targetIdx--;
        }

        const node = this.nodes[targetIdx];
        if (!node || node.type !== 'topic') return;

        node.resume_numbering = !node.resume_numbering;
        if (node.resume_numbering) node.restart_numbering = false;
        
        this.selectedIndex = targetIdx;
        this.lastFocusedIndex = targetIdx;
        this.render();
        this.pushHistory(false);
        UI.showToast(node.resume_numbering ? 'A numeração retomará o contador anterior.' : 'O bloco seguirá a contagem normal.', 'success');
    },

    deleteSelectedBlock() {
        const activeIdx = this.getActiveNodeIndex();
        if (activeIdx == null || activeIdx < 0 || activeIdx >= this.nodes.length) {
            UI.showToast('Selecione ou clique na linha do bloco que deseja excluir.', 'info');
            return;
        }
        let start = activeIdx;
        while (start > 0 && this.nodes[start]?.type === 'topic' && this.nodes[start].level > 1) {
            start--;
        }
        const number = this.numberedNodes()[start]?.number || '';
        if (!confirm(`Excluir o bloco ${number} completo, incluindo todos os seus subtópicos?`)) return;
        const end = this.getBlockEnd(start);
        this.nodes.splice(start, end - start);
        this.selectedIndex = null;
        if (!this.nodes.some(n => n.type === 'topic')) this.mode = this.nodes.some(n => String(n.text || '').trim()) ? 'FREE' : 'STRUCTURED';
        this.render();
        this.pushHistory(false);
    },

    duplicateSelectedBlock() {
        const activeIdx = this.getActiveNodeIndex();
        if (activeIdx == null || activeIdx < 0 || activeIdx >= this.nodes.length) {
            UI.showToast('Selecione ou clique na linha do bloco que deseja duplicar.', 'info');
            return;
        }
        this.syncAllFromDom();
        let start = activeIdx;
        while (start > 0 && this.nodes[start]?.type === 'topic' && this.nodes[start].level > 1) {
            start--;
        }
        const end = this.getBlockEnd(start);
        const copies = this.nodes.slice(start, end).map(n => ({ ...n, id: this.uid() }));
        this.nodes.splice(end, 0, ...copies);
        this.selectedIndex = end;
        this.render();
        this.pushHistory(false);
    },

    async saveSelectedBlock() {
        const activeIdx = this.getActiveNodeIndex();
        if (activeIdx == null || activeIdx < 0 || activeIdx >= this.nodes.length) {
            UI.showToast('Selecione ou clique na linha do bloco que deseja salvar como padrão.', 'info');
            return;
        }
        this.syncAllFromDom();
        
        let start = activeIdx;
        while (start > 0 && this.nodes[start]?.type === 'topic' && this.nodes[start].level > 1) {
            start--;
        }

        const rootNode = this.nodes[start];
        if (!rootNode || rootNode.type !== 'topic') {
            UI.showToast('Selecione a linha de um tópico para salvar como bloco padrão.', 'warning');
            return;
        }

        const end = this.getBlockEnd(start);
        const rootLevel = rootNode.level;
        const block = this.nodes.slice(start, end).map(n => ({
            ...n,
            id: this.uid(),
            level: n.type === 'topic' ? Math.max(1, n.level - rootLevel + 1) : 0
        }));

        try {
            this.blocks = await API.get('/api/long-text-blocks') || [];
        } catch (e) {
            console.warn('Não foi possível carregar categorias:', e);
        }
        this.openSaveBlockDialog(block);
    },

    ensureBlockDialogs() {
        if (!document.getElementById('modal-lt-save-block')) {
            document.body.insertAdjacentHTML('beforeend', `<div id="modal-lt-save-block" class="modal-overlay hidden" style="z-index:2700"><div class="modal modal-md"><div class="modal-header"><h2>⭐ Salvar Bloco Padrão</h2><button class="btn-icon" onclick="LongTextEditor.closeDialog('modal-lt-save-block')">✕</button></div><div class="modal-body"><div class="form-group"><label>Nome do bloco</label><input id="lt-block-title" placeholder="Ex: Sensor de subvelocidade"></div><div class="form-group"><label>Categoria</label><input id="lt-block-category" value="GERAL" placeholder="Selecione ou digite uma nova categoria" list="lt-block-category-options" autocomplete="off" onkeydown="LongTextEditor.onBlockCategoryKeydown(event)"><datalist id="lt-block-category-options"></datalist><small class="muted">Escolha uma categoria existente ou digite uma nova e pressione Enter.</small></div><div class="form-group"><label>Tags</label><input id="lt-block-tags" placeholder="sensor, subvelocidade, correia"></div><input type="hidden" id="lt-block-json"></div><div class="modal-footer"><button class="btn btn-outline" onclick="LongTextEditor.closeDialog('modal-lt-save-block')">Cancelar</button><button class="btn btn-primary" onclick="LongTextEditor.confirmSaveBlock()">Salvar bloco</button></div></div></div>`);
        }
        if (!document.getElementById('modal-lt-block-library')) {
            document.body.insertAdjacentHTML('beforeend', `<div id="modal-lt-block-library" class="modal-overlay hidden" style="z-index:2700"><div class="modal modal-lg"><div class="modal-header"><div><h2>🧩 Biblioteca de Blocos Padrão</h2><small>Insira um procedimento dentro do texto longo; a numeração será recalculada automaticamente.</small></div><button class="btn-icon" onclick="LongTextEditor.closeDialog('modal-lt-block-library')">✕</button></div><div class="modal-body"><div class="lt-block-library-controls"><input id="lt-block-search" placeholder="Pesquisar bloco, categoria ou tag..." oninput="LongTextEditor.renderBlockLibrary()"><select id="lt-block-placement"><option value="after">Depois do bloco selecionado</option><option value="before">Antes do bloco selecionado</option><option value="inside">Dentro do bloco selecionado</option><option value="end">No final do texto</option></select></div><div id="lt-block-library-list" class="lt-block-library-list"></div></div><div class="modal-footer"><button class="btn btn-outline" onclick="LongTextEditor.closeDialog('modal-lt-block-library')">Fechar</button></div></div></div>`);
        }
    },

    openSaveBlockDialog(block) {
        this.ensureBlockDialogs();
        this.renderBlockCategoryOptions();
        document.getElementById('lt-block-title').value = block.find(n => n.type === 'topic')?.text || '';
        document.getElementById('lt-block-category').value = 'GERAL';
        document.getElementById('lt-block-tags').value = '';
        document.getElementById('lt-block-json').value = JSON.stringify(block);
        document.getElementById('modal-lt-save-block').classList.remove('hidden');
    },

    blockCategories() {
        return [...new Set(['GERAL', ...(this.blocks || []).map(block => String(block.category || '').trim().toUpperCase()).filter(Boolean)])]
            .sort((a, b) => a.localeCompare(b, 'pt-BR'));
    },

    renderBlockCategoryOptions(extra = '') {
        const list = document.getElementById('lt-block-category-options');
        if (!list) return;
        const categories = this.blockCategories();
        const value = String(extra || '').trim().toUpperCase();
        if (value && !categories.includes(value)) categories.push(value);
        list.innerHTML = categories.sort((a, b) => a.localeCompare(b, 'pt-BR'))
            .map(category => `<option value="${this.esc(category)}"></option>`).join('');
    },

    onBlockCategoryKeydown(event) {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        const input = event.currentTarget;
        const category = String(input.value || '').trim().toUpperCase();
        if (!category) return UI.showToast('Digite ou selecione uma categoria.', 'warning');
        const isNew = !this.blockCategories().includes(category);
        input.value = category;
        this.renderBlockCategoryOptions(category);
        UI.showToast(isNew ? `Nova categoria "${category}" será criada ao salvar o bloco.` : `Categoria "${category}" selecionada.`, 'success');
        document.getElementById('lt-block-tags')?.focus();
    },

    async confirmSaveBlock() {
        const title = document.getElementById('lt-block-title').value.trim();
        if (!title) return UI.showToast('Informe o nome do bloco.', 'warning');
        try {
            await API.post('/api/long-text-blocks', {
                title,
                category: document.getElementById('lt-block-category').value.trim().toUpperCase() || 'GERAL',
                tags: document.getElementById('lt-block-tags').value.trim(),
                structure_json: document.getElementById('lt-block-json').value
            });
            this.closeDialog('modal-lt-save-block');
            UI.showToast(`Bloco "${title}" salvo na biblioteca.`, 'success');
        } catch (e) { UI.showToast(e.message, 'error'); }
    },

    async openBlockLibrary() {
        if (this.mode === 'FREE') return UI.showToast('Para inserir blocos, primeiro use um texto estruturado ou crie um tópico.', 'info');
        this.ensureBlockDialogs();
        try { this.blocks = await API.get('/api/long-text-blocks') || []; }
        catch (e) { return UI.showToast(e.message, 'error'); }
        const placement = document.getElementById('lt-block-placement');
        if (this.selectedIndex == null) placement.value = 'end';
        document.getElementById('lt-block-search').value = '';
        this.renderBlockLibrary();
        document.getElementById('modal-lt-block-library').classList.remove('hidden');
    },

    renderBlockLibrary() {
        const host = document.getElementById('lt-block-library-list'); if (!host) return;
        const q = (document.getElementById('lt-block-search')?.value || '').toLowerCase().trim();
        const list = this.blocks.filter(b => !q || `${b.title} ${b.category} ${b.tags} ${b.text}`.toLowerCase().includes(q));
        host.innerHTML = list.length ? list.map(b => `<div class="lt-block-card"><div><strong>${this.esc(b.title)}</strong><small>${this.esc(b.category || 'GERAL')} ${b.tags ? '• ' + this.esc(b.tags) : ''}</small><pre>${this.esc((b.text || '').split('\n').slice(0,4).join('\n'))}${(b.text || '').split('\n').length > 4 ? '\n…' : ''}</pre></div><div class="lt-block-card-actions"><button class="btn btn-xs btn-primary" onclick="LongTextEditor.insertBlock(${b.id})">Inserir</button><button class="btn btn-xs btn-danger" onclick="LongTextEditor.deleteStandardBlock(${b.id})">Excluir</button></div></div>`).join('') : '<div class="empty-state-small">Nenhum bloco encontrado.</div>';
    },

    async deleteStandardBlock(id) {
        const block = this.blocks.find(b => Number(b.id) === Number(id));
        if (!confirm(`Excluir o bloco padrão "${block?.title || id}"?`)) return;
        try { await API.delete(`/api/long-text-blocks/${id}`); this.blocks = this.blocks.filter(b => Number(b.id) !== Number(id)); this.renderBlockLibrary(); }
        catch (e) { UI.showToast(e.message, 'error'); }
    },

    insertBlock(id) {
        const block = this.blocks.find(b => Number(b.id) === Number(id)); if (!block) return;
        let nodes; try { nodes = JSON.parse(block.structure_json || '[]'); } catch (_) { nodes = []; }
        nodes = this.normalizeNodes(nodes).map(n => ({ ...n, id: this.uid() }));
        if (!nodes.length) return UI.showToast('Este bloco está vazio.', 'warning');
        this.syncAllFromDom();
        const placement = document.getElementById('lt-block-placement')?.value || 'end';
        let insertAt = this.nodes.length, baseLevel = 1;
        if (this.selectedIndex != null && this.nodes[this.selectedIndex]?.type === 'topic' && placement !== 'end') {
            const targetLevel = this.nodes[this.selectedIndex].level;
            baseLevel = placement === 'inside' ? Math.min(8, targetLevel + 1) : targetLevel;
            insertAt = placement === 'before' ? this.selectedIndex : (placement === 'inside' ? this.selectedIndex + 1 : this.getBlockEnd(this.selectedIndex));
        }
        const rootLevel = nodes.find(n => n.type === 'topic')?.level || 1;
        nodes.forEach(n => { if (n.type === 'topic') n.level = Math.max(1, Math.min(8, baseLevel + n.level - rootLevel)); });
        this.nodes.splice(insertAt, 0, ...nodes);
        this.mode = this.nodes.some(n => n.type === 'free' && String(n.text || '').trim()) ? 'MIXED' : 'STRUCTURED';
        this.selectedIndex = insertAt;
        this.closeDialog('modal-lt-block-library');
        this.render();
        this.pushHistory(false);
        UI.showToast(`Bloco "${block.title}" inserido. A numeração foi atualizada.`, 'success');
    },

    closeDialog(id) { document.getElementById(id)?.classList.add('hidden'); },

    onDragStart(event, index) {
        if (index == null || index < 0 || index >= this.nodes.length) return;
        this.syncAllFromDom();
        this.dragIndex = index;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(index));
    },

    onDragOver(event) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    },

    onDrop(event, targetIndex) {
        event.preventDefault();
        const start = this.dragIndex != null ? this.dragIndex : Number(event.dataTransfer.getData('text/plain'));
        if (!Number.isInteger(start) || start < 0 || start >= this.nodes.length || targetIndex == null || targetIndex < 0 || targetIndex >= this.nodes.length) return;
        if (start === targetIndex) return;

        this.syncAllFromDom();
        const srcNode = this.nodes[start];
        const count = srcNode && srcNode.type === 'topic' ? (this.getBlockEnd(start) - start) : 1;
        const block = this.nodes.splice(start, count);

        let adjustedTarget = targetIndex;
        if (targetIndex > start) {
            adjustedTarget -= count;
        }

        adjustedTarget = Math.max(0, Math.min(this.nodes.length, adjustedTarget));
        this.nodes.splice(adjustedTarget, 0, ...block);

        this.dragIndex = null;
        this.selectedIndex = adjustedTarget;
        this.render();
        this.pushHistory(false);
        UI.showToast('Linha / bloco reordenado com sucesso!', 'success', 1500);
    }
};
