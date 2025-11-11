# Air-Gapped Document Search System

A simplified, on-premise document search system with role-based access control (RBAC), built by extracting key components from Airweave.

## Features

- **Document Processing**: Support for PDF, DOCX, XLSX, code files, and more
- **Semantic Search**: Local embeddings using FastEmbed (no internet required)
- **Keyword Search**: PostgreSQL full-text search
- **Hybrid Search**: Combines semantic and keyword search
- **Multi-Tenancy**: Organization-based isolation
- **RBAC**: Owner, Admin, and Member roles
- **Air-Gapped**: Runs completely offline

## Architecture

```
┌─────────────────┐
│   React UI      │  (Port 8080)
└────────┬────────┘
         │
┌────────┴────────┐
│  FastAPI Backend│  (Port 8001)
└────────┬────────┘
         │
    ┌────┴─────┬─────────────┐
    │          │             │
┌───┴────┐ ┌──┴───────┐ ┌──┴──────┐
│Postgres│ │  Qdrant  │ │FastEmbed│
│(5432)  │ │  (6333)  │ │ (Local) │
└────────┘ └──────────┘ └─────────┘
```

## Quick Start

### Prerequisites

- Docker and Docker Compose
- At least 4GB RAM
- 10GB disk space

### Installation

1. **Copy environment configuration:**
   ```bash
   cp .env.example .env
   ```

2. **Generate secrets:**
   ```bash
   # Generate a secure secret key
   python3 -c "import secrets; print(secrets.token_urlsafe(32))" > secret_key.txt
   # Add to .env file:
   # SECRET_KEY=<paste-generated-key>
   ```

3. **Start the stack:**
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

4. **Access the application:**
   - Frontend: http://localhost:8080
   - Backend API: http://localhost:8001
   - API Docs: http://localhost:8001/docs

### Manual Setup

If you prefer manual setup:

```bash
# Start services
docker-compose up -d

# Wait for PostgreSQL to be ready
docker-compose exec postgres pg_isready -U airgapped_search

# Run migrations
docker-compose exec backend alembic upgrade head

# Check logs
docker-compose logs -f backend
```

## Project Structure

```
airgapped-search/
├── backend/
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   │   ├── deps/         # Dependencies & auth
│   │   │   └── endpoints/    # Route handlers
│   │   ├── core/             # Configuration
│   │   ├── database/         # Models & database setup
│   │   │   └── models/       # SQLAlchemy models
│   │   ├── conversions/      # Document converters
│   │   │   └── converters/   # Format-specific converters
│   │   └── search/           # Search service
│   ├── alembic/              # Database migrations
│   ├── requirements.txt      # Python dependencies
│   └── Dockerfile
├── frontend/                 # React application (TODO)
├── docker-compose.yml        # Service orchestration
├── .env.example              # Environment template
└── README.md
```

## Database Models

### User Model
- Email-based authentication
- Superuser flag for system admins
- Many-to-many relationship with organizations

### Organization Model
- Multi-tenant container
- Owns documents and users
- Isolated search spaces

### UserOrganization Model
- Junction table with roles
- Roles: `owner`, `admin`, `member`
- Primary organization flag

### Document Model
- Uploaded files metadata
- Processing status tracking
- Organization-scoped

### Chunk Model
- Document segments for search
- Links to Qdrant vectors
- Organization-scoped for fast filtering

### APIKey Model
- Programmatic authentication
- User and organization scoped
- Expiration support

## API Endpoints (Planned)

### Authentication
- `POST /api/auth/register` - Create account
- `POST /api/auth/login` - Login
- `POST /api/auth/api-key` - Generate API key

### Organizations
- `GET /api/organizations` - List user's organizations
- `POST /api/organizations` - Create organization
- `GET /api/organizations/{id}` - Get organization details
- `PATCH /api/organizations/{id}` - Update organization

### Users
- `GET /api/users/me` - Get current user
- `POST /api/organizations/{id}/users` - Invite user
- `PATCH /api/organizations/{id}/users/{user_id}` - Update role

### Documents
- `POST /api/documents/upload` - Upload document
- `GET /api/documents` - List documents
- `GET /api/documents/{id}` - Get document details
- `DELETE /api/documents/{id}` - Delete document

### Search
- `POST /api/search` - Search documents
- `GET /api/search/history` - Search history

## RBAC Permissions

| Action | Owner | Admin | Member |
|--------|-------|-------|--------|
| Upload documents | ✓ | ✓ | ✗ |
| Search documents | ✓ | ✓ | ✓ |
| Delete documents | ✓ | ✓ | ✗ |
| Invite users | ✓ | ✓ | ✗ |
| Manage roles | ✓ | ✗ | ✗ |
| Delete organization | ✓ | ✗ | ✗ |

## Development

### Install dependencies locally

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run database migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Run tests (TODO)

```bash
pytest backend/tests/
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | postgres | PostgreSQL hostname |
| `POSTGRES_PORT` | 5432 | PostgreSQL port |
| `POSTGRES_USER` | airgapped_search | Database user |
| `POSTGRES_PASSWORD` | changeme | Database password |
| `POSTGRES_DB` | airgapped_search | Database name |
| `QDRANT_HOST` | qdrant | Qdrant hostname |
| `QDRANT_PORT` | 6333 | Qdrant port |
| `SECRET_KEY` | (required) | JWT signing key |
| `EMBEDDING_MODEL` | BAAI/bge-small-en-v1.5 | FastEmbed model |
| `EMBEDDING_DIMENSION` | 384 | Vector dimensions |
| `MAX_UPLOAD_SIZE_MB` | 100 | Max file size |

### Supported Document Formats

- **Documents**: PDF, DOCX, PPTX, TXT, MD
- **Spreadsheets**: XLSX, CSV
- **Code**: Python, JavaScript, TypeScript, Java, Go, Rust, etc.
- **Data**: JSON, YAML, XML
- **Web**: HTML, HTM

## Deployment

### Production Checklist

- [ ] Change default passwords in `.env`
- [ ] Set strong `SECRET_KEY`
- [ ] Configure HTTPS/TLS
- [ ] Set up backups for PostgreSQL and Qdrant volumes
- [ ] Configure firewall rules
- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Review resource limits in `docker-compose.yml`

### Backup & Restore

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U airgapped_search airgapped_search > backup.sql

# Restore PostgreSQL
docker-compose exec -T postgres psql -U airgapped_search airgapped_search < backup.sql

# Backup Qdrant
docker-compose exec qdrant tar czf /tmp/qdrant-backup.tar.gz /qdrant/storage
docker cp airgapped-qdrant:/tmp/qdrant-backup.tar.gz ./qdrant-backup.tar.gz
```

## Extracted Components from Airweave

This project extracts and simplifies the following components:

- **Database Models**: User, Organization, RBAC system
- **Document Converters**: PDF, DOCX, XLSX, code parsers
- **Chunking Logic**: Semantic chunking for optimal search
- **Search Patterns**: Hybrid search architecture

## Differences from Full Airweave

| Feature | Airweave | This Project |
|---------|----------|--------------|
| Cloud LLMs | Required | Optional (local only) |
| External APIs | 30+ integrations | None (air-gapped) |
| Dependencies | 66+ packages | ~20 packages |
| Services | 9 Docker containers | 3 containers |
| Temporal | Required | Not needed |
| Redis | Required | Not needed |
| Analytics | PostHog | None |
| Billing | Stripe | None |

## Roadmap

- [x] Database models and migrations
- [x] Docker Compose setup
- [ ] Document converters integration
- [ ] File upload API
- [ ] Qdrant integration
- [ ] FastEmbed integration
- [ ] Search service implementation
- [ ] RBAC middleware
- [ ] React frontend
- [ ] User authentication
- [ ] API documentation
- [ ] End-to-end tests

## Troubleshooting

### PostgreSQL won't start
```bash
# Check logs
docker-compose logs postgres

# Reset database
docker-compose down -v
docker-compose up -d postgres
```

### Qdrant connection errors
```bash
# Check Qdrant health
curl http://localhost:6333/health

# Restart Qdrant
docker-compose restart qdrant
```

### Backend errors
```bash
# Check logs
docker-compose logs backend

# Restart backend
docker-compose restart backend
```

## Contributing

This is a simplified, self-contained project. To add features:

1. Create a feature branch
2. Implement changes
3. Test thoroughly
4. Update documentation
5. Submit for review

## License

This project extracts components from Airweave (Apache 2.0 License).

## Support

For issues or questions, refer to:
- Backend logs: `docker-compose logs backend`
- Database logs: `docker-compose logs postgres`
- Qdrant logs: `docker-compose logs qdrant`

## Security Considerations

This system is designed for air-gapped environments:

- No external API calls
- All data stored locally
- Local embedding generation
- API key authentication
- Organization-based data isolation
- RBAC for access control

Ensure you:
- Use strong passwords
- Rotate API keys regularly
- Keep systems updated
- Monitor access logs
- Back up data regularly
