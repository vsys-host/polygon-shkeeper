import requests
import prometheus_client
from prometheus_client import generate_latest, Info, Gauge
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware 

from . import metrics_blueprint
from ..config import config
from ..models import Settings, db


prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)


def get_latest_release(name):
    if name == 'bor':
        url = 'https://api.github.com/repos/maticnetwork/bor/releases/latest'
    else:
        return False
    data = requests.get(url).json()
    version = data["tag_name"].split('v')[1]
    info = { key:data[key] for key in ["name", "tag_name", "published_at"] }
    info['version'] = version
    return info

def get_all_metrics():
    w3 = Web3(HTTPProvider(config["FULLNODE_URL"], request_kwargs={'timeout': int(config['FULLNODE_TIMEOUT'])}))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if w3.isConnected:
        response = {}
        last_fullnode_block_number = w3.eth.block_number
        response['last_fullnode_block_number'] = last_fullnode_block_number
        response['last_fullnode_block_timestamp'] = w3.eth.get_block(w3.toHex(last_fullnode_block_number))['timestamp']
    
        bor_version = w3.clientVersion
        bor_version = bor_version.split('v')[1].split('-')[0]
        response['bor_version'] = bor_version
    
        pd = Settings.query.filter_by(name = 'last_block').first()
        last_checked_block_number = int(pd.value)
        response['polygon_wallet_last_block'] = last_checked_block_number
        block =  w3.eth.get_block(w3.toHex(last_checked_block_number))
        response['polygon_wallet_last_block_timestamp'] = block['timestamp']
        response['polygon_fullnode_status'] = 1
        return response
    else:
        response['polygon_fullnode_status'] = 0
        return response

bor_last_release = Info(
    'bor_last_release',
    'Version of the latest release from https://github.com/maticnetwork/bor/releases'
)


bor_last_release.info(get_latest_release('bor'))

bor_fullnode_version = Info('bor_fullnode_version', 'Current bor version in use')

polygon_fullnode_status = Gauge('polygon_fullnode_status', 'Connection status to polygon fullnode')

polygon_fullnode_last_block = Gauge('polygon_fullnode_last_block', 'Last block loaded to the fullnode', )
polygon_wallet_last_block = Gauge('polygon_wallet_last_block', 'Last checked block ') 

polygon_fullnode_last_block_timestamp = Gauge('polygon_fullnode_last_block_timestamp', 'Last block timestamp loaded to the fullnode', )
polygon_wallet_last_block_timestamp = Gauge('polygon_wallet_last_block_timestamp', 'Last checked block timestamp')

@metrics_blueprint.get("/metrics")
def get_metrics():
    response = get_all_metrics()
    if response['polygon_fullnode_status'] == 1:
        bor_fullnode_version.info({'version': response['bor_version']})
        polygon_fullnode_last_block.set(response['last_fullnode_block_number'])
        polygon_fullnode_last_block_timestamp.set(response['last_fullnode_block_timestamp'])
        polygon_wallet_last_block.set(response['polygon_wallet_last_block'])
        polygon_wallet_last_block_timestamp.set(response['polygon_wallet_last_block_timestamp'])
        polygon_fullnode_status.set(response['polygon_fullnode_status'])
    else:
        polygon_fullnode_status.set(response['polygon_fullnode_status'])


    return generate_latest().decode()