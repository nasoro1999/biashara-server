from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch, exceptions
from elasticsearch.exceptions import ConnectionError, AuthenticationException
import firebase_admin
from firebase_admin import credentials, firestore
from indexMapping import indexMapping
from documentPreparation import prepareDocument, model

app = Flask(__name__)

# Initialize Elasticsearch connection
try:
    es = Elasticsearch("http://localhost:9200")
    if es.ping():
        print("Connected to Elasticsearch")
    else:
        print("Failed to connect to Elasticsearch")
except ConnectionError as e:
    print(f"Error connecting to Elasticsearch: {e}")
except AuthenticationException as e:
    print(f"Authentication failed: {e}")
except Exception as e:
    print(f"An error occurred: {e}")

# Initialize Firestore connection
try:
    cred = credentials.Certificate('/home/chumvi/Development/firebase/biashara-app.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"An error occurred with Firestore: {e}")

# Create the index with the mapping if it doesn't exist
if not es.indices.exists(index="all_products"):
    es.indices.create(index="all_products", body=indexMapping)

# Function to index a new product in Elasticsearch
def index_new_product(product):
    doc = prepareDocument(product)
    res = es.index(index="all_products", id=product["id"], document=doc)
    es.indices.refresh(index="all_products")  # Refresh the index to make the document searchable immediately
    print(res['result'])

# API route to add a new product
@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        product = request.json
        index_new_product(product)
        return jsonify({"message": "Product added and indexed successfully"}), 201
    except Exception as e:
        return jsonify({"error": f"Error adding product: {e}"}), 500

# API route to perform KNN search
@app.route('/search', methods=['POST'])
def knn_search():
    try:
        input_keyword = request.json.get('keyword')
        vector_of_input_keyword = model.encode(input_keyword)

        knn_query = {
            "field": "DescriptionVector",
            "query_vector": vector_of_input_keyword,
            "k": 4,
            "num_candidates": 500
        }

        res = es.knn_search(index="all_products", knn=knn_query,
                            _source=["productName", "productDescription", "currency", "imageUrls", "videoUrls",
                                     "userId", "productPrice"])

        results = [hit["_source"] for hit in res["hits"]["hits"]]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": f"Error performing KNN search: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
