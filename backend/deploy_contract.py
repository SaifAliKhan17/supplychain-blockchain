#!/usr/bin/env python3
import json
import os
from solcx import compile_standard, install_solc
from web3 import Web3

ROOT = os.path.dirname(os.path.dirname(__file__))  # project root
CONTRACT_PATH = os.path.join(ROOT, 'contracts', 'ProductRegistry.sol')
OUT_JSON = os.path.join(os.path.dirname(__file__), 'contract_interface.json')
OUT_ADDR = os.path.join(os.path.dirname(__file__), 'contract_address.txt')

# ensure solc
install_solc('0.8.20')

with open(CONTRACT_PATH, 'r') as f:
    source = f.read()

compiled = compile_standard({
    "language": "Solidity",
    "sources": {
        "ProductRegistry.sol": {"content": source}
    },
    "settings": {
        "outputSelection": {
            "*": {
                "*": ["abi", "evm.bytecode.object"]
            }
        }
    }
}, solc_version="0.8.20")

contract_data = compiled['contracts']['ProductRegistry.sol']['ProductRegistry']
abi = contract_data['abi']
bytecode = contract_data['evm']['bytecode']['object']

# Save ABI and bytecode for later use
with open(OUT_JSON, 'w') as wf:
    json.dump({'abi': abi, 'bytecode': bytecode}, wf, indent=2)

# Connect to Ganache
GANACHE_URL = "http://127.0.0.1:7545"
w3 = Web3(Web3.HTTPProvider(GANACHE_URL))
if not w3.is_connected():
    raise SystemExit(f"Error: cannot connect to Ganache at {GANACHE_URL}. Start Ganache first.")

acct = w3.eth.accounts[0]
Product = w3.eth.contract(abi=abi, bytecode=bytecode)

print("Deploying contract from account:", acct)
tx_hash = Product.constructor().transact({'from': acct})
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
contract_address = receipt.contractAddress
print("Deployed at:", contract_address)

with open(OUT_ADDR, 'w') as wf:
    wf.write(contract_address)

print("Saved contract interface ->", OUT_JSON)
print("Saved contract address ->", OUT_ADDR)
