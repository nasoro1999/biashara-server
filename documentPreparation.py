from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-mpnet-base-v2")

# Function to prepare document
def prepareDocument(product):
    description_vector = model.encode(product["productDescription"]).tolist()
    document = {
        "productName": product["productName"],
        "productDescription": product["productDescription"],
        "DescriptionVector": description_vector,
        "currency": product["currency"],
        "imageUrls": product.get("imageUrls", []),
        "videoUrls": product.get("videoUrls", []),
        "userId": product["userId"],
        "productPrice": product["productPrice"]
    }

    # Add optional fields if they are present
    if "color" in product:
        document["color"] = product["color"]
    if "size" in product:
        document["size"] = product["size"]
    if "brand" in product:
        document["brand"] = product["brand"]
    if "category" in product:
        document["category"] = product["category"]

    return document
