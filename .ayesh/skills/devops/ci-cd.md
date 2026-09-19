---
name: ci-cd
description: "CI/CD pipeline configuration. Trigger: /cicd"
---

# CI/CD Pipeline Configuration

## GitHub Actions

### Basic Workflow
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
      
      - name: Install dependencies
        run: npm ci
      
      - name: Run tests
        run: npm test
      
      - name: Build
        run: npm run build
```

### Matrix Build
```yaml
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        node-version: [16, 18, 20]
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
      - run: npm ci
      - run: npm test
```

### Docker Build & Push
```yaml
jobs:
  docker:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: user/app:${{ github.sha }}
```

### Deploy to Kubernetes
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: build
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.KUBE_CONFIG }}
      
      - name: Deploy
        run: |
          kubectl set image deployment/app app=user/app:${{ github.sha }}
          kubectl rollout status deployment/app
```

## GitLab CI

### Basic Config
```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - deploy

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

build:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    - docker build -t $DOCKER_IMAGE .
    - docker push $DOCKER_IMAGE

test:
  stage: test
  image: node:18
  script:
    - npm ci
    - npm test
  coverage: '/Coverage: \d+\.\d+%/'

deploy:
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - kubectl set image deployment/app app=$DOCKER_IMAGE
  only:
    - main
  environment:
    name: production
    url: https://app.example.com
```

### Multi-Environment
```yaml
.deploy_template: &deploy_template
  stage: deploy
  image: bitnami/kubectl:latest
  script:
    - kubectl config use-context $KUBE_CONTEXT
    - kubectl set image deployment/app app=$DOCKER_IMAGE

deploy_staging:
  <<: *deploy_template
  variables:
    KUBE_CONTEXT: staging
  environment:
    name: staging
  only:
    - develop

deploy_production:
  <<: *deploy_template
  variables:
    KUBE_CONTEXT: production
  environment:
    name: production
  only:
    - main
  when: manual
```

## Jenkins

### Jenkinsfile (Declarative)
```groovy
pipeline {
    agent any
    
    environment {
        DOCKER_IMAGE = "user/app:${BUILD_NUMBER}"
        DOCKER_CREDENTIALS = credentials('docker-hub')
    }
    
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        
        stage('Build') {
            steps {
                sh 'npm ci'
                sh 'npm run build'
            }
        }
        
        stage('Test') {
            steps { sh 'npm test' }
            post {
                always { junit 'test-results/*.xml' }
            }
        }
        
        stage('Deploy') {
            when { branch 'main' }
            steps {
                sh "kubectl set image deployment/app app=${DOCKER_IMAGE}"
            }
        }
    }
    
    post {
        success { slackSend channel: '#deployments', message: "Build ${BUILD_NUMBER} succeeded" }
        failure { slackSend channel: '#deployments', message: "Build ${BUILD_NUMBER} failed" }
    }
}
```

## Common Patterns

### Semantic Versioning
```yaml
name: Release
on:
  push:
    tags: ['v*']
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
```

### Caching
```yaml
- name: Cache node modules
  uses: actions/cache@v3
  with:
    path: ~/.npm
    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-node-
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Build failed | Cek logs, reproduce locally |
| Permission error | Cek secrets, token |
| Cache miss | Cek cache key |
| Deploy timeout | Increase timeout |
| Secret leak | Cek masking, rotate |
