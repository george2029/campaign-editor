"""Traffic split between the offers of one flow.

Shares are whole percents and the shares of the offers still in the flow
always add up to 100. Pinned offers keep the share they have; removed offers
get 0; everyone else splits what is left evenly. When it doesn't divide
evenly, the first offers in the list get one extra percent each
(3 offers -> 34 / 33 / 33).
"""

from pydantic import BaseModel


class OfferShare(BaseModel):
    offer_id: int
    share: int = 0
    pinned: bool = False
    removed: bool = False


class SharesError(ValueError):
    pass


def rebalance(offers: list[OfferShare]) -> list[OfferShare]:
    active = [o for o in offers if not o.removed]
    if not active:
        raise SharesError("The flow needs at least one offer")

    pinned = [o for o in active if o.pinned]
    free = [o for o in active if not o.pinned]

    for o in pinned:
        if not 0 <= o.share <= 100:
            raise SharesError(f"Offer {o.offer_id}: share must be between 0 and 100")

    left = 100 - sum(o.share for o in pinned)
    if left < 0:
        raise SharesError(f"Pinned offers take {100 - left}%, more than 100%")
    if not free and left != 0:
        raise SharesError(f"All offers are pinned and add up to {100 - left}%, not 100%")

    result = []
    free_index = 0
    for o in offers:
        if o.removed:
            share = 0
        elif o.pinned:
            share = o.share
        else:
            # Even split, the first `left % len(free)` offers get +1.
            share = left // len(free) + (1 if free_index < left % len(free) else 0)
            free_index += 1
        result.append(o.model_copy(update={"share": share}))
    return result


def check_ready_to_push(offers: list[OfferShare]) -> None:
    """The final split we send to Keitaro must be valid as is."""
    active = [o for o in offers if not o.removed]
    if not active:
        raise SharesError("The flow needs at least one offer")
    total = sum(o.share for o in active)
    if total != 100:
        raise SharesError(f"Shares add up to {total}%, not 100%")
    if len({o.offer_id for o in active}) != len(active):
        raise SharesError("The same offer is in the flow twice")
