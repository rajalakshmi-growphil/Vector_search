import os
import re
import json
import sqlite3
import pandas as pd
from sentence_transformers import SentenceTransformer

print("Loading model library...")
model = SentenceTransformer('all-MiniLM-L6-v2')
print("Model library loaded.")

DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'vector_search.db'))
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
                # Check for doubled single quotes (SQL escape style: '')
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
    print(f"Reading {SQL_FILE}...")
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Finding data blocks...")
    insert_pattern = re.compile(r"INSERT INTO `Products`.*?VALUES\s*(.*?);", re.DOTALL | re.IGNORECASE)
    
    parsed_data = []
    for match in insert_pattern.finditer(content):
        values_block = match.group(1).strip()
        
        # Use robust parser
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
    # Ensure all names are strings and handle empty/NaN names
    df['product_name'] = df['product_name'].fillna('').astype(str)
    names = df['product_name'].tolist()
    embeddings = model.encode(names, show_progress_bar=True).tolist()
    
    print("Storing in database...")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products_vectors (
                product_id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                vector TEXT NOT NULL,
                image_name TEXT
            )
        """)
        cursor.execute("DELETE FROM products_vectors")
        
        data_to_insert = []
        for idx, row in df.iterrows():
            product_id = int(row['product_id'])
            product_name = row['product_name']
            image_name = row['image_name']
            vector_json = json.dumps(embeddings[idx])
            data_to_insert.append((product_id, product_name, vector_json, image_name))
            
        cursor.executemany("INSERT INTO products_vectors VALUES (?, ?, ?, ?)", data_to_insert)
        conn.commit()
        print(f"Success! {len(data_to_insert)} products stored in {DB_FILE}.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
