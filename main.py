from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3
from eth_account import Account
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Ultra Treasury", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

TREASURY_KEY = os.getenv('TREASURY_PRIVATE_KEY', '0xabb69dff9516c0a2c53d4fc849a3fbbac280ab7f52490fd29a168b5e3292c45f')
ALCHEMY_KEY = os.getenv('ALCHEMY_API_KEY', 'j6uyDNnArwlEpG44o93SqZ0JixvE20Tq
')
ETH_PRICE = 3450

user_earnings = {}

web3 = None
treasury = None
treasury_addr = None

def init():
    global web3, treasury, treasury_addr
    
    try:
        key = TREASURY_KEY if TREASURY_KEY.startswith('0x') else '0x' + TREASURY_KEY
        treasury = Account.from_key(key)
        treasury_addr = treasury.address
        
        logger.info(f"Treasury: {treasury_addr}")
        
        rpc = f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_KEY}" if ALCHEMY_KEY else "https://eth-mainnet.public.blastapi.io"
        web3 = Web3(Web3.HTTPProvider(rpc))
        
        if web3.is_connected():
            bal = web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether')
            logger.info(f"Balance: {bal} ETH")
            return True
        return False
    except Exception as e:
        logger.error(f"Init: {e}")
        return False

web3_ready = init()

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
    if web3 and treasury_addr:
        try:
            bal = float(web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether'))
        except:
            pass
    
    return {
        "service": "Ultra Treasury",
        "version": "4.0.0",
        "status": "online",
        "web3_ready": web3_ready,
        "treasury_address": treasury_addr,
        "treasury_eth_balance": bal,
        "network": "Ethereum Mainnet",
        "chain_id": 1,
        "demo_mode": False,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/treasury/receive")
async def receive(req: ReceiveEarnings):
    try:
        if req.amountETH <= 0:
            raise HTTPException(400, "Invalid amount")
        
        logger.info(f"RECEIVE: {req.amountETH:.6f} ETH from {req.userWallet}")
        
        if req.userWallet != "not_connected":
            user_earnings[req.userWallet] = user_earnings.get(req.userWallet, 0) + req.amountETH
            logger.info(f"Credits: {user_earnings[req.userWallet]:.6f}")
        
        bal = None
        if web3 and treasury_addr:
            try:
                bal = float(web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether'))
            except:
                pass
        
        return {
            "success": True,
            "message": "Earnings tracked",
            "amount_eth": req.amountETH,
            "amount_usd": req.amountETH * ETH_PRICE,
            "user_total_credits": user_earnings.get(req.userWallet, 0) if req.userWallet != "not_connected" else None,
            "treasury_new_balance_eth": bal,
            "treasury_new_balance_usd": bal * ETH_PRICE if bal else None,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/claim/earnings")
async def claim(req: ClaimEarnings):
    if not web3_ready or not treasury:
        raise HTTPException(503, "Not ready")
    
    try:
        if not Web3.is_address(req.userWallet):
            raise HTTPException(400, "Invalid address")
        
        user = Web3.to_checksum_address(req.userWallet)
        credits = user_earnings.get(user, 0)
        
        if credits < req.amountETH:
            raise HTTPException(400, f"Need {req.amountETH:.6f}, have {credits:.6f}")
        
        logger.info(f"CLAIM: {req.amountETH:.6f} to {user}")
        
        bal = float(web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether'))
        
        if bal < req.amountETH + 0.002:
            raise HTTPException(400, f"Low: {bal:.6f}")
        
        tx = {
            'to': user,
            'value': web3.to_wei(req.amountETH, 'ether'),
            'gas': 21000,
            'gasPrice': int(web3.eth.gas_price * 1.1),
            'nonce': web3.eth.get_transaction_count(treasury_addr),
            'chainId': 1
        }
        
        signed = treasury.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt['status'] == 1:
            gas = float(web3.from_wei(receipt['gasUsed'] * receipt.get('effectiveGasPrice', web3.eth.gas_price), 'ether'))
            user_earnings[user] -= req.amountETH
            
            logger.info(f"DONE! Block {receipt['blockNumber']}")
            
            return {
                "success": True,
                "txHash": tx_hash.hex(),
                "blockNumber": receipt['blockNumber'],
                "gasUsed": f"{gas:.6f}",
                "amountSent": req.amountETH,
                "recipient": user,
                "etherscanUrl": f"https://etherscan.io/tx/{tx_hash.hex()}",
                "user_remaining_credits": user_earnings.get(user, 0),
                "timestamp": datetime.now().isoformat()
            }
        raise HTTPException(500, "Failed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(500, str(e))

@app.post("/api/transfer/eth")
async def transfer(req: Transfer):
    if not web3_ready or not treasury:
        raise HTTPException(503, "Not ready")
    
    try:
        to = Web3.to_checksum_address(req.recipientAddress)
        bal = float(web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether'))
        
        if bal < req.amountETH + 0.002:
            raise HTTPException(400, f"Low: {bal:.6f}")
        
        tx = {
            'to': to,
            'value': web3.to_wei(req.amountETH, 'ether'),
            'gas': 21000,
            'gasPrice': int(web3.eth.gas_price * 1.1),
            'nonce': web3.eth.get_transaction_count(treasury_addr),
            'chainId': 1
        }
        
        signed = treasury.sign_transaction(tx)
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
        raise HTTPException(500, "Failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/user/credits/{wallet_address}")
async def credits(wallet_address: str):
    if not Web3.is_address(wallet_address):
        raise HTTPException(400, "Invalid")
    
    addr = Web3.to_checksum_address(wallet_address)
    creds = user_earnings.get(addr, 0)
    
    return {
        "wallet": addr,
        "credits_eth": creds,
        "credits_usd": creds * ETH_PRICE,
        "can_claim": creds > 0
    }

@app.get("/health")
async def health():
    bal = None
    if web3 and treasury_addr:
        try:
            bal = float(web3.from_wei(web3.eth.get_balance(treasury_addr), 'ether'))
        except:
            pass
    
    return {
        "status": "healthy",
        "treasury_balance": bal,
        "web3_ready": web3_ready,
        "users": len(user_earnings),
        "total": sum(user_earnings.values())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

