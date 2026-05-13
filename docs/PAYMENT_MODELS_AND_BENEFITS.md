# VeraDoc — Payment Models & Benefits

**Purpose:** Describe how customers pay for verification, what each model is for, and why it matters for users and for VeraDoc.

**Payments rail:** All collections go through **Squad** (initiate transaction → user pays → webhook confirms → verification runs). Amounts in Nigeria are expressed in **kobo** in the API (e.g. ₦1,000 = `100000`).

---

## 1. Why payment models matter

- **HR and institutions** have different volumes: a recruiter doing five checks a month should not pay like a university admissions desk doing hundreds.
- **Predictable revenue** (subscriptions, enterprise contracts) funds reliability: API uptime, support, and optional issuer follow-up workflows.
- **Pay-as-you-go** lowers friction for first-time verifiers and demos.

---

## 2. Payment models (overview)

| Model | Who it’s for | Billing pattern | Typical use |
|--------|----------------|-----------------|-------------|
| **Pay-per-verification** | Individuals, small HR, one-off checks | Per document, charged before analysis runs | Low volume, trial, occasional hiring windows |
| **Monthly subscription** | Teams with steady hiring or admissions | Fixed monthly fee for a bundle or “unlimited” tier (per your plan limits) | Medium-to-high monthly volume, predictable budget |
| **Enterprise API** | Large companies, banks, agencies, schools embedding VeraDoc | Custom pricing, SLA, integration support | High volume, embedded workflows, compliance needs |

*Exact NGN figures should stay in your commercial/pricing sheet; the product overview referenced illustrative ranges (e.g. pay-per in hundreds–low thousands of Naira per check; subscriptions from tens of thousands NGN/month depending on tier).*

---

## 3. Pay-per-verification

### What it is

The user uploads a document and pays **once per verification** before the AI (and optional web corroboration) runs. No recurring commitment.

### Benefits — **customers**

- **Low barrier:** Pay only when they need a check.
- **Simple to explain:** One fee = one report on one document (subject to fair-use limits you define).
- **Good for spikes:** Seasonal hiring or a single sensitive hire.

### Benefits — **VeraDoc**

- Easy onboarding and hackathon demos (“pay → verify”).
- Natural upgrade path when volume repeats (“you’ve spent X this month; subscription saves Y”).
- Cash-per-event aligns cost with Groq/Tavily/infrastructure usage.

---

## 4. Monthly subscription

### What it is

A fixed recurring fee for **included verifications per month** or an **unlimited / high-cap** tier within documented limits (rate limits, abuse prevention, and fair use policy).

### Benefits — **customers**

- **Predictable cost** for finance teams.
- **Faster workflow:** Team members can verify without approving micro-payments each time (depending on how you implement seats vs organisation wallet).
- **Better for compliance programmes:** Regular screening as standard process.

### Benefits — **VeraDoc**

- **Recurring revenue (MRR)** improves planning and support coverage.
- Stronger retention when embedded in HR or admissions routines.
- Easier to bundle **priority support** or **bulk reporting**.

---

## 5. Enterprise API access

### What it is

Direct integration of VeraDoc into the customer’s **ATS, HRIS, or internal portal**, typically with:

- API keys and environment separation (sandbox vs live),
- Volume-based or annual contracts,
- Optional SLAs, audit logs, and dedicated onboarding.

### Benefits — **customers**

- **Automation:** Verify at scale inside existing tools (less copy-paste).
- **Governance:** Central billing, role-based access, and audit trail (as you implement them).
- **Brand trust:** Fits procurement and infosec review for large employers.

### Benefits — **VeraDoc**

- Highest **lifetime value** and clearest path to **national or sector-wide** deployment (education, banking, government contractors).
- Funds deeper integrations (issuer workflows, dedicated infra).

---

## 6. Cross-cutting benefits (all models)

### For verifiers (end users)

- **Defensible process:** Payment creates an auditable trail that a check was requested and completed (alongside your stored verification record).
- **Structured output:** Verdict, score, flags, and optional web context — usable in hiring or admissions discussions (with clear disclaimers that AI + search are **screening aids**, not legal proof unless issuer confirms).

### For VeraDoc (business)

- **Squad integration** satisfies hackathon/commercial requirements for real payments, not mock gates.
- Tiered pricing matches **cost drivers**: model inference, search API calls, storage, and human escalation if you add it later.

---

## 7. Product positioning (honest scope)

- **Pay-per / subscription / enterprise** describe **who pays and how often**, not “legal truth.”
- **Issuer confirmation** (ministry, school, exam body) remains the gold standard for **official acceptance**; VeraDoc tiers fund better **screening**, **workflow**, and eventually **manual or API issuer routes** where partnerships exist.

---

## 8. Implementation notes (engineering)

- **Single verification fee** is enforced in the backend via Squad `transaction/initiate` using a configurable amount (e.g. `SQUAD_VERIFICATION_AMOUNT_KOBO`).
- **Subscriptions and enterprise** usually require a **billing product** on top of per-verification credits or Stripe-like invoicing; Squad can remain the payment collector per invoice or you add a subscription provider — document your chosen approach in the deployment runbook when finalized.

---

*VeraDoc — internal commercial & product reference — May 2026*
