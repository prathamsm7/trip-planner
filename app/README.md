# Safar AI

Conversation-based trip planner (Next.js + FastAPI + LangGraph).

## Setup

1. Copy env from repo root or use examples:

```bash
cp ../.env app/.env   # optional if keys are at repo root
cp .env.example app/.env
cp frontend/.env.local.example frontend/.env.local
```

Required: `OPENAI_API_KEY`, `SERPAPI_API_KEY`

2. Install and run (single command):

```bash
cd app
npm install
npm run install:all
npm run dev
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

## Structure

- `backend/` — FastAPI + LangGraph (ported from `../traveltest.ipynb`)
- `frontend/` — Next.js UI
- `IMPLEMENTATION.md` — phase tracker

## Notes

- MVP uses in-memory checkpoints (`thread_id` in localStorage).
- No floating package bar in v1.
- Notebook at repo root is unchanged for experiments.
