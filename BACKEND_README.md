Prayer App — Backend (FastAPI)

Overview
--------
This folder contains the FastAPI backend for Prayer App.

Prerequisites
-------------
- Python 3.10+
- A PostgreSQL database (Supabase)
- Firebase service account JSON and configured FIREBASE_CREDENTIALS_PATH

Quick start
-----------
1. Create a virtual environment and install dependencies:

   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt

2. Copy and set environment variables in .env (DATABASE_URL, JWT_SECRET, FIREBASE_CREDENTIALS_PATH).

3. Run database migrations (alembic):

   alembic upgrade head

4. Run a quick DB connection check:

   python -m app.check_db

5. Start the development server:

   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Notes
-----
- The repository currently uses synchronous SQLAlchemy (create_engine + sessionmaker).
- Alembic migrations are already present under alembic/versions.
- LiveKit, Firebase, Supabase credentials should be supplied via environment variables for production.
