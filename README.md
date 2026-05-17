# Exam Forge

Production-ready web app for exam preparation from tagged PDF question bases.

## Stack

- Backend: Django, Django REST Framework, Simple JWT
- Frontend: React, Vite, React Router, Axios, Recharts
- Database: PostgreSQL
- Infra: Docker Compose

## Project Structure

```text
base/
  <subject_name>/
    *.pdf
backend/
  apps/exams/
    importer.py              # PDF parsing and duplicate-safe import
    services.py              # question selection, scoring, progress updates
    models.py
    serializers.py
    views.py
    management/commands/import_questions.py
frontend/
  src/
    pages/
    components/
    context/
docker-compose.yml
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

After startup:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api
- Django admin: http://localhost:8000/admin

Create an admin user:

```bash
docker compose run --rm backend python manage.py createsuperuser
```

Apply migrations manually, if you run the backend outside Compose:

```bash
cd backend
python manage.py migrate
```

## Import Questions

Question bases live under:

```text
base/<subject_name>/
```

Current example:

```text
base/Machine_learning/Additional Final exam sample questions.pdf
```

Run import:

```bash
docker compose run --rm backend python manage.py import_questions
```

On Render, if Shell is not available, set this backend environment variable and redeploy:

```env
AUTO_IMPORT_QUESTIONS=1
```

Dry run:

```bash
docker compose run --rm backend python manage.py import_questions --dry-run
```

The importer:

- scans every folder inside `base/`;
- creates subjects dynamically from folder names;
- parses every PDF with `<question>`, `<variant>`, `<variantright>`;
- stores questions and variants in PostgreSQL;
- calculates a SHA-256 hash per question to avoid duplicates across files and repeated imports;
- rejects malformed questions with fewer than two variants, duplicated variants, or anything other than exactly one correct answer;
- writes an `ImportRun` with counts and parsing errors.

To add a new subject, create a new folder in `base/`, put PDF files inside, then run the import command again.

## Scoring

Points are awarded by `backend/apps/exams/services.py`:

- first correct answer for a question: `+10`;
- repeated correct answer on a hard or previously missed question: up to `+3`;
- wrong answer: `-2`;
- streak bonuses at meaningful streak milestones;
- positive points per user/question are capped, so one question cannot be farmed forever.

Wrong answers can reduce score repeatedly. Positive score farming is limited by `QUESTION_POINT_CAP`, and leaderboard rows only include users who have answered at least one question.

## Question Selection

The selector is weighted, not plain random:

- unseen questions get high weight;
- questions with wrong answers and low personal winrate get higher weight;
- mastered questions and repeatedly correct questions get lower weight;
- older questions slowly regain weight;
- modes constrain the pool first, then apply weights where appropriate.

Important semantics:

- `times_seen` means the question was included in a started test session.
- `total_answered`, `correct_answers`, `wrong_answers`, and score change only after an answer is submitted.
- `new`, `mistakes`, and `hard` modes do not silently fall back to all questions. If the constrained pool is empty, the API returns `400` with `No questions available for the selected mode.`

Supported modes:

- `random`
- `new`
- `mistakes`
- `hard`
- `rare`
- `review_all`
- `spaced`

## API

Auth:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`

Subjects:

- `GET /api/subjects/`
- `GET /api/subjects/:id/`

Tests:

- `POST /api/tests/start/`

  ```json
  {
    "subject_id": 1,
    "mode": "random",
    "question_count": "10"
  }
  ```

- `GET /api/tests/:id/`
- `POST /api/tests/:id/answer/`

  ```json
  {
    "question_id": 10,
    "selected_variant_id": 42,
    "time_spent": 18
  }
  ```

- `POST /api/tests/:id/finish/`
- `GET /api/tests/:id/result/`

Progress:

- `GET /api/progress/summary/`
- `GET /api/progress/subjects/`
- `GET /api/progress/mistakes/`
- `POST /api/progress/questions/:id/mark-mastered/`

Leaderboard:

- `GET /api/leaderboard/`
- `GET /api/leaderboard/?subject=<id>`

Import:

- `POST /api/admin/import-questions/` admin only
- `GET /api/admin/import-status/`

## Backend Tests

```bash
docker compose run --rm backend python manage.py test
```

Covered areas:

- tagged question parsing;
- duplicate-stable hashing;
- duplicate-safe import across multiple PDF files and repeated runs;
- weighted question selection modes;
- no fallback for empty `new` pools;
- per-question point cap;
- progress and subject stats updates after answers.
- API edge cases for invalid test size, empty subjects, duplicate answers, and leaderboard filtering.

## Docker Notes

`docker compose up --build` starts:

- `db` on the internal Compose network;
- `backend` on `localhost:8000`, running migrations before Gunicorn;
- `frontend` on `localhost:3000`, with `VITE_API_URL=http://localhost:8000/api`.

If you use Docker Desktop with WSL 2, enable integration for the current distro. Without Docker available in the shell, Compose commands cannot run.

## Deploy

The project is prepared for:

- Neon PostgreSQL
- Render backend
- Vercel frontend

Use [DEPLOYMENT.md](DEPLOYMENT.md) for the step-by-step setup.

## Notes For Production

- Set a strong `SECRET_KEY`.
- Set `DEBUG=0`.
- Restrict `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`.
- Keep JWTs short-lived and serve the frontend over HTTPS.
- Put the frontend behind a production web server or build static assets with `npm run build`.
- Add backups for the PostgreSQL volume.

## Future Improvements

- PDF parser preview UI with per-file validation before import.
- Admin review queue for malformed questions.
- More advanced spaced repetition intervals.
- Per-subject achievements and weekly leagues.
- Email/password reset flow.
- Full OpenAPI schema and generated frontend API types.
