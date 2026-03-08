from app.database import get_db

with get_db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='vehicle_logs' ORDER BY ordinal_position")
    columns = cur.fetchall()
    print("vehicle_logs columns:", [col[0] for col in columns])
    
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='weigh_bridge_data' ORDER BY ordinal_position")
    columns = cur.fetchall()
    print("weigh_bridge_data columns:", [col[0] for col in columns])
