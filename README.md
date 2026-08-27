# Sistema de Controle e Balanceamento PM13 Local

Este é um sistema completo, local e offline para controle, criação, organização, importação e balanceamento de planos de manutenção programada PM13 em indústrias siderúrgicas. Ele substitui planilhas Excel complexas por um banco de dados estruturado SQLite e um servidor HTTP em Python com interface Single Page Application (SPA) moderna, responsiva e dinâmica.

O sistema opera sob as restrições corporativas de segurança e infraestrutura: roda localmente no Windows 10/11, com Python 3.11 padrão, sem privilégios de administrador e de forma 100% offline.

---

## 🛠️ Estrutura do Projeto

Abaixo estão descritos os principais arquivos e pastas que compõem o sistema:

```text
├── core/
│   ├── audit_service.py       # Registro estruturado JSON de modificações (CRUD) no banco de dados.
│   ├── backup_service.py      # Utilitário para snapshots do SQLite usando API de backup nativa online.
│   ├── calculations.py        # Motor matemático para cálculo de ocorrências de paradas e histogramas.
│   ├── database.py            # Gerenciamento de conexão SQLite, Row mapping e PRAGMAs.
│   ├── export_service.py      # Formatador e gerador de arquivos CSV adaptados para o Excel em português.
│   ├── import_service.py      # Validador e normalizador de planilhas Excel antes da escrita no banco.
│   ├── migrations.py          # Definição e criação do esquema de 9 tabelas do banco de dados e índices.
│   ├── models.py              # Camada de persistência de dados (CRUDs) e duplicação profunda de projetos.
│   ├── validators.py          # Regras de negócio (limite de 35 caracteres, divergência de códigos).
│   └── xlsx_reader.py         # Leitor XML nativo de planilhas XLSX sem dependências externas.
├── static/
│   ├── css/
│   │   └── app.css            # Estilização visual corporativa moderna com CSS nativo e variáveis.
│   ├── js/
│   │   ├── api.js             # Cliente Fetch centralizado para endpoints locais REST.
│   │   ├── app.js             # Roteador de hash SPA, menu de navegação e estado global do projeto.
│   │   ├── balance.js         # Controladores da tela de balanceamento e mapa de calor.
│   │   ├── components.js      # Gráficos SVG interativos (Bar, Stacked Bar) e Toasts/Loader locais.
│   │   ├── dashboard.js       # Controladores dos KPIs gerenciais da tela inicial e alertas.
│   │   ├── import.js          # Wizard de importação guiada de arquivos Excel.
│   │   ├── items.js           # Gerenciador de itens com edição inline e ações em lote.
│   │   ├── plans.js           # Gerenciador de planos e regras de exclusão segura.
│   │   └── projects.js        # Controladores de listagem, abertura, criação e duplicação de projetos.
│   └── index.html             # Estrutura HTML única (SPA) com containers e modais.
├── tests/
│   └── test_system.py         # Suíte de testes unitários e de integração HTTP em portas efêmeras.
├── INICIAR_PM13.bat           # Executável de inicialização automática do sistema local.
├── TESTAR_PM13.bat            # Executável para rodar a suíte de testes automatizados.
├── MANUAL_USUARIO.html        # Manual do usuário estilizado em HTML com regras de negócio detalhadas.
└── README.md                  # Este guia geral da aplicação.
```

---

## ⚙️ Pré-requisitos de Ambiente

* **Sistema Operacional:** Windows 10 ou 11 (Corporativo ou Pessoal).
* **Interpretador Python:** Python 3.11 instalado de 64 bits.
* **Bibliotecas adicionais:** Nenhuma (o sistema usa estritamente a biblioteca padrão do Python: `sqlite3`, `zipfile`, `http.server`, etc., e não precisa de `pip install`).

---

## 🚀 Como Executar o Sistema

1. Navegue até a pasta raiz do projeto.
2. Dê dois cliques no arquivo `INICIAR_PM13.bat`.
3. O script detectará o Python 3.11, iniciará o servidor HTTP local em `127.0.0.1:8765` (ou na primeira porta livre subsequente) e abrirá automaticamente seu navegador web padrão.
4. Para encerrar o sistema, clique em **Encerrar Sistema** no menu lateral esquerdo ou dê um `Ctrl+C` no prompt de comando.

---

## 🧪 Como Executar a Suíte de Testes

1. Dê dois cliques no arquivo `TESTAR_PM13.bat` na pasta raiz.
2. O script executará o comando:
   ```cmd
   python -m unittest tests/test_system.py
   ```
3. O terminal executará os 11 casos de teste que validam:
   * Criação do banco e migrations.
   * Regras matemáticas de balanceamento (intervalos modULARES, média de headcount teto).
   * Alertas de validação de dados (descrições > 35 caracteres e divergência de sistemas).
   * Fluxos CRUDs do banco de dados e duplicação de cenários.
   * Criação e restauração de snapshots compactados.
   * Respostas de status e rotas do servidor HTTP local.

---

## 📊 Regras de Negócio e Cálculos

### Fórmula de Ocorrência de Planos
Um plano programado de ciclo \(C\) e contador de referência inicial \(R\) ocorre na parada \(S\) (onde \(S\) é o contador numérico da parada) se:
$$S \ge R \quad \text{e} \quad (S - R) \pmod C == 0$$

### Efetivo Necessário
O efetivo necessário é calculado dividindo a carga total de HH da parada pelas horas produtivas totais disponíveis da equipe (soma da duração dos turnos ativos multiplicada pelo fator de aproveitamento do projeto):
$$\text{Efetivo} = \left\lceil \frac{\text{HH}_{\text{total}}}{\text{Horas}_{\text{produtivas}}} \right\rceil$$

---

## 💾 Banco de Dados Schema (SQLite)

O banco de dados é criado em `data/pm13.db`. Ele contém as seguintes tabelas estruturadas:
1. `projects`: Guarda diferentes cenários de simulações.
2. `shifts`: Configura turnos (ex: Turno 1 = 10,5h, Turno 2 = 10,5h).
3. `cycle_catalog`: Frequências de ciclo (1 paradas, 3 paradas, 6 paradas, etc.) vinculadas ao horizonte de abertura no ERP.
4. `plans`: Cadastro dos planos de manutenção unificados do projeto.
5. `maintenance_items`: Detalhamento técnico de equipamentos, CTs, prioridades, durações e efetivos.
6. `imports`: Histórico de planilhas importadas no projeto.
7. `import_errors`: Registro das inconsistências detectadas nas linhas das planilhas importadas.
8. `audit_log`: Logs detalhados de histórico de auditoria de alterações (com JSON dos estados anterior e novo).
9. `project_settings`: Configurações de padrões de máscara de códigos e filtros globais.
