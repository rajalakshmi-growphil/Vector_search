import os

# Configure HF mirror first to avoid timeouts
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import json
import numpy as np
import mysql.connector
import faiss
from sentence_transformers import SentenceTransformer
from urllib.parse import urlparse

def get_sentence_transformer_model():
    # Try dynamic local cache path first to bypass network timeouts
    user_home = os.path.expanduser('~')
    cache_dir = os.path.join(user_home, '.cache', 'huggingface', 'hub', 'models--sentence-transformers--all-MiniLM-L6-v2', 'snapshots')
    
    if os.path.exists(cache_dir):
        try:
            snapshots = os.listdir(cache_dir)
            for snapshot in snapshots:
                local_model_path = os.path.join(cache_dir, snapshot)
                # Ensure the snapshot actually contains model weights
                if os.path.exists(os.path.join(local_model_path, "model.safetensors")) or os.path.exists(os.path.join(local_model_path, "pytorch_model.bin")):
                    print(f"Attempting to load model from local cache snapshot: {local_model_path}")
                    return SentenceTransformer(local_model_path)
        except Exception as e:
            print(f"Failed to load from local cache snapshot: {e}")
            
    # Fallback to default online download
    print("Falling back to downloading model 'all-MiniLM-L6-v2'...")
    return SentenceTransformer('all-MiniLM-L6-v2')

def main():
    db_url = "mysql+mysqlconnector://root:@127.0.0.1:3306/medingen"
    print("Connecting to local database...")
    try:
        parsed = urlparse(db_url)
        db_name = parsed.path[1:]
        username = parsed.username or "root"
        password = parsed.password or ""
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 3306

        conn = mysql.connector.connect(
            host=host,
            user=username,
            password=password,
            database=db_name,
            port=port
        )
        cursor = conn.cursor(dictionary=True)
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return
    
    print("Fetching products from database table...")
    try:
        cursor.execute("SELECT product_id, name, salt_name, composition FROM products WHERE name IS NOT NULL AND name != ''")
        products = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Error fetching data from products table: {e}")
        if 'conn' in locals() and conn.is_connected():
            conn.close()
        return

    print(f"Loaded {len(products)} products from database.")
    if not products:
        print("No products to index.")
        return

    print("Loading SentenceTransformer model...")
    try:
        model = get_sentence_transformer_model()
        print("SentenceTransformer model loaded successfully.")
    except Exception as e:
        print(f"Error loading SentenceTransformer: {e}")
        return

    product_ids = []
    texts_to_embed = []
    
    for p in products:
        product_ids.append(p['product_id'])
        
        # Combine name, salt_name, and composition for richer vector search representation
        parts = [p['name'], p['salt_name'], p['composition']]
        combined_text = " - ".join([str(part).strip() for part in parts if part and str(part).strip()])
        texts_to_embed.append(combined_text)

    print("Generating embeddings (this may take a few minutes)...")
    try:
        embeddings = model.encode(texts_to_embed, show_progress_bar=True)
    except Exception as e:
        print(f"Error encoding embeddings: {e}")
        return
    
    # Normalize vectors for cosine similarity search (using IndexFlatIP)
    print("Normalizing embeddings...")
    embeddings = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    print("Building FAISS IndexFlatIP...")
    try:
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)
    except Exception as e:
        print(f"Error building FAISS index: {e}")
        return

    index_path = os.path.join(os.path.dirname(__file__), 'products.index')
    mapping_path = os.path.join(os.path.dirname(__file__), 'products_mapping.json')

    print(f"Saving FAISS index to {index_path}...")
    try:
        faiss.write_index(index, index_path)
    except Exception as e:
        print(f"Error saving FAISS index: {e}")
        return

    print(f"Saving product mapping to {mapping_path}...")
    try:
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(product_ids, f)
    except Exception as e:
        print(f"Error saving product mapping: {e}")
        return

    print("FAISS indexing completed successfully!")

if __name__ == "__main__":
    main()
