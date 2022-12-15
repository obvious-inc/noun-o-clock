import logging
from decimal import Decimal
from typing import Union

import requests

import settings
from helpers.w3 import get_wallet_short_name

logger = logging.getLogger(__name__)


async def create_message(data):
    response = requests.post(settings.NS_WEBHOOK_URL, json=data)
    if not response.ok:
        logger.error(f"problems creating message via webhook: {response.status_code} {response.text}")


async def create_finalized_auction_message(noun_id: str, bidder: str, amount: Union[int, Decimal]):
    bidder = await get_wallet_short_name(address=bidder)
    data = {
        "blocks": [
            {
                "type": "paragraph",
                "children": [
                    {"text": f"{bidder} is the owner of noun {noun_id} at "},
                    {"text": f"Ξ{amount:.2f}", "bold": True},
                ],
            }
        ]
    }

    await create_message(data)


async def create_new_auction_message(noun_id: str, image_url: str):
    new_auction_message = {
        "type": "paragraph",
        "children": [
            {"text": f"Noun {noun_id}", "bold": True},
            {"text": " has been minted."},
        ],
    }

    data = {
        "blocks": [
            new_auction_message,
            {
                "type": "attachments",
                "children": [{"type": "image-attachment", "url": image_url, "width": 320, "height": 320}],
            },
            {
                "type": "paragraph",
                "children": [
                    {
                        "type": "link",
                        "url": f"https://nouns.wtf/noun/{noun_id}",
                        "children": [{"text": f"https://nouns.wtf/noun/{noun_id}"}],
                    }
                ],
            },
        ],
    }
    await create_message(data)


async def new_bid_message(amount, bidder, bid_note=None, stats_text=None):
    bidder = await get_wallet_short_name(address=bidder)

    bid_message = [{"text": f"Ξ{amount:.2f} bid from "}, {"text": f"{bidder}", "bold": True}]
    if stats_text and stats_text != "":
        bid_message.append({"text": f"\n[{stats_text}]", "italic": True})

    blocks = [
        {
            "type": "paragraph",
            "children": bid_message,
        }
    ]

    if bid_note and bid_note != "":
        blocks.append(
            {
                "type": "paragraph",
                "children": [
                    {"text": "> "},
                    {"text": f'"{bid_note}"', "italic": True},
                ],
            }
        )

    data = {"blocks": blocks}
    await create_message(data)


async def new_pending_bid_message(amount, bidder):
    bidder = await get_wallet_short_name(address=bidder)
    blocks = [
        {
            "type": "paragraph",
            "children": [{"italic": True, "text": f"pending Ξ{amount:.2f} bid from {bidder}..."}],
        }
    ]

    data = {"blocks": blocks}
    await create_message(data)


async def new_pending_settlement_message(settler):
    settler = await get_wallet_short_name(address=settler)
    blocks = [
        {
            "type": "paragraph",
            "children": [
                {"italic": True, "text": f"{settler} is trying to manually settle the auction!"},
                {"text": " 🚨 rug alert 🚨"},
            ],
        }
    ]

    data = {"blocks": blocks}
    await create_message(data)
