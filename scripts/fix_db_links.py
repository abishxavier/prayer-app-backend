import psycopg2

DATABASE_URL = "postgresql://postgres:Jesuseabish1828@db.xjomlcjxwgebqjqtgsgi.supabase.co:5432/postgres"

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM public.users LIMIT 1")
    user = cur.fetchone()
    if not user:
        print("No users found!")
        return
    user_id = user[0]
    print(f"Assigning items to user: {user_id} ({user[1]}, {user[2]})")
    
    cur.execute("UPDATE gallery_items SET uploaded_by = %s WHERE uploaded_by IS NULL", (user_id,))
    print(f"Gallery items updated: {cur.rowcount}")
    
    cur.execute("UPDATE scheduled_calls SET host_id = %s WHERE host_id IS NULL", (user_id,))
    print(f"Scheduled calls updated: {cur.rowcount}")
    
    conn.commit()
    conn.close()
    print("Database links fixed successfully!")

if __name__ == "__main__":
    main()
