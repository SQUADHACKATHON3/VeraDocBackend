# VeraDoc — Backend PRD
**Owner:** Tobi (Next.js API Routes + Squad Integration) & Temi (FastAPI AI Service)
**Repos:**
- Frontend/Backend: github.com/SQUADHACKATHON3/VeraDocFrontend
- AI Service: github.com/SQUADHACKATHON3/VeraDocBacktend
**Stack:** Next.js API Routes, Python FastAPI, MongoDB, Squad API, Groq API
**Deployments:** Vercel (Next.js) · Render (FastAPI)
**Last Updated:** May 2026

---

## 1. Overview

This document defines all backend requirements for VeraDoc. It is split into two services:

- **Service A — Next.js API Layer (Tobi):** API routes inside the Next.js app. Handles auth, Squad payment flow, MongoDB operations, and proxying documents to the FastAPI service.
- **Service B — FastAPI AI Service (Temi):** Standalone Python service deployed on Render. Receives documents, runs AI analysis via Groq, and returns structured JSON verdicts.

---

## 2. MongoDB Schemas

### User
```js
{
  _id: ObjectId,
  name: String,           // required
  organisation: String,   // required
  email: String,          // required, unique
  password: String,       // hashed with bcrypt
  createdAt: Date
}
```

### Verification
```js
{
  _id: ObjectId,
  userId: ObjectId,       // ref: User
  documentName: String,   // original file name
  squadTransactionRef: String,  // from Squad
  paymentStatus: String,  // "pending" | "paid" | "failed"
  status: String,         // "pending" | "processing" | "complete" | "error"
  verdict: String,        // "AUTHENTIC" | "SUSPICIOUS" | "FAKE" | null
  trustScore: Number,     // 0-100 | null
  flags: [String],        // issues detected
  passedChecks: [String], // checks that passed
  summary: String,        // one-sentence AI summary
  createdAt: Date,
  completedAt: Date
}
```

---

## 3. Next.js API Routes (Tobi)

Base URL (local): `http://localhost:3000/api`
Base URL (prod): `https://veradoc.vercel.app/api`

---

### 3.1 Auth Routes

#### `POST /api/auth/register`
Register a new user.

**Request Body:**
```json
{
  "name": "string",
  "organisation": "string",
  "email": "string",
  "password": "string"
}
```

**Logic:**
1. Validate all fields present
2. Check email not already registered
3. Hash password with bcrypt (salt rounds: 10)
4. Save user to MongoDB
5. Return success — NextAuth handles sign-in from frontend

**Response 201:**
```json
{ "message": "Account created successfully" }
```

**Response 409:**
```json
{ "error": "Email already registered" }
```

---

#### NextAuth — `GET/POST /api/auth/[...nextauth]`
Handled by NextAuth.js credentials provider. Validates email + password against MongoDB. Returns JWT session.

---

### 3.2 Verification Routes

#### `POST /api/verify/initiate`
Initiate a verification — upload document and trigger Squad payment.

**Auth:** Required (NextAuth session)

**Request:** `multipart/form-data`
- `file`: PDF, JPG, PNG, JPEG (max 5MB)

**Logic:**
1. Validate file type and size
2. Create a `Verification` document in MongoDB with `status: "pending"`, `paymentStatus: "pending"`
3. Store file temporarily in `/tmp` or as base64 in MongoDB
4. Call Squad Initiate Transaction API:
```
POST https://sandbox-api-d.squadco.com/transaction/initiate
Body: {
  email: user.email,
  amount: 100000,        // NGN 1,000 in kobo
  currency: "NGN",
  transaction_ref: verification._id.toString(),
  callback_url: "https://veradoc.vercel.app/verify/[id]"
}
```
5. Return Squad `checkout_url` and `verificationId` to frontend

**Response 200:**
```json
{
  "verificationId": "abc123",
  "checkoutUrl": "https://sandbox-pay.squadco.com/ref"
}
```

---

#### `POST /api/verify/webhook`
Receive Squad payment webhook and trigger AI analysis.

**Auth:** None (public endpoint) — verified via `x-squad-signature` header

**Logic:**
1. Read raw request body
2. Verify `x-squad-signature` header using HMAC-SHA512 with `SQUAD_SECRET_KEY`
3. If signature invalid → return 401
4. Check event type is `charge_successful`
5. Extract `transaction_ref` (maps to `verificationId`)
6. Update Verification in MongoDB: `paymentStatus: "paid"`, `status: "processing"`
7. Retrieve stored document
8. POST document to FastAPI service `/analyze` endpoint
9. On FastAPI response → update Verification: `status: "complete"`, save verdict, trustScore, flags, passedChecks, summary, completedAt
10. On FastAPI error → update `status: "error"`

**Response 200:**
```json
{ "received": true }
```

> Note: Always return 200 immediately to Squad. Do AI processing asynchronously or within the same handler before responding if sync.

---

#### `GET /api/verify/[id]/status`
Poll verification status. Used by frontend during processing state.

**Auth:** Required

**Logic:**
1. Find Verification by `_id` and `userId` (user can only access their own)
2. Return current status and result if complete

**Response 200:**
```json
{
  "status": "processing",
  "verdict": null,
  "trustScore": null
}
```

```json
{
  "status": "complete",
  "verdict": "AUTHENTIC",
  "trustScore": 87,
  "summary": "Document passed all forensic checks with high confidence."
}
```

---

#### `GET /api/verifications`
Get all verifications for the logged-in user.

**Auth:** Required

**Query Params:**
- `limit` (default: 10)
- `page` (default: 1)
- `verdict` — filter: `AUTHENTIC` | `SUSPICIOUS` | `FAKE`
- `search` — search by documentName

**Response 200:**
```json
{
  "data": [...],
  "total": 42,
  "page": 1,
  "limit": 10
}
```

---

#### `GET /api/verifications/[id]`
Get full detail of a single verification.

**Auth:** Required. User must own the verification.

**Response 200:**
```json
{
  "_id": "abc123",
  "documentName": "certificate.pdf",
  "verdict": "FAKE",
  "trustScore": 12,
  "flags": ["Font inconsistency detected", "Seal appears digitally inserted"],
  "passedChecks": ["Date format valid"],
  "summary": "Multiple forensic anomalies detected. Document likely forged.",
  "createdAt": "2026-05-15T10:32:00Z",
  "completedAt": "2026-05-15T10:32:08Z"
}
```

---

### 3.3 User Routes

#### `PUT /api/user/password`
Change password.

**Auth:** Required

**Request Body:**
```json
{
  "currentPassword": "string",
  "newPassword": "string"
}
```

**Logic:**
1. Verify current password against stored hash
2. Hash new password
3. Update MongoDB

**Response 200:**
```json
{ "message": "Password updated" }
```

---

#### `DELETE /api/user`
Delete account.

**Auth:** Required

**Logic:**
1. Delete all Verifications for user
2. Delete User document

**Response 200:**
```json
{ "message": "Account deleted" }
```

---

## 4. FastAPI AI Service (Temi)

Base URL (local): `http://localhost:8000`
Base URL (prod): `https://veradoc-ai.onrender.com`

---

### 4.1 Health Check

#### `GET /`
```json
{ "status": "VeraDoc AI Service running" }
```

---

### 4.2 Core Endpoint

#### `POST /analyze`
Analyze a document and return a trust verdict.

**Auth:** Internal only. Protected by `X-Internal-Key` header (shared secret between Next.js and FastAPI via env var).

**Request Body:** `multipart/form-data`
- `file`: PDF, JPG, PNG, JPEG

**Logic:**
1. Validate `X-Internal-Key` header
2. If PDF → convert first page to image using `pdf2image`
3. Convert image to base64
4. Call Groq API with system prompt and base64 image
5. Parse JSON response
6. Return structured verdict

**Groq API Call:**
```python
from groq import Groq
import base64

client = Groq(api_key=os.environ["GROQ_API_KEY"])

response = client.chat.completions.create(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    messages=[
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": "Analyze this academic document and return the JSON verdict."
                }
            ]
        }
    ],
    temperature=0.1,
    max_tokens=1000
)
```

**System Prompt:**
```
You are VeraDoc, a forensic document verification AI specialized in detecting 
fake or tampered Nigerian academic certificates and transcripts.

Your ONLY job is to analyze the provided document image for signs of forgery, 
tampering, or inauthenticity.

You MUST always return a JSON object in this exact format with no extra text, 
no markdown, no preamble:

{
  "verdict": "AUTHENTIC" or "SUSPICIOUS" or "FAKE",
  "trust_score": integer between 0 and 100,
  "flags": ["list of specific forensic issues found"],
  "passed_checks": ["list of checks that passed"],
  "summary": "one sentence explanation of your verdict"
}

Analyze the following signals:
- Font consistency across the entire document
- Seal and watermark presence, placement, and quality
- Formatting alignment and spacing regularity
- Text layer anomalies suggesting digital alteration
- Date format validity and logical consistency
- Institution name spelling and official formatting patterns
- Signature presence and placement
- Overall document structural integrity

Verdict guidelines:
- AUTHENTIC (trust_score 75-100): All or most checks pass, no significant anomalies
- SUSPICIOUS (trust_score 40-74): Some anomalies present but not conclusive
- FAKE (trust_score 0-39): Multiple clear forensic indicators of forgery

Do NOT return anything outside the JSON structure.
Do NOT add markdown code fences.
Do NOT explain your reasoning outside the summary field.
```

**Response 200:**
```json
{
  "verdict": "SUSPICIOUS",
  "trust_score": 54,
  "flags": [
    "Seal placement inconsistent with standard OAU certificate format",
    "Font weight varies across different sections"
  ],
  "passed_checks": [
    "Date format valid",
    "Institution name correctly spelled",
    "Signature present"
  ],
  "summary": "Document shows moderate forensic anomalies suggesting possible tampering, particularly around the institutional seal."
}
```

**Response 422:**
```json
{ "error": "Unsupported file type" }
```

**Response 500:**
```json
{ "error": "AI analysis failed", "detail": "..." }
```

---

### 4.3 FastAPI Project Structure

```
VeraDocBacktend/
├── main.py              # FastAPI app, routes
├── analyzer.py          # Groq API call + system prompt
├── utils.py             # PDF to image conversion, base64 helpers
├── requirements.txt
├── .env
└── README.md
```

**requirements.txt:**
```
fastapi
uvicorn
groq
pdf2image
Pillow
python-multipart
python-dotenv
```

---

## 5. Environment Variables

### Next.js Service (Vercel)
```env
NEXTAUTH_SECRET=
NEXTAUTH_URL=

MONGODB_URI=

NEXT_PUBLIC_SQUAD_PUBLIC_KEY=
SQUAD_SECRET_KEY=

FASTAPI_SERVICE_URL=https://veradoc-ai.onrender.com
INTERNAL_SERVICE_KEY=
```

### FastAPI Service (Render)
```env
GROQ_API_KEY=
INTERNAL_SERVICE_KEY=
```

> `INTERNAL_SERVICE_KEY` must be the same value in both services.

---

## 6. Squad API Reference

**Sandbox base URL:** `https://sandbox-api-d.squadco.com`
**Live docs:** `https://docs.squadco.com`
**Auth:** Bearer token — `Authorization: Bearer <SQUAD_SECRET_KEY>`

| Endpoint | Method | Owner | Purpose |
|---|---|---|---|
| `/transaction/initiate` | POST | Tobi | Create payment, get checkout URL |
| `/transaction/verify` | POST | Tobi | Verify transaction status manually |
| Webhook (`/api/verify/webhook`) | POST | Tobi | Receive Squad payment confirmation |

**Webhook Signature Verification:**
```js
import crypto from 'crypto';

const hash = crypto
  .createHmac('sha512', process.env.SQUAD_SECRET_KEY)
  .update(rawBody)
  .digest('hex');

if (hash !== req.headers['x-squad-signature']) {
  return res.status(401).json({ error: 'Invalid signature' });
}
```

---

## 7. Service Communication

```
Next.js API ──POST /analyze──► FastAPI Service
             multipart/form-data (file)
             Header: X-Internal-Key

FastAPI ──────────────────────► Groq API
             base64 image + system prompt

FastAPI ◄─────────────────────── Groq API
             structured JSON verdict

Next.js ◄──── JSON verdict ───── FastAPI
```

---

## 8. Error Handling Standards

All API routes must return consistent error shapes:

```json
{ "error": "Human-readable message", "detail": "Optional technical detail" }
```

| Code | Meaning |
|---|---|
| 200 | Success |
| 201 | Created |
| 400 | Bad request / validation error |
| 401 | Unauthorized (no session or bad signature) |
| 403 | Forbidden (accessing another user's resource) |
| 404 | Not found |
| 409 | Conflict (duplicate email) |
| 500 | Internal server error |

---

## 9. Out of Scope (Hackathon)

- Rate limiting per user
- Email notifications on verification complete
- Bulk document upload and batch processing
- Admin dashboard
- Audit logging

---

*VeraDoc Backend PRD — The Dev Team — Squad Hackathon 3.0*
