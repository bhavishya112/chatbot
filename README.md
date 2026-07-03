# Production Agent Chatbot

This project is a small streaming chatbot app. The browser talks to PHP, PHP starts a Python agent, and Python calls Gemini plus optional tools such as search, UI debugging, memory, and Qdrant retrieval.

The most important idea is separation of responsibilities:

- `frontend.html` owns the browser UI.
- `backend.php` owns request validation and Server-Sent Event streaming.
- `Agent.py` is the Python process entrypoint called by PHP.
- `app/` contains the actual agent code.
- `tests/` contains basic behavior tests.

## Quick Start

Run these commands from the project root:

```powershell
$env:GEMINI_API_KEY="your_gemini_api_key"
$env:GEMINI_MODEL="gemini-2.5-flash"
php -S 127.0.0.1:8000
```

Then open:

```text
http://127.0.0.1:8000/frontend.html
```

Minimum required configuration:

- `GEMINI_API_KEY`: your Google Gemini API key.

Optional configuration:

- `GEMINI_MODEL`: Gemini model name. Defaults to `gemini-2.5-flash`.
- `PYTHON_BIN`: Python executable used by PHP. Defaults to `python`.
- `AGENT_TIMEOUT_SECONDS`: max time PHP waits for Python. Defaults to `120`.
- `ENABLE_GOOGLE_SEARCH`: enables search tool. Defaults to `true`.
- `ENABLE_RAG`: enables Qdrant retrieval. Defaults to `false`.
- `QDRANT_URL`: Qdrant server URL. Defaults to `http://localhost:6333`.
- `QDRANT_API_KEY`: optional Qdrant API key.
- `QDRANT_COLLECTION`: Qdrant collection name. Defaults to `webdoc`.
- `RETRIEVAL_TOP_K`: number of chunks to retrieve. Defaults to `5`.
- `EMBEDDING_MODEL`: embedding model. Defaults to `all-MiniLM-L6-v2`.
- `MEMORY_WINDOW`: number of previous turns stored per session. Defaults to `5`.

Optional packages:

```powershell
pip install google-genai
pip install qdrant-client sentence-transformers
```

`google-genai` is needed for the search tool. `qdrant-client` and `sentence-transformers` are needed for retrieval and ingestion.

## Request Flow

1. The user types a message in `frontend.html`.
2. The frontend sends JSON to `backend.php`.
3. `backend.php` validates the request and starts `Agent.py`.
4. `backend.php` writes the request JSON into Python stdin.
5. `Agent.py` builds an `AgentRequest`.
6. `ProductionAgent` decides whether it needs UI context, search, memory, or retrieval.
7. Python prints newline-delimited JSON events.
8. PHP converts those events into browser SSE events.
9. The frontend renders streamed markdown safely with `marked` and `DOMPurify`.

## UI Capture Rule

The frontend does not send UI context for every message.

For UI-related questions, the agent first emits:

```json
{"event":"ui_context_request","message":"The agent needs visible UI context to answer this.","done":false}
```

Only after that event does the frontend capture:

- visible DOM HTML
- browser console errors already captured by the page

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
│   │   └── gemini.py
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

## Root Files

### `frontend.html`

This is the browser app. It contains HTML, CSS, and JavaScript in one file.

Important DOM variables:

- `chatMessages`: the message list container.
- `queryInput`: the text input where the user types.
- `sendBtn`: the Send/Stop button.
- `errorMsg`: the hidden error display box.

Important runtime variables:

- `eventSource`: tracks whether a stream is currently active. Despite the name, the code uses `fetch()` streaming, not the browser `EventSource` class.
- `currentAssistantBubble`: the assistant message currently receiving streamed tokens.
- `rawTextBuffer`: accumulated raw markdown text from the agent.
- `lastRenderedHtml`: last rendered sanitized HTML, used to avoid unnecessary re-rendering.
- `sessionId`: stable browser session id stored in `localStorage`.
- `consoleErrors`: recent console errors captured by the page.
- `originalConsoleError`: original `console.error`, saved before wrapping it.

Important functions:

- `getOrCreateSessionId()`: reads `chatbot_session_id` from `localStorage`, or creates one with `crypto.randomUUID()`.
- `rememberConsoleError(text)`: stores recent console errors, trimming each entry to 2000 characters and keeping only the latest 20.
- `captureVisibleHtml()`: builds a sanitized snapshot of only currently visible DOM nodes. It ignores script/style/template/noscript nodes.
- `isVisibleElement(element)`: nested helper used by `captureVisibleHtml()` to check layout visibility.
- `cloneVisible(node)`: nested helper used by `captureVisibleHtml()` to clone only visible nodes and useful text.
- `addMessage(text, isUser)`: adds a user or assistant message bubble to the chat.
- `renderMarkdown(text)`: converts markdown to HTML with `marked`, then sanitizes it with `DOMPurify`.
- `createStreamingMessage()`: creates an empty assistant bubble with a streaming cursor.
- `updateStreamingMarkdown(text)`: re-renders the assistant bubble as new markdown tokens arrive.
- `addCopyButtons(container)`: adds Copy buttons to rendered code blocks.
- `showError(text)`: displays a temporary error message.
- `stopStreaming()`: stops the current stream and restores the UI to idle state.
- `sendQuery(queryOverride = null, includeUiContext = false, reuseBubble = false)`: sends a chat request to `backend.php`, parses SSE text, and updates the UI.

Special behavior in `sendQuery()`:

- Normal request: sends `query`, `session_id`, empty `visible_html`, and empty `console_errors`.
- If the agent sends `ui_context_request`: captures visible UI context and retries the same query.
- If the agent sends `message`: appends `token` to `rawTextBuffer`.
- If the agent sends `done`: finalizes the message.
- If the agent sends `error`: displays the error.

### `backend.php`

This is the PHP bridge between browser and Python. It does not call Gemini directly.

Functions:

- `emit_sse(string $event, array $data): void`: sends one SSE event to the browser.
- `fail_request(string $message): never`: sends an error SSE event and exits.

Important PHP variables:

- `$rawBody`: raw request body from `php://input`.
- `$data`: decoded JSON body.
- `$query`: trimmed user query.
- `$consoleErrors`: safe array of frontend console error strings.
- `$sessionId`: sanitized session id. If missing, PHP creates one.
- `$payload`: JSON object sent to Python.
- `$projectDir`: current project directory.
- `$pythonBin`: Python executable from `PYTHON_BIN`, defaulting to `python`.
- `$agentPath`: path to `Agent.py`.
- `$timeoutSeconds`: max runtime for the Python process.
- `$cmd`: shell command used to start Python.
- `$descriptors`: process pipe setup for stdin, stdout, and stderr.
- `$process`: running Python process from `proc_open()`.
- `$pipes`: PHP handles for Python stdin/stdout/stderr.
- `$stdoutBuffer`: buffers Python stdout until full lines are available.
- `$stderrBuffer`: stores recent Python stderr output.
- `$doneSent`: remembers whether a final `done` event has already been sent.

What it validates:

- request method must be `POST`
- request body must exist
- JSON must be valid
- `query` must not be empty
- `console_errors` must be an array if present
- `session_id` is restricted to letters, numbers, `_`, and `-`

### `Agent.py`

This is the Python executable called by PHP.

Functions:

- `emit(event: dict[str, Any]) -> None`: prints one JSON event line to stdout and flushes immediately.
- `main() -> int`: reads JSON from stdin, creates settings and request objects, runs the agent, emits events, and returns an exit code.

Important variables:

- `raw`: complete JSON string read from stdin.
- `data`: parsed JSON dictionary.
- `request`: typed `AgentRequest`.
- `agent`: `ProductionAgent` instance.
- `event`: one streamed event from the agent.

If anything crashes, `main()` emits a safe user-facing error:

```json
{"event":"error","error":"Sorry, the agent could not complete that request."}
```

## `app/` Package

### `app/config.py`

Loads configuration from environment variables.

Functions:

- `_bool_env(name: str, default: bool) -> bool`: reads a boolean environment variable. Values like `1`, `true`, `yes`, and `on` mean true.

Classes:

- `Settings`: immutable dataclass holding runtime configuration.

`Settings` fields:

- `project_root`: root directory of the project.
- `data_dir`: `data/` directory.
- `memory_dir`: `data/memory/` directory.
- `gemini_api_key`: value of `GEMINI_API_KEY`.
- `gemini_model`: value of `GEMINI_MODEL`, default `gemini-2.5-flash`.
- `enable_google_search`: value of `ENABLE_GOOGLE_SEARCH`, default true.
- `qdrant_url`: value of `QDRANT_URL`, default `http://localhost:6333`.
- `qdrant_api_key`: value of `QDRANT_API_KEY`.
- `qdrant_collection`: value of `QDRANT_COLLECTION`, default `webdoc`.
- `retrieval_top_k`: value of `RETRIEVAL_TOP_K`, default `5`.
- `embedding_model`: value of `EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`.
- `memory_window`: value of `MEMORY_WINDOW`, default `5`.

Class methods:

- `Settings.from_env()`: builds a `Settings` object from environment variables.

### `app/schemas.py`

Contains small typed data containers shared across the agent.

Classes:

- `UIContext`: frontend-provided visible UI state.
- `AgentRequest`: complete request sent from PHP to Python.
- `ToolRequest`: request sent from the agent to one tool.
- `ToolObservation`: result returned by a tool.

`UIContext` fields:

- `visible_html`: sanitized visible DOM snapshot.
- `console_errors`: list of browser console errors.

`UIContext.from_dict(data)`:

- Accepts raw dictionary input.
- Returns empty context if input is invalid.
- Ensures `console_errors` is always a list of strings.

`AgentRequest` fields:

- `query`: user message.
- `ui_context`: `UIContext` object.
- `session_id`: stable conversation/session id.
- `stream`: whether streaming is requested. Currently defaults to true.

`AgentRequest.from_dict(data)`:

- Validates that `query` is present.
- Creates `UIContext`.
- Defaults `session_id` to `default` if missing.

`ToolRequest` fields:

- `name`: tool name.
- `arguments`: tool-specific arguments.
- `session_id`: current session id.

`ToolObservation` fields:

- `ok`: true if the tool succeeded.
- `content`: text result from the tool.
- `metadata`: optional extra structured data.

### `app/logging_config.py`

Configures logging.

Functions:

- `configure_logging()`: sends Python logs to stderr with timestamp, level, logger name, and message.

### `app/prompts.py`

Builds the prompt sent to Gemini.

Variables:

- `SYSTEM_PROMPT`: high-level instruction for the chatbot.
- `REACT_TOOL_PROMPT`: describes available tools and the rule that scratchpad reasoning stays internal.

Functions:

- `build_prompt(query, memory, retrieval, ui_context)`: combines system instructions, tool instructions, recent memory, retrieved context, UI context, and the user query into one prompt string.

### `app/memory.py`

Stores short conversation memory in JSON files.

Classes:

- `ConversationTurn`: one user/assistant pair.
- `JsonConversationMemory`: load/save/prune memory backend.

`ConversationTurn` fields:

- `user`: user message.
- `assistant`: assistant response.

`JsonConversationMemory.__init__(memory_dir, window)`:

- `memory_dir`: folder where JSON memory files live.
- `window`: number of turns to keep.
- Creates the memory directory if needed.

Methods:

- `_path(session_id)`: converts a session id to a safe JSON file path.
- `load(session_id)`: reads previous turns and returns only the newest `window` turns.
- `save_turn(session_id, user, assistant)`: appends one turn and prunes old turns.
- `format(session_id)`: converts memory to plain text for the prompt.

### `app/agent.py`

Contains the orchestration logic.

Variables:

- `UI_KEYWORDS`: words that suggest the agent needs visible UI context.
- `SEARCH_KEYWORDS`: words that suggest the search tool may be useful.

Classes:

- `ProductionAgent`: main chatbot agent.

`ProductionAgent.__init__(settings)` creates:

- `self.settings`: app configuration.
- `self.memory`: `JsonConversationMemory`.
- `self.retriever`: `QdrantRetriever`.
- `self.gemini`: `GeminiService`.
- `self.tools`: `ToolRegistry` with `SearchTool` and `UIResolutionTool`.

Methods:

- `stream(request)`: public streaming method. Yields event dictionaries for PHP.
- `_answer(request)`: builds memory/retrieval/UI/search context, calls Gemini, and returns final text.
- `_needs_search(query)`: returns true if the query contains search-like keywords.
- `_needs_ui_context(request)`: returns true if the query seems UI-related and no UI context was provided.
- `_fallback_answer(request, retrieval, search, ui)`: response used when Gemini is not configured or unavailable.
- `_chunk(text, size=80)`: splits text into small chunks for streaming.

Important behavior:

- Scratchpad reasoning is not emitted.
- UI context is requested before capture.
- Memory is saved after a successful response.
- Qdrant/search failures degrade gracefully.

### `app/services/gemini.py`

Wraps the Gemini text generation API.

Classes:

- `GeminiService`: small service object for Gemini calls.

Methods:

- `__init__(settings)`: stores config.
- `available()`: returns true if `GEMINI_API_KEY` exists.
- `generate(prompt)`: sends a prompt to Gemini and returns text.

Important local variables in `generate()`:

- `url`: Gemini REST API URL.
- `payload`: request body sent to Gemini.
- `request`: `urllib.request.Request` object.
- `data`: parsed Gemini JSON response.
- `parts`: candidate text parts returned by Gemini.

If the API key is missing or the request fails, `generate()` returns an empty string. The agent then uses a fallback response.

### `app/retrieval.py`

Reads relevant chunks from Qdrant.

Classes:

- `QdrantRetriever`: retrieval adapter.

Methods:

- `__init__(settings)`: stores config.
- `retrieve(query)`: embeds the query, searches Qdrant, and returns chunk dictionaries.
- `format(chunks)`: converts retrieved chunks into prompt text.

Important local variables in `retrieve()`:

- `embedder`: `SentenceTransformer` model.
- `vector`: embedding vector for the query.
- `client`: Qdrant client.
- `results`: Qdrant search results.

Returned chunk fields:

- `score`: similarity score.
- `text`: retrieved text.
- `metadata`: source metadata.

If dependencies are missing or Qdrant is unavailable, `retrieve()` returns an empty list.

## Tools

### `app/tools/base.py`

Defines the expected shape of a tool.

Classes:

- `Tool`: Python `Protocol`, meaning any class with the same attributes and methods can act like a tool.

Required tool attributes:

- `name`: unique tool name.
- `description`: short explanation of what the tool does.

Required tool methods:

- `input_schema()`: returns a JSON-schema-like description of tool inputs.
- `execute(request)`: runs the tool and returns `ToolObservation`.

### `app/tools/registry.py`

Stores and runs tools by name.

Classes:

- `ToolRegistry`: generic registry for all tools.

Fields:

- `_tools`: dictionary mapping tool name to tool instance.

Methods:

- `register(tool)`: adds or replaces a tool.
- `get(name)`: returns a registered tool or raises `KeyError`.
- `execute(name, arguments, session_id)`: creates `ToolRequest` and runs the selected tool.
- `names()`: returns sorted tool names.

### `app/tools/search.py`

Search tool backed by Gemini Google Search tooling when installed and configured.

Classes:

- `SearchTool`

Class attributes:

- `name = "search"`
- `description`: describes when to use the tool.

Methods:

- `__init__(settings)`: stores config.
- `input_schema()`: declares that the tool requires a string `query`.
- `execute(request)`: validates the query, checks config, calls Gemini search tooling, and returns `ToolObservation`.

Important local variables:

- `query`: search query string.
- `client`: Google GenAI client.
- `response`: Gemini search-enabled response.
- `text`: response text.

Failure cases:

- empty query
- `ENABLE_GOOGLE_SEARCH=false`
- missing `GEMINI_API_KEY`
- missing package or API failure

### `app/tools/ui_resolution.py`

Analyzes visible frontend context for UI debugging.

Classes:

- `_VisibleTextParser`: internal HTML parser that extracts visible text from HTML.
- `UIResolutionTool`: public tool used by the agent.

`_VisibleTextParser` fields:

- `text_parts`: collected text pieces.

`_VisibleTextParser.handle_data(data)`:

- Receives text from HTML parsing.
- Trims it.
- Stores non-empty text.

`UIResolutionTool` class attributes:

- `name = "ui_resolution"`
- `description`: explains that it uses only frontend-provided visible HTML and console errors.

Methods:

- `input_schema()`: declares required inputs: `question`, `visible_html`, and `console_errors`.
- `execute(request)`: extracts visible text, element ids, classes, and console errors into one observation.

Important local variables:

- `visible_html`: sanitized visible HTML from the frontend.
- `question`: user question.
- `errors`: console errors.
- `parser`: `_VisibleTextParser`.
- `visible_text`: combined text extracted from HTML.
- `ids`: up to 30 element ids found in the HTML.
- `classes`: up to 30 class strings found in the HTML.
- `parts`: sections of the final observation.

If no useful context is present, it returns `ok=False`.

## Ingestion

### `app/ingestion/source_ingestor.py`

Builds Qdrant-ready chunks from source code files.

Variables:

- `SUPPORTED_EXTENSIONS`: file extensions included in ingestion: `.html`, `.css`, `.js`, `.php`, `.py`.

Classes:

- `SourceIngestor`

Methods:

- `__init__(settings)`: stores config.
- `iter_files(root=None)`: returns supported files under the project root, ignoring `.git`, `__pycache__`, and `data`.
- `chunk_text(text, size=1200, overlap=150)`: splits text into overlapping chunks.
- `build_points(root=None)`: creates point dictionaries with stable ids, text, and metadata.
- `upsert(root=None)`: embeds chunks and upserts them into Qdrant.

Important local variables:

- `base`: root folder being scanned.
- `ignored`: directories skipped during scanning.
- `chunks`: text chunks.
- `digest`: SHA-256 id for a chunk.
- `points`: list of chunk records.
- `embedder`: sentence-transformer model.
- `vectors`: embeddings for all chunks.
- `client`: Qdrant client.

If dependencies or Qdrant are unavailable, `upsert()` returns `0`.

## Tests

### `tests/test_core.py`

Uses Python `unittest`.

Classes:

- `CoreTests`: test case class.

Tests:

- `test_memory_prunes_to_window()`: verifies memory keeps only the newest 5 turns.
- `test_tool_registry_executes_registered_tool()`: verifies `ToolRegistry` can run `UIResolutionTool`.
- `test_ui_resolution_rejects_empty_context()`: verifies empty UI context returns failure.

Run tests:

```powershell
python -m unittest discover -s tests
```

## Data Files

### `md_parser/marked.min.js`

Browser library used by `frontend.html` to convert markdown text into HTML.

### `md_parser/purify.min.js`

Browser library used by `frontend.html` to sanitize HTML before inserting it into the page.

## Event Contracts

### Browser to PHP

```json
{
  "query": "user question",
  "visible_html": "optional visible DOM snapshot",
  "console_errors": ["optional browser error text"],
  "session_id": "stable browser session id"
}
```

### PHP to Python

```json
{
  "query": "user question",
  "ui_context": {
    "visible_html": "visible DOM only",
    "console_errors": ["errors"]
  },
  "session_id": "resolved session id",
  "stream": true
}
```

### Python to PHP

Message event:

```json
{"event":"message","token":"partial text","done":false}
```

Done event:

```json
{"event":"done","finished":true}
```

Error event:

```json
{"event":"error","error":"safe user-facing error"}
```

UI context request:

```json
{"event":"ui_context_request","message":"The agent needs visible UI context to answer this.","done":false}
```

## Adding a New Tool

1. Create a new file in `app/tools/`.
2. Give the class these attributes:

```python
name = "your_tool_name"
description = "What the tool does."
```

3. Add these methods:

```python
def input_schema(self) -> dict:
    ...

def execute(self, request: ToolRequest) -> ToolObservation:
    ...
```

4. Register it in `ProductionAgent.__init__()`:

```python
self.tools.register(YourTool())
```

The core agent loop does not need to change if the tool follows the same contract.

## Common Problems

### The page loads, but the assistant says Gemini is not configured

Set `GEMINI_API_KEY` before starting PHP:

```powershell
$env:GEMINI_API_KEY="your_gemini_api_key"
php -S 127.0.0.1:8000
```

### Search does not work

Install:

```powershell
pip install google-genai
```

Also confirm:

```powershell
$env:ENABLE_GOOGLE_SEARCH="true"
$env:GEMINI_API_KEY="your_gemini_api_key"
```

### Retrieval returns no context

Install dependencies, run Qdrant, and ingest source files first:

```powershell
pip install qdrant-client sentence-transformers
```

The current code provides the ingestion class, but does not include a command-line wrapper yet. A developer can call `SourceIngestor(Settings.from_env()).upsert()` from a small script or Python shell.

### PHP cannot start Python

Set `PYTHON_BIN` to your Python executable:

```powershell
$env:PYTHON_BIN="C:\Python314\python.exe"
```

### UI debugging does not include page state

That is expected until the agent asks for it. UI capture only happens after `ui_context_request`.

## Verification Commands

```powershell
php -l backend.php
python -m py_compile Agent.py app\agent.py app\config.py app\schemas.py app\memory.py app\prompts.py app\retrieval.py app\services\gemini.py app\tools\base.py app\tools\registry.py app\tools\search.py app\tools\ui_resolution.py app\ingestion\source_ingestor.py
python -m unittest discover -s tests
```
