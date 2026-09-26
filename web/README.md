# Airmate Web (`web/`)

Next.js frontend for Airmate (Asthma Air Guard).

- **Framework**: Next.js App Router (TypeScript, Tailwind CSS)
- **Export Mode**: Static export (`output: "export"`, `trailingSlash: true`, `images: { unoptimized: true }`)
- **Backend Serving**: The build output in `web/out` is mounted and served statically at `/` by FastAPI (`uv run airmate-api`).

## Development

```bash
# In development pointing to local FastAPI backend (:8000)
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env.local` if running the dev server on `:3000`.

## Production Build

```bash
npm run build
```

Build outputs static files to `web/out`, which `uv run airmate-api` serves directly at `http://localhost:8000/`.
