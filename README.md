# Lume — MVP de criação de vídeos curtos

Aplicação inicial para converter um briefing em guião estruturado com IA e renderizar um MP4 vertical localmente com Remotion.

## Componentes

- `backend/`: Django REST Framework and PostgreSQL/SQLite.
- `frontend/`: Next.js com briefing, revisão do guião, pré-visualização e histórico.
- `remotion/`: composição 1080×1920 e renderização MP4 com Remotion/FFmpeg.

O render não usa uma API externa de geração de vídeo. O fornecedor de IA é compatível com Chat Completions e configurável; podem aplicar-se custos de IA, alojamento, armazenamento e largura de banda.

## Configuração local

Requisitos: Python 3.11+, Node.js 20.9+ e npm. O modo local usa SQLite, executa agente e render no próprio pedido HTTP e não requer Redis, Celery ou Docker. O pedido fica aberto até o MP4 estar pronto; use-o para desenvolvimento e testes manuais, não para tráfego concorrente.

### Django

```powershell
Copy-Item backend\.env.example backend\.env
# Preencher AGENT_API_KEY e AGENT_MODEL em backend\.env.
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Worker

Não é necessário iniciar um worker no modo local. Django lê `backend/.env` automaticamente, sem substituir variáveis já exportadas no ambiente. Não partilhar nem versionar o `.env`.

### Processamento assíncrono (opcional, produção)

Para evitar pedidos HTTP longos e permitir workers independentes, configurar Redis e Celery:

```powershell
pip install -r backend\requirements-async.txt
docker compose up -d redis
```

Definir `VIDEO_RENDER_MODE=celery` e `CELERY_BROKER_URL=redis://127.0.0.1:6379/0` no ambiente do backend. Iniciar o worker num terminal separado:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
celery -A config.celery:app worker --loglevel=INFO --pool=solo --concurrency=1
```

`--pool=solo` destina-se ao desenvolvimento em Windows. Em Linux, usar um pool suportado e limitar concorrência conforme os recursos do servidor.
Quando `DJANGO_DEBUG=false`, o modo predefinido é `celery`; o modo inline é recusado por segurança. Para produção, configurar PostgreSQL, TLS e armazenamento persistente.

### Logs do pipeline

O backend escreve no stdout eventos `generation_stage=...`, sempre associados ao `generation_id` depois de o projecto ser persistido. Os eventos cobrem validação, persistência, dispatch/fila, agente, imagens, narração, assets do Remotion, render e resposta HTTP, incluindo duração e contagens relevantes. Excepções inesperadas que resultam em HTTP 500 são também registadas com traceback completo pelo logger `config.api` e recebem um `request_id` na resposta JSON; use esse ID para localizar o traceback no terminal/log do processo Django. A saída do Remotion é capturada pelo subprocesso e a cauda do erro é escrita no log do backend. Ajustar o detalhe com `DJANGO_LOG_LEVEL` (`DEBUG`, `INFO`, `WARNING` ou `ERROR`); o padrão é `INFO`. Os briefings, prompts, payloads, credenciais e chaves não são incluídos nos eventos.

### Remotion

```powershell
cd remotion
npm install
```

Na primeira execução, Remotion pode descarregar o Chrome Headless Shell. Preparar e testar essa dependência no host, em vez de depender de uma descarga durante cada geração.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Abrir `http://localhost:3000`. A interface usa rotas navegáveis: `/projects`, `/create/templates`, `/create/themes`, `/create/briefing` e `/videos/<uuid>`. O login cria uma sessão Django armazenada na base de dados e identificada por cookie `HttpOnly`; a interface verifica a sessão ao abrir ou recarregar e não guarda a palavra-passe no browser. O cookie dura 14 dias por padrão (`SESSION_COOKIE_AGE`) e é invalidado ao terminar sessão. As operações de escrita usam proteção CSRF. Em produção, servir frontend e backend sob a mesma origem HTTPS e configurar `DJANGO_CSRF_TRUSTED_ORIGINS` com as origens públicas do frontend. Os botões de voltar/avançar do browser acompanham os passos.

As chamadas `/api/` são encaminhadas pelo Next.js para `http://127.0.0.1:8000`. Estas são rotas de API, não páginas: por exemplo, a renderização é iniciada por `POST /api/v1/videos/<uuid>/render/` com autenticação e payload; abrir esse URL na barra de endereços envia um `GET` e não inicia o processo. Para outro endereço do backend, definir `API_INTERNAL_URL` no ambiente do processo Next.js.

## Configuração do agente

Definir no ambiente do backend (não colocar segredos no frontend nem no controlo de versões):

```text
AGENT_API_BASE_URL=https://api.openai.com/v1/chat/completions
AGENT_API_KEY=<chave do fornecedor>
AGENT_MODEL=<modelo que suporta JSON mode>
AGENT_TIMEOUT=45
```

O endpoint e o modelo devem ser compatíveis com o formato Chat Completions e `response_format: {"type":"json_object"}`. A resposta é validada pelo schema antes de ser renderizada. Sem a chave/modelo configurados, a geração falha com estado e mensagem explícitos.

Outras variáveis úteis: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `CELERY_BROKER_URL`, `MEDIA_ROOT`, `REMOTION_PROJECT_DIR`, `REMOTION_RENDER_TIMEOUT`, `NODE_EXECUTABLE`, `POLLINATIONS_API_KEY`, `POLLINATIONS_TIMEOUT` e `POLLINATIONS_MAX_IMAGE_BYTES`.

## Fluxo e API

1. O utilizador autentica-se com a conta Django.
2. O utilizador escolhe um formato narrativo e um tema visual. `POST /api/v1/videos/` recebe, por exemplo, `{"prompt":"...","template_id":"tutorial","visual_theme_id":"cinematic_stories"}`. O formato orienta o agente; o tema não altera o guião.
3. O backend valida e guarda o JSON como rascunho. No modo inline responde `201` depois de criar o guião; no modo Celery responde `202` e o frontend acompanha os estados.
4. O utilizador revê título, texto, duração, cor e direcção visual; pode escolher a transição de entrada de cada cena e carregar imagens/clips ou áudio de narração.
5. `POST /api/v1/videos/<uuid>/render/` recebe `{"payload":{...},"visual_theme_id":"kinetic_editorial"}`, valida o guião e inicia o Remotion. Uma geração concluída pode ser novamente renderizada com outro tema, sem gerar outro guião. No modo inline responde após terminar; no modo Celery devolve `202`.
6. `GET /api/v1/videos/` e `GET /api/v1/videos/<uuid>/` consultam o histórico/estado do utilizador autenticado.
7. `GET /api/v1/videos/<uuid>/file/` transmite o MP4 apenas ao proprietário.
8. `POST /api/v1/videos/assets/` recebe multipart (`kind` e `file`) para imagem, vídeo ou áudio. `GET /api/v1/videos/assets/<uuid>/file/` transmite o asset apenas ao proprietário. Os assets são copiados para uma pasta temporária do Remotion durante o render e removidos no final.

Os cinco formatos narrativos são `showcase` (produto em destaque), `tutorial` (tutorial rápido), `before_after` (antes e depois), `quick_tips` (lista de dicas) e `brand_story` (história da marca). São independentes dos temas visuais e orientam a estrutura do guião.

O Visual Theme Engine oferece `cinematic_stories` (composição documental e movimento contemplativo), `kinetic_editorial` (tipografia cinética e ritmo rápido) e `modern_product` (apresentação premium com espaço negativo). O tema é guardado em `VideoGeneration.visual_theme_id` e enviado como propriedade da composição Remotion, fora do JSON de conteúdo. Assim, a mesma lista de cenas pode ser renderizada em temas diferentes sem voltar a chamar o agente. Gerações anteriores à migração usam `cinematic_stories`.

O agente sugere um `visual_prompt` descritivo em inglês e movimento por cena, mas não gera código, caminhos, IDs de ficheiros nem URLs de fornecedores. Quando uma cena ainda não tem media, o backend pede uma imagem vertical ao endpoint de geração de imagem do Pollinations.ai, valida o ficheiro e guarda-o no armazenamento privado do utilizador. Os assets são associados por ID e limitados ao proprietário; o Remotion usa a cópia local durante o render e não depende da disponibilidade de URLs externas. A integração responde à indisponibilidade de acesso à pesquisa Pexels neste projecto, não a uma descontinuação universal do Pexels. Camadas e narração usam `schema_version: 2`; o schema 1 continua compatível com guiões já guardados. O plano visual opcional permite configurar movimento de câmara e transições de entrada por cena (`cut`, `fade`, `wipe_left`, `wipe_right`); sem plano, o Remotion mantém o comportamento dos payloads anteriores. A composição também pode sobrepor segmentos de legenda. A narração pode ser carregada ou sintetizada com Piper local, se `PIPER_EXECUTABLE` e `PIPER_MODEL_PATH` estiverem configurados. Sem Piper, a renderização normal e a narração carregada continuam disponíveis; a opção de síntese local devolve um erro explícito.

Na fase de criação do guião, cada cena sem media e com `visual_prompt` pode receber uma imagem gerada pelo modelo `black-forest-labs/flux.1-schnell` através do endpoint `https://gen.pollinations.ai/image/{prompt}`. A requisição usa dimensões verticais (1080×1920) e uma seed única por cena. A direcção visual partilhada pelo guião e o tema visual seleccionado são combinados com a descrição específica da cena para manter paleta, luz e linguagem fotográfica coerentes sem repetir o mesmo assunto. O prompt resultante e a seed são guardados no registo do asset; não são apresentados créditos de fotógrafo. O serviço documenta actualmente a geração de imagens por URL sem chave; `POLLINATIONS_API_KEY` é opcional para autenticação quando necessária/configurada. A imagem é descarregada, validada e guardada localmente antes de ser associada à cena. Sem descrição visual ou perante timeout, erro do fornecedor ou ficheiro inválido, o guião é preservado e a interface recebe uma mensagem de estado. Assets carregados pelo utilizador ou já associados não são substituídos. A geração depende de um serviço externo, cuja disponibilidade, limites, modelos e condições podem mudar; não é garantido um nível de serviço ou custo futuro.

O agente recebe requisitos de Visual Intelligence: interpretar o conceito narrativo em vez de procurar palavras genéricas, descrever sujeito, acção, ambiente, enquadramento, foco e luz, e variar os elementos entre cenas sob uma direcção visual comum. Não existe limite fixo de cenas, mas a duração total está limitada a 60 segundos por enquanto; cada cena deve ter duração positiva em segundos. O ecrã final opcional também conta para esse limite. O backend valida o total e o editor limita a duração disponível ao tempo restante. Uma resposta que não passe a validação recebe uma tentativa de correcção antes de o projecto ser marcado como falhado. A direcção visual fica visível ao utilizador no editor. O fluxo automático actual gera imagens com Pollinations; não gera clips de vídeo por IA. Clips carregados pelo utilizador continuam suportados e são animados pelo Remotion. O editor permite escolher por cena tratamento de imagem (`natural`, `warm`, `cool`, `monochrome`, `film`), animação tipográfica (`fade_up`, `pop`, `typewriter`, `word_reveal`, `none`) e motion graphics (`accent_line`, `orbit`, `corner_frame`, `none`). O ecrã final configurável contém título, mensagem, CTA e duração de 1 a 10 segundos; payloads anteriores sem estas opções continuam suportados. A avaliação de qualidade deve incluir briefings de temas diferentes e revisão humana de relevância e continuidade; testes automatizados simulam o fornecedor e não substituem essa avaliação.

Configuração opcional de voz local:

```text
PIPER_EXECUTABLE=piper
PIPER_MODEL_PATH=C:\models\pt_PT-model.onnx
PIPER_TIMEOUT=180
POLLINATIONS_API_KEY=<opcional>
POLLINATIONS_TIMEOUT=120
POLLINATIONS_MAX_IMAGE_BYTES=15728640
```

O modelo Piper é instalado e mantido no próprio servidor; não há chamada a serviços pagos de TTS. A geração de imagens Pollinations é externa e está sujeita à disponibilidade, limites, modelos e termos actuais do fornecedor. Os formatos de áudio aceites para upload são MP3, M4A, WAV e OGG; imagens JPG, PNG e WebP; vídeo MP4, MOV e WebM. Cada ficheiro carregado pelo utilizador tem limite de 100 MB.

Os estados visíveis incluem `queued`, `writing_script`, `draft`, `render_queued`, `rendering`, `completed` e `failed`. A interface apresenta o estado real do backend, sem estimar percentagens durante o render.

O frontend MVP usa HTTP Basic Auth e mantém a credencial apenas em memória durante a sessão do browser. Usar HTTPS em qualquer ambiente partilhado e substituir por sessão/JWT antes de disponibilizar a utilizadores externos.

## Validação

```powershell
cd backend
python manage.py check
python manage.py test videos
```

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```
