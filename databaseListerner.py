import firebase_admin
from firebase_admin import credentials, firestore
from elasticsearch import Elasticsearch

# Initialize Firebase Admin SDK
cred = credentials.Certificate('/home/chumvi/Development/firebase/biashara-app.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

# Connect to Elasticsearch
es = Elasticsearch("http://localhost:9200")

def on_firestore_update(doc_snapshot, changes, read_time):
    """
    Cloud Function triggered when Firestore is updated.
    """
    for change in changes:
        if change.type.name == 'ADDED' or change.type.name == 'MODIFIED':
            # Get the document ID and data
            doc_id = change.document.id
            doc_data = change.document.to_dict()

            # Index the updated data into Elasticsearch
            try:
                es.index(index="all_products", id=doc_id, body=doc_data)
                print(f"Document with ID {doc_id} indexed successfully.")
            except Exception as e:
                print(f"Error indexing document {doc_id} into Elasticsearch: {e}")

# Assign the Cloud Function to the Firestore trigger
collection_ref = db.collection('posts')
update_listener = collection_ref.on_snapshot(on_firestore_update)
