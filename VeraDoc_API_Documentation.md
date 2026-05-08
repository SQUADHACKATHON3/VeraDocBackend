# VeraDoc — API Documentation
**Version:** 1.0.0
**Organisation:** github.com/SQUADHACKATHON3
**Last Updated:** May 2026

---

## Base URLs

| Service | Environment | URL |
|---|---|---|
| Next.js API | Local | `http://localhost:3000/api` |
| Next.js API | Production | `https://veradoc.vercel.app/api` |
| FastAPI AI Service | Local | `http://localhost:8000` |
| FastAPI AI Service | Production | `https://veradoc-ai.onrender.com` |

---

## Authentication

All protected Next.js API routes require a valid NextAuth session. Requests without a session return `401`.

The FastAPI service is internal-only and protected by a shared `X-Internal-Key` header. It is never called directly from the frontend.

```
Authorization model:
- Public routes: no auth required
- Protected routes: NextAuth JWT session (cookie-based)
- Internal routes (FastAPI): X-Internal-Key header
```

---

## Response Format

All endpoints return JSON. Errors follow this shape:

```json
{ "error": "Human-readable message", "detail": "Optional technical detail" }
```

### HTTP Status Codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Resource created |
| `400` | Bad request or validation error |
| `401` | Unauthenticated |
| `403` | Forbidden — accessing another user's resource |
| `404` | Resource not found |
| `409` | Conflict — e.g. duplicate email |
| `422` | Unprocessable entity |
| `500` | Internal server error |

---

## Next.js API Routes

---

### Auth

---

#### Register
`POST /api/auth/register`

Create a new verifier account.

**Auth:** None

**Request Body:**
```json
{
  "name": "Samkiel",
  "organisation": "OAU Engineering Dept",
  "email": "samkiel@veradoc.com",
  "password": "securepassword123"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | Full name |
| `organisation` | string | Yes | Company or institution |
| `email` | string | Yes | Must be unique |
| `password` | string | Yes | Min 8 characters |

**Response `201`:**
```json
{ "message": "Account created successfully" }
```

**Response `409`:**
```json
{ "error": "Email already registered" }
```

**Response `400`:**
```json
{ "error": "All fields are required" }
```

---

#### NextAuth Session
`POST /api/auth/[...nextauth]`

Handled internally by NextAuth.js. Used by the frontend `signIn()` call.

**Provider:** Credentials (email + password)

**Returns:** JWT session with `id`, `name`, `email`, `organisation`

---

### Verifications

---

#### Initiate Verification
`POST /api/verify/initiate`

Upload a document and create a Squad payment session.

**Auth:** Required

**Request:** `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | Yes | PDF, JPG, PNG, JPEG. Max 5MB |

**Response `200`:**
```json
{
  "verificationId": "6645f3c2a1b2c3d4e5f60001",
  "checkoutUrl": "https://sandbox-pay.squadco.com/4678388588350909090AH"
}
```

**Response `400`:**
```json
{ "error": "Invalid file type. Accepted: PDF, JPG, PNG, JPEG" }
```

**Response `400`:**
```json
{ "error": "File size exceeds 5MB limit" }
```

**Response `401`:**
```json
{ "error": "Unauthorized" }
```

---

#### Squad Payment Webhook
`POST /api/verify/webhook`

Receives Squad payment confirmation. Triggers AI analysis pipeline.

**Auth:** None — verified via `x-squad-signature` HMAC header

**Headers:**
| Header | Value |
|---|---|
| `x-squad-signature` | HMAC-SHA512 of raw request body using `SQUAD_SECRET_KEY` |

**Request Body (sent by Squad):**
```json
{
  "Event": "charge_successful",
  "Body": {
    "transaction_ref": "6645f3c2a1b2c3d4e5f60001",
    "transaction_status": "Success",
    "amount": 100000,
    "currency": "NGN",
    "email": "user@example.com"
  }
}
```

**Logic:**
1. Verify `x-squad-signature`
2. Check event is `charge_successful`
3. Update Verification `paymentStatus: "paid"`, `status: "processing"`
4. Forward document to FastAPI `/analyze`
5. Save result, update `status: "complete"`

**Response `200`:**
```json
{ "received": true }
```

**Response `401`:**
```json
{ "error": "Invalid signature" }
```

> Always return `200` to Squad immediately to prevent retries, even if downstream processing takes time.

---

#### Poll Verification Status
`GET /api/verify/[id]/status`

Poll the current status of a verification. Used by the frontend during the processing state.

**Auth:** Required

**Path Params:**
| Param | Type | Description |
|---|---|---|
| `id` | string | Verification `_id` |

**Response `200` — Processing:**
```json
{
  "status": "processing",
  "verdict": null,
  "trustScore": null,
  "summary": null
}
```

**Response `200` — Complete:**
```json
{
  "status": "complete",
  "verdict": "AUTHENTIC",
  "trustScore": 91,
  "summary": "Document passed all forensic checks with high confidence."
}
```

**Response `200` — Error:**
```json
{
  "status": "error",
  "verdict": null,
  "trustScore": null,
  "summary": null
}
```

**Response `404`:**
```json
{ "error": "Verification not found" }
```

**Response `403`:**
```json
{ "error": "Forbidden" }
```

---

#### Get All Verifications
`GET /api/verifications`

Retrieve all verifications for the authenticated user with filtering and pagination.

**Auth:** Required

**Query Parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `page` | number | `1` | Page number |
| `limit` | number | `10` | Results per page |
| `verdict` | string | — | Filter: `AUTHENTIC`, `SUSPICIOUS`, `FAKE` |
| `search` | string | — | Search by document name |

**Example Request:**
```
GET /api/verifications?page=1&limit=10&verdict=FAKE
```

**Response `200`:**
```json
{
  "data": [
    {
      "_id": "6645f3c2a1b2c3d4e5f60001",
      "documentName": "transcript.pdf",
      "verdict": "FAKE",
      "trustScore": 12,
      "status": "complete",
      "createdAt": "2026-05-15T10:32:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 10
}
```

---

#### Get Single Verification
`GET /api/verifications/[id]`

Retrieve full details of a single verification including all AI output.

**Auth:** Required. User must own the verification.

**Path Params:**
| Param | Type | Description |
|---|---|---|
| `id` | string | Verification `_id` |

**Response `200`:**
```json
{
  "_id": "6645f3c2a1b2c3d4e5f60001",
  "documentName": "oluwaseun_certificate.pdf",
  "squadTransactionRef": "4678388588350909090AH",
  "paymentStatus": "paid",
  "status": "complete",
  "verdict": "SUSPICIOUS",
  "trustScore": 54,
  "flags": [
    "Seal placement inconsistent with standard certificate format",
    "Font weight varies across different sections"
  ],
  "passedChecks": [
    "Date format valid",
    "Institution name correctly spelled",
    "Signature present"
  ],
  "summary": "Document shows moderate forensic anomalies suggesting possible tampering around the institutional seal.",
  "createdAt": "2026-05-15T10:32:00Z",
  "completedAt": "2026-05-15T10:32:08Z"
}
```

**Response `404`:**
```json
{ "error": "Verification not found" }
```

**Response `403`:**
```json
{ "error": "Forbidden" }
```

---

### User

---

#### Change Password
`PUT /api/user/password`

**Auth:** Required

**Request Body:**
```json
{
  "currentPassword": "oldpassword123",
  "newPassword": "newpassword456"
}
```

**Response `200`:**
```json
{ "message": "Password updated successfully" }
```

**Response `401`:**
```json
{ "error": "Current password is incorrect" }
```

---

#### Delete Account
`DELETE /api/user`

Permanently deletes the user account and all associated verifications.

**Auth:** Required

**Response `200`:**
```json
{ "message": "Account deleted successfully" }
```

---

## FastAPI AI Service Routes

> This service is internal. It is only called by the Next.js backend via `FASTAPI_SERVICE_URL`. Never expose this service URL to the client.

---

#### Health Check
`GET /`

**Auth:** None

**Response `200`:**
```json
{ "status": "VeraDoc AI Service running" }
```

---

#### Analyze Document
`POST /analyze`

Analyze an academic document and return a forensic trust verdict.

**Auth:** `X-Internal-Key` header (shared secret)

**Request:** `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | Yes | PDF, JPG, PNG, JPEG |

**Headers:**
| Header | Required | Description |
|---|---|---|
| `X-Internal-Key` | Yes | Shared secret matching `INTERNAL_SERVICE_KEY` env var |
| `Content-Type` | Yes | `multipart/form-data` |

**Processing:**
1. Validate `X-Internal-Key`
2. If PDF — convert first page to JPEG using `pdf2image`
3. Convert image to base64
4. Send to Groq API (`meta-llama/llama-4-scout-17b-16e-instruct`) with structured system prompt
5. Parse and validate JSON response
6. Return verdict

**Response `200`:**
```json
{
  "verdict": "FAKE",
  "trust_score": 11,
  "flags": [
    "Institutional seal appears digitally inserted",
    "Font inconsistency detected in student name field",
    "Watermark pattern does not match known OAU format",
    "Signature appears copied from another document"
  ],
  "passed_checks": [
    "Date format valid"
  ],
  "summary": "Multiple strong forensic indicators of forgery detected. Document is highly likely to be fake."
}
```

**Response `401`:**
```json
{ "error": "Unauthorized" }
```

**Response `422`:**
```json
{ "error": "Unsupported file type" }
```

**Response `500`:**
```json
{ "error": "AI analysis failed", "detail": "Groq API timeout" }
```

---

## Squad API Reference

VeraDoc uses the following Squad APIs. Full documentation at `https://docs.squadco.com`.

---

#### Initiate Transaction
`POST https://sandbox-api-d.squadco.com/transaction/initiate`

Called by Tobi's Next.js API to create a payment session.

**Headers:**
```
Authorization: Bearer <SQUAD_SECRET_KEY>
Content-Type: application/json
```

**Request Body:**
```json
{
  "email": "user@example.com",
  "amount": 100000,
  "currency": "NGN",
  "transaction_ref": "6645f3c2a1b2c3d4e5f60001",
  "callback_url": "https://veradoc.vercel.app/verify/6645f3c2a1b2c3d4e5f60001"
}
```

| Field | Notes |
|---|---|
| `amount` | In kobo. NGN 1,000 = `100000` |
| `transaction_ref` | Use the MongoDB Verification `_id` |
| `callback_url` | Where Squad redirects after payment |

**Response:**
```json
{
  "status": 200,
  "data": {
    "checkout_url": "https://sandbox-pay.squadco.com/4678388588350909090AH",
    "transaction_ref": "6645f3c2a1b2c3d4e5f60001"
  }
}
```

---

#### Verify Transaction
`POST https://sandbox-api-d.squadco.com/transaction/verify`

Manually verify a transaction status. Used as a fallback if webhook is delayed.

**Headers:**
```
Authorization: Bearer <SQUAD_SECRET_KEY>
Content-Type: application/json
```

**Request Body:**
```json
{
  "transaction_ref": "6645f3c2a1b2c3d4e5f60001"
}
```

**Response:**
```json
{
  "status": 200,
  "data": {
    "transaction_status": "Success",
    "amount": 100000,
    "currency": "NGN",
    "email": "user@example.com"
  }
}
```

---

## Environment Variables Summary

### Next.js (Vercel)
```env
NEXTAUTH_SECRET=
NEXTAUTH_URL=https://veradoc.vercel.app

MONGODB_URI=

NEXT_PUBLIC_SQUAD_PUBLIC_KEY=
SQUAD_SECRET_KEY=

FASTAPI_SERVICE_URL=https://veradoc-ai.onrender.com
INTERNAL_SERVICE_KEY=
```

### FastAPI (Render)
```env
GROQ_API_KEY=
INTERNAL_SERVICE_KEY=
```

---

## Data Flow Summary

```
[Frontend] 
  → POST /api/verify/initiate        (upload file, create verification)
  → Redirect to Squad checkout_url   (user pays)
  
[Squad] 
  → POST /api/verify/webhook         (payment confirmed)
  
[Next.js API]
  → POST https://veradoc-ai.onrender.com/analyze  (forward document)
  
[FastAPI]
  → Groq API (llama-4-scout-17b-16e-instruct)     (analyze document)
  → Return JSON verdict
  
[Next.js API]
  → Save result to MongoDB
  
[Frontend]
  → GET /api/verify/[id]/status      (poll until complete)
  → GET /api/verifications/[id]      (fetch full result)
  → Render results dashboard
```

---

*VeraDoc API Documentation — The Dev Team — Squad Hackathon 3.0*
