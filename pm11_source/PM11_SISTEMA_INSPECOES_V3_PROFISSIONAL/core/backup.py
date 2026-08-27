import os, json, zipfile, datetime, shutil
from .database import DB_PATH, get_conn
BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR=os.path.join(BASE_DIR,'backups')

def create_backup(label='manual'):
    os.makedirs(BACKUP_DIR,exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S');name=f'pm11_backup_{stamp}_{label}.zip';path=os.path.join(BACKUP_DIR,name)
    c=get_conn();projects=[dict(r) for r in c.execute('SELECT id,name FROM projects ORDER BY id').fetchall()];c.close()
    meta={'version':'1.0.0','date':datetime.datetime.now().isoformat(),'description':'Backup PM11','projects':projects}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        if os.path.exists(DB_PATH):z.write(DB_PATH,'pm11.db')
        z.writestr('metadata.json',json.dumps(meta,ensure_ascii=False,indent=2))
    return path

def restore_backup(zip_path):
    import tempfile, sqlite3
    create_backup('auto_before_restore')
    with zipfile.ZipFile(zip_path,'r') as z:
        if 'pm11.db' not in z.namelist():
            raise ValueError('Backup inválido: pm11.db não encontrado.')
        data=z.read('pm11.db')
        fd,tmp=tempfile.mkstemp(prefix='pm11_restore_',suffix='.db');os.close(fd);open(tmp,'wb').write(data)
        try:
            con=sqlite3.connect(tmp);con.execute('PRAGMA integrity_check').fetchone();con.close()
            shutil.copy2(tmp,DB_PATH)
        finally:
            try:os.remove(tmp)
            except:pass
    return True
