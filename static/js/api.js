/**
 * Central API client for PM13 local application
 */
window.Logger = {
    log(msg, ctx = 'APP') {
        const text = typeof msg === 'object' ? JSON.stringify(msg) : String(msg);
        console.log(`[LOG] [${ctx}] ${text}`);
        try {
            fetch('/api/logs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, context: ctx })
            }).catch(() => {});
        } catch (e) {}
    }
};

const API = {
    async request(url, options = {}) {
        const timeoutMs = Number(options.timeoutMs || 0);
        delete options.timeoutMs;
        let timeoutId = null;
        let timedOut = false;
        if (timeoutMs > 0 && !options.signal) {
            const controller = new AbortController();
            options.signal = controller.signal;
            timeoutId = setTimeout(() => {
                timedOut = true;
                controller.abort();
            }, timeoutMs);
        }
        const defaultHeaders = {
            'Accept': 'application/json',
        };

        const method = String(options.method || 'GET').toUpperCase();
        if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            const app = window.App;
            const projectId = app?.getValidProjectId?.() || app?.currentProjectId;
            if (Number(projectId) > 0) {
                defaultHeaders['X-PM13-Project-ID'] = String(Number(projectId));
            }
        }

        if (options.body && !(options.body instanceof FormData)) {
            defaultHeaders['Content-Type'] = 'application/json';
            options.body = JSON.stringify(options.body);
        }

        options.headers = {
            ...defaultHeaders,
            ...options.headers
        };

        try {
            const response = await fetch(url, options);
            const isJson = response.headers.get('content-type')?.includes('application/json');
            const data = isJson ? await response.json() : null;

            if (!response.ok) {
                const errorMsg = data?.error || `Erro HTTP: ${response.status}`;
                throw new Error(errorMsg);
            }

            return data;
        } catch (error) {
            console.error(`Falha na requisição para ${url}:`, error);
            if (timedOut || error?.name === 'AbortError') {
                throw new Error('O servidor ultrapassou o tempo limite da operação. O balanceamento foi interrompido; tente novamente com menos varreduras.');
            }
            throw error;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
        }
    },

    async get(url, params = {}) {
        const query = Object.keys(params)
            .filter(k => params[k] !== undefined && params[k] !== null && params[k] !== '')
            .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
            .join('&');
        const fullUrl = query ? `${url}?${query}` : url;
        return this.request(fullUrl, { method: 'GET' });
    },

    async post(url, body = {}, options = {}) {
        return this.request(url, {
            method: 'POST',
            body: body,
            ...options
        });
    },

    async put(url, body = {}) {
        return this.request(url, {
            method: 'PUT',
            body: body
        });
    },

    async delete(url, params = {}) {
        const query = Object.keys(params)
            .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
            .join('&');
        const fullUrl = query ? `${url}?${query}` : url;
        return this.request(fullUrl, { method: 'DELETE' });
    },

    async log(message, context = '') {
        try {
            await this.post('/api/logs', { message: message, context: context });
        } catch (err) {
            console.error("Failed to send frontend log to backend:", err);
        }
    }
};
