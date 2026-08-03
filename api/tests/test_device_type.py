"""What kind of device somebody joined from, as a category and never as a fingerprint.

Two things are being protected here. That the categories are useful — an iPad counted as a Mac
makes the tablet figure a fiction — and that the User-Agent header itself never reaches the
database, because it carries browser build, engine version and often the exact model, which
together identify a person far better than anything else stored.
"""
import pytest

from src.models.salon_event import SalonEvent
from src.models.session import SessionModel
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
def session(db):
    user = User(email="dev@example.com")
    db.add(user)
    db.commit()
    s = SessionModel(
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

def test_the_category_is_stored_on_the_participation(db, session):
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type="iphone",
    )
    assert db.query(SalonEvent).one().device_type == "iphone"


def test_the_user_agent_itself_never_reaches_the_row(db, session):
    """The point of the whole module. A header passed straight through would be a fingerprint
    sitting in a table, and this is what stops one arriving by accident."""
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type=IPHONE,
    )
    row = db.query(SalonEvent).one()
    assert row.device_type == "", "an unrecognised value is dropped, not stored"
    assert "Mozilla" not in row.device_type


def test_no_device_is_an_empty_string_not_null(db, session):
    """A telephone participant has no device in this sense at all, and the sibling columns use
    the same convention: absent is a value that compares."""
    salon_event_service.record_entry(
        db, email="dev@example.com", user_type="host", salon_name=session.livekit_room_name
    )
    assert db.query(SalonEvent).one().device_type == ""


def test_a_device_learned_on_re_entry_is_filled_in(db, session):
    salon_event_service.record_entry(
        db, email="dev@example.com", user_type="host", salon_name=session.livekit_room_name
    )
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type="windows",
    )
    assert db.query(SalonEvent).one().device_type == "windows"


def test_rejoining_from_another_device_does_not_rewrite_the_first(db, session):
    """One participation, one device: the interesting one is what they arrived on. Someone who
    switches from laptop to phone mid-salon is one participation, not two devices."""
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type="mac",
    )
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type="iphone",
    )
    assert db.query(SalonEvent).one().device_type == "mac"


def test_an_unusable_device_never_costs_the_participation(db, session):
    """Same rule as the position: failing to note something must not keep anyone out."""
    salon_event_service.record_entry(
        db,
        email="dev@example.com",
        user_type="host",
        salon_name=session.livekit_room_name,
        device_type="nonsense",
    )
    assert db.query(SalonEvent).count() == 1
