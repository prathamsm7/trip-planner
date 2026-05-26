# Safar AI — Implementation tracker

> Keep planning/phases here; product code lives in `backend/` and `frontend/`.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Scaffold, single `npm run dev` | Done |
| 1 | LangGraph port from `traveltest.ipynb` | Done |
| 2 | FastAPI + SSE streaming | Done |
| 3 | Next.js chat + step progress | Done |
| 4 | Right panel tabs + package card | Done |
| 5 | Weather extract, FAQ stub | Done |

## Decisions

- Brand: **Safar AI**
- No floating package bar (v1)
- Itinerary sub-tabs: Overview + Daily Plan only
- Resume: LLM maps natural language → `{question: answer}`
- `modify_itinerary` → auto-open itinerary tab in UI

## Dev

```bash
cd app && npm install && npm run dev
```

- API: http://localhost:8000
- Web: http://localhost:3000
