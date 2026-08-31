window.PM11 = window.PM11 || {};

window.PM11.UI = {
  showLoader(t = 'Processando...') {
    const elText = document.querySelector('#loader-text');
    if (elText) elText.textContent = t;
    document.querySelector('#loader')?.classList.remove('hidden');
  },

  hideLoader() {
    document.querySelector('#loader')?.classList.add('hidden');
  },

  toast(msg, type = 'ok') {
    const w = document.querySelector('#toast-container') || document.querySelector('#toast-wrap');
    if (!w) return;
    const e = document.createElement('div');
    e.className = 'toast ' + (type === 'error' ? 'error' : type === 'warn' ? 'warn' : '');
    e.textContent = msg;
    w.appendChild(e);
    setTimeout(() => e.remove(), 4200);
  },

  download(url) {
    if (!url) return;
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  },

  esc(s) {
    return String(s ?? '').replace(/[&<>'"]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[m]));
  },

  pageHead(title, subtitle = '', actions = '') {
    return `<div class="section-header-actions">
      <div>
        <h1>${this.esc(title)}</h1>
        ${subtitle ? `<p class="subtitle">${this.esc(subtitle)}</p>` : ''}
      </div>
      <div class="actions-group">
        ${actions}
      </div>
    </div>`;
  },

  filterCard(fieldsHtml, actionsHtml = '', id = 'filters-card') {
    return `<div class="card filter-card" id="${id}">
      <div class="filter-header" onclick="this.parentElement.classList.toggle('collapsed')">
        <span class="filter-title">
          <svg viewBox="0 0 24 24"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>
          Filtros de Pesquisa
        </span>
        <span class="chevron-icon">▼</span>
      </div>
      <div class="filter-body">
        <div class="filters-grid">
          ${fieldsHtml}
        </div>
        ${actionsHtml ? `<div class="filters-actions">${actionsHtml}</div>` : ''}
      </div>
    </div>`;
  },

  tableCard(titleOrCount, toolsHtml, tableHtml) {
    return `<div class="card table-card">
      <div class="table-toolbar">
        <span class="table-results-count">${this.esc(String(titleOrCount))}</span>
        <div class="actions-group">
          ${toolsHtml}
        </div>
      </div>
      <div class="table-responsive-container">
        ${tableHtml}
      </div>
    </div>`;
  },

  selectionBar(id, count, buttonsHtml) {
    return `<div class="selection-bar ${count ? '' : 'hidden'}" id="${id}">
      <strong>${count} selecionado(s)</strong>
      <div class="actions-group">${buttonsHtml}</div>
    </div>`;
  },

  modal(title, html, { subtitle = '', wide = false, saveText = 'Salvar', cancelText = 'Cancelar', onSave = null, onOpen = null, hideSave = false } = {}) {
    let bd = document.querySelector('#modal-backdrop');
    let m = document.querySelector('#modal');

    if (!bd || !m) {
      const wrap = document.createElement('div');
      wrap.innerHTML = `
        <div id="modal-backdrop" class="modal-overlay hidden" style="position:fixed;top:0;bottom:0;left:0;right:0;background:rgba(15,23,42,0.5);backdrop-filter:blur(2px);z-index:2000;display:flex;align-items:center;justify-content:center;">
          <div id="modal" class="modal modal-md" style="background:#fff;border-radius:10px;box-shadow:0 20px 40px rgba(0,0,0,0.25);width:min(92vw, 680px);max-height:90vh;display:flex;flex-direction:column;overflow:hidden;">
            <div class="modal-header" style="padding:16px 20px;border-bottom:1px solid var(--border-color);display:flex;justify-content:space-between;align-items:center;">
              <div>
                <h2 id="modal-title" style="font-size:16px;font-weight:700;margin:0;"></h2>
                <p id="modal-subtitle" class="subtitle" style="margin:2px 0 0;font-size:12px;color:var(--text-muted);"></p>
              </div>
              <button class="modal-close btn-icon" id="modal-close" style="border:none;background:none;font-size:20px;cursor:pointer;color:var(--text-muted);">✕</button>
            </div>
            <div class="modal-body" id="modal-body" style="padding:20px;overflow-y:auto;flex:1;"></div>
            <div class="modal-footer" id="modal-actions" style="padding:12px 20px;border-top:1px solid var(--border-color);background:#FAFCFA;display:flex;justify-content:flex-end;gap:10px;"></div>
          </div>
        </div>
      `;
      document.body.appendChild(wrap.firstElementChild);
      bd = document.querySelector('#modal-backdrop');
      m = document.querySelector('#modal');
    }

    if (m) {
      m.style.width = wide ? 'min(94vw, 920px)' : 'min(92vw, 680px)';
    }

    const t = document.querySelector('#modal-title');
    const sub = document.querySelector('#modal-subtitle');
    const body = document.querySelector('#modal-body');
    const act = document.querySelector('#modal-actions');

    if (t) t.textContent = title;
    if (sub) sub.textContent = subtitle;
    if (body) body.innerHTML = html;
    if (act) act.innerHTML = `<button class="btn btn-outline" id="m-cancel">${cancelText}</button>${hideSave ? '' : `<button class="btn btn-primary" id="m-save">${saveText}</button>`}`;
    
    bd.classList.remove('hidden');
    bd.style.display = 'flex';

    const close = () => {
      this.closeFloating();
      bd.classList.add('hidden');
      bd.style.display = 'none';
    };

    const cancelBtn = document.querySelector('#m-cancel');
    if (cancelBtn) cancelBtn.onclick = close;
    const closeBtn = document.querySelector('#modal-close');
    if (closeBtn) closeBtn.onclick = close;

    const saveBtn = document.querySelector('#m-save');
    if (saveBtn) {
      saveBtn.onclick = async (e) => {
        const b = e.currentTarget;
        try {
          b.disabled = true;
          const ok = await onSave?.();
          if (ok !== false) close();
        } catch (err) {
          this.toast(err.message, 'error');
        } finally {
          b.disabled = false;
        }
      };
    }

    if (onOpen) onOpen(body);
    return close;
  },

  closeModal() {
    this.closeFloating();
    const bd = document.querySelector('#modal-backdrop');
    if (bd) {
      bd.classList.add('hidden');
      bd.style.display = 'none';
    }
  },

  formData(root = document) {
    const d = {};
    root.querySelectorAll('[name]').forEach(el => {
      d[el.name] = el.type === 'checkbox' ? el.checked : el.value;
    });
    return d;
  },

  selectOptions(rows, value = 'id', label = 'name', selected = '') {
    return `<option value="">— selecione —</option>` + (rows || []).map(r => `<option value="${this.esc(r[value])}" ${String(r[value]) === String(selected) ? 'selected' : ''}>${this.esc(typeof label === 'function' ? label(r) : r[label])}</option>`).join('');
  },

  badgeStatus(s) {
    return `<span class="badge ${s === 'ACTIVE' ? 'green' : 'gray'}">${s === 'ACTIVE' ? 'ATIVO' : 'INATIVO'}</span>`;
  },

  fmtMin(m) {
    m = Number(m || 0);
    const h = Math.floor(m / 60),
      mi = Math.round(m % 60);
    return h ? `${h}h${String(mi).padStart(2, '0')}` : `${mi} min`;
  },

  fmtDate(s, year = false) {
    if (!s) return '';
    const [y, m, d] = String(s).slice(0, 10).split('-');
    return year ? `${d}/${m}/${y}` : `${d}/${m}`;
  },

  tableEmpty(cols, msg = 'Nenhum registro encontrado.') {
    return `<tr class="empty-row"><td colspan="${cols}" class="empty-table-cell">${this.esc(msg)}</td></tr>`;
  },

  colorSelect(selected = '') {
    const colors = [['', 'Sem cor'], ['yellow', 'Amarelo'], ['green', 'Verde'], ['blue', 'Azul'], ['red', 'Vermelho'], ['purple', 'Roxo']];
    return colors.map(([v, n]) => `<option value="${v}" ${v === selected ? 'selected' : ''}>${n}</option>`).join('');
  },

  tableTools(prefix) {
    return `<div class="actions-group">
      <button class="btn btn-sm btn-outline" data-tool="head" data-prefix="${prefix}">📌 Cabeçalho</button>
      <button class="btn btn-sm btn-outline" data-tool="actions" data-prefix="${prefix}">📌 Ações</button>
      <button class="btn btn-sm btn-outline" data-tool="fit" data-prefix="${prefix}">↔ Ajustar colunas</button>
    </div>`;
  },

  bindTableTools(tableId) {
    const t = document.querySelector('#' + tableId);
    if (!t) return;
    const prefix = tableId.replace('-table', '');
    const card = t.closest('.table-card');
    const wrap = t.closest('.table-responsive-container');

    document.querySelectorAll(`[data-prefix="${prefix}"]`).forEach(b => {
      const tool = b.dataset.tool;
      if (tool === 'head') {
        const isSticky = t.classList.contains('sticky-head');
        b.classList.toggle('active', isSticky);
        if (card) card.classList.toggle('card-sticky-active', isSticky);
        if (wrap) wrap.classList.toggle('wrap-sticky-active', isSticky);
      }
      if (tool === 'actions') b.classList.toggle('active', t.classList.contains('sticky-actions'));
      if (tool === 'fit') b.classList.toggle('active', t.classList.contains('compact-cols'));

      b.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (tool === 'head') {
          const isSticky = t.classList.toggle('sticky-head');
          b.classList.toggle('active', isSticky);
          if (card) card.classList.toggle('card-sticky-active', isSticky);
          if (wrap) wrap.classList.toggle('wrap-sticky-active', isSticky);
        }
        if (tool === 'actions') {
          const isSticky = t.classList.toggle('sticky-actions');
          b.classList.toggle('active', isSticky);
        }
        if (tool === 'fit') {
          const isFit = t.classList.toggle('compact-cols');
          b.classList.toggle('active', isFit);
        }
      };
    });
  },

  rowClass(color, selected = false, copied = false) {
    return `${color ? `row-color-${color}` : ''} ${selected ? 'row-selected' : ''} ${copied ? 'row-copied' : ''}`;
  },

  closeFloating() {
    if (this._floatingListeners) {
      document.removeEventListener('pointerdown', this._floatingListeners.onOutsideClick, true);
      document.removeEventListener('keydown', this._floatingListeners.onKeydown, true);
      this._floatingListeners = null;
    }
    document.querySelectorAll('.floating-picker').forEach(x => x.remove());
  },

  floatingPicker(anchor, { rows = [], valueKey = 'id', primary = r => r.name || r.description || r.code, secondary = r => '', searchPlaceholder = 'Pesquisar...', onSelect = () => {}, allowCreate = null, minWidth = 360 } = {}) {
    this.closeFloating();
    const box = document.createElement('div');
    box.className = 'floating-picker';
    box.innerHTML = `<div class="floating-search-wrap">🔎 <input class="floating-search control" placeholder="${this.esc(searchPlaceholder)}"></div><div class="floating-list"></div>`;
    document.body.appendChild(box);
    const input = box.querySelector('input'),
      list = box.querySelector('.floating-list');

    const onOutsideClick = (e) => {
      if (!box.contains(e.target) && !anchor.contains(e.target)) {
        this.closeFloating();
      }
    };

    const onKeydown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        this.closeFloating();
      }
    };

    this._floatingListeners = { onOutsideClick, onKeydown };
    setTimeout(() => {
      document.addEventListener('pointerdown', onOutsideClick, true);
      document.addEventListener('keydown', onKeydown, true);
    }, 10);

    const position = () => {
      const r = anchor.getBoundingClientRect(),
        h = Math.min(360, window.innerHeight * .48);
      box.style.minWidth = Math.max(minWidth, r.width) + 'px';
      box.style.left = Math.min(r.left, window.innerWidth - box.offsetWidth - 12) + 'px';
      const down = window.innerHeight - r.bottom > Math.min(h, 240);
      box.style.top = (down ? r.bottom + 6 : Math.max(8, r.top - h - 6)) + 'px';
      box.style.maxHeight = h + 'px';
    };
    const draw = () => {
      const q = input.value.trim().toLowerCase();
      const filtered = rows.filter(r => (primary(r) + ' ' + secondary(r)).toLowerCase().includes(q)).slice(0, 80);
      list.innerHTML = filtered.map(r => `<button class="floating-option" data-v="${this.esc(r[valueKey])}"><b>${this.esc(primary(r))}</b><span>${this.esc(secondary(r))}</span></button>`).join('') + (allowCreate && q && !filtered.some(r => String(r[valueKey]).toLowerCase() === q) ? `<button class="floating-option create-option" data-create="1"><b>+ Criar “${this.esc(input.value.trim().toUpperCase())}”</b><span>Pressione Enter ou clique para cadastrar e selecionar</span></button>` : '');
      list.querySelectorAll('[data-v]').forEach((b, i) => b.onclick = () => {
        onSelect(filtered[i]);
        this.closeFloating();
      });
      list.querySelector('[data-create]')?.addEventListener('click', async () => {
        const x = await allowCreate(input.value.trim().toUpperCase());
        if (x) {
          onSelect(x);
          this.closeFloating();
        }
      });
    };
    input.oninput = draw;
    input.onkeydown = async e => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        e.preventDefault();
        this.closeFloating();
        return;
      }
      if (e.key === 'Enter' && allowCreate) {
        e.preventDefault();
        const exact = rows.find(r => String(r[valueKey]).toLowerCase() === input.value.trim().toLowerCase());
        if (exact) {
          onSelect(exact);
          this.closeFloating();
        } else {
          const x = await allowCreate(input.value.trim().toUpperCase());
          if (x) {
            onSelect(x);
            this.closeFloating();
          }
        }
      }
    };
    window.addEventListener('resize', position, { once: true });
    position();
    draw();
    setTimeout(() => input.focus(), 0);
  },

  input(label, name, value = '', extra = '') {
    return `<div class="form-group"><label>${label}</label><input class="control" name="${name}" value="${this.esc(value)}" ${extra}></div>`;
  },

  makeSearchableSelect(selectEl) {
    if (!selectEl || selectEl.dataset.searchableEnhanced === 'true') return;
    selectEl.dataset.searchableEnhanced = 'true';

    // Hide native select visually
    selectEl.style.display = 'none';

    const wrapper = document.createElement('div');
    wrapper.className = 'searchable-select-wrapper';
    selectEl.parentNode.insertBefore(wrapper, selectEl);
    wrapper.appendChild(selectEl);

    const trigger = document.createElement('div');
    trigger.className = 'searchable-select-trigger';
    trigger.tabIndex = 0;
    trigger.innerHTML = `<span class="searchable-select-label"></span><span class="searchable-select-arrow">▼</span>`;
    wrapper.appendChild(trigger);

    const dropdown = document.createElement('div');
    dropdown.className = 'searchable-select-dropdown hidden';
    dropdown.innerHTML = `
      <div class="searchable-select-search-box">
        <input type="text" class="searchable-select-input" placeholder="🔍 Digite para buscar...">
      </div>
      <div class="searchable-select-options"></div>
    `;
    wrapper.appendChild(dropdown);

    const labelEl = trigger.querySelector('.searchable-select-label');
    const inputEl = dropdown.querySelector('.searchable-select-input');
    const optionsContainer = dropdown.querySelector('.searchable-select-options');

    const norm = str => String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

    const updateTriggerLabel = () => {
      const selectedOpt = selectEl.options[selectEl.selectedIndex];
      labelEl.textContent = selectedOpt ? selectedOpt.textContent : (selectEl.options[0]?.textContent || '');
    };

    const renderOptions = (filterQuery = '') => {
      const q = norm(filterQuery);
      const opts = Array.from(selectEl.options);
      optionsContainer.innerHTML = '';
      let matchCount = 0;

      opts.forEach(opt => {
        const text = opt.textContent || opt.innerText || '';
        const val = opt.value;
        const matches = !q || norm(text).includes(q) || norm(val).includes(q);

        if (matches) {
          matchCount++;
          const optDiv = document.createElement('div');
          const isSelected = opt.selected || String(val) === String(selectEl.value);
          optDiv.className = `searchable-select-option ${isSelected ? 'selected' : ''}`;
          optDiv.textContent = text;
          optDiv.dataset.value = val;
          optDiv.onclick = (e) => {
            e.stopPropagation();
            selectEl.value = val;
            selectEl.dispatchEvent(new Event('change', { bubbles: true }));
            updateTriggerLabel();
            closeDropdown();
          };
          optionsContainer.appendChild(optDiv);
        }
      });

      if (matchCount === 0) {
        optionsContainer.innerHTML = `<div class="searchable-select-no-results">Nenhum resultado encontrado</div>`;
      }
    };

    const openDropdown = () => {
      document.querySelectorAll('.searchable-select-wrapper.open').forEach(w => {
        if (w !== wrapper) {
          w.classList.remove('open');
          w.querySelector('.searchable-select-dropdown')?.classList.add('hidden');
        }
      });
      wrapper.classList.add('open');
      dropdown.classList.remove('hidden');
      inputEl.value = '';
      renderOptions('');
      setTimeout(() => inputEl.focus(), 30);
    };

    const closeDropdown = () => {
      wrapper.classList.remove('open');
      dropdown.classList.add('hidden');
    };

    trigger.onclick = (e) => {
      e.stopPropagation();
      if (wrapper.classList.contains('open')) {
        closeDropdown();
      } else {
        openDropdown();
      }
    };

    inputEl.onclick = (e) => e.stopPropagation();
    inputEl.oninput = (e) => {
      renderOptions(e.target.value);
    };

    inputEl.onkeydown = (e) => {
      if (e.key === 'Escape') {
        closeDropdown();
      }
    };

    if (!window._searchableSelectGlobalClickListener) {
      window._searchableSelectGlobalClickListener = true;
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.searchable-select-wrapper')) {
          document.querySelectorAll('.searchable-select-wrapper.open').forEach(w => {
            w.classList.remove('open');
            w.querySelector('.searchable-select-dropdown')?.classList.add('hidden');
          });
        }
      });
    }

    const observer = new MutationObserver(() => {
      updateTriggerLabel();
      if (wrapper.classList.contains('open')) {
        renderOptions(inputEl.value);
      }
    });
    observer.observe(selectEl, { childList: true, subtree: true, attributes: true });

    selectEl.addEventListener('change', () => {
      updateTriggerLabel();
    });

    updateTriggerLabel();
  },

  enhanceSelects(parentEl) {
    const root = parentEl || document;
    root.querySelectorAll('select.control, .filters-grid select, .filter-card select, .form-group select').forEach(sel => {
      this.makeSearchableSelect(sel);
    });
  }
};
