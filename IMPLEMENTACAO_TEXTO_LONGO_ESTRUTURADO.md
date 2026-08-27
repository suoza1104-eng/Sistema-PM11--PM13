# Implementação — Texto Longo Estruturado

Build: 2026.08.17-structured-long-text-v1

## Entregue

- Editor hierárquico de Texto Longo com tópicos e subtópicos automáticos (1, 1.1, 1.1.1...).
- Enter cria o próximo tópico no mesmo nível e renumera os itens abaixo.
- Tab avança um nível; Shift+Tab e Backspace no início retornam um nível.
- Seleção de bloco pelo número do tópico, incluindo todos os descendentes.
- Exclusão, duplicação e arrastar/soltar de blocos com renumeração automática.
- Linhas de texto livre convivem com tópicos estruturados.
- Biblioteca global de Blocos Padrão: salvar um bloco existente, pesquisar, inserir antes/depois/dentro de outro tópico ou ao final e excluir padrões.
- Botão de Bloco Padrão nas operações e na visualização da ordem SAP.
- Importador tolerante a variações como 1.1., 1.1 -, 1.1-, 1.1_, espaços múltiplos e TAB.
- O importador não inventa tópicos quando o Texto Longo é livre e evita interpretar medidas como 1.1 kW ou 2.5 mm como numeração.
- Textos mistos (parágrafos livres + tópicos) são preservados.
- Texto original importado é preservado em metadados quando a estrutura é reconhecida.
- Numeração é materializada como texto real em toda saída oficial: visualização SAP, CSV/Excel e exportações de carga.
- Clonagem de itens, modelos de item e aplicação de modelos preservam a estrutura dos Textos Longos.
- Migração automática do SQLite para adicionar os metadados e a tabela de Blocos Padrão sem apagar os dados existentes.

## Instalação

1. Faça backup da pasta `data` do sistema.
2. Encerre o PM13 pelo botão **Encerrar Sistema**.
3. Extraia o PATCH sobre a pasta atual, mantendo as mesmas subpastas e substituindo os arquivos.
4. Não apague nem substitua a pasta `data`.
5. Execute `INICIAR_PM13.bat` novamente.
6. No navegador, pressione `Ctrl+F5` na primeira abertura para limpar o cache dos arquivos JS/CSS antigos.

Na primeira inicialização o sistema executa a migração do banco automaticamente.
