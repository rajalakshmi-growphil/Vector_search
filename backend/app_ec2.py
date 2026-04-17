import json
import os
import mysql.connector
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from werkzeug.utils import secure_filename
import boto3
from botocore.exceptions import NoCredentialsError

app = Flask(__name__)
CORS(app)

# DB Configuration from environment variables
DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': os.environ.get('DB_NAME')
}

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# S3 & CloudFront Config
S3_BUCKET = os.environ.get('S3_DATA_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('IMAGE_CLOUDFRONT_DOMAIN')
s3_client = boto3.client('s3')

# Try to load ML model (only available on EC2, not on Lambda)
model = None
ML_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    ML_AVAILABLE = True
    print("✔ ML model loaded successfully")
except ImportError:
    print("⚠ ML libraries not available - vector search will be disabled")

def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

def init_db():
    """Initializes the database by creating necessary tables if they don't exist."""
    print("Initialising database check...")
    try:
        # We might need to connect without a database first if it doesn't exist, 
        # but DB_CONFIG usually implies the DB exists.
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products_vectors (
                product_id INT NOT NULL PRIMARY KEY,
                product_name VARCHAR(255) NOT NULL,
                vector LONGTEXT NOT NULL,
                image_name VARCHAR(255)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        # Add image_name column if it doesn't exist (for existing tables)
        try:
            cursor.execute("ALTER TABLE products_vectors ADD COLUMN image_name VARCHAR(255)")
            print("✔ Added image_name column to products_vectors")
        except mysql.connector.Error as err:
            if err.errno == 1060: # Column already exists
                pass
            else:
                raise err
        
        # Check if 95761_presc.png placeholder exists in uploads (logical check)
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        conn.commit()
        print("✔ Database and tables verified/created.")
    except Exception as e:
        print(f"✘ Database initialization error: {e}")
        # We don't exit, as the DB might be reachable later or handled by environment
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/search', methods=['POST', 'GET'])
def search_products():
    data = request.get_json() if request.is_json else request.args
    query = data.get('query')
    limit = int(data.get('limit', 10))
    
    if not query:
        return jsonify({"error": "No query provided"}), 400
    
    return perform_vector_search(query, limit)

def perform_vector_search(query, limit=10):
    # Check if ML is available
    if not ML_AVAILABLE:
        # Fallback to pure keyword search if ML is down
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            sql = "SELECT product_id, product_name FROM products_vectors WHERE product_name LIKE %s LIMIT %s"
            cursor.execute(sql, (f"%{query}%", limit))
            results = cursor.fetchall()
            for r in results:
                r['score'] = 1.0
                r['image_url'] = None # Simplified
            return jsonify({"query": query, "results": results})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # 1. Embed query
    query_vector = model.encode(query)
    
    # 2. Connect to DB and fetch vectors + names for hybrid
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT product_id, product_name, vector, image_name FROM products_vectors")
        all_items = cursor.fetchall()
        
        # 3. Calculate similarities and Keyword matches
        combined_results = []
        query_lower = query.lower()
        
        for item in all_items:
            item_vector = np.array(json.loads(item['vector']))
            v_score = cosine_similarity(query_vector, item_vector)
            
            # Keyword score boost
            name_lower = item['product_name'].lower()
            k_score = 0
            if query_lower in name_lower:
                k_score = 0.5 # Base boost for containing string
                if name_lower.startswith(query_lower):
                    k_score = 0.8 # Higher boost for prefix
            
            # Final score (weighted combination)
            final_score = float(max(v_score, k_score))
            
            if item.get('image_name'):
                img_url = f"https://{CLOUDFRONT_DOMAIN}/uploads/{item['image_name']}"
            else:
                img_url = f"https://{CLOUDFRONT_DOMAIN}/uploads/95761_presc.png"

            combined_results.append({
                "product_id": item['product_id'],
                "product_name": item['product_name'],
                "score": final_score,
                "image_url": img_url
            })
            
        sorted_results = sorted(combined_results, key=lambda x: x['score'], reverse=True)[:limit]

        return jsonify({
            "query": query,
            "results": sorted_results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/products', methods=['GET'])
def get_all_products():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT product_id, product_name, image_name FROM products_vectors ORDER BY product_id DESC")
        results = cursor.fetchall()
        
        for item in results:
            if item.get('image_name'):
                item['image_url'] = f"https://{CLOUDFRONT_DOMAIN}/uploads/{item['image_name']}"
                item['has_image'] = True
            else:
                item['image_url'] = f"https://{CLOUDFRONT_DOMAIN}/uploads/95761_presc.png"
                item['has_image'] = False
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/delete-product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("SELECT image_name FROM products_vectors WHERE product_id = %s", (product_id,))
        row = cursor.fetchone()
        
        cursor.execute("DELETE FROM products_vectors WHERE product_id = %s", (product_id,))
        conn.commit()
        
        if row and row['image_name']:
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=f"uploads/{row['image_name']}")
            except Exception as e:
                print(f"⚠ Failed to delete S3 object: {e}")
        
        return jsonify({"message": f"Product {product_id} deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/add-product', methods=['POST'])
def add_product():
    if 'image' not in request.files:
        return jsonify({"error": "No image part"}), 400
    
    file = request.files['image']
    product_name = request.form.get('name')
    product_id = request.form.get('id')
    
    if not product_name or not product_id:
        return jsonify({"error": "Product name and ID are required"}), 400

    if file and file.filename != '':
        # Use a consistent naming convention: {product_id}_image.ext
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
        filename = f"{product_id}_image.{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save to local for fallback/cache
        file.save(filepath)
        
        # Upload to S3
        try:
            # Re-open file to upload to S3 since file.save() might have exhausted the stream
            with open(filepath, 'rb') as f:
                s3_client.upload_fileobj(
                    f,
                    S3_BUCKET,
                    f"uploads/{filename}",
                    ExtraArgs={'ContentType': file.content_type if file.content_type else 'image/jpeg'}
                )
        except NoCredentialsError:
            return jsonify({"error": "S3 Credentials failure"}), 500
        except Exception as e:
            return jsonify({"error": f"S3 Upload failed: {str(e)}"}), 500

        # 1. Generate embedding for the new product (only if ML is available)
        vector = None
        if ML_AVAILABLE:
            vector = model.encode(product_name).tolist()
        else:
            vector = []
        
        # 2. Store in DB
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            sql = """
                INSERT INTO products_vectors (product_id, product_name, vector, image_name) 
                VALUES (%s, %s, %s, %s) 
                ON DUPLICATE KEY UPDATE product_name=%s, vector=%s, image_name=%s
            """
            cursor.execute(sql, (product_id, product_name, json.dumps(vector), filename, product_name, json.dumps(vector), filename))
            conn.commit()
            image_url = f"https://{CLOUDFRONT_DOMAIN}/uploads/{filename}"
            return jsonify({"message": "Product added and embedded successfully", "filename": filename, "image_url": image_url})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
    
    return jsonify({"error": "Invalid file"}), 400

# Mock categorical data (Integrated from ec2_file.py)
EXTERNAL_CATEGORIES = [
    {
        "id": "CAT1",
        "name": "Pain Management",
        "description": "Relieve pain and inflammation.",
        "top_product": "Paracetamol"
    },
    {
        "id": "CAT2",
        "name": "Antibiotics",
        "description": "Treat bacterial infections.",
        "top_product": "Amoxicillin"
    },
    {
        "id": "CAT3",
        "name": "Vitamins",
        "description": "Essential nutrients for health.",
        "top_product": "Vitamin D3"
    }
]

def get_ec2_instance_id():
    """Find the EC2 instance ID by name tag."""
    import boto3
    ec2 = boto3.client('ec2', region_name=provider_region)
    response = ec2.describe_instances(
        Filters=[{'Name': 'tag:Name', 'Values': ['Lakshmi-App-Server']}]
    )
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            if instance['State']['Name'] != 'terminated':
                return instance['InstanceId']
    return None

provider_region = os.environ.get('AWS_REGION', 'ap-south-1')

@app.route('/api/ec2/status', methods=['GET'])
def get_ec2_status():
    try:
        import boto3
        ec2 = boto3.client('ec2', region_name=provider_region)
        instance_id = get_ec2_instance_id()
        if not instance_id:
            return jsonify({"error": "EC2 Instance not found"}), 404
            
        response = ec2.describe_instances(InstanceIds=[instance_id])
        state = response['Reservations'][0]['Instances'][0]['State']['Name']
        public_ip = response['Reservations'][0]['Instances'][0].get('PublicIpAddress', 'N/A')
        
        return jsonify({
            "instance_id": instance_id,
            "status": state,
            "public_ip": public_ip
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ec2/start', methods=['POST'])
def start_ec2():
    try:
        import boto3
        ec2 = boto3.client('ec2', region_name=provider_region)
        instance_id = get_ec2_instance_id()
        if not instance_id:
            return jsonify({"error": "EC2 Instance not found"}), 404
            
        ec2.start_instances(InstanceIds=[instance_id])
        return jsonify({"message": f"Starting instance {instance_id}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ec2/stop', methods=['POST'])
def stop_ec2():
    try:
        import boto3
        ec2 = boto3.client('ec2', region_name=provider_region)
        instance_id = get_ec2_instance_id()
        if not instance_id:
            return jsonify({"error": "EC2 Instance not found"}), 404
            
        ec2.stop_instances(InstanceIds=[instance_id])
        return jsonify({"message": f"Stopping instance {instance_id}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/external-data', methods=['GET'])
def get_external_data():
    """Returns categorical data directly (integrated microservice logic)."""
    try:
        # Mock external call to jsonplaceholder for news alert
        news_alert = "No news today"
        try:
            placeholder = requests.get("https://jsonplaceholder.typicode.com/posts/1", timeout=2).json()
            news_alert = placeholder.get('title', 'No news today')
        except:
            pass
            
        return jsonify({
            "categories": EXTERNAL_CATEGORIES,
            "news_alert": news_alert,
            "source": "Integrated Pharma Network"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/uploads/<filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "lakshmi-ai-api"})

# For local testing
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
