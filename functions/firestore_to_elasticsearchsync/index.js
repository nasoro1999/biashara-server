const functions = require('firebase-functions');
const admin = require('firebase-admin');
const { Client } = require('@elastic/elasticsearch');

admin.initializeApp();
const db = admin.firestore();

// Set up Elasticsearch client
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

// Firestore trigger for new documents in "posts" collection
exports.onNewPost = functions.firestore.document('posts/{postId}')
    .onCreate(async (snap, context) => {
        const product = snap.data();
        product.id = context.params.postId;  // Assign Firestore document ID to product ID
        await indexNewProduct(product);
    });

// Example HTTP function
exports.helloWorld = functions.https.onRequest((request, response) => {
    functions.logger.info("Hello logs!", {structuredData: true});
    response.send("Hello from Firebase!");
});
