# Plano de implementação — rodada atual

## 1. Importação tolerante a operações sem item

**Status:** implementado e validado.

- Permitir que a importação prossiga quando uma operação não possuir item correspondente.
- Criar um item provisório para preservar a integridade do vínculo no banco.
- Marcar o item e a operação com erro de validação.
- Registrar a inconsistência no histórico da importação para correção posterior no sistema.

## 2. Balanceamento com proximidade geográfica

**Status:** implementado nesta rodada, com modos desativado, preferencial e obrigatório.

### Objetivo

Evitar que uma mesma parada reúna, sem necessidade, equipamentos geograficamente distantes. O balanceador deverá considerar, além do HH e da identificação da máquina, dois sinais de proximidade:

1. **Sequência dos itens:** a ordem/identificador dos itens representa a sequência geográfica da área; itens próximos nessa sequência devem receber preferência para permanecer na mesma parada.
2. **Família do plano:** os nove primeiros caracteres do código do plano identificam a área, máquina e sistema. Exemplo: `URR ST2 STC` representa o sistema C da máquina de sínter 2 e deve ser tratado como um agrupamento geográfico.

### Configuração na interface

Adicionar ao modal de Balanceamento Automático uma opção de agrupamento geográfico com os modos:

- **Desativado:** não considerar proximidade geográfica.
- **Preferencial:** proximidade entra como bônus/penalidade na pontuação, sem impedir uma solução de HH melhor.
- **Obrigatório:** itens pertencentes ao mesmo grupo compatível devem ser tratados como um bloco e alocados juntos.

A interface deverá explicar que o modo obrigatório somente pode ser aplicado quando periodicidade e fases dos planos forem compatíveis.

### Regra de agrupamento proposta

- Normalizar o código do plano em maiúsculas e extrair sua família pelos nove primeiros caracteres.
- Ordenar os itens pelo identificador sequencial usado na lista geográfica.
- Formar grupos considerando prioritariamente a mesma família de plano e a continuidade/proximidade na sequência.
- Não alterar a periodicidade original dos itens ou planos.
- Não movimentar itens para planos fora das famílias e fases permitidas.
- Manter planos `1P` protegidos.

### Comportamento preferencial

- Acrescentar ao cálculo uma penalidade por separar itens próximos da mesma família.
- Acrescentar penalidade menor por separar vizinhos geográficos, mesmo quando os códigos não forem idênticos.
- Manter como objetivo principal a redução do GAP e do desvio de HH, usando pesos configurados e auditáveis.
- Exibir no resultado quantos grupos foram mantidos juntos e quantos foram separados para favorecer o HH.

### Comportamento obrigatório

- Consolidar itens compatíveis do grupo em um bloco de HH durante a otimização.
- Avaliar e movimentar o bloco inteiro, sem separar seus integrantes.
- Validar antes da execução se todos os integrantes possuem periodicidade e fases compatíveis.
- Quando o agrupamento for impossível, não aplicar silenciosamente: informar os itens, planos e a causa da incompatibilidade para o usuário corrigir ou trocar para o modo preferencial.

### Ordem de prioridade proposta

1. Restrições obrigatórias e integridade das periodicidades.
2. Regras operacionais explícitas criadas pelo usuário.
3. Agrupamento geográfico quando configurado como obrigatório.
4. Redução do GAP entre a maior e a menor carga.
5. Redução do desvio-padrão e dos picos de HH.
6. Agrupamento geográfico preferencial.
7. Similaridade por máquina/título.

### Alterações técnicas previstas

- Evoluir a extração de similaridade para considerar descrição do item, código do equipamento, família de nove caracteres e posição geográfica.
- Incluir o modo de agrupamento no payload das APIs de prévia e aplicação do balanceamento.
- Persistir a configuração junto às regras do cenário.
- Incluir as métricas geográficas na pontuação e no resumo do resultado.
- Registrar no log de auditoria o modo utilizado, grupos formados, separações e incompatibilidades.

### Critérios de aceite

- Com agrupamento desativado, preservar o comportamento atual.
- No modo preferencial, itens próximos e da mesma família devem permanecer juntos quando a diferença de HH estiver dentro da tolerância configurada.
- No modo obrigatório, nenhum grupo compatível pode ser separado.
- Grupos incompatíveis devem produzir uma mensagem clara antes de qualquer alteração no banco.
- O resultado deve informar GAP, desvio-padrão, grupos preservados, grupos separados e motivo das separações.
- A mesma entrada e a mesma quantidade de varreduras devem produzir resultado reproduzível.
- Testes devem cobrir ciclos `1P`, `2P`, `3P`, `6P`, famílias iguais e diferentes, vizinhos de sequência, regras conflitantes e grupos incompatíveis.

### Pontos a confirmar antes da implementação

- Se espaços, hífens e outros separadores contam entre os nove caracteres do código ou devem ser removidos antes da extração.
- Qual distância máxima na sequência ainda caracteriza itens como geograficamente próximos.
- Qual tolerância de aumento do GAP é aceitável para preservar um grupo no modo preferencial.
- Se a regra explícita “Executar juntos” deve sempre prevalecer sobre o agrupamento geográfico obrigatório em caso de conflito.

## 3. Modo de Balanceamento Manual com Book de Itens

**Status:** implementado nesta rodada com rascunho persistente, Book, filtros, lote e integração automática.

### Objetivo

Criar um fluxo de balanceamento manual mais rápido e simples que uma planilha Excel: o usuário inicia com os itens balanceáveis fora do gráfico, encontra rapidamente o que precisa no Book, arrasta para a parada desejada e acompanha imediatamente o efeito em HH e efetivo.

### Princípio de segurança: trabalhar em rascunho

O modo manual deverá criar uma **sessão de balanceamento em rascunho**, salva automaticamente, sem sobrescrever imediatamente o cenário oficial.

- Ao iniciar do zero, os itens com ciclo maior que `1P` ficam com estado **Pendente** e deixam de compor as barras do gráfico do rascunho.
- Os planos são normalizados virtualmente para sua fase 1 (`2P1`, `3P1`, `4P1` etc.) apenas como referência inicial, preservando ciclo, família e vínculo originais.
- Os itens `1P` continuam protegidos, pois obrigatoriamente ocorrem em todas as paradas. O gráfico poderá exibi-los como uma camada-base fixa ou ocultá-los visualmente por um botão, sem removê-los do cálculo.
- Nenhuma informação original é perdida: a sessão guarda plano/fase de origem, destino atual e estado do item.
- Cada movimentação é salva automaticamente. Fechar a tela ou o sistema não perde o trabalho.
- O cenário oficial somente é substituído ao selecionar **Concluir balanceamento**.
- Deve existir **Descartar rascunho** e restauração pelo histórico/backup.

Essa separação evita gravar todos os itens fisicamente em P1 apenas para depois retirá-los e permite retomar um trabalho interrompido com segurança.

### Entrada no modo manual

Adicionar o botão **Balanceamento Manual** próximo ao Balanceamento Automático. Ao acioná-lo:

1. Se não existir rascunho, abrir uma confirmação resumida com as opções **Iniciar do zero** ou **Partir do cenário atual**.
2. Se existir rascunho, oferecer **Continuar rascunho**, **Recomeçar** ou **Descartar**.
3. Criar backup automático antes de recomeçar ou concluir.
4. Abrir o gráfico e o Book lado a lado, já em modo de edição.

No modo **Iniciar do zero**, o gráfico começa vazio de itens balanceáveis; apenas a camada fixa `1P` pode permanecer visível. No modo **Partir do cenário atual**, todos os itens existentes começam posicionados e marcados como manuais.

### Painel lateral com duas visões

Reaproveitar a lateral atual e transformá-la em duas abas claras:

- **Book de itens:** apresenta todos os itens/ordens do projeto ou somente os pendentes.
- **Parada Pn:** ao clicar em uma barra, apresenta apenas as ordens daquela parada.

Deve existir um botão permanente **Abrir Book**, com contador de pendências, para retornar à lista geral sem precisar fechar o painel. Clicar numa barra troca automaticamente para a aba da parada; clicar no botão Book retorna ao acervo.

### Conteúdo e filtros do Book

Cada linha deverá mostrar, de forma compacta:

- alça de arraste;
- checkbox para seleção em massa;
- identificador e descrição do item;
- código e descrição do plano;
- ciclo;
- HH total e especialidades;
- família geográfica de nove caracteres;
- estado: **Pendente**, **Manual**, **Automático** ou **Fixo 1P**.

Filtros rápidos:

- checkbox **Somente não balanceados**, ativado por padrão ao iniciar do zero;
- botões/chips de ciclo gerados dinamicamente (`1P`, `2P`, `3P`, `4P`, `6P`, `10P`, `12P` etc.), com contador e seleção múltipla;
- campo único de pesquisa incremental por identificador, descrição, equipamento, código ou parte do código do plano;
- filtro específico por plano/família, também incremental;
- filtros por especialidade, CT, GPM e estado do balanceamento;
- comandos **Limpar filtros** e **Selecionar visíveis**.

A busca deverá ser atualizada enquanto o usuário digita, com pequeno debounce, sem botão “Pesquisar”. Os filtros escolhidos permanecem ao alternar entre Book e parada.

### Arrastar do Book para o gráfico

- Arrastar uma linha sobre uma barra posiciona o item naquela parada, respeitando seu ciclo e escolhendo automaticamente o plano/fase compatível.
- O item passa de **Pendente** para **Manual** e sai imediatamente da visão “Somente não balanceados”.
- O gráfico, mapa de calor, HH, efetivo e indicadores são atualizados imediatamente, sem recarregar toda a página.
- Durante o arraste, apenas paradas válidas ficam destacadas; destinos incompatíveis aparecem bloqueados com a explicação do motivo.
- Se houver uma única combinação compatível, o movimento ocorre em um gesto, sem modal de confirmação.
- Se houver mais de um plano compatível, abrir um seletor curto e contextual, priorizando mesma família geográfica e mesmo equipamento.
- Permitir selecionar várias linhas por checkbox e arrastar o conjunto como um bloco, exibindo antes do drop o HH total selecionado.

### Retirar uma ordem da parada

Na aba **Parada Pn**, as ordens continuam arrastáveis. Para evitar remoções acidentais:

- exibir durante o arraste uma área clara **Retornar ao Book / Marcar como pendente**;
- soltar fora das áreas válidas não produz alteração;
- soltar na área de retorno mostra um aviso curto e retira a ordem do rascunho;
- após confirmar, o gráfico desconta imediatamente seu HH e efetivo;
- a ordem volta ao Book com estado **Pendente**;
- oferecer ação **Desfazer** no aviso de sucesso.

Se a retirada afetar vários itens ou uma regra obrigatória, a confirmação deve informar quantidade, HH e vínculos afetados.

### Salvamento, progresso e retomada

- Autosave após cada movimentação ou lote, com indicador discreto **Salvo agora**.
- Mostrar no topo: itens e HH **Balanceados**, **Pendentes** e percentual concluído.
- Ao sair da tela, informar que o rascunho foi salvo e poderá ser retomado.
- O botão **Concluir balanceamento** só publica o rascunho após uma revisão com GAP, picos, pendências e violações.
- Permitir concluir com pendências apenas mediante confirmação explícita; o recomendado é concluir sem pendências.
- Integrar todas as ações ao Desfazer/Refazer persistente, inclusive após reiniciar o sistema.

### Integração com o Balanceamento Automático

Se houver um rascunho manual, ao acionar o automático o sistema deverá perguntar:

- **Manter posicionados e balancear somente os pendentes** — opção recomendada;
- **Rebalancear tudo do zero**;
- **Cancelar**.

Na primeira opção:

- itens com estado **Manual** e itens `1P` tornam-se bloqueados para o algoritmo;
- somente itens **Pendentes** podem ser movimentados;
- a carga fixa já posicionada entra no cálculo do HH de cada parada;
- regras obrigatórias incompatíveis com itens bloqueados devem ser informadas antes da execução;
- itens colocados pelo algoritmo recebem estado **Automático**, distinguindo-os dos manuais.

O usuário poderá posteriormente desbloquear um item manual específico e devolvê-lo ao Book ou permitir que o automático o reavalie.

### Recursos adicionais para produtividade

- Duplo clique em um item abre uma ação rápida **Enviar para P...** para quem preferir não arrastar.
- Atalhos de teclado para pesquisa, selecionar visíveis, desfazer e refazer.
- Ordenação por sequência geográfica como padrão, preservando a lógica operacional da lista original.
- Indicadores de capacidade diretamente sobre a barra durante o arraste: carga atual, carga após o drop e eventual excesso.
- Cores consistentes para Pendente, Manual, Automático e Fixo.
- Possibilidade de recolher o painel lateral sem perder filtros ou seleção.
- Lista virtualizada/paginada para manter fluidez com milhares de ordens.
- Atualizações em lote no servidor para evitar uma requisição e um recálculo completo por item selecionado.

### Modelo de dados previsto

Criar entidades próprias para não confundir “pendente de balanceamento” com “item sem plano”:

- sessão manual por projeto, com status `DRAFT`, `COMPLETED` ou `DISCARDED`;
- atribuição por item contendo plano/fase original, plano/fase de destino, estado do balanceamento, origem manual/automática e data da última alteração;
- preferência e filtros da sessão;
- versão da sessão para impedir que duas telas sobrescrevam o mesmo rascunho simultaneamente.

As APIs do gráfico deverão receber o identificador da sessão ativa e calcular as barras apenas com itens fixos ou já posicionados no rascunho.

### Critérios de aceite

- Iniciar do zero deixa fora do gráfico todos os itens balanceáveis e preserva a periodicidade de cada um.
- Itens `1P` permanecem protegidos e podem ser exibidos/ocultados como camada-base.
- O Book abre por botão próprio e a aba da parada abre ao clicar na barra.
- Pesquisa parcial por código de plano filtra enquanto se digita.
- Chips de ciclo refletem dinamicamente os ciclos existentes no projeto.
- Arrastar para uma parada válida atualiza gráfico e indicadores imediatamente.
- Retornar ao Book desconta a carga e marca o item como pendente.
- Fechar e reabrir o sistema recupera exatamente o rascunho e seus filtros essenciais.
- O automático, no modo recomendado, não altera nenhum item marcado como Manual.
- Desfazer/Refazer funciona para movimentos individuais e em lote.
- Um projeto com milhares de itens mantém pesquisa, rolagem e drops responsivos.
- Nenhuma ação do rascunho altera o cenário oficial antes de **Concluir balanceamento**.

### Entrega sugerida em etapas

1. Sessão em rascunho, estado Pendente/Manual e autosave.
2. Book lateral com pesquisa, filtros e indicadores de progresso.
3. Drag-and-drop Book → gráfico e parada → Book, com atualização incremental.
4. Seleção e movimentação em lote, Desfazer/Refazer persistente.
5. Automático parcial preservando itens manuais.
6. Otimizações de desempenho, atalhos e métricas de produtividade.

## 4. Regras operacionais entre ciclos diferentes e regra de exclusão

**Status:** implementado nesta rodada, inclusive encontros entre ciclos e exclusão obrigatória/preferencial.

### Problema atual

As regras operacionais exigem que todos os itens selecionados tenham a mesma periodicidade. Essa restrição impede combinações reais de manutenção, nas quais planos de ciclos diferentes podem se encontrar em determinadas paradas.

Exemplos:

- um item `3P` pode ser executado junto com um `6P` nas ocorrências do plano `6P`;
- um item `2P` pode ser executado junto com um `4P` nas ocorrências do plano `4P`;
- planos de outros ciclos podem coincidir periodicamente conforme suas fases e o mínimo múltiplo comum dos ciclos.

### Novos comportamentos de regra

Ampliar o campo **Comportamento** para oferecer:

- **Executar juntos — mesma fase:** comportamento atual para itens de ciclos iguais; todas as ocorrências coincidem.
- **Executar juntos — quando os ciclos se encontram:** permite ciclos diferentes e alinha as fases para maximizar as ocorrências comuns.
- **Não executar juntos:** impede que os itens selecionados apareçam na mesma parada dentro do horizonte do cenário.
- **Executar em sequência:** preserva a regra existente para distribuir itens em fases sucessivas, quando aplicável.

A interface deve usar nomes simples. Uma apresentação recomendada é manter **Executar juntos** e, quando houver ciclos diferentes na seleção, explicar automaticamente: “O item de ciclo menor continuará nas demais paradas; as ocorrências do ciclo maior serão alinhadas sempre que possível.”

### Semântica de “Executar juntos” com ciclos diferentes

A regra não altera a periodicidade dos itens. Ela ajusta somente suas fases para produzir encontros válidos.

- Se o ciclo mais longo for múltiplo do menor, todas as ocorrências do ciclo mais longo devem coincidir com ocorrências do ciclo menor. Ex.: `3P + 6P` e `2P + 4P`.
- O item mais frequente continuará aparecendo também nas paradas intermediárias determinadas por seu próprio ciclo.
- Se os ciclos não forem múltiplos, o sistema deve calcular as coincidências pelo mínimo múltiplo comum e alinhar as fases para maximizar os encontros dentro do horizonte.
- A prévia da regra deverá mostrar em quais paradas os itens coincidirão antes de aplicar o balanceamento.
- O balanceador deverá tratar a coincidência definida como restrição obrigatória, e não apenas como bônus de similaridade.

Exemplo em 12 paradas:

- item `3P`: `P1, P4, P7, P10`;
- item `6P`: `P1, P7`;
- resultado: o `6P` executa junto com o `3P` em `P1` e `P7`; o `3P` mantém suas execuções adicionais em `P4` e `P10`.

### Regra “Não executar juntos”

Permitir selecionar dois ou mais itens que não podem compartilhar a mesma parada, por motivos como interferência operacional, segurança, acesso, recurso exclusivo ou indisponibilidade simultânea.

- Durante o balanceamento automático, qualquer candidato que gere coincidência proibida deve ser descartado.
- No balanceamento manual, uma parada inválida deve aparecer bloqueada durante o arraste, com a identificação da regra conflitante.
- Se uma alteração posterior criar conflito, o sistema deve impedir a gravação ou solicitar a correção, nunca violar silenciosamente a regra.
- A regra deve funcionar entre ciclos iguais e diferentes, desde que exista uma combinação de fases capaz de evitar coincidências no horizonte considerado.
- O painel de resultado deve informar quantos conflitos foram evitados e listar regras impossíveis de atender.

### Validação matemática e de viabilidade

Antes de salvar ou executar uma regra, calcular as ocorrências de cada ciclo e verificar se ela é possível:

- `1P` encontra todos os demais ciclos em todas as suas ocorrências; portanto, não pode participar de **Não executar juntos** com um item ativo no mesmo horizonte.
- Ciclos iguais podem executar juntos pela mesma fase ou separados por fases distintas, quando o ciclo oferece posições suficientes.
- Ciclos em que um é múltiplo do outro, como `3P/6P` e `2P/4P`, podem ser alinhados ou, conforme as fases disponíveis, separados.
- Ciclos coprimos, como `2P/3P`, inevitavelmente se encontram ao longo de um ciclo completo de `6P`; uma proibição total poderá ser inviável dependendo do horizonte.
- Para mais de dois itens, validar o conjunto completo, não apenas cada par isoladamente.
- Considerar o horizonte do cenário na prévia, mas alertar quando uma solução válida apenas no horizonte atual produzir conflito em paradas futuras.

Quando a regra for inviável, a mensagem deve explicar claramente a causa e sugerir alternativas, por exemplo:

> Não é possível impedir completamente o encontro entre os ciclos 2P e 3P ao longo de 12 paradas. Use uma restrição por parada específica ou reveja um dos ciclos.

### Regras obrigatórias versus preferenciais

Cada regra operacional deverá ter um nível:

- **Obrigatória:** nenhuma solução que viole a regra pode ser aplicada.
- **Preferencial:** o algoritmo tenta cumprir, mas pode separar ou aproximar os itens para evitar sobrecarga; toda exceção deve aparecer no resultado.

Para **Não executar juntos**, o padrão recomendado é **Obrigatória**. Para **Executar juntos**, o usuário pode escolher entre obrigatória e preferencial.

### Experiência de uso

- Remover a mensagem fixa “Itens de planos diferentes devem possuir a mesma periodicidade”.
- Mostrar chips dos ciclos selecionados e uma explicação dinâmica da compatibilidade.
- Exibir uma mini prévia das ocorrências comuns ou proibidas (`P1`, `P7` etc.).
- Avisar imediatamente, ainda na montagem da regra, se a combinação for impossível.
- Permitir pesquisar itens por identificador, descrição, equipamento e código do plano.
- Exibir no Book e na lista da parada ícones de “devem executar juntos” e “não podem executar juntos”.
- Ao arrastar um item que participa de uma regra obrigatória, oferecer movimentar automaticamente todo o grupo quando necessário.

### Integração com os balanceamentos manual e automático

- O automático deverá montar candidatos de fase considerando primeiro todas as regras obrigatórias.
- Itens ligados por **Executar juntos obrigatório** serão avaliados como um grupo, mesmo quando tiverem ciclos diferentes.
- Itens ligados por **Não executar juntos obrigatório** nunca poderão compartilhar uma ocorrência dentro do horizonte.
- Ao balancear somente os pendentes, regras que envolvam itens já fixados manualmente deverão usar essas posições como restrição para os pendentes.
- Se um item manual fixo tornar uma regra impossível, o sistema deverá indicar qual item precisa ser desbloqueado, sem movê-lo automaticamente.
- No manual, as barras válidas e inválidas devem ser calculadas em tempo real durante o arraste.

### Alterações técnicas previstas

- Substituir a validação de “mesma periodicidade” por um solucionador de compatibilidade baseado em ciclo, fase, máximo divisor comum e mínimo múltiplo comum.
- Representar regras por ocorrências exigidas/proibidas, nível obrigatório/preferencial e horizonte de validação.
- Persistir o tipo, o nível e o diagnóstico de compatibilidade da regra.
- Aplicar as mesmas validações no servidor, mesmo que a interface já tenha validado.
- Incluir violações e exceções de regras na função de pontuação, na prévia e na auditoria.

### Critérios de aceite

- Permitir criar uma regra válida entre `3P` e `6P`, alinhando todas as ocorrências do `6P` com o `3P` sem modificar nenhum ciclo.
- Permitir o mesmo comportamento entre `2P` e `4P`.
- Mostrar previamente as paradas de encontro no horizonte selecionado.
- Impedir no automático e no manual uma coincidência coberta por **Não executar juntos obrigatório**.
- Recusar uma regra matematicamente impossível com explicação compreensível.
- Não permitir **Não executar juntos** entre `1P` e qualquer item ativo.
- Preservar regras ao salvar, fechar e reabrir o projeto.
- Testar combinações de ciclos iguais, múltiplos, não múltiplos, coprimos, grupos com mais de dois itens e horizontes diferentes.

## 5. Filosofia do Balanceamento Automático: Horizontal ou Vertical

**Status:** implementado nesta rodada com prévia comparativa e preferências salvas por projeto.

### Objetivo

Permitir que o usuário escolha a filosofia de construção do cenário automático conforme a necessidade operacional:

- **Horizontal — equilibrar todo o horizonte:** lógica atual, que distribui os itens considerando simultaneamente os saldos de HH de todas as paradas.
- **Vertical — preencher parada por parada:** percorre `P1`, `P2`, `P3` etc., priorizando completar cada parada até uma meta segura antes de avançar para a seguinte.

As duas filosofias devem respeitar periodicidades, fases válidas, regras operacionais, agrupamentos geográficos, itens fixos manualmente e limites de capacidade.

### Seletor na interface

Adicionar ao modal de Balanceamento Automático o campo **Estratégia de distribuição**:

- **Horizontal — menor desvio global** (recomendada para uniformidade);
- **Vertical — preencher por parada e sequência dos itens**.

Ao selecionar uma estratégia, mostrar uma descrição curta e uma ilustração simples do comportamento. A escolha deverá ser salva no cenário.

Para o modo vertical, exibir ainda:

- **Meta por parada:** média calculada, capacidade da equipe ou valor informado;
- **Tolerância:** percentual de HH permitido acima da meta;
- **Ordem de preenchimento:** crescente `P1 → Pn` como padrão, com possibilidade futura de escolher a parada inicial;
- **Respeitar sequência geográfica dos identificadores:** ativada por padrão.

### Cálculo da meta vertical

Calcular inicialmente o HH total projetado de todas as ocorrências no horizonte e dividir pela quantidade de paradas:

`Meta média = HH total projetado no horizonte / número de paradas`

Quando houver capacidade configurada por especialidade, a meta não poderá ignorar esses limites. O sistema deverá controlar simultaneamente:

- HH total da parada;
- HH e efetivo de mecânica, elétrica e solda;
- capacidade máxima configurada;
- tolerância vertical escolhida;
- impacto das recorrências nas paradas futuras.

### Funcionamento horizontal

- Avaliar o horizonte de forma global.
- Para cada item ou grupo, testar as fases permitidas.
- Priorizar menor GAP, menor desvio-padrão e menores picos.
- Distribuir conforme saldos de HH, periodicidades e regras.
- Usar a sequência geográfica e a família do plano como preferência ou obrigação, conforme configuração.
- Manter o comportamento atual quando essa opção estiver selecionada, garantindo compatibilidade com cenários existentes.

### Funcionamento vertical

1. Calcular a meta segura de todas as paradas antes de iniciar.
2. Ordenar os itens pendentes pelo identificador, preservando a sequência geográfica.
3. Selecionar `P1` como parada-foco.
4. Procurar, na ordem dos itens, grupos que possuam uma fase válida contendo `P1`.
5. Antes de aceitar cada grupo, projetar todas as suas recorrências no horizonte.
6. Aceitar somente se a inclusão não ultrapassar os limites das paradas futuras além da tolerância autorizada e não violar regras.
7. Quando nenhum próximo grupo compatível couber de forma segura, considerar `P1` concluída e avançar para `P2`.
8. Repetir até a última parada e executar uma etapa final de ajuste dos itens ainda pendentes.

Assim, “preencher P1” não significa olhar apenas para P1. Um item `3P` posicionado na fase de P1 também carrega `P4`, `P7`, `P10` etc.; todas essas ocorrências devem ser reservadas antes de confirmar a inclusão.

### Preservação da sequência dos itens

No vertical, a sequência por identificador será parte central da decisão:

- tentar consumir os itens na ordem geográfica original;
- tratar agrupamentos obrigatórios como um único bloco;
- evitar saltos na sequência quando houver alternativa compatível;
- permitir pular temporariamente um item que não caiba na parada-foco, sem bloqueá-lo definitivamente;
- registrar quantos saltos foram necessários e por qual motivo;
- retornar aos itens pulados na etapa final.

Para evitar uma solução ruim apenas por causa de um item grande, usar uma pequena janela de procura adiante na lista, configurada internamente. Isso mantém a sequência como prioridade sem transformar o processo em um encaixe rígido e ineficiente.

### Proteções do modo vertical

- Nunca ultrapassar capacidade rígida de uma especialidade.
- Nunca violar uma regra operacional obrigatória.
- Nunca alterar a periodicidade de um plano ou item.
- Não sobrecarregar silenciosamente paradas futuras para completar a parada atual.
- Itens `1P` entram como carga-base antes do cálculo das metas.
- Itens já balanceados manualmente entram como carga fixa quando o usuário escolher preservá-los.
- Se a meta média for matematicamente impossível devido a blocos grandes, regras ou recorrências, informar o melhor resultado possível e as causas.

### Tratamento dos itens restantes

Após percorrer verticalmente todas as paradas, alguns itens podem permanecer sem encaixe. O sistema deverá oferecer uma etapa final controlada:

- tentar encaixe pelo menor excesso global;
- permitir elevar a tolerância e recalcular;
- deixar os itens no Book como pendentes;
- ou, mediante confirmação, aplicar o horizontal somente sobre os restantes.

A opção recomendada será **Finalizar pendentes pelo menor impacto**, sem alterar itens já posicionados verticalmente.

### Prévia comparativa

Antes de aplicar, permitir calcular e comparar Horizontal e Vertical com os mesmos dados e regras. Mostrar de forma compacta:

| Indicador | Horizontal | Vertical |
|---|---:|---:|
| GAP máximo | valor | valor |
| Desvio-padrão | valor | valor |
| Pico de HH | valor | valor |
| Grupos geográficos preservados | valor | valor |
| Saltos na sequência | valor | valor |
| Itens pendentes | valor | valor |
| Violações obrigatórias | 0 | 0 |

O usuário poderá visualizar a distribuição antes de escolher qual cenário aplicar.

### Integração com regras e agrupamentos

A ordem de prioridade proposta para ambos os modos será:

1. integridade dos ciclos, fases e capacidades rígidas;
2. regras operacionais obrigatórias, incluindo executar juntos e não executar juntos;
3. itens posicionados manualmente e bloqueados;
4. agrupamento geográfico obrigatório;
5. objetivo da estratégia escolhida: equilíbrio global no Horizontal ou preenchimento sequencial seguro no Vertical;
6. agrupamentos preferenciais e similaridade de máquina;
7. critérios de desempate por GAP, desvio e pico.

### Alterações técnicas previstas

- Incluir `distribution_strategy = horizontal | vertical` nas APIs de prévia e aplicação.
- Separar o gerador de candidatos das funções de avaliação, para reutilizar as mesmas validações nos dois modos.
- Criar um solucionador vertical com parada-foco, reserva de recorrências futuras e janela de procura na sequência.
- Persistir meta, tolerância, ordem e estratégia utilizadas.
- Permitir executar os dois métodos em prévia sem alterar o banco.
- Registrar em auditoria a estratégia, metas, tolerâncias, itens pulados e etapa final aplicada.

### Critérios de aceite

- Horizontal reproduz o comportamento atual quando nenhuma nova regra estiver ativa.
- Vertical inicia em `P1`, segue até `Pn` e prioriza a ordem dos identificadores.
- Um item colocado em `P1` reserva corretamente todas as ocorrências futuras determinadas pelo seu ciclo.
- Nenhuma parada futura ultrapassa limite rígido para completar uma parada anterior.
- Regras obrigatórias e itens manuais bloqueados são respeitados nos dois modos.
- A meta e a tolerância usadas ficam visíveis no resultado.
- Itens sem encaixe permanecem identificados e podem voltar ao Book.
- A prévia permite comparar os dois cenários sem gravar alterações.
- Testes cobrem itens grandes, múltiplas especialidades, ciclos `1P` a `12P`, regras cruzadas, capacidade insuficiente e sequência geográfica.
