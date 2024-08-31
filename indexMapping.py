# Elasticsearch index mapping
indexMapping = {
    "mappings": {
        "properties": {
            "userId": {
                "type": "keyword"
            },
            "productDescription": {
                "type": "text"
            },
            "DescriptionVector": {
                "type": "dense_vector",
                "dims": 768
            },
            "imageUrls": {
                "type": "keyword"
            },
            "videoUrls": {
                "type": "keyword"
            },
            "productName": {
                "type": "text"
            },
            "currency": {
                "type": "keyword"
            },
            "productPrice": {
                "type": "float"
            },
            "color": {
                "type": "keyword"
            },
            "size": {
                "type": "keyword"
            },
            "brand": {
                "type": "keyword"
            },
            "category": {
                "type": "keyword"
            }
        }
    }
}