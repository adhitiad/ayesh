# Ayesh-Core Authorization — owner / vip ($13.87) / user

> Versi 2.1 — Breaking (admin → vip). `user manage` = owner-only, `model manage` = self, lainnya vip (owner+vip) untuk global.

## 1. Ringkasan

| Role | Cara dapat | Hak API | Kuota | Model |
|------|------------|---------|-------|-------|
| `owner` | `POST /users` (owner-only) atau `POST /users/bootstrap` (first user) | **Full** — `user manage` (`GET /users`, `POST /users`, `DELETE /users/{id}`, `POST /users/{uid}/rotate`, `POST/DELETE /users/{uid}/vip`) + semua `vip` + semua `self` | `VIP` limits (owner == vip) | semua + premium |
| `vip` | `POST /webhooks/vip-upgrade` HMAC `$13.87`/bulan (1387c, `vip_expires +30d`) atau `POST /users/{uid}/vip` manual owner | **Global vip** — `keywords` (`POST/DELETE /keywords`, `GET /keywords`), `templates` (`POST/DELETE /templates/{name}`, `POST /templates`), `marketplace` (`POST/DELETE /marketplace/*`), `audit` (`GET /audit*`), `analytics` (`GET /analytics`), `usage global` (`GET /usage/summary|/recent`), `metrics` (`GET /metrics|/prometheus`) + **model manage self** + **self resources** + katalog read | `VIP`: chat 20/s, 120/min (default `user*2 burst, *4 sustained`), env `RATE_LIMIT_*_VIP_*` | semua + premium |
| `user` | `POST /users/register` publik (rate-limit 2/s,5/min) → `role=user` | **Self-only** — `chat` + `sessions|plans|tasks|jobs|approvals|memory` milik sendiri + `llm/mcp/skill` milik sendiri (`model manage` self + premium gate) + `usage/me` + katalog read; **tidak** dapat global vip | `user`: chat 10/s,30/min; tasks/jobs/approvals/feedback 5/s,20/min | hanya non-premium bila `VIP_ONLY_MODELS` diisi |

`admin` **deprecated** — DB constraint tetap izinkan `admin` untuk kompatibilitas, tapi `create_user(..., "admin")` otomatis jadi `vip`, dan `UserRequest(role=admin)` di-coerce ke `vip`. Guard `require_admin` kini alias `require_owner_only` (owner saja).

`admin_agent` (nama agen AI di `src/config/rules.py:52`) **tidak** berubah.

## 2. Login — api_key (tanpa password)

```
register → api_key fr_... (tampil SEKALI) → kirim tiap request
```

**Header (2 cara, di-support `src/core/auth/auth_request.py:15-34`):**
```
X-API-Key: fr_abc123...
— atau —
Authorization: Bearer fr_abc123...
```

**Verify (`src/core/auth/auth_keys.py:330-370`):**
- prefix 11 char → `salt$sha256` + legacy `sha256` + grace `old_key_hash` (`old_prefix`, `old_key_expires_at`)
- `verify_key` → `{id, name, role}` → set `ContextVar current_user`, `current_user_role`, `_authenticated`
- **Lazy demote**: role `vip` + `vip_expires_at <= now` → tulis `role='user'` (commit + `invalidate_user_cache`); `vip_since/vip_expires_at/vip_ref` **dipertahankan sebagai riwayat**. Gagal komparasi timestamp (aware/naive) → dianggap expired (fail-closed). Owner tidak kena aturan ini.
- `REQUIRE_API_KEY=1` (default fail-closed) → tanpa key valid → 401. `REQUIRE_API_KEY=0` → chat boleh anonim, tapi **control-plane (`require_authenticated`) tetap 401**.

**Ownership (`src/core/auth/auth_guards.py:12-109`):**
- `require_auth` — tolak anon hanya bila `REQUIRE_API_KEY=1` (kini hanya dipakai internal, semua endpoint publik diganti `require_authenticated`)
- `require_authenticated` — selalu butuh key valid
- `require_owner(request, owner_id)` — self atau owner
- `require_owner_only` — hanya owner
- `require_vip` — vip atau owner (premium gate) + **cek masa aktif**: ContextVar `current_user_vip_expires` di-set dari `verify_key`; `vip_expires_active()` `None`=aktif, expired/gagal komparasi → **403 `Forbidden: masa aktif vip habis`** (defense-in-depth di atas lazy demote)
- `require_self_or_owner(request, uid)` — self atau owner (vip/user tidak bisa lihat orang lain)

## 3. Endpoint matrix (guard baru)

| Kategori | Endpoint | Guard baru | Catatan |
|----------|----------|------------|---------|
| **Publik** | `GET /health` `src/api/routes_system.py:25` | **none** | tetap publik |
|  | `POST /users/register` `src/api/routes_agents.py` | **none** + `register` scope RL | selalu `role=user` |
|  | `POST /webhooks/vip-upgrade` `src/api/routes_webhooks.py:40` | **HMAC** (`VIP_WEBHOOK_SECRET`) | fail-closed 503 bila secret kosong |
| **Publik — akun web** | `POST /auth/register` `src/api/routes_auth.py:108` | **none** + RL scope `register` (2/s, 5/min IP) | selalu `role=user`; 400 bila email terdaftar (W9 → 409 + `hint_provider`) |
|  | `POST /auth/login`, `POST /auth/login/2fa` `routes_auth.py:134,162` | **none** + RL scope `auth` (5/20) | sukses → cookie `ayesh_session` + `ayesh_csrf` |
|  | `POST /auth/logout` `routes_auth.py:184` | cookie opsional | clear cookie (idempoten) |
|  | `POST /auth/email/verify[/request]`, `POST /auth/password/reset[/confirm]` `routes_auth.py:206-237` | token sekali-pakai (hashed) | register gagal kirim email → **503 fail-closed** |
|  | `GET /auth/oauth/{provider}` + `/callback` `routes_auth.py:331,342` | state `auth_oauth_states` TTL 10 mnt | Google/GitHub; error → redirect `/?auth=error` |
| **Authenticated — akun web** | `GET /auth/me`, `POST /auth/password/change` `routes_auth.py:196,251` | `require_authenticated` + CSRF (`X-CSRF-Token`) bila cookie |  |
|  | `GET /auth/2fa/status`, `POST /auth/2fa/{setup,confirm,disable}` `routes_auth.py:268-310` | `require_authenticated` + CSRF | TOTP pyotp + 10 backup code sekali pakai |
| **Authenticated read (user/vip/owner)** | `POST /chat`, `POST /chat/stream*` `routes_chat.py:30-139` | `require_authenticated` | dulunya `require_auth` |
|  | `POST /feedback` `routes_feedback.py:19` | `require_authenticated` |  |
|  | `GET /agents`, `GET /skills`, `GET /skills/{name}` `routes_agents.py:49-82` | `require_authenticated` | katalog, filter `disabled_*` per-user |
|  | `GET /marketplace` `routes_marketplace.py:13` | `require_authenticated` | list saja |
|  | `GET /templates` `routes_system.py:144` | `require_authenticated` | preview 400 char |
|  | `GET /users/me` **baru** `routes_agents.py` | `require_authenticated` | `{id,name,role,vip_*}` |
|  | `GET /usage/me` **baru** `routes_system.py:132` | `require_authenticated` | wrapper `summarize_user_usage(me)` |
| **Self ∨ owner** | `GET /users/{uid}/llm-configs` `routes_agents.py:160` | `require_self_or_owner` | masking `api_key` (`***` bila bukan self) `auth_keys.py:560-620` |
|  | `POST/PUT/DELETE /users/{uid}/llm-configs*` `routes_agents.py:179-240` | `require_self_or_owner` + premium gate | `VIP_ONLY_MODELS` cek → user 403 |
|  | `GET /users/{uid}/skill-overrides`, `/{skill}`, `GET /users/{uid}/mcp-overrides`, `/{mcp}` `routes_agents.py:245-297` | `require_self_or_owner` | **fix** — dulunya hanya `require_auth` |
|  | `PUT/PATCH .../skill|mcp-overrides` | `require_self_or_owner` | tetap |
|  | `GET /usage/user/{uid}` `routes_system.py:122` | `require_self_or_owner` | dulu `require_admin` (owner saja) |
|  | `GET /sessions`, `GET /sessions/{id}`, `PUT /sessions/{id}`, `GET /sessions/{id}/chat`, `GET/DELETE /memory/{id}` `routes_system.py:191-343` | `require_authenticated` + `require_owner(sess.owner)` | owner-scoped |
|  | `GET /plans`, `GET/PATCH /plans/{id}`, `DELETE /sessions/{id}` `routes_control.py:90-198` | `require_authenticated` + `require_owner` |  |
|  | `POST /tasks`, `GET /tasks`, `GET /tasks/{id}` `routes_tasks.py:11-36` `POST/GET/DELETE/PATCH /jobs` `routes_jobs.py:13-92` `GET /approvals/pending`, `POST /approvals/{id}/approve|deny` `routes_approvals.py:12-43` | `require_authenticated` (owner-scoped query) |  |
| **Owner-only (user manage)** | `POST /users` `routes_agents.py:85` | `require_owner_only` | user manage |
|  | `POST /users/bootstrap` `routes_agents.py:96` | **hardened** — tolak bila *user aktif apapun* masih ada |  |
|  | `GET /users` `routes_agents.py:126` | `require_owner_only` |  |
|  | `DELETE /users/{uid}` `routes_agents.py:148` | `require_owner_only` | vip tidak bisa hapus owner |
|  | `POST /users/{uid}/rotate` `routes_agents.py:135` | `require_owner_only` |  |
|  | `POST /users/{uid}/vip`, `DELETE /users/{uid}/vip` **baru** | `require_owner_only` | manual |
| **Vip (owner+vip)** | `POST/DELETE /keywords` `routes_control.py:35-87` | `require_vip` | dulu `require_admin` → kini vip |
|  | `DELETE /templates/{name}` `routes_control.py:201` | `require_vip` |  |
|  | `POST/DELETE /marketplace/{name}/install` `routes_marketplace.py:20-32` | `require_vip` |  |
|  | `POST /templates` `routes_system.py:151` | `require_vip` |  |
|  | `GET /audit`, `GET /audit/verify` `routes_system.py:63-88` | `require_vip` |  |
|  | `GET /analytics` `routes_system.py:57` | `require_vip` |  |
|  | `GET /usage/summary`, `GET /usage/recent` `routes_system.py:91-119` | `require_vip` | usage global |
|  | `GET /keywords` `routes_system.py:377` | `require_vip` |  |
|  | `GET /metrics`, `GET /metrics/prometheus` `routes_system.py:41-54` | `require_vip` | dulu publik |
| **Owner-only (logs/feedback)** | `GET /feedback/stats`, `GET /feedback/recent` `routes_system.py:160-188` | `require_owner_only` | tetap owner |
|  | `GET /logs`, `DELETE /logs` `routes_system.py:346-374` | `require_owner_only` | tetap owner |

## 4. Register publik

**`POST /users/register`**

Request:
```json
{"name": "budi santoso"}
```

Response 200:
```json
{
  "id": "uuid",
  "name": "budi santoso",
  "api_key": "fr_...",
  "prefix": "fr_abc...",
  "role": "user",
  "warning": "Simpan api_key sekarang - tidak ditampilkan lagi. Daftar vip: webhook $13.87.",
  "request_id": "..."
}
```

- Tanpa `X-API-Key` (fail-open hanya endpoint ini)
- Rate-limit scope `register` `src/core/system/rate_limit.py:101` — `2/s burst, 5/min sustained` per-IP (env `RATE_LIMIT_REGISTER_*`)
- Validasi `src/api/models.py:RegisterRequest` — `name 1-100, regex ^[a-zA-Z0-9 _-]+$`, selalu `user`
- `GET /users/me` butuh key, kembalikan `vip_since, vip_ref, vip_expires_at` bila vip.

Curl:
```bash
curl -X POST http://127.0.0.1:8080/users/register -H 'Content-Type: application/json' -d '{"name":"budi"}'
# simpan api_key
curl http://127.0.0.1:8080/users/me -H 'X-API-Key: fr_...'
```

## 5. VIP webhook — $13.87 stub (tanpa gateway)

**Env:**
```
VIP_WEBHOOK_SECRET=random-32chars   # wajib, kosong → 503 fail-closed
VIP_PRICE_CENTS=1387                # 1387 = $13.87
VIP_ONLY_MODELS=gpt-4o,claude-opus  # kosong = semua boleh (backward compat)
```

**`POST /webhooks/vip-upgrade`** `src/api/routes_webhooks.py:40`

Headers:
```
X-Signature: sha256=<hmac hex>
# atau Authorization: Bearer <secret> (fallback manual test)
# atau X-Webhook-Signature
Body adalah raw JSON bytes yang di-HMAC: HMAC-SHA256(secret, body) hex
```

Body:
```json
{
  "uid": "user-uuid",
  "external_ref": "pay_abc123",
  "amount_cents": 1387,
  "currency": "USD"
}
```

Validasi:
- `uid` + `external_ref` wajib, `external_ref` unique (idempoten) `src/core/db/models.py:VipUpgrade`
- `currency==USD`, `amount_cents==VIP_PRICE_CENTS` (1387)
- `uid` harus `user/vip` aktif, `owner` ditolak 404 (owner tidak perlu vip)

Response:
- `200 {id, role:vip, vip_since, vip_ref}` — baru upgrade (`applied_at IS NULL` → apply + tandai `applied_at`)
- `200 {status:already, ...}` — replay `external_ref` **yang sudah pernah di-apply** (`applied_at IS NOT NULL`) → tanpa grant ulang, `paid_at` tidak ditimpa, `vip_expires_at` tidak di-extend
- Ref **baru** saat masih vip → **tetap menambah +30d** (perpanjangan), bukan `already`
- `401` signature invalid, `400` amount/currency salah, `503` secret belum set

Catatan idempotency: aturan lama ("ref sukses + role vip → already") diganti ke tanda `applied_at` — karena itu replay setelah masa aktif habis **tidak** menghidupkan lagi vip lama, dan renewal ber-ref berbeda tidak salah ditolak.

Audit: `append_audit("vip_upgrade", actor=webhook:external_ref)`

Manual (owner):
```bash
curl -X POST http://127.0.0.1:8080/users/<uid>/vip -H 'X-API-Key: <owner>' -H 'Content-Type: application/json' -d '{"external_ref":"manual_1","amount_cents":1387}'
curl -X DELETE http://127.0.0.1:8080/users/<uid>/vip -H 'X-API-Key: <owner>'
```

DB: `users.vip_since, vip_expires_at (+30 days default), vip_ref, vip_amount_cents` `src/core/db/models.py:107-119`, migasi lazy `auth_keys.py:_ensure_vip_columns` + fix constraint `users_role_check` → `owner|vip|user|admin`.

## 6. Kuota & premium models

**Rate limit `src/core/system/rate_limit.py`, `src/api/middleware.py:96-124`:**
- Dual bucket per-request: `ip` selalu + `user` bila key valid.
- `vip`/`owner` dapat `VIP` limits: `burst = USER*2`, `sustained = USER*4` untuk `chat|tasks|jobs|approvals|feedback`, `*2` untuk lainnya, kecuali di-override env:

```
RATE_LIMIT_CHAT_VIP_BURST=20
RATE_LIMIT_CHAT_VIP_SUSTAINED=120
RATE_LIMIT_TASKS_VIP_BURST=10
RATE_LIMIT_REGISTER_BURST=2   # register IP-only
RATE_LIMIT_WEBHOOKS_BURST=5
```

**Premium gate `src/core/llm/premium.py`, `src/api/routes_agents.py:179-214`:**
```python
VIP_ONLY_MODELS = os.getenv("VIP_ONLY_MODELS","")  # comma list, lower-case
is_premium_model(model) -> 400/403 jika user coba set premium
```
- `POST /users/{uid}/llm-configs` dan `PUT .../{id}` cek: bila `is_premium_model(req.model)` dan `role not in (vip, owner)` → `403 Model premium hanya untuk vip. Upgrade $13.87 via webhook.`
- `vip`/`owner` lolos. Kosong env → gate nonaktif (semua boleh).

## 7. Semua orang bisa lihat apa

Sesuai permintaan: user/vip lihat **model, mcp, skill, usage, catalog**.

| Lihat | Endpoint | Guard |
|-------|----------|-------|
| model aktif | `GET /users/me` → `vip_*`, `GET /users/{uid}/llm-configs` (self/owner) + slash `/model` | self |
| mcp | `GET /users/{uid}/mcp-overrides` (self), `GET /users/{uid}/mcp-overrides/{name}` (self) | self_or_owner |
| skill | `GET /skills`, `GET /skills/{name}` | authenticated |
| marketplace katalog | `GET /marketplace` | authenticated |
| agents katalog | `GET /agents` | authenticated |
| templates katalog | `GET /templates` | authenticated (preview) |
| usage milik sendiri | `GET /usage/me`, `GET /usage/user/{uid}` (self) | self_or_owner |
| usage global | `GET /usage/summary|/recent` | owner-only |
| payment status | `GET /users/me` (`vip_*`) + `GET /audit?limit=...` filter `vip_upgrade` | self / owner |

## 8. Perubahan DB & migrasi

- `alembic` tidak kelola `users`; migrasi lazy:
  - `users` kolom baru `vip_since, vip_expires_at, vip_ref, vip_amount_cents` `models.py:117-120`, `_ensure_vip_columns` `auth_keys.py:240`
  - `users_role_check` → `CHECK (role IN ('owner','vip','user','admin'))` (admin dipertahankan untuk kompat)
  - `vip_upgrades` tabel baru `models.py:VipUpgrade` — `_ensure_vip_tables`
- `vip_upgrades.applied_at TIMESTAMP` (nullable) — **penanda idempotency**: hak vip sudah pernah di-apply untuk `external_ref` itu. Backfill `COALESCE(applied_at, paid_at, created_at)` untuk baris `status='success'`.
- Tabel lama `user_llm_configs, user_skill_overrides, user_mcp_overrides` tetap via `_ensure_user_config_tables`.

Manual fix existing DB bila sudah ada constraint lama:
```sql
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role = ANY (ARRAY['owner'::text,'vip'::text,'user'::text,'admin'::text]));
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_since TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expires_at TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_ref VARCHAR(100);
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_amount_cents INTEGER;
CREATE TABLE IF NOT EXISTS vip_upgrades (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, external_ref VARCHAR(100) NOT NULL UNIQUE, amount_cents INTEGER NOT NULL, currency VARCHAR(10) NOT NULL DEFAULT 'USD', created_at TIMESTAMP NOT NULL DEFAULT NOW());
ALTER TABLE vip_upgrades ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP;   -- penanda replay idempoten
```

## 9. Curl ringkas

```bash
# 1. Register
R=$(curl -s -X POST http://127.0.0.1:8080/users/register -H 'Content-Type: application/json' -d '{"name":"andi"}'); echo $R
KEY=$(echo $R | python -c "import sys,json; print(json.load(sys.stdin)['api_key'])")

# 2. Lihat diri
curl -s http://127.0.0.1:8080/users/me -H "X-API-Key: $KEY" | python -m json.tool

# 3. Chat
curl -s -X POST http://127.0.0.1:8080/chat -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{"message":"halo","session_id":"sess1"}' | python -m json.tool

# 4. Lihat katalog (user/vip boleh)
curl -s http://127.0.0.1:8080/agents -H "X-API-Key: $KEY"
curl -s http://127.0.0.1:8080/skills -H "X-API-Key: $KEY"
curl -s http://127.0.0.1:8080/marketplace -H "X-API-Key: $KEY"
curl -s http://127.0.0.1:8080/templates -H "X-API-Key: $KEY"

# 5. Usage milik sendiri
curl -s http://127.0.0.1:8080/usage/me -H "X-API-Key: $KEY"
curl -s http://127.0.0.1:8080/usage/user/<uid> -H "X-API-Key: $KEY"

# 6. Coba set model premium sebagai user → 403
curl -s -X POST http://127.0.0.1:8080/users/<uid>/llm-configs -H "X-API-Key: $KEY" -H 'Content-Type: application/json' -d '{"provider":"openai","model":"gpt-4o"}'

# 7. Webhook VIP (dari server billing) — status pending|success
BODY='{"uid":"<uid>","external_ref":"pay_'.$(date +%s).'","amount_cents":1387,"currency":"USD","status":"pending"}'
SIG=$(python -c "import hmac,hashlib,os; print(hmac.new(os.getenv('VIP_WEBHOOK_SECRET').encode(), b'$BODY', hashlib.sha256).hexdigest())")
curl -s -X POST http://127.0.0.1:8080/webhooks/vip-upgrade -H "Content-Type: application/json" -H "X-Signature: sha256=$SIG" -d "$BODY"

# 8. Billing history (self; owner bisa ?uid=)
curl -s "http://127.0.0.1:8080/billing/history?status=pending" -H "X-API-Key: $KEY"
curl -s "http://127.0.0.1:8080/billing/status/pay_123" -H "X-API-Key: $KEY"
curl -s "http://127.0.0.1:8080/billing/history/pay_123" -H "X-API-Key: $KEY"

# 9. Owner cek metrics (owner-only kini)
curl -s http://127.0.0.1:8080/metrics/prometheus -H "X-API-Key: <owner_key>" | head
```

## 10. File yang diubah

- `src/core/db/models.py` — `User.vip_*` + `VipUpgrade`
- `src/core/auth/auth_keys.py` — `_ensure_vip_*`, `create_user` vip, `set_user_vip/demote/get_user_by_id`, migrasi constraint, `list_user_llm_configs` privileged owner saja
- `src/core/auth/auth_guards.py` — `require_vip`, `require_self_or_owner`, `require_admin` → alias owner-only
- `src/core/auth/auth.py` — re-export, docstring
- `src/api/models.py` — `RegisterRequest`, `VipUpgradeRequest`, `UserRequest` coerce admin→vip
- `src/api/routes_agents.py` — `POST /users/register`, `GET /users/me`, `POST/DELETE /users/{uid}/vip`, semua guard jadi `require_self_or_owner`/`require_owner_only`, premium gate, bootstrap harden
- `src/api/routes_system.py` — `require_owner_only` untuk `metrics|prometheus|audit|analytics|usage/summary|recent|logs|keywords`, `GET /templates` → authenticated, `GET /usage/user/{uid}` → self_or_owner, baru `GET /usage/me`
- `src/api/routes_control.py` — `POST/DELETE /keywords`, `DELETE /templates/{name}` → owner-only
- `src/api/routes_marketplace.py` — install/uninstall → owner-only
- `src/api/routes_chat.py`, `routes_feedback.py` — `require_auth` → `require_authenticated`
- `src/api/routes_webhooks.py` **baru** — HMAC webhook + `status pending|success|failed|expired` (history UPSERT `vip_upgrades`, `pending` tanpa `set_user_vip`)
- `src/api/routes_billing.py` **baru** — `GET /billing/history|history/{ref}|status/{ref}` self/owner, `raw_payload` owner saja
- `src/api/middleware.py` — `_authed_user_info`, role-aware `check_rate_limit`
- `src/core/system/rate_limit.py` — scope `register|webhooks`, `_vip_limits`, `get_limits_for_role`
- `src/core/llm/premium.py` **baru** — `VIP_ONLY_MODELS`, `vip_price_cents`
- `api_server.py` — docs role, `webhooks_router`, `billing_router`, metrics tag
- `.env.example` — `VIP_*`, `RATE_LIMIT_*_VIP_*`
- `tests/test_api_control_endpoints.py`, `tests/test_prompt_structure.py`, `tests/test_prometheus_metrics.py` — update ke owner-only & vip
- `tests/test_billing_history.py` **baru** — 23 test HMAC + flow + IDOR
- `ayesh-payment/` **baru** (Go, port 8090) — mock gateway, `X-API-Key` + HMAC ke ayesh-core (lihat `docs/PAYMENT.md`)

## 11. Verifikasi

```bash
# dari ayesh-core/
E:/code/fr/venv/Scripts/ruff.exe check .
# all checks passed

python -m unittest discover -s tests
# Ran 617 tests in ... OK   (608 + 9 expiry di tests/test_vip_expiry.py)

# ayesh-payment (Go)
cd ../ayesh-payment && go vet ./... && go test ./... -count=1
# 5 PASS
```

## 12. Diagram

Lihat `AUTHORIZATION_DIAGRAM.md` (Mermaid) — auth flow, state vip, endpoint matrix.

## 13. Enforcement masa aktif vip (expiry)

Sebelum fase ini vip abadi: `require_vip` tidak pernah membaca `vip_expires_at`, jadi akun yang sudah lewat 30 hari tetap dapat hak global. Tiga lapis sekarang:

1. **Lazy demote** `src/core/auth/auth_keys.py:verify_key` — satu titik normalisasi untuk semua request (dipanggil `auth_request.py:bind_request_user` dan `middleware.py:84`): `role=vip` + `vip_expires_at <= now` → tulis `role='user'`, `invalidate_user_cache()`. Riwayat `vip_*` tidak dihapus. Fail-closed bila komparasi timestamp error.
2. **Guard runtime** `src/core/auth/auth_guards.py:require_vip` — `vip_expires_active()` dari ContextVar `current_user_vip_expires` (di-set di `bind_request_user`, dibersihkan `finally`) → `403 Forbidden: masa aktif vip habis`. `vip_expires_at is None` = legacy aktif.
3. **Premium gate** `src/api/routes_agents.py` (`POST/PUT /users/{uid}/llm-configs`) pakai `get_current_user_role()` → otomatis ikut turun peran setelah demote.

Efek samping yang diperbaiki bersamaan: `_require_ownership` (semua mutasi `llm-config`/`skill`/`mcp` override) **tidak pernah memanggil `require_authenticated`**, sehingga ContextVar masih `default` dan **semua caller — termasuk owner — selalu kena 403**. Kini wajib bind dulu.

Test regresi: `tests/test_vip_expiry.py` (9) — vip aktif lolos, expired → demote + endpoint vip 403 + premium gate 403, legacy tanpa expiry tetap aktif, owner bebas, replay `applied_at` tidak grant ulang, ref baru menambah +30d.

---
*Owner = satu-satunya yang kelola global. user/vip = sama API, beda kuota + premium. Login = api_key header tiap request.*

