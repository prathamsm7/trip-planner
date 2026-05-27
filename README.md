# Trip Planner (Safar AI)

Safar AI is a conversation-based trip planning application with:

- **Frontend**: Next.js + React + TypeScript
- **Backend**: FastAPI + LangGraph + OpenAI + SerpAPI
- **Streaming UX**: SSE (Server-Sent Events) for step-by-step assistant progress

The repo also includes an experiment notebook (`traveltest.ipynb`) used during prototyping.

## Project Structure

```text
trip-planner/
├── app/
│   ├── backend/                  # FastAPI + LangGraph API
│   │   ├── src/safar_api/
│   │   │   ├── api/              # Routes, stream helpers, serializers
│   │   │   ├── graph/            # LangGraph builder
│   │   │   ├── models/           # State + schemas
│   │   │   ├── nodes/            # Agent node logic (planner, weather, flights, hotels, FAQ)
│   │   │   └── services/         # LLM + SerpAPI wrappers
│   │   └── pyproject.toml
│   ├── frontend/                 # Next.js UI
│   │   ├── src/app/              # App router entry
│   │   ├── src/components/       # Chat + results UI
│   │   ├── src/hooks/            # useSafarTrip streaming state hook
│   │   └── src/lib/              # API client + shared types
│   ├── .env.example
│   ├── package.json              # Monorepo-like convenience scripts
│   └── README.md
├── traveltest.ipynb
└── README.md
```

## Features

- Conversational trip planning workflow
- Itinerary generation
- Flight and hotel suggestions
- Weather summary integration
- Follow-up / clarification flow
- Live step progress from backend graph execution
- Thread-based chat continuity

## Tech Stack

### Frontend
- Next.js 15
- React 19
- TypeScript
- Tailwind CSS

### Backend
- Python 3.12+
- FastAPI
- LangGraph + LangChain OpenAI
- SSE via `StreamingResponse`

## Prerequisites

- **Node.js** 18+ (LTS recommended)
- **npm** 9+
- **Python** 3.12+
- **uv** package manager for Python ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- API keys:
  - OpenAI
  - SerpAPI

## Environment Variables

Create environment files before running locally.

### Backend (`app/.env`)

Copy from example:

```bash
cp app/.env.example app/.env
```

Variables:

- `OPENAI_API_KEY` - required
- `SERPAPI_API_KEY` - required
- `OPENAI_SECONDARY_MODEL` - optional model override
- `OPENAI_FLIGHT_MODEL` - optional model override
- `OPENAI_WEATHER_MODEL` - optional model override
- `LANGSMITH_API_KEY` - optional tracing
- `LANGSMITH_PROJECT` - optional tracing project name
- `CORS_ORIGINS` - comma-separated allowed origins (default local frontend)

Example:

```env
OPENAI_API_KEY=...
SERPAPI_API_KEY=...
CORS_ORIGINS=http://localhost:3000
```

### Frontend (`app/frontend/.env.local`)

Copy from example:

```bash
cp app/frontend/.env.local.example app/frontend/.env.local
```

Variable:

- `NEXT_PUBLIC_API_URL` - backend base URL for browser calls

Local value:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Local Development

From repository root:

```bash
cd app
npm install
npm run install:all
npm run dev
```

This starts both services:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend: [http://localhost:8000](http://localhost:8000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Available Scripts

From `app/`:

- `npm run dev` - run backend + frontend together
- `npm run dev:api` - run only FastAPI backend
- `npm run dev:web` - run only Next.js frontend
- `npm run install:all` - install backend (`uv sync`) and frontend (`npm install`) deps

From `app/frontend/`:

- `npm run dev` - Next.js dev server
- `npm run build` - production build
- `npm run start` - run production server
- `npm run lint` - lint frontend

## API Overview

Base path: `/api`

- `GET /api/health` - health check
- `POST /api/threads` - create thread id
- `GET /api/threads/{thread_id}` - fetch thread snapshot + pending interrupt
- `POST /api/threads/{thread_id}/messages` - stream graph run (SSE)
- `POST /api/threads/{thread_id}/resume` - resume after follow-up answer (SSE)
- `PATCH /api/threads/{thread_id}/selections` - persist selected hotels/flights

## Deployment Guide (Vercel + Railway)

Recommended architecture:

- **Frontend** on Vercel
- **Backend** on Railway (public domain)

### 1) Deploy backend (Railway)

- Deploy `app/backend`
- Ensure service has public domain (not `*.railway.internal`)
- Set backend env vars (`OPENAI_API_KEY`, `SERPAPI_API_KEY`, etc.)
- Set:
  - `CORS_ORIGINS=https://<your-vercel-domain>,http://localhost:3000`

### 2) Deploy frontend (Vercel)

- Root directory for project: `app/frontend`
- Framework preset: **Next.js**
- Set env var:
  - `NEXT_PUBLIC_API_URL=https://<your-railway-public-domain>`
- Redeploy after env changes

## Troubleshooting

### CORS blocked in browser

Error example:

`No 'Access-Control-Allow-Origin' header is present on the requested resource`

Fix:

- Ensure Railway backend variable `CORS_ORIGINS` includes exact Vercel origin (no trailing slash)
- Redeploy backend after variable change

### Frontend calls wrong API URL

If requests hit unexpected URL segments or localhost in production:

- Confirm `NEXT_PUBLIC_API_URL` is set in Vercel project variables
- Redeploy frontend (required for `NEXT_PUBLIC_*` updates)

### Vercel: "No Output Directory named public"

Fix by configuring project as Next.js:

- Vercel framework preset should be **Next.js**
- Keep `app/frontend/vercel.json` with:
  - `{ "framework": "nextjs" }`

### Build error: `Can't resolve '@/lib/api'`

Usually caused by ignored/untracked files in `app/frontend/src/lib/`.
Ensure your `.gitignore` does not accidentally ignore nested `lib/` directories needed by frontend source.

## Notes

- LangGraph thread state is currently in-memory and keyed by `thread_id`.
- `traveltest.ipynb` is preserved for experimentation and reference.

## Contributing

1. Create a feature branch
2. Make and test changes
3. Open a PR with clear test steps

## License

Add a license file (`LICENSE`) if you plan to open-source this project.