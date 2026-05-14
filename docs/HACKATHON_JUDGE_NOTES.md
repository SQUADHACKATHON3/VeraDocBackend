# Hackathon judge notes (VeraDoc)

Use this file for deck copy and demo narration. It mirrors what the backend actually does.

## AI technical depth (talk track)

**Multimodal forensic pipeline**

- PDFs are rasterized to images (`pdf2image`); raster images are normalized to JPEG for the vision model.
- The model receives **pixels plus** a strict forensic instruction set (layout, seals, typography, chronology, structural integrity).
- Outputs are forced into a **structured JSON contract** (`verdict`, `trust_score`, `flags`, `passed_checks`, `summary`) validated with **Pydantic** (`GroqVerdict` / `GroqMergeOutput`). Malformed JSON is repaired with a small extractor; merge step falls back if the outreach field fails validation.

**Vision + NLP + consistency / anomaly framing**

- **Vision:** document page as image through a multimodal LLM.
- **NLP:** extraction pass for entities (institution, dates, serial, region), merge prompts combining forensic JSON with web snippets, outreach letter generation grounded in extracted fields (no invented serials).
- **Consistency / anomaly:** prompts explicitly treat seal drift, font mismatch, impossible dates, and template inconsistencies as **consistency anomalies** (analogy to anomaly detection on document signals). A **hybrid rule layer** (`forensic_hybrid.py`) enforces coherence between **verdict bands** and **trust_score** (e.g. cannot keep `AUTHENTIC` if score is below the declared AUTHENTIC band).

**Optional web corroboration (Tavily)**

- When `TAVILY_API_KEY` is set: entity-driven queries → snippet blocks → merge model with **guardrails** (web never alone upgrades to AUTHENTIC; caps on score movement; adversarial / irrelevant snippet handling called out in the system prompt).
- Nigeria-first search bias when `VERIFICATION_PRIMARY_REGION=NG` (e.g. `.edu.ng` / regulatory language in merge instructions; query templates include Nigeria unless region is unlocked).

**Hosted LLM vs custom training (honest framing)**

- Core is a **hosted multimodal model** with **engineering depth**: schema validation, hybrid calibration, optional retrieval merge, issuer outreach hints. This is standard for high-stakes MVP teams; custom fine-tuning or a small student model can be a **phase-2** story if you collect a labeled set.

## Slide bullets (short)

1. **Pipeline:** Upload → storage → forensic vision → (optional) entity extract + Tavily → merge + Pydantic validate → hybrid band check → DB + status poll.
2. **Output:** Trust score + three-way verdict + auditable flags + `forensic_only` preserved when web runs (for comparison).
3. **Nigeria-first:** `VERIFICATION_PRIMARY_REGION=NG` (default); set to another code later for multi-country mode (`_REGION_BLOCK_GENERAL` + neutral Tavily bias).
4. **Squad:** Credits purchased via Squad; webhook verifies transactions before granting credits; verification consumes credits (meaningful payment loop for the verification product).

## Responsible AI (one paragraph for deck)

VeraDoc is a **screening aid**, not a court or registrar. Automated checks can **false-positive** (legitimate scans marked suspicious) and **false-negative** (sophisticated forgeries missed). Users should treat `SUSPICIOUS` and borderline scores as a prompt for **human confirmation** with the issuing institution—we surface outreach hints, not a final legal ruling. **Uploaded documents** may contain sensitive personal data; operators should use **encrypted transport**, **access-controlled storage** (e.g. Cloudinary with appropriate policies), **retention limits** aligned with law and policy, and avoid using production data for demos without consent. Teams should monitor for **bias** against low-quality scans or unfamiliar layouts and document known limitations in the demo.

## Backlog (things to do next)

| Priority | Task |
|----------|------|
| P0 | **Demo set:** 5–8 real-looking PDFs/JPEGs (mix: clean legit, blurry legit, obvious fake, subtle fake). Narrate outcomes live. |
| P1 | **Mini eval sheet:** spreadsheet with columns `file_id`, `human_label`, `verdict`, `trust_score`, `notes` (even 15–20 rows impresses judges). |
| P1 | **Deck:** one architecture diagram + Squad payment diagram + Responsible AI paragraph above. |
| P2 | **Optional:** small curated list of **known problematic issuer strings** (env or file) merged into flags only when entity match (hybrid, not ML). |
| P2 | **Unlock regions:** set `VERIFICATION_PRIMARY_REGION` to a non-`NG` code in env when you expand beyond Nigeria (prompts already branch). |
| P3 | **Custom model story:** only if you have time—fine-tune a classifier on exported crops, or train a lightweight binary on embeddings (separate from current MVP). |

## Env reference (new / relevant)

| Variable | Purpose |
|----------|---------|
| `VERIFICATION_PRIMARY_REGION` | Default `NG`. Nigeria-first prompts and Tavily bias. Use another region code later for general international mode. |
| `HYBRID_VERDICT_SCORE_CONSISTENCY` | Default `true`. Set `false` to disable deterministic verdict/score band checks. |
| `TAVILY_API_KEY` | Optional web corroboration step. |
