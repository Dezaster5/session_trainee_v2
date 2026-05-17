# Deployment Guide: Neon + Render + Vercel

This project is prepared for:

- Neon PostgreSQL as the production database
- Render Web Service for the Django API
- Vercel for the React/Vite frontend

## 1. Push To GitHub

Commit and push the whole repository, including:

- `backend/`
- `frontend/`
- `base/`
- `render.yaml`

Do not commit `.env`.

## 2. Neon

1. Create a Neon project.
2. Copy the pooled or direct connection string.
3. Make sure the connection string includes SSL, for example:

```text
postgresql://user:password@host/dbname?sslmode=require
```

You will use this as `DATABASE_URL` on Render.

## 3. Render Backend

Recommended path: use `render.yaml` from this repo.

1. In Render, create a new Blueprint from the GitHub repository.
2. Render will detect `render.yaml`.
3. Set these environment variables:

```text
DATABASE_URL=<your Neon connection string>
FRONTEND_URL=https://your-vercel-app.vercel.app
CORS_ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
CSRF_TRUSTED_ORIGINS=https://your-vercel-app.vercel.app
```

The blueprint already sets:

```text
DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1,.onrender.com
BASE_QUESTIONS_DIR=/opt/render/project/src/base
DB_SSL_REQUIRE=1
SECURE_SSL_REDIRECT=1
```

Render commands:

```bash
cd backend && bash build.sh
cd backend && bash start.sh
```

Healthcheck:

```text
https://your-render-service.onrender.com/api/health/
```

## 4. Create Admin User On Render

Open Render Shell for the backend service:

```bash
cd backend
python manage.py createsuperuser
```

## 5. Import Questions On Render

Open Render Shell:

```bash
cd backend
python manage.py import_questions
```

Expected output should show imported and duplicate counts. If you already imported locally, production still needs its own import because Neon is a separate database.

If Render Shell is not available, use automatic import:

1. Open the backend service in Render.
2. Go to Environment.
3. Set:

```text
AUTO_IMPORT_QUESTIONS=1
```

4. Redeploy the backend.
5. After successful deploy, you can either keep it enabled or set it back to `0`.

Repeated imports are safe: existing questions are detected by hash and skipped as duplicates.

## 6. Vercel Frontend

1. Import the same GitHub repository into Vercel.
2. Set Root Directory:

```text
frontend
```

3. Vercel will use `frontend/vercel.json`.
4. Set environment variable:

```text
VITE_API_URL=https://your-render-service.onrender.com/api
```

5. Deploy.

After Vercel gives you the final URL, put it back into Render:

```text
FRONTEND_URL=https://your-vercel-app.vercel.app
CORS_ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
CSRF_TRUSTED_ORIGINS=https://your-vercel-app.vercel.app
```

Redeploy Render after changing env variables.

## 7. Local Production Smoke Test

You can test production-like frontend build locally:

```bash
cd frontend
npm ci
npm run build
```

Backend syntax and Django checks:

```bash
cd backend
python manage.py check --deploy
```

For Docker local:

```bash
docker compose up --build
```

## 8. Share With Classmates

Send them the Vercel URL. They should register their own accounts. Progress and leaderboard are per-user and stored in Neon.

## 9. Common Issues

- `CORS` error in browser: update `CORS_ALLOWED_ORIGINS` on Render to the exact Vercel URL.
- `DisallowedHost`: add the backend domain to `ALLOWED_HOSTS`.
- Frontend still calls localhost: update `VITE_API_URL` on Vercel and redeploy.
- No questions in production: run `python manage.py import_questions` in Render Shell.
- Render free service sleeps: first request can be slow.
