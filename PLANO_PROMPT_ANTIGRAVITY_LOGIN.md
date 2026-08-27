# Plano de implementação e prompt técnico — Tela de Login PM13/PM11

## Objetivo

Criar a arte e a implementação frontend de uma tela de login profissional para o sistema local/web PM13/PM11, preservando a identidade visual já existente. A entrega deve estar pronta para futura integração com as rotas reais de autenticação, mas não deve simular segurança apenas no frontend nem implementar credenciais fixas.

## Contexto técnico do sistema

- Aplicação servida por Python com `BaseHTTPRequestHandler`.
- Frontend atual em HTML, CSS e JavaScript puro, sem React, Vue, Bootstrap ou bundler.
- Documento principal: `static/index.html`.
- Scripts principais em `static/js/`.
- Módulos PM11 em `static/js/pm11/`.
- O sistema possui dois modos: PM13 — Planos de Manutenção e PM11 — Inspeções PM11.
- Identidade atual: sidebar verde muito escuro, destaque verde-limão, superfícies claras, cartões brancos e tipografia corporativa compacta.
- A tela deve funcionar em servidor remoto, desktop e dispositivos menores.

## Prompt técnico para o Antigravity

Copie integralmente o conteúdo desta seção para o Antigravity:

---

Você é um designer de produto sênior e engenheiro frontend especializado em aplicações industriais corporativas. Crie e implemente uma tela de login completa, elegante, responsiva e acessível para um sistema chamado **PM13 Local**, que reúne dois módulos:

1. **PM13 — Planos de Manutenção**
2. **PM11 — Inspeções PM11**

Trabalhe diretamente sobre o projeto existente. Antes de editar, examine `static/index.html`, os estilos carregados por ele e os componentes visuais atuais para reutilizar tokens, cores, espaçamentos e tipografia. Não introduza framework, biblioteca externa, CDN, fonte remota, npm ou processo de build. Use somente HTML5, CSS e JavaScript puro compatíveis com a arquitetura atual.

### Resultado visual esperado

Desenvolva uma tela corporativa industrial contemporânea, sóbria e confiável. Ela deve parecer parte natural do sistema atual, não uma página genérica ou um template SaaS. Use como referências visuais internas:

- Verde-limão institucional próximo de `#84BD00` para ações e indicadores.
- Verde muito escuro próximo de `#14230F` ou a variável já usada na sidebar.
- Fundo claro próximo de `#F3F6F1`.
- Texto principal próximo de `#25302A`.
- Texto secundário em cinza esverdeado.
- Bordas discretas, sombras suaves e raios entre 8 e 14 px.
- Aparência técnica, limpa e operacional.

Evite excesso de gradientes, ilustrações abstratas, glassmorphism forte, ícones decorativos desnecessários e aparência de aplicativo financeiro. A interface deve comunicar manutenção industrial, organização, segurança e continuidade operacional.

### Composição da página

Em telas desktop, use uma composição dividida:

- Painel institucional à esquerda, ocupando aproximadamente 42% da largura.
- Formulário de acesso à direita, ocupando aproximadamente 58%.
- Altura mínima de `100dvh` com fallback para `100vh`.

#### Painel institucional esquerdo

O painel esquerdo deve usar fundo verde muito escuro e conter:

- Marca textual `PM13 Local`, com `PM13` em verde-limão e `Local` em branco suave.
- Título principal: `Planejamento e inspeção em um só ambiente.`
- Texto curto explicando que o acesso reúne os módulos PM13 e PM11.
- Dois pequenos cartões ou linhas de produto:
  - badge `PM13`, título `Planos de Manutenção` e descrição curta;
  - badge `PM11`, título `Inspeções PM11` e descrição curta.
- Uma composição gráfica discreta inspirada em calendário de paradas, linhas de planejamento, equipamentos ou checklist técnico. Faça isso apenas com CSS/SVG inline simples; não use imagens externas.
- Rodapé com texto de segurança: `Ambiente restrito a usuários autorizados`.

O painel institucional deve ter contraste adequado e não competir visualmente com o formulário.

#### Área direita e cartão de login

Centralize um cartão de acesso com largura ideal entre 400 e 460 px. O cartão deve conter:

- Título `Acessar o sistema`.
- Subtítulo `Informe suas credenciais para continuar.`
- Campo `Usuário ou e-mail`.
- Campo `Senha`.
- Botão para mostrar/ocultar senha, com `aria-label` atualizado dinamicamente.
- Checkbox `Manter conectado`, preparado para ser omitido posteriormente caso a política de segurança não permita sessão persistente.
- Link visual `Esqueci minha senha`, inicialmente preparado para abrir orientação ao usuário, sem inventar recuperação funcional.
- Botão principal `Entrar`.
- Área reservada para mensagens de erro, sucesso ou sessão expirada.
- Pequeno texto abaixo do formulário: `O acesso e as ações realizadas podem ser registrados para fins de auditoria.`

Inclua um indicador de ambiente na parte superior da área direita, por exemplo `AMBIENTE SEGURO`, acompanhado de um ícone SVG inline discreto.

### Estrutura de arquivos

Implemente preferencialmente desta forma:

- Criar `static/css/login.css` com todos os estilos exclusivos da autenticação.
- Criar `static/js/auth.js` para controle da interface e futura integração da autenticação.
- Alterar `static/index.html` somente nos pontos necessários para:
  - carregar `css/login.css`;
  - inserir a camada/tela `#login-view` antes do shell principal;
  - identificar o shell da aplicação com `#app-shell` ou reutilizar um contêiner equivalente;
  - carregar `js/auth.js` antes da inicialização principal quando necessário.

Não mova nem reescreva grandes blocos existentes sem necessidade. Preserve integralmente PM13 e PM11.

### Estrutura HTML requerida

Use HTML semântico e uma estrutura equivalente a:

```html
<main id="login-view" class="login-view" aria-labelledby="login-title">
  <section class="login-brand-panel" aria-label="PM13 e PM11">
    <!-- marca, mensagem institucional e módulos -->
  </section>

  <section class="login-form-panel">
    <div class="login-card">
      <form id="login-form" novalidate>
        <!-- usuário, senha, opções, erro e submit -->
      </form>
    </div>
  </section>
</main>

<div id="app-shell" hidden>
  <!-- aplicação existente -->
</div>
```

Se envolver todo o shell existente em um novo elemento for arriscado, use classes no `body` para alternar os estados `auth-pending`, `auth-required` e `auth-authenticated`, sem quebrar o layout atual.

### Contrato JavaScript

Organize `static/js/auth.js` como módulo global compatível com os scripts atuais:

```javascript
window.Auth = {
  state: 'pending',
  user: null,
  init(),
  checkSession(),
  login(credentials),
  logout(),
  showLogin(message),
  showApplication(user),
  setLoading(isLoading),
  showError(message)
};
```

Prepare a integração com estes endpoints futuros:

```text
GET  /api/auth/me
POST /api/auth/login
POST /api/auth/logout
```

Formato futuro esperado para login:

```json
{
  "login": "usuario@empresa.com",
  "password": "senha-informada",
  "remember": false
}
```

Resposta esperada:

```json
{
  "user": {
    "id": 1,
    "name": "Nome do Usuário",
    "login": "usuario@empresa.com",
    "role": "USER"
  }
}
```

Regras obrigatórias do JavaScript:

- Enviar requisições com `credentials: 'same-origin'`.
- Nunca armazenar senha.
- Nunca armazenar token de sessão no `localStorage` ou `sessionStorage`.
- A futura sessão deve ser mantida pelo servidor em cookie `HttpOnly`.
- Tratar `401` mostrando novamente a tela de login.
- Tratar `403` com mensagem de acesso negado, sem apagar a sessão automaticamente.
- Desabilitar os campos e o botão durante o envio.
- Exibir spinner pequeno e texto `Entrando...` durante o carregamento.
- Impedir envio duplicado.
- Remover mensagens de erro quando o usuário começar a corrigir os campos.
- Não revelar se o usuário ou a senha individualmente estão errados; usar `Usuário ou senha inválidos.`.
- Não implementar credenciais falsas, usuário padrão no JavaScript ou autenticação apenas visual.

Enquanto o backend real ainda não estiver implementado, crie um modo de apresentação explicitamente marcado no código como `AUTH_UI_PREVIEW`, desativado por padrão. O modo normal não pode liberar o sistema sem resposta autenticada do servidor.

### Estados da interface

Implemente visualmente todos os estados:

1. Inicialização/verificação de sessão.
2. Formulário vazio.
3. Campos focados.
4. Campo inválido.
5. Credenciais inválidas.
6. Servidor indisponível.
7. Envio em andamento.
8. Sessão expirada.
9. Usuário autenticado e transição para a aplicação.
10. Botão mostrar/ocultar senha.
11. Caps Lock ativo, com aviso discreto se tecnicamente viável.

Para erros, use uma região com `role="alert"` e `aria-live="polite"`. Não use `alert()` do navegador.

### Validação do formulário

- Usuário/e-mail obrigatório, máximo de 160 caracteres.
- Senha obrigatória, máximo de 256 caracteres no frontend.
- Não remova espaços internos da senha.
- Permita Enter para envio.
- Leve o foco ao primeiro campo inválido.
- Use `autocomplete="username"` e `autocomplete="current-password"`.
- Use `type="password"` por padrão.

### Responsividade

- Desktop acima de 960 px: layout em duas colunas.
- Tablet: painel institucional menor e formulário preservado.
- Abaixo de 760 px: uma coluna; transformar o painel institucional em cabeçalho compacto.
- Abaixo de 420 px: cartão sem margens excessivas, campos e botão com largura total.
- Considerar teclado virtual e usar `100dvh`.
- Não gerar rolagem horizontal em nenhuma largura.

### Acessibilidade

- Contraste WCAG AA.
- Ordem de tabulação natural.
- Foco visível em todos os elementos interativos.
- Labels reais associados aos inputs.
- SVGs decorativos com `aria-hidden="true"`.
- Respeitar `prefers-reduced-motion`.
- Não depender somente de cor para indicar erro.
- Tamanho mínimo confortável para áreas clicáveis.

### Animações

Use animações discretas:

- Fade/slide de entrada entre 160 e 240 ms.
- Transição do botão e campos entre 120 e 180 ms.
- Nenhum movimento contínuo.
- Desabilitar movimentos não essenciais com `prefers-reduced-motion: reduce`.

### Segurança visual e funcional

- Não mostrar lista de projetos antes da autenticação.
- Não inicializar módulos PM13/PM11 enquanto a sessão estiver pendente ou inválida.
- Não considerar ocultação CSS como proteção; documentar que a autorização final pertence ao backend.
- Evitar mensagens com detalhes técnicos do servidor.
- Preparar o cabeçalho do sistema para mostrar nome do usuário e ação `Sair` após autenticação, mantendo o seletor PM13/PM11.

### Preservação do sistema atual

- Não quebrar o seletor PM13/PM11.
- Não alterar rotas de importação, balanceamento, projetos ou histórico nesta tarefa visual.
- Não renomear APIs existentes.
- Não duplicar listeners a cada troca de modo.
- Não sobrescrever `window.onload` ou os manipuladores globais já existentes.
- Usar `DOMContentLoaded` com segurança ou inicialização explícita e idempotente.
- Manter compatibilidade com os navegadores Chromium modernos usados no ambiente corporativo.

### Entrega esperada

Entregue:

1. Tela de login implementada e integrada visualmente.
2. CSS isolado e organizado por tokens, layout, componentes, estados e responsividade.
3. JavaScript idempotente e preparado para API real.
4. Comentários somente onde explicarem decisões não óbvias.
5. Resumo dos arquivos alterados.
6. Instruções para ativar a integração quando os endpoints de autenticação existirem.
7. Capturas desktop e mobile, se o ambiente permitir.
8. Relatório de verificação sem erros no console.

### Critérios de aceite

- A tela parece nativa do PM13/PM11.
- O usuário não vê o sistema antes da autenticação.
- Formulário funciona por mouse e teclado.
- Estados de erro e carregamento são claros.
- Layout funciona em 1440 px, 1024 px, 768 px, 390 px e 320 px.
- Não existem dependências externas.
- Nenhuma senha ou token é salvo no armazenamento do navegador.
- A aplicação atual continua funcionando após autenticação válida.
- O seletor PM13/PM11 continua funcionando.
- Não há erros ou rejeições não tratadas no console.
- A implementação visual não é apresentada como segurança concluída sem o backend.

Antes de finalizar, inspecione o resultado no navegador e corrija sobreposição, foco, contraste, responsividade e qualquer erro de console. Preserve o trabalho existente e informe precisamente cada arquivo criado ou alterado.

---

## Plano de implementação posterior ao trabalho visual

### Etapa 1 — Arte isolada

- Criar os arquivos de estilo e comportamento visual.
- Inserir a tela no documento principal sem remover o shell existente.
- Validar desktop, tablet e celular.

### Etapa 2 — Backend real

- Criar tabelas `users`, `sessions` e `project_members`.
- Armazenar senhas com Argon2 ou bcrypt.
- Implementar `/api/auth/login`, `/api/auth/logout` e `/api/auth/me`.
- Utilizar cookie de sessão `HttpOnly`, `SameSite=Lax` e `Secure` sob HTTPS.

### Etapa 3 — Inicialização protegida

- Aguardar `/api/auth/me` antes de inicializar PM13 e PM11.
- Exibir o shell somente após sessão válida.
- Retornar ao login quando a sessão expirar.

### Etapa 4 — Isolamento de dados

- Filtrar projetos pelo usuário autenticado.
- Conferir autorização no backend em todas as rotas que recebem `project_id`.
- Retornar `401` para ausência de sessão e `403` para falta de permissão.

### Etapa 5 — Administração

- Criar gestão de usuários e vínculos com projetos.
- Adicionar nome do usuário e logout ao cabeçalho.
- Registrar `user_id` em auditoria, importações e alterações.

### Etapa 6 — Testes

- Testar login válido e inválido.
- Testar expiração e logout.
- Confirmar que um usuário não acessa projeto de outro alterando o `project_id` manualmente.
- Confirmar que nenhuma tela ou API protegida vaza dados antes da autenticação.
- Executar regressão completa de PM13, PM11 e importação.

## Observação de segurança

A tela criada por este prompt é a camada visual e o ponto de integração. O isolamento entre usuários somente estará concluído quando a autenticação, a sessão e a autorização por projeto também forem implementadas no backend.
