---
name: kubernetes
description: "Manajemen cluster & deployment Kubernetes. Trigger: /kubernetes"
---

# Kubernetes Cluster Management

## Cluster Operations
```bash
kubectl cluster-info
kubectl cluster-info dump
kubectl get nodes
kubectl get nodes -o wide
kubectl describe node node_name
kubectl top nodes
```

## Pod Management
```bash
kubectl get pods
kubectl get pods -n namespace
kubectl get pods -o wide
kubectl get pods --all-namespaces
kubectl get pods -l app=nginx
kubectl get pods --field-selector status.phase=Running

kubectl describe pod pod_name
kubectl logs pod_name
kubectl logs pod_name -c container_name
kubectl logs -f pod_name
kubectl logs --previous pod_name

kubectl exec -it pod_name -- bash
kubectl exec -it pod_name -c container_name -- bash
kubectl cp pod_name:/path/file ./local_file
kubectl cp ./local_file pod_name:/path/file

kubectl delete pod pod_name
kubectl delete pod pod_name --grace-period=0 --force
```

## Deployment
```bash
kubectl get deployments
kubectl describe deployment deploy_name
kubectl create deployment nginx --image=nginx:alpine
kubectl create deployment nginx --image=nginx:alpine --replicas=3
kubectl rollout status deployment/nginx
kubectl rollout history deployment/nginx
kubectl rollout undo deployment/nginx
kubectl rollout undo deployment/nginx --to-revision=2
kubectl scale deployment nginx --replicas=5
kubectl autoscale deployment nginx --min=3 --max=10 --cpu-percent=80
```

## Service
```bash
kubectl get svc
kubectl describe svc svc_name
kubectl expose deployment nginx --port=80 --type=LoadBalancer
kubectl expose deployment nginx --port=80 --type=NodePort
kubectl expose deployment nginx --port=80 --type=ClusterIP
kubectl port-forward pod_name 8080:80
kubectl port-forward svc/svc_name 8080:80
```

## Namespace
```bash
kubectl get namespaces
kubectl create namespace myns
kubectl delete namespace myns
kubectl config set-context --current --namespace=myns
kubectl get all -n myns
```

## Config & Secrets
```bash
kubectl get configmaps
kubectl get secrets
kubectl create configmap myconfig --from-literal=key=value
kubectl create configmap myconfig --from-file=config.yaml
kubectl create secret generic mysecret --from-literal=password=pass
kubectl create secret tls mysecret --cert=cert.pem --key=key.pem
kubectl describe configmap myconfig
kubectl describe secret mysecret
kubectl get secret mysecret -o jsonpath='{.data.password}' | base64 -d
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Pod Pending | `kubectl describe pod`, cek resources |
| Pod CrashLoop | `kubectl logs --previous` |
| Pod OOMKilled | Naikkan memory limit |
| Service tidak accessible | `kubectl get endpoints`, cek selector |
| Deployment stuck | `kubectl rollout status`, cek events |
