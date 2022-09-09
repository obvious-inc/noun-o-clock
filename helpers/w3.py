import json

from ens import ENS
from web3 import Web3

import settings

w3_client = Web3(Web3.WebsocketProvider(settings.W3_WS_PROVIDER_URL))


def get_contract(contract_address):
    contract_address = w3_client.toChecksumAddress(contract_address)
    with open(f"contracts/{contract_address}.json", "r") as f:
        contract_abi = json.load(f)

    return w3_client.eth.contract(address=contract_address, abi=contract_abi)


def get_ens_primary_name_for_address(wallet_address: str) -> str:
    wallet_address = Web3.toChecksumAddress(wallet_address)
    ens_name = ENS.fromWeb3(w3_client).name(wallet_address)
    return ens_name


async def get_wallet_short_name(address: str, check_ens: bool = True) -> str:
    address = Web3.toChecksumAddress(address)
    short_address = f"{address[:5]}...{address[-3:]}"
    if check_ens:
        try:
            ens_name = get_ens_primary_name_for_address(address)
            short_address = ens_name or short_address
        except Exception:
            pass

    return short_address


async def get_wallet_balance(wallet_address: str):
    wallet_address = Web3.toChecksumAddress(wallet_address)
    return w3_client.eth.get_balance(wallet_address)
