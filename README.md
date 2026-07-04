# Production Local Agent Chatbot

This project is a streaming chatbot app that runs against a local model. The browser talks to PHP, PHP starts a Python agent, and Python sends prompts to an Ollama-compatible local model endpoint.

Default local model runtime:

- Ollama URL: `http://127.0.0.1:11434/api/generate`
- Model name: `llama3.1:8b`

## Quick Start

Install Ollama, pull a model, then run the PHP app:

```powershell
ollama pull llama3.1:8b

cd D:\cs\projects\chatbot
$env:LOCAL_MODEL_NAME="llama3.1:8b"
$env:LOCAL_MODEL_URL="http://127.0.0.1:11434/api/generate"
$env:ENABLE_RAG="false"
php -S 127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:8000/frontend.html
```

## Configuration

Required:

- `LOCAL_MODEL_NAME`: local model name installed in Ollama. Default: `llama3.1:8b`.
- `LOCAL_MODEL_URL`: Ollama-compatible generate endpoint. Default: `http://127.0.0.1:11434/api/generate`.

Optional:

- `LOCAL_MODEL_TIMEOUT`: max seconds to wait for local model output. Default: `120`.
- `PYTHON_BIN`: Python executable used by PHP. Default: `python`.
- `AGENT_TIMEOUT_SECONDS`: max seconds PHP waits for Python. Default: `120`.
- `ENABLE_RAG`: enables Qdrant retrieval. Default: `false`.
- `ENABLE_GOOGLE_SEARCH`: search flag. Default: `false`; search is not implemented in local-only mode.
- `QDRANT_URL`: Qdrant server URL. Default: `http://localhost:6333`.
- `QDRANT_API_KEY`: optional Qdrant API key.
- `QDRANT_COLLECTION`: Qdrant collection name. Default: `webdoc`.
- `RETRIEVAL_TOP_K`: number of chunks to retrieve. Default: `5`.
- `EMBEDDING_MODEL`: embedding model. Default: `all-MiniLM-L6-v2`.
- `MEMORY_WINDOW`: previous turns stored per session. Default: `5`.

## Request Flow

1. The user types a message in `frontend.html`.
2. The frontend sends JSON to `backend.php`.
3. `backend.php` validates the request and starts `Agent.py`.
4. `Agent.py` builds an `AgentRequest`.
5. `ProductionAgent` gathers memory, optional RAG context, optional UI context, and optional tool observations.
6. `LocalModelService` sends the prompt to the local model.
7. Python prints newline-delimited JSON events.
8. PHP converts those events into browser Server-Sent Events.
9. The frontend renders streamed markdown safely with `marked` and `DOMPurify`.

## UI Capture Rule

The frontend does not send UI context for every message.

For UI-related questions, the agent first emits:

```json
{"event":"ui_context_request","message":"The agent needs visible UI context to answer this.","done":false}
```

Only after that event does the frontend capture visible DOM HTML and browser console errors already captured by the page.

It does not capture hidden DOM, cookies, local storage contents, screenshots, or unrelated browser state.

## Directory Structure

```text
.
├── Agent.py
├── backend.php
├── frontend.html
├── app/
│   ├── agent.py
│   ├── config.py
│   ├── logging_config.py
│   ├── memory.py
│   ├── prompts.py
│   ├── retrieval.py
│   ├── schemas.py
│   ├── ingestion/
│   │   └── source_ingestor.py
│   ├── services/
│   │   └── local_model.py
│   └── tools/
│       ├── base.py
│       ├── registry.py
│       ├── search.py
│       └── ui_resolution.py
├── md_parser/
│   ├── marked.min.js
│   └── purify.min.js
└── tests/
    └── test_core.py
```

## Main Files

### `frontend.html`

The browser UI. It sends chat requests, renders streamed markdown, captures console errors, and captures visible UI context only when the agent asks for it.

Important functions:

- `getOrCreateSessionId()`: creates or reads a stable browser session id.
- `rememberConsoleError(text)`: stores recent browser console errors.
- `captureVisibleHtml()`: snapshots visible DOM only.
- `addMessage(text, isUser)`: adds a user or assistant message.
- `renderMarkdown(text)`: converts markdown to sanitized HTML.
- `createStreamingMessage()`: creates the assistant bubble during streaming.
- `updateStreamingMarkdown(text)`: re-renders streamed markdown.
- `stopStreaming()`: restores idle UI state.
- `sendQuery(queryOverride, includeUiContext, reuseBubble)`: posts to `backend.php` and parses SSE events.

### `backend.php`

The PHP bridge. It validates browser input, starts `Agent.py`, and forwards Python events as browser SSE.

Important functions:

- `emit_sse($event, $data)`: sends one SSE event.
- `fail_request($message)`: sends an error event and exits.

Important variables:

- `$payload`: normalized PHP-to-Python request.
- `$pythonBin`: Python executable.
- `$agentPath`: path to `Agent.py`.
- `$timeoutSeconds`: PHP bridge timeout.
- `$stdoutBuffer`: buffers Python event lines.
- `$doneSent`: prevents duplicate final events.

### `Agent.py`

The Python entrypoint called by PHP.

Important functions:

- `emit(event)`: prints one JSON event line to stdout.
- `main()`: reads stdin JSON, loads settings, runs `ProductionAgent`, and emits events.

### `app/config.py`

Loads environment configuration.

Important fields on `Settings`:

- `local_model_url`
- `local_model_name`
- `local_model_timeout`
- `enable_rag`
- `qdrant_url`
- `qdrant_collection`
- `retrieval_top_k`
- `embedding_model`
- `memory_window`

### `app/agent.py`

The main orchestrator.

`ProductionAgent` owns:

- `memory`: JSON conversation memory.
- `retriever`: optional Qdrant retrieval.
- `model`: local model service.
- `tools`: search and UI-resolution registry.

Important methods:

- `stream(request)`: yields Python event dictionaries for PHP.
- `_answer(request)`: builds context and calls the local model.
- `_needs_ui_context(request)`: asks frontend for visible UI context when needed.
- `_needs_search(query)`: detects search-like questions. Search currently returns a local-only-mode message.
- `_fallback_answer(...)`: response used when the local model is unreachable.
- `_chunk(text)`: splits text into streamed chunks.

### `app/services/local_model.py`

Local model adapter.

`LocalModelService.generate(prompt)` sends this style of request to Ollama:

```json
{
  "model": "llama3.1:8b",
  "prompt": "full prompt text",
  "stream": false,
  "options": {
    "temperature": 0.7,
    "top_p": 0.9
  }
}
```

It returns the `response` field from Ollama.

### `app/memory.py`

Stores the last few conversation turns in `data/memory/<session>.json`.

Important classes:

- `ConversationTurn`: one user/assistant pair.
- `JsonConversationMemory`: load, save, prune, and format memory.

### `app/retrieval.py`

Optional Qdrant RAG adapter.

Important class:

- `QdrantRetriever`

Important methods:

- `retrieve(query)`: embeds query and searches Qdrant.
- `format(chunks)`: turns retrieved chunks into prompt text.

### `app/ingestion/source_ingestor.py`

Optional source-code ingestion for Qdrant.

Supported files:

- `.html`
- `.css`
- `.js`
- `.php`
- `.py`

Important methods:

- `iter_files(root)`: finds supported files.
- `chunk_text(text)`: splits files into overlapping chunks.
- `build_points(root)`: creates Qdrant point payloads.
- `upsert(root)`: embeds and writes points to Qdrant.

Manual ingestion smoke test:

```powershell
python -c "from app.config import Settings; from app.ingestion.source_ingestor import SourceIngestor; print(SourceIngestor(Settings.from_env()).upsert())"
```

### `app/tools/search.py`

Search is intentionally disabled in local-only mode unless you add a separate search backend such as SearxNG, Tavily, or SerpAPI.

### `app/tools/ui_resolution.py`

Analyzes only frontend-provided visible HTML and console errors.

### `tests/test_core.py`

Standard-library tests for memory and tools.

Run:

```powershell
python -m unittest discover -s tests
```

## Event Contracts

Browser to PHP:

```json
{
  "query": "user question",
  "visible_html": "optional visible DOM snapshot",
  "console_errors": ["optional browser error text"],
  "session_id": "stable browser session id"
}
```

Python message:

```json
{"event":"message","token":"partial text","done":false}
```

Python done:

```json
{"event":"done","finished":true}
```

Python error:

```json
{"event":"error","error":"safe user-facing error"}
```

## Common Problems

### The assistant says the local model is not reachable

Make sure Ollama is running:

```powershell
ollama list
ollama run llama3.1:8b
```

Then restart PHP with the same model name:

```powershell
$env:LOCAL_MODEL_NAME="llama3.1:8b"
php -S 127.0.0.1:8000
```

### First response is slow

Local models often take time to load into memory. Try one warm-up prompt directly:

```powershell
ollama run llama3.1:8b "Say ready."
```

### RAG is slow

Keep RAG disabled until Qdrant and embeddings are ready:

```powershell
$env:ENABLE_RAG="false"
```

Enable it only when testing retrieval:

```powershell
$env:ENABLE_RAG="true"
```

### Logs

Watch Python logs:

```powershell
Get-Content logs\agent.log -Wait
```

## Verification Commands

```powershell
php -l backend.php
python -m py_compile Agent.py app\agent.py app\config.py app\schemas.py app\memory.py app\prompts.py app\retrieval.py app\services\local_model.py app\tools\base.py app\tools\registry.py app\tools\search.py app\tools\ui_resolution.py app\ingestion\source_ingestor.py
python -m unittest discover -s tests
```
