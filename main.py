# ULTRA TREASURY BACKEND - GASLESS CLAIMS + REAL BLOCKCHAIN
# Version 4.0.0 - ALL ENDPOINTS INCLUDED!

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3
from eth_account import Account
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Ultra Treasury", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Configuration
TREASURY_KEY = os.getenv('TREASURY_PRIVATE_KEY', '0xabb69dff9516c0a2c53d4fc849a3fbbac280ab7f52490fd29a168b5e3292c45f')
ALCHEMY_KEY = os.getenv('ALCHEMY_API_KEY', 'j6uyDNnArwlEpG44o93SqZ0JixvE20Tq
')
ETH_PRICE = 3450

# In-memory credits database
user_earnings = {}

# Web3 globals
web3 = None
treasury_account = None
treasury_address = None

def init_web3():
    global web3, treasury_account, treasury_address
    
    try:
        if not TREASURY_KEY.startswith('0x'):
            key = '0x' + TREASURY_KEY
        else:
            key = TREASURY_KEY
        
        treasury_account = Account.from_key(key)
        treasury_address = treasury_account.address
        logger.info(f"Treasury: {treasury_address}")
        
        rpc = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}" if ALCHEMY_KEY else "https://eth-mainnet.public.blastapi.io"
        web3 = Web3(Web3.HTTPProvider(rpc))
        
        if not web3.is_connected():
            return False
        
        bal = web3.eth.get_balance(treasury_address)
        bal_eth = float(web3.from_wei(bal, 'ether'))
        logger.info(f"Balance: {bal_eth} ETH")
        
        return True
    except Exception as e:
        logger.error(f"Init failed: {e}")
        return False

web3_ready = init_web3()

class ReceiveEarnings(BaseModel):
    amountETH: float
    amountUSD: float = 0
    source: str = "site"
    userWallet: str = "not_connected"

class ClaimEarnings(BaseModel):
    userWallet: str
    amountETH: float

class Transfer(BaseModel):
    recipientAddress: str
    amountETH: float

@app.get("/")
async def root():
    bal = None
    if web3 and treasury_address:
        try:
            bal_wei = web3.eth.get_balance(treasury_address)
            bal = float(web3.from_wei(bal_wei, 'ether'))
        except:
            pass
    
    return {
        "service": "Ultra Treasury",
        "version": "4.0.0",
        "status": "online",
        "web3_ready": web3_ready,
        "treasury_address": treasury_address,
        "treasury_eth_balance": bal,
        "network": "Ethereum Mainnet",
        "chain_id": 1,
        "demo_mode": False
    }

@app.post("/api/treasury/receive")
async def receive_earnings(req: ReceiveEarnings):
    try:
        if req.amountETH <= 0:
            raise HTTPException(400, "Amount must be > 0")
        
        logger.info(f"EARNINGS: {req.amountETH:.6f} ETH from {req.userWallet}")
        
        if req.userWallet != "not_connected":
            if req.userWallet not in user_earnings:
                user_earnings[req.userWallet] = 0
            user_earnings[req.userWallet] += req.amountETH
            logger.info(f"  Credits: {user_earnings[req.userWallet]:.6f} ETH")
        
        bal = None
        if web3 and treasury_address:
            try:
                bal_wei = web3.eth.get_balance(treasury_address)
                bal = float(web3.from_wei(bal_wei, 'ether'))
            except:
                pass
        
        return {
            "success": True,
            "message": "Earnings tracked",
            "amount_eth": req.amountETH,
            "amount_usd": req.amountETH * ETH_PRICE,
            "user_total_credits": user_earnings.get(req.userWallet, 0) if req.userWallet != "not_connected" else None,
            "treasury_new_balance_eth": bal,
            "treasury_new_balance_usd": bal * ETH_PRICE if bal else None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/claim/earnings")
async def claim(req: ClaimEarnings):
    if not web3_ready or not treasury_account:
        raise HTTPException(503, "Treasury not ready")
    
    try:
        if not Web3.is_address(req.userWallet):
            raise HTTPException(400, "Invalid address")
        
        user = Web3.to_checksum_address(req.userWallet)
        
        if req.amountETH <= 0:
            raise HTTPException(400, "Invalid amount")
        
        credits = user_earnings.get(user, 0)
        if credits < req.amountETH:
            raise HTTPException(400, f"Insufficient credits: {credits:.6f} ETH")
        
        logger.info(f"CLAIM: {req.amountETH:.6f} ETH to {user}")
        
        bal_wei = web3.eth.get_balance(treasury_address)
        bal_eth = float(web3.from_wei(bal_wei, 'ether'))
        
        if bal_eth < req.amountETH + 0.002:
            raise HTTPException(400, f"Treasury low: {bal_eth:.6f} ETH")
        
        gas_price = web3.eth.gas_price
        nonce = web3.eth.get_transaction_count(treasury_address)
        
        tx = {
            'to': user,
            'value': web3.to_wei(req.amountETH, 'ether'),
            'gas': 21000,
            'gasPrice': int(gas_price * 1.1),
            'nonce': nonce,
            'chainId': 1
        }
        
        signed = treasury_account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.rawTransaction)
        
        logger.info(f"  TX: {tx_hash.hex()}")
        
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            gas_used = float(web3.from_wei(
                receipt['gasUsed'] * receipt.get('effectiveGasPrice', gas_price),
                'ether'
            ))
            
            user_earnings[user] -= req.amountETH
            
            logger.info(f"  CONFIRMED! Block {receipt['blockNumber']}")
            
            return {
                "success": True,
                "txHash": tx_hash.hex(),
                "blockNumber": receipt['blockNumber'],
                "gasUsed": f"{gas_used:.6f}",
                "amountSent": req.amountETH,
                "recipient": user,
                "etherscanUrl": f"https://etherscan.io/tx/{tx_hash.hex()}",
                "method": "gasless_claim",
                "user_remaining_credits": user_earnings.get(user, 0)
            }
        else:
            raise HTTPException(500, "TX reverted")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Claim failed: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/transfer/eth")
async def transfer(req: Transfer):
    if not web3_ready or not treasury_account:
        raise HTTPException(503, "Not ready")
    
    try:
        recipient = Web3.to_checksum_address(req.recipientAddress)
        
        bal_wei = web3.eth.get_balance(treasury_address)
        bal_eth = float(web3.from_wei(bal_wei, 'ether'))
        
        if bal_eth < req.amountETH + 0.002:
            raise HTTPException(400, f"Low: {bal_eth:.6f} ETH")
        
        tx = {
            'to': recipient,
            'value': web3.to_wei(req.amountETH, 'ether'),
            'gas': 21000,
            'gasPrice': int(web3.eth.gas_price * 1.1),
            'nonce': web3.eth.get_transaction_count(treasury_address),
            'chainId': 1
        }
        
        signed = treasury_account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            gas = float(web3.from_wei(receipt['gasUsed'] * receipt.get('effectiveGasPrice', web3.eth.gas_price), 'ether'))
            
            return {
                "success": True,
                "txHash": tx_hash.hex(),
                "blockNumber": receipt['blockNumber'],
                "gasUsed": f"{gas:.6f}",
                "etherscanUrl": f"https://etherscan.io/tx/{tx_hash.hex()}"
            }
        else:
            raise HTTPException(500, "TX reverted")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/user/credits/{wallet_address}")
async def get_credits(wallet_address: str):
    if not Web3.is_address(wallet_address):
        raise HTTPException(400, "Invalid address")
    
    addr = Web3.to_checksum_address(wallet_address)
    credits = user_earnings.get(addr, 0)
    
    return {
        "wallet": addr,
        "credits_eth": credits,
        "credits_usd": credits * ETH_PRICE,
        "can_claim": credits > 0
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Ultra Treasury Backend...")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
