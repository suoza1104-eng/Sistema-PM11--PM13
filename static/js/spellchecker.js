/**
 * SpellChecker.js - Módulo Avançado e Preciso de Revisão Ortográfica e Acentuação.
 * Sem falsos positivos em palavras válidas ou já acentuadas.
 */

window.SpellChecker = {
    // Dicionário estrito de termos sem acento -> com acento (focado em manutenção e português)
    dictionary: {
        'manutencao': 'manutenção',
        'manutencoes': 'manutenções',
        'eletrica': 'elétrica',
        'eletrico': 'elétrico',
        'eletricos': 'elétricos',
        'eletricas': 'elétricas',
        'mecanica': 'mecânica',
        'mecanico': 'mecânico',
        'mecanicos': 'mecânicos',
        'mecanicas': 'mecânicas',
        'inspecao': 'inspeção',
        'inspecoes': 'inspeções',
        'verificacao': 'verificação',
        'verificacoes': 'verificações',
        'lubrificacao': 'lubrificação',
        'lubrificacoes': 'lubrificações',
        'substituicao': 'substituição',
        'substituicoes': 'substituições',
        'tubulacao': 'tubulação',
        'tubulacoes': 'tubulações',
        'calibracao': 'calibração',
        'calibracoes': 'calibrações',
        'orientacao': 'orientação',
        'orientacoes': 'orientações',
        'seguranca': 'segurança',
        'fixacao': 'fixação',
        'fixacoes': 'fixações',
        'pressao': 'pressão',
        'pressoes': 'pressões',
        'protecao': 'proteção',
        'protecoes': 'proteções',
        'valvula': 'válvula',
        'valvulas': 'válvulas',
        'oleo': 'óleo',
        'oleos': 'óleos',
        'saida': 'saída',
        'saidas': 'saídas',
        'nivel': 'nível',
        'niveis': 'níveis',
        'periodico': 'periódico',
        'periodica': 'periódica',
        'periodicos': 'periódicos',
        'periodicas': 'periódicas',
        'critico': 'crítico',
        'critica': 'crítica',
        'maximo': 'máximo',
        'maxima': 'máxima',
        'minimo': 'mínimo',
        'minima': 'mínima',
        'revisao': 'revisão',
        'revisoes': 'revisões',
        'instalacao': 'instalação',
        'instalacoes': 'instalações',
        'operacao': 'operação',
        'operacoes': 'operações',
        'especificacao': 'especificação',
        'especificacoes': 'especificações',
        'especifico': 'específico',
        'especifica': 'específica',
        'especificos': 'específicos',
        'especificas': 'específicas',
        'padrao': 'padrão',
        'padroes': 'padrões',
        'tecnico': 'técnico',
        'tecnica': 'técnica',
        'tecnicos': 'técnicos',
        'tecnicas': 'técnicas',
        'necessario': 'necessário',
        'necessaria': 'necessária',
        'necessarios': 'necessários',
        'necessarias': 'necessárias',
        'posicao': 'posição',
        'posicoes': 'posições',
        'atencao': 'atenção',
        'situacao': 'situação',
        'situacoes': 'situações',
        'tensao': 'tensão',
        'tensoes': 'tensões',
        'frequencia': 'frequência',
        'frequencias': 'frequências',
        'potencia': 'potência',
        'vibracao': 'vibração',
        'vibracoes': 'vibrações',
        'fusivel': 'fusível',
        'fusiveis': 'fusíveis',
        'rele': 'relé',
        'area': 'área',
        'areas': 'áreas',
        'modulo': 'módulo',
        'modulos': 'módulos',
        'numero': 'número',
        'numeros': 'números',
        'codigo': 'código',
        'codigos': 'códigos',
        'catalogo': 'catálogo',
        'catalogos': 'catálogos',
        'tambem': 'também',
        'alem': 'além',
        'apos': 'após',
        'ate': 'até',
        'ja': 'já',
        'nao': 'não',
        'sao': 'são',
        'estao': 'estão',
        'serao': 'serão',
        'deverao': 'deverão',
        'ira': 'irá',
        'irao': 'irão',
        'ultimo': 'último',
        'ultima': 'última',
        'vasamento': 'vazamento',
        'regulajem': 'regulagem'
    },

    /**
     * Tenta encontrar uma sugestão estrita para a palavra.
     * NUNCA substitui palavras válidas ou já acentuadas.
     */
    findSuggestion(word) {
        if (!word || word.length < 2) return null;

        // Regra 1: Se a palavra já possui acentuação correta (á, é, í, ó, ú, â, ê, ô, ã, õ, ç), NUNCA ALTERA!
        if (/[áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]/.test(word)) {
            return null;
        }

        // Regra 2: Se for número ou contiver dígitos (ex: NR10, 4º, P10, 1.1), ignora
        if (/\d/.test(word)) return null;

        const lower = word.toLowerCase();

        // 1. Busca direta de palavra sem acento no dicionário
        if (this.dictionary[lower]) {
            return this.dictionary[lower];
        }

        // 2. Normalização de vogais/consoantes repetidas em excesso (ex: MANUTECAOOO -> manutecao)
        const deRepeated = lower.replace(/(.)\1{2,}/g, '$1');
        if (this.dictionary[deRepeated]) {
            return this.dictionary[deRepeated];
        }

        // 3. Padrões específicos de erros de digitação em sufixos (-cao, -caoo, -caooo)
        const stemMatches = [
            { pattern: /^manut/i, replacement: 'manutenção' },
            { regex: /^inspec(a|ao)+$/i, replacement: 'inspeção' },
            { regex: /^verificac(a|ao)+$/i, replacement: 'verificação' },
            { regex: /^lubrificac(a|ao)+$/i, replacement: 'lubrificação' },
            { regex: /^substituic(a|ao)+$/i, replacement: 'substituição' },
            { regex: /^operac(a|ao)+$/i, replacement: 'operação' },
            { regex: /^especificac(a|ao)+$/i, replacement: 'especificação' },
            { regex: /^protec(a|ao)+$/i, replacement: 'proteção' },
            { regex: /^fixac(a|ao)+$/i, replacement: 'fixação' },
            { regex: /^calibrac(a|ao)+$/i, replacement: 'calibração' },
            { regex: /^orientac(a|ao)+$/i, replacement: 'orientação' },
            { regex: /^situac(a|ao)+$/i, replacement: 'situação' }
        ];

        for (const item of stemMatches) {
            if (item.pattern && item.pattern.test(lower)) return item.replacement;
            if (item.regex && item.regex.test(lower)) return item.replacement;
        }

        return null;
    },

    /**
     * Analisa o texto e retorna as sugestões de correção ortográfica/acentuação.
     * @param {string} text 
     * @returns {Object} { hasSuggestions, originalText, correctedText, changesCount, diffList }
     */
    analyze(text) {
        if (!text || typeof text !== 'string') {
            return { hasSuggestions: false, originalText: text || '', correctedText: text || '', changesCount: 0, diffList: [] };
        }

        let corrected = text;
        const diffList = [];

        // 1. Limpeza de espaços duplos e pontuação espaçada (ex: "palavra ,outra" -> "palavra, outra")
        const spacingFixes = [
            { regex: /[ \t]{2,}/g, replace: ' ', label: 'Espaços duplos removidos' },
            { regex: / \s*([,.:;!?])/g, replace: '$1', label: 'Espaço antes de pontuação' },
            { regex: /([,.:;!?])([A-Za-zÀ-ÿ])/g, replace: '$1 $2', label: 'Espaço após pontuação' }
        ];

        spacingFixes.forEach(fix => {
            if (fix.regex.test(corrected)) {
                corrected = corrected.replace(fix.regex, fix.replace);
            }
        });

        // 2. Correção Estrita de Palavras e Acentuações (Sem falsos positivos)
        const wordRegex = /\b[A-Za-zÀ-ÿ0-9_-]+\b/g;
        const matches = [...text.matchAll(wordRegex)];

        matches.forEach(match => {
            const word = match[0];
            const replacement = this.findSuggestion(word);

            if (replacement && replacement.toLowerCase() !== word.toLowerCase()) {
                let formattedReplacement = replacement;

                // Mantém caixa Alta total (ex: MANUTECAOOO -> MANUTENÇÃO)
                if (word === word.toUpperCase() && word.length > 1) {
                    formattedReplacement = replacement.toUpperCase();
                } 
                // Mantém Primeira maiúscula (ex: Manutecaooo -> Manutenção)
                else if (word[0] === word[0].toUpperCase() && word[0] !== word[0].toLowerCase()) {
                    formattedReplacement = replacement.charAt(0).toUpperCase() + replacement.slice(1).toLowerCase();
                } else {
                    formattedReplacement = replacement.toLowerCase();
                }

                if (word !== formattedReplacement) {
                    diffList.push({
                        original: word,
                        suggested: formattedReplacement,
                        index: match.index
                    });
                }
            }
        });

        // Substituição das palavras no texto final (de trás para frente)
        let finalCorrectedText = text;

        diffList.sort((a, b) => b.index - a.index).forEach(diff => {
            finalCorrectedText = finalCorrectedText.substring(0, diff.index) + 
                                diff.suggested + 
                                finalCorrectedText.substring(diff.index + diff.original.length);
        });

        // Aplica ajustes de pontuação no texto final
        spacingFixes.forEach(fix => {
            finalCorrectedText = finalCorrectedText.replace(fix.regex, fix.replace);
        });

        const hasSuggestions = diffList.length > 0 || finalCorrectedText !== text;

        return {
            hasSuggestions,
            originalText: text,
            correctedText: finalCorrectedText,
            changesCount: diffList.length,
            diffList
        };
    },

    /**
     * Retorna o texto corrigido diretamente.
     * @param {string} text 
     * @returns {string}
     */
    autoCorrect(text) {
        return this.analyze(text).correctedText;
    }
};
