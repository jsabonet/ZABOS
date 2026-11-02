# Lume — MVP de criação de vídeos curtos

Aplicação inicial para converter um briefing em guião estruturado com IA e renderizar um MP4 vertical localmente com Remotion.

## Componentes

- `backend/`: Django REST Framework and PostgreSQL/SQLite.
- `frontend/`: Next.js com interface de chat, histórico e player.
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

Abrir `http://localhost:3000`. As chamadas `/api/` são encaminhadas pelo Next.js para `http://127.0.0.1:8000`. Para outro endereço, definir `API_INTERNAL_URL` no ambiente do processo Next.js.

## Configuração do agente

Definir no ambiente do backend (não colocar segredos no frontend nem no controlo de versões):

```text
AGENT_API_BASE_URL=https://api.openai.com/v1/chat/completions
AGENT_API_KEY=<chave do fornecedor>
AGENT_MODEL=<modelo que suporta JSON mode>
AGENT_TIMEOUT=45
```

O endpoint e o modelo devem ser compatíveis com o formato Chat Completions e `response_format: {"type":"json_object"}`. A resposta é validada pelo schema antes de ser renderizada. Sem a chave/modelo configurados, a geração falha com estado e mensagem explícitos.

Outras variáveis úteis: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `CELERY_BROKER_URL`, `MEDIA_ROOT`, `REMOTION_PROJECT_DIR`, `REMOTION_RENDER_TIMEOUT` e `NODE_EXECUTABLE`.

## Fluxo e API

1. O utilizador autentica-se com a conta Django.
2. `POST /api/v1/videos/` recebe `{"prompt":"..."}` e responde `202 Accepted`.
3. No modo local, o próprio pedido solicita o guião ao agente, valida/persiste o JSON e executa Remotion; no modo assíncrono, o worker executa os mesmos passos.
4. `GET /api/v1/videos/` e `GET /api/v1/videos/<uuid>/` consultam o histórico/estado do utilizador autenticado.
5. `GET /api/v1/videos/<uuid>/file/` transmite o MP4 apenas ao proprietário.

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
