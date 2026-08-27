/**
 * Frontend Technical Classes & Dynamic Dropdown Reordering Engine.
 * Reordena métodos e unidades nos menus suspensos agrupando pela mesma classe técnica.
 */

window.TechnicalClasses = {
  CLASSES: {
    "TEMPERATURA": {
      label: "Temperatura",
      methods: ["PIRÔMETRO", "PIRÔMETRO / CÂMERA TERMOGRÁFICA", "CÂMERA TERMOGRÁFICA", "TERMÔMETRO", "TERMÔMETRO INFRAVERMELHO", "TERMOGRA", "TERMOGRAFIA", "TERMO", "TERM", "PIROM"],
      units: ["°C", "°F", "K", "C", "F"]
    },
    "VIBRACAO": {
      label: "Vibração / Alinhamento",
      methods: ["CANETVIB", "CANETAVIB", "COLETOR DE VIBRAÇÃO", "COLETVIB", "ACELERÔMETRO", "VELOCÍMETRO DE VIBRAÇÃO", "CANETA DE VIBRAÇÃO", "ANALISADOR DE VIBRAÇÃO", "VIBRAÇÃO", "VIBR", "VIB", "CANETA"],
      units: ["MM/S", "G", "µM", "UM", "MM/S RMS", "MM/S2", "M/S2"]
    },
    "ELETRICA": {
      label: "Grandezas Elétricas",
      methods: ["ALICATE AMPERÍMETRO", "AMPERÍMETRO", "AMPER", "MULTÍMETRO", "MULTIM", "MEGÔMETRO", "MEGOM", "TERRÔMETRO", "OSCILOSCÓPIO", "ANALISADOR DE ENERGIA", "VOLTÍMETRO"],
      units: ["A", "MA", "V", "KV", "MV", "W", "KW", "MW", "MΩ", "KΩ", "Ω", "OHM", "HZ", "PF"]
    },
    "PRESSAO": {
      label: "Pressão / Vácuo",
      methods: ["MANÔMETRO", "MANOM", "TRANSDUTOR DE PRESSÃO", "PRESSOSTATO", "PRESSÃO", "VACUÔMETRO"],
      units: ["BAR", "PSI", "KGF/CM²", "KGF/CM2", "KPA", "MPA", "PA", "MMHG", "MCA"]
    },
    "LUBRIFICACAO": {
      label: "Lubrificação & Análise de Óleo",
      methods: ["ANÁLISE DE ÓLEO", "VISCOSÍMETRO", "VISCOS", "CONTAGEM DE PARTÍCULAS", "TETRAESTANHO", "ÓLEO"],
      units: ["CST", "PPM", "NAS", "ISO4406", "ISO 4406", "%", "MG KOH/G"]
    },
    "ESPESSURA": {
      label: "Ultrassom & Espessura",
      methods: ["MEDIDOR DE ESPESSURA", "MEDESP", "ULTRASSOM", "ULTRAS", "PAQUÍMETRO", "PAQUIM", "MICROMETRO", "MICROM"],
      units: ["MM", "UM", "µM", "CM", "M", "INCH", "POL"]
    },
    "ROTACAO": {
      label: "Rotação",
      methods: ["TACÔMETRO", "TACOM", "STROBOSCÓPIO", "INDICADOR DE ROTAÇÃO", "ROTAÇÃO"],
      units: ["RPM", "M/MIN", "M/S", "HZ", "RAD/S"]
    },
    "GASES": {
      label: "Análise de Gases / O2",
      methods: ["ANALISADOR DE GASES", "MONITOR DE O2", "DETECTOR DE GASES", "GASES", "GÁS"],
      units: ["% O2", "%O2", "% CO", "PPM", "LEL", "% VOL", "VOL%"]
    }
  },

  getMethodClass(method) {
    if (!method) return null;
    const clean = method.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    for (const [key, info] of Object.entries(this.CLASSES)) {
      if (info.methods.some(m => {
        const sm = m.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        return sm.includes(clean) || clean.includes(sm);
      })) {
        return key;
      }
    }
    return null;
  },

  getUnitClass(unit) {
    if (!unit) return null;
    const clean = unit.trim().toUpperCase();
    for (const [key, info] of Object.entries(this.CLASSES)) {
      if (info.units.some(u => u.toUpperCase() === clean)) {
        return key;
      }
    }
    return null;
  },

  checkCompatibility(method, unit) {
    if (!method || !unit) return { compatible: true };
    const mClass = this.getMethodClass(method);
    const uClass = this.getUnitClass(unit);
    const cleanU = unit.trim().toUpperCase();

    if (mClass) {
      const info = this.CLASSES[mClass];
      if (!info.units.some(u => u.toUpperCase() === cleanU)) {
        return {
          compatible: false,
          warning: `Incompatibilidade Técnica: Método '${method}' (Classe ${info.label}) não aceita a Unidade '${unit}'.`
        };
      }
    }

    if (uClass) {
      const info = this.CLASSES[uClass];
      const cleanM = method.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      if (!info.methods.some(m => {
        const sm = m.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        return sm.includes(cleanM) || cleanM.includes(sm);
      })) {
        return {
          compatible: false,
          warning: `Incompatibilidade Técnica: Unidade '${unit}' (Classe ${info.label}) não combina com o Método '${method}'.`
        };
      }
    }

    if (mClass && uClass && mClass !== uClass) {
      return {
        compatible: false,
        warning: `Incompatibilidade Técnica: Método '${method}' (${this.CLASSES[mClass].label}) não combina com Unidade '${unit}' (${this.CLASSES[uClass].label}).`
      };
    }
    return { compatible: true };
  },

  sortDropdownOptions(options, selectedValue, currentClassKey) {
    if (!currentClassKey || !this.CLASSES[currentClassKey]) return options;
    const info = this.CLASSES[currentClassKey];
    const preferred = [];
    const others = [];

    options.forEach(opt => {
      const val = (opt.value || opt).toUpperCase();
      const isPreferred = info.methods.some(m => m.toUpperCase().includes(val) || val.includes(m.toUpperCase())) ||
                          info.units.some(u => u.toUpperCase() === val);
      if (isPreferred) preferred.push(opt);
      else others.push(opt);
    });

    return [
      { header: `⭐ Recomendados (${info.label})`, items: preferred },
      { header: `Outras Opções`, items: others }
    ];
  }
};

