# Plano de Implementação — Sistema Avançado de Detecção de Falhas, Validações e Alertas em Tempo Real (PM11 & PM13)

Documento oficial de planejamento técnico para a implementação da detecção de falhas, validações de consistência técnica e destaques visuais em **amarelo** e **vermelho** nos módulos **PM11** e **PM13**.

---

## 🎯 Objetivos Principais

1. **Leitura Tolerante com Diagnóstico Visual:** Permitir a importação de planilhas com erros, identificando e circulando em **amarelo** (avisos/sugestões) e **vermelho** (erros impeditivos / incompatibilidades).
2. **Validação em 3 Camadas:**
   - **Camada 1 (Diagnóstico de Upload):** Validação durante a leitura do arquivo Excel.
   - **Camada 2 (Pós-Carregamento / Banco de Dados):** Atualização do `validation_status` e resumo de inconsistências (`validation_issues_json`) nas tabelas.
   - **Camada 3 (Tempo Real na Edição Inline):** Sinalização imediata de borda/fundo na célula editada e reordenação de dropdowns por classe técnica.
3. **Aprimoramento sem Substituição:** Manter e evoluir o sistema de marcação e alertas já existente no PM13, estendendo-o em nível equivalente para o PM11.

---

## 📋 Detalhamento das 9 Regras de Validação Técnica

### 1. Validação de Catálogos Oficiais
- Todos os campos vinculados a catálogos (`Método`, `Unidade de Medida`, `Ciclo SAP`, `Centro de Trabalho`, `GPM`) devem corresponder rigorosamente às listas oficiais.
- **Ação:** Divergências geram aviso com borda/fundo **vermelho** na célula e aviso de compatibilidade.

---

### 2. Integridade de Vínculos e Unicidade de IDs
- **Unicidade:** O campo `ID / Identificador` na aba/tabela **ITENS** não pode ter duplicatas (deve ser estritamente único por projeto).
- **Integridade de Vínculo:** Todos os registros da aba **CARACTERÍSTICAS / OPERAÇÕES** devem apontar para um `ID de Item` existente na aba **ITENS**.

---

### 3. Regras de Consistência das Características (Quantitativo vs Qualitativo)
1. **Hierarquia e Desigualdade Estrita de Limites:**
   $$\text{Limite Inferior} < \text{Valor Teórico} < \text{Limite Superior}$$
   - Se $\text{Limite Inferior} \ge \text{Valor Teórico}$ ou $\text{Valor Teórico} \ge \text{Limite Superior}$, gera **ERRO CRÍTICO (Vermelho)**.
2. **Casas Decimais:** Padronizadas estritamente em **2 casas decimais** para características numéricas.
3. **Diferenciação por Tipo (`QUANTIT` vs `QUALITAT`):**
   - **Quantitativo (`QUANTIT`):** Obrigatório conter `Valor Teórico`, `Limite Mínimo`, `Limite Máximo`, `Método` e `Unidade de Medida`. Se algum estiver em branco, gera alerta/erro.
   - **Qualitativo (`QUALITAT`):** Não deve possuir esses campos numéricos preenchidos.
4. **Classes de Compatibilidade Física (Técnica Preditiva vs Grandeza):**
   - Matriz de compatibilidade entre Técnicas/Métodos e Unidades de Medida:
     - **Classe Temperatura:** Métodos (`PIRÔMETRO`, `CÂMERA TERMOGRÁFICA`, `TERMÔMETRO`) $\leftrightarrow$ Unidades (`°C`, `°F`, `K`).
     - **Classe Vibração:** Métodos (`COLETOR DE VIBRAÇÃO`, `ACELERÔMETRO`, `VELOCÍMETRO`) $\leftrightarrow$ Unidades (`mm/s`, `g`, `µm`).
     - **Classe Elétrica:** Métodos (`ALICATE AMPERÍMETRO`, `MULTÍMETRO`, `MEGÔMETRO`) $\leftrightarrow$ Unidades (`A`, `mA`, `V`, `kV`, `MΩ`).
     - **Classe Pressão:** Métodos (`MANÔMETRO`, `TRANSDUTOR DE PRESSÃO`) $\leftrightarrow$ Unidades (`bar`, `psi`, `kgf/cm²`, `kPa`).
     - **Classe Lubrificação / Amostragem:** Métodos (`ANÁLISE DE ÓLEO`, `VISCOSÍMETRO`) $\leftrightarrow$ Unidades (`cSt`, `ppm`, `NAS`, `ISO4406`).
   - **Reordenação Inteligente nos Dropdowns:** Na tela de edição, ao selecionar a grandeza/classe, o sistema prioriza e exibe **no topo da lista** os Métodos e Unidades pertencentes àquela mesma classe técnica, colocando os demais abaixo.

---

### 5. Validação de Condição Operacional vs Tipo de Ciclo
- **Ciclo `SMS` (Semanal / Tempo):** A condição operacional da máquina deve ser obrigatoriamente `P` (Parado), `F` (Funcionando) ou `Q` (Qualquer).
- **Ciclo `PRD` (Produção / Rodagem / Contador):** A condição deve ser obrigatoriamente `M` (Manutenção).

---

### 6. Regras de Prioridade por Módulo
- **Módulo PM11:** A Prioridade deve ser obrigatoriamente `0`. Se diferente de 0, gera aviso/correção.
- **Módulo PM13:** A Prioridade deve ser um valor inteiro entre `1` e `4`.

---

### 7. Unicidade de Identificador em Itens
- Proibida a presença de identificadores repetidos na tabela de Itens de Manutenção do mesmo projeto.

---

### 8. Existência de Referência em Planos
- Todo `Item de Manutenção` e toda `Característica` deve estar obrigatoriamente associado a um código de `Plano` cadastrado na tabela de PLANOS.

---

### 9. Sanitização e Rigor de Caracteres no PM11
- No módulo **PM11**, os campos `Tipo` e `Método` destinados à planilha SAP não podem conter caracteres especiais (como `Ç`, acentos `á, é, í, ó, ú`) nem espaços em branco no código de carga.

---

## 🎨 Destaque Visual e Diagnóstico Amarelo/Vermelho

| Severidade | Cor Visual | Situação / Significado | Ação Recomendada |
|---|---|---|---|
| **Erro Crítico** | 🟥 **Vermelho (`#FEE2E2` / Borda `#EF4444`)** | Violação de limites, ID duplicado, incompatibilidade grave de unidade/classe técnica ou falta de plano pai. | Correção obrigatória para geração de planilha SAP. |
| **Alerta / Warning** | 🟨 **Amarelo (`#FEF3C7` / Borda `#F59E0B`)** | Descrição longa (>35 caracteres), prioridade fora do padrão recomendado ou falta de recomendação técnica. | Sugestão de ajuste visual/gerencial. |
| **Válido / OK** | 🟩 **Verde / Padrão** | Dado totalmente compatível e verificado pelos catálogos. | Nenhuma ação necessária. |

---

## 🛠️ Evidências de Implementação e Execução

### 1. Arquivos Criados:
- [NEW] [`core/technical_classes.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core/technical_classes.py): Mapeamento central das 7 Classes Técnicas Físicas (Temperatura, Vibração, Elétrica, Pressão, Lubrificação, Espessura, Rotação) e função `sanitize_code()` para PM11.
- [NEW] [`core_pm11/validation_engine.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/validation_engine.py): Motor de validação automatizada das 9 regras para o módulo PM11.
- [NEW] [`core/validation_engine.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core/validation_engine.py): Motor de validação automatizada das 9 regras para o módulo PM13.
- [NEW] [`static/js/technical_classes.js`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/js/technical_classes.js): Engine frontend de agrupamento por classe e reordenação dinâmica de dropdowns.

### 2. Modificações em Arquivos Existentes:
- [MODIFY] [`core_pm11/sap_standards.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/sap_standards.py): Atualização da função `generate_nponto_hash` para utilizar o sufixo alfanumérico em Base36 de `00` a `ZZ`.
- [MODIFY] [`core_pm11/database.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/database.py): Migração automatizada adicionando as colunas `validation_status` e `validation_issues_json` nas tabelas do PM11.
- [MODIFY] [`core_pm11/handler.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/handler.py) & [`app.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/app.py): Registro dos endpoints `POST /api/pm11/validate` e `POST /api/validate`.
- [MODIFY] [`core_pm11/import_export.py`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/core_pm11/import_export.py): Disparo automático do motor de validação logo após concluir a importação de planilhas.
- [MODIFY] [`static/css/app.css`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/css/app.css): Estilização CSS para `.cell-invalid-error` (borda e fundo vermelho `#FEE2E2`) e `.cell-invalid-warning` (borda e fundo amarelo `#FEF3C7`).
- [MODIFY] [`static/js/pm11/characteristics.js`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/js/pm11/characteristics.js) & [`static/js/pm11/items.js`](file:///c:/EMERSON/projetos%20antigravity/Planos%20PM13-PM11/static/js/pm11/items.js): Renderização visual dos alertas/erros e reordenação de dropdowns.

### 3. Resultados de Execução dos Testes:
- **Execução do Motor PM11 (Projeto 1):** 182 planos, 380 itens e 2.774 características verificados e atualizados no banco em menos de 2 segundos.
- **Respostas de Endpoint HTTP:** `POST /api/pm11/validate` e `POST /api/validate` respondendo `200 OK`.

