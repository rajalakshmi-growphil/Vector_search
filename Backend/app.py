from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
import mysql.connector
from vector_engine import VectorSearchEngine
from spelling import SpellingCorrector

app = Flask(__name__, static_folder='static', static_url_path='/')
CORS(app)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'medingen'

vector_engine = VectorSearchEngine()

def get_db_connection():
    return mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB']
    )

spelling_corrector = SpellingCorrector(get_db_connection)

def format_product_row(row):
    photo_str = row.get('photo')
    image_file = None
    if photo_str:
        try:
            photo_list = json.loads(photo_str)
            if isinstance(photo_list, list) and len(photo_list) > 0:
                image_file = photo_list[0].get('img')
        except Exception:
            pass
            
    return {
        "id": row.get('product_id'),
        "name": row.get('name'),
        "salt_name": row.get('salt_name'),
        "composition": row.get('composition'),
        "image": image_file,
        "product_url": row.get('product_name_url'),
        "product_pricing_new": float(row.get('product_pricing_new')) if row.get('product_pricing_new') is not None else None
    }

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/search', methods=['GET'])
def search_products():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    original_query = query
    oq_lower = query.lower()
    
    try:
        corrected_query = spelling_corrector.correct(query)
    except Exception as e:
        print(f"Spelling correction failed: {e}")
        corrected_query = query
        
    search_query = corrected_query
    sq_lower = corrected_query.lower()

    try:
        vector_results = vector_engine.search(search_query, top_k=150)
    except Exception as e:
        print(f"Error during vector search: {e}")
        vector_results = []

    candidate_scores = {r['product_id']: r['score'] for r in vector_results}

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT product_id 
            FROM products 
            WHERE name LIKE %s OR salt_name LIKE %s 
            LIMIT 100
        """, (f"%{search_query}%", f"%{search_query}%"))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for row in rows:
            pid = row['product_id']
            if pid not in candidate_scores:
                # Add exact text matches to candidates with a baseline vector score
                candidate_scores[pid] = 0.1
    except Exception as e:
        print(f"Database error during LIKE candidate retrieval: {e}")

    product_ids = list(candidate_scores.keys())

    # 3. Retrieve database details for all merged candidates
    try:
        if not product_ids:
            product_map = {}
        else:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            format_strings = ','.join(['%s'] * len(product_ids))
            cursor.execute(f"""
                SELECT product_id, name, salt_name, composition, photo, product_name_url, product_pricing_new 
                FROM products 
                WHERE product_id IN ({format_strings})
            """, tuple(product_ids))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            product_map = {row['product_id']: format_product_row(row) for row in rows}
    except Exception as e:
        print(f"Database error during product batch retrieval: {e}")
        product_map = {}

    # 4. Score, rank, and sort candidates
    ranked_candidates = []
    for p_id in product_ids:
        p = product_map.get(p_id)
        v_score = candidate_scores[p_id]
        if p:
            name_lower = p['name'].lower() if p['name'] else ""
            salt_lower = p['salt_name'].lower() if p['salt_name'] else ""
            comp_lower = p['composition'].lower() if p['composition'] else ""
            
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
                if v_score >= 0.45:
                    boost = 20
                    display_score = 0.88
                elif v_score >= 0.30:
                  boost = 10
                  display_score = 0.50
                else:
                    boost = 0
                    display_score = 0.20

            ranked_candidates.append((boost, v_score, {
                "product_id": p['id'],
                "product_name": p['name'],
                "salt_name": p['salt_name'],
                "composition": p['composition'],
                "image": p['image'],
                "product_url": p['product_url'],
                "product_pricing_new": p['product_pricing_new'],
                "score": display_score
            }))
        else:
            # Handle placeholder mapping if product not found in database details
            display_score = 0.20
            if v_score >= 0.45:
                display_score = 0.88
            elif v_score >= 0.30:
                display_score = 0.50
            
            ranked_candidates.append((0, v_score, {
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
    
    # Return top 50 results
    return jsonify(sorted_results[:50])

if __name__ == '__main__':
    # Initialize Vector Search Engine and Spelling Corrector on startup
    try:
        vector_engine.load()
    except Exception as e:
        print(f"Error loading vector search engine: {e}")
        
    try:
        spelling_corrector.load()
    except Exception as e:
        print(f"Error loading spelling corrector: {e}")
        
    # Trigger reload to load fresh FAISS index
    app.run(debug=True, use_reloader=False)
