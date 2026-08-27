window.Auth = {
  state: 'pending',
  user: null,
  AUTH_UI_PREVIEW: false,

  async init() {
    this.bindEvents();
    if (this.AUTH_UI_PREVIEW) {
      console.warn('Auth em modo AUTH_UI_PREVIEW: exibindo tela de login para visualização.');
      this.showLogin();
      return;
    }
    await this.checkSession();
  },

  async checkSession() {
    try {
      const res = await fetch('/api/auth/me', { credentials: 'same-origin' });
      if (res.ok) {
        const data = await res.json();
        if (data && data.user) {
          this.user = data.user;
          this.showApplication(data.user);
          return true;
        }
      }
    } catch (e) {
      console.warn('Não foi possível validar a sessão no servidor:', e);
    }
    this.showLogin();
    return false;
  },

  async login(loginStr, passwordStr, rememberBool) {
    this.showError('');
    this.setLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ login: loginStr, password: passwordStr, remember: rememberBool })
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.user) {
        this.user = data.user;
        this.showApplication(data.user);
        return true;
      } else {
        const msg = data.error || 'Usuário ou senha inválidos.';
        this.showError(msg);
        return false;
      }
    } catch (e) {
      this.showError('Servidor indisponível ou falha de conexão.');
      return false;
    } finally {
      this.setLoading(false);
    }
  },

  async logout() {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch (e) {}
    this.user = null;
    this.showLogin('Sessão encerrada com sucesso.');
  },

  showLogin(message = '') {
    this.state = 'login';
    const loginView = document.querySelector('#login-view');
    const appShell = document.querySelector('#app-shell');
    if (loginView) loginView.classList.remove('hidden');
    if (appShell) appShell.classList.add('hidden');
    document.body.classList.add('auth-pending');
    document.body.classList.remove('auth-authenticated');

    if (message) {
      this.showError(message, false);
    } else {
      this.showError('');
    }
  },

  showApplication(user) {
    this.state = 'authenticated';
    this.user = user;
    const loginView = document.querySelector('#login-view');
    const appShell = document.querySelector('#app-shell');
    if (loginView) loginView.classList.add('hidden');
    if (appShell) appShell.classList.remove('hidden');
    document.body.classList.remove('auth-pending');
    document.body.classList.add('auth-authenticated');

    this.updateUserHeader(user);

    // Boot PM13 and PM11 applications
    if (window.App && typeof window.App.route === 'function') {
      window.App.route();
    }
    if (window.PM11 && window.PM11.App && typeof window.PM11.App.init === 'function') {
      window.PM11.App.init();
    }
  },

  setLoading(isLoading) {
    const btn = document.querySelector('#login-submit');
    const txt = document.querySelector('#login-submit-text');
    const spin = document.querySelector('#login-submit-spinner');
    const inputLogin = document.querySelector('#login-username');
    const inputPwd = document.querySelector('#login-password');

    if (btn) btn.disabled = isLoading;
    if (inputLogin) inputLogin.disabled = isLoading;
    if (inputPwd) inputPwd.disabled = isLoading;

    if (txt) txt.textContent = isLoading ? 'Entrando...' : 'Entrar';
    if (spin) spin.classList.toggle('hidden', !isLoading);
  },

  showError(message, isError = true) {
    const box = document.querySelector('#login-alert');
    const text = document.querySelector('#login-alert-text');
    if (!box || !text) return;
    if (!message) {
      box.classList.add('hidden');
      text.textContent = '';
      return;
    }
    text.textContent = message;
    box.classList.remove('hidden');
    box.style.color = isError ? 'var(--login-danger)' : '#15803D';
    box.style.background = isError ? 'var(--login-danger-bg)' : '#F0FDF4';
    box.style.borderColor = isError ? 'var(--login-danger-border)' : '#BBF7D0';
  },

  updateUserHeader(user) {
    let wrap = document.querySelector('#user-header-wrap');
    if (!wrap) {
      const targetGroup = document.querySelector('.header-right') || document.querySelector('.actions-group');
      if (targetGroup) {
        wrap = document.createElement('div');
        wrap.id = 'user-header-wrap';
        wrap.className = 'topbar-user-badge';
        targetGroup.prepend(wrap);
      }
    }
    if (wrap && user) {
      wrap.innerHTML = `
        <span>👤 <b>${this.esc(user.name || user.login)}</b></span>
        <button class="btn-logout" id="btn-user-logout" title="Encerrar sessão">Sair</button>
      `;
      const btnLogout = wrap.querySelector('#btn-user-logout');
      if (btnLogout) btnLogout.onclick = () => this.logout();
    }
  },

  esc(s) {
    return String(s ?? '').replace(/[&<>'"]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[m]));
  },

  bindEvents() {
    const form = document.querySelector('#login-form');
    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const loginEl = document.querySelector('#login-username');
        const pwdEl = document.querySelector('#login-password');
        const remEl = document.querySelector('#login-remember');

        const u = (loginEl?.value || '').trim();
        const p = pwdEl?.value || '';
        const r = !!remEl?.checked;

        if (!u) {
          this.showError('Por favor, informe seu usuário ou e-mail.');
          loginEl?.focus();
          return;
        }
        if (!p) {
          this.showError('Por favor, informe sua senha.');
          pwdEl?.focus();
          return;
        }
        await this.login(u, p, r);
      };
    }

    // Toggle Password Visibility
    const pwdToggle = document.querySelector('#login-pwd-toggle');
    const pwdInput = document.querySelector('#login-password');
    if (pwdToggle && pwdInput) {
      pwdToggle.onclick = () => {
        const isPwd = pwdInput.type === 'password';
        pwdInput.type = isPwd ? 'text' : 'password';
        pwdToggle.textContent = isPwd ? '🔒' : '👁️';
        pwdToggle.setAttribute('aria-label', isPwd ? 'Ocultar senha' : 'Mostrar senha');
      };
    }

    // Clear error alert on input typing
    const inputs = document.querySelectorAll('#login-username, #login-password');
    inputs.forEach(input => {
      input.addEventListener('input', () => this.showError(''));
    });

    // Detect Caps Lock
    if (pwdInput) {
      const capsWarning = document.querySelector('#login-caps-warning');
      const checkCaps = (e) => {
        if (e.getModifierState && capsWarning) {
          const isCaps = e.getModifierState('CapsLock');
          capsWarning.classList.toggle('hidden', !isCaps);
        }
      };
      pwdInput.addEventListener('keydown', checkCaps);
      pwdInput.addEventListener('keyup', checkCaps);
    }

    // Forgot password orientation click
    const forgotLink = document.querySelector('#login-forgot-link');
    if (forgotLink) {
      forgotLink.onclick = (e) => {
        e.preventDefault();
        alert('Entre em contato com a equipe de suporte TI / Manutenção da sua unidade para redefinir sua senha.');
      };
    }
  }
};

// Initialize Auth when DOM is loaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => window.Auth.init(), { once: true });
} else {
  window.Auth.init();
}

