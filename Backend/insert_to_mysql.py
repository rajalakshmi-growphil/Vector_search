import os
import json
import mysql.connector
from urllib.parse import urlparse
from dotenv import load_dotenv

def main():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set in environment variables.")
        return

    json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'temp_embeddings.json'))
    if not os.path.exists(json_path):
        print(f"Error: Temporary embeddings file {json_path} not found.")
        return

    print(f"Reading temporary embeddings from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data_to_insert = json.load(f)
    print(f"Loaded {len(data_to_insert)} items to insert.")

    try:
        parsed = urlparse(db_url)
        db_name = parsed.path[1:] if parsed.path else ""
        username = parsed.username or "root"
        password = parsed.password or ""
        host = parsed.hostname or "localhost"
        if host == "localhost":
            host = "127.0.0.1"
        port = parsed.port or 3306

        print(f"Connecting to MySQL server at {host}:{port}...")
        
        temp_conn = mysql.connector.connect(
            host=host,
            user=username,
            password=password,
            port=port
        )
        temp_cursor = temp_conn.cursor()
        temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
        temp_cursor.close()
        temp_conn.close()

        conn = mysql.connector.connect(
            host=host,
            user=username,
            password=password,
            database=db_name,
            port=port
        )
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS products_vectors")
        conn.commit()

        records = []
        for item in data_to_insert:
            records.append((
                json.dumps(item['vector']),
                int(item['product_id'])
            ))

        batch_size = 100
        print("Updating vector column in 'products' table...")
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            cursor.executemany(
                "UPDATE products SET vector = %s WHERE id = %s", 
                batch
            )
            conn.commit()
            print(f"Updated {min(i + batch_size, len(records))}/{len(records)} products...")

        print(f"Success! {len(records)} product vectors successfully stored in MySQL table 'products'.")

    except Exception as e:
        print(f"Error during MySQL insertion: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    main()
