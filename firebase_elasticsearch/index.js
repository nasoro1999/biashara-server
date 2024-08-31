const functions = require('firebase-functions');
const admin = require('firebase-admin');
const { Client } = require('@elastic/elasticsearch');

// Initialize Firebase Admin
admin.initializeApp();

// Initialize Elasticsearch Client
const esClient = new Client({ node: 'http://localhost:9200' });

// Function to index a new product in Elasticsearch
async function indexNewProduct(product) {
    const { id, ...productData } = product;
    try {
        await esClient.index({
            index: 'all_products',
            id: id,
            body: productData,
        });
        await esClient.indices.refresh({ index: 'all_products' });
        console.log('Product indexed successfully');
    } catch (error) {
        console.error('Error indexing product:', error);
    }
}

// Cloud Function to handle new Firestore document creation
exports.onNewPost = functions.firestore.document('posts/{postId}')
    .onCreate(async (snap, context) => {
        const product = snap.data();
        product.id = context.params.postId;
        await indexNewProduct(product);
    });

