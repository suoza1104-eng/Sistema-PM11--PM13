# Plano de Implementação — Novo Modelo de Balanceamento PM11, Offset nos Planos e Data Inicial

Reestruturar o algoritmo de balanceamento automático e a estrutura de dados do **PM11 (Sistema de Inspeções)**. No novo modelo, o balanceamento **reassocia itens entre planos** da mesma família/ciclo e o gráfico exibe os dias úteis (Segunda a Sexta/Sábado), com campo de **Offset**, **Dia da Semana** e **Data Inicial (Start)** calculados no plano de inspeção com base na **Data de Início da Programação**, e **eliminação da coluna Contador**.

---

## 📸 Referência do Modelo (SAP PM11)

No modelo do cliente (`media_1787686761080.png`), os planos de inspeção podem conter códigos de frequência na descrição ou no código do plano:
- `1S2`: Semana 1 — 2º dia de trabalho (Terça-feira)
- `1S3`: Semana 1 — 3º dia de trabalho (Quarta-feira)
- `2S2`: Semana 2 — 2º dia de trabalho (Terça-feira da 2ª semana)
- `4S5`: Semana 4 — 5º dia de trabalho (Sexta-feira da 4ª semana)

> [!IMPORTANT]
> **Ajustes Solicitados:**
> 1. **Data de Início no Topo da Tela de Planos:** Campo de data (`balance_anchor_date` / Data de Início da Programação) no cabeçalho da página de Planos PM11.
> 2. **Cálculo da Data Inicial (`Data Start`) de Cada Plano:**
>    - Para cada plano: $\text{Data Start} = \text{Data de Início} + (\text{Offset} - 1) \text{ dias}$.
>    - Exibida em nova coluna na tabela de planos (ex: `16/09/2026`).
>    - Ao alterar a Data de Início no topo ou o Offset do plano, a Data Inicial é recalculada em tempo real!
> 3. **Eliminação da Coluna Contador:** A coluna `counter` / `Contador` será removida da interface do PM11.
> 4. **Detecção Opcional do Offset:**
>    - Quando os códigos (`1S1`, `1S2`, etc.) estiverem no texto/código do plano, o sistema preenche o **Offset** automaticamente.
>    - Quando não estiverem presentes, o campo **Offset** permanece **vazio (nulo)**.

---

## 🎯 Regras Principais do Novo Modelo

1. **Movimentação de Itens entre Planos:**
   - O balanceamento automático **moverá `item.plan_id` de um plano para outro**.
   - **Restrição Estrita:** Um item só pode ser movido para outro plano se o destino possuir exatamente o **Mesmo Ciclo (`cycle_value` + `unit`)** E o **Mesmo Texto Ciclo / Família de Plano (`text_cycle`)**.
   - Se não houver planos de destino disponíveis na mesma família/ciclo, o sistema gera um alerta/falha informativa.

2. **Novos Campos e Visualização na Tela de Planos:**
   - **Data de Início no Topo (`balance_anchor_date`):** Data base configurável do projeto.
   - **`offset_days` (INTEGER, opcional/editável):** Posição de início do plano no ciclo (ex: `1` = 1ª Segunda, `2` = 1ª Terça...).
   - **`day_of_week` (TEXT, calculado / não-editável):** Exibição dinâmica do dia da semana (ex: *"1ª Terça-feira (1S2)"*).
   - **`start_date` / `Data Inicial` (TEXT, calculado / não-editável):** Data exata da primeira execução do plano (ex: `16/09/2026`).

3. **Gráfico e Calendário de Balanceamento:**
   - Gráfico de cargas organizado em colunas de **Segunda a Sexta** (ou Segunda a Sábado se configurado), repetindo o ciclo de semanas ($1S, 2S, 3S, 4S$).

---

## 📐 Proposta de Alterações

---

### [Componente 1] Detecção de Padrões & Banco de Dados (`core_pm11/`)

#### [MODIFY] [migrations.py](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/migrations.py)
- Adicionar coluna `offset_days INTEGER DEFAULT NULL` na tabela `inspection_plans`.
- Adicionar coluna `balance_anchor_date TEXT` na tabela `projects` (se não existir).
- Script de migração automática no SQLite.

#### [NEW] [plans_util.py](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/plans_util.py)
- Função `parse_offset_from_text(description, code)`: Extrai automaticamente a semana/dia de `1S1`, `1S2`, etc.
- Função `get_plan_dates_and_labels(anchor_date_str, offset_days)`:
  - Retorna `day_of_week_label` (ex: `"1ª Terça-feira (1S2)"`).
  - Retorna `calculated_start_date` formatada (ex: `"16/09/2026"`).

---

### [Componente 2] Algoritmo de Balanceamento (`core_pm11/balance.py`)

#### [MODIFY] [balance.py](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/balance.py)
- Usar `balance_anchor_date` como marco zero do calendário de simulação.
- **Reassociação de Planos:** Testar a mudança de `item.plan_id` entre os planos elegíveis da mesma família com `offset_days` configurados.
- **Gráfico de Dias Úteis:** Agrupar cargas exclusivamente por dias úteis de Segunda a Sexta.

---

### [Componente 3] API & Importação (`core_pm11/handler.py` & `xlsx_io.py`)

#### [MODIFY] [handler.py](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/handler.py)
- Adicionar endpoint `POST /api/pm11/projects/:id/anchor-date` para salvar a Data de Início no topo da tela de Planos.
- Retornar os campos calculados `day_of_week_label` e `calculated_start_date` em todas as consultas de planos.

#### [MODIFY] [xlsx_io.py](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/xlsx_io.py)
- Extrair o offset automaticamente ao importar planilhas Excel.
- Remover tratamento da coluna `counter`.

---

### [Componente 4] Interface do Usuário (`static/js/pm11/`)

#### [MODIFY] [plans.js](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/js/pm11/plans.js)
- **Painel Superior:** Inserir o campo de data **`Data de Início da Programação`** no topo da tela de Planos.
- **Tabela de Planos:**
  - Remover a coluna **Contador**.
  - Adicionar a coluna **Offset** (editável / numérico / aceita vazio).
  - Adicionar a coluna **Dia da Semana** (não-editável).
  - Adicionar a coluna **Data Inicial** (não-editável, ex: `16/09/2026`).
- **Recálculo em Tempo Real:** Ao alterar a Data de Início no topo ou o Offset de qualquer plano, recalcular instantaneamente as datas iniciais de todos os planos exibidos na tabela.

#### [MODIFY] [balance.js](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/js/pm11/balance.js)
- Sincronizar a Data de Início com o gráfico de simulação diária (Segunda a Sexta).
- Exibir relatório das trocas de planos efetuadas pelo balanceamento.

---

## 🧪 Plano de Verificação

### Testes Automatizados
- Executar script de teste Python `tests/test_pm11_offset_dates.py`:
  - Testar o cálculo de `Data Start = Data de Início + (Offset - 1) dias`.
  - Testar persistência do endpoint `anchor-date`.
  - Confirmar a ausência da coluna `counter`.

### Verificação Manual
1. Abrir a tela de **Planos de Inspeção (PM11)** e selecionar a Data de Início no topo (ex: `01/09/2026`).
2. Verificar se a coluna **Data Inicial** de um plano com Offset `1` exibe `01/09/2026` e para um plano com Offset `3` exibe `03/09/2026`.
3. Alterar o Offset de um plano na tabela e confirmar a atualização instantânea da **Data Inicial** e do **Dia da Semana**.
4. Executar o **Balanceamento Automático** e verificar a distribuição das cargas de Segunda a Sexta.

