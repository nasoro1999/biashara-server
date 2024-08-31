def extract_product_name(query):
    # Implement logic to extract product name from user query
    # Example implementation (basic, can be enhanced):
    keywords = ['sellers of', 'who sells']
    for keyword in keywords:
        if keyword in query.lower():
            return query.lower().split(keyword)[-1].strip()

def find_sellers(product_name):
    try:
        res = es.search(index="all_products", body={
            "query": {
                "match": {
                    "productName": product_name
                }
            }
        })

        sellers = list(set([hit["_source"]["userId"] for hit in res["hits"]["hits"]]))
        return sellers

    except Exception as e:
        logger.error(f"Error finding sellers for {product_name}: {e}")
        return []
