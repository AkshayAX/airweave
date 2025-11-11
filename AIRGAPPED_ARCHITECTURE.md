# Air-Gapped Document Search System Architecture

## Recommended Approach: Extract + Simplify

Based on analysis of the Airweave codebase, here's a blueprint for your on-premise, air-gapped document search system with RBAC.

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    FRONTEND                         │
│  React + TypeScript (minimal)                       │
│  ├─ Document upload interface                       │
│  ├─ Search UI                                       │
│  ├─ Admin panel (users/orgs/roles)                  │
│  └─ No external dependencies                        │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP/REST API
┌─────────────────┴───────────────────────────────────┐
│              FASTAPI BACKEND                        │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ API Endpoints                                │  │
│  │ ├─ POST /documents/upload                    │  │
│  │ ├─ POST /search                              │  │
│  │ ├─ GET/POST /users, /organizations          │  │
│  │ └─ POST /auth/api-key                        │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ Document Processing                          │  │
│  │ ├─ File type detection                       │  │
│  │ ├─ Format-specific converters ← AIRWEAVE    │  │
│  │ │  ├─ PDF (pdfminer-six)                    │  │
│  │ │  ├─ DOCX (python-docx)                    │  │
│  │ │  ├─ XLSX (openpyxl)                       │  │
│  │ │  ├─ Code (tree-sitter)                    │  │
│  │ │  └─ HTML, TXT, CSV, JSON                  │  │
│  │ ├─ Chunking (semantic) ← AIRWEAVE           │  │
│  │ └─ Embedding (FastEmbed local)               │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ Search Module                                │  │
│  │ ├─ Query embedding (FastEmbed)               │  │
│  │ ├─ Vector search (Qdrant)                    │  │
│  │ ├─ Keyword search (PostgreSQL FTS)           │  │
│  │ ├─ Hybrid ranking                            │  │
│  │ └─ Optional: Local LLM (Ollama)              │  │
│  └──────────────────────────────────────────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐  │
│  │ RBAC & Auth ← AIRWEAVE MODELS               │  │
│  │ ├─ User model (email-based)                  │  │
│  │ ├─ Organization model                        │  │
│  │ ├─ UserOrganization (roles)                  │  │
│  │ │  ├─ owner (full control)                  │  │
│  │ │  ├─ admin (manage users)                  │  │
│  │ │  └─ member (read-only)                    │  │
│  │ └─ API key authentication                    │  │
│  └──────────────────────────────────────────────┘  │
└──────────────────┬────────────────┬────────────────┘
                   │                │
         ┌─────────┴────────┐  ┌───┴─────────────┐
         │   PostgreSQL     │  │    Qdrant       │
         │                  │  │                 │
         │ ├─ Users         │  │ ├─ Embeddings  │
         │ ├─ Organizations │  │ ├─ Vectors     │
         │ ├─ Documents     │  │ └─ Metadata    │
         │ ├─ Chunks        │  │                 │
         │ ├─ API Keys      │  │                 │
         │ └─ FTS Index     │  │                 │
         └──────────────────┘  └─────────────────┘
```

---

## Components to Extract from Airweave

### 1. Document Converters (Copy as-is)
**Source:** `backend/app/conversions/converters/`

```
Your Project
└── backend/
    └── app/
        └── conversions/
            ├── pdf_converter.py       ← Airweave
            ├── docx_converter.py      ← Airweave
            ├── xlsx_converter.py      ← Airweave
            ├── code_converter.py      ← Airweave (tree-sitter)
            ├── html_converter.py      ← Airweave
            ├── txt_converter.py       ← Airweave
            └── base_converter.py      ← Airweave (interface)
```

**Dependencies needed:**
```
pdfminer-six>=20250506
python-docx>=1.2.0
openpyxl>=3.1.5
tree-sitter>=0.23.5
html-to-markdown>=2.4.1
```

### 2. Chunking Logic
**Source:** `backend/app/platform/entity_processing/operations/chunking/`

```python
# Extract semantic_chunking.py
from backend.app.platform.entity_processing.operations.chunking import SemanticChunker

chunker = SemanticChunker(
    chunk_size=500,
    chunk_overlap=50
)
chunks = chunker.chunk(text)
```

**Dependency:**
```
chonkie>=1.4.0  # Semantic chunking
```

### 3. Database Models (Simplified)
**Source:** `backend/app/database/`

**Tables to copy:**
- `user.py` - User model
- `organization.py` - Organization model
- `user_organization.py` - Many-to-many with roles
- `api_key.py` - API authentication

**New tables to add:**
```python
# document.py
class Document(Base):
    id: UUID
    organization_id: UUID  # Tenant isolation
    filename: str
    file_type: str
    file_size: int
    upload_date: datetime
    uploaded_by: UUID  # User ID

# chunk.py
class Chunk(Base):
    id: UUID
    document_id: UUID
    organization_id: UUID  # For search filtering
    content: str
    chunk_index: int
    vector_id: str  # Qdrant point ID
```

### 4. Search Architecture (Simplified)
**Source:** `backend/app/search/`

```python
# search_service.py (simplified)
class SearchService:
    def __init__(self, qdrant_client, db_session):
        self.qdrant = qdrant_client
        self.db = db_session
        self.embedder = FastEmbed()  # Local

    async def search(
        self,
        query: str,
        organization_id: UUID,  # RBAC filter
        limit: int = 10
    ):
        # 1. Embed query (local)
        vector = self.embedder.embed(query)

        # 2. Vector search (Qdrant)
        vector_results = self.qdrant.search(
            collection_name=f"org_{organization_id}",
            query_vector=vector,
            limit=limit * 2
        )

        # 3. Keyword search (PostgreSQL FTS)
        keyword_results = await self.db.execute(
            select(Chunk)
            .where(Chunk.organization_id == organization_id)
            .where(Chunk.content.match(query))  # Full-text search
            .limit(limit * 2)
        )

        # 4. Hybrid merge + rank
        return self._merge_results(vector_results, keyword_results, limit)
```

---

## Minimal Dependencies

### Python Backend (17 packages vs Airweave's 66+)
```
# Web framework
fastapi>=0.115.6
uvicorn>=0.34.0
pydantic>=2.10.6
pydantic-settings>=2.7.0

# Database
sqlalchemy>=2.0.36
asyncpg>=0.29.0
alembic>=1.14.0

# Vector DB
qdrant-client>=1.13.3
fastembed>=0.4.2  # Local embeddings

# Document processing
pdfminer-six>=20250506
python-docx>=1.2.0
openpyxl>=3.1.5
tree-sitter>=0.23.5
html-to-markdown>=2.4.1
chonkie>=1.4.0  # Semantic chunking

# Utilities
cryptography>=46.0.2
python-dotenv>=1.0.0
```

### Optional (if you need LLM features)
```
# Local LLM
ollama>=0.1.0  # Python client for Ollama
```

---

## RBAC Implementation

### Role Matrix
```
Feature              | owner | admin | member
---------------------|-------|-------|--------
Upload documents     |   ✓   |   ✓   |   ✗
Search documents     |   ✓   |   ✓   |   ✓
Delete documents     |   ✓   |   ✓   |   ✗
Invite users         |   ✓   |   ✓   |   ✗
Manage roles         |   ✓   |   ✗   |   ✗
Delete organization  |   ✓   |   ✗   |   ✗
```

### Access Control Middleware
```python
# From Airweave pattern
from backend.app.api.context import APIContext

async def check_permission(
    context: APIContext,
    required_role: str
):
    user_org = await db.get_user_organization(
        user_id=context.user_id,
        org_id=context.organization_id
    )

    if not user_org or user_org.role not in ROLE_HIERARCHY[required_role]:
        raise HTTPException(403, "Insufficient permissions")
```

---

## Deployment Stack

### Docker Compose (3 services vs Airweave's 9)
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: airweave
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: airweave
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:v1.12.0
    volumes:
      - qdrant_data:/qdrant/storage

  backend:
    build: ./backend
    environment:
      POSTGRES_HOST: postgres
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
    ports:
      - "8001:8001"
    depends_on:
      - postgres
      - qdrant

  frontend:
    build: ./frontend
    ports:
      - "8080:80"
    depends_on:
      - backend

volumes:
  postgres_data:
  qdrant_data:
```

### Optional: Local LLM
```yaml
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    # Pre-download models:
    # docker exec ollama ollama pull llama3.2
```

---

## Implementation Phases

### Phase 1: Core System (Week 1-2)
- [ ] Set up FastAPI project structure
- [ ] Copy database models from Airweave (User, Org, UserOrg)
- [ ] Implement PostgreSQL + SQLAlchemy setup
- [ ] Add basic auth (API keys)
- [ ] Create Docker Compose stack

### Phase 2: Document Processing (Week 2-3)
- [ ] Copy converters from Airweave
- [ ] Implement file upload endpoint
- [ ] Add document storage in PostgreSQL
- [ ] Implement chunking logic (from Airweave)
- [ ] Set up Qdrant collections (per organization)

### Phase 3: Search (Week 3-4)
- [ ] Integrate FastEmbed for local embeddings
- [ ] Implement vector search (Qdrant)
- [ ] Add PostgreSQL full-text search
- [ ] Create hybrid search merge logic
- [ ] Add RBAC filtering to search

### Phase 4: Frontend (Week 4-5)
- [ ] React app setup
- [ ] Document upload UI
- [ ] Search interface
- [ ] Admin panel (users/orgs/roles)

### Phase 5: Testing & Optimization (Week 5-6)
- [ ] Load testing with realistic document corpus
- [ ] Security audit (SQL injection, XSS, etc.)
- [ ] Performance tuning (indexing, caching)
- [ ] Documentation

---

## Key Advantages Over Full Airweave

| Aspect | Airweave | Your System |
|--------|----------|-------------|
| **Dependencies** | 66+ Python packages | ~17 packages |
| **Docker Services** | 9 services | 3-4 services |
| **External APIs** | OpenAI, Anthropic, etc. | None (fully local) |
| **Complexity** | High (multi-purpose) | Low (focused) |
| **Codebase Size** | ~50K LOC | ~5K LOC (est.) |
| **Audit Surface** | Large | Small |
| **Maintenance** | Complex | Simple |
| **Air-Gapped** | Requires modifications | Native support |

---

## What You Lose (vs Full Airweave)

- ❌ LLM-powered answer generation (unless you add Ollama)
- ❌ Query expansion (can add basic keyword variations)
- ❌ Advanced reranking (Cohere/OpenAI)
- ❌ External source sync (Slack, Salesforce, etc.)
- ❌ Web scraping
- ❌ Temporal workflows (not needed for simple upload)
- ❌ Analytics/telemetry

**But you probably don't need these for on-premise document search!**

---

## Migration Path (If Needed Later)

If you later decide you need more features:

1. **Add Temporal workflows** - For async document processing
2. **Integrate local LLM** - Ollama for answer generation
3. **Add database connectors** - For syncing internal databases
4. **Implement custom sources** - For internal APIs

Your simplified system is a solid foundation that can grow.

---

## Conclusion

**Recommended approach:** Extract the valuable components from Airweave (converters, chunking, RBAC models, search patterns) and build a focused, air-gapped document search system.

**Why not modify Airweave directly?**
- Too many unused dependencies (cloud APIs, integrations, billing)
- Harder to audit and secure
- Ongoing maintenance burden
- Not designed for air-gapped from the ground up

**What to take from Airweave:**
- Document processing pipeline (excellent quality)
- Database schema for RBAC
- Search architecture patterns
- Chunking logic

**What to build yourself:**
- Simplified API layer (FastAPI)
- Document upload handling
- Search service (Qdrant + PostgreSQL FTS)
- Minimal frontend

**Estimated effort:** 4-6 weeks for MVP vs 6-10 weeks to modify Airweave.
