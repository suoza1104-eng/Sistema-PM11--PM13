# Validação — build 2026.09.10-desktop-1

Ponto de retorno anterior às alterações: commit `33bb51d`.

## Correções e distribuição

- PM13: especialidade e ciclo usam seletores nativos; ambos os módulos respeitam `no-searchable`.
- Projetos PM13 novos recebem os 20 ciclos PRD oferecidos anteriormente em Configurações.
- Uma migração preenche somente catálogos vazios; catálogos personalizados são preservados.
- A geração limpa roda migrações em outro processo com caminhos temporários explícitos.
  O gerador antigo podia inicializar o banco PM11 de origem e deixar o destino vazio.
- Versão navegador: console visível, servidor em 127.0.0.1:8765 e detecção de `py`/`python`.
- Versão desktop: EXE x64 com Python incorporado, WebView2, porta automática e mutex.
- Downloads de exportações habilitados na janela desktop.
- Dados e backups portáteis separados; cópia SQLite consistente antes das migrações por build.
- Identidade informativa Windows sem login; campos adicionais na auditoria PM13.
- Instalador offline Microsoft incluído, com assinatura Authenticode `Valid` verificada.
- ZIP de atualização inspecionado: sem bancos, `data`, `backups`, `dados_usuario` ou `backups_usuario`.

## Testes executados

- `tests.test_portable_distribution`: 3 testes aprovados (banco limpo e plano elétrico,
  catálogo personalizado, backup por versão e filtragem do ZIP).
- `tests.test_models_project_scope` e `tests.test_history_service`: aprovados;
  junto aos testes de distribuição, 13 testes aprovados.
- Sintaxe JavaScript dos módulos relacionados validada.
- Build PyInstaller concluído; geração pelo script offline concluída.
- `tests/desktop_smoke.py`: EXE executado com dados temporários; janela nativa,
  `/api/auth/me` sem login, interface servida, encerramento pelo endpoint e pelo X verificados.
- Segunda instância exibe aviso e encerra, preservando a primeira janela.
- Integridade CRC do ZIP desktop de atualização verificada.

## Falhas anteriores identificadas

A suíte existente tem 108 testes, dos quais 5 falharam tanto nesta árvore quanto
em uma cópia isolada do commit `33bb51d`, antes das alterações:

- `test_deleted_code_rename_survives_undo_redo_with_stable_ids_and_links`
- `test_mutation_undo_redo_and_redo_branch`
- `test_stop_workforce_uses_daily_team_hours`
- `test_duplicate_project`
- `test_description_length_warning`

Essas falhas anteriores não foram alteradas neste trabalho. Os testes direcionados
de preservação de dados e distribuição passaram. A instalação do WebView2 em um
computador sem o componente não foi exercitada: esta máquina já o possui. O caminho
offline, a presença do instalador e sua assinatura foram verificados.
