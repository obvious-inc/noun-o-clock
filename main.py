import asyncio
import functools
import json
import logging
import signal
from asyncio import CancelledError, Queue
from datetime import datetime

import websockets
from web3 import Web3
from websockets.exceptions import ConnectionClosedError

import settings
from helpers.cloudinary import upload_image
from helpers.newshades import create_finalized_auction_message, create_new_auction_message, new_bid_message
from helpers.nounoclock import get_bid_notes
from helpers.nouns import (
    get_curr_auction_remaining_seconds,
    get_current_auction,
    get_current_noun_id,
    get_noun_metadata,
)
from helpers.subgraph import NounsSubgraphClient
from helpers.timer import AsyncTimer
from helpers.w3 import get_contract

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

NO_CONSUMERS = 5
auction_timer: AsyncTimer = AsyncTimer()

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

past_bids = set()


async def handle_new_auction_event(noun_id: str):
    token_metadata = await get_noun_metadata(noun_id)
    image_id = f"{noun_id}_{settings.TOKEN_CONTRACT_ADDRESS}"
    image_url = await upload_image(image_id=image_id, image=token_metadata.get("image"))
    await create_new_auction_message(noun_id, image_url)


async def finalize_auction():
    logger.info("finalizing auction...")
    contract = get_contract(settings.AUCTION_HOUSE_CONTRACT_ADDRESS)
    curr_auction_info = contract.functions.auction().call()
    noun_id, wei_amount, _, _, bidder, _ = curr_auction_info

    amount = Web3.fromWei(wei_amount, "ether")
    logger.info(f"> auction for noun {noun_id} ended. winner was {bidder} with their bid for Ξ{amount:.2f}")
    await create_finalized_auction_message(noun_id, bidder, amount)


async def setup_auction():
    auction = await get_current_auction()
    end_time = auction.get("end_time")
    noun_id = auction.get("noun_id")
    end_date = datetime.fromtimestamp(end_time)
    if end_date < datetime.now():
        logger.info(f"> no auction ongoing. latest was: {noun_id}")
        return

    logger.info(f"ongoing auction: {noun_id}")
    await handle_auction_end()


async def process_new_auction():
    auction = await get_current_auction()
    noun_id = auction.get("noun_id")
    end_time = auction.get("end_time")
    end_date = datetime.fromtimestamp(end_time)

    logger.info(f"> new auction started for noun id {noun_id}. ends at {end_date.isoformat()}")
    try:
        await handle_new_auction_event(noun_id)
    except asyncio.exceptions.TimeoutError as e:
        logger.warning(f"issues posting new auction for noun {noun_id}: {e}")
    await handle_auction_end()


async def process_pending_transaction(tx: dict):
    contract = get_contract(settings.AUCTION_HOUSE_CONTRACT_ADDRESS)
    func, args = contract.decode_function_input(tx.get("input"))
    str_func = func.function_identifier
    if str_func == "settleCurrentAndCreateNewAuction":
        logger.info("> pending transaction for settleCurrentAndCreateNewAuction")
    elif str_func == "createBid":
        await process_new_bid(tx, pending=True)
    else:
        logger.info(f"> unknown pending transaction for function: {str_func} {args}")


async def handle_auction_end():
    seconds_remaining = await get_curr_auction_remaining_seconds()
    global auction_timer
    if seconds_remaining < 0:
        await finalize_auction()
    else:
        if auction_timer is not None:
            auction_timer.cancel()

        auction_timer = AsyncTimer(seconds_remaining + 1, handle_auction_end)
        logger.info(f"created new timer for {seconds_remaining} seconds.")


async def process_new_bid(tx: dict, pending: bool = False):
    tx_hash = tx.get("transactionHash")
    bidder = tx.get("from")
    value = tx.get("value")

    if value:
        weth_amount = value
        amount = Web3.fromWei(Web3.toInt(hexstr=value), "ether")
    else:
        transaction = w3_client.eth.getTransaction(tx_hash)
        weth_amount = transaction.get("value")
        amount = Web3.fromWei(weth_amount, "ether")
        bidder = transaction.get("from")

    if not amount or amount == 0:
        bid = await NounsSubgraphClient().get_bid(tx_hash)
        if not bid:
            logger.warning(f"couldn't find info on transaction: {tx_hash}. ignoring bid...")
            return

        weth_amount = int(bid.get("amount", "0"))
        amount = Web3.fromWei(weth_amount, "ether")

    logger.info(f"> new bid of Ξ{amount:.2f} from {bidder} {'(pending)' if pending else ''}")

    if not pending:
        if tx_hash in past_bids:
            logger.warning(f"already saw transaction {tx_hash}")
            return

        try:
            noun_id = str(await get_current_noun_id())
            bid_note = await get_bid_notes(noun_id=noun_id, bidder_address=bidder, bidder_weth=weth_amount)
        except Exception as e:
            logger.warning("issue fetching bid notes", e)
            bid_note = None

        await new_bid_message(amount, bidder, bid_note=bid_note)
        past_bids.add(tx_hash)


async def process_message(message: dict, subs: dict):
    message_sub = message.get("params").get("subscription")
    message_type = subs[message_sub].get("type")
    logger.info(f"message_type {message_type} {message}")

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


async def consumer(queue):
    while True:
        task = await queue.get()
        try:
            await process_message(task.get("message"), subs=task.get("subs"))
        except Exception as e:
            logger.warning(f"problems handling {task}: {e}. sleeping and trying again")
            await asyncio.sleep(3)
            await queue.put({"message": task.get("message"), "subs": task.get("subs")})


async def noun_listener(queue: Queue):
    for i in range(NO_CONSUMERS):
        asyncio.ensure_future(consumer(queue))

    while True:
        try:
            await setup_auction()
            async with websockets.connect(settings.W3_WS_PROVIDER_URL) as websocket:
                retries = 0
                subs_dict = await create_subscriptions(websocket)

                async for str_message in websocket:
                    message = json.loads(str_message)
                    await q.put({"message": message, "subs": subs_dict})

        except (ConnectionClosedError, asyncio.TimeoutError):
            if retries == 0:
                retries += 1
                continue
            if retries >= 10:
                raise Exception("Connection to websocket %s failed > 10 times")

            retries += 1
            backoff = max(3, min(60, 2**retries))
            logger.info(f"Connection to websocket was closed, retry in {backoff} seconds. ({retries} attempts)")
            await asyncio.sleep(backoff)
        except CancelledError:
            return


def shutdown(loop):
    logging.info("received stop signal, cancelling tasks...")
    for task in asyncio.all_tasks():
        task.cancel()


q = Queue()
loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGHUP, functools.partial(shutdown, loop))
loop.add_signal_handler(signal.SIGTERM, functools.partial(shutdown, loop))
loop.add_signal_handler(signal.SIGINT, functools.partial(shutdown, loop))

try:
    loop.run_until_complete(noun_listener(q))
finally:
    loop.close()
