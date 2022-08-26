import logging
import random
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
    celebrating_gifs = [
        ("https://c.tenor.com/PeCmi116QoMAAAAC/celebration-yay.gif", 498, 241),
        ("https://c.tenor.com/Lbrr3HR3CnkAAAAd/snoop-dogg-rap.gif", 314, 498),
        ("https://c.tenor.com/RdepuTw_kK0AAAAC/happy-dancing.gif", 498, 373),
        ("https://c.tenor.com/WdBls8CGwUEAAAAC/lets-celebrate-dance.gif", 466, 498),
        ("https://c.tenor.com/2butBxs8FYkAAAAC/celebrate-happy.gif", 498, 373),
        ("https://c.tenor.com/VUwAmiXWcOoAAAAC/happy-happy-dance.gif", 200, 242),
        ("https://c.tenor.com/HKmiQDvMdewAAAAC/nouns-nounish.gif", 498, 245),
        ("https://c.tenor.com/NyJKBEzDNkcAAAAC/nouns-nounish.gif", 498, 498),
        ("https://c.tenor.com/9JPzcRO625QAAAAd/nouns-nounsdao.gif", 462, 498),
        ("https://c.tenor.com/pxpHOiXiFD8AAAAC/nouns-nounsdao.gif", 498, 284),
    ]
    picked_gif = random.choice(celebrating_gifs)

    end_messages = [
        [
            {"text": f"{bidder} is the proud owner of noun {noun_id}! "},
            {"text": f"Ξ{amount:.2f}", "bold": True},
        ],
        [
            {"text": f"Auction for noun {noun_id} ended. Winner was {bidder} with their "},
            {"text": f"Ξ{amount:.2f}", "bold": True},
            {"text": f" bid."},
        ],
    ]

    data = {
        "blocks": [
            {"type": "paragraph", "children": random.choice(end_messages)},
            {
                "type": "attachments",
                "children": [
                    {
                        "type": "image-attachment",
                        "url": picked_gif[0],
                        "width": picked_gif[1],
                        "height": picked_gif[2],
                    }
                ],
            },
        ]
    }

    await create_message(data)


async def create_new_auction_message(noun_id: str, image_url: str):
    new_auction_choices = [
        {
            "type": "paragraph",
            "children": [
                {"text": "Auction for "},
                {"text": f"Noun {noun_id}", "bold": True},
                {"text": " started:"},
            ],
        },
        {
            "type": "paragraph",
            "children": [{"text": f"New noun in the block: 🙇 Noun {noun_id} 🙇"}],
        },
        {
            "type": "paragraph",
            "children": [{"text": f"Noun {noun_id} has just been minted, let the games begin!"}],
        },
    ]
    new_auction_message = random.choice(new_auction_choices)

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


async def new_bid_message(amount, bidder, bid_note=None):
    bidder = await get_wallet_short_name(address=bidder)
    bid_message_choices = [
        [
            {"text": f"New Ξ{amount:.2f} bid from "},
            {"text": f"{bidder}", "bold": True},
        ],
        [
            {"text": f"{bidder}", "bold": True},
            {"text": f" coming in hot with their Ξ{amount:.2f} bid!"},
        ],
        [
            {"text": f"{bidder}", "bold": True},
            {"text": f" is the new high-bidder! Ξ{amount:.2f}"},
        ],
    ]

    blocks = [
        {
            "type": "paragraph",
            "children": random.choice(bid_message_choices),
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
