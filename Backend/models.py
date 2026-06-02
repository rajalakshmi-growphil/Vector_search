from flask_sqlalchemy import SQLAlchemy

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

    def __init__(self, name=None, brand=None, image_url=None, price=None, rating=None, description=None):
        self.name = name
        self.brand = brand
        self.image_url = image_url
        self.price = price
        self.rating = rating
        self.description = description
