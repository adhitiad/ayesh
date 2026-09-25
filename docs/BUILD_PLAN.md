# Build Plan — ayesh-core dari awal hingga saat ini

> Versi 2.1 — `owner / vip ($13.87/bulan) / user` — fail-closed. Semua `user manage` owner-only, `model manage` self, global `vip (owner+vip)`.

## Timeline build

### 0. Baseline
- `users.role` = `owner|admin|user` + `CHECK users_role_check`, `require_admin` (`admin|owner`), `require_auth` lolos anon bila `REQUIRE_API_KEY=0`. Bug `except A, B:` 3 file break `compileall`.

### 1. DB & Model — fondasi
- Fix `except (A,B):` `src/core/llm/factory.py:288` `src/memory/summarizer.py:58,86` `src/plugins/input_guard.py:105`.
- `src/core/db/models.py:107` — `User.vip_since, vip_expires_at, vip_ref, vip_amount_cents` + `VipUpgrade(id, user_id, external_ref UNIQUE, amount_cents, currency, created_at)` (+ nanti `status|provider|raw_payload|paid_at|updated_at` pending|sukses).
- `src/core/auth/auth_keys.py:14-240` — `_VIP_COLUMNS`, `_VALID_ROLES`, `_ensure_vip_columns` (ALTER ADD + fix `users_role_check` → `owner|vip|user|admin` + `UPDATE admin→vip`), `_ensure_vip_tables`, `create_user` coerce `admin→vip`, `list_users` + `get_user_by_id` + `set_user_vip/demote_user_vip` (idempoten `external_ref`, `+30d`).
- Manual `ALTER TABLE users DROP/ADD CONSTRAINT` + `vip_upgrades` (seed `fix_role2.py`).
- Gate: `compileall -q src api_server.py` ok.

### 2. Guard tunggal
- `src/core/auth/auth_guards.py:1-109` — `require_vip` (`vip|owner`), `require_self_or_owner`, `require_admin` alias `require_owner_only`, `require_owner_or_admin` → owner saja.
- `src/core/auth/auth.py:1-119` — re-export `require_vip, require_self_or_owner, _ensure_vip_*`, docstring `REQUIRE_API_KEY=1` + `vip` + `fail-closed`.

### 3. Register publik + me + bootstrap harden
- `src/api/models.py:62` — `RegisterRequest` + `UserRequest` coerce `admin→vip`.
- `src/api/routes_agents.py:49-148` — `POST /users/register` publik `register 2/s 5/min`, `GET /users/me`, `POST /users/bootstrap` tolak bila `COUNT(active)>0`, `_require_ownership` `role != owner`, `list_agents|skills` `require_auth→require_authenticated`, `GET /users` + `DELETE /users/{uid}` → `require_owner_only`, `POST /users/{uid}/vip` + `DELETE …/vip` owner manual.
- `src/core/auth/auth_keys.py:560` — `list_user_llm_configs` privileged `owner` saja.

### 4. Webhook VIP stub `$13.87` + premium
- Baru `src/api/routes_webhooks.py:40` — `POST /webhooks/vip-upgrade` HMAC `VIP_WEBHOOK_SECRET` (`503` bila kosong, `401` salah), `amount_cents==1387` `USD`, `external_ref` unique, `success` → `set_user_vip(+30d)`.
- Baru `src/core/llm/premium.py:1` — `VIP_ONLY_MODELS` csv, `is_premium_model` + `vip_price_cents`.
- `src/api/routes_agents.py:179` — `POST/PUT llm-configs` premium gate `user→403`.

### 5. Kuota role-aware
- `src/core/system/rate_limit.py:101` — scope `register(2,5)`, `webhooks(5,20)`, `_vip_limits` (`USER*2 burst, *4 sustained`), `get_limits_for_role`, `check_rate_limit(..., role)`.
- `src/api/middleware.py:96` — `_authed_user_info → (id,role)`, `RateLimitMiddleware` ip + user vip.

### 6. Guard matrix final
- Publik: `GET /health`, `POST /users/register`, `POST /webhooks/vip-upgrade` (HMAC).
- Auth read: `POST /chat|/feedback`, `GET /agents|/skills|/marketplace`, `GET /templates` preview `require_authenticated`.
- Model manage self: `GET/POST/PUT/DELETE /users/{uid}/llm-configs*`, `skill|mcp`, `GET /usage/user/{uid}` self `require_self_or_owner` + premium.
- User manage owner-only: `POST /users`, `GET /users`, `DELETE /users/{uid}`, `POST …/rotate`, `POST/DELETE …/vip`.
- Vip (owner+vip): `POST/DELETE /keywords` `routes_control.py:35`, `GET /keywords` `routes_system.py:377`, `POST/DELETE /templates/{name}` `routes_control.py:201` + `POST /templates` `routes_system.py:151`, `POST/DELETE /marketplace/*` `routes_marketplace.py:20`, `GET /audit*` `63`, `GET /analytics` `57`, `GET /usage/summary|/recent` `91`, `GET /metrics|/prometheus` `41` → `require_vip`.
- Logs/feedback `require_owner_only` tetap.

### 7. API Server & Env
- `api_server.py:40` `v2.1`, deskripsi `owner/vip/user`, `webhooks_router` (+ nanti `billing`), `.env.example` `VIP_WEBHOOK_SECRET`, `VIP_PRICE_CENTS=1387`, `VIP_ONLY_MODELS`, `RATE_LIMIT_*_VIP_*`.

### 8. Tests
- `tests/test_api_control_endpoints.py:47` `admin→owner` header, `tests/test_prompt_structure.py:1069` `owner|vip|user`, `tests/test_prometheus_metrics.py:76` `X-API-Key owner` (vip lolos) — `ruff` ok, `585 OK`.

### 9. Docs & Diagram
- `ayesh-core/docs/AUTHORIZATION_VIP.md` matrix, `AUTHORIZATION_DIAGRAM.md` Mermaid (auth flow, `pending→success→active→expired`, matrix), root `AUTHORIZATION_VIP.md` ringkas, copy `docs/AUTHORIZATION_VIP.md` `docs/AUTHORIZATION_DIAGRAM.md`.

### 10. History pending|sukses + billing ✔
- DB `vip_upgrades` + `status|provider|raw_payload|paid_at|updated_at` (`_ensure_vip_tables` lazy ALTER + backfill pending→success utk user vip) — `src/core/db/models.py:127`.
- `routes_webhooks.py` `status` (`success` default; `pending|failed|expired` → history saja, tanpa `set_user_vip`), UPSERT per `external_ref` (ref success → upgrade; replay → `already`).
- `set_user_vip` (`auth_keys.py:509`): idempotency berbasis kolom baru **`applied_at`** — `applied_at IS NOT NULL` → `already` (replay tak grant ulang); `applied_at IS NULL` (pending→success / sukses dari crash) → apply + set `applied_at`. (Aturan lama "status success + role vip → already" dihapus; lihat fase 12.)
- Baru `src/api/routes_billing.py` — `GET /billing/history` (`?uid=&status=&limit=&offset=`, self/owner), `GET /billing/history/{ref}` (raw_payload owner saja), `GET /billing/status/{ref}` (`vip_active`, `vip_expires_at`).
- `api_server.py` `billing_router` registered.
- `tests/test_billing_history.py` 23 test (HMAC 503/401/400, pending→success flow, IDOR 403, filter, clamp) → 608 OK.

### 11. ayesh-payment Go mock `8090` (`X-API-Key`) ✔
- `ayesh-payment/` stdlib-only (`go.mod`, `main.go`, `main_test.go`, `README.md`) — Go 1.27, `go vet` + 5 test PASS.
- `POST /payments/create` `X-API-Key` verify `GET /users/me` (401 invalid, 403 uid≠me kecuali owner) → invoice `pending` + HMAC webhook → 201 `{external_ref, pay_url, amount_cents:1387}`.
- `POST /mock/callback` `{external_ref, status:success|failed|expired}` → HMAC webhook → `success` → vip aktif; `GET /mock/pay/{ref}` dummy; `GET /payments` daftar lokal.
- Fail-closed: secret kosong 503, amount ≠1387 → 400, webhook gagal → 502.
- `.env.example` (`VIP_WEBHOOK_SECRET`, `AYESH_CORE_URL`, `PAYMENT_PORT`) untuk menjalankan dua service.

### 12. Enforcement masa aktif vip (expiry) ✔
- Masalah: `require_vip` tidak pernah baca `vip_expires_at` → vip abadi setelah 30 hari.
- **Lazy demote** di `verify_key` (`auth_keys.py`): `role=vip` + `vip_expires_at <= now` → `role='user'` (commit + `invalidate_user_cache`), riwayat `vip_*` dipertahankan; gagal komparasi timestamp → dianggap expired (fail-closed).
- **Guard runtime** `require_vip`: ContextVar baru `current_user_vip_expires` (`auth_context.py`) di-set di `bind_request_user` (`auth_request.py`), dibaca via `vip_expires_active()` → `403 Forbidden: masa aktif vip habis`.
- Premium gate `POST /users/{uid}/llm-configs` ikut tertutup otomatis (pakai `get_current_user_role()`).
- **Bug laten diperbaiki**: `_require_ownership` (`routes_agents.py`) tidak pernah memanggil `require_authenticated` → ContextVar `default` → semua mutasi `llm-config`/`skill`/`mcp` selalu 403 (termasuk owner). Kini bind dulu.
- `vip_upgrades.applied_at` + backfill `COALESCE(applied_at, paid_at, created_at)`; webhook short-circuit `already` hanya bila `applied_at IS NOT NULL`; `paid_at` tidak ditimpa saat replay; **ref baru saat masih vip = perpanjangan +30d**.
- `tests/test_vip_expiry.py` 9 test → **617 OK**.

## Verifikasi tiap fase
- `compileall -q src api_server.py`, `ruff check .` **All checks passed**, `unittest discover -s tests` **617 OK**, `go vet ./...` + `go test ./...` 5 PASS.
- E2E smoke live: register `role=user` → create `pending` → `vip_active=false` → callback `success` → `role=vip` +30d → `billing/history` 1 row, IDOR 403, replay idempoten (expires tidak extend).

## File diubah
- `src/core/db/models.py`, `src/core/auth/*`, `src/api/*`, `src/core/system/rate_limit.py`, `src/core/llm/premium.py`, `api_server.py`, `.env.example`, `tests/*`, `docs/*`.

---
*Plan-mode → build-mode — eksekusi 1→12 berurutan, fail-closed, tidak breaking selain `admin→vip` & `metrics` owner→vip (disetujui).*
