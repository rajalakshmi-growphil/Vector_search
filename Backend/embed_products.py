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

def parse_sql_values(row_str):
    # Standard splitting by comma is risky, let's use a regex-based parser
    # Match strings: '...' or numbers or NULL
    # This pattern matches balanced parentheses for rows better
    # But for values inside a row, we can use:
    pattern = re.compile(r"('(?:''|[^'])*'|NULL|[^,]+)")
    matches = pattern.findall(row_str)
    
    final_values = []
    for m in matches:
        m = m.strip()
        if m.upper() == 'NULL':
            final_values.append(None)
        elif m.startswith("'") and m.endswith("'"):
            val = m[1:-1].replace("''", "'").replace("\\'", "'")
            final_values.append(val)
        else:
            try:
                if '.' in m:
                    final_values.append(float(m))
                else:
                    final_values.append(int(m))
            except ValueError:
                final_values.append(m)
    return final_values

def main():
    print(f"Reading {SQL_FILE}...")
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Finding data blocks...")
    # Find all INSERT INTO `Products` ... VALUES ( ... );
    # Note: dumps can have multiple INSERT statements
    insert_pattern = re.compile(r"INSERT INTO `Products`.*?VALUES\s*(.*?);", re.DOTALL | re.IGNORECASE)
    
    parsed_data = []
    for match in insert_pattern.finditer(content):
        values_block = match.group(1).strip()
        # values_block is (val1, val2, ...), (val1, val2, ...)
        
        # Split by "), ("
        # To avoid splitting on "), (" inside strings, we use a more careful approach
        # But for now, let's try a simple regex split for speed if the data is clean
        rows = re.split(r"\s*,\s*\n\s*\(", "(" + values_block) # Add leading ( for consistency
        # Wait, the split is tricky.
        
        # Let's find every ( ... ) that is NOT followed by a word (to avoid matching something else)
        # Actually, standard dumps have one row per line usually.
        
        row_pattern = re.compile(r"\((.*?)\)(?:,|\s*;)", re.DOTALL)
        for row_match in row_pattern.finditer(values_block):
            row_str = row_match.group(1)
            vals = parse_sql_values(row_str)
            
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
