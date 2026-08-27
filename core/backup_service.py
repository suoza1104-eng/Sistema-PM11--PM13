import os
import sqlite3
import datetime
import zipfile
import json
import shutil
from core.migrations import run_migrations

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'pm13.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

def get_projects_summary():
    """Gets a list of projects and counts for metadata inclusion."""
    if not os.path.exists(DB_PATH):
        return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, current_counter FROM projects WHERE deleted_at IS NULL;")
        projects = cursor.fetchall()
        summary = []
        for p in projects:
            cursor.execute("SELECT COUNT(*) FROM plans WHERE project_id = ? AND deleted_at IS NULL;", (p['id'],))
            plans_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM maintenance_items WHERE project_id = ? AND deleted_at IS NULL;", (p['id'],))
            items_count = cursor.fetchone()[0]
            summary.append({
                'id': p['id'],
                'name': p['name'],
                'current_counter': p['current_counter'],
                'plans_count': plans_count,
                'items_count': items_count
            })
        return summary
    except Exception:
        return []
    finally:
        conn.close()

def create_backup(name_suffix=None):
    """Creates a zip backup containing the sqlite database and projects metadata."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = f"_{name_suffix}" if name_suffix else ""
    backup_filename = f"pm13_backup_{timestamp}{suffix}.zip"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    # 1. Create a safe temporary copy of the DB using SQLite's online backup API
    temp_db_path = os.path.join(BACKUP_DIR, f"temp_{timestamp}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(temp_db_path)
    try:
        src.backup(dst)
        # A restored backup may come from an older schema.  Upgrade it before
        # the application serves another request so deleted plan codes remain
        # reusable and all current invariants are present immediately.
        run_migrations(dst)
    finally:
        src.close()
        dst.close()
        
    # 2. Get projects summary metadata
    proj_summary = get_projects_summary()
    metadata = {
        'version': '1.0.0',
        'date': datetime.datetime.now().isoformat(),
        'database_size_bytes': os.path.getsize(temp_db_path) if os.path.exists(temp_db_path) else 0,
        'projects': proj_summary,
        'description': f"Backup PM13 criado em {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    }
    
    temp_meta_path = os.path.join(BACKUP_DIR, f"metadata_{timestamp}.json")
    with open(temp_meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    # 3. Create zip file
    pm11_db_path = os.path.join(BASE_DIR, 'data', 'pm11.db')
    temp_pm11_db_path = None
    if os.path.exists(pm11_db_path):
        temp_pm11_db_path = os.path.join(BACKUP_DIR, f"temp_pm11_{timestamp}.db")
        try:
            src_pm11 = sqlite3.connect(pm11_db_path)
            dst_pm11 = sqlite3.connect(temp_pm11_db_path)
            src_pm11.backup(dst_pm11)
            src_pm11.close()
            dst_pm11.close()
        except Exception:
            temp_pm11_db_path = None

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(temp_db_path, 'pm13.db')
        if temp_pm11_db_path and os.path.exists(temp_pm11_db_path):
            z.write(temp_pm11_db_path, 'pm11.db')
        z.write(temp_meta_path, 'metadata.json')
        
    # 4. Clean up temporary files
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
    if temp_pm11_db_path and os.path.exists(temp_pm11_db_path):
        os.remove(temp_pm11_db_path)
    if os.path.exists(temp_meta_path):
        os.remove(temp_meta_path)
        
    return {
        'filename': backup_filename,
        'path': backup_path,
        'size_bytes': os.path.getsize(backup_path),
        'metadata': metadata
    }

def restore_backup(backup_filename):
    """Restores database from a zip backup file."""
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Arquivo de backup não encontrado: {backup_filename}")
        
    # 1. Unzip to temporary files
    temp_extract_dir = os.path.join(BACKUP_DIR, 'temp_restore')
    os.makedirs(temp_extract_dir, exist_ok=True)
    
    with zipfile.ZipFile(backup_path, 'r') as z:
        z.extractall(temp_extract_dir)
        
    extracted_db = os.path.join(temp_extract_dir, 'pm13.db')
    if not os.path.exists(extracted_db):
        shutil.rmtree(temp_extract_dir)
        raise ValueError("Backup inválido: arquivo pm13.db não encontrado dentro do zip.")
        
    # 2. Safely restore SQLite using native backup API from extracted db to main db
    # Ensure active main database directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    src = sqlite3.connect(extracted_db)
    dst = None
    try:
        # Backups may have been created by an older application build. Upgrade
        # the extracted copy first so an incomplete/invalid migration can never
        # replace the live database and leave new features without their tables.
        from core.migrations import run_migrations
        run_migrations(src)
        dst = sqlite3.connect(DB_PATH)
        src.backup(dst)
    finally:
        src.close()
        if dst is not None:
            dst.close()
        
    # 3. Clean extraction directory
    shutil.rmtree(temp_extract_dir)
    return True

def list_backups():
    """Lists all available backups and parses their metadata.json."""
    if not os.path.exists(BACKUP_DIR):
        return []
        
    backups = []
    for file in os.listdir(BACKUP_DIR):
        if file.endswith('.zip') and file.startswith('pm13_backup_'):
            full_path = os.path.join(BACKUP_DIR, file)
            size = os.path.getsize(full_path)
            
            # Extract metadata from zip without full extraction
            metadata = {}
            try:
                with zipfile.ZipFile(full_path, 'r') as z:
                    if 'metadata.json' in z.namelist():
                        meta_bytes = z.read('metadata.json')
                        metadata = json.loads(meta_bytes.decode('utf-8'))
            except Exception:
                pass
                
            # Date can be extracted from filename or metadata
            created_at = None
            if 'date' in metadata:
                created_at = metadata['date']
            else:
                # Fallback to file modified time
                mtime = os.path.getmtime(full_path)
                created_at = datetime.datetime.fromtimestamp(mtime).isoformat()
                
            backups.append({
                'filename': file,
                'size_bytes': size,
                'created_at': created_at,
                'metadata': metadata
            })
            
    # Sort backups by creation date descending
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return backups

def delete_backup(backup_filename):
    """Deletes a backup file."""
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    if os.path.exists(backup_path):
        os.remove(backup_path)
        return True
    return False

def get_latest_pre_balance_backup(project_id):
    """Finds the most recent backup created before auto-balancing for a specific project."""
    backups = list_backups()
    target_suffix = f"auto_before_balance_proj_{project_id}"
    for b in backups:
        if target_suffix in b['filename']:
            return b['filename']
    return None
