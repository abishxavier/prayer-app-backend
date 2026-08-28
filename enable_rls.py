from app.db.session import SessionLocal
from sqlalchemy import text

def enable_rls_on_all_tables():
    db = SessionLocal()
    try:
        query = text("SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';")
        rows = db.execute(query).fetchall()
        
        print("Found tables in public schema:")
        for t, rls in rows:
            print(f" - {t} (RLS currently: {rls})")
        
        print("\nEnabling Row Level Security (RLS) on all public tables...")
        for t, _ in rows:
            db.execute(text(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY;'))
            print(f"  [OK] Enabled RLS on: {t}")
        
        db.commit()
        print("\nSuccess! All public tables now have Row Level Security enabled.")
        print("Unauthorized public API access is now completely blocked.")
    except Exception as e:
        db.rollback()
        print("Error enabling RLS:", e)
    finally:
        db.close()

if __name__ == "__main__":
    enable_rls_on_all_tables()
