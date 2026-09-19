---
name: docker-container
description: "Container lifecycle management Docker. Trigger: /dcontainer"
---

# Docker Container Management

## Container Lifecycle
```bash
docker run -d nginx
docker run -d --name web nginx
docker run -d -p 8080:80 nginx
docker run -d -v /host/path:/container/path nginx
docker run -d -e "ENV_VAR=value" nginx
docker run -d --rm nginx
docker run -d --memory 512m nginx
docker run -it ubuntu bash

docker ps
docker ps -a
docker ps -q
docker ps -f "status=running"
docker ps -f "status=exited"
docker ps -f "label=env=prod"

docker stop container_name
docker stop $(docker ps -q)
docker start container_name
docker restart container_name
docker pause container_name
docker unpause container_name

docker rm container_name
docker rm -f container_name
docker rm $(docker ps -aq)

docker exec -it container_name bash
docker exec container_name command
docker attach container_name
docker logs container_name
docker logs -f container_name
docker logs --tail 100 container_name
docker logs --since 1h container_name
```

## Resource Monitoring
```bash
docker stats
docker stats --no-stream
docker stats container1 container2

docker top container_name
docker inspect container_name
docker inspect -f "{{.State.Status}}" container_name
docker inspect -f "{{.NetworkSettings.IPAddress}}" container_name

docker port container_name
docker diff container_name
docker cp container_name:/path/file ./local_file
docker cp ./local_file container_name:/path/file
```

## Container Lifecycle States
```
Created → Running → Paused → Stopped → Deleted
   ↓         ↓        ↓        ↓
  run      pause   unpause    rm
```

## Cleanup
```bash
docker container prune
docker container prune -f
docker system prune
docker system prune -a
docker system prune --volumes
```

## Common Scenarios

### Debug Container
```bash
docker exec -it container_name /bin/sh
docker logs -f --tail 50 container_name
docker inspect container_name
docker stats container_name
```

### Copy Files
```bash
docker cp container_name:/var/log/app.log ./app.log
docker cp ./config.yml container_name:/app/config.yml
```

### Batch Stop
```bash
docker stop $(docker ps -q)
docker rm $(docker ps -aq)
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Container exited | `docker logs container_name` |
| OOMKilled | Naikkan `--memory` |
| Tidak bisa exec | Cek status, `docker start` |
| Port conflict | `docker ps`, cek port mapping |
| Disk penuh | `docker system prune` |
