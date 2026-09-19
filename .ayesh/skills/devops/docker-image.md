---
name: docker-image
description: "Image management Docker (build, push, pull). Trigger: /dimage"
---

# Docker Image Management

## Image Lifecycle
```bash
docker pull nginx:1.25
docker pull --all-tags nginx
docker images
docker images -a
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
docker images --filter "dangling=true"
docker images --filter "reference=nginx:*"

docker tag nginx:latest myrepo/nginx:v1
docker tag nginx:latest myrepo/nginx:latest

docker push myrepo/nginx:v1
docker push -a myrepo/nginx

docker rmi nginx:old
docker rmi $(docker images -q --filter "dangling=true")
docker image prune
docker image prune -a
docker image prune -af
```

## Build
```bash
docker build -t myimage:latest .
docker build -t myimage:latest -f Dockerfile.prod .
docker build --no-cache -t myimage:latest .
docker build --target builder -t myimage:builder .
docker build --build-arg VERSION=1.0 -t myimage:1.0 .
```

## Image Inspection
```bash
docker history nginx:latest
docker inspect nginx:latest
docker inspect -f "{{.Config.Env}}" nginx:latest
docker inspect -f "{{.Config.ExposedPorts}}" nginx:latest
docker inspect -f "{{.RootFS.Layers}}" nginx:latest

docker image inspect nginx:latest
docker image ls --digests
```

## Save & Load
```bash
docker save nginx:latest > nginx.tar
docker save nginx:latest | gzip > nginx.tar.gz
docker save -o nginx.tar nginx:latest nginx:alpine

docker load < nginx.tar
docker load < nginx.tar.gz
docker load -i nginx.tar
```

## Image History
```bash
docker history nginx:latest
docker history --no-trunc nginx:latest
docker history --format "{{.CreatedBy}}: {{.Size}}" nginx:latest
```

## Cleanup
```bash
docker image prune
docker image prune -a
docker image prune -af
docker system prune -a
docker system prune -af --volumes
```

## Common Patterns

### Multi-Tag
```bash
docker build -t myrepo/app:latest .
docker tag myrepo/app:latest myrepo/app:1.0
docker push myrepo/app:latest
docker push myrepo/app:1.0
```

### Export Image
```bash
docker save myrepo/app:latest | gzip > app.tar.gz
# On another machine
docker load < app.tar.gz
```

### Cleanup Dangling
```bash
docker images --filter "dangling=true"
docker image prune -f
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Pull timeout | Cek network, registry auth |
| Build cache invalidation | Cek urutan COPY/RUN |
| Image terlalu besar | Multi-stage build, alpine base |
| Push gagal | `docker login`, cek tag |
| Layer corrupt | `docker image prune -a`, re-pull |
