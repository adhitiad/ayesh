---
name: compose
description: "Docker Compose multi-container setup. Trigger: /compose"
---

# Docker Compose

## Basic Commands
```bash
docker compose up
docker compose up -d
docker compose up --build
docker compose up -d --force-recreate
docker compose up service1 service2

docker compose down
docker compose down -v           # remove volumes
docker compose down --rmi all    # remove images

docker compose ps
docker compose ps -a
docker compose logs
docker compose logs -f service
docker compose logs --tail 100 service

docker compose exec service bash
docker compose run service command
docker compose exec service command

docker compose build
docker compose build --no-cache service
docker compose pull
```

## Basic Structure
```yaml
version: '3.8'

services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - app
    environment:
      - NODE_ENV=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost"]
      interval: 30s
      timeout: 3s
      retries: 3

  app:
    build: .
    ports:
      - "3000:3000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/mydb
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=mydb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

## Common Patterns

### Development Stack
```yaml
version: '3.8'

services:
  app:
    build: .
    volumes:
      - ./src:/app/src
      - /app/node_modules
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=development

  db:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=devdb
      - POSTGRES_PASSWORD=devpass

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
```

### Production Stack
```yaml
version: '3.8'

services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - app1
      - app2

  app1:
    build: .
    environment:
      - NODE_ENV=production
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  db:
    image: postgres:15-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      placement:
        constraints:
          - node.labels.db == true

volumes:
  pgdata:
```

## Scaling
```bash
docker compose up -d --scale app=3
docker compose up -d --scale web=2 --scale app=5
```

## Profiles
```yaml
services:
  app:
    image: myapp
    profiles: ["web", "api"]

  test:
    image: myapp-test
    profiles: ["test"]
```

```bash
docker compose --profile web up
docker compose --profile test up
```

## Environments
```yaml
services:
  app:
    image: myapp
    env_file:
      - .env
      - .env.production
    environment:
      - NODE_ENV=production
```

```bash
# .env file
POSTGRES_USER=user
POSTGRES_PASSWORD=pass
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Service tidak start | `docker compose logs service` |
| Port conflict | Cek port mapping, `docker compose ps` |
| Network error | `docker network inspect`, cek depends_on |
| Volume tidak mount | Cek path, permissions |
| Build error | `docker compose build --no-cache` |
