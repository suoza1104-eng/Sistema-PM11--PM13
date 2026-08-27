# PM11 V3 Profissional — Planos e Ordens de Inspeção

Sistema local para engenharia, cadastro, padronização e balanceamento de **Planos PM11 e Ordens de Inspeção**, desenvolvido com a mesma linguagem visual e práticas de uso do sistema PM13, porém com regras próprias de inspeção.

## Iniciar

1. Extraia a pasta completa.
2. No Windows, execute `INICIAR_PM11.bat`.
3. Acesse `http://127.0.0.1:8766`.
4. Mantenha a janela do servidor aberta para acompanhar logs e diagnósticos.

O banco local fica em `data/pm11.db`.

## Estrutura funcional

- **Visão Geral** — dashboard do projeto.
- **Planos** — código corporativo estruturado, ciclos temporais, CRUD, filtros, cores, ações em massa e modelos.
- **Itens** — equipamento, GPM, CT, condição Q/P/M/F, prioridade, Plano, Identificador, Rota, descrição, t(min), status e modelos.
- **Características de Controle** — qualitativas/quantitativas, Método, Unidade, casas decimais, referência e limites.
- **Balanceamento** — Manual + Book de Ordens e Automático, por minutos/dia, periodicidade, rota e Meta diária.
- **Biblioteca** — padrões de Características, Itens e Equipamentos/Pacotes.
- **Projetos** — criar, editar, duplicar, trancar/destrancar e excluir.
- **Importar / Exportar** — reconhecimento automático de Planos, Itens e Características, mapeamento manual, diagnóstico, MERGE/REPLACE, Projeto Completo e backup.
- **Configurações** — catálogos e parâmetros do projeto.

## Práticas herdadas do PM13

- mesma identidade visual geral;
- tabelas compactas;
- cabeçalho e ações fixáveis;
- largura de colunas ajustável;
- marcação/colorização e filtro por cor;
- seleção múltipla e barra contextual;
- edição e exclusão em massa;
- Ctrl+C / Ctrl+V quando aplicável;
- Ctrl+Z / Ctrl+Y global;
- Esc para cancelar seleção/cópia;
- bibliotecas/modelos;
- backup, restauração e logs detalhados.

## Planilha PM11

O importador foi testado com `references/Planos Padrão Área1.xlsx` e reconhece as três estruturas principais mesmo com cabeçalhos em linhas diferentes:

- `Cod Planos` → Planos;
- `ITENS` → Itens;
- `SÍNTESE DE CARACT - INSPEÇÃO` → Características.

O usuário pode revisar e corrigir o mapeamento de abas e colunas antes de gravar.

## Catálogos

A pasta `catalogs/` contém os catálogos internos e a pasta `references/` preserva as fontes fornecidas:

- `Planos Padrão Área1.xlsx`;
- `METODOS_UNIDADES.xlsx`.

## Testes

Execute `TESTAR_PM11.bat` para rodar a bateria automatizada.

A validação V3 cobre criação e vínculos, condição F, quantitativa/qualitativa, clonagem, bibliotecas, balanceamento, projetos, round-trip Excel, renumeração no MERGE e reconhecimento da planilha real.

Consulte também:

- `PLANO_IMPLEMENTACAO_PM11_V3.md`
- `VALIDACAO_PM11_V3.md`
