import pytest

from app.shares import OfferShare, SharesError, check_ready_to_push, rebalance


def shares(offers):
    return [o.share for o in offers]


def make(*specs):
    """make(1, 2, 3) -> plain offers; pass dicts for pinned/removed ones."""
    result = []
    for i, spec in enumerate(specs):
        if isinstance(spec, dict):
            result.append(OfferShare(offer_id=i + 1, **spec))
        else:
            result.append(OfferShare(offer_id=i + 1, share=spec))
    return result


def test_single_offer_gets_everything():
    assert shares(rebalance(make(0))) == [100]


def test_even_split():
    assert shares(rebalance(make(0, 0))) == [50, 50]
    assert shares(rebalance(make(0, 0, 0, 0))) == [25, 25, 25, 25]


def test_remainder_goes_to_first_offers():
    assert shares(rebalance(make(0, 0, 0))) == [34, 33, 33]
    assert shares(rebalance(make(0, 0, 0, 0, 0, 0))) == [17, 17, 17, 17, 16, 16]


def test_adding_an_offer_rebalances():
    # 34/33/33 + a new offer -> 25 each (as in the video)
    assert shares(rebalance(make(34, 33, 33, 0))) == [25, 25, 25, 25]


def test_removed_offer_gets_zero_and_others_take_its_share():
    offers = make(25, 25, {"share": 25, "removed": True}, 25)
    assert shares(rebalance(offers)) == [34, 33, 0, 33]


def test_pinned_offer_keeps_its_share():
    # One offer pinned at 25%, two free ones split 75 -> 38/37 (as in the video)
    offers = make(0, 0, {"share": 25, "pinned": True})
    assert shares(rebalance(offers)) == [38, 37, 25]


def test_removed_pinned_offer_frees_its_share():
    offers = make(0, {"share": 40, "pinned": True, "removed": True}, 0)
    assert shares(rebalance(offers)) == [50, 0, 50]


def test_pinned_over_100_is_an_error():
    offers = make({"share": 60, "pinned": True}, {"share": 50, "pinned": True}, 0)
    with pytest.raises(SharesError):
        rebalance(offers)


def test_all_pinned_must_add_up_to_100():
    ok = make({"share": 70, "pinned": True}, {"share": 30, "pinned": True})
    assert shares(rebalance(ok)) == [70, 30]
    bad = make({"share": 70, "pinned": True}, {"share": 20, "pinned": True})
    with pytest.raises(SharesError):
        rebalance(bad)


def test_pinned_at_100_leaves_zero_for_others():
    offers = make({"share": 100, "pinned": True}, 0, 0)
    assert shares(rebalance(offers)) == [100, 0, 0]


def test_all_removed_is_an_error():
    with pytest.raises(SharesError):
        rebalance(make({"removed": True}))


def test_result_always_adds_up_to_100():
    for n in range(1, 30):
        for pinned_share in (0, 1, 33, 99):
            offers = make({"share": pinned_share, "pinned": True}, *[0] * n)
            assert sum(shares(rebalance(offers))) == 100


def test_check_ready_to_push():
    check_ready_to_push(make(50, 50, {"share": 0, "removed": True}))
    with pytest.raises(SharesError):
        check_ready_to_push(make(50, 40))
    with pytest.raises(SharesError):
        check_ready_to_push([OfferShare(offer_id=1, share=50), OfferShare(offer_id=1, share=50)])
