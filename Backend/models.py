from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    brand = db.Column(db.String(255))
    image_url = db.Column(db.String(255))
    price = db.Column(db.Float)
    rating = db.Column(db.Float)
    description = db.Column(db.Text)

    salts = db.relationship("SaltContent", backref="product", cascade="all, delete-orphan")
    reviews = db.relationship("Review", backref="product", cascade="all, delete-orphan")
    descriptions = db.relationship("ProductDescription", backref="product", cascade="all, delete-orphan")


class SaltContent(db.Model):
    __tablename__ = "salt_contents"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    salt_name = db.Column(db.String(255), nullable=False)
    amount_mg = db.Column(db.Float)
    notes = db.Column(db.String(512))


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    author = db.Column(db.String(255))
    rating = db.Column(db.Float)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProductDescription(db.Model):
    __tablename__ = "product_descriptions"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255))
    body = db.Column(db.Text)
