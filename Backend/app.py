from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json

from models import db, Product
from vector_engine import VectorSearchEngine

app = Flask(__name__, static_folder='static', static_url_path='/')
CORS(app)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'medingen'

# app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+mysqlconnector://{app.config['MYSQL_USER']}:{app.config['MYSQL_PASSWORD']}@{app.config['MYSQL_HOST']}/{app.config['MYSQL_DB']}"
# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)

vector_engine = VectorSearchEngine()

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/search', methods=['GET'])
def search_products():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    # Typo correction: Map spelling variations of paracetamol to the correct term
    q_lower = query.lower()
    search_query = query
    
    # Matches "parac", "paracit", "paracitamol", "paracitmol", "paracet", "paraceta", etc.
    if "parac" in q_lower or "paracet" in q_lower or "paracit" in q_lower:
        search_query = "PARACETAMOL"

    try:
        # Increase top_k to 150 to get a wide enough candidate pool for hybrid ranking
        vector_results = vector_engine.search(search_query, top_k=150)
    except Exception as e:
        print(f"Error during search: {e}")
        vector_results = []

    # If vector search has no results, fall back to SQL LIKE query
    if not vector_results:
        db_products = Product.query.filter(
            (Product.name.like(f"%{search_query}%")) |
            (Product.salt_name.like(f"%{search_query}%")) |
            (Product.composition.like(f"%{search_query}%"))
        ).limit(50).all()
        
        results = []
        for idx, p in enumerate(db_products):
            name_lower = p.name.lower() if p.name else ""
            salt_lower = p.salt_name.lower() if p.salt_name else ""
            comp_lower = p.composition.lower() if p.composition else ""
            sq_lower = search_query.lower()
            oq_lower = query.lower()
            
            # Determine display score for LIKE fallback
            if name_lower.startswith(sq_lower) or name_lower.startswith(oq_lower):
                display_score = 1.0
            elif sq_lower in name_lower or oq_lower in name_lower:
                display_score = 0.99
            elif sq_lower in salt_lower or oq_lower in salt_lower:
                display_score = 0.99
            elif sq_lower in comp_lower or oq_lower in comp_lower:
                display_score = 0.88
            else:
                display_score = 0.50
                
            results.append({
                "product_id": p.id,
                "product_name": p.name,
                "salt_name": p.salt_name,
                "composition": p.composition,
                "image": p.image,
                "product_url": p.product_url,
                "product_pricing_new": float(p.product_pricing_new) if p.product_pricing_new is not None else None,
                "score": display_score
            })
        return jsonify(results)

    product_ids = [r['product_id'] for r in vector_results]
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    product_map = {p.id: p for p in products}

    ranked_candidates = []
    for r in vector_results:
        p_id = r['product_id']
        p = product_map.get(p_id)
        if p:
            name_lower = p.name.lower() if p.name else ""
            salt_lower = p.salt_name.lower() if p.salt_name else ""
            comp_lower = p.composition.lower() if p.composition else ""
            sq_lower = search_query.lower()
            oq_lower = query.lower()
            
            boost = 0
            display_score = 0.20
            
            # 1. Product name starts with fully corrected search term (highest priority)
            if name_lower.startswith(sq_lower):
                boost = 110
                display_score = 1.0
            # 2. Product name starts with original query
            elif name_lower.startswith(oq_lower):
                boost = 100
                display_score = 1.0
            # 3. Product name contains fully corrected search term
            elif sq_lower in name_lower:
                boost = 90
                display_score = 0.99
            # 4. Product name contains original query
            elif oq_lower in name_lower:
                boost = 80
                display_score = 0.99
            # 5. Salt name contains corrected search term or original query
            elif sq_lower in salt_lower or oq_lower in salt_lower:
                boost = 60
                display_score = 0.99
            # 6. Composition contains corrected search term or original query
            elif sq_lower in comp_lower or oq_lower in comp_lower:
                boost = 40
                display_score = 0.88
            # 7. Pure semantic match
            else:
                v_score = r['score']
                if v_score >= 0.45:
                    boost = 20
                    display_score = 0.88
                elif v_score >= 0.30:
                    boost = 10
                    display_score = 0.50
                else:
                    boost = 0
                    display_score = 0.20

            ranked_candidates.append((boost, r['score'], {
                "product_id": p.id,
                "product_name": p.name,
                "salt_name": p.salt_name,
                "composition": p.composition,
                "image": p.image,
                "product_url": p.product_url,
                "product_pricing_new": float(p.product_pricing_new) if p.product_pricing_new is not None else None,
                "score": display_score
            }))
        else:
            # Handle mapping placeholder if DB query fails to return it
            display_score = 0.20
            v_score = r['score']
            if v_score >= 0.45:
                display_score = 0.88
            elif v_score >= 0.30:
                display_score = 0.50
            
            ranked_candidates.append((0, r['score'], {
                "product_id": p_id,
                "product_name": f"Product #{p_id}",
                "salt_name": None,
                "composition": None,
                "image": None,
                "product_url": None,
                "product_pricing_new": 0.0,
                "score": display_score
            }))
            
    # Sort candidates by boost descending, then raw vector score descending
    ranked_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    # Extract only the result dicts
    sorted_results = [item[2] for item in ranked_candidates]
    
    # Return top 50 results (more matches so frontend columns can display full results)
    return jsonify(sorted_results[:50])

if __name__ == '__main__':
    # Initialize Vector Search Engine on startup
    try:
        with app.app_context():
            vector_engine.load()
    except Exception as e:
        print(f"Error loading vector search engine: {e}")
        
    # Trigger reload to load fresh FAISS index
    app.run(debug=True)
