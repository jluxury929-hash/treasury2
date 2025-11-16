# PRODUCTION TREASURY PT2 - SENDS REAL ETH
from flask import Flask, request, jsonify
from flask_cors import CORS
from web3 import Web3
import os
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TREASURY_PRIVATE_KEY = os.environ.get('TREASURY_PRIVATE_KEY')
ALCHEMY_API_KEY = os.environ.get('ALCHEMY_API_KEY')
PORT = int(os.environ.get('PORT', 3000))

# Web3 setup
ALCHEMY_URL = f'https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}'
w3 = Web3(Web3.HTTPProvider(ALCHEMY_URL))

# Treasury account
treasury_account = w3.eth.account.from_key(TREASURY_PRIVATE_KEY)
treasury_address = treasury_account.address

logger.info(f'Treasury PT2: {treasury_address}')

@app.route('/', methods=['GET'])
def health_check():
    try:
        balance = w3.eth.get_balance(treasury_address)
        balance_eth = w3.from_wei(balance, 'ether')
        block_number = w3.eth.block_number
        
        return jsonify({
            'status': 'online',
            'service': 'Treasury PT2',
            'version': '2.0',
            'treasury_address': treasury_address,
            'treasury_eth_balance': float(balance_eth),
            'network': 'Ethereum Mainnet',
            'chain_id': w3.eth.chain_id,
            'block_number': block_number,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/claim/earnings', methods=['POST'])
def claim_earnings():
    data = request.json
    user_wallet = data.get('userWallet')
    amount_eth = float(data.get('amountETH', 0))
    amount_usd = data.get('amountUSD', 0)
    backup_id = data.get('backupId', 'N/A')
    user_email = data.get('userEmail', 'N/A')
    source = data.get('source', 'N/A')

    logger.info('=' * 50)
    logger.info('WITHDRAWAL REQUEST PT2')
    logger.info(f'Amount: {amount_eth} ETH USD: {amount_usd}')
    logger.info(f'To: {user_wallet}')
    logger.info(f'User: {user_email}')
    logger.info(f'Backup: {backup_id}')
    logger.info(f'Source: {source}')
    logger.info('=' * 50)

    try:
        if not w3.is_address(user_wallet):
            raise ValueError('Invalid wallet address')
        
        user_wallet = w3.to_checksum_address(user_wallet)

        if not amount_eth or amount_eth <= 0 or amount_eth > 10:
            raise ValueError(f'Invalid amount: {amount_eth} ETH must be 0-10')

        treasury_balance = w3.eth.get_balance(treasury_address)
        treasury_balance_eth = float(w3.from_wei(treasury_balance, 'ether'))
        
        logger.info(f'Treasury balance: {treasury_balance_eth:.8f} ETH')
        
        if treasury_balance_eth < amount_eth + 0.001:
            raise ValueError(f'Insufficient treasury: {treasury_balance_eth:.6f} ETH')

        amount_wei = w3.to_wei(amount_eth, 'ether')
        
        logger.info('Sending transaction...')
        
        gas_price = w3.eth.gas_price
        
        transaction = {
            'to': user_wallet,
            'value': amount_wei,
            'gas': 21000,
            'gasPrice': gas_price,
            'nonce': w3.eth.get_transaction_count(treasury_address),
            'chainId': w3.eth.chain_id
        }

        signed_txn = treasury_account.sign_transaction(transaction)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_hash_hex = tx_hash.hex()

        logger.info(f'TX broadcast: {tx_hash_hex}')
        logger.info('Waiting for confirmation...')

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        logger.info('')
        logger.info('SUCCESS')
        logger.info(f'TX: {tx_hash_hex}')
        logger.info(f'Block: {receipt["blockNumber"]}')
        logger.info(f'Gas Used: {receipt["gasUsed"]}')
        logger.info(f'Amount: {amount_eth} ETH')
        logger.info(f'To: {user_wallet}')
        logger.info('=' * 50)

        return jsonify({
            'success': True,
            'txHash': tx_hash_hex,
            'blockNumber': receipt['blockNumber'],
            'gasUsed': receipt['gasUsed'],
            'amount': amount_eth,
            'amountUSD': amount_usd,
            'recipientWallet': user_wallet,
            'treasuryAddress': treasury_address,
            'etherscanUrl': f'https://etherscan.io/tx/{tx_hash_hex}',
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        logger.error('=' * 50)
        logger.error('WITHDRAWAL FAILED')
        logger.error(f'Error: {str(e)}')
        logger.error('=' * 50)
        
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 400

if __name__ == '__main__':
    logger.info('')
    logger.info('=' * 50)
    logger.info('TREASURY PT2 SERVER RUNNING')
    logger.info(f'Port: {PORT}')
    logger.info(f'Treasury: {treasury_address}')
    logger.info('Network: Ethereum Mainnet')
    logger.info('=' * 50)
    logger.info('')
    app.run(host='0.0.0.0', port=PORT)
