import asyncio
import base64
import json
import logging

import requests
from cloudinary.uploader import upload
from web3 import Web3

import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

w3_client = Web3(Web3.WebsocketProvider(settings.W3_WS_PROVIDER_URL))


def _get_contract(contract_address):
    contract_address = w3_client.toChecksumAddress(contract_address)
    with open(f"contracts/{contract_address}.json", "r") as f:
        contract_abi = json.load(f)

    return w3_client.eth.contract(address=contract_address, abi=contract_abi)


def handle_event(event):
    logger.debug(event)
    args = event.args
    new_noun_id = args.get("nounId")
    logger.info(f"New auction started event for LilNoun {new_noun_id}")

    nouns_contract = _get_contract(settings.LIL_NOUNS_TOKEN_ADDRESS)
    token_uri = nouns_contract.functions.tokenURI(new_noun_id).call()
    token_metadata_base64 = token_uri.split(";")[1][7:]
    token_metadata = json.loads(base64.b64decode(token_metadata_base64))

    cloudinary_image_id = f"{new_noun_id}_{settings.LIL_NOUNS_TOKEN_ADDRESS}"
    result = upload(file=token_metadata.get("image"), public_id=cloudinary_image_id, overwrite=False)
    noun_image_url = result.get("secure_url")

    data = {
        "blocks": [
            {
                "type": "paragraph",
                "children": [
                    {"text": "Auction for "},
                    {"text": f"LilNoun {new_noun_id}", "bold": True},
                    {"text": " started:"},
                ],
            },
            {
                "type": "attachments",
                "children": [{"type": "image-attachment", "url": noun_image_url, "width": 320, "height": 320}],
            },
            {
                "type": "link",
                "url": f"https://lilnouns.wtf/lilnoun/{new_noun_id}",
                "children": [{"text": f"https://lilnouns.wtf/lilnoun/{new_noun_id}"}],
            },
        ],
    }
    response = requests.post(settings.NS_WEBHOOK_URL, json=data)
    if not response.ok:
        logger.error(f"problems creating message via webhook: {response.status_code} {response.text}")
        return

    logger.info(f"Auction for LilNoun {new_noun_id} posted successfully to NewShades")


async def log_loop(event_filter, poll_interval):
    while True:
        try:
            for event in event_filter.get_new_entries():
                handle_event(event)
        except asyncio.exceptions.TimeoutError:
            continue
        except Exception as e:
            logger.exception(e)
            continue
        await asyncio.sleep(poll_interval)


def main():
    auction_house_contract = _get_contract(contract_address=settings.LIL_NOUNS_AUCTION_HOUSE_ADDRESS)
    new_auction_filter = auction_house_contract.events.AuctionCreated.createFilter(fromBlock="latest")
    loop = asyncio.get_event_loop()
    try:
        logger.info("Listening to contract events...")
        loop.run_until_complete(asyncio.gather(log_loop(new_auction_filter, settings.POLL_INTERVAL_SECONDS)))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
