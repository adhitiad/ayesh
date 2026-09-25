# Authorization Diagram — ayesh-core 2.1 (owner / vip / user)

## 1. Request → Auth → Guard → Handler

```mermaid
flowchart TD
    A[Client: X-API-Key / Bearer] --> B{bind_request_user<br/>auth_request.py}
    B -->|key valid| C[_authenticated=True<br/>current_user=id<br/>current_user_role=role]
    B -->|key invalid & REQUIRE_API_KEY=1| D[401]
    B -->|key missing & REQUIRE_API_KEY=0| E[_authenticated=False<br/>user=default<br/>role=user]
    C --> F[Route guard]
    E --> F
    F -->|require_authenticated| G{is_authenticated?}
    F -->|require_owner_only| H{role==owner?}
    F -->|require_vip| I{role in vip,owner?}
    F -->|require_self_or_owner| J{uid==me or role==owner?}
    F -->|require_owner| K{owner_id==me or role==owner?}
    F -->|public| L[handler]
    G -->|no| D
    G -->|yes| L
    H -->|no| M[403]
    H -->|yes| L
    I -->|no| M
    I -->|yes| L
    J -->|no| M
    J -->|yes| L
    K -->|no| M
    K -->|yes| L
    L --> N[RateLimitMiddleware<br/>ip bucket + user bucket role-aware]
    N --> O[Handler → audit hash-chain → response]
```

## 2. Role & Upgrade Flow

```mermaid
stateDiagram-v2
    [*] --> user: POST /users/register<br/>or POST /users (owner)
    user --> vip: POST /webhooks/vip-upgrade<br/>HMAC + $13.87 (1387c)<br/>external_ref unique
    vip --> user: DELETE /users/{uid}/vip<br/>owner demote
    vip --> user: vip_expires_at lewat → lazy demote<br/>(verify_key tulis role=user)<br/>403 "masa aktif vip habis" (require_vip)
    user --> user: chat / own data / katalog read
    vip --> vip: chat (higher quota) / premium models
    vip --> vip: ref baru (renewal) → +30d<br/>ref lama replay → already (applied_at)
    vip --> owner: tidak otomatis (owner via POST /users role=owner)
    owner --> owner: full
    note right of vip: vip_since, vip_expires_at +30d,<br/>vip_ref, vip_amount_cents<br/>VipUpgrade.applied_at idempoten<br/>riwayat vip_* tetap ada saat expired
```

## 3. Register → Chat → Usage → VIP

```mermaid
sequenceDiagram
    participant U as User (anon)
    participant API as API
    participant DB as PG
    participant WH as Webhook (billing)
    participant O as Owner

    U->>API: POST /users/register {name}
    API->>DB: create_user(name, role=user) → fr_... (salt$hash)
    API-->>U: {id, api_key (sekali), role=user}

    U->>API: GET /users/me (X-API-Key)
    API-->>U: {id, role:user, vip:null}

    U->>API: POST /chat {message} (X-API-Key)
    API->>API: require_authenticated → is_authenticated?
    API->>DB: rate-limit ip + user (10/s user, 20/s vip)
    API-->>U: {agent_type, response, request_id}

    U->>API: GET /usage/me (X-API-Key)
    API-->>U: summarize_user_usage(me)

    U->>WH: bayar $13.87
    WH->>API: POST /webhooks/vip-upgrade {uid, external_ref, 1387, USD} + X-Signature
    API->>API: _verify_hmac (hmac sha256, secret compare_digest)
    API->>DB: set_user_vip(uid) → role=vip, vip_since, VipUpgrade external_ref unique
    API-->>WH: {role:vip}
    WH-->>U: vip aktif

    U->>API: POST /users/{uid}/llm-configs {model:gpt-4o} (X-API-Key vip)
    API->>API: is_premium_model? role vip? → allow
    API-->>U: {id, model}

    O->>API: GET /metrics/prometheus (X-API-Key owner/vip)
    API->>API: require_vip (owner+vip)
    API-->>O: text/plain version=0.0.4

    O->>API: GET /usage/summary (owner/vip)
    API->>API: require_vip
    API-->>O: {requests, tokens, cost_usd, by_agent}
```

## 4. Guard Matrix (warna) — final: user manage=owner, global=vip, model=self

```mermaid
flowchart LR
    subgraph Public [Publik tanpa key]
        P1[GET /health]
        P2[POST /users/register]
        P3[POST /webhooks/vip-upgrade<br/>HMAC]
    end
    subgraph AuthRead [Authenticated read<br/>user/vip/owner]
        A1[GET /agents /skills /marketplace<br/>GET /templates preview]
        A2[POST /chat /feedback]
    end
    subgraph SelfOwner [Model manage: Self ∨ owner<br/>+ premium gate]
        S1[GET /users/{uid}/llm-*, skill, mcp<br/>GET /usage/user/{uid} self<br/>GET /usage/me]
        S2[GET /sessions /plans /memory<br/>POST /tasks /jobs<br/>GET /approvals]
    end
    subgraph OwnerOnly [Owner-only: user manage]
        O1[GET /users<br/>DELETE /users/{uid}<br/>POST /users<br/>POST /users/{uid}/rotate]
        O2[POST /users/{uid}/vip<br/>DELETE /users/{uid}/vip]
        O3[GET /logs<br/>GET /feedback/stats|recent]
    end
    subgraph Vip [Vip = owner+vip]
        V1[POST DELETE /keywords<br/>GET /keywords]
        V2[POST /templates<br/>DELETE /templates/{name}]
        V3[POST DELETE /marketplace/*]
        V4[GET /audit /audit/verify<br/>GET /analytics<br/>GET /usage/summary /recent<br/>GET /metrics /metrics/prometheus]
    end
    Public --- AuthRead --- SelfOwner --- OwnerOnly --- Vip
```

## 5. Rate Limit — role-aware

```mermaid
flowchart TD
    R[Request path → scope<br/>_scope_for_path] --> IP[IP bucket<br/>RATE_LIMIT_{SCOPE}_BURST/SUSTAINED]
    R --> U{Authenticated?}
    U -->|no| IP
    U -->|yes + role=user| UB[user limits<br/>_user_limits<br/>USER_BURST/SUSTAINED]
    U -->|yes + role=vip/owner| VB[vip limits<br/>_vip_limits<br/>VIP_BURST = USER*2<br/>SUSTAINED = USER*4]
    IP --> C1{burst/sustained > limit? 429}
    UB --> C2{burst/sustained > limit? 429}
    VB --> C3{burst/sustained > limit? 429}
    C1 -->|no| OK[handler]
    C2 -->|no| OK
    C3 -->|no| OK
```

- Scope: `chat 10/30`, `tasks|jobs|approvals|feedback 5/20`, `users 2/5`, `register 2/5`, `webhooks 5/20`, `health 10/30` — override via `RATE_LIMIT_{SCOPE}_{USER|VIP}_*`.

## 6. DB Schema delta

```mermaid
erDiagram
    users {
        varchar id PK
        varchar name
        varchar key_hash
        varchar prefix
        varchar role  """owner|vip|user|admin(legacy)"""
        boolean active
        timestamp created_at
        varchar old_key_hash
        varchar old_prefix
        timestamp old_key_expires_at
        timestamp vip_since
        timestamp vip_expires_at
        varchar vip_ref
        int vip_amount_cents
    }
    vip_upgrades {
        varchar id PK
        varchar user_id FK
        varchar external_ref UK
        int amount_cents
        varchar currency
        timestamp created_at
    }
    users ||--o{ vip_upgrades : "user_id"
    users ||--o{ user_llm_configs : "user_id"
    users ||--o{ user_skill_overrides : "user_id"
    users ||--o{ user_mcp_overrides : "user_id"
```

---
*Diagram Mermaid — render di GitHub / Mermaid Live Editor. Semua panah 401/403 fail-closed.*

