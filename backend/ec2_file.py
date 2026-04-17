import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Mock categorical data
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

@app.route('/data', methods=['GET'])
def get_data():

    try:
        placeholder = requests.get("https://jsonplaceholder.typicode.com/posts/1").json()
        return jsonify({
            "categories": EXTERNAL_CATEGORIES,
            "news_alert": placeholder.get('title', 'No news today'),
            "source": "External Pharma Network"
        })
    except:
        return jsonify({"categories": EXTERNAL_CATEGORIES, "source": "Cache"})

if __name__ == "__main__":
    print("External Category Service on port 5001...")
    app.run(port=5001, debug=True)
