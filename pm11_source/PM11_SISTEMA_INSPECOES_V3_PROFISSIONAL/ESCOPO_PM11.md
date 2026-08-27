# Escopo consolidado — PM11 V3

## 1. Modelo central

**Projeto → Plano PM11 → Item de Inspeção → Características de Controle**.

- Plano = quando a inspeção ocorre.
- Item = qual equipamento/local gera uma Ordem.
- Características = o que o inspetor verifica ou mede.

## 2. Planos PM11

Código corporativo: `X X X XXX XXX XXX`.

1. Centro produtivo.
2. Processo.
3. Tipo do Plano (`I` para Inspeção).
4. Linha, 3 caracteres.
5. Subárea, 3 caracteres.
6. Sufixo, 3 caracteres.

Linha e Subárea são catálogos dinâmicos: o usuário pode pesquisar e, se o código não existir, criá-lo diretamente no campo.

Periodicidade é temporal (DIA/SMS e catálogo corporativo), com preenchimento derivado de Ciclo, Unidade, Texto de Ciclo e Horizonte de Abertura.

A tela possui CRUD por linha, duplicação, aplicar/salvar modelo, filtros, cores, seleção e edição em massa.

## 3. Itens

Campos principais:

- Equipamento SAP;
- GPM;
- Centro de Trabalho;
- Condição: `Q`, `P`, `M`, `F` (Funcionando);
- Prioridade 0–4;
- Plano de Inspeção;
- Identificador;
- Rota de 4 dígitos;
- Descrição (máx. 35 caracteres);
- `t(min)`;
- Criticidade;
- Status.

O Plano pode ser alterado diretamente na grade por menu pesquisável com pré-visualização, além das ações em massa.

## 4. Características de Controle

### Qualitativa

Avaliação Normal/Anormal. Campos numéricos permanecem vazios.

### Quantitativa

Possui Método, casas decimais, Unidade, Referência, Limite Inferior e Superior.

Métodos e Unidades são pesquisáveis por digitação, com sugestões contextuais e listas flutuantes que não são cortadas pelo modal.

## 5. Bibliotecas

Três níveis formais:

1. **Características** — conjunto de características reutilizáveis.
2. **Item** — item + suas características.
3. **Equipamento/Pacote** — vários itens + todas as características.

A Biblioteca possui abas, filtros, preview hierárquico, CRUD, duplicação, aplicação, status, cores e ações em massa.

## 6. Balanceamento PM11

Variável base: **tempo de inspeção em minutos**.

Objetivo: linearizar a carga diária respeitando periodicidade e sequência de Rota.

Recursos:

- Manual e Automático;
- Book de Ordens;
- clique nas barras para abrir Ordens do Dia;
- arrastar do Book para o dia e entre dias;
- cenário antes de gravar;
- Meta de tempo máximo/dia com linha tracejada;
- destaque dos dias acima da Meta;
- filtros reativos;
- mapa de calor;
- janelas de 30/60/90/180/365/730 dias;
- datas `dd/mm` ou `dd/mm/aaaa`.

## 7. Projetos

A mesma filosofia do PM13:

- criar;
- abrir;
- editar;
- duplicar com dados;
- trancar/destrancar;
- excluir com confirmação.

Projeto trancado é protegido também no backend.

## 8. Importação e Exportação

Fluxo: **Arquivo → Mapeamento → Diagnóstico → Conclusão**.

Reconhecimento por nome da aba + cabeçalhos + conteúdo, com ajuste manual de abas/colunas.

Modos:

- **Adicionar e Unificar (MERGE)** — renumera Identificadores conflitantes e preserva vínculos das Características.
- **Substituir (REPLACE)** — substitui dados importáveis do projeto mediante confirmação.

Projeto Completo XLSX possui abas padronizadas:

- `Cod Planos`;
- `ITENS`;
- `SÍNTESE DE CARACT - INSPEÇÃO`;
- `Balanceamento`.

O fluxo Exportar → Reimportar é testado automaticamente.

## 9. Proteções de XLSX

- leitura streaming;
- detecção de caudas artificiais de fórmulas/formatação;
- limites preventivos para arquivos anormais;
- erro visível em vez de travamento;
- logs de etapa e traceback no servidor.

## 10. UX padrão PM13

Aplicável às telas principais:

- filtros avançados;
- campos e modais com CSS padronizado;
- cabeçalho/ações fixáveis;
- largura ajustável;
- cor de linha e filtro por cor;
- barra contextual após seleção;
- editar/excluir em massa;
- Ctrl+C/V;
- Ctrl+Z/Y;
- Esc;
- feedback visual e histórico.
