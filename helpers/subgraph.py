import logging

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

logging.getLogger("gql").setLevel(logging.WARN)

NOUNS_SUBGRAPH_ENDPOINT = "https://api.thegraph.com/subgraphs/name/nounsdao/nouns-subgraph"


class NounsSubgraphClient:
    def __init__(self):
        self.client = Client(transport=AIOHTTPTransport(url=NOUNS_SUBGRAPH_ENDPOINT))

    async def get_bid(self, transaction_hash: str):
        async with self.client as session:
            query = gql(
                """
                query Bid ($id: ID!) {
                  bid(id: $id) {
                    id
                    amount
                  }
                }
                """
            )

            result = await session.execute(query, variable_values={"id": transaction_hash})
            return result.get("bid")
