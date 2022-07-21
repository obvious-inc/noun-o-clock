import asyncio
import json
import logging
from datetime import datetime
from threading import Timer

import websockets
from web3 import Web3
from websockets.exceptions import ConnectionClosedError

import settings
from helpers.cloudinary import upload_image
from helpers.newshades import create_finalized_auction_message, create_new_auction_message, new_bid_message
from helpers.nouns import get_current_auction, get_noun_metadata
from helpers.w3 import get_contract

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

w3_client = Web3(Web3.WebsocketProvider(settings.W3_WS_PROVIDER_URL))

SUBSCRIPTIONS = [
    {
        "type": "bids",
        "params": [
            "logs",
            {
                "address": settings.AUCTION_HOUSE_CONTRACT_ADDRESS,
                "topics": ["0x1159164c56f277e6fc99c11731bd380e0347deb969b75523398734c252706ea3"],
            },
        ],
    },
    {
        "type": "auction-settled",
        "params": [
            "logs",
            {
                "address": settings.AUCTION_HOUSE_CONTRACT_ADDRESS,
                "topics": ["0xc9f72b276a388619c6d185d146697036241880c36654b1a3ffdad07c24038d99"],
            },
        ],
    },
    {
        "type": "pending-transactions",
        "params": [
            "alchemy_pendingTransactions",
            {"toAddress": [settings.AUCTION_HOUSE_CONTRACT_ADDRESS], "hashesOnly": False},
        ],
    },
]

auction_end = None
auction_timer = None


async def handle_new_auction_event(noun_id: str):
    logger.info(f"New auction started event for Noun {noun_id}")
    token_metadata = await get_noun_metadata(noun_id)
    image_id = f"{noun_id}_{settings.TOKEN_CONTRACT_ADDRESS}"
    image_url = await upload_image(image_id=image_id, image=token_metadata.get("image"))
    await create_new_auction_message(noun_id, image_url)


def finalize_auction():
    contract = get_contract(settings.AUCTION_HOUSE_CONTRACT_ADDRESS)
    curr_auction_info = contract.functions.auction().call()
    noun_id, wei_amount, start_time, end_time, bidder, settled = curr_auction_info
    end_date = datetime.fromtimestamp(end_time)
    if end_date < datetime.now():
        return
    amount = Web3.fromWei(wei_amount, "ether")
    logger.info(f"> auction for noun {noun_id} ended. winner was {bidder} with their bid for Ξ{amount:.2f}")
    asyncio.run(create_finalized_auction_message(noun_id, bidder, amount))

    global auction_timer
    auction_timer = None


async def update_current_auction():
    auction = await get_current_auction()
    end_time = auction.get("end_time")
    noun_id = auction.get("noun_id")
    end_date = datetime.fromtimestamp(end_time)
    if end_date < datetime.now():
        return

    global auction_end
    if end_time != auction_end:
        auction_end = end_time
        seconds_remaining = int((end_date - datetime.now()).total_seconds())
        if seconds_remaining < 0:
            return

        logger.info(f"set current auction end time: {end_date} for noun id {noun_id}")
        global auction_timer
        if auction_timer:
            auction_timer.cancel()
        auction_timer = Timer(seconds_remaining, finalize_auction)
        auction_timer.start()
        logger.info(f"> timer started for {seconds_remaining} seconds")


async def process_new_auction():
    auction = await get_current_auction()
    logger.debug(auction)
    noun_id = auction.get("noun_id")
    end_time = auction.get("end_time")
    global auction_end
    auction_end = end_time
    end_date = datetime.fromtimestamp(end_time)
    seconds_remaining = int((end_date - datetime.now()).total_seconds())
    global auction_timer
    auction_timer = Timer(seconds_remaining, finalize_auction)
    auction_timer.start()
    logger.info(f"> new auction started for noun id {noun_id}. ends at {end_date.isoformat()}")
    await handle_new_auction_event(noun_id)


async def process_pending_transaction(tx: dict):
    contract = get_contract(settings.AUCTION_HOUSE_CONTRACT_ADDRESS)
    func, args = contract.decode_function_input(tx.get("input"))
    str_func = func.function_identifier
    if str_func == "settleCurrentAndCreateNewAuction":
        logger.debug("> pending transaction for settleCurrentAndCreateNewAuction")
    elif str_func == "createBid":
        await process_new_bid(tx, pending=True)
    else:
        logger.debug(f"> unknown pending transaction for function: {str_func} {args}")


async def process_new_bid(tx: dict, pending: bool = False):
    bidder = tx.get("from")
    value = tx.get("value")
    if value:
        amount = Web3.fromWei(Web3.toInt(hexstr=value), "ether")
    else:
        transaction = w3_client.eth.getTransaction(tx.get("transactionHash"))
        amount = Web3.fromWei(transaction.get("value"), "ether")
        bidder = transaction.get("from")

    logger.info(f"> new bid of Ξ{amount:.2f} from {bidder} {'(pending)' if pending else ''}")

    if not pending:
        await new_bid_message(amount, bidder)
        await update_current_auction()


async def process_message(message: dict, subs: dict):
    message_sub = message.get("params").get("subscription")
    message_type = subs[message_sub].get("type")
    logger.debug(f"message_type {message_type} {message}")

    result = message.get("params").get("result")

    if message_type == "bids":
        await process_new_bid(result)
    elif message_type == "auction-settled":
        await process_new_auction()
    elif message_type == "pending-transactions":
        await process_pending_transaction(result)


async def create_subscriptions(ws_client) -> dict:
    subs = {}
    for subscription in SUBSCRIPTIONS:
        ws_message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "eth_subscribe",
            "params": subscription.get("params"),
        }
        await ws_client.send(json.dumps(ws_message))
        connect_msg = await ws_client.recv()
        logger.info(f"connected: {connect_msg}")
        subscription_id = json.loads(connect_msg).get("result")
        subs[subscription_id] = {"type": subscription.get("type")}

    return subs


async def noun_listener():
    while True:
        try:
            async with websockets.connect(settings.W3_WS_PROVIDER_URL) as websocket:
                await update_current_auction()
                retries = 0
                subs_dict = await create_subscriptions(websocket)

                async for str_message in websocket:
                    message = json.loads(str_message)
                    await process_message(message, subs=subs_dict)

        except (ConnectionClosedError, asyncio.TimeoutError):
            if retries == 0:
                retries += 1
                continue
            if retries >= 10:
                raise Exception("Connection to websocket %s failed > 10 times")

            retries += 1
            backoff = max(3, min(60, 2**retries))
            logger.info(f"Connection to websocket was closed, retry in {backoff} seconds.")
            await asyncio.sleep(backoff)


if __name__ == "__main__":
    auction_end = None
    asyncio.run(noun_listener())
