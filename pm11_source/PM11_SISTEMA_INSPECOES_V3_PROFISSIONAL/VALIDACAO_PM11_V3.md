# Relatório de Validação — PM11 V3 Profissional

Data da validação: 20/08/2026

## 1. Validação estática

- Compilação Python (`compileall`): **OK**.
- Sintaxe de todos os JavaScripts (`node --check`): **OK**.

## 2. Testes automatizados

Bateria: `tests/test_pm11.py`.

Resultado: **8/8 aprovados**.

Cobertura:

1. Plano → Item → Característica + Condição F.
2. Característica qualitativa limpa campos quantitativos.
3. Modelos de Item e Equipamento/Pacote.
4. Clonagem de Plano com Itens + Características.
5. Balanceamento com Meta e filtros.
6. Duplicação e trancamento de Projeto.
7. Exportação completa → MERGE com renumeração e vínculo preservado.
8. Reconhecimento da planilha real de referência.

## 3. Planilha real fornecida

Arquivo: `references/Planos Padrão Área1.xlsx`.

Reconhecimento automático obtido:

- **94 Planos**;
- **1 Item real de exemplo**;
- **2 Características de Controle**.

Abas reconhecidas:

- `Cod Planos`;
- `ITENS`;
- `SÍNTESE DE CARACT - INSPEÇÃO`.

O leitor identifica cabeçalhos mesmo quando estão em linhas diferentes e evita interpretar caudas artificiais da planilha como registros reais.

## 4. Teste HTTP integrado

Servidor iniciado em `127.0.0.1:8766` e validado via API real.

Fluxo aprovado:

- health;
- criar Projeto;
- cadastrar Linha/Subárea;
- criar Plano;
- criar Item com Condição F e Rota normalizada;
- criar Característica quantitativa;
- listar/filtrar Planos, Itens e Características;
- gerar Balanceamento e Book;
- exportar Projeto Completo XLSX;
- salvar Modelo de Item;
- trancar Projeto e confirmar bloqueio de mutação;
- destrancar;
- duplicar Projeto;
- excluir cópia e Projeto de teste.

Resultado: **HTTP_INTEGRATION_OK**.

O banco de entrega foi restaurado ao estado anterior após o teste integrado.

## 5. Round-trip XLSX

Validado automaticamente:

`Projeto → Exportar XLSX → Projeto destino → MERGE`.

Quando existe colisão de Identificador, o Item importado recebe novo Identificador e sua Característica continua vinculada ao novo Item.

## 6. Observação

A validação automatizada cobre backend, arquivos, importação/exportação e contratos de API. Recomenda-se ainda um teste operacional visual no computador de uso final para validar particularidades de resolução, navegador corporativo e políticas locais do Windows.

## 7. Validação do ZIP final

O pacote final foi extraído em uma pasta limpa e novamente validado:

- `MANIFEST_SHA256.txt`: **OK**;
- sintaxe Python: **OK**;
- sintaxe JavaScript: **OK**;
- testes automatizados 8/8: **OK**;
- reconhecimento da planilha real: **OK**;
- inicialização do servidor a partir da pasta extraída: **OK**;
- `/api/health`: **OK**;
- leitura de Projetos: **OK**;
- encerramento pela API/interface: **OK**.
