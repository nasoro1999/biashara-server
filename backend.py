from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch, exceptions
from elasticsearch.exceptions import ConnectionError, AuthenticationException
import firebase_admin
from firebase_admin import credentials, firestore
from indexMapping import indexMapping
from documentPreparation import prepareDocument, model
import os
import logging
import uuid

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL', 'http://localhost:9200')
FIREBASE_CREDENTIALS = os.getenv('FIREBASE_CREDENTIALS', '/home/chumvi/Development/firebase/biashara-app.json')

# Initialize Elasticsearch connection
try:
    es = Elasticsearch(ELASTICSEARCH_URL)
    if es.ping():
        logger.info("Connected to Elasticsearch")
    else:
        raise ConnectionError("Failed to connect to Elasticsearch")
except ConnectionError as e:
    logger.error(f"Error connecting to Elasticsearch: {e}")
    es = None  # Ensuring 'es' is not used if the connection fails
except AuthenticationException as e:
    logger.error(f"Authentication failed: {e}")
    es = None
except Exception as e:
    logger.error(f"An error occurred: {e}")
    es = None

# Initialize Firestore connection
try:
    cred = credentials.Certificate(FIREBASE_CREDENTIALS)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logger.info("Connected to Firestore")
except Exception as e:
    logger.error(f"An error occurred with Firestore: {e}")
    db = None  # Ensuring 'db' is not used if the connection fails

# Create the index with the mapping if it doesn't exist
if es and not es.indices.exists(index="all_products"):
    es.indices.create(index="all_products", body=indexMapping)
    logger.info("Index 'all_products' created")

# Function to index a new product in Elasticsearch
def index_new_product(product):
    try:
        product_id = str(uuid.uuid4())  # Generate a unique ID for the product
        doc = prepareDocument(product)
        res = es.index(index="all_products", id=product_id, document=doc)
        es.indices.refresh(index="all_products")  # Refresh the index to make the document searchable immediately
        logger.info(f"Product indexed successfully: {res['result']}")
    except Exception as e:
        logger.error(f"Error indexing product: {e}")

# API route to add a new product
@app.route('/add_product', methods=['POST'])
def add_product():
    if not es:
        return jsonify({"error": "Elasticsearch is not available"}), 500

    try:
        product = request.json
        logger.info(f"Received product data: {product}")

        # Validate input
        if not product:
            return jsonify({"error": "No product data provided"}), 400
        required_fields = ["productName", "productDescription", "currency", "userId", "productPrice"]
        for field in required_fields:
            if field not in product:
                return jsonify({"error": f"{field} is required"}), 400

        index_new_product(product)
        return jsonify({"message": "Product added and indexed successfully"}), 201
    except Exception as e:
        logger.error(f"Error adding product: {e}")
        return jsonify({"error": f"Error adding product: {e}"}), 500

# API route to perform KNN search
@app.route('/search', methods=['POST'])
def knn_search():
    if not es:
        return jsonify({"error": "Elasticsearch is not available"}), 500

    try:
        input_keyword = request.json.get('keyword')
        if not input_keyword:
            return jsonify({"error": "Keyword is required"}), 400

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
        logger.error(f"Error performing KNN search: {e}")
        return jsonify({"error": f"Error performing KNN search: {e}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
