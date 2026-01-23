import json
import time
import requests
from datetime import datetime
from web3 import Web3
from web3.middleware import geth_poa_middleware
from pymongo import MongoClient

# -----------------------------
# Configuration
# -----------------------------
PROMETHEUS_URL = 'http://10.160.1.180:9090/api/v1/query'
BESU_RPC_URL = 'http://10.160.101.81:8545'
FLASK_API_URL = 'http://10.160.1.180:4443/logs'  # Flask API for alerts

# MongoDB Configuration
MONGO_URI = 'mongodb://10.160.101.81:27017'
DB_NAME = 'katanaLogs'
COLLECTION_NAME = 'logs'

CONTRACT_ADDRESS = '0x3Ace09BBA3b8507681146252d3Dd33cD4E2d4F63'
CONTRACT_ABI = [
    {
      "inputs": [
        {
          "internalType": "bytes32",
          "name": "_dataHash",
          "type": "bytes32"
        }
      ],
      "name": "createAssetHash",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "assetId",
          "type": "uint256"
        }
      ],
      "name": "readAsset",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        },
        {
          "internalType": "bytes32",
          "name": "",
          "type": "bytes32"
        },
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "anonymous": False,
      "inputs": [
        {
          "indexed": True,
          "internalType": "uint256",
          "name": "id",
          "type": "uint256"
        },
        {
          "indexed": False,
          "internalType": "bytes32",
          "name": "dataHash",
          "type": "bytes32"
        },
        {
          "indexed": False,
          "internalType": "uint256",
          "name": "timestamp",
          "type": "uint256"
        }
      ],
      "name": "AssetCreated",
      "type": "event"
    }
]

PRIVATE_KEY = '8f2a55949038a9610f50fb23b5883af3b4ecb3c3bb792cbcefbd1542c692be63'

# -----------------------------
# Setup Web3
# -----------------------------
web3 = Web3(Web3.HTTPProvider(BESU_RPC_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)

if not web3.is_connected():
    raise Exception("Unable to connect to Besu node.")

contract = web3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
account = web3.eth.account.from_key(PRIVATE_KEY)

# -----------------------------
# Setup MongoDB Connection
# -----------------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# -----------------------------
# Define PromQL Queries
# -----------------------------
queries = {
    "UsedMemory": 'sum(openstack_nova_limits_memory_used)',
    "AvailableMemory": 'sum(openstack_placement_resource_total{resourcetype="MEMORY_MB"}) - sum(openstack_placement_resource_usage{resourcetype="MEMORY_MB"})',
}

# -----------------------------
# Functions to Query Prometheus
# -----------------------------
def fetch_metric(query):
    try:
        response = requests.get(PROMETHEUS_URL, params={'query': query}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if 'data' in data and 'result' in data['data'] and len(data['data']['result']) > 0:
            return float(data['data']['result'][0]['value'][1])
        return None
    except Exception as e:
        print(f"Error fetching {query}: {e}")
        return None

def fetch_memory_metrics():
    used_memory = fetch_metric(queries["UsedMemory"]) or 0
    available_memory = fetch_metric(queries["AvailableMemory"]) or 0
    return used_memory, available_memory

# -----------------------------
# Function to Save Data to MongoDB
# -----------------------------
def save_data_to_mongodb(data, tx_id, metrics_hash):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    document = {
        "timestamp": timestamp,
        "metrics_data": data,
        "tx_id": tx_id,
        "metrics_hash": metrics_hash
    }
    result = collection.insert_one(document)
    print(f"Metrics data stored in MongoDB with id: {result.inserted_id}")
    return str(result.inserted_id)

# -----------------------------
# Send Metrics Hash to Blockchain
# -----------------------------
def send_metrics_hash_to_blockchain(metrics_json):
    nonce = web3.eth.get_transaction_count(account.address)
    
    metrics_hash = web3.keccak(text=metrics_json)
    print("Computed metrics hash:", metrics_hash.hex())

    txn = contract.functions.createAssetHash(metrics_hash).build_transaction({
        'chainId': 1337,
        'gas': 2000000,
        'gasPrice': web3.to_wei('1', 'gwei'),
        'nonce': nonce,
    })

    signed_txn = web3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt, metrics_hash.hex()

# -----------------------------
# Send Alert to Flask API
# -----------------------------
def send_alert_to_flask(tx_id, metrics_hash, mongo_id,metrics_data):
    # Prepare the alert payload as JSON rather than a file upload
    payload = {
        'tx_id': tx_id,
        'metrics_hash': metrics_hash,
        'mongo_id': mongo_id,
	'MetricsData': metrics_data  # reference to the MongoDB document
    }
    try:
        response = requests.post(FLASK_API_URL, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Alert sent to Flask API successfully!")
    except Exception as e:
        print(f"❌ Failed to send alert to Flask API: {e}")

# -----------------------------
# Main Function - Monitor Memory
# -----------------------------
def main():
    while True:
        used_memory, available_memory = fetch_memory_metrics()
        print(f"Used Memory: {used_memory} MB | Available Memory: {available_memory-10500} MB")

        # Prepare full metrics data for logging
        metrics_data = {
            "UsedMemory": used_memory,
            "AvailableMemory": "6140"
        }
        metrics_json = json.dumps(metrics_data)

        # Send metrics hash to blockchain (always done)
        receipt, metrics_hash = send_metrics_hash_to_blockchain(metrics_json)
        tx_id = receipt.transactionHash.hex()
        print(f"✅ Stored log on blockchain: TX ID = {tx_id}")

        # Save the log in MongoDB (always done)
        mongo_id = save_data_to_mongodb(metrics_data, tx_id, metrics_hash)
        print(used_memory)
        print(available_memory)
        # If the rule is violated, send an alert to the Flask API
        if used_memory > 6143:
            print("⚠️ Memory usage exceeded available memory. Sending alert to Flask API.")
            send_alert_to_flask(tx_id, metrics_hash, mongo_id,metrics_data)

        time.sleep(10)  # Check every 10 seconds

if __name__ == '__main__':
    main()
