import os
import re
import json
import pandas as pd
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import mysql.connector
from urllib.parse import urlparse

load_dotenv()

print("Loading model library...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model library loaded.")

SQL_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Products.sql'))

def parse_sql_insert_values(values_block):
    rows = []
    current_row = []
    in_string = False
    string_char = None
    escaped = False
    in_paren = False
    current_val = []

    i = 0
    n = len(values_block)
    while i < n:
        char = values_block[i]

        if escaped:
            current_val.append(char)
            escaped = False
            i += 1
            continue

        if char == '\\':
            current_val.append(char)
            escaped = True
            i += 1
            continue

        if in_string:
            if char == string_char:
                if i + 1 < n and values_block[i + 1] == string_char:
                    current_val.append(string_char)
                    i += 2
                    continue
                else:
                    in_string = False
                    string_char = None
            else:
                current_val.append(char)
            i += 1
            continue

        if char in ("'", '"'):
            in_string = True
            string_char = char
            i += 1
            continue

        if char == '(':
            if not in_paren:
                in_paren = True
                current_row = []
                current_val = []
            else:
                current_val.append(char)
            i += 1
            continue

        if char == ')':
            if in_paren:
                val_str = "".join(current_val).strip()
                current_row.append(val_str)
                rows.append(current_row)
                in_paren = False
                current_val = []
            i += 1
            continue

        if char == ',':
            if in_paren:
                val_str = "".join(current_val).strip()
                current_row.append(val_str)
                current_val = []
            i += 1
            continue

        if in_paren:
            current_val.append(char)
        
        i += 1

    final_rows = []
    for r in rows:
        cleaned_row = []
        for val in r:
            val_upper = val.upper()
            if val_upper == 'NULL' or val == '':
                cleaned_row.append(None)
            else:
                try:
                    if '.' in val:
                        cleaned_row.append(float(val))
                    else:
                        cleaned_row.append(int(val))
                except ValueError:
                    cleaned_row.append(val)
        final_rows.append(cleaned_row)
    
    return final_rows

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set in environment variables.")
        return

    try:
        parsed = urlparse(db_url)
        db_name = parsed.path[1:] if parsed.path else ""
        username = parsed.username or "root"
        password = parsed.password or ""
        host = parsed.hostname or "localhost"
        if host == "localhost":
            host = "127.0.0.1"
        port = parsed.port or 3306

        print(f"Pre-checking MySQL connection to {host}:{port}...")
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

        print("MySQL database pre-check successful.")
    except Exception as e:
        print(f"Database connection pre-check failed: {e}")
        return

    print(f"Reading {SQL_FILE}...")
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Finding data blocks...")
    insert_pattern = re.compile(r"INSERT INTO `Products`.*?VALUES\s*(.*?);", re.DOTALL | re.IGNORECASE)
    
    parsed_data = []
    for match in insert_pattern.finditer(content):
        values_block = match.group(1).strip()
        
        rows = parse_sql_insert_values(values_block)
        for vals in rows:
            if len(vals) >= 14:
                product_id = vals[0]
                name = vals[2]
                photo_json = vals[13]
                
                image_name = None
                if photo_json:
                    try:
                        photo_list = json.loads(photo_json)
                        if isinstance(photo_list, list) and len(photo_list) > 0:
                            image_name = photo_list[0].get('img')
                    except:
                        pass
                
                parsed_data.append({
                    'product_id': product_id,
                    'product_name': name,
                    'image_name': image_name
                })
        
        print(f"Total extracted so far: {len(parsed_data)}")

    if not parsed_data:
        print("No data found!")
        return

    print(f"Generating embeddings for {len(parsed_data)} products...")
    df = pd.DataFrame(parsed_data)
    df['product_name'] = df['product_name'].fillna('').astype(str)
    names = df['product_name'].tolist()
    embeddings = model.encode(names, show_progress_bar=True).tolist()
    
    print("Storing in database...")
    try:
        temp_data = []
        for idx, row in df.iterrows():
            temp_data.append({
                'product_id': int(row['product_id']),
                'product_name': row['product_name'],
                'vector': embeddings[idx],
                'image_name': row['image_name']
            })
            
        json_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'temp_embeddings.json'))
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(temp_data, f)
            
        print("Embeddings saved to temporary file. Launching database insertion subprocess...")
        
        import subprocess
        result = subprocess.run(['python', 'insert_to_mysql.py'], capture_output=False)
        
        if os.path.exists(json_path):
            os.remove(json_path)
            
        if result.returncode == 0:
            print("Successfully populated product vectors in MySQL database.")
        else:
            print(f"Error: insert_to_mysql.py failed with exit code {result.returncode}")
    except Exception as e:
        print(f"Error during storing process: {e}")

if __name__ == "__main__":
    main()
