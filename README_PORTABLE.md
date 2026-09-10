# PM11 / PM13 — duas versões

## Navegador com console

Execute `GERAR_SISTEMA_LIMPO.bat`. O ZIP `SISTEMA_PM13_PM11_NAVEGADOR_LIMPO_*.zip`
contém bancos novos e catálogos, sem projetos do remetente. Extraia tudo e execute
`INICIAR_SISTEMA.bat`: o console fica aberto e a interface abre no navegador.
Essa versão precisa de Python 3 no computador; procura primeiro `py -3`, depois `python`.

## Desktop portátil

Na máquina de compilação Windows x64, prepare uma vez com:

```powershell
.\CRIAR_EXECUTAVEL.bat -PrepareOnline
```

Isso baixa as dependências de build e o instalador oficial WebView2 x64.
Nas próximas compilações, `CRIAR_EXECUTAVEL.bat` usa `offline_packages` e
`offline_runtime`, sem downloads. A geração requer Python na máquina de compilação.

Distribua `dist/SISTEMA_PM11_PM13_DESKTOP_LIMPO.zip` inteiro. Extraia a pasta
completa em local gravável e execute `Sistema_PM11_PM13.exe`. Não copie somente o
EXE: `_internal` e `offline_runtime` são necessários. O Python está incorporado.
A janela própria não abre console nem navegador. WebView2 é detectado e, quando
ausente, o instalador Microsoft incluído é validado e executado silenciosamente.
Nenhum componente é baixado pelo inicializador no computador de destino.
Políticas corporativas podem impedir a instalação do WebView2; a falha é exibida.

Os bancos ficam em `dados_usuario/pm13.db` e `dados_usuario/pm11.db` e os backups
em `backups_usuario`. Em código-fonte usam-se `data` e `backups`.
`MCM_USER_DATA_DIR` e `MCM_BACKUP_DIR` permitem redirecionar os caminhos.
Antes das migrações, bancos existentes recebem uma cópia SQLite consistente por build.
Não mova uma instalação antiga de navegador para desktop sem exportar/importar seu backup.

## Atualização de uma instalação desktop

1. Feche completamente o sistema.
2. Extraia `dist/ATUALIZACAO_PM11_PM13.zip`.
3. Copie seu conteúdo por cima da pasta existente, confirmando substituições.
4. Abra `Sistema_PM11_PM13.exe` novamente.

O ZIP de atualização não contém bancos nem pastas de dados ou backups.
Não apague essas pastas. Atualizações do navegador usam `GERAR_PACOTE_ATUALIZACAO.bat`.

O acesso é local, sem login. O cabeçalho identifica a conta Windows e a auditoria
PM13 registra nome, conta, SID e computador nas ações já auditadas.
O serviço escuta apenas em 127.0.0.1; no desktop a porta é automática.

Referências: [distribuição WebView2](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
e [empacotamento pywebview](https://pywebview.flowrl.com/guide/freezing).
