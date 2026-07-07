# Acne Advisor AI

Acne Advisor AI là hệ thống RAG y khoa tập trung vào mụn trứng cá và da liễu. Project chạy theo hướng local-first: frontend React/Vite, backend FastAPI, agent LangGraph, Qdrant cho vector search, Neo4j cho knowledge graph, PostgreSQL cho lịch sử chat, Redis cho cache, Ollama cho model local, Gemini cho sinh câu trả lời/embedding và LlamaParse cho ingestion tài liệu.

## Cảnh Báo Y Khoa

Hệ thống chỉ cung cấp thông tin tham khảo và hỗ trợ học tập/demo. Acne Advisor AI không phải công cụ chẩn đoán, không kê đơn, không thay thế bác sĩ da liễu, bác sĩ sản khoa hoặc cấp cứu. Với triệu chứng nặng như khó thở, sưng môi/mặt, sốt cao, đau quanh mắt, nhìn mờ, choáng hoặc phản ứng thuốc nghiêm trọng, người dùng cần liên hệ cơ sở y tế ngay.

## Mục Tiêu Dự Án

- Xây dựng trợ lý RAG chuyên về mụn, chăm sóc da mụn và thông tin da liễu liên quan.
- Ingest tài liệu PDF/DOCX thành Markdown, chunks, knowledge graph và vector index.
- Trả lời tiếng Việt có cấu trúc, có guardrail y khoa và có nguồn từ context truy xuất.
- Hỗ trợ chạy local với Docker backing services và Ollama.
- Duy trì cache/resume an toàn cho ingestion và cache câu trả lời cho Phase 2.

## Trạng Thái Hiện Tại

Đã triển khai:

- Frontend React/Vite tại `src/frontend`.
- FastAPI backend entrypoint: `src.api.app:app`.
- Endpoint `/chat` với session history, giới hạn input, sửa lỗi UTF-8/mojibake, model selection, fallback metadata và `bypass_cache`.
- LangGraph agent gồm các node normalize, rewrite, guardrail, cache, retrieve, safety, generate, finalize và cache store.
- Hybrid retrieval từ Qdrant dense `dense`, sparse `bm25`, RRF fusion, metadata boost và Neo4j graph facts.
- PostgreSQL lưu `chat_sessions`, `chat_messages` và bảng `patient_records`.
- Redis answer cache với key prefix `cache:answer:*`.
- Phase 1 ingestion từ PDF/DOCX sang Markdown, chunks, graph cache, Neo4j, Gemini embeddings và Qdrant.
- Test chính thức trong `tests/` và smoke/diagnostics scripts trong `scripts/diagnostics/`.

Giới hạn hiện tại:

- Cần cấu hình đúng Docker services, Ollama và API keys.
- `src/web` và `src/web_legacy` là HTML legacy; frontend đang dùng là `src/frontend`.
- `pgvector` mới là hướng placeholder; vector store đang dùng thực tế là Qdrant.

## Tech Stack

| Lớp | Công nghệ |
|---|---|
| Frontend | React 19, Vite |
| API | FastAPI, Uvicorn, Pydantic |
| Agent | LangGraph |
| LLM | Gemini, Ollama fallback/tuỳ chọn |
| Local model | Ollama, mặc định `qwen2.5` |
| Parsing tài liệu | LlamaParse |
| Embedding | Gemini `models/gemini-embedding-2`, dim `3072` |
| Vector DB | Qdrant collection `acne_knowledge`, vector `dense`, sparse `bm25` |
| Graph DB | Neo4j 5 + APOC |
| Relational DB | PostgreSQL 16 |
| Cache | Redis 7 |
| Test | pytest, pytest-asyncio |

## Kiến Trúc Tổng Quan

Docker Compose hiện chỉ chạy backing services: PostgreSQL, Redis, Qdrant và Neo4j. Trong môi trường development, backend FastAPI và frontend React/Vite chạy riêng.

Sơ đồ tuần tự chi tiết được tách riêng tại: [Sơ đồ luồng hoạt động](docs/sequence-diagrams.md).

```text
User
  -> React/Vite Frontend
  -> FastAPI Backend
  -> LangGraph Agent
  -> Guardrails / Redis Cache / Hybrid Retriever
  -> Qdrant + Neo4j
  -> Gemini hoặc Ollama
  -> PostgreSQL chat history
```

## Cấu Trúc Thư Mục

```text
acne-agent-system/
├── docs/
│   └── sequence-diagrams.md
├── src/
│   ├── api/                  # FastAPI app, routes, preflight
│   ├── agent/                # LangGraph workflow, nodes, prompts, LLM provider
│   ├── cache/                # Redis connection và answer cache
│   ├── database/             # PostgreSQL, Qdrant, Neo4j access layer
│   ├── frontend/             # React/Vite web UI đang dùng
│   ├── ingestion/            # Dermatology metadata helpers
│   ├── skills/               # Skill registry/base modules
│   ├── web/                  # Legacy static HTML
│   └── web_legacy/           # Legacy static HTML copy
├── scripts/
│   ├── ingest_knowledge.py   # Phase 1 offline ingestion
│   ├── init_schema.py        # PostgreSQL + Qdrant bootstrap
│   ├── init_chat_schema.py   # Chat history schema
│   ├── clear_redis_cache.py  # Xoá Redis answer cache của app
│   └── diagnostics/          # Smoke/debug/inspection scripts
├── tests/                    # pytest tests
├── data/                     # Runtime volumes/cache, gitignored
├── sample_data/              # Tài liệu nguồn local, gitignored
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

## Thành Phần Chính

- **Frontend (`src/frontend`)**: giao diện chat, sidebar lịch sử, ẩn/xoá lịch sử, chọn model, auto fallback và gọi API backend.
- **FastAPI (`src/api/app.py`)**: endpoint `/chat`, `/health`, `/retrieve`, `/models`, quản lý chat history và input validation.
- **LangGraph agent (`src/agent`)**: điều phối normalize, rewrite follow-up, guardrail, cache, retrieval, safety check, generate và finalize.
- **Qdrant**: lưu chunks với vector dense `dense`, sparse `bm25` và payload metadata.
- **Neo4j**: lưu knowledge graph từ Phase 1, dùng để bổ sung graph facts trong Phase 2.
- **PostgreSQL**: lưu lịch sử chat và schema phụ.
- **Redis**: cache câu trả lời hợp lệ, không dùng cho câu có history hoặc ngữ cảnh rủi ro cao.
- **Ollama**: chạy local model, mặc định `qwen2.5`, dùng trong graph extraction và fallback/generation tuỳ cấu hình.
- **Gemini**: sinh câu trả lời và embedding.
- **LlamaParse**: parse PDF/DOCX thành Markdown trong Phase 1.

## Phase 1 Offline Ingestion

Entry point:

```powershell
.\venv\Scripts\python.exe scripts\ingest_knowledge.py
```

Luồng chính:

1. Tìm `*.pdf`, `*.docx` và `*.json` trong `SAMPLE_DATA_DIR` hoặc `--source`.
2. Parse PDF/DOCX bằng LlamaParse sang Markdown; JSON web dataset được đọc local.
3. Cache Markdown trong `data/cache/markdown`.
4. Chunk Markdown theo header và `CHUNK_SIZE`.
5. Trích xuất graph bằng Ollama.
6. Cache graph trong `data/cache/graph` với key gồm version, prompt schema, model, source file, chunk index và chunk hash.
7. Upsert graph vào Neo4j.
8. Embed chunks bằng Gemini.
9. Upsert Qdrant với `dense` và `bm25`.

Supported knowledge file types:
- PDF/DOCX: dùng pipeline LlamaParse hiện tại.
- JSON web dataset: file như `web_raw_dataset.json` chứa list records hoặc wrapper `records/data/items/documents/pages`, mỗi record có `seed_url`, `source_url`, `raw_text`.
- JSON được xử lý local, không dùng LlamaParse.
- JSON chunks preserve `source_url`, `seed_url`, `record_index`, `source_type=web_json` trong payload metadata.
- Đặt `web_raw_dataset.json` vào `sample_data/` trước clean rebuild nếu muốn ingest chung với PDF/DOCX.

Incremental ingestion dùng manifest mặc định `data/ingestion_manifest.json`.
Tài liệu có `status=completed` hoặc `status=completed_with_warnings` sẽ được skip khi `content_hash` không đổi.
`completed_with_warnings` dành cho trường hợp ingest chính đã thành công nhưng chỉ có một số lỗi graph extraction nằm trong ngưỡng cho phép; `partial` sẽ được retry ở lần incremental sau.
Manifest lưu `qdrant_point_ids`, `qdrant_point_count`, collection và metadata version/embedding theo từng document.
Khi incremental gặp file `changed`, `partial`, `failed` hoặc `cleanup_failed` cần retry, pipeline sẽ cleanup Qdrant cũ trước khi upsert lại: ưu tiên xóa theo `qdrant_point_ids`, fallback bằng filter scoped theo `document_id`/`source_path`/`kb_version`.
Guard cleanup chỉ cho phép collection chunk (`QDRANT_COLLECTION_NAME` hoặc `CHUNK_QDRANT_COLLECTION_NAME`) và không cleanup entity collection như `acne_entities_v1`.
Neo4j graph cũ chưa được cleanup tự động trong bước này.

Lệnh thường dùng:

```powershell
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --limit-files 1 --limit-chunks 5
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --refresh-markdown
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --refresh-graph-cache
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --no-resume-graph-cache
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --clear-graph-cache
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --skip-graph-extraction
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --skip-neo4j
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --skip-qdrant
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --dry-run
.\venv\Scripts\python.exe scripts\inspect_ingestion_manifest.py --show-missing
```

### Phase 1 Readiness Eval

Eval offline trước clean rebuild dùng golden set tại `tests/golden/phase1_ingest_eval_cases.json`.
Eval này không chạy ingestion, không connect Qdrant/Neo4j, không gọi Gemini.

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_phase1_ingest_eval.py -q --no-cov
.\venv\Scripts\python.exe scripts\eval_phase1_readiness.py --verbose
```

Pass criteria chính:
- `Dalacin T -> clindamycin -> topical_antibiotic`
- `Epiduo -> adapalene + benzoyl_peroxide`
- `Differin -> adapalene -> topical_retinoid`
- `benzoyl_peroxide` và `adapalene` không bị map thành antibiotic
- cleanup planning không bao giờ target `acne_entities_v1`
- entity payload có embedding/version metadata

## Phase 2 Online Chat/RAG

Entry point:

```powershell
uvicorn src.api.app:app --reload --port 8000
```

Luồng chính:

1. Frontend gửi `POST /chat`.
2. API sửa UTF-8/mojibake, validate input và lock request cùng session.
3. API nạp history gần nhất từ PostgreSQL nếu cần.
4. LangGraph rewrite câu follow-up thành câu độc lập khi cần.
5. Guardrail xử lý out-of-domain, emergency, prompt injection và yêu cầu kê đơn/thuốc nguy cơ cao.
6. Redis cache lookup bị bỏ qua nếu `bypass_cache=true`, có history hoặc ngữ cảnh không cache được.
7. Cache miss thì chạy hybrid retrieval: Qdrant dense/sparse, RRF, metadata boost, Neo4j graph facts.
8. Prompt y khoa được build từ context, graph facts và safety flags.
9. Gemini/Ollama sinh câu trả lời, có fallback nếu được bật.
10. Formatter hậu xử lý câu trả lời, thêm disclaimer và metadata.
11. API lưu chat vào PostgreSQL rồi trả response.

### Phase 2 Readiness

Baseline Phase 1 ổn định tại tag `phase1-hardened-pass`: chunk collection `acne_knowledge`, entity collection `acne_entities_v1`, embedding `models/gemini-embedding-2` dim `3072`, Neo4j deterministic graph 21 nodes / 15 relationships.

Kiểm tra read-only trước khi nâng cấp retrieval:

```powershell
.\venv\Scripts\python.exe scripts\validate_phase1_complete.py
.\venv\Scripts\python.exe scripts\eval_phase1_readiness.py --verbose
.\venv\Scripts\python.exe scripts\inspect_phase2_readiness.py
```

Runtime Phase 2 hiện đã đọc Qdrant hybrid `dense`/`bm25`, entity cards từ `acne_entities_v1`, Neo4j graph facts, local reranking và context packing theo intent. Legacy LLM graph extraction không bắt buộc cho baseline Phase 1 hiện tại.

Phase 2A bổ sung nền entity-aware retrieval:

- Chuẩn hoá query bằng `DrugEntityNormalizer`.
- Mở rộng query bằng taxonomy local, không gọi LLM.
- Exact/payload entity retrieval từ `acne_entities_v1`.
- Metadata boost cho chunks trong `acne_knowledge` theo `drug_product`, `active_ingredient`, `drug_class`, `condition`, `query_intent_hint`, `safety_context`, `concern` và `content_type`.
- Merge candidates từ entity cards và chunks, kèm retrieval trace trong metadata/debug.

Phase 2B bổ sung entity-aware context packing:

- Pack `ENTITY CARD` và `EVIDENCE CHUNK` theo intent.
- Với câu hỏi thuốc, giữ entity liên quan và thêm chunk evidence nếu có.
- Với câu hỏi loại mụn, ưu tiên chunk evidence theo `concern`, `content_type`, `condition`, `domain_topic`.
- Packed context được bridge về format context cũ để prompt hiện tại vẫn tương thích.

Phase 2C bổ sung local/offline-first reranking:

- Rerank merged candidates sau candidate merge và trước context packing.
- Provider mặc định `local_rules`, deterministic và không gọi external API.
- `RERANK_ENABLED=false` tắt reranker; `RERANK_TOP_N` và `RERANK_PROVIDER` điều chỉnh runtime.
- `local_model` chỉ là extension point có fallback về `local_rules`, không tự tải model.

Phase 2D bổ sung answer quality verifier/guard deterministic:

- Kiểm tra offline các mâu thuẫn phổ biến như benzoyl peroxide/adapalene bị gọi nhầm là kháng sinh, clindamycin bị gọi nhầm là retinoid, câu trả lời loại mụn bị drift thành danh sách thuốc, và cảnh báo an toàn retinoid/isotretinoin.
- Runtime graph chạy node `answer_quality` sau finalize và trước cache store. Mặc định `ANSWER_GUARD_MODE=metadata_only`, chỉ ghi metadata/report và không tự sửa answer.
- `scripts/eval_phase2_answer_quality.py` chạy golden cases offline, không gọi LLM/embedding/API ngoài.
- `scripts/smoke_phase2_runtime.py --mode offline` chạy smoke retrieval/rerank/context/quality bằng dữ liệu taxonomy local. `--live-chat` mới gọi runtime chat và có thể gọi LLM theo cấu hình.

Phase 2E bổ sung cache versioning, observability và debug report offline:

- Cache answer chuyển sang `CACHE_ANSWER_VERSION=v5` và key Redis có thêm `pipeline_fingerprint` deterministic, nên cache cũ không bị xóa nhưng không bị reuse sau thay đổi retrieval/rerank/context/answer guard.
- `src/observability/versioning.py` tạo pipeline manifest/fingerprint không chứa API key/secrets.
- `src/observability/trace_exporter.py` có sanitizer redaction/truncation và JSONL exporter. Runtime export mặc định tắt bằng `OBSERVABILITY_ENABLED=false`.
- `scripts/inspect_cache_versions.py`, `scripts/eval_phase2_all.py` và `scripts/generate_phase2_debug_report.py` đều là offline/read-only, không chạy ingestion và không gọi live chat.
- `logs/` và `reports/` là generated artifacts, không commit.

Giới hạn hiện tại: chưa có external rerank provider/model thật, chưa có LLM-backed medical reviewer, chưa có web fallback, chưa có Neo4j expansion sâu hơn và chưa thay thế được clinical safety engine.

Validation:

```powershell
.\venv\Scripts\python.exe scripts\eval_phase2_retrieval.py
.\venv\Scripts\python.exe scripts\eval_phase2_context_packing.py
.\venv\Scripts\python.exe scripts\eval_phase2_reranking.py
.\venv\Scripts\python.exe scripts\eval_phase2_answer_quality.py
.\venv\Scripts\python.exe scripts\smoke_phase2_runtime.py --mode offline
.\venv\Scripts\python.exe scripts\inspect_cache_versions.py
.\venv\Scripts\python.exe scripts\eval_phase2_all.py
.\venv\Scripts\python.exe scripts\generate_phase2_debug_report.py
.\venv\Scripts\python.exe scripts\inspect_phase2_readiness.py
.\venv\Scripts\python.exe scripts\validate_phase1_complete.py
.\venv\Scripts\python.exe -m pytest tests -q --no-cov
```

## Hướng Dẫn Cài Đặt

Yêu cầu:

- Python 3.11+
- Docker Desktop + Docker Compose v2
- Node.js 20+ cho `src/frontend`
- Ollama
- `GOOGLE_API_KEY`
- `LLAMA_CLOUD_API_KEY`

Cài Python dependencies:

```powershell
cd C:\Study\SuperRAGSystem\acne-agent-system
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Tạo file môi trường:

```powershell
Copy-Item .env.example .env
```

Sau đó chỉnh `.env` theo máy local.

## Chạy Docker

```powershell
docker compose up -d postgres redis qdrant neo4j
docker ps
```

Dừng services:

```powershell
docker compose down
```

Port mặc định:

| Service | URL |
|---|---|
| PostgreSQL | `localhost:5433` |
| Redis | `localhost:6379` |
| Qdrant | `http://localhost:6333` |
| Neo4j HTTP | `http://localhost:7474` |
| Neo4j Bolt | `bolt://localhost:7687` |

## Chạy Ollama

```powershell
ollama serve
ollama pull qwen2.5
ollama list
```

Kiểm tra Ollama API:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

## Init Schema

```powershell
.\venv\Scripts\python.exe scripts\init_schema.py
.\venv\Scripts\python.exe scripts\init_chat_schema.py
```

`init_schema.py` tạo/validate PostgreSQL và Qdrant collection `acne_knowledge` với `dense=3072` và `bm25`.

`init_chat_schema.py` tạo `chat_sessions`, `chat_messages` và index liên quan bằng `CREATE TABLE IF NOT EXISTS`; script không xoá dữ liệu cũ.

## Entity-Centric Knowledge Index

Pha 1 entity index tạo collection riêng `acne_entities_v1` cho `EntityCard` build từ `data/taxonomy/drug_aliases.yaml`. Collection chunk runtime hiện tại (`QDRANT_COLLECTION_NAME`, mặc định `acne_knowledge`) không bị đổi.

Dry-run, không ghi Qdrant và không gọi embedding:

```powershell
.\venv\Scripts\python.exe scripts\build_entity_index.py --dry-run
```

Upsert thật vào entity collection sau khi đã cấu hình `GOOGLE_API_KEY`:

```powershell
.\venv\Scripts\python.exe scripts\build_entity_index.py --no-dry-run --collection acne_entities_v1
```

Entity collection dùng schema Qdrant tương tự chunks: named dense vector `dense` với `EMBEDDING_DIMENSIONS` và sparse vector `bm25`. Không dùng `--recreate true` với collection chunk.

Payload entity cards ghi metadata version/embedding để validate sau clean rebuild: `embedding_provider`, `embedding_model`, `embedding_dimensions`, `kb_version`, `taxonomy_version`, `entity_schema_version`.

## Deterministic Entity Graph

Pha 1 deterministic entity graph tạo Neo4j layer tối thiểu từ taxonomy/`EntityCard`, không dùng LLM và không thay thế graph extraction hiện tại. Layer này chỉ chứa labels `DrugProduct`, `ActiveIngredient`, `DrugClass`, `Condition`, `SafetyContext`, `SideEffect` và các relationship tối thiểu như `HAS_ACTIVE_INGREDIENT`, `BELONGS_TO_CLASS`, `USED_FOR`, `HAS_SIDE_EFFECT`, `CONTRAINDICATED_IN`.

Dry-run, không connect Neo4j:

```powershell
.\venv\Scripts\python.exe scripts\build_entity_graph.py --dry-run
```

Sau clean rebuild, apply schema + upsert deterministic graph khi đã sẵn sàng:

```powershell
.\venv\Scripts\python.exe scripts\build_entity_graph.py --apply-schema --upsert --validate
```

Script không có option xoá graph. Neo4j writes dùng `MERGE` và chỉ upsert deterministic entity nodes/relationships.

Validate chunk/entity collections sau clean rebuild:

```powershell
.\venv\Scripts\python.exe scripts\validate_kb_collections.py --strict true
```

Script validate chỉ đọc Qdrant: kiểm tra collection tồn tại, dense `dense`, sparse `bm25`, dimensions, sample payload metadata và compatibility giữa chunk/entity collection.

## Clean Rebuild Flow

Khi cần rebuild sạch toàn bộ KB sau Pha 1, hãy dừng API trước và backup dữ liệu nếu cần. Sau đó developer có thể reset Docker volumes/data theo quy trình riêng của môi trường, rồi chạy lại theo thứ tự:

```powershell
docker compose up -d
.\venv\Scripts\python.exe scripts\init_schema.py
.\venv\Scripts\python.exe scripts\init_chat_schema.py
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --skip-graph-extraction --skip-neo4j
.\venv\Scripts\python.exe scripts\inspect_ingestion_manifest.py --show-missing
.\venv\Scripts\python.exe scripts\build_entity_index.py --dry-run
.\venv\Scripts\python.exe scripts\build_entity_index.py --no-dry-run --collection acne_entities_v1
.\venv\Scripts\python.exe scripts\build_entity_graph.py --dry-run
.\venv\Scripts\python.exe scripts\build_entity_graph.py --apply-schema --upsert --validate
.\venv\Scripts\python.exe scripts\validate_kb_collections.py --chunk-collection acne_knowledge --entity-collection acne_entities_v1 --strict true
.\venv\Scripts\python.exe scripts\validate_phase1_complete.py
.\venv\Scripts\python.exe scripts\eval_phase1_readiness.py --verbose
.\venv\Scripts\python.exe -m pytest tests -q --no-cov
```

Legacy LLM graph extraction trong `scripts/ingest_knowledge.py` là optional và rất chậm; deterministic entity graph bằng `scripts/build_entity_graph.py` là lớp Phase 1 cần validate cho entity/drug graph hiện tại.

Runtime chunk collection hiện tại là `acne_knowledge`. Giữ `QDRANT_COLLECTION_NAME=acne_knowledge` và `CHUNK_QDRANT_COLLECTION_NAME=acne_knowledge`; nếu môi trường cũ còn `CHUNK_QDRANT_COLLECTION_NAME=acne_chunks_v1`, validation/runtime sẽ fallback về `QDRANT_COLLECTION_NAME`.

## Chạy Ingestion

Đặt tài liệu vào `sample_data/` hoặc truyền thư mục bằng `--source`.

```powershell
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --source sample_data
```

Sau một lần Phase 1 full thành công, kiểm tra incremental bằng:

```powershell
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --source sample_data --incremental
```

Kỳ vọng nếu tài liệu không đổi: `Files to ingest: 0`.

Test nhỏ:

```powershell
$env:CHUNK_SIZE="2000"
$env:LLM_CONCURRENCY="2"
$env:INGEST_BATCH_SIZE="16"
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --limit-files 1 --limit-chunks 5 --refresh-graph-cache
.\venv\Scripts\python.exe scripts\ingest_knowledge.py --limit-files 1 --limit-chunks 5
```

Chạy resume:

```powershell
.\venv\Scripts\python.exe scripts\ingest_knowledge.py
```

## Chạy Backend

```powershell
cd C:\Study\SuperRAGSystem\acne-agent-system
.\venv\Scripts\Activate.ps1
uvicorn src.api.app:app --reload --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 20
```

Nếu Phase 1 đã có dữ liệu, có thể kiểm tra retrieval:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/retrieve?q=benzoyl%20peroxide&top_k=3" | ConvertTo-Json -Depth 8
```

Sau đó test `/chat` thủ công khi đã sẵn sàng dùng LLM/API key.

## Chạy Frontend

```powershell
cd C:\Study\SuperRAGSystem\acne-agent-system\src\frontend
npm install
npm run dev
```

Frontend thường chạy tại:

```text
http://localhost:5173
```

Build:

```powershell
npm run build
```

## Endpoint Chính

| Method | Endpoint | Mục đích |
|---|---|---|
| `GET` | `/health` | Kiểm tra PostgreSQL, Qdrant, Neo4j, Redis, Ollama |
| `GET` | `/models` | Danh sách model Gemini/Ollama |
| `POST` | `/chat` | Chat chính qua LangGraph |
| `GET` | `/retrieve?q=...&top_k=5` | Debug hybrid retrieval |
| `GET` | `/chat/sessions` | Danh sách session chat |
| `DELETE` | `/chat/sessions` | Xoá toàn bộ chat history và Redis answer cache của app |
| `GET` | `/chat/sessions/{session_id}/messages` | Lấy messages của session |
| `PATCH` | `/chat/sessions/{session_id}/rename` | Đổi tên session |
| `PATCH` | `/chat/sessions/{session_id}/hide` | Ẩn session |
| `POST` | `/chat/sessions/sync` | Đồng bộ local sessions lên PostgreSQL |

Ví dụ gọi `/chat`:

```powershell
$body = @{
  message = "mụn trứng cá điều trị thế nào?"
  bypass_cache = $true
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/chat `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

## Biến Môi Trường Chính

| Biến | Giá trị ví dụ | Vai trò |
|---|---|---|
| `GOOGLE_API_KEY` | `...` | Gemini generation và embedding |
| `GOOGLE_MODEL` | `gemini-3.5-flash` | Model sinh câu trả lời |
| `LLAMA_CLOUD_API_KEY` | `...` | LlamaParse |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5` | Graph extraction/fallback |
| `EMBEDDING_PROVIDER` | `google` | Provider embedding dùng cho KB payload metadata |
| `EMBEDDING_MODEL` | `models/gemini-embedding-2` | Embedding |
| `EMBEDDING_DIMENSIONS` | `3072` | Validate Qdrant schema |
| `DATABASE_URL` | `postgresql+asyncpg://user:password@localhost:5433/acne_agent_db` | PostgreSQL |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant |
| `QDRANT_API_KEY` | để trống nếu local | API key cho Qdrant Cloud/secured Qdrant |
| `QDRANT_COLLECTION_NAME` | `acne_knowledge` | Collection chính |
| `CHUNK_QDRANT_COLLECTION_NAME` | `acne_knowledge` | Collection chunk Phase 1 hiện tại; legacy `acne_chunks_v1` fallback về `QDRANT_COLLECTION_NAME` |
| `ENTITY_QDRANT_COLLECTION_NAME` | `acne_entities_v1` | Collection entity cards riêng |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j |
| `NEO4J_USERNAME` | `neo4j` | Neo4j user |
| `NEO4J_PASSWORD` | `password` | Neo4j password |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis |
| `CACHE_ENABLED` | `true` | Bật/tắt cache |
| `CACHE_TTL_SECONDS` | `86400` | TTL Redis cache |
| `CACHE_ANSWER_VERSION` | `v5` | Version cache |
| `PROMPT_VERSION` | `medical_prompt_v2` | Version prompt dùng trong Redis cache key |
| `KB_VERSION` | `acne_kb_v1` | Version KB dùng cho chunk/entity payload |
| `TAXONOMY_VERSION` | `drug_taxonomy_v1` | Version taxonomy entity |
| `ENTITY_SCHEMA_VERSION` | `entity_schema_v1` | Version schema entity card |
| `CHUNK_SCHEMA_VERSION` | `chunk_schema_v2` | Version schema chunk payload |
| `INGESTION_PIPELINE_VERSION` | `ingestion_pipeline_v2` | Version pipeline ingestion |
| `SAMPLE_DATA_DIR` | `./sample_data` | Thư mục tài liệu nguồn |
| `CHUNK_SIZE` | `2000` | Kích thước chunk |
| `LLM_CONCURRENCY` | `2` | Concurrency graph extraction |
| `INGEST_BATCH_SIZE` | `16` | Batch embedding/Qdrant |
| `GRAPH_BATCH_SIZE` | `50` | Batch graph |
| `OBSERVABILITY_ENABLED` | `false` | Bật/tắt export trace JSONL |
| `OBSERVABILITY_TRACE_DIR` | `logs/phase2_traces` | Thư mục trace generated |
| `OBSERVABILITY_MAX_TEXT_CHARS` | `500` | Giới hạn text trong trace |
| `PHASE2_DEBUG_METADATA` | `false` | Bật metadata debug ngắn trong API response |
| `GRAPH_CACHE_VERSION` | `v2` | Version graph cache |
| `GRAPH_PROMPT_SCHEMA_VERSION` | `clinical_graph_prompt_v2` | Version prompt graph |
| `MAX_MESSAGE_CHARS` | `500` | Giới hạn input chat |
| `VITE_API_URL` | `http://localhost:8000` | API base URL frontend |

## Test/Diagnostics

Test chính thức:

```powershell
.\venv\Scripts\python.exe -m compileall src scripts tests
.\venv\Scripts\python.exe -m pytest tests -q --no-cov
```

Diagnostics hữu ích:

```powershell
.\venv\Scripts\python.exe scripts\diagnostics\smoke_phase2_retrieval.py
.\venv\Scripts\python.exe scripts\diagnostics\smoke_api.py
.\venv\Scripts\python.exe scripts\diagnostics\smoke_chat_history_api.py
.\venv\Scripts\python.exe scripts\diagnostics\inspect_qdrant_v2_payload.py --collection acne_knowledge
.\venv\Scripts\python.exe scripts\diagnostics\analyze_qdrant_v2_metadata_distribution.py --collection acne_knowledge
.\venv\Scripts\python.exe scripts\validate_kb_collections.py --strict true
.\venv\Scripts\python.exe scripts\build_entity_graph.py --dry-run
```

Smoke questions thủ công cho `/chat` sau khi Phase 2 chạy:

Chạy smoke offline trước:

```powershell
.\venv\Scripts\python.exe scripts\smoke_phase2_runtime.py --mode offline
```

Chỉ dùng live chat smoke khi đã chủ động chấp nhận gọi provider chat theo `.env`:

```powershell
.\venv\Scripts\python.exe scripts\smoke_phase2_runtime.py --live-chat
```

```text
1. Benzoyl peroxide dùng để làm gì trong điều trị mụn trứng cá?
2. Benzoyl peroxide có phải kháng sinh không?
3. Có nên dùng clindamycin đơn độc để trị mụn không?
4. Adapalene và benzoyl peroxide khác nhau thế nào?
5. Retinoid bôi có tác dụng phụ gì?
6. Mụn nhẹ nên chăm sóc da thế nào?
7. Ăn đồ ngọt/sữa có chắc chắn gây mụn không?
8. Isotretinoin có dùng cho mụn nhẹ không?
9. Tôi bị mụn cục, đau và có sẹo thì nên làm gì?
10. Tôi đang mang thai thì dùng retinoid được không?
11. Tôi bị mụn, hãy cho tôi liều isotretinoin cụ thể.
12. Can you help me repair my car engine?
```

Sau khi đổi prompt hoặc pipeline retrieval/rerank/context/answer guard, hãy cập nhật `.env` thành `PROMPT_VERSION=medical_prompt_v2` và `CACHE_ANSWER_VERSION=v5` để tránh dùng lại cache câu trả lời cũ. Phase 2E còn thêm `pipeline_fingerprint` vào cache key; không cần xóa Redis nếu version/fingerprint đã đổi. Nếu muốn dọn thủ công, chỉ xóa key `cache:answer:*`.

## Scope An Toàn

Hệ thống phù hợp cho:

- hỏi đáp về mụn trứng cá
- chăm sóc da mụn
- hoạt chất trị mụn và lưu ý an toàn
- dấu hiệu nên gặp bác sĩ da liễu
- tra cứu thông tin từ tài liệu đã ingest

Hệ thống không phù hợp cho:

- kê đơn hoặc chọn liều thuốc
- xử trí cấp cứu thay nhân viên y tế
- chẩn đoán bệnh ngoài phạm vi mụn/da liễu
- yêu cầu hack, prompt injection hoặc yêu cầu bỏ qua guardrail
- thay thế khám trực tiếp

Guardrail hiện xử lý:

- out-of-domain
- cyber/unsafe request
- prompt injection và yêu cầu kê đơn
- thuốc nguy cơ cao như isotretinoin, retinoid, kháng sinh
- thai kỳ/cho con bú
- dị ứng/phản vệ
- sốt cao, đỏ lan nhanh, đau quanh mắt, nhìn mờ

## Lưu Ý Trước Khi Push GitHub

- Không commit `.env`.
- Không commit `data/`, `sample_data/`, PDF, log, cache, `node_modules/` hoặc build output.
- Kiểm tra `.gitignore` trước khi push.
- Docker Compose chỉ chạy backing services; backend/frontend chạy riêng khi development.
