import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

NOUN_O_CLOCK_ENDPOINT = "https://noc-app-prod.herokuapp.com"


async def get_bid_notes(noun_id, bidder_address, bidder_weth) -> Optional[str]:
    notes_endpoint = f"{NOUN_O_CLOCK_ENDPOINT}/notes/{noun_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(notes_endpoint) as response:
            if not response.ok:
                text = await response.text()
                logger.warning(f"problem with response: {response.status} {text}")
                response.raise_for_status()

            json_resp = await response.json()
            logger.info(f"noun-o-clock app response: {json_resp}")
            note_id = f"{noun_id}-{bidder_address.lower()}-{bidder_weth}"

            note = json_resp.get(note_id, None)
            return note
