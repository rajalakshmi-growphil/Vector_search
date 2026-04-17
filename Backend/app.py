from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
import jwt

from models import db, Product, SaltContent, Review, ProductDescription
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)
db.init_app(app)

# JWT AUTHENTICATION

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            parts = auth_header.split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]

        if not token:
            return jsonify({'error': 'Authorization header missing'}), 401

        try:
            data = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)
    return decorated


# LOGIN ENDPOINT

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    token = jwt.encode(
        {'user': username, 'exp': datetime.utcnow() + timedelta(hours=1)},
        Config.SECRET_KEY,
        algorithm='HS256'
    )

    return jsonify({'token': token})


# PRODUCT CRUD

@app.route('/products', methods=['GET'])
@token_required
def get_products():
    products = Product.query.all()
    result = [
        {
            "id": p.id,
            "name": p.name,
            "brand": p.brand,
            "price": p.price,
            "rating": p.rating,
            "image_url": p.image_url,
            "description": p.description
        }
        for p in products
    ]
    return jsonify(result)


@app.route('/products/<int:product_id>', methods=['GET'])
@token_required
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    result = {
        "id": product.id,
        "name": product.name,
        "brand": product.brand,
        "price": product.price,
        "rating": product.rating,
        "image_url": product.image_url,
        "description": product.description
    }
    return jsonify(result)


@app.route('/products', methods=['POST'])
@token_required
def add_product():
    data = request.get_json()
    new_product = Product(
        name=data.get('name'),
        brand=data.get('brand'),
        price=data.get('price'),
        rating=data.get('rating'),
        image_url=data.get('image_url'),
        description=data.get('description')
    )
    db.session.add(new_product)
    db.session.commit()
    return jsonify({'message': 'Product added successfully', 'id': new_product.id}), 201


@app.route('/products/<int:product_id>', methods=['PUT'])
@token_required
def update_product(product_id):
    product = Product.query.get_or_404(product_id)
    data = request.get_json()

    product.name = data.get('name', product.name)
    product.brand = data.get('brand', product.brand)
    product.price = data.get('price', product.price)
    product.rating = data.get('rating', product.rating)
    product.image_url = data.get('image_url', product.image_url)
    product.description = data.get('description', product.description)

    db.session.commit()
    return jsonify({'message': 'Product updated successfully'})


@app.route('/products/<int:product_id>', methods=['DELETE'])
@token_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted successfully'})


# SALT CONTENT CRUD

@app.route('/products/<int:product_id>/salts', methods=['GET'])
@token_required
def get_salts(product_id):
    salts = SaltContent.query.filter_by(product_id=product_id).all()
    result = [
        {"id": s.id, "salt_name": s.salt_name, "amount_mg": s.amount_mg, "notes": s.notes}
        for s in salts
    ]
    return jsonify(result)


@app.route('/products/<int:product_id>/salts/<int:salt_id>', methods=['GET'])
@token_required
def get_salt(product_id, salt_id):
    salt = SaltContent.query.filter_by(product_id=product_id, id=salt_id).first_or_404()
    result = {"id": salt.id, "salt_name": salt.salt_name, "amount_mg": salt.amount_mg, "notes": salt.notes}
    return jsonify(result)


@app.route('/products/<int:product_id>/salts', methods=['POST'])
@token_required
def add_salt(product_id):
    data = request.get_json()
    new_salt = SaltContent(
        product_id=product_id,
        salt_name=data.get('salt_name'),
        amount_mg=data.get('amount_mg'),
        notes=data.get('notes')
    )
    db.session.add(new_salt)
    db.session.commit()
    return jsonify({'message': 'Salt added successfully', 'id': new_salt.id}), 201


@app.route('/products/<int:product_id>/salts/<int:salt_id>', methods=['PUT'])
@token_required
def update_salt(product_id, salt_id):
    salt = SaltContent.query.filter_by(product_id=product_id, id=salt_id).first_or_404()
    data = request.get_json()

    salt.salt_name = data.get('salt_name', salt.salt_name)
    salt.amount_mg = data.get('amount_mg', salt.amount_mg)
    salt.notes = data.get('notes', salt.notes)

    db.session.commit()
    return jsonify({'message': 'Salt updated successfully'})


@app.route('/products/<int:product_id>/salts/<int:salt_id>', methods=['DELETE'])
@token_required
def delete_salt(product_id, salt_id):
    salt = SaltContent.query.filter_by(product_id=product_id, id=salt_id).first_or_404()
    db.session.delete(salt)
    db.session.commit()
    return jsonify({'message': 'Salt deleted successfully'})


# REVIEW CRUD

@app.route('/products/<int:product_id>/reviews', methods=['GET'])
@token_required
def get_reviews(product_id):
    reviews = Review.query.filter_by(product_id=product_id).all()
    result = [{"id": r.id, "rating": r.rating, "content": r.content} for r in reviews]
    return jsonify(result)


@app.route('/products/<int:product_id>/reviews/<int:review_id>', methods=['GET'])
@token_required
def get_review(product_id, review_id):
    review = Review.query.filter_by(product_id=product_id, id=review_id).first_or_404()
    result = {"id": review.id, "rating": review.rating, "content": review.content}
    return jsonify(result)


@app.route('/products/<int:product_id>/reviews', methods=['POST'])
@token_required
def add_review(product_id):
    data = request.get_json()
    new_review = Review(
        product_id=product_id,
        rating=data.get('rating'),
        content=data.get('content')
    )
    db.session.add(new_review)
    db.session.commit()
    return jsonify({'message': 'Review added successfully', 'id': new_review.id}), 201


@app.route('/products/<int:product_id>/reviews/<int:review_id>', methods=['PUT'])
@token_required
def update_review(product_id, review_id):
    review = Review.query.filter_by(product_id=product_id, id=review_id).first_or_404()
    data = request.get_json()

    review.rating = data.get('rating', review.rating)
    review.content = data.get('content', review.content)

    db.session.commit()
    return jsonify({'message': 'Review updated successfully'})


@app.route('/products/<int:product_id>/reviews/<int:review_id>', methods=['DELETE'])
@token_required
def delete_review(product_id, review_id):
    review = Review.query.filter_by(product_id=product_id, id=review_id).first_or_404()
    db.session.delete(review)
    db.session.commit()
    return jsonify({'message': 'Review deleted successfully'})


# DESCRIPTION CRUD

@app.route('/products/<int:product_id>/descriptions', methods=['GET'])
@token_required
def get_descriptions(product_id):
    descriptions = ProductDescription.query.filter_by(product_id=product_id).all()
    result = [{"id": d.id, "details": d.details} for d in descriptions]
    return jsonify(result)


@app.route('/products/<int:product_id>/descriptions/<int:desc_id>', methods=['GET'])
@token_required
def get_description(product_id, desc_id):
    description = ProductDescription.query.filter_by(product_id=product_id, id=desc_id).first_or_404()
    result = {"id": description.id, "details": description.details}
    return jsonify(result)


@app.route('/products/<int:product_id>/descriptions', methods=['POST'])
@token_required
def add_description(product_id):
    data = request.get_json()
    new_description = ProductDescription(
        product_id=product_id,
        details=data.get('details')
    )
    db.session.add(new_description)
    db.session.commit()
    return jsonify({'message': 'Description added successfully', 'id': new_description.id}), 201


@app.route('/products/<int:product_id>/descriptions/<int:desc_id>', methods=['PUT'])
@token_required
def update_description(product_id, desc_id):
    description = ProductDescription.query.filter_by(product_id=product_id, id=desc_id).first_or_404()
    data = request.get_json()

    description.details = data.get('details', description.details)
    db.session.commit()
    return jsonify({'message': 'Description updated successfully'})


@app.route('/products/<int:product_id>/descriptions/<int:desc_id>', methods=['DELETE'])
@token_required
def delete_description(product_id, desc_id):
    description = ProductDescription.query.filter_by(product_id=product_id, id=desc_id).first_or_404()
    db.session.delete(description)
    db.session.commit()
    return jsonify({'message': 'Description deleted successfully'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
