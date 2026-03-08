import psycopg2
from app.database import parse_database_url
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
DB_CONFIG = parse_database_url(DATABASE_URL)

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns 
                   WHERE table_name = 'weigh_bridge_data' 
                   ORDER BY ordinal_position;""")
    columns = cur.fetchall()
    print('weigh_bridge_data columns:')
    for col in columns:
        print(f'  {col[0]}: {col[1]}')
    
    # Also check for any weigh_bridges table
    cur.execute("""SELECT table_name FROM information_schema.tables 
                   WHERE table_name LIKE '%weigh%' AND table_schema = 'public';""")
    tables = cur.fetchall()
    print('\nTables with "weigh" in name:')
    for table in tables:
        print(f'  - {table[0]}')
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
