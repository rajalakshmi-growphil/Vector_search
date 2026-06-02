import os
import json
import sqlite3
import numpy as np

class VectorSearchEngine:
    def __init__(self, db_path='vector_search.db'):
        self.db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_path))
        self.model = None
        self.product_ids = []
        self.embeddings = None
        self.product_names = []
        self.image_names = []

    def load(self):
        if not os.path.exists(self.db_path):
            print(f"Warning: Vector database {self.db_path} not found. Please run embed_products.py first.")
            return

        print("Loading sentence-transformers model...")
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            print("SentenceTransformer model loaded.")
        except ImportError:
            print("Error: sentence-transformers is not installed. Vector search will be unavailable.")
            return

        print("Loading vector database into memory...")
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT product_id, product_name, vector, image_name FROM products_vectors")
            rows = cursor.fetchall()
            conn.close()
        except Exception as e:
            print(f"Error reading vector database: {e}")
            return

        if not rows:
            print("Warning: No product vectors found in database.")
            return

        self.product_ids = []
        self.product_names = []
        self.image_names = []
        vectors = []

        for row in rows:
            pid, name, vec_str, img_name = row
            self.product_ids.append(pid)
            self.product_names.append(name)
            self.image_names.append(img_name)
            vectors.append(json.loads(vec_str))

        self.embeddings = np.array(vectors, dtype=np.float32)
        # Normalize embeddings for cosine similarity via dot product
        norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.embeddings = self.embeddings / norms
        print(f"Vector search engine loaded successfully with {len(self.product_ids)} items.")

    def search(self, query, top_k=10):
        if self.model is None or self.embeddings is None:
            print("VectorSearchEngine is not fully loaded.")
            return []

        query_vector = self.model.encode(query, convert_to_numpy=True)
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        # Compute cosine similarity (dot product of normalized vectors)
        similarities = np.dot(self.embeddings, query_vector)
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                "product_id": int(self.product_ids[idx]),
                "product_name": self.product_names[idx],
                "score": float(similarities[idx]),
                "image_name": self.image_names[idx]
            })
        return results
