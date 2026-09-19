---
name: docker-networking
description: "Jaringan Docker containers. Trigger: /dnetwork"
---

# Docker Networking

## Network Types

### Bridge (Default)
```bash
docker network create mybridge
docker run -d --network mybridge --name web nginx
docker run -d --network mybridge --name app myapp
docker network inspect mybridge

# Containers communicate via container name
docker exec app ping web
```

### Host
```bash
docker run -d --network host nginx
docker run -d --network host --name app myapp

# Port automatically mapped to host
curl http://localhost:80
```

### None
```bash
docker run -d --network none alpine
docker network create none_net --driver none
```

### Overlay (Swarm)
```bash
docker network create --driver overlay mynet
docker service create --network mynet --name web nginx
docker service create --network mynet --name app myapp
```

## DNS Resolution
```bash
# Automatic DNS for container names
docker exec app ping web

# Custom DNS
docker run -d --dns 8.8.8.8 nginx
docker run -d --dns-search mydomain.com nginx

# /etc/hosts mapping
docker run -d --add-host=host.docker.internal:host-gateway nginx
```

## Port Mapping
```bash
# Single port
docker run -d -p 8080:80 nginx

# Multiple ports
docker run -d -p 8080:80 -p 8443:443 nginx

# Range
docker run -d -p 8080-8090:80-90 nginx

# UDP
docker run -d -p 5353:53/udp nginx

# Bind to specific interface
docker run -d -p 127.0.0.1:8080:80 nginx

# List port mappings
docker port container_name
```

## Network Inspection
```bash
docker network ls
docker network inspect mybridge
docker network inspect -f '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}' mybridge

# Connected containers
docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' mybridge
```

## Network Management
```bash
docker network create mynet
docker network create --driver bridge mynet
docker network create --subnet 172.20.0.0/16 mynet
docker network create --gateway 172.20.0.1 mynet

docker network connect mynet container_name
docker network disconnect mynet container_name

docker network rm mynet
docker network prune
```

## Custom Bridge
```bash
docker network create \
    --driver bridge \
    --subnet 172.20.0.0/16 \
    --gateway 172.20.0.1 \
    mynet

docker run -d --network mynet --ip 172.20.0.10 --name web nginx
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Container tidak bisa ping | Cek `docker network inspect`, pastikan sama |
| DNS tidak resolve | Cek DNS config, restart service |
| Port tidak accessible | Cek port mapping, firewall |
| Bridge tidak ada | `docker network create` |
| Network timeout | Cek `docker network inspect` |
