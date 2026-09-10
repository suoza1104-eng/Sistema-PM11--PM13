"""The same 1..20 stop catalog offered by Settings, only for empty catalogs."""
def ensure_default_cycles(conn, project_id):
    if conn.execute('SELECT 1 FROM cycle_catalog WHERE project_id=? LIMIT 1', (project_id,)).fetchone():
        return
    conn.executemany(
        'INSERT INTO cycle_catalog(project_id,cycle,unit,cycle_text,opening_horizon,active) VALUES(?,?,?,?,?,1)',
        [(project_id, n, 'PRD', 'PARADA' if n == 1 else f'{n} PARADAS', 100) for n in range(1, 21)])
