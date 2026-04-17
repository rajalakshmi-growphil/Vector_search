import json
import os
import boto3
import pymysql
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DB Configuration
DB_CONFIG = {
    'host': os.environ.get('DB_HOST'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'database': os.environ.get('DB_NAME')
}

CLOUDFRONT_DOMAIN = os.environ.get('IMAGE_CLOUDFRONT_DOMAIN')

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS, GET, POST, PUT, DELETE",
    "Access-Control-Allow-Headers": "Content-Type, Authorization"
}

S3_BUCKET = os.environ.get('S3_DATA_BUCKET')
s3_client = boto3.client('s3')

def get_db_connection():
    return pymysql.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
        database=DB_CONFIG['database'],
        cursorclass=pymysql.cursors.DictCursor
    )

def get_all_products():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, product_name, image_name FROM products_vectors ORDER BY product_id DESC")
        results = cursor.fetchall()
        
        # Format image URLs
        for item in results:
            if item.get('image_name'):
                item['image_url'] = f"https://{CLOUDFRONT_DOMAIN}/uploads/{item['image_name']}"
                item['has_image'] = True
            else:
                item['image_url'] = f"https://{CLOUDFRONT_DOMAIN}/uploads/95761_presc.png"
                item['has_image'] = False

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(results)
        }
    except Exception as e:
        logger.error(f"DB Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        if conn and conn.open:
            conn.close()

def get_external_data():
    # Mock data as in original app
    EXTERNAL_CATEGORIES = [
        {"id": "CAT1", "name": "Pain Management", "description": "Relieve pain and inflammation.", "top_product": "Paracetamol"},
        {"id": "CAT2", "name": "Antibiotics", "description": "Treat bacterial infections.", "top_product": "Amoxicillin"},
        {"id": "CAT3", "name": "Vitamins", "description": "Essential nutrients for health.", "top_product": "Vitamin D3"}
    ]
    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "categories": EXTERNAL_CATEGORIES,
            "news_alert": "No news today",
            "source": "Integrated Pharma Network"
        })
    }

def search_products(event):
    # Extract query from body (POST) or query string (GET)
    query = None
    limit = 10
    if event.get('body'):
        try:
            body = json.loads(event['body'])
            query = body.get('query')
            limit = int(body.get('limit', 10))
        except:
            pass
            
    if not query:
        q_params = event.get('queryStringParameters', {}) or {}
        query = q_params.get('query')
        limit = int(q_params.get('limit', 10))

    if not query:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "No query provided"})
        }

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Try SQL LIKE search (fastest for exact/prefix matches)
        sql = "SELECT product_id, product_name, image_name FROM products_vectors WHERE product_name LIKE %s LIMIT %s"
        cursor.execute(sql, (f"%{query}%", limit))
        results = list(cursor.fetchall())
        
        # 2. If results are sparse (< 3), perform Fuzzy search using difflib
        import difflib
        
        # Fetch all product names to compare
        cursor.execute("SELECT product_id, product_name, image_name FROM products_vectors")
        all_products = cursor.fetchall()
        
        # Extract names for difflib
        name_to_id = {p['product_name']: p['product_id'] for p in all_products}
        name_to_img = {p['product_name']: p['image_name'] for p in all_products}
        all_names = list(name_to_id.keys())
        
        # Get fuzzy matches
        fuzzy_matches = difflib.get_close_matches(query, all_names, n=limit, cutoff=0.4)
        
        # Set of IDs already found
        found_ids = {r['product_id'] for r in results}
        
        for name in fuzzy_matches:
            pid = name_to_id[name]
            if pid not in found_ids:
                ratio = difflib.SequenceMatcher(None, query.lower(), name.lower()).ratio()
                results.append({
                    "product_id": pid,
                    "product_name": name,
                    "score": float(ratio),
                    "image_name": name_to_img[name]
                })
                found_ids.add(pid)

        # Format final output with CloudFront URLs
        formatted_results = []
        for item in results:
            score = item.get('score', 1.0)
            if item.get('image_name'):
                img_url = f"https://{CLOUDFRONT_DOMAIN}/uploads/{item['image_name']}"
            else:
                img_url = f"https://{CLOUDFRONT_DOMAIN}/uploads/95761_presc.png"
                
            formatted_results.append({
                "product_id": item['product_id'],
                "product_name": item['product_name'],
                "score": score,
                "image_url": img_url
            })
            
        # Re-sort by score
        formatted_results = sorted(formatted_results, key=lambda x: x['score'], reverse=True)[:limit]

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"query": query, "results": formatted_results})
        }
    except Exception as e:
        logger.error(f"Search DB Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        if conn and conn.open:
            conn.close()


def delete_product(product_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Get image name from DB before deletion
        cursor.execute("SELECT image_name FROM products_vectors WHERE product_id = %s", (product_id,))
        row = cursor.fetchone()
        
        # 2. Delete from Database
        cursor.execute("DELETE FROM products_vectors WHERE product_id = %s", (product_id,))
        conn.commit()
        
        # 3. Delete from S3
        if row and row['image_name']:
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=f"uploads/{row['image_name']}")
            except Exception as e:
                logger.error(f"Failed to delete S3 object: {e}")
        
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": f"Product {product_id} deleted successfully"})
        }
    except Exception as e:
        logger.error(f"Delete Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        if conn and conn.open:
            conn.close()

def add_product(event):
    # Manual multipart parsing for Lambda
    try:
        headers = {k.lower(): v for k, v in event.get('headers', {}).items()}
        content_type = headers.get('content-type')
        if not content_type or 'multipart/form-data' not in content_type:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"error": "Invalid Content-Type"})}
        
        boundary = content_type.split('boundary=')[-1].encode()
        body = event.get('body', '')
        if event.get('isBase64Encoded'):
            import base64
            body = base64.b64decode(body)
        else:
            if isinstance(body, str):
                body = body.encode()

        parts = body.split(b'--' + boundary)
        form_data = {}
        file_content = None
        file_name = None
        file_type = 'image/jpeg'

        for part in parts:
            if b'Content-Disposition' not in part: continue
            
            try:
                header_section, content = part.split(b'\r\n\r\n', 1)
            except ValueError:
                continue
                
            content = content.rstrip(b'\r\n--\r\n').rstrip(b'\r\n')
            
            headers_list = header_section.decode(errors='ignore').split('\r\n')
            disposition = next((h for h in headers_list if 'Content-Disposition' in h), '')
            
            if 'filename=' in disposition:
                # This is the file part
                import re
                file_name_match = re.search(r'filename="([^"]+)"', disposition)
                if file_name_match:
                    file_name = file_name_match.group(1)
                
                type_header = next((h for h in headers_list if 'Content-Type' in h), None)
                if type_header:
                    file_type = type_header.split(': ')[-1]
                
                file_content = content
            else:
                # This is a regular field
                import re
                name_match = re.search(r'name="([^"]+)"', disposition)
                if name_match:
                    name = name_match.group(1)
                    form_data[name] = content.decode(errors='ignore')

        product_id = form_data.get('id')
        product_name = form_data.get('name')

        if not product_id or not product_name:
            return {"statusCode": 400, "headers": CORS_HEADERS, "body": json.dumps({"error": f"Missing ID ({product_id}) or Name ({product_name})", "formData": list(form_data.keys())})}

        # Save to S3 if file provided
        filename = None
        if file_content:
            ext = file_name.split('.')[-1] if '.' in file_name else 'jpg'
            filename = f"{product_id}_image.{ext}"
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=f"uploads/{filename}",
                Body=file_content,
                ContentType=file_type
            )

        # Vector placeholder (Lambda doesn't have ML libraries)
        vector = []

        # Store in DB
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO products_vectors (product_id, product_name, vector, image_name) 
            VALUES (%s, %s, %s, %s) 
            ON DUPLICATE KEY UPDATE product_name=%s, vector=%s, image_name=%s
        """
        cursor.execute(sql, (product_id, product_name, json.dumps(vector), filename, product_name, json.dumps(vector), filename))
        conn.commit()
        conn.close()

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"message": "Product saved successfully", "id": product_id})
        }
    except Exception as e:
        logger.error(f"Add Product Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)})
        }

def handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    
    # Handle preflight CORS
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": ""
        }

    raw_path = event.get('rawPath', '/')
    
    if raw_path == '/api/products':
        return get_all_products()
    elif raw_path == '/api/search':
        return search_products(event)
    elif raw_path == '/api/add-product':
        return add_product(event)
    elif raw_path.startswith('/api/delete-product/'):
        pid = raw_path.split('/')[-1]
        return delete_product(pid)
    elif raw_path == '/api/external-data':
        return get_external_data()
    elif raw_path == '/api/':
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"status": "healthy", "service": "lakshmi-ai-api"})
        }

    # Default 404
    return {
        "statusCode": 404,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": "Path not found", "path": raw_path})
    }
