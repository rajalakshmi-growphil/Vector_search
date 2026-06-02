from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
import re

from models import db, Product
from config import Config
from vector_engine import VectorSearchEngine

app = Flask(__name__, static_folder='static', static_url_path='/')
app.config.from_object(Config)
CORS(app)
db.init_app(app)

vector_engine = VectorSearchEngine()

# PRODUCT ENDPOINTS

@app.route('/')
def home():
    return app.send_static_file('index.html')


@app.route('/search', methods=['GET'])
def search_products():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    # Perform vector search
    try:
        vector_results = vector_engine.search(query, top_k=12)
    except Exception as e:
        print(f"Vector search failed: {e}")
        vector_results = []

    if not vector_results:
        # Fallback to plain SQL search if vector search is unavailable/empty
        db_products = Product.query.filter(Product.name.like(f"%{query}%")).limit(12).all()
        return jsonify([
            {
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "price": p.price,
                "rating": p.rating,
                "image_url": p.image_url,
                "description": p.description,
                "score": 1.0  # mock score for keyword match
            } for p in db_products
        ])

    # Fetch full product details from the main database
    product_ids = [r['product_id'] for r in vector_results]
    products = Product.query.filter(Product.id.in_(product_ids)).all()
    product_map = {p.id: p for p in products}

    results = []
    for r in vector_results:
        p_id = r['product_id']
        p = product_map.get(p_id)
        if p:
            results.append({
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "price": p.price,
                "rating": p.rating,
                "image_url": p.image_url,
                "description": p.description,
                "score": r['score']
            })
        else:
            # Fallback to vector data if not found in Product table
            results.append({
                "id": p_id,
                "name": r['product_name'],
                "brand": "Medingen",
                "price": 0.0,
                "rating": 4.5,
                "image_url": r['image_name'],
                "description": "",
                "score": r['score']
            })
    return jsonify(results)


def seed_database_from_sql():
    # Check if we already have products
    if Product.query.first() is not None:
        print("Database already seeded with products.")
        return

    sql_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Products.sql'))
    if not os.path.exists(sql_file_path):
        print(f"Warning: {sql_file_path} not found. Cannot seed database.")
        return

    print("Seeding database from Products.sql... (this might take a few moments)")
    with open(sql_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Use the robust parser
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

    insert_pattern = re.compile(r"INSERT INTO `Products`.*?VALUES\s*(.*?);", re.DOTALL | re.IGNORECASE)
    products_to_insert = []
    seen_ids = set()

    for match in insert_pattern.finditer(content):
        values_block = match.group(1).strip()
        rows = parse_sql_insert_values(values_block)
        for vals in rows:
            if len(vals) >= 24:
                product_id = vals[0]
                if not product_id or product_id in seen_ids:
                    continue
                seen_ids.add(product_id)

                name = vals[2]
                if not name:
                    continue
                brand = vals[5]
                photo_json = vals[13]
                price = vals[23] if len(vals) > 23 else 0.0
                description = vals[21] if len(vals) > 21 else (vals[10] if len(vals) > 10 else "")

                # Extract first image from photo JSON
                image_url = None
                if photo_json:
                    try:
                        photo_list = json.loads(photo_json)
                        if isinstance(photo_list, list) and len(photo_list) > 0:
                            image_url = photo_list[0].get('img')
                    except:
                        pass

                products_to_insert.append({
                    "id": product_id,
                    "name": name,
                    "brand": brand,
                    "image_url": image_url,
                    "price": price,
                    "rating": 4.5,
                    "description": description
                })

    if products_to_insert:
        print(f"Inserting {len(products_to_insert)} products into database...")
        db.session.bulk_insert_mappings(Product, products_to_insert)
        db.session.commit()
        print("Database seeding completed successfully.")
    else:
        print("No products parsed from SQL file.")


if __name__ == '__main__':
    with app.app_context():
        # Drop unwanted tables if they exist
        try:
            db.session.execute(db.text("DROP TABLE IF EXISTS product_descriptions;"))
            db.session.execute(db.text("DROP TABLE IF EXISTS reviews;"))
            db.session.execute(db.text("DROP TABLE IF EXISTS salt_contents;"))
            db.session.commit()
            print("Successfully cleaned up unused tables (product_descriptions, reviews, salt_contents) from database.")
        except Exception as e:
            print(f"Error dropping unused tables: {e}")

        db.create_all()
        try:
            seed_database_from_sql()
        except Exception as e:
            print(f"Error seeding database: {e}")
    
    # Load the vector search engine
    try:
        vector_engine.load()
    except Exception as e:
        print(f"Error loading vector search engine: {e}")
        
    app.run(debug=True)
