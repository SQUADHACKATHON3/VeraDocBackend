# VeraDoc Backend — Frontend API Guide

Base URL: use your deployed API origin (e.g. `https://api.example.com`). Local dev is often `http://127.0.0.1:8000`.

- **OpenAPI / Swagger UI:** `GET {BASE_URL}/docs` (interactive try-out).
- **JSON:** Request and response bodies use **`application/json`** unless noted.
- **Auth:** Send **`Authorization: Bearer <access_token>`** on every protected route.
- **IDs:** UUIDs are strings in JSON (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`).
- **Dates:** ISO 8601 strings with timezone (e.g. `"2026-05-13T10:15:00+00:00"`).
- **CORS:** The backend does **not** ship CORS middleware by default. If the web app is on another origin, add CORS on the API or proxy through the same host.

---

## 1. Authentication

### 1.1 Register

`POST /api/auth/register`  
**Auth:** none  

**Body (JSON):**

| Field | Type | Rules |
|--------|------|--------|
| `name` | string | 1–200 chars |
| `organisation` | string | 1–200 chars |
| `email` | string | Valid email |
| `password` | string | 8–200 chars |

**201 response:**

```json
{
  "message": "Account created successfully",
  "credits": 1
}
```

New users start with **1 credit**.

**Errors:** `409` — `{"detail": "Email already registered"}`

---

### 1.2 Login

`POST /api/auth/login`  
**Auth:** none  

**Body:**

```json
{
  "email": "user@example.com",
  "password": "secret"
}
```

**200 response (`TokenOut`):**

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer"
}
```

Store both tokens securely (memory + refresh in httpOnly cookie is a common pattern).

**Errors:** `401` — `{"detail": "Invalid credentials"}`

---

### 1.3 Refresh access token

`POST /api/auth/refresh?refresh_token=<refresh_token>`  
**Auth:** none  

`refresh_token` is a **query parameter** (full JWT string). URL-encode it if you build the URL manually.

**200 response:** same shape as login (`access_token`, `refresh_token`, `token_type`).

**Errors:** `401` — `{"detail": "Unauthorized"}`

---

### 1.4 Current user (profile + credits)

`GET /api/auth/me`  
**Auth:** Bearer  

**200 response (`MeOut`):**

```json
{
  "id": "uuid",
  "name": "Jane Doe",
  "organisation": "Acme Ltd",
  "email": "user@example.com",
  "credits": 5
}
```

Use this after login and after **credit purchase** webhooks to refresh the balance.

---

## 2. Credits (Squad checkout)

Pricing is driven by the server (`CREDIT_PRICE_KOBO`, default **70000** = **₦700** per credit). Packs: **1, 5, 10, 20** credits.

### 2.1 List packs (prices)

`GET /api/credits/packs`  
**Auth:** none (public catalogue)

**200 response (`CreditPacksOut`):**

```json
{
  "packs": [
    { "credits": 1, "amountKobo": 70000 },
    { "credits": 5, "amountKobo": 350000 },
    { "credits": 10, "amountKobo": 700000 },
    { "credits": 20, "amountKobo": 1400000 }
  ],
  "pricePerCreditKobo": 70000,
  "currency": "NGN"
}
```

Display amounts to users as **₦ (amountKobo / 100)**.

---

### 2.2 Start credit purchase (Squad)

`POST /api/credits/purchase/initiate`  
**Auth:** Bearer  
**Body:**

```json
{ "pack": 5 }
```

`pack` must be **1**, **5**, **10**, or **20**.

**200 response (`CreditPurchaseInitiateOut`):**

```json
{
  "purchaseId": "uuid-of-purchase",
  "checkoutUrl": "https://...",
  "credits": 5,
  "amountKobo": 350000
}
```

**Frontend flow**

1. Call initiate → receive `checkoutUrl` and `purchaseId`.
2. Open `checkoutUrl` (new tab, WebView, or redirect).
3. After user pays, Squad notifies the **backend** webhook; credits update on the server.
4. Poll **`GET /api/auth/me`** (or **`GET /api/credits/purchases/{purchaseId}`**) until `credits` increases / `status` is `completed`.

**Errors:** `400` — invalid pack.

---

### 2.3 Purchase status

`GET /api/credits/purchases/{purchase_id}`  
**Auth:** Bearer (must own the purchase)

**200 response:**

```json
{
  "purchaseId": "uuid-string",
  "status": "pending",
  "credits": 5
}
```

`status`: `pending` | `completed` | `failed`

**Errors:** `404` — not found or not yours.

---

## 3. Document verification (consumes 1 credit)

Each successful **initiate** costs **1 credit** immediately (no Squad step on verify).

### 3.1 Start verification

`POST /api/verify/initiate`  
**Auth:** Bearer  
**Content-Type:** `multipart/form-data`  

**Form field**

| Field | Type | Notes |
|--------|------|--------|
| `file` | file | Required. PDF, JPEG, or PNG. **Max 5 MB**. |

Example (browser):

```ts
const form = new FormData();
form.append("file", fileBlob, "certificate.pdf");
await fetch(`${BASE}/api/verify/initiate`, {
  method: "POST",
  headers: { Authorization: `Bearer ${accessToken}` },
  body: form,
});
```

**200 response (`InitiateOut`):**

```json
{
  "verificationId": "uuid",
  "creditsRemaining": 4
}
```

Processing runs **asynchronously** (Celery). Poll **§3.2** with `verificationId`.

**Errors**

| Status | When |
|--------|------|
| `400` | Wrong file type or file &gt; 5 MB |
| `401` | Missing/invalid token |
| `402` | Not enough credits |

**402 body** (object inside `detail`):

```json
{
  "detail": {
    "message": "Insufficient credits. Buy a credit pack to run a verification.",
    "credits": 0
  }
}
```

Send the user to **§2.2** when you get `402`.

---

### 3.2 Verification status (poll)

`GET /api/verify/{verification_id}/status`  
**Auth:** Bearer  

**200 response (`StatusOut`):**

```json
{
  "status": "processing",
  "verdict": null,
  "trustScore": null,
  "summary": null
}
```

`status` values: `pending` | `processing` | `complete` | `error`

When `status` is `complete`, `verdict`, `trustScore`, and `summary` are usually set. On `error`, verdict/score/summary may stay `null` — load the **detail** endpoint or handle empty.

**Errors:** `404`, `403` (wrong user).

**Suggested polling:** every 2–4 s while `processing`, back off when `complete` or `error`.

---

## 4. Verification history & full report

### 4.1 List verifications

`GET /api/verifications?page=1&limit=10&verdict=SUSPICIOUS&search=cert`  
**Auth:** Bearer  

**Query params**

| Param | Default | Notes |
|--------|---------|--------|
| `page` | `1` | ≥ 1 |
| `limit` | `10` | 1–100 |
| `verdict` | omit | Optional: `AUTHENTIC`, `SUSPICIOUS`, or `FAKE` |
| `search` | omit | Case-insensitive substring on `documentName` |

**200 response (`VerificationListOut`):**

```json
{
  "data": [
    {
      "id": "uuid",
      "documentName": "cert.pdf",
      "verdict": "SUSPICIOUS",
      "trustScore": 65,
      "status": "complete",
      "createdAt": "2026-05-13T10:00:00+00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 10
}
```

---

### 4.2 Verification detail (full UI payload)

`GET /api/verifications/{verification_id}`  
**Auth:** Bearer  

**200 response (`VerificationDetailOut`):**

```json
{
  "id": "uuid",
  "documentName": "cert.pdf",
  "squadTransactionRef": null,
  "paymentStatus": "paid",
  "status": "complete",
  "verdict": "SUSPICIOUS",
  "trustScore": 65,
  "flags": ["…"],
  "passedChecks": ["…"],
  "summary": "One paragraph explanation.",
  "issuerContactHints": null,
  "createdAt": "2026-05-13T10:00:00+00:00",
  "completedAt": "2026-05-13T10:01:30+00:00"
}
```

**Enums (string values)**

- **`paymentStatus`:** `pending` | `paid` | `failed`
- **`status`:** `pending` | `processing` | `complete` | `error`
- **`verdict`:** `AUTHENTIC` | `SUSPICIOUS` | `FAKE` or `null` until done

**`issuerContactHints`**

- **`null`** — no issuer-hint block for this row (wrong verdict band, no Tavily path, or legacy data).
- **Object** — present only when the backend stored hints (typically **SUSPICIOUS** + trust **45–70** + web path). Shape:

```json
{
  "included": true,
  "trigger": "suspicious_45_70_trust",
  "unverified": true,
  "disclaimer": "…",
  "items": [
    {
      "type": "email",
      "value": "admissions@example.edu.ng",
      "sourceUrl": "https://…",
      "sourceTitle": "…"
    }
  ],
  "suggestedOutreachMessage": "Subject: …\n\nDear …",
  "suggestedOutreachMessageNote": "…",
  "outreachMessageSource": "ai_merge",
  "note": null
}
```

- **`items`** may be **empty** if no email/phone was found in snippets; **`note`** may be `"no_contacts_found_in_snippets"`.
- **`outreachMessageSource`:** `ai_merge` | `template_fallback` | `null` (older rows).
- Show **`suggestedOutreachMessage`** with a **Copy** button; treat **`disclaimer`** and **`suggestedOutreachMessageNote`** as small print.

**Errors:** `404`, `403`.

---

## 5. Account settings

### 5.1 Change password

`PUT /api/user/password`  
**Auth:** Bearer  

**Body:**

```json
{
  "currentPassword": "old",
  "newPassword": "newlonger"
}
```

**200:** `{ "message": "Password updated successfully" }`  
**401:** current password wrong.

---

### 5.2 Delete account

`DELETE /api/user`  
**Auth:** Bearer  

**200:** `{ "message": "Account deleted" }`  
**Warning:** This removes the user row; handle confirmations in the UI.

---

## 6. Server-only: Squad webhook (not called by frontend)

`POST /api/verify/webhook`

Squad’s servers call this with a signed body. The SPA **must not** pretend to be Squad. Configure **`SQUAD_WEBHOOK_CALLBACK_URL`** on the backend to a **public HTTPS** URL that reaches this route.

---

## 7. Typical user journeys (cheat sheet)

### A) First-time user

1. `POST /api/auth/register` → note `credits` (1).
2. `POST /api/auth/login` → store tokens.
3. `POST /api/verify/initiate` with `file` → `verificationId`, `creditsRemaining`.
4. Poll `GET /api/verify/{id}/status` until `complete` / `error`.
5. `GET /api/verifications/{id}` for full report + optional `issuerContactHints`.

### B) Out of credits

1. `POST /api/verify/initiate` → **402** → show “Buy credits”.
2. `GET /api/credits/packs` for prices.
3. `POST /api/credits/purchase/initiate` → open `checkoutUrl`.
4. After payment, poll `GET /api/auth/me` until `credits` increases.
5. Retry verify.

### C) Session refresh

When `access_token` expires, `POST /api/auth/refresh?refresh_token=...` then retry the failed request.

---

## 8. Global errors

| Status | Meaning |
|--------|---------|
| `401` | Missing/invalid Bearer or wrong password |
| `403` | Authenticated but not allowed (e.g. another user’s verification) |
| `404` | Resource not found |
| `409` | Register conflict (email taken) |
| `422` | Validation error (FastAPI) — body lists invalid fields |
| `500` | Unhandled server error — `{ "error": "Internal server error", "detail": "…" }` |

FastAPI usually wraps errors as `{ "detail": ... }` where `detail` is a string **or** an object/array for validation.

---

## 9. Product copy reminders (for UI)

- Verdicts are **AI screening**, not a legal ruling from the school or ministry.
- **`issuerContactHints`** contacts come from **web snippets** — always confirm on the **official** site before calling or emailing.
- **`suggestedOutreachMessage`** is a **draft**; users must replace placeholders and proofread.

---

*Generated for VeraDoc backend; field names match current Pydantic/OpenAPI models. When in doubt, use `/docs` against your running API.*
