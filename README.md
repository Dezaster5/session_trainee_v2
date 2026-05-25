# Exam Forge

Production-ready web app for exam preparation from tagged PDF and JSON question bases.

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
    *.json
backend/
  apps/exams/
    importer.py              # PDF/JSON parsing and duplicate-safe import
    services.py              # theory question selection, scoring, progress updates
    live_coding_services.py  # similarity scoring for live coding practice
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
base/Sociology/sociology_exam_questions.json
base/Web_component_development/final_exam_questions.json
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
- parses every JSON file with `questions` and `liveCoding` sections;
- creates `Topic` records from JSON topics/subtopics;
- stores questions and variants in PostgreSQL;
- stores live coding tasks separately from multiple-choice questions;
- calculates a SHA-256 hash per question to avoid duplicates across files and repeated imports;
- uses stable JSON ids in hashes, so repeated imports update existing JSON records instead of duplicating them;
- rejects malformed PDF questions with fewer than two variants, duplicated variants, or anything other than exactly one correct answer;
- rejects malformed JSON multiple-choice questions unless they have exactly four variants and exactly one correct answer;
- writes an `ImportRun` with counts and parsing errors.

To add a new subject, create a new folder in `base/`, put PDF or JSON files inside, then run the import command again.

Minimal JSON shape:

```json
{
  "questions": [
    {
      "id": "Q0001",
      "topic": "Spring Boot / Backend",
      "subtopic": "Spring Fundamentals",
      "question": "What does @RestController do?",
      "options": [
        {"id": "A", "text": "Marks a REST controller", "is_correct": true},
        {"id": "B", "text": "Creates a database", "is_correct": false},
        {"id": "C", "text": "Configures the JVM only", "is_correct": false},
        {"id": "D", "text": "Marks a JPA relation only", "is_correct": false}
      ],
      "correct_option_id": "A",
      "explanation": "..."
    }
  ],
  "liveCoding": [
    {
      "id": "LC0001",
      "topic": "Docker",
      "task": "Write the command to check Docker version.",
      "expected_solution_language": "shell",
      "expected_solution": "docker --version",
      "checking_method": {"mode": "similarity_percentage"}
    }
  ]
}
```

### Sociology JSON import

The Sociology base is stored at:

```text
base/Sociology/sociology_exam_questions.json
```

It uses the same JSON importer as Web Component Development:

```json
{
  "questions": [
    {
      "id": "SOC-Q0001",
      "topic": "Foundations of Sociology and Scientific Knowledge",
      "subtopic": "Sociology as Science, Positivism, Ethics and Research Logic",
      "question": "Sociology as a science is product of",
      "type": "multiple_choice_manual_answer_practice",
      "options": [
        {"id": "A", "text": "Classical antiquity and its moral philosophy", "is_correct": false},
        {"id": "B", "text": "Modernity and the industrial transformation of society", "is_correct": true},
        {"id": "C", "text": "Medieval scholastic theology", "is_correct": false},
        {"id": "D", "text": "Post-industrial digital culture", "is_correct": false}
      ],
      "correct_option_id": "B",
      "correct_answer": "Modernity and the industrial transformation of society",
      "explanation": ""
    }
  ],
  "liveCoding": []
}
```

Import it with the standard command:

```bash
docker compose run --rm backend python manage.py import_questions
```

Expected result for Sociology:

- subject name: `Sociology`;
- theory questions: `67`;
- live coding tasks: `0`;
- every question has exactly four answer variants and exactly one correct answer;
- topics are created from `topic` + `subtopic`;
- `is_correct` should be a JSON boolean; string values such as `"true"`/`"false"` are normalized defensively;
- repeated imports update existing JSON questions by stable id/hash instead of creating duplicates.

## Topics

JSON imports create typed topics:

- `theory` topics for multiple-choice questions;
- `live_coding` topics for live coding tasks.

The frontend can practice the full subject or selected topics. Existing PDF questions keep working without topics, so Machine Learning remains compatible.

## Scoring

Points are awarded by `backend/apps/exams/services.py`:

- first correct answer for a question: `+10`;
- repeated correct answer on a hard or previously missed question: up to `+3`;
- wrong answer: `-2`;
- streak bonuses at meaningful streak milestones;
- positive points per user/question are capped, so one question cannot be farmed forever.

Wrong answers can reduce score repeatedly. Positive score farming is limited by `QUESTION_POINT_CAP`, and leaderboard rows only include users who have answered at least one question.

Live coding scoring is separate but contributes to the same subject points:

- `90-100%` similarity: up to `+15` first time, less on repeats;
- `75-89%`: up to `+8` first time, less on repeats;
- `50-74%`: `+3`;
- below `50%`: `-1`;
- positive points per live coding task are capped by `LIVE_CODING_POINT_CAP`.

The checker does not execute submitted code. It normalizes commands/code and combines text similarity, token overlap, and Java/Spring keyword or annotation matching.
Each live coding session accepts one submitted attempt per task. To retry the same task, start another live coding session; positive points remain capped per user/task.

## Question Selection

The selector is weighted, not plain random:

- unseen questions get high weight;
- questions with wrong answers and low personal winrate get higher weight;
- mastered questions and repeatedly correct questions get lower weight;
- older questions slowly regain weight;
- modes constrain the pool first, then apply weights where appropriate.
- optional `topic_ids` constrain the pool before mode logic and weighting.

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
    "question_count": "10",
    "topic_ids": [3, 4]
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
- `GET /api/progress/live-coding/mistakes/`
- `POST /api/progress/questions/:id/mark-mastered/`

Topics:

- `GET /api/subjects/:id/topics/`

Live coding:

- `GET /api/live-coding/tasks/?subject=<id>&topic=<id>&status=all`
- `POST /api/live-coding/start/`

  ```json
  {
    "subject_id": 2,
    "mode": "random",
    "task_count": "10",
    "topic_ids": [8]
  }
  ```

- `GET /api/live-coding/:id/`
- `POST /api/live-coding/:id/submit/`

  ```json
  {
    "task_id": 10,
    "submitted_code": "docker --version",
    "time_spent": 120
  }
  ```

- `GET /api/live-coding/:id/result/`

Leaderboard:

- `GET /api/leaderboard/`
- `GET /api/leaderboard/?subject=<id>`
- `GET /api/leaderboard/?type=theory`
- `GET /api/leaderboard/?type=live_coding`

Import:

- `POST /api/admin/import-questions/` admin only
- `GET /api/admin/import-status/`

## Backend Tests

```bash
docker compose run --rm backend python manage.py test
```

Covered areas:

- tagged question parsing;
- JSON import for theory questions, topics, answer variants, and live coding tasks;
- duplicate-stable hashing;
- duplicate-safe import across multiple PDF files and repeated runs;
- weighted question selection modes;
- topic-filtered question selection;
- no fallback for empty `new` pools;
- per-question point cap;
- progress and subject stats updates after answers.
- live coding similarity, solved threshold, progress updates, and point cap;
- duplicate live coding submissions inside one session are rejected;
- API edge cases for invalid test size, empty subjects, duplicate answers, topics, live coding, mistakes, and leaderboard filtering.

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
- Optional sandboxed code execution for selected live coding languages.
- Per-subject achievements and weekly leagues.
- Email/password reset flow.
- Full OpenAPI schema and generated frontend API types.
