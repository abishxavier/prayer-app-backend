from sqlalchemy import create_engine, text
from app.core.config import settings


def check_db_connection():
    """Simple DB connection check using the project's DATABASE_URL from .env.

    Run: python -m app.check_db
    """
    url = settings.database_url
    if not url:
        print("DATABASE_URL is not set in environment (.env).")
        return 1

    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("DB check OK, result:", result.scalar())
        return 0
    except Exception as exc:
        print("DB check failed:", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(check_db_connection())
