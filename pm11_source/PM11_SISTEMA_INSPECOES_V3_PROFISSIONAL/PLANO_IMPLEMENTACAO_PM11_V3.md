# Plano de Implementação — PM11 V3 Profissional

## Objetivo da rodada

Consolidar o PM11 sobre a base visual/operacional já validada no PM13, mantendo o mesmo padrão de navegação e produtividade, mas substituindo a lógica de manutenção/HH por inspeção/periodicidade/rota/tempo.

## Entregas implementadas

### Interface e padrão visual

- modais de Plano, Item e Característica redesenhados;
- filtros, inputs, selects e autocompletes no padrão visual PM13;
- dropdowns flutuantes para evitar corte em Método/Unidade;
- campos de busca e filtros padronizados;
- tabelas com cabeçalho/ações fixáveis, resize, cores e barra contextual.

### Planos

- CRUD por linha;
- duplicar Plano sozinho ou com Itens + Características;
- aplicar modelo/pacote;
- salvar Plano como modelo/pacote;
- editar e excluir em massa;
- cadastro rápido de Linha e Subárea;
- ciclos temporais e código estruturado.

### Itens

- Condição `F — Funcionando`;
- seletor pesquisável de Plano diretamente na grade;
- CRUD, clonagem, modelos, seleção, cores e edição em massa;
- Ctrl+C/Ctrl+V e Esc;
- Rota em 4 dígitos e t(min).

### Características

- quantitativa/qualitativa;
- Método e Unidade por catálogo pesquisável;
- validação de limites;
- CRUD, filtros, cores e edição em massa;
- Ctrl+C/Ctrl+V.

### Biblioteca

- abas Características / Itens / Equipamentos-Pacotes;
- preview da estrutura;
- aplicar, editar, duplicar, excluir, status e cores;
- ações em massa.

### Projetos

- editar;
- duplicar integralmente;
- trancar/destrancar;
- excluir;
- isolamento por `project_id`.

### Importar / Exportar

- wizard em quatro etapas;
- reconhecimento automático e mapeamento manual;
- diagnóstico antes de gravar;
- MERGE com remapeamento de Identificadores;
- REPLACE;
- backup automático antes da importação;
- Projeto Completo XLSX round-trip;
- proteção para planilhas anormalmente grandes/infladas.

### Balanceamento

- Manual + Book de Ordens;
- Automático com comparação Antes × Depois;
- Meta máxima de inspeção por dia;
- linha tracejada e dias excedentes;
- filtros atualizando cenário;
- painel lateral de Ordens;
- arrastar Ordens para dias;
- mapa de calor;
- cálculo por minutos, periodicidade e rota.

## Critérios de aceite executados

1. Plano → Item → Característica criado e relacionado.
2. Condição F aceita e exportável.
3. Qualitativa limpa parâmetros numéricos.
4. Clonagem de Plano com filhos preserva estrutura independente.
5. Modelo de Item e Pacote cria novos registros/vínculos.
6. Balanceamento aceita Meta e filtros.
7. Projeto duplicado mantém dados; projeto trancado bloqueia mutações.
8. Exportar Projeto Completo → reimportar em MERGE renumera conflitos e preserva Características.
9. Planilha padrão real reconhece Planos, Itens e Características.
10. API HTTP validada para CRUD, filtros, exportação, biblioteca, bloqueio e duplicação.

## Próximas evoluções após uso em campo

A V3 foi preparada para refinamento posterior de:

- tolerância/calendário exato de cada periodicidade;
- feriados e dias de trabalho;
- regras avançadas de Rota;
- score adicional de qualidade do Balanceamento;
- mais heurísticas de recomendação de Método/Unidade;
- regras SAP que ainda não foram fornecidas.
