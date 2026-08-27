# Especificação Técnica — Planilha de Carga Sistemas (5 Abas SAP) — PM11 e PM13

Documento oficial de referência técnica para a geração da **Planilha de Carga Sistemas** (modelo 5 abas SAP) e a padronização das frequências para os módulos **PM11** e **PM13**.

---

## 📐 Estrutura Geral e Abas do Arquivo (.xlsx)

O arquivo é gerado em formato OpenXML `.xlsx` contendo exatamente 5 abas organizadas:

1. **`PLANO`**: Planos de manutenção baseados em tempo.
2. **`ITEM`**: Vínculo entre planos, equipamentos, rotas e características.
3. **`CABEÇALHO`**: Listas de tarefas do cabeçalho da ordem.
4. **`OPERAÇÃO`**: Detalhamento da operação (duração em minutos, centro de trabalho, chave de cálculo).
5. **`CARACTERISTICAS`**: Especificações técnicas (qualitativas/quantitativas) atreladas aos pontos de controle.

---

## 🔑 Regra da Chave Única N.PONTO (13 Dígitos Numéricos - Fórmula Personalizada)

- **Composição dos 13 Dígitos:**
  1. **Primeiros 6 dígitos:** Data atual no formato `DDMMAA` (ex: `260826` para 26/08/2026).
  2. **Próximos 5 dígitos:** Segundo exato do dia da geração (`00000` a `86399`, ex: `39505` para 10:58:25).
  3. **Últimos 2 dígitos:** Sequência / Semente aleatória por item (`00` a `99`, ex: `14`).
- **Tamanho Total:** Exatamente **13 dígitos numéricos**.
- **Exemplo de Resultado:** `2608263950514`
- **Garantia de Não-Colisão:** Como cada exportação inclui os segundos exatos do dia e cada item possui uma semente/sequência de 2 dígitos, é virtualmente impossível 20 pessoas gerarem códigos idênticos na mesma data.
- **Utilização:** Serve como chave primária / estrangeira que conecta e cruza os dados entre as abas `ITEM`, `CABEÇALHO`, `OPERAÇÃO` e `CARACTERISTICAS`.

---

## 📋 Detalhamento Campo a Campo das 5 Abas

### 1. Aba `PLANO`
| Coluna | Campo SAP | Origem dos Dados / Regra |
|---|---|---|
| A | Cód. Plano | `plan.code` |
| B | Categoria | Fixo: `PM` |
| C | Ciclo | `plan.cycle_value` |
| D | unid. | `plan.unit` (`SMS` ou `DIA`) |
| E | Texto Ciclo | `plan.text_cycle` (Padronizado via Tabela SAP) |
| F | No.ACOM Objeto | Vazio (Plano por tempo) |
| G | Offset | `plan.offset_days` (ou Vazio se nulo) |
| H | Txt. Descritivo | `plan.description` |
| I..M | Conf. Obrigatória a Tol. | Vazio |
| N | Interv. Solicitação | Intervalo correspondente da Tabela SAP (ex: `2` para 2 SEMANAS) |
| O | unid. | `unid_solic` da Tabela SAP (`SMS`) |
| P | Horiz. Abertura | Horizonte de Abertura da Tabela SAP (ex: `50` para 2 SEMANAS, `100` para 1 SEMANA/DIA) |
| Q..S | Data Inicio a Calendário | Vazio |

---

### 2. Aba `ITEM`
| Coluna | Campo SAP | Origem dos Dados / Regra |
|---|---|---|
| A | Cód.Plano | `item.plan_code` |
| B | Cat | Fixo: `PM` |
| C | Txt.Descritivo | Concatenação: `item.route` + `" "` + `plan.description` |
| D | cod equipamento | `item.equipment_code` |
| E | Centro | Fixo: `US01` |
| F | GPM | `item.gpm` |
| G | Tipo Ordem | Fixo: `PM11` (ou `PM13`) |
| H | Atividade | Fixo: `015` |
| I | CT Inspetor | `item.work_center` |
| J | Centro | Fixo: `US01` |
| K | Prioridade | `item.priority` (Se vazio, `0`) |
| L | N.PONTO | Código Hash único de 13 caracteres (`260826P000042`) |
| M | MNAME_01 Característica | Condição do Item (`item.condition_code`, ex: `F`, `Q`, `P`) |
| N | MNAME_01 (2ª col) | Vazio |
| O | Criticidade | Vazio |

---

### 3. Aba `CABEÇALHO`
| Coluna | Campo SAP | Origem dos Dados / Regra |
|---|---|---|
| A | EQUNREquipamento ACOM | `item.equipment_code` |
| B | PROFIDNETZ Perfil | Fixo: `PM01` |
| C | STTAG Data fixada | Vazio |
| D | KTEXT Denominação Lista | Concatenação: `item.route` + `" "` + `plan.description` |
| E | ARBPLCentro de trabalho | `item.work_center` |
| F | WERKS Centro | Fixo: `US01` |
| G | VERWE Utilização | Fixo: `PR1` |
| H | VAGRPGPM | `item.gpm` |
| I | STATU Status | Fixo: `4` |
| J | ANLZU Conds. instal. | `item.condition_code` |
| K | SLWBEZ Ponto de controle | `300` se houver Equipamento; `310` se for Local de Instalação |
| L | KLART Tipo de classe | Fixo: `018` |
| M | CLASS_01 Classe | Fixo: `USPM_LISTA_TAREFA` |
| N | MNAME_01 Característica | Fixo: `SUPM_QUANTIDADE_DE_PONTOS` |
| O | MNAME_02 Característica | Fixo: `SUPM_NUMERO_ACOM` |
| P | MNAME_03 Característica | Fixo: `USPM_TECNICA_DE_PREDITIVA` |
| Q | MWERT_01 Valor da Caract | Fixo: `1` |
| R | MWERT_02 Valor da Caract | Código Hash N.PONTO criado (`260826P000042`) |

---

### 4. Aba `OPERAÇÃO`
| Coluna | Campo SAP | Origem dos Dados / Regra |
|---|---|---|
| A | Nº antigo do ACOM | Código Hash N.PONTO criado (`260826P000042`) |
| B | VORNR Nº operação | Fixo: `0010` |
| C | UVORN Nº Sub operação | Vazio |
| D | ARBPL2 Centro Trabalho | `item.work_center` |
| E | WERKS2 Centro | Fixo: `US01` |
| F | STEUS Chave controle | Fixo: `PM01` |
| G | LTXA1 Txt breve operação | Concatenação: `item.route` + `" "` + `plan.description` |
| H | ARBEH Unidade trabalho | Fixo: `MIN` |
| I | ANZZL Núm capacidades | Fixo: `1` |
| J | DAUNO Duração operação | `item.inspection_minutes` (em minutos) |
| K | DAUNE Unidade Duração | Fixo: `MIN` |
| L | INDET Chave de Cálculo | Fixo: `2` |
| M | PRZNT Porcentagem aumento| Fixo: `100` |
| N | LARNT Tipo Atividade | Vazio |

---

### 5. Aba `CARACTERISTICAS`
| Coluna | Campo SAP | Origem dos Dados / Regra |
|---|---|---|
| A | MWERT_02 Valor Caract | Código Hash N.PONTO do item (`260826P000042`) |
| B | VORNR Nº operação | Fixo: `0010` |
| C | VERWMERKM Carac.mestre | `characteristic.characteristic_type` (`QUALITAT` / `QUANTIT`) |
| D | QPMK_WERKS Centro | Fixo: `US01` |
| E | KURZTEXT Texto breve | `characteristic.description` |
| F | PMETHODE Método | `characteristic.method_code` |
| G | QPMK_WERKS Centro | Fixo: `US01` |
| H | STICHPRVER Processo | Fixo: `AMRT0001` |
| I | STELLEN Casas decimais | `characteristic.decimals` |
| J | MASSEINHSW Unidade | `characteristic.unit_code` |
| K | SOLLWERT Valor teórico | `characteristic.reference_value` |
| L | TOLERANZUN Limite inf. | `characteristic.lower_limit` |
| M | TOLERANZOB Limite sup. | `characteristic.upper_limit` |
| N | AUSWMENGE1 Grupo codes | Fixo: `PMAVALIA` |
| O | AUSWMGWRK1 Centro Cat. | Fixo: `US01` |

---

## 📊 Tabela de Referência Padrão SAP para Frequências

| Código SAP | Ciclo | Unidade | Texto do Ciclo | Intervalo | Unid. Solic. | Horiz. Insp. (%) | Horiz. Periódico (%) |
|---|---|---|---|---|---|---|---|
| 01D | 1 | DIA | DIÁRIA | 1 | SMS | 100 | 100 |
| 02D | 2 | DIA | DOIS DIAS | 1 | SMS | 100 | 100 |
| 03D | 3 | DIA | 3 DIAS | 1 | SMS | 100 | 100 |
| 01S | 1 | SMS | 1 SEMANA | 1 | SMS | 100 | 100 |
| 02S | 2 | SMS | DUAS SEMANAS | 2 | SMS | 50 | 100 |
| 03S | 3 | SMS | 3 SEMANAS | 3 | SMS | 65 | 35 |
| 01M | 4 | SMS | 4 SEMANAS = 1M | 4 | SMS | 80 | 50 |
| 06S | 6 | SMS | 6 SEMANAS | 6 | SMS | 83 | 65 |
| 02M | 9 | SMS | 9 SEMANAS = 2M | 9 | SMS | 89 | 65 |
| 03M | 13 | SMS | TRIMESTRAL = 3M | 13 | SMS | 92 | 75 |
| 04M | 17 | SMS | 17 SEMANAS = 4M | 17 | SMS | 94 | 80 |
| 06M | 26 | SMS | SEMESTRAL = 26S | 26 | SMS | 96 | 85 |
| 09M | 39 | SMS | 9 MESES = 39S | 39 | SMS | 97 | 90 |
| 01A | 52 | SMS | ANUAL | 52 | SMS | 98 | 90 |
| 18M | 78 | SMS | 18 MESES = 78S | 78 | SMS | 99 | 95 |
| 02A | 104 | SMS | 2 ANOS | 104 | SMS | 99 | 95 |
| 03A | 156 | SMS | 3 ANOS | 156 | SMS | 99 | 97 |
| 04A | 208 | SMS | 4 ANOS | 208 | SMS | 99 | 98 |

