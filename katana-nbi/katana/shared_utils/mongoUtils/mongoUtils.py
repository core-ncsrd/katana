from pymongo import MongoClient, ASCENDING


client = MongoClient("mongodb://mongo")
db = client.katana

# Initialize all collections and create indexes
db.vim.create_index([("id", ASCENDING)], unique=True)
db.nfvo.create_index([("id", ASCENDING)], unique=True)
db.wim.create_index([("id", ASCENDING)], unique=True)
db.ems.create_index([("id", ASCENDING)], unique=True)
db.policy.create_index([("id", ASCENDING)], unique=True)
db.nsd.create_index([("nsd-id", ASCENDING)], unique=True)
db.vnfd.create_index([("vnfd-id", ASCENDING)], unique=True)
db.func.create_index([("id", ASCENDING)], unique=True)
db.location.create_index([("id", ASCENDING)], unique=True)


def index(collection_name):
    collection = db[collection_name]
    return collection.find({})


def get(collection_name, uuid):
    collection = db[collection_name]
    return collection.find_one({"_id": uuid})


def add(collection_name, json_data):
    collection = db[collection_name]
    return collection.insert_one(json_data).inserted_id


def add_many(collection_name, list_data):
    collection = db[collection_name]
    return collection.insert_many(list_data).inserted_ids


def delete(collection_name, uuid):
    result = db[collection_name].delete_one({"_id": uuid}).deleted_count
    return result


def update(collection_name, uuid, json_data):
    collection = db[collection_name]
    return collection.replace_one({"_id": uuid}, json_data).modified_count


def count(collection_name):
    collection = db[collection_name]
    return collection.count_documents({})


def find(collection_name, data={}):
    collection = db[collection_name]
    return collection.find_one(data)


def find_all(collection_name, data={}):
    collection = db[collection_name]
    return collection.find(data)


def delete_all(collection_name, data={}):
    collection = db[collection_name]
    return collection.delete_many(data)
