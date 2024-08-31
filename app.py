from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch, exceptions
from elasticsearch.exceptions import ConnectionError, AuthenticationException
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from transformers import AutoModelForCausalLM, AutoTokenizer

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
        product_id = product.get('id', str(uuid.uuid4()))
        doc = prepareDocument(product)
        res = es.index(index="all_products", id=product_id, document=doc)
        es.indices.refresh(index="all_products")  # Refresh the index to make the document searchable immediately
        logger.info(f"Product indexed successfully: {res['result']}")
    except Exception as e:
        logger.error(f"Error indexing product: {e}")


def get_user_query_history(user_id):
    try:
        searches_ref = db.collection('searchHistory').document(user_id).collection('searches')
        query_docs = searches_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        query_history = [doc.to_dict().get('query', '') for doc in query_docs]
        logger.info(f"Query history for user {user_id}: {query_history}")
        print(f"Successfully retrieved query history for user {user_id}: {query_history}")
        return query_history
    except Exception as e:
        logger.error(f"Error fetching user query history: {e}")
        return []


# Function to recommend products based on user query history
def recommend_products(user_id):
    try:
        query_history = get_user_query_history(user_id)
        if not query_history:
            return []

        # Example recommendation logic: Find products similar to the most recent query
        latest_query = query_history[-1]  # Assuming the last query is the most recent
        query_vector = model.encode(latest_query).tolist()

        # Elasticsearch KNN query based on the query_vector
        knn_query = {
            "field": "DescriptionVector",
            "query_vector": query_vector,
            "k": 5,  # Adjust the number of recommendations as needed
            "num_candidates": 10
        }

        res = es.knn_search(
            index="all_products",
            knn=knn_query,
            _source=["productName", "productDescription", "currency", "imageUrls", "videoUrls", "userId",
                     "productPrice"]
        )

        # Extract _id and _source from hits and include id in the response
        results = [{"id": hit["_id"], **hit["_source"]} for hit in res["hits"]["hits"]]
        logger.info(f"Recommendations for user {user_id}: {results}")
        print(f"Successfully generated recommendations for user {user_id}: {results}")
        return results
    except Exception as e:
        logger.error(f"Error recommending products: {e}")
        return []


# Initialize the Swahili model and tokenizer
model_name = "Mollel/swahili-serengeti-E250-nli-matryoshka"
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Ensure eos_token is set; otherwise, set it to a default
if tokenizer.eos_token is None:
    tokenizer.eos_token = tokenizer.sep_token if tokenizer.sep_token else tokenizer.pad_token

try:
    chat_model = AutoModelForCausalLM.from_pretrained(model_name)
except Exception as e:
    print(f"Model loading failed: {e}")
    chat_model = None


@app.route('/chat', methods=['POST'])
def chat():
    if chat_model is None:
        return jsonify({"error": "Model is not loaded"}), 500

    user_id = request.json.get('user_id')
    user_input = request.json.get('message')

    if not user_input or not user_id:
        return jsonify({"error": "User ID and message are required"}), 400

    # Encode user input with EOS token
    inputs = tokenizer.encode(user_input + tokenizer.eos_token, return_tensors='pt')

    # Generate response using the model with adjusted parameters
    reply_ids = chat_model.generate(
        inputs,
        max_length=100,
        pad_token_id=tokenizer.eos_token_id,
        temperature=0.7,  # Adjust temperature for randomness
        top_p=0.9,  # Use nucleus sampling
        top_k=50,  # Limit sampling to top-k tokens
        repetition_penalty=1.2  # Penalize repetition
    )

    # Decode the generated tokens to a string
    reply = tokenizer.decode(reply_ids[:, inputs.shape[-1]:][0], skip_special_tokens=True)

    # Store message and response in Firestore
    chat_id = uuid.uuid4().hex
    message_data = {
        'sender_id': user_id,
        'message': user_input,
        'timestamp': datetime.utcnow()
    }
    response_data = {
        'sender_id': 'bot',
        'message': reply,
        'timestamp': datetime.utcnow()
    }

    db.collection('chats').document(chat_id).collection('messages').add(message_data)
    db.collection('chats').document(chat_id).collection('messages').add(response_data)

    return jsonify({'response': reply})
# API route to get recommendations based on user query history
@app.route('/recommendations/<user_id>', methods=['GET'])
def get_recommendations(user_id):
    if not es:
        return jsonify({"error": "Elasticsearch is not available"}), 500

    try:
        recommendations = recommend_products(user_id)
        return jsonify(recommendations), 200
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return jsonify({"error": f"Error getting recommendations: {e}"}), 500


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


@app.route('/update_product/<product_id>', methods=['PUT'])
def update_product(product_id):
    if not es:
        return jsonify({"error": "Elasticsearch is not available"}), 500

    try:
        updated_data = request.json
        logger.info(f"Received updated product data: {updated_data}")

        # Validate input
        if not updated_data:
            return jsonify({"error": "No update data provided"}), 400

        # Get existing document from Firestore
        doc_ref = db.collection('posts').document(product_id)
        existing_data = doc_ref.get()
        if not existing_data.exists:
            return jsonify({"error": "Product not found"}), 404

        # Update only the fields that are provided and different from existing ones
        fields_to_update = {}
        for key, value in updated_data.items():
            if key in existing_data.to_dict() and value != existing_data.to_dict()[key]:
                fields_to_update[key] = value

        if not fields_to_update:
            return jsonify({"message": "No fields updated"}), 200

        # Update Firestore document
        doc_ref.update(fields_to_update)

        # Prepare the document for Elasticsearch
        updated_data['id'] = product_id  # Ensure the document has an ID for Elasticsearch
        doc = prepareDocument(updated_data)

        # Index the updated document in Elasticsearch
        res = es.index(index="all_products", id=product_id, document=doc)
        es.indices.refresh(index="all_products")  # Refresh the index to make the document searchable immediately
        logger.info(f"Product updated and indexed successfully: {res['result']}")

        return jsonify({"message": "Product updated and indexed successfully"}), 200
    except Exception as e:
        logger.error(f"Error updating product: {e}")
        return jsonify({"error": f"Error updating product: {e}"}), 500


@app.route('/search', methods=['POST'])
def knn_search():
    if not es:
        return jsonify({"error": "Elasticsearch is not available"}), 500

    try:
        data = request.json
        input_keyword = data.get('keyword')
        max_price = data.get('max_price')
        color = data.get('color')
        size = data.get('size')
        brand = data.get('brand')
        category = data.get('category')

        if not input_keyword:
            return jsonify({"error": "Keyword is required"}), 400

        vector_of_input_keyword = model.encode(input_keyword).tolist()

        knn_query = {
            "field": "DescriptionVector",
            "query_vector": vector_of_input_keyword,
            "k": 4,
            "num_candidates": 500
        }

        res = es.knn_search(index="all_products", knn=knn_query,
                            _source=["productName", "productDescription", "currency", "imageUrls", "videoUrls",
                                     "userId", "productPrice", "color", "size", "brand", "category",
                                     "_id"])  # Include '_id'

        results = [{**hit["_source"], "id": hit["_id"]} for hit in res["hits"]["hits"]]  # Add 'id' field

        # Filter results based on additional criteria
        filtered_results = []
        for product in results:
            if max_price and product['productPrice'] > max_price:
                continue
            if color and color.lower() not in product.get('color', '').lower():
                continue
            if size and size.lower() not in product.get('size', '').lower():
                continue
            if brand and brand.lower() not in product.get('brand', '').lower():
                continue
            if category and category.lower() not in product.get('category', '').lower():
                continue
            filtered_results.append(product)

        return jsonify(filtered_results), 200
    except Exception as e:
        logger.error(f"Error performing KNN search: {e}")
        return jsonify({"error": f"Error performing KNN search: {e}"}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
