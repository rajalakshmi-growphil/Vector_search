import pandas as pd
import json
import mysql.connector
from sentence_transformers import SentenceTransformer

import os

# DB Configuration from environment variables
DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': os.environ.get('DB_NAME')
}

def embed_and_store():
    # 1. Load Data
    print("Loading products.csv...")
    df = pd.read_csv('products.csv')
    
    # 2. Load Model
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    # 3. Generate Embeddings
    print("Generating embeddings for 500 products...")
    names = df['product_name'].tolist()
    embeddings = model.encode(names).tolist() # Convert to list for JSON storage
    
    # 4. Connect to MySQL
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 5. Insert into Database
        sql = "REPLACE INTO products_vectors (product_id, product_name, vector) VALUES (%s, %s, %s)"
        
        data_to_insert = []
        for idx, row in df.iterrows():
            product_id = int(row['product_id'])
            product_name = row['product_name']
            vector_json = json.dumps(embeddings[idx])
            data_to_insert.append((product_id, product_name, vector_json))
            
        print(f"Inserting {len(data_to_insert)} products into MySQL...")
        cursor.executemany(sql, data_to_insert)
        conn.commit()
        
        print("Successfully stored products and vectors in MySQL.")
        
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    embed_and_store()
