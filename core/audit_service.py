import json
from core.database import get_db_connection

def log_action(project_id, entity_type, entity_id, action, previous_data=None, new_data=None):
    """Logs an administrative or CRUD action into the database audit log.
    previous_data and new_data should be dicts, which are serialized to JSON.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        prev_json = json.dumps(previous_data, ensure_ascii=False) if previous_data is not None else None
        new_json = json.dumps(new_data, ensure_ascii=False) if new_data is not None else None
        from windows_identity import get_identity
        actor = get_identity()
        
        cursor.execute("""
        INSERT INTO audit_log (project_id, entity_type, entity_id, action, previous_data_json, new_data_json,
                               actor_name, actor_account, actor_sid, actor_computer)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (project_id, entity_type, entity_id, action, prev_json, new_json,
              actor['name'], actor['account'], actor['sid'], actor['computer']))
        
        conn.commit()
    except Exception as e:
        # Avoid crashing the application due to audit log failures
        print(f"Erro ao salvar log de auditoria: {e}")
    finally:
        conn.close()
