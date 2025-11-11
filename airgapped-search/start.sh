#!/bin/bash

set -e

echo "=========================================="
echo "Air-Gapped Document Search System"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env

    # Generate SECRET_KEY
    echo "Generating SECRET_KEY..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    # Update .env with generated key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/SECRET_KEY=generate_a_secure_random_key_here/SECRET_KEY=$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/SECRET_KEY=generate_a_secure_random_key_here/SECRET_KEY=$SECRET_KEY/" .env
    fi

    echo "✓ Environment file created"
    echo ""
fi

echo "Starting services..."
echo ""

# Start Docker Compose
docker-compose up -d

echo ""
echo "Waiting for services to be healthy..."
echo ""

# Wait for PostgreSQL
echo -n "Waiting for PostgreSQL"
until docker-compose exec -T postgres pg_isready -U airgapped_search > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo " ✓"

# Wait for Qdrant
echo -n "Waiting for Qdrant"
until curl -s http://localhost:6333/health > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo " ✓"

echo ""
echo "Running database migrations..."
docker-compose exec -T backend alembic upgrade head || echo "Note: Migrations may not be ready yet"

echo ""
echo "=========================================="
echo "✓ Services are running!"
echo "=========================================="
echo ""
echo "Access points:"
echo "  - Frontend:  http://localhost:8080"
echo "  - Backend:   http://localhost:8001"
echo "  - API Docs:  http://localhost:8001/docs"
echo "  - Qdrant UI: http://localhost:6333/dashboard"
echo ""
echo "Useful commands:"
echo "  - View logs:       docker-compose logs -f"
echo "  - Stop services:   docker-compose down"
echo "  - Restart:         docker-compose restart"
echo ""
echo "=========================================="
