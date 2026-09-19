---
name: configmap-secret
description: "ConfigMap & Secret management Kubernetes. Trigger: /k8ssecret"
---

# ConfigMap & Secret Management

## ConfigMap

### Create
```bash
kubectl create configmap myconfig --from-literal=key1=value1 --from-literal=key2=value2
kubectl create configmap myconfig --from-file=config.yaml
kubectl create configmap myconfig --from-file=./config/
kubectl create configmap myconfig --from-env-file=.env
```

### YAML
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: myconfig
  namespace: default
data:
  key1: value1
  key2: value2
  config.yaml: |
    server:
      port: 8080
    database:
      host: localhost
```

### Use in Pod
```yaml
spec:
  containers:
    - name: app
      envFrom:
        - configMapRef:
            name: myconfig
      env:
        - name: SPECIFIC_KEY
          valueFrom:
            configMapKeyRef:
              name: myconfig
              key: key1
      volumeMounts:
        - name: config-volume
          mountPath: /etc/config
  volumes:
    - name: config-volume
      configMap:
        name: myconfig
```

## Secret

### Create
```bash
kubectl create secret generic mysecret --from-literal=password=mysecret
kubectl create secret generic mysecret --from-file=ssh-key=$HOME/.ssh/id_rsa
kubectl create secret generic mysecret --from-env-file=.env
kubectl create secret tls mysecret --cert=cert.pem --key=key.pem
kubectl create secret docker-registry mysecret --docker-server=registry.example.com --docker-username=user --docker-password=pass
```

### YAML
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mysecret
  namespace: default
type: Opaque
data:
  username: YWRtaW4=      # base64 encoded
  password: cGFzc3dvcmQ=  # base64 encoded
```

```bash
echo -n "admin" | base64
echo -n "password" | base64
```

### Use in Pod
```yaml
spec:
  containers:
    - name: app
      envFrom:
        - secretRef:
            name: mysecret
      env:
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mysecret
              key: password
      volumeMounts:
        - name: secret-volume
          mountPath: /etc/secrets
          readOnly: true
  volumes:
    - name: secret-volume
      secret:
        secretName: mysecret
```

## TLS Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: tls-secret
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-cert>
  tls.key: <base64-encoded-key>
```

## Docker Registry Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: regcred
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-json>
```

## Management
```bash
kubectl get configmap
kubectl get secret
kubectl describe configmap myconfig
kubectl describe secret mysecret
kubectl get secret mysecret -o jsonpath='{.data.password}' | base64 -d
kubectl delete configmap myconfig
kubectl delete secret mysecret
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Pod restart | Cek secret/configmap exist |
| Mount gagal | Cek path, permissions |
| Secret tidak ada | `kubectl get secret`, create ulang |
| Base64 error | `echo -n "value" | base64` |
| Config change | Delete & recreate (immutable) |
