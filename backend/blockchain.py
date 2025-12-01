# backend/blockchain.py
import json
import os
from web3 import Web3
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = Path(__file__).resolve().parent / 'contract_interface.json'
CONTRACT_ADDR_FILE = Path(__file__).resolve().parent / 'contract_address.txt'
GANACHE_URL = "http://127.0.0.1:7545"

w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
if not w3.is_connected():
    raise SystemExit(f"Cannot connect to Ganache at {GANACHE_URL}")

with open(CONTRACT_JSON, 'r') as f:
    contract_data = json.load(f)
abi = contract_data['abi']

def load_contract(contract_address: str):
    return w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

def compute_sha256_hex(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest().lower()

def register_product_onchain(contract, product_id: str, canonical_json_str: str, from_addr: str):
    """
    Hash the canonical JSON and store bytes32 on chain.
    Returns (receipt, hex_hash).
    """
    hexhash = compute_sha256_hex(canonical_json_str)
    # bytes32 value:
    data_bytes = bytes.fromhex(hexhash)  # exactly 32 bytes
    tx_hash = contract.functions.registerProduct(product_id, data_bytes).transact({'from': from_addr})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt, hexhash

def get_onchain_hash(contract, product_id: str):
    """
    Returns (hexstr_no0x_lowercase, timestamp, submitter)
    """
    data_hash, timestamp, submitter = contract.functions.getProductHash(product_id).call()
    # data_hash is bytes-like (HexBytes). Convert to 64-char hex string:
    hexstr = Web3.to_hex(data_hash)  # returns '0x...'
    clean = hexstr.lower().replace('0x', '')
    return clean, timestamp, submitter

# helper: return contract path (for debugging)
def get_contract_address_from_file():
    with open(CONTRACT_ADDR_FILE, 'r') as f:
        return f.read().strip()
