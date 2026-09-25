# Ayesh Payment — Go mock (port 8090, X-API-Key)

> `ayesh-payment` (Go `go.dev/doc/install`) mock gateway → `POST /payments/create` (`X-API-Key: fr_…`) → `pending` → `POST /mock/callback` → `success` → HMAC `POST /webhooks/vip-upgrade` ayesh-core `$13.87`.

## Kontrak

### POST /payments/create — 8090, X-API-Key wajib
```
X-API-Key: fr_...  (verify via ayesh-core GET /users/me → 401 bila invalid, 403 bila uid != me.id kecuali owner)
Body: {"uid":"<uuid>","external_ref":"pay_123 (opsional auto pay_<nanohex>)","amount_cents":1387 (opsional)}
Resp 201: {"external_ref":"pay_123","pay_url":"http://127.0.0.1:8090/mock/pay/pay_123","status":"pending","amount_cents":1387,"currency":"USD"}
Effect: Go → POST http://127.0.0.1:8080/webhooks/vip-upgrade {uid, external_ref, 1387, USD, status:pending, provider:mock} HMAC sha256
```

### POST /mock/callback — mock provider
```
X-API-Key: fr_... (verify + uid/ref harus milik key kecuali owner → 403)
Body: {"external_ref":"pay_123","status":"success|failed|expired"}
Resp: {"external_ref":"pay_123","status":"success","vip_active":true}
Effect: Go → POST ayesh-core/webhooks {same external_ref, status:success|failed} HMAC → ayesh-core UPSERT status=success + paid_at → set_user_vip +30d
```

### GET /health, GET /mock/pay/{ref} dummy (halaman mock checkout)

## Env shared

Dibaca `main.go` (`getenv`, default dalam kurung):

```
PAYMENT_PORT=8090                       # (8090) port service payment
AYESH_CORE_URL=http://127.0.0.1:8080    # (http://127.0.0.1:8080) verify X-API-Key + kirim webhook
VIP_WEBHOOK_SECRET=change_me_same_as_ayesh-core   # wajib, sama dengan ayesh-core; kosong = fail-closed
```

`amount_cents` dikunci 1387 di kode (`vipPriceCents`), sinkron `VIP_PRICE_CENTS=1387` ayesh-core. Template: `ayesh-payment/.env.example`.

## Struktur

```
ayesh-payment/
  go.mod (stdlib-only, tanpa dep)
  main.go       : config, HMAC sign, meInfo verify, handlers create|callback|mockPay|list
  main_test.go  : 5 test (vet + go test PASS)
  README.md
  .env.example  : template env service
```

## Keamanan

- `POST /payments/create` tanpa `X-API-Key` → `401`, `uid` mismatch → `403`, HMAC Go→core `X-Signature: sha256=<hmac hex(body, secret)>` (`routes_webhooks.py:33`), rate-limit `5/s 20/min`.
- History `pending|sukses` tetap `GET /billing/history` di ayesh-core (self/owner), Go tidak simpan DB.

## Verifikasi

```
go vet ./...; go test ./... -count=1     → 5 PASS
ruff check . + unittest discover         → ayesh-core 608 OK
E2E smoke (live, 25 Sep 2026):
  POST :8090/payments/create -H X-API-Key:fr_… -d '{"uid":"…"}' → 201 pending 1387
  GET  :8080/billing/status/{ref} → status=pending, vip_active=false
  POST :8090/mock/callback {success} → vip_active=true
  GET  :8080/billing/status/{ref} → success + vip_expires_at +30d
  GET  :8080/users/me → role=vip
  GET  :8080/billing/history?status=success → 1 row (provider=mock, paid_at)
  IDOR: user lain GET /billing/history/{ref} → 403
  Replay: callback success kedua → role tetap vip, expires tidak extend, count=1
```

---
*Mock dulu, Xendit/Midtrans/Stripe nanti ganti `provider/*.go` tanpa ubah ayesh-core webhook HMAC.*
