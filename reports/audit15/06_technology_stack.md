# Audit 15 Technology Stack

## Python Runtime

| Component | Evidence | Role |
|---|---|---|
| Python `>=3.11` | `pyproject.toml` | Backend, ingestion, scripts, tests |
| Python 3.11.9 in CI | `.github/workflows/python-ci.yml` | Reproducible Windows CI |
| `requirements.lock.txt` | CI install source | Locked dependency set |
| `pip check` | CI and local validation | Dependency consistency |

## API and Agent

| Technology | Evidence | Use |
|---|---|---|
| FastAPI | `src/api/app.py`, requirements | HTTP API |
| Uvicorn | requirements, README | Local app server |
| Pydantic | API models, retrieval contracts, taxonomy models | Runtime and validation schemas |
| LangGraph | `src/agent/graph.py` | Clinical agent workflow |
| LangChain packages | requirements | Agent integration dependencies |
| HTTPX | requirements, provider clients | Ollama/API HTTP calls |

## LLM and Embeddings

| Technology | Evidence | Use |
|---|---|---|
| Google GenAI SDK | `src/integrations/google_genai.py`, requirements | Gemini text generation and embeddings |
| Gemini `gemini-3.5-flash` | `.env.example` | Default Google generation model |
| Gemini fallback `gemini-3.1-flash-lite` | `.env.example` | Provider fallback |
| Gemini embedding `models/gemini-embedding-2` | `.env.example`, version checks | 3072-dimensional dense embeddings |
| Ollama | `src/agent/llm/ollama_client.py`, `.env.example` | Local generation provider |
| Ollama model `qwen3:8b` | `.env.example` | Default local model |

Guardrail:

- CI scans for legacy `google-generativeai` usage and fails if found.
- Google calls are centralized through `src/integrations/google_genai.py`.

## Retrieval and Data Stores

| Technology | Evidence | Use |
|---|---|---|
| Qdrant v1.18.0 | `docker-compose.yml` pinned digest | Hybrid vector database |
| Named dense vector `dense` | Qdrant collection config | 3072 cosine vector |
| Named sparse vector `bm25` | Qdrant collection config | Sparse BM25-style retrieval |
| Neo4j 5 with APOC | `docker-compose.yml` pinned digest | Knowledge graph |
| PostgreSQL 16 plus pgvector image | `docker-compose.yml` pinned digest | Chat history and future vector capability |
| Redis 7 Alpine | `docker-compose.yml` pinned digest | Semantic answer cache |
| SQLAlchemy async | database connection/repository files | PostgreSQL access |
| Neo4j Python driver | graph store/index files | Graph access |
| Qdrant Python client | vector/entity store files | Vector operations |

## Reranking

| Technology | Evidence | Use |
|---|---|---|
| sentence-transformers CrossEncoder | `src/retrieval/reranking/providers.py`, requirements | Local semantic reranking |
| PyTorch | requirements and local GPU validation history | CrossEncoder runtime |
| Hybrid fusion | `providers.py`, `reranker.py` | Semantic + rule + retrieval-order fusion |
| Offline mode env | `.env.example`, CI | Prevents accidental model download in offline checks |

Local GPU model path is intentionally machine-specific:

- `SEMANTIC_RERANK_MODEL_PATH=C:/Models/acne-reranker/bge-reranker-v2-m3`

## Ingestion

| Technology | Evidence | Use |
|---|---|---|
| LlamaParse/LlamaCloud | ingestion script and `.env.example` | PDF/DOCX parsing |
| Markdown cache | ingestion script | Avoid repeated source parsing |
| Google embeddings | ingestion script and adapter | Dense vectors |
| Ollama graph extraction | ingestion script | Chunk graph extraction when enabled |
| JSON loader | `src/ingestion/json_loader.py` | Web/raw JSON source ingestion |

## Frontend

| Technology | Evidence | Use |
|---|---|---|
| React `^19.2.6` | `src/frontend/package.json` | UI |
| ReactDOM `^19.2.6` | `package.json` | UI rendering |
| Vite `^8.0.12` | `package.json` | Dev/build tool |
| ESLint 10 | `package.json`, CI | Frontend lint |
| Node 24.x in CI | `.github/workflows/python-ci.yml` | Frontend build/test environment |
| Node test runner | `npm test` script | Frontend unit tests |

## Testing and QA

| Tool | Evidence | Use |
|---|---|---|
| pytest | `pyproject.toml`, tests | Python tests |
| pytest-asyncio | requirements | Async tests |
| pytest-cov | `pyproject.toml` | Coverage threshold 70 |
| Node test runner | frontend package | Frontend unit tests |
| `pip check` | CI and validation | Dependency consistency |
| `compileall` | validation workflows | Syntax/import compilation sanity |

## CI/CD

| Technology | Evidence | Use |
|---|---|---|
| GitHub Actions | `.github/workflows/python-ci.yml` | PR/main validation |
| Windows latest | CI workflow | Primary CI OS |
| `actions/checkout@v5` | workflow | Source checkout |
| `actions/setup-python@v6` | workflow | Python install/cache |
| `actions/setup-node@v6` | workflow | Node install/cache |

## Version and Contract Variables

Current important defaults from `.env.example` and CI:

| Variable | Value |
|---|---|
| `KB_VERSION` | `acne_kb_v1` |
| `CACHE_ANSWER_VERSION` | `v5` |
| `ANSWER_FORMATTING_CONTRACT_VERSION` | `answer_formatting_contract_v4` |
| `RUNTIME_RESILIENCE_VERSION` | `runtime_resilience_v1` |
| `SEVERITY_GUARD_VERSION` | `severity_aware_answer_guard_v1` |
| `SAFE_FALLBACK_FLOW_VERSION` | `safe_fallback_flow_v1` |
| `GOOGLE_GENAI_SDK_VERSION` | `google_genai_sdk_v1` |
| `REPRODUCIBLE_ENVIRONMENT_VERSION` | `reproducible_environment_v1` |
| `END_TO_END_RELEASE_READINESS_VERSION` | `end_to_end_release_readiness_v1` |

## Stack Assessment

Strengths:

- Strong separation between data foundation, retrieval, generation, safety, and presentation.
- Hybrid retrieval stack is explicit and testable.
- Runtime stores are containerized and bound to loopback ports.
- Google SDK migration is protected by CI scans.
- Version/fingerprint strategy reduces stale-cache regressions.

Weaknesses:

- The stack is broad for a small app, so operational sequencing matters.
- Local GPU reranker readiness cannot be fully validated in GitHub Actions.
- README snapshots can lag behind runtime state if not refreshed after controlled rebuilds.
