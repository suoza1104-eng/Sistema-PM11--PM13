window.PM11 = window.PM11 || {};

window.PM11.API = {
    async request(url, opt = {}) {
        let reqUrl = url;
        if (reqUrl.startsWith('/api/') && !reqUrl.startsWith('/api/pm11/')) {
            reqUrl = '/api/pm11/' + reqUrl.substring(5);
        }
        const o = { ...opt };
        if (o.body && typeof o.body === 'object' && !(o.body instanceof FormData)) {
            o.headers = { ...(o.headers || {}), 'Content-Type': 'application/json' };
            o.body = JSON.stringify(o.body);
        }
        o.headers = { Accept: 'application/json', ...(o.headers || {}) };
        const pid = window.PM11?.App?.projectId;
        if (pid) o.headers['X-PM11-Project-ID'] = String(pid);
        
        const r = await fetch(reqUrl, o);
        const ct = r.headers.get('content-type') || '';
        const data = ct.includes('json') ? await r.json() : await r.blob();
        if (!r.ok) throw new Error(data?.error || `Erro HTTP ${r.status}`);
        return data;
    },
    get(u, p = {}) {
        const q = new URLSearchParams(Object.entries(p).filter(([, v]) => v !== '' && v !== null && v !== undefined));
        return this.request(u + (q.toString() ? `?${q}` : ''));
    },
    post(u, b) {
        return this.request(u, { method: 'POST', body: b });
    },
    put(u, b) {
        return this.request(u, { method: 'PUT', body: b });
    },
    delete(u, p = {}) {
        const q = new URLSearchParams(p);
        return this.request(u + (q.toString() ? `?${q}` : ''), { method: 'DELETE' });
    }
};
