"""POST /salons/{salon_id}/ad — the one HTTP surface for the auction (Story 8.4 / FR69).

Mode B and Mode C sell no advertising, for a rate the auction's own revenue does not have to
cover. Nothing here enforced that before this file existed: the auction ran for every Salon
regardless of what its host paid for, so a host on Mode C — "no advertising" — got exactly the
same pitch a Base host did. That gap is what these tests hold shut.
"""
from unittest.mock import patch

import pytest

from src.models.ad import Ad
from src.models.advertiser import Advertiser
from src.models.salon import Salon
from src.models.user import User
from src.services import ad_billing_service
from src.services.jwt_service import issue_token


@pytest.fixture
def host(db):
    u = User(email="adrequesthost@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, issue_token(str(u.id))


def _salon(db, host_user, *, host_tier=None):
    s = Salon(
        host_user_id=host_user.id,
        livekit_room_name="salon-ad-request",
        source_type="url",
        source_content="c",
        status="active",
        host_tier=host_tier,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("tier", [None, "Base", "Mode A"])
def test_ad_supported_tiers_still_reach_the_auction(client, db, host, tier):
    """Not asserting a pitch — the auction may still find nothing eligible — only that a
    tier which sells advertising is not turned away before the auction gets to decide."""
    host_user, token = host
    salon = _salon(db, host_user, host_tier=tier)
    with patch(
        "src.routers.salons.ad_auction_service.broadcast_winner", return_value=None
    ) as auction:
        resp = client.post(f"/salons/{salon.id}/ad", headers=_auth(token))
    assert resp.status_code == 200
    auction.assert_called_once()


@pytest.mark.parametrize("tier", ["Mode B", "Mode C"])
def test_ad_free_tiers_never_reach_the_auction(client, db, host, tier):
    host_user, token = host
    salon = _salon(db, host_user, host_tier=tier)
    with patch(
        "src.routers.salons.ad_auction_service.broadcast_winner"
    ) as auction:
        resp = client.post(f"/salons/{salon.id}/ad", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json() == {"pitch": "", "reason": "tier_excludes_ads"}
    auction.assert_not_called()


def test_a_second_ad_request_is_refused_before_the_tier_is_even_checked(client, db, host):
    """already_broadcast outranks the tier check: a Base Salon that already spent its one
    broadcast must not get a second because nothing else told it no."""
    host_user, token = host
    salon = _salon(db, host_user, host_tier="Base")

    advertiser = Advertiser(company="Café Rivard", email="ads@caferivard.example")
    db.add(advertiser)
    db.commit()
    db.refresh(advertiser)
    ad = Ad(
        advertiser_id=advertiser.advertiser_id,
        sales_pitch="Come for the coffee.",
        number_of_broadcasts_left=3,
        topic="coffee",
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    ad_billing_service.record_broadcast(db, ad=ad, salon=salon)

    with patch("src.routers.salons.ad_auction_service.broadcast_winner") as auction:
        resp = client.post(f"/salons/{salon.id}/ad", headers=_auth(token))
    assert resp.json() == {"pitch": "", "reason": "already_broadcast"}
    auction.assert_not_called()
