"""What kind of device somebody joined from, as a category and never as a fingerprint.

Two things are being protected here. That the categories are useful — an iPad counted as a Mac
makes the tablet figure a fiction — and that the User-Agent header itself never reaches the
database, because it carries browser build, engine version and often the exact model, which
together identify a person far better than anything else stored.
"""
import pytest

from src.models.salon_event import SalonEvent
from src.models.salon import Salon
from src.models.user import User
from src.services import device_service, salon_event_service

MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
IPAD_OLD = "Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X) AppleWebKit/605.1.15"
ANDROID_PHONE = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari"
ANDROID_TABLET = "Mozilla/5.0 (Linux; Android 13; SM-X710) AppleWebKit/537.36 Safari"
WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
CHROMEBOOK = "Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 Chrome/120"


@pytest.fixture
def salon(db):
    user = User(email="dev@example.com")
    db.add(user)
    db.commit()
    s = Salon(
        host_user_id=user.id,
        livekit_room_name="salon-dev",
        source_type="url",
        source_content="c",
        status="active",
    )
    db.add(s)
    db.commit()
    return s


# ─── Reading the header ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "agent,expected",
    [
        (IPHONE, "iphone"),
        (IPAD_OLD, "ipad"),
        (ANDROID_PHONE, "android-phone"),
        (ANDROID_TABLET, "android-tablet"),
        (WINDOWS, "windows"),
        (CHROMEBOOK, "chromeos"),
        (LINUX, "linux"),
        (MAC, "mac"),
    ],
)
def test_the_ordinary_headers_are_classified(agent, expected):
    assert device_service.classify(agent) == expected


def test_an_android_tablet_is_not_called_linux():
    """Every Android header contains "Linux", so checking Linux first would put every Android
    device in the desktop column."""
    assert device_service.classify(ANDROID_TABLET) == "android-tablet"


def test_an_iphone_is_not_called_a_mac():
    """The iPhone header contains "like Mac OS X"."""
    assert device_service.classify(IPHONE) == "iphone"


def test_a_chromebook_is_not_called_linux():
    assert device_service.classify(CHROMEBOOK) == "chromeos"


def test_no_header_is_unknown_rather_than_a_guess():
    assert device_service.classify(None) == ""
    assert device_service.classify("") == ""
    assert device_service.classify("something nobody has ever sent") == ""


# ─── The iPad, which is the whole reason the client decides ──────────────────

def test_a_modern_ipad_is_indistinguishable_from_a_mac_in_the_header():
    """Not a bug in the classifier — a fact about iPadOS, and the reason the browser is asked.

    Safari has sent a desktop header since iPadOS 13. If this ever starts returning "ipad" the
    header gained something to go on, and the client-side detection could be simplified.
    """
    assert device_service.classify(MAC) == "mac"


def test_the_client_settles_it_when_the_header_cannot():
    """The page checks maxTouchPoints, which a real Mac reports as zero."""
    assert device_service.resolve("ipad", MAC) == "ipad"
    assert device_service.resolve("mac", MAC) == "mac"


def test_the_header_answers_when_the_client_says_nothing():
    assert device_service.resolve(None, IPHONE) == "iphone"
    assert device_service.resolve("", IPHONE) == "iphone"


def test_a_category_nobody_recognises_falls_back_to_the_header():
    """The vocabulary is closed so a client cannot turn the column into free text — a count is
    only useful if everybody spells the categories the same way."""
    assert device_service.resolve("SuperPhone 9000", WINDOWS) == "windows"
    assert device_service.resolve("<script>", WINDOWS) == "windows"


def test_a_claim_is_accepted_whatever_the_case():
    assert device_service.resolve("IPhone", None) == "iphone"
    assert device_service.resolve("  ipad  ", None) == "ipad"


def test_every_category_the_clients_can_send_is_accepted():
    """The web and mobile classifiers must not produce a value the server throws away."""
    from_clients = {
        "ipad", "iphone", "mac", "windows", "linux", "chromeos",
        "android-phone", "android-tablet", "phone", "tablet",
    }
    assert from_clients <= device_service.KNOWN


# ─── What reaches the database ───────────────────────────────────────────────

def test_the_category_is_stored_on_the_participation(db, salon):
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type="iphone",
    )
    assert db.query(SalonEvent).one().device_type == "iphone"


def test_the_user_agent_itself_never_reaches_the_row(db, salon):
    """The point of the whole module. A header passed straight through would be a fingerprint
    sitting in a table, and this is what stops one arriving by accident."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type=IPHONE,
    )
    row = db.query(SalonEvent).one()
    assert row.device_type == "", "an unrecognised value is dropped, not stored"
    assert "Mozilla" not in row.device_type


def test_no_device_is_an_empty_string_not_null(db, salon):
    """A telephone participant has no device in this sense at all, and the sibling columns use
    the same convention: absent is a value that compares."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com", user_type="host", salon_name=salon.livekit_room_name
    )
    assert db.query(SalonEvent).one().device_type == ""


def test_a_device_learned_on_re_entry_is_filled_in(db, salon):
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com", user_type="host", salon_name=salon.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type="windows",
    )
    assert db.query(SalonEvent).one().device_type == "windows"


def test_rejoining_from_another_device_does_not_rewrite_the_first(db, salon):
    """One participation, one device: the interesting one is what they arrived on. Someone who
    switches from laptop to phone mid-salon is one participation, not two devices."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type="mac",
    )
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type="iphone",
    )
    assert db.query(SalonEvent).one().device_type == "mac"


def test_an_unusable_device_never_costs_the_participation(db, salon):
    """Same rule as the position: failing to note something must not keep anyone out."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_type="nonsense",
    )
    assert db.query(SalonEvent).count() == 1


# ─── The device token, and what it refuses ───────────────────────────────────
#
# It lands in an indexed column and arrives in a request body, so it is validated rather than
# trusted. Anything that is not the UUID a client should send is not a token.

def test_a_uuid_is_kept(db, salon):
    token = "66666666-6666-4666-8666-666666666666"
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_token=token,
    )
    assert db.query(SalonEvent).one().device_token == token


@pytest.mark.parametrize(
    "bad",
    ["", "not-a-uuid", "<script>alert(1)</script>", "1" * 36, "a" * 200],
)
def test_anything_that_is_not_a_uuid_is_dropped(db, salon, bad):
    """Dropped rather than stored: this column is indexed and queried by value, and it must not
    become a place to put arbitrary text."""
    salon_event_service.record_entry(
        db,
        participant_identity="test-identity",
        email="dev@example.com",
        user_type="host",
        salon_name=salon.livekit_room_name,
        device_token=bad,
    )
    assert db.query(SalonEvent).one().device_token == ""


def test_a_token_is_not_replaced_on_re_entry(db, salon):
    """One participation came from one browser. A later call from another would be a different
    participation, not a correction of this one."""
    first = "77777777-7777-4777-8777-777777777777"
    second = "88888888-8888-4888-8888-888888888888"
    for token in (first, second):
        salon_event_service.record_entry(
            db,
            participant_identity="test-identity",
            email="dev@example.com",
            user_type="host",
            salon_name=salon.livekit_room_name,
            device_token=token,
        )
    assert db.query(SalonEvent).one().device_token == first
