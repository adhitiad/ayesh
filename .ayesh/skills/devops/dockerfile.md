---
name: dockerfile
description: "Penulisan & optimasi Dockerfile. Trigger: /dockerfile"
---

# Dockerfile Best Practices

## Basic Structure
```dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

EXPOSE 3000
USER node
CMD ["node", "server.js"]
```

## Multi-Stage Build
```dockerfile
# Build stage
FROM golang:1.21 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o server

# Runtime stage
FROM alpine:3.18
RUN apk --no-cache add ca-certificates
COPY --from=builder /app/server /server
USER nobody:nobody
ENTRYPOINT ["/server"]
```

## Layer Optimization
```dockerfile
# Bad - multiple layers
RUN apt-get update
RUN apt-get install -y curl
RUN apt-get install -y wget
RUN apt-get clean

# Good - single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        wget && \
    rm -rf /var/lib/apt/lists/*
```

## Caching
```dockerfile
# Bad - always invalidates cache
COPY . .
RUN npm install

# Good - dependencies cached separately
COPY package*.json ./
RUN npm ci --only=production
COPY . .
```

## Security
```dockerfile
FROM node:18-alpine
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --chown=appuser:appgroup . .
USER appuser
CMD ["node", "server.js"]

# Scan for vulnerabilities
# docker scan myimage
```

## Health Check
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1
```

## Common Patterns

### Python
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

### Go
```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o main

FROM alpine:3.18
COPY --from=builder /app/main /main
CMD ["/main"]
```

### Java
```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn package -DskipTests

FROM eclipse-temurin:17-jre
COPY --from=builder /app/target/*.jar /app.jar
CMD ["java", "-jar", "/app.jar"]
```

### Nginx
```dockerfile
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY dist/ /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## .dockerignore
```
.git
node_modules
*.md
.env
.env.*
Dockerfile
docker-compose*.yml
.dockerignore
*.log
```

## Best Practices
```
1. Use specific base image tags (node:18-alpine, not node:latest)
2. Minimize layers (combine RUN commands)
3. Use multi-stage builds for compiled languages
4. Order instructions from least to most frequently changing
5. Use COPY over ADD (unless tar extraction needed)
6. Run as non-root user
7. Use .dockerignore
8. Scan images for vulnerabilities
9. Pin package versions in production
10. Don't store secrets in images
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Build lambat | Perbaiki cache, perkecil context |
| Image terlalu besar | Multi-stage build, alpine base |
| Build invalidates cache | Cek urutan instruksi |
| Permission error | Cek `USER` directive, `chown` |
| Secret bocor | Gunakan build secrets |
