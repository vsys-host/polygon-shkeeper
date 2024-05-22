import json
from decimal import Decimal

from flask import current_app, g
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware 
import decimal
import requests

from .. import events
from ..config import config
from ..encryption import Encryption
from ..models import Accounts, Settings, db, Wallets
from ..token import Token, Coin, get_all_accounts
from ..logging import logger
from . import api
from app import create_app
from ..unlock_acc import get_account_password

w3 = Web3(HTTPProvider(config["FULLNODE_URL"], request_kwargs={'timeout': int(config['FULLNODE_TIMEOUT'])}))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)


app = create_app()
app.app_context().push()

@api.post("/generate-address")
def generate_new_address():    
    acc = w3.eth.account.create()
    crypto_str = str(g.symbol)
    e = Encryption
    logger.warning(f'Saving wallet {acc.address} to DB')
    try:
        with app.app_context():
            db.session.add(Wallets(pub_address = acc.address, 
                                    priv_key = e.encrypt(acc.key.hex()),
                                    type = "regular",
                                    ))
            db.session.add(Accounts(address = acc.address, 
                                         crypto = crypto_str,
                                         amount = 0,
                                         ))
            db.session.commit()
            db.session.close()
            db.engine.dispose() 
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose() 

    logger.info(f'Added new address and wallet added to DB')
    return {'status': 'success', 'address': acc.address}

@api.post('/balance')
def get_balance():
    crypto_str = str(g.symbol)   
    if crypto_str == config["COIN_SYMBOL"]:
        inst = Coin(config["COIN_SYMBOL"])
        balance = inst.get_fee_deposit_coin_balance()
    else:
        if crypto_str in config['TOKENS'][config["CURRENT_POLYGON_NETWORK"]].keys():
            token_instance = Token(crypto_str)
            balance = token_instance.get_fee_deposit_token_balance()
        else:
            return {'status': 'error', 'msg': 'token is not defined in config'}
    return {'status': 'success', 'balance': balance}

@api.post('/status')
def get_status():
    with app.app_context():
        pd = Settings.query.filter_by(name = 'last_block').first()
    
    last_checked_block_number = int(pd.value)
    block =  w3.eth.get_block(w3.toHex(last_checked_block_number))
    return {'status': 'success', 'last_block_timestamp': block['timestamp']}

@api.post('/transaction/<txid>')
def get_transaction(txid):
    related_transactions = []
    list_accounts = get_all_accounts()
    if g.symbol == config["COIN_SYMBOL"]:
        try:
            transaction = w3.eth.get_transaction(txid)
            if (transaction['to'] in list_accounts) and (transaction['from'] in list_accounts):
                address = transaction["from"]
                category = 'internal'
            elif transaction['to'] in list_accounts:
                address = transaction["to"]
                category = 'receive'
            elif transaction['from'] in list_accounts:                
                address = transaction["from"]
                category = 'send'
            else:
                return {'status': 'error', 'msg': 'txid is not related to any known address'}
            amount = w3.fromWei(transaction["value"], "ether") 
            confirmations = int(w3.eth.blockNumber) - int(transaction["blockNumber"])
            related_transactions.append([address, amount, confirmations, category])
        except Exception as e:
            return {f'status': 'error', 'msg': {e}}
    elif g.symbol in config['TOKENS'][config["CURRENT_POLYGON_NETWORK"]].keys():
        token_instance  = Token(g.symbol)
        try:
            transfer_abi_args = token_instance.contract._find_matching_event_abi('Transfer')['inputs']
            for argument in transfer_abi_args:
                if argument['type'] == 'uint256':
                    amount_name = argument['name']
            transactions_array = token_instance.get_token_transaction(txid)
            if len(transactions_array) == 0:
                logger.warning(f"There is not any token {g.symbol} transaction with transactionID {txid}")
                return {'status': 'error', 'msg': 'txid is not found for this crypto '}
            logger.warning(transactions_array)
            for transaction in transactions_array:
                if ((token_instance.provider.toChecksumAddress(transaction['to']) in list_accounts) and 
                    (token_instance.provider.toChecksumAddress(transaction['from']) in list_accounts)):
                    address = token_instance.provider.toChecksumAddress(transaction["from"])
                    category = 'internal'
                    amount = Decimal(transaction["amount"]) / Decimal(10** (token_instance.contract.functions.decimals().call()))
                    confirmations = int(w3.eth.blockNumber) - int(transaction["block_number"])
                    related_transactions.append([address, amount, confirmations, category])

                elif token_instance.provider.toChecksumAddress(transaction['to']) in list_accounts:
                    address = token_instance.provider.toChecksumAddress(transaction["to"])
                    category = 'receive'
                    amount = Decimal(transaction["amount"]) / Decimal(10** (token_instance.contract.functions.decimals().call()))
                    confirmations = int(w3.eth.blockNumber) - int(transaction["block_number"])
                    related_transactions.append([address, amount, confirmations, category])
                elif token_instance.provider.toChecksumAddress(transaction['from']) in list_accounts:                
                    address = token_instance.provider.toChecksumAddress(transaction["from"])
                    category = 'send'
                    amount = Decimal(transaction["amount"]) / Decimal(10** (token_instance.contract.functions.decimals().call()))
                    confirmations = int(w3.eth.blockNumber) - int(transaction["block_number"])
                    related_transactions.append([address, amount, confirmations, category])
            if not related_transactions:
                logger.warning(f"txid {txid} is not related to any known address for {g.symbol}")
                return {'status': 'error', 'msg': 'txid is not related to any known address'}        
        except Exception as e:
            raise e 
    else:
        return {'status': 'error', 'msg': 'Currency is not defined in config'}
    logger.warning(related_transactions)
    return related_transactions


@api.post('/dump')
def dump():
    w = Coin(config["COIN_SYMBOL"])
    all_wallets = w.get_dump()
    return all_wallets

@api.post('/fee-deposit-account')
def get_fee_deposit_account():
    if g.symbol != config["COIN_SYMBOL"]:
        token_instance = Token(g.symbol)
        return {'account': token_instance.get_fee_deposit_account(), 
                'balance': token_instance.get_fee_deposit_account_balance()}
    else:
        token_instance = Coin(g.symbol)
        return {'account': token_instance.get_fee_deposit_account(), 
                'balance': token_instance.get_fee_deposit_coin_balance()}


@api.post('/get_all_addresses')
def get_all_addresses():
    all_addresses_list = get_all_accounts()   
    return all_addresses_list


    
