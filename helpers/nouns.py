import base64
import json
from datetime import datetime

import settings
from helpers.w3 import get_contract


async def get_noun_metadata(noun_id: str):
    nouns_contract = get_contract(settings.TOKEN_CONTRACT_ADDRESS)
    token_uri = nouns_contract.functions.tokenURI(noun_id).call()
    token_metadata_base64 = token_uri.split(";")[1][7:]
    token_metadata = json.loads(base64.b64decode(token_metadata_base64))
    return token_metadata


async def get_current_auction():
    contract = get_contract(settings.AUCTION_HOUSE_CONTRACT_ADDRESS)
    curr_auction_info = contract.functions.auction().call()
    noun_id, wei_amount, start_time, end_time, bidder, settled = curr_auction_info
    return {
        "noun_id": noun_id,
        "wei_amount": wei_amount,
        "start_time": start_time,
        "end_time": end_time,
        "bidder": bidder,
        "settled": settled,
    }


async def get_curr_auction_remaining_seconds():
    auction = await get_current_auction()
    end_time = auction.get("end_time")
    end_date = datetime.fromtimestamp(end_time)
    seconds_remaining = int((end_date - datetime.now()).total_seconds())
    return seconds_remaining
