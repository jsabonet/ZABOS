# Plano de execução — SaaS de automação de vídeos curtos

## 1. Objectivo e âmbito

Entregar em 48 horas um MVP utilizável para criar vídeos verticais destinados a TikTok, Reels e Shorts. Em desenvolvimento local, o utilizador inicia uma geração síncrona sem serviços auxiliares; em produção, o pipeline é assíncrono e o resultado acompanha-se num player.

### Incluído no MVP

- Frontend Next.js com chat, estado da geração e player de vídeo.
- API Django REST Framework com autenticação, validação, histórico e autorização por utilizador.
- PostgreSQL para utilizadores, projectos e registos de geração.
- Um agente que devolve dados estruturados e validados para um único formato de vídeo.
- Renderização local no servidor com Remotion, Node.js e FFmpeg, executada fora do pedido HTTP.
- Armazenamento de ficheiros no disco do servidor, com a referência/caminho persistida no PostgreSQL.
- Estados de processamento, erros visíveis e possibilidade de voltar a consultar o histórico.

### Fora do âmbito das primeiras 48 horas

- Publicação automática nas redes sociais, agendamento e analytics.
- Editor de vídeo completo, múltiplos templates e colaboração em equipa.
- Pagamentos, planos e limites comerciais.
- Escala horizontal, armazenamento distribuído, CDN e garantias de alta disponibilidade.
- Prometer custo operacional total zero: a renderização não usa uma API de vídeo paga, mas servidor, armazenamento, largura de banda e chamadas ao modelo de IA podem ter custos.

## 2. Princípios de implementação

1. **Renderização local:** síncrona no modo de desenvolvimento; assíncrona em produção para não bloquear pedidos HTTP.
2. **Contratos explícitos:** o JSON do agente é validado por um schema antes de ser guardado ou enviado ao Remotion.
3. **Isolamento por utilizador:** todas as consultas e operações sobre gerações verificam a propriedade do registo.
4. **Execução segura:** usar argumentos de subprocesso sem `shell=True`, limitar duração e concorrência e não aceitar comandos ou caminhos fornecidos pelo utilizador.
5. **Uma composição, um template:** limitar o primeiro lançamento a um formato e uma composição vertical para caber no prazo.
6. **Falhas recuperáveis:** guardar estado, progresso, mensagens de erro sanitizadas e logs suficientes para diagnóstico.
7. **Custos transparentes:** não usar APIs de geração de vídeo; identificar separadamente os custos de IA, infraestrutura e licenciamento.

## 3. Arquitectura alvo

```text
Next.js
  ├─ autenticação e interface de chat
  ├─ consulta do estado/histórico
  └─ player <video>
        │ HTTPS / JSON
        ▼
Django REST Framework ───── PostgreSQL/SQLite
  ├─ autenticação e autorização
  ├─ validação do pedido e do JSON do agente
  ├─ criação do registo de geração
  ├─ modo local: agente e Remotion executados no próprio pedido HTTP
  └─ modo assíncrono (produção): publicação de tarefa
        │                                      │
        │                                      ▼
        │                              Celery worker ── Redis
        │                                      │
        └──────────────────┬───────────────────┘
                           ▼
               Remotion/Node/FFmpeg local
                           │
                           ▼
         Armazenamento local de media ── MP4 servido de forma autorizada
```

### Modos de execução

- **Desenvolvimento local:** `VIDEO_RENDER_MODE=inline` (predefinido com `DJANGO_DEBUG=true`). A API executa agente e renderização após guardar a geração; o pedido só responde quando terminar. Não requer Redis, Celery nem Docker.
- **Produção:** `VIDEO_RENDER_MODE=celery`. A API agenda a tarefa e devolve `202 Accepted`; o worker actualiza o registo para `processing`, `completed` ou `failed`. Instalar as dependências assíncronas e configurar Redis.

O modo inline é recusado quando `DJANGO_DEBUG=false`: renders longos ocupam um processo web e não devem receber tráfego de produção. Em produção, o worker deve ser um processo separado, ainda que no mesmo host.

### Integração Django–Remotion

- Definir o caminho do projecto Remotion por configuração de ambiente, não por input do utilizador.
- Validar os dados e escrever um ficheiro `props.json` temporário por geração.
- Invocar `npx remotion render <entry> <composition-id> <output> --props=<ficheiro>` com `subprocess.run`/`Popen` e uma lista de argumentos.
- Executar com `cwd` fixo no projecto Remotion, timeout, captura de saída e limites de concorrência.
- Não interpolar prompt, nome de ficheiro ou texto do utilizador numa shell command.
- Confirmar que o ficheiro de saída existe e tem tamanho válido antes de marcar como concluído.
- Preferir instalação e versão fixadas das dependências Node no servidor; evitar que `npx` descarregue versões inesperadas durante cada renderização.

## 4. Estrutura de projecto proposta

```text
repo/
├─ backend/
│  ├─ manage.py
│  ├─ config/
│  │  ├─ settings.py
│  │  ├─ urls.py
│  │  └─ celery.py
│  ├─ apps/
│  │  ├─ accounts/
│  │  └─ videos/
│  │     ├─ models.py
│  │     ├─ serializers.py
│  │     ├─ views.py
│  │     ├─ urls.py
│  │     ├─ tasks.py
│  │     └─ services/
│  │        ├─ agent.py
│  │        ├─ remotion.py
│  │        └─ schemas.py
│  └─ media/                    # saída local, fora do controlo de versão
├─ frontend/
│  ├─ app/
│  ├─ components/
│  └─ lib/
└─ remotion/
   ├─ src/
   │  ├─ Root.tsx
   │  ├─ compositions/ShortVideo.tsx
   │  └─ schemas/videoProps.ts
   └─ public/
```

Adaptar a estrutura à organização já existente em vez de duplicar aplicações ou configurações.

## 5. Modelo de dados e estados

### Entidades mínimas

- **User:** utilizador autenticado do Django.
- **VideoGeneration:**
  - `id` UUID como identificador público.
  - `user` FK para o proprietário.
  - `prompt` ou briefing original.
  - `agent_payload` JSONField com os dados validados usados no render.
  - `status`: `queued`, `processing`, `completed` ou `failed`.
  - `progress` opcional (0–100), se o progresso real puder ser obtido; não inventar percentagens.
  - `output_file` FileField ou caminho relativo do ficheiro.
  - `error_message` sanitizada, sem segredos nem stack traces expostos ao cliente.
  - timestamps `created_at`, `started_at`, `completed_at`.
  - opcional: duração, dimensões, versão do template e chave de idempotência.

### Regras de persistência

- Guardar no PostgreSQL os metadados e a referência relativa do media, não os bytes do MP4.
- Usar `FileField` e `MEDIA_ROOT` para manter o backend de armazenamento substituível.
- Criar migrações e índices para proprietário, estado e data de criação.
- Não permitir ao cliente alterar `user`, `status`, `output_file` ou o payload final de render.
- Definir uma política posterior de retenção e remoção; no MVP, documentar o limite de disco e monitorizá-lo.

## 6. Contrato do payload do agente

Estabelecer um schema versionado antes de integrar os componentes. Exemplo conceptual:

```json
{
  "schema_version": 1,
  "title": "Título do vídeo",
  "scenes": [
    {
      "text": "Texto curto do frame",
      "duration_seconds": 3,
      "background_color": "#101010",
      "image_url": null
    }
  ],
  "music": null
}
```

### Validações necessárias

- Campos obrigatórios, tipos, número máximo de cenas e limites de caracteres.
- Duração total dentro do limite do MVP.
- Cores em formato permitido; valores não arbitrários para estilos/CSS.
- Imagens provenientes de upload validado ou de uma origem permitida; não aceitar caminhos locais.
- Se for necessário descarregar imagens, bloquear URLs privadas/internas e impor limites de tamanho e timeout para reduzir risco de SSRF.
- Usar assets locais como fallback previsível, sem criar um resultado de sucesso quando o payload for inválido.
- Guardar o payload validado e versionado para permitir reproduzir uma geração.

## 7. API mínima

Prefixo proposto: `/api/v1/`.

| Método | Endpoint | Finalidade | Resposta esperada |
|---|---|---|---|
| `POST` | `/videos/` | Criar guião a partir do briefing | `201` (inline) ou `202` (fila), `id`/`status` |
| `GET` | `/videos/` | Listar histórico do utilizador | Lista paginada |
| `GET` | `/videos/{id}/` | Consultar estado e metadados | Estado actual |
| `POST` | `/videos/{id}/render/` | Aprovar payload e iniciar render | `200` (inline) ou `202` (fila) |
| `GET` | `/videos/{id}/file/` | Obter/servir o vídeo concluído | MP4 autorizado |

O Django chama o agente e valida a resposta estruturada. O payload fica em estado de rascunho até o utilizador rever e aprovar; só então o frontend o envia ao endpoint de renderização.

### Comportamento da criação

1. Autenticar e validar o utilizador e o briefing.
2. Criar um registo de geração.
3. Obter a resposta estruturada do agente e validá-la com o schema.
4. Persistir o payload como rascunho e expor a revisão ao utilizador.
5. Validar e persistir o payload aprovado no endpoint de renderização.
6. Executar localmente ou enfileirar o Remotion, conforme o modo configurado.

No modo local inline, o pedido de criação aguarda pelo guião e o pedido de render aguarda pelo MP4. No modo assíncrono, o worker actualiza separadamente os estados da criação do guião e do render.

## 8. Interface e experiência

- Página principal limpa: chat à esquerda e preview à direita, adaptável a ecrãs pequenos.
- Mostrar estados claros: a preparar guião, em fila, a renderizar, concluído e falhou.
- Separar a geração do agente da aprovação: permitir editar título, texto, duração e cor das cenas antes de iniciar o render.
- Actualizar o estado através de polling moderado (por exemplo, alguns segundos) enquanto `queued`/`processing`; parar ao concluir ou falhar. WebSockets ficam fora do MVP.
- Player `<video controls playsInline>` para o ficheiro concluído; indicar visualmente quando ainda não existe vídeo.
- Histórico recente com estado, data, título e acesso ao resultado.
- Biblioteca inicial de formatos narrativos e visuais: produto em destaque, tutorial rápido, antes/depois, lista de dicas e história da marca. A selecção orienta o agente e o Remotion; não representa promessa de viralidade.
- Tratar `401`, `403`, `404`, `429` e erros de validação sem mensagens genéricas de sucesso.
- Nunca construir URLs de ficheiros a partir de caminhos arbitrários fornecidos pelo browser.

## 9. Plano de execução — 48 horas

As horas são blocos de execução, não uma estimativa de disponibilidade contínua. Manter um corte de âmbito: no fim de cada bloco, o fluxo vertical deve continuar executável.

### Fase 0 — Preparação e decisões (0–2 h)

- Inspeccionar o repositório, identificar o que já existe e confirmar versões de Python, Django, Node e Remotion.
- Confirmar disponibilidade de PostgreSQL, Redis e FFmpeg no ambiente de alojamento.
- Verificar os termos/licença de Remotion para o uso comercial pretendido.
- Fixar um único template, duração máxima, resolução e origem de assets.
- Criar `.env.example`, manter segredos fora do repositório e registar as decisões essenciais no README existente.

**Saída:** ambiente conhecido, escopo fechado e comandos locais de arranque identificados.

### Fase 1 — Prova do motor de renderização (2–7 h)

- Implementar uma composição Remotion vertical 1080×1920, com FPS e duração definidos.
- Definir os tipos/schema das props partilhados conceptualmente entre Django e TypeScript.
- Criar um payload fixo de exemplo e gerar um MP4 local pela CLI.
- Validar proporção, legibilidade de texto, margens seguras e reprodução do ficheiro.
- Confirmar utilização de CPU/memória e dependências do browser headless/FFmpeg no host.

**Critério de saída:** um comando reproduz o MP4 de exemplo sem API externa de vídeo.

### Fase 2 — Backend, dados e contratos (7–14 h)

- Configurar PostgreSQL e o app Django de vídeos.
- Criar `VideoGeneration`, migrações, serializers, permissões e testes de propriedade.
- Implementar endpoints de criação, listagem e detalhe.
- Definir e testar o schema do payload; rejeitar dados incompletos/fora dos limites.
- Integrar autenticação mínima adequada ao frontend escolhido (por exemplo, sessão ou JWT), sem inventar dois mecanismos.

**Critério de saída:** utilizador autenticado cria e consulta um registo; outro utilizador não o consegue consultar.

### Fase 3 — Integração Remotion e execução local (14–23 h)

- Implementar o serviço de geração comum que recebe o UUID do registo e lê dados validados do banco.
- Implementar modo local inline, sem depender de Redis, Celery ou Docker.
- Criar directório/ficheiro temporário controlado para props e saída.
- Invocar Remotion com `cwd` e argumentos fixos, timeout e captura dos logs.
- Actualizar estados em sucesso e falha; limpar temporários em `finally`.
- Para produção, acrescentar o adaptador Celery/Redis e limitar concorrência segundo a memória/CPU real do servidor.
- Servir o MP4 de modo autorizado; não expor `MEDIA_ROOT` directamente se os vídeos forem privados.

**Critério de saída local:** chamada síncrona completa a geração e devolve o registo actualizado sem broker. **Critério de produção:** API devolve rapidamente e o worker completa o ficheiro, ou regista falha observável.

### Fase 4 — Agente e frontend funcional (23–34 h)

- Integrar a chamada ao modelo de IA com timeout, tratamento de falha e schema validado.
- Manter geração e render no worker Celery em produção; no modo local inline, o pedido aguarda a conclusão e apresenta o estado final.
- Implementar layout de chat + player, formulário de briefing e mensagens de estado.
- Fazer polling do endpoint de detalhe, apresentar histórico e carregar o MP4 concluído.
- Validar pedidos duplicados e evitar criar múltiplos renders por duplo clique/retry.

**Critério de saída:** um utilizador percorre o fluxo do briefing ao vídeo no browser sem intervenção manual.

### Fase 5 — Robustez e segurança operacional (34–41 h)

- Testar ownership, validação, estados inválidos, payload malformado e falhas do modelo/worker.
- Verificar que entradas não podem alterar comando, paths, composição ou destino de saída.
- Testar timeout, worker reiniciado, tarefa repetida e disco sem espaço de forma controlada.
- Aplicar limites no tamanho/duração do pedido e rate limit básico à criação.
- Garantir que logs não incluem tokens, prompts sensíveis desnecessários ou conteúdo de credenciais.
- Adicionar configuração e health checks para Django, PostgreSQL, Redis, worker e Remotion.

**Critério de saída:** falhas ficam explícitas e não deixam gerações permanentemente em processamento sem forma de diagnóstico.

### Fase 6 — Deploy e ensaio de lançamento (41–48 h)

- Preparar variáveis de ambiente, migrações, collectstatic, processo web, worker e Redis.
- Instalar dependências Node fixadas e validar execução como utilizador sem privilégios.
- Configurar armazenamento/media persistente e backups do PostgreSQL; definir limpeza/retention provisória.
- Executar uma geração de ponta a ponta no servidor com conteúdo representativo.
- Verificar TLS, autenticação, limites de recursos, espaço livre, logs e URL de reprodução.
- Fazer checklist de lançamento e documentar operação de reinício e diagnóstico.

**Critério de saída:** fluxo validado no host de destino e procedimento de recuperação conhecido.

## 10. Testes e critérios de aceitação

### Testes automatizados prioritários

- Modelos: transições de estado e propriedades obrigatórias.
- API: autenticação, validação, paginação e isolamento entre utilizadores.
- Tarefa: enfileiramento, sucesso, timeout, erro do subprocesso e repetição idempotente.
- Schema: payload válido, campos ausentes, duração excessiva, URLs/payloads inválidos.
- Remotion: render de integração com fixture pequena e confirmação de MP4 não vazio.
- Frontend: estados de carregamento, erro, concluído e reprodução do vídeo.

### Aceitação funcional

- Uma pessoa autenticada envia um briefing e recebe confirmação rápida com um ID consultável.
- A geração prossegue sem manter o pedido HTTP aberto.
- O agente produz dados aceites pelo schema ou uma falha é indicada claramente.
- O Remotion gera vídeo vertical 1080×1920 localmente, com as props esperadas.
- O histórico apresenta apenas gerações do utilizador autenticado.
- O vídeo concluído pode ser reproduzido pelo utilizador autorizado.
- Uma falha não é apresentada como sucesso e pode ser investigada pelos logs.

## 11. Riscos e mitigação

| Risco | Mitigação no MVP |
|---|---|
| Render excede CPU/RAM disponíveis | Limitar duração, resolução e concorrência; testar no host real |
| Worker cai ou reinicia | Tarefa idempotente, timeouts e estado persistido; rotina de recuperação |
| JSON do modelo inconsistente | Schema estrito, limites e falha explícita; não passar texto bruto para a CLI |
| Execução de comandos ou acesso a ficheiros indevidos | Argumentos em lista, `shell=False`, paths internos fixos e assets validados |
| Ficheiros privados expostos | Endpoint autorizado para servir/download; não revelar paths locais |
| Disco enche | Monitorização, limites de geração e política inicial de retenção |
| Dependência da rede durante o render | Fixar pacotes e pré-instalar browser/FFmpeg; não depender de downloads por render |
| Custos interpretados como zero total | Comunicar que zero se refere a APIs de geração de vídeo; estimar IA e alojamento separadamente |
| Licença incompatível com monetização | Confirmar termos actuais da Remotion antes do lançamento comercial |
| Submissão repetida pelo utilizador | Chave de idempotência ou controlo de pedido duplicado e botão desactivado durante envio |

## 12. Decisões a não adiar

- O sistema de autenticação usado pelo Next.js e Django.
- Se o vídeo é privado ou publicamente acessível por URL assinada.
- O modelo de IA e o custo/limite de chamadas; vídeo sem custo de API não significa IA sem custo.
- O limite de duração e tamanho do payload/ficheiro.
- O local persistente de media e o procedimento de limpeza.
- A licença e os termos comerciais aplicáveis ao Remotion.
- A capacidade real do servidor para executar Node, browser headless e FFmpeg.

## 13. Regra de corte para cumprir as 48 horas

Se o prazo apertar, preservar este fluxo completo: **briefing → payload válido → tarefa enfileirada → um template Remotion → MP4 reproduzível → histórico protegido**. Adiar publicação social, editor avançado, streaming de progresso, múltiplos templates, pagamentos e integrações secundárias. Não cortar autenticação, validação, isolamento de dados ou execução segura do subprocesso.
