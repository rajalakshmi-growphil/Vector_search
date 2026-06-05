from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = "products"
    
    id = db.Column('product_id', db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    salt_name = db.Column(db.String(255))
    composition = db.Column(db.String(255))
    photo = db.Column(db.Text)
    product_pricing_new = db.Column(db.Float)
    product_name_url = db.Column(db.String(255))

    @property
    def image(self):
        if self.photo:
            try:
                photo_list = json.loads(self.photo)
                if isinstance(photo_list, list) and len(photo_list) > 0:
                    return photo_list[0].get('img')
            except Exception:
                pass
        return None

    @property
    def image_url(self):
        # Fallback property for backward compatibility with frontend if it uses image_url
        return self.image

    @property
    def product_url(self):
        return self.product_name_url

    @property
    def rating(self):
        return 4.5
