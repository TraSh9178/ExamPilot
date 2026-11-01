# ExamPilot

Turn course materials into focused exam practice.

ExamPilot is a Streamlit learning platform that combines document extraction, AI-assisted course preparation, practice exams, progress tracking, and an interactive knowledge map.

Built for HackRU Fall 2026.

## Screenshots

| Dashboard | Study Plan |
|---|---|
| ![Dashboard with the three demo courses](docs/screenshots/dashboard.png) | ![Study Plan with the exam scope confirmed](docs/screenshots/study_plan.png) |

| Practice result | Knowledge Map |
|---|---|
| ![Graded mock exam with explanations](docs/screenshots/practice_result.png) | ![Knowledge map with mastery colours](docs/screenshots/knowledge_map.png) |

## Features

- **Course materials:** Extract text from UTF-8 TXT, text-based PDF and PPTX, and PNG/JPG/JPEG images.
- **AI-assisted preparation:** Generate candidate topics and multiple-choice questions with Claude, then confirm the topics to practise.
- **Practice:** Take Mock Exams or Topic Practice sessions with scoring, answer review, and explanations.
- **Progress:** Track results and topic mastery separately for each course and practice mode.
- **Knowledge Map:** Explore topic relationships, inspect topic details, view mastery colours, and ask Claude to suggest connections from your saved material (applied only after you review them).
- **Anki export:** Preview cards and download all questions or questions from weak/developing topics as UTF-8 TSV.
- **Accounts and persistence:** Register, log in, and save or restore courses and graded practice records through PostgreSQL.
- **Pilot assistant:** Ask course-related questions through a draggable floating assistant.

AI-generated topics, questions, answers, explanations, and relationships require human review.

## Demo Courses

Three built-in courses provide practice content without requiring AI generation:

| Course | Topics | Questions | Relationships |
|---|---:|---:|---:|
| Introduction to Microeconomics | 3 | 3 | 2 |
| Calculus I | 3 | 3 | 2 |
| Python Basics | 3 | 9 | 0 |

Demo content does not require a Claude API key. The normal application still requires a working account database to register or log in.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/TraSh9178/ExamPilot.git
cd ExamPilot
```

### 2. Create a virtual environment

Python 3.12 is recommended.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 3. Configure PostgreSQL

Create a local `.env` file using `.env.example` as a template:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
DATABASE_SSLMODE=require
```

Use a PostgreSQL database such as TigerData or Supabase PostgreSQL. Authentication and learning-record persistence must use the same database.

Accounts are managed by the application's server-side authentication service, not Supabase Auth.

Never commit database credentials or API keys. Local `.env` files and backups are ignored by Git; `.env.example` is a configuration template only.

### 4. Prepare the database

For a new database, an authorised maintainer must prepare the learning-data tables before initialising Auth.

The learning-data schema lives in numbered migration files:

```text
db/migrations/
```

Apply them in order. Each file is recorded in `exampilot_schema_migrations` with a checksum, so the command is safe to run again later to pick up new migrations:

```bash
python -m services.database_migrations
```

The same migrations can be applied from Python:

```python
from services.postgres_store import initialize_schema

result = initialize_schema()
```

After the learning-data schema is ready, initialise the account schema:

```bash
python -m services.auth_service
```

Auth uses:

```text
db/auth_schema_minimal.sql
```

The account table requires an existing, compatible `public.demo_users` table. Normal application startup does not automatically create database tables.

For a shared or existing database, have its maintainer verify the schema and permissions rather than running initialisation commands blindly.

See [account setup](docs/account_setup.md) for additional configuration details.

### 5. Start the application

```bash
python -m streamlit run app.py
```

Open the **Local URL** printed in the terminal, usually:

```text
http://localhost:8501
```

A localhost address is accessible only on the machine running the application. Sharing the application publicly requires a separate deployment.

## Deploying a public demo

The application runs unchanged on [Streamlit Community Cloud](https://streamlit.io/cloud):

1. Create a PostgreSQL database (for example a free Neon or Supabase project). Prepare it once from your own machine with the migration command and the Auth initialiser from step 4, using a local `.env` that points at that database.
2. In Streamlit Community Cloud, deploy this repository with `app.py` as the entry point and Python 3.12.
3. Add the secrets `DATABASE_URL` and `DATABASE_SSLMODE = "require"`. Streamlit exposes secrets as environment variables, which is how this application reads them.
4. Leave `ANTHROPIC_API_KEY` unset on a public demo. The Generate buttons are then disabled with an explanatory message and Pilot replies that it is not configured, while the built-in demo courses keep working and nobody can run up your Claude bill. Set the key only for a private deployment.

`packages.txt` installs Tesseract with English language data on the Cloud image, so image uploads can be extracted there.

Anyone can register on a public deployment, so point it at a database that holds no real data.

## Configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string for accounts and learning records |
| `DATABASE_SSLMODE` | TLS mode: `require`, `verify-ca`, or `verify-full` |
| `ANTHROPIC_API_KEY` | Claude API key; required for AI generation and Pilot answers |
| `ANTHROPIC_MODEL` | Optional model override; the code default is `claude-opus-5-5` |
| `OCR_LANG` | Tesseract language selection; defaults to `eng` |

The AI service reads configuration from the server process environment. Set its variables before starting Streamlit; do not assume that adding a key to `.env` alone configures every service.

AI calls use the official `anthropic` SDK with structured JSON output for topics, questions and connections, a 180-second timeout for generation, 60 seconds for Pilot answers, and no automatic retries. Choose a Claude model available to your account: the default Claude Opus 5.5 gives the best question quality; `claude-sonnet-5-5` or `claude-haiku-5-5` cost less.

### Image OCR

Image OCR requires the Tesseract system engine and the selected language data in addition to the Python dependencies.

On macOS with Homebrew:

```bash
brew install tesseract
tesseract --version
tesseract --list-langs
```

Confirm that `eng` is available for English OCR. Other platforms require their own Tesseract installation and PATH configuration.

See [document processing and Claude usage](docs/claude_usage.md) for supported formats, source structures, and error handling.

## Typical Workflow

1. Register or log in.
2. Open a built-in Demo or create a course from uploaded materials.
3. Extract and review the text.
4. Generate candidate topics when using your own materials.
5. Review the topics and explicitly confirm the exam scope.
6. Generate questions if needed, then start Mock Exam or Topic Practice.
7. Submit answers and review the score and explanations.
8. Inspect Progress and Knowledge Map.
9. Preview or download Anki cards for further review.

Pilot is available after login. It uses the selected course's topic summaries and relationships; open a course before asking a question.

## Data Persistence and Privacy

### Saved to PostgreSQL

- Course packages
- Exam sessions
- Submitted answer results

Database operations use the authenticated account's server-side user ID. Course records are scoped by account.

On login, the application discovers saved courses and restores their histories. Topic statistics and mastery are recalculated from the restored records.

Saving and restoring require a working database connection. A successful local grading operation does not guarantee that its database save succeeded; check the displayed save status.

### Kept in the current session

- Unsaved learning records
- Pilot conversations and input drafts
- Account avatars
- Uploaded document previews

Pilot conversations and avatars are not restored from PostgreSQL or synchronised across devices.

Signing out clears the current session. Saved learning records can be restored after signing in again; unsaved records do not have that guarantee.

### Restore conflicts

Database history is used for active statistics after a successful restore. Conflicting local records are kept separately in the current login session and excluded from those statistics.

Unresolved local conflicts require attention before logout. Do not treat session-only conflict records as durable backups.

### Account security

- Passwords are stored as salted scrypt hashes.
- Repeated failed logins temporarily lock the account.
- Account and learning-data queries are performed server-side.
- Database credentials and API keys must remain outside the repository.

## Practice and Mastery

Mock Exam and Topic Practice statistics are calculated separately.

| Status | Rule |
|---|---|
| Unattempted | No recorded answers |
| Insufficient evidence | Fewer than 3 recorded answers |
| Weak | At least 3 answers, accuracy below 60% |
| Developing | At least 3 answers, accuracy from 60% to below 80% |
| Mastered | At least 3 answers, accuracy of 80% or higher |

These labels summarise recorded practice performance; they are not a formal assessment of subject proficiency.

## Known Limitations

- AI-generated content may contain mistakes and must be reviewed.
- Question generation is currently disabled for courses with existing practice history.
- Deleting a course from the Dashboard removes it from the current session; it does not delete its saved database records.
- Scanned PDF OCR, legacy `.ppt`, PPTX image OCR, and slide notes are not supported.
- Document uploads are limited to 5 MiB and extracted text to 50,000 characters.
- Image OCR also has pixel and execution-time limits.
- OCR defaults to English. Other languages require appropriate language data and separate validation.
- Pilot requests are independent; previous chat messages are not sent as multi-turn conversation context.
- Anki export supports text import through TSV, not AnkiWeb synchronisation. Anki Desktop import has not been verified.
- The knowledge map loads its browser rendering library from an external CDN.
- A built-in Demo avoids AI generation, but the complete authenticated application is not a fully offline application.
- Password reset and email verification are not implemented.

## Project Structure

```text
app.py                       Application entry point and authentication guard
pages/                       Dashboard, study, practice, progress, graph, and Anki
services/                    AI, extraction, authentication, persistence, and engines
models/schemas.py            Shared Pydantic data models
components/                  Interactive knowledge-map components
assets/                      UI styles, illustrations, and Pilot frontend assets
data/                        Built-in Demo course packages
db/                          Learning-data and account SQL schemas
tests/                       Automated tests
docs/                        Setup guides, contracts, and development records
```

## Shared Data Contract

The source of truth is [`models/schemas.py`](models/schemas.py).

Core models include:

- `StudyPackage`
- `Topic`
- `Relationship`
- `Question`
- `ExamSession`
- `AttemptResult`
- `TopicStats`

Topic and question IDs must be unique within a course package. Questions and relationships must reference existing topics.

Schema validation checks structure and references; it does not establish factual correctness.

See [interface contract](docs/interface_contract.md) for module-level interfaces.

## Testing

With the virtual environment activated:

```bash
python -m pytest -q
```

Tests cover document extraction, AI service behaviour, authentication, persistence, exams, mastery, course state, UI flows, knowledge graphs, and Anki export.

Many automated tests use mock services or database connections. Passing them does not by itself prove real database, Claude, OCR, or browser behaviour.

Record the exact commit and environment when reporting real integration results.

## Contributors

- [Yingxuan Huang (@Zerune0)](https://github.com/Zerune0) — Streamlit frontend, multi-course workflows, practice and progress UI, Anki/OCR interface integration, and account Save/Restore UI.
- [Charles Chen (@k086-cloud)](https://github.com/k086-cloud) — AI integration (Gemini, later Claude), document parsing and OCR, account authentication, floating AI tutor, and UI refinements.
- [Zhengchang Quan (@mormal1016)](https://github.com/mormal1016) — Exam and mastery engines, PostgreSQL persistence, saved-course discovery, and database validation.
- [Jiale Li (@TraSh9178)](https://github.com/TraSh9178) — Shared data schema, knowledge graph, Anki export service, integration review, and release coordination.

## Documentation

- [Account and database setup](docs/account_setup.md)
- [Document processing and Claude usage](docs/claude_usage.md)
- [Interface contract](docs/interface_contract.md)
- [Testing on another computer](docs/other_computer_testing.md)
- [Floating Pilot assistant](docs/floating_tutor.md)
- [Shared UI typography](docs/ui_typography.md)

Some development documents describe earlier branch snapshots and their test results. Their historical status statements should not be treated as the current release status.