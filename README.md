# VeraDoc Backend

VeraDoc is an AI-powered forensic document verification platform. The backend is built with FastAPI and is responsible for handling document uploads, interacting with the Groq Vision API to detect forgeries, and utilizing Tavily to cross-reference institutional data in real-time.

## 🚀 Key Features

*   **Forensic AI Analysis**: Uses **Meta Llama 4 Scout (17B)** via **Groq's LPU inference engine** to analyze document text layers, fonts, seals, and dates to detect anomalies in milliseconds.
*   **Web Corroboration**: Integrates with **Tavily AI Search** to crawl official institution websites, confirming accreditation and extracting registrar contact information via Regex.
*   **Deterministic Hybrid Logic**: Employs a custom consistency engine that fuses AI vision scores with web evidence to output an absolute verdict (`AUTHENTIC`, `NEEDS REVIEW`, or `FAKE`).
*   **Squad Payments**: Built-in wallet and credit system via Squad API webhooks for per-verification billing.
*   **Secure Auth**: JWT-based authentication with Redis token blocklisting and Google OAuth support.

## 🛠 Tech Stack

*   **Framework**: FastAPI (Python 3.12+)
*   **Database**: PostgreSQL
*   **ORM / Migrations**: SQLAlchemy 2.0 & Alembic
*   **AI Models**: Groq API (Vision)
*   **Web Search**: Tavily API
*   **Caching & Rate Limiting**: Redis
*   **File Storage**: Local Disk or Cloudinary
*   **Image Processing**: Pillow & pdf2image (requires `poppler-utils`)

## 📋 Prerequisites

*   Python 3.12+
*   PostgreSQL
*   Redis (optional, but recommended for token caching)
*   `poppler-utils` (Required for PDF-to-Image extraction)
    *   Mac: `brew install poppler`
    *   Linux: `sudo apt-get install poppler-utils`

## ⚙️ Environment Setup

Create a `.env` file in the root directory and populate it with the necessary variables (see `app/core/config.py` for all options):

```ini
ENV=local
DATABASE_URL=postgresql://user:password@localhost/veradoc
REDIS_URL=redis://localhost:6379/0

# Authentication
JWT_SECRET=your_super_secret_jwt_key

# External APIs
GROQ_API_KEY=gsk_...
TAVILY_API_KEY=tvly-...

# Payments
SQUAD_SECRET_KEY=sandbox_sk_...

# Frontend URL for CORS
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
```

## 💻 Local Development

1.  **Create a Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(If using pip-tools or poetry, use the respective install command)*

3.  **Run Database Migrations:**
    ```bash
    alembic upgrade head
    ```

4.  **Start the Server:**
    ```bash
    uvicorn app.main:app --reload --port 8000
    ```

The API will be available at `http://localhost:8000`. 
Interactive API documentation (Swagger) is automatically generated at `http://localhost:8000/docs`.

## 📂 Project Structure

```
├── alembic/                 # Database migration scripts
├── app/
│   ├── api/                 # FastAPI routers and endpoints
│   ├── core/                # Configuration and security logic
│   ├── models/              # SQLAlchemy database models
│   ├── schemas/             # Pydantic schemas for request/response validation
│   ├── services/            # Core business logic (Groq, Tavily, Forensic Hybrid Engine)
│   └── main.py              # Application entry point
├── storage/                 # Local file upload storage (if not using Cloudinary)
└── requirements.txt         # Project dependencies
```

## 🧠 AI Verification Pipeline

1.  User uploads a document (PDF, PNG, JPG).
2.  `pdf2image` parses the document and `Pillow` compresses it into an optimized Base64 JPEG.
3.  The Groq API (Vision) analyzes the visual structure for anomalies, outputting a trust score.
4.  The system parses the institution name and triggers Tavily to scrape the web for accreditation and contact hints.
5.  The **Hybrid Consistency Engine** merges the AI score and web data to deliver the final structured JSON verdict to the frontend.
