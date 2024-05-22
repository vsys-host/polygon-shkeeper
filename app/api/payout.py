from decimal import Decimal

from flask import g, request
from flask import current_app as app
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware 

from .. import celery
from ..tasks import make_multipayout 
from ..utils import BaseConverter
from . import api

from ..token import Token, Coin
from ..logging import logger
from ..config import config


@api.post('/calc-tx-fee/<decimal:amount>')
def calc_tx_fee(amount):
    if g.symbol == config["COIN_SYMBOL"]:
        coin_inst = Coin(config["COIN_SYMBOL"])
        fee = coin_inst.get_transaction_price()
        return {'accounts_num': 1,
                'fee': float(fee)}

    elif g.symbol in config['TOKENS'][config["CURRENT_POLYGON_NETWORK"]].keys():
        token_instance = Token(g.symbol)
        need_crypto = token_instance.get_coin_transaction_fee()       
        return {
            'accounts_num': 1,
            'fee': float(need_crypto),
        }
    else:
        return {'status': 'error', 'msg': 'unknown crypto' }

@api.post('/multipayout')
def multipayout():
    w3 = Web3(HTTPProvider(config["FULLNODE_URL"], request_kwargs={'timeout': int(config['FULLNODE_TIMEOUT'])}))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    
    try:
        payout_list = request.get_json(force=True)
    except Exception as e:
        raise Exception(f"Bad JSON in payout list: {e}")

    if not payout_list:
            raise Exception(f"Payout list is empty!")

    for transfer in payout_list:
        try:
            is_address = w3.isAddress(transfer['dest'])
        except Exception as e:
            raise Exception(f"Bad destination address in {transfer}: {e}")
        if not is_address:
            raise Exception(f"Bad destination address in {transfer}")
        try:
            transfer['amount'] = Decimal(transfer['amount'])
        except Exception as e:
            raise Exception(f"Bad amount in {transfer}: {e}")

        if transfer['amount'] <= 0:
            raise Exception(f"Payout amount should be a positive number: {transfer}")

    if g.symbol == config["COIN_SYMBOL"]:
        task = (make_multipayout.s(g.symbol, payout_list, Decimal(config['MAX_PRIORITY_FEE']))).apply_async()
        return{'task_id': task.id}
    elif  g.symbol in config['TOKENS'][config["CURRENT_POLYGON_NETWORK"]].keys(): 
        task = ( make_multipayout.s(g.symbol, payout_list, Decimal(config['MAX_PRIORITY_FEE']))).apply_async()
        return {'task_id': task.id}
    else:
        raise Exception(f"{g.symbol} is not defined in config, cannot make payout")
    
@api.post('/payout/<to>/<decimal:amount>')
def payout(to, amount):
    payout_list = [{ "dest": to, "amount": amount }]
    if g.symbol == config["COIN_SYMBOL"]:
        payout_list = [{ "dest": to, "amount": amount }]
        task = (make_multipayout.s(g.symbol, payout_list, Decimal(config['MAX_PRIORITY_FEE']))).apply_async()        
        return {'task_id': task.id}
    elif  g.symbol in config['TOKENS'][config["CURRENT_POLYGON_NETWORK"]].keys():
        task = (make_multipayout.s(g.symbol, payout_list, Decimal(config['MAX_PRIORITY_FEE']))).apply_async()
        return {'task_id': task.id}
    else:
        raise Exception(f"{g.symbol} is not defined in config, cannot make payout")

@api.post('/task/<id>')
def get_task(id):
    task = celery.AsyncResult(id)
    if isinstance(task.result, Exception):
        return {'status': task.status, 'result': str(task.result)}
    return {'status': task.status, 'result': task.result}

