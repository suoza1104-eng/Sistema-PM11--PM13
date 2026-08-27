"""
Módulo de Classes de Compatibilidade Técnica entre Métodos de Inspeção e Unidades de Medida.
Permite agrupar grandezas físicas, reordenar menus suspensos inteligentes e detectar incompatibilidades físicas.
"""

import re
import unicodedata

TECHNICAL_CLASSES = {
    "TEMPERATURA": {
        "label": "Temperatura",
        "methods": ["PIROMETRO", "PIROMETRO / CAMERA TERMOGRAFICA", "CAMERA TERMOGRAFICA", "TERMOMETRO", "TERMOMETRO INFRAVERMELHO", "TERMOMETRO DE CONTATO", "TERMOGRA", "TERMOGRAFIA", "TERMO", "TERM", "PIROM"],
        "units": ["°C", "°F", "K", "C", "F"]
    },
    "VIBRACAO": {
        "label": "Vibração / Alinhamento",
        "methods": ["CANETVIB", "CANETAVIB", "CANETA DE VIBRACAO", "COLETOR DE VIBRACAO", "COLETVIB", "ACELEROMETRO", "VELOCIMETRO DE VIBRACAO", "ANALISADOR DE VIBRACAO", "VIBRACAO", "VIBR", "VIB", "CANETA"],
        "units": ["MM/S", "G", "µM", "UM", "MM/S RMS", "MM/S2", "M/S2"]
    },
    "ELETRICA": {
        "label": "Grandezas Elétricas",
        "methods": ["ALICATE AMPERIMETRO", "AMPERIMETRO", "AMPER", "MULTIMETRO", "MULTIM", "MEGOMETRO", "MEGOM", "TERROMETRO", "OSCILOSCOPIO", "ANALISADOR DE ENERGIA", "VOLTIMETRO"],
        "units": ["A", "MA", "V", "KV", "MV", "W", "KW", "MW", "MΩ", "KΩ", "Ω", "OHM", "HZ", "PF"]
    },
    "PRESSAO": {
        "label": "Pressão / Vácuo",
        "methods": ["MANOMETRO", "MANOM", "TRANSDUTOR DE PRESSAO", "PRESSOSTATO", "PRESSAO", "VACUOMETRO"],
        "units": ["BAR", "PSI", "KGF/CM2", "KGF/CM²", "KPA", "MPA", "PA", "MMHG", "MCA"]
    },
    "LUBRIFICACAO": {
        "label": "Lubrificação & Análise de Óleo",
        "methods": ["ANALISE DE OLEO", "VISCOSIMETRO", "VISCOS", "CONTAGEM DE PARTICULAS", "TETRAESTANHO", "OLEO"],
        "units": ["CST", "PPM", "NAS", "ISO4406", "ISO 4406", "%", "MG KOH/G"]
    },
    "ESPESSURA": {
        "label": "Ultrassom & Medição de Espessura",
        "methods": ["MEDIDOR DE ESPESSURA", "MEDESP", "ULTRASSOM", "ULTRAS", "PAQUIMETRO", "PAQUIM", "MICROMETRO", "MICROM"],
        "units": ["MM", "UM", "µM", "CM", "M", "INCH", "POL"]
    },
    "ROTACAO": {
        "label": "Rotação / Velocidade Linear",
        "methods": ["TACOMETRO", "TACOM", "STROBOSCOPIO", "INDICADOR DE ROTACAO", "ROTACAO"],
        "units": ["RPM", "M/MIN", "M/S", "HZ", "RAD/S"]
    },
    "GASES": {
        "label": "Análise de Gases / O2",
        "methods": ["ANALISADOR DE GASES", "MONITOR DE O2", "DETECTOR DE GASES", "GASES", "GAS"],
        "units": ["% O2", "%O2", "% CO", "PPM", "LEL", "% VOL", "VOL%"]
    }
}


def sanitize_code(text):
    """
    Sanitiza um código para o PM11/SAP:
    - Remove acentos e Ç -> C
    - Remove caracteres especiais
    - Substitui espaços por underline ou elimina
    """
    if not text:
        return ""
    text = unicodedata.normalize('NFD', str(text)).encode('ascii', 'ignore').decode('utf-8')
    text = text.upper().replace('Ç', 'C')
    text = re.sub(r'[^A-Z0-9_-]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    return text


def get_method_technical_class(method_code_or_desc):
    """Retorna o nome da classe técnica correspondente ao Método."""
    if not method_code_or_desc:
        return None
    clean = sanitize_code(method_code_or_desc)
    for class_key, info in TECHNICAL_CLASSES.items():
        for m in info["methods"]:
            sm = sanitize_code(m)
            if sm in clean or clean in sm:
                return class_key
    return None


def get_unit_technical_class(unit_code_or_desc):
    """Retorna o nome da classe técnica correspondente à Unidade de Medida."""
    if not unit_code_or_desc:
        return None
    clean = str(unit_code_or_desc).strip().upper()
    for class_key, info in TECHNICAL_CLASSES.items():
        for u in info["units"]:
            if u.upper() == clean:
                return class_key
    return None


def check_technical_class_compatibility(method, unit):
    """
    Verifica se o Método e a Unidade de Medida pertencem à mesma classe técnica.
    Retorna (is_compatible, method_class, unit_class, warning_message)
    """
    if not method or not unit:
        return True, None, None, None

    m_class = get_method_technical_class(method)
    u_class = get_unit_technical_class(unit)
    clean_u = str(unit).strip().upper()

    if m_class:
        info = TECHNICAL_CLASSES[m_class]
        if not any(u.upper() == clean_u for u in info['units']):
            msg = f"Incompatibilidade Técnica: Método '{method}' (Classe {info['label']}) não aceita a Unidade '{unit}'."
            return False, m_class, u_class, msg

    if u_class:
        info = TECHNICAL_CLASSES[u_class]
        clean_m = sanitize_code(method)
        if not any(sanitize_code(m) in clean_m or clean_m in sanitize_code(m) for m in info['methods']):
            msg = f"Incompatibilidade Técnica: Unidade '{unit}' (Classe {info['label']}) não combina com o Método '{method}'."
            return False, m_class, u_class, msg

    if m_class and u_class and m_class != u_class:
        msg = f"Incompatibilidade Técnica: Método '{method}' ({TECHNICAL_CLASSES[m_class]['label']}) não combina com Unidade '{unit}' ({TECHNICAL_CLASSES[u_class]['label']})."
        return False, m_class, u_class, msg

    return True, m_class, u_class, None

