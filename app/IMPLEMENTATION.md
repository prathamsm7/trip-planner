# Safar AI — Implementation tracker

> Keep planning/phases here; product code lives in `backend/` and `frontend/`.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Scaffold, single `npm run dev` | Done |
| 1 | Supervisor trip agent | Done |
| 2 | FastAPI + SSE streaming | Done |
| 3 | Next.js chat + step progress | Done |
| 4 | Right panel tabs + package card | Done |
| 5 | Weather extract | Done |

## Decisions

- Brand: **Safar AI**
- No floating package bar (v1)
- Itinerary sub-tabs: Overview + Daily Plan only
- Missing trip details are asked in the normal chat
- A finished itinerary opens the itinerary tab

## Dev

```bash
cd app && npm install && npm run dev
```

- API: http://localhost:8000
- Web: http://localhost:3000
