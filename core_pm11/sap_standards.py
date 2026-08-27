"""
Tabela de referência padrão SAP para elaboração de planos de manutenção (PM11 / PM13).
Contém a lista de frequências válidas, horizontes de abertura e a função geradora do N.PONTO (Hash 13 caracteres).
"""
import datetime

SAP_CYCLE_TABLE = [
    {"code": "01D", "cycle_value": 1,   "unit": "DIA", "text_cycle": "DIÁRIA",         "interval": 1,   "unid_solic": "SMS", "horiz_insp": 100, "horiz_period": 100},
    {"code": "02D", "cycle_value": 2,   "unit": "DIA", "text_cycle": "DOIS DIAS",      "interval": 1,   "unid_solic": "SMS", "horiz_insp": 100, "horiz_period": 100},
    {"code": "03D", "cycle_value": 3,   "unit": "DIA", "text_cycle": "3 DIAS",         "interval": 1,   "unid_solic": "SMS", "horiz_insp": 100, "horiz_period": 100},
    {"code": "01S", "cycle_value": 1,   "unit": "SMS", "text_cycle": "1 SEMANA",       "interval": 1,   "unid_solic": "SMS", "horiz_insp": 100, "horiz_period": 100},
    {"code": "02S", "cycle_value": 2,   "unit": "SMS", "text_cycle": "DUAS SEMANAS",   "interval": 2,   "unid_solic": "SMS", "horiz_insp": 50,  "horiz_period": 100},
    {"code": "03S", "cycle_value": 3,   "unit": "SMS", "text_cycle": "3 SEMANAS",      "interval": 3,   "unid_solic": "SMS", "horiz_insp": 65,  "horiz_period": 35},
    {"code": "01M", "cycle_value": 4,   "unit": "SMS", "text_cycle": "4 SEMANAS = 1M", "interval": 4,   "unid_solic": "SMS", "horiz_insp": 80,  "horiz_period": 50},
    {"code": "06S", "cycle_value": 6,   "unit": "SMS", "text_cycle": "6 SEMANAS",      "interval": 6,   "unid_solic": "SMS", "horiz_insp": 83,  "horiz_period": 65},
    {"code": "02M", "cycle_value": 9,   "unit": "SMS", "text_cycle": "9 SEMANAS = 2M", "interval": 9,   "unid_solic": "SMS", "horiz_insp": 89,  "horiz_period": 65},
    {"code": "03M", "cycle_value": 13,  "unit": "SMS", "text_cycle": "TRIMESTRAL = 3M","interval": 13,  "unid_solic": "SMS", "horiz_insp": 92,  "horiz_period": 75},
    {"code": "04M", "cycle_value": 17,  "unit": "SMS", "text_cycle": "17 SEMANAS = 4M","interval": 17,  "unid_solic": "SMS", "horiz_insp": 94,  "horiz_period": 80},
    {"code": "06M", "cycle_value": 26,  "unit": "SMS", "text_cycle": "SEMESTRAL = 26S","interval": 26,  "unid_solic": "SMS", "horiz_insp": 96,  "horiz_period": 85},
    {"code": "09M", "cycle_value": 39,  "unit": "SMS", "text_cycle": "9 MESES = 39S",  "interval": 39,  "unid_solic": "SMS", "horiz_insp": 97,  "horiz_period": 90},
    {"code": "01A", "cycle_value": 52,  "unit": "SMS", "text_cycle": "ANUAL",          "interval": 52,  "unid_solic": "SMS", "horiz_insp": 98,  "horiz_period": 90},
    {"code": "18M", "cycle_value": 78,  "unit": "SMS", "text_cycle": "18 MESES = 78S", "interval": 78,  "unid_solic": "SMS", "horiz_insp": 99,  "horiz_period": 95},
    {"code": "02A", "cycle_value": 104, "unit": "SMS", "text_cycle": "2 ANOS",         "interval": 104, "unid_solic": "SMS", "horiz_insp": 99,  "horiz_period": 95},
    {"code": "03A", "cycle_value": 156, "unit": "SMS", "text_cycle": "3 ANOS",         "interval": 156, "unid_solic": "SMS", "horiz_insp": 99,  "horiz_period": 97},
    {"code": "04A", "cycle_value": 208, "unit": "SMS", "text_cycle": "4 ANOS",         "interval": 208, "unid_solic": "SMS", "horiz_insp": 99,  "horiz_period": 98},
]

# Conjunto de textos de ciclo válidos para comparação rápida
VALID_CYCLE_TEXTS = {item["text_cycle"].upper(): item for item in SAP_CYCLE_TABLE}

def is_valid_cycle_text(text):
    if not text:
        return False
    return text.strip().upper() in VALID_CYCLE_TEXTS

def get_sap_cycle_info(text):
    if not text:
        return None
    return VALID_CYCLE_TEXTS.get(text.strip().upper())

def generate_nponto_hash(project_id=None, item_id=None, sequence_idx=1, dt=None, equipment_code=None, export_seed=None):
    """
    Gera o código único N.PONTO de exatamente 13 caracteres.
    Formato:
    - 6 dígitos de data: DDMMAA (ex: 260826)
    - 5 dígitos do segundo do dia: 00000 a 86399 (ex: 39505)
    - 2 caracteres alfanuméricos em Base36: 00 a ZZ (ex: 0A, 1F, ZZ)
    Exemplo resultante: 260826395050A (Total 13 caracteres).
    """
    import random
    if dt is None:
        dt = datetime.datetime.now()
    if export_seed is None:
        export_seed = random.randint(0, 1295)

    ddmmaa = dt.strftime("%d%m%y")  # 6 dígitos (ex: 260826)
    seconds_of_day = dt.hour * 3600 + dt.minute * 60 + dt.second  # 0 a 86399 (5 dígitos)
    sec_str = f"{seconds_of_day:05d}"

    chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    num = (export_seed + int(sequence_idx or 1) - 1) % 1296
    b36_str = chars[num // 36] + chars[num % 36]  # 00 a ZZ

    return f"{ddmmaa}{sec_str}{b36_str}"
