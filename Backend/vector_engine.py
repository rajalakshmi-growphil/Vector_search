import os
import json
import numpy as np
import faiss

class VectorSearchEngine:
    def __init__(self):
        self.model = None
        self.index = None
        self.product_ids = []

    def get_sentence_transformer_model(self):
        # Try dynamic local cache path first to bypass network timeouts
        user_home = os.path.expanduser('~')
        cache_dir = os.path.join(user_home, '.cache', 'huggingface', 'hub', 'models--sentence-transformers--all-MiniLM-L6-v2', 'snapshots')
        
        from sentence_transformers import SentenceTransformer
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

    def load(self):
        print("Loading sentence-transformers model...")
        try:
            if "HF_ENDPOINT" not in os.environ:
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

            self.model = self.get_sentence_transformer_model()
            print("SentenceTransformer model loaded.")
        except Exception as e:
            print(f"Error loading SentenceTransformer: {e}")
            return

        index_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'products.index'))
        mapping_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'products_mapping.json'))

        if not os.path.exists(index_path) or not os.path.exists(mapping_path):
            print("Warning: FAISS index or product mapping file not found. Please run build_faiss_index.py first.")
            return

        print("Loading FAISS index and product ID mapping...")
        try:
            self.index = faiss.read_index(index_path)
            with open(mapping_path, 'r', encoding='utf-8') as f:
                self.product_ids = json.load(f)
            print(f"FAISS index loaded successfully with {len(self.product_ids)} items.")
        except Exception as e:
            print(f"Error loading FAISS index: {e}")

    def search(self, query, top_k=10):
        if self.model is None or self.index is None or not self.product_ids:
            print("VectorSearchEngine is not fully loaded.")
            return []

        # Generate query vector
        query_vector = self.model.encode(query, convert_to_numpy=True).reshape(1, -1)
        
        # Normalize the query vector for cosine similarity
        norm = np.linalg.norm(query_vector)
        if norm > 0:
            query_vector = query_vector / norm

        # Search the index
        scores, indices = self.index.search(query_vector.astype(np.float32), top_k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self.product_ids):
                continue
            
            pid = self.product_ids[idx]
            results.append({
                "product_id": int(pid),
                "score": float(score)
            })
        return results

