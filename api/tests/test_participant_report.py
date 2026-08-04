"""The hourly participant report.

Eight columns, and two of them are weaker than they look. The tests below pin exactly how
weak, because a report that overstates its own precision is worse than no report: somebody
would make a decision on it.

  Pays      the browser's locale region, self-reported by the device.
  Secondes  metered time on the account, not the sum of the participations listed beside it.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.salon_event import SalonEvent
from src.models.user import User
from src.services import participant_report

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _event(db, email, salon, **kw):
    db.add(
        SalonEvent(
            # Stable per person by default, which is how a host behaves: they join every
            # salon as their own account UUID, so their salons aggregate into one line. A test
            # about several identities passes them explicitly.
            participant_identity=kw.pop("identity", email),
            email=email,
            user_type=kw.pop("role", "host"),
            salon_name=salon,
            entered_at=kw.pop("entered", NOW),
            first_spoken_language=kw.pop("language", None),
            device_type=kw.pop("device", ""),
            device_token=kw.pop("token", ""),
            country=kw.pop("country", ""),
        )
    )
    db.commit()


# ─── What is in it ───────────────────────────────────────────────────────────

def test_the_columns_are_the_eight_asked_for_plus_three(db):
    """Eight were requested. Two more were added deliberately, and both answer a question that
    had no answer:

      Micro                    separates a host who never tried to speak from one who tried and
                               was not heard — the open question about the first real users.
      Salons de cet appareil   separates a returning anonymous visitor from a new one, which an
                               invitation-derived identity cannot do on its own.
      Identité                 the row's key, and the only thing that tells two anonymous
                               guests apart — "Contact" reads the same for both.

    Pinned here so the additions stay visible rather than being something a reader has to
    notice."""
    _event(db, "a@example.com", "salon-a")
    row = participant_report.collect(db)[0]
    assert list(row.keys()) == participant_report.COLUMNS
    assert participant_report.COLUMNS == [
        "Contact",
        "Identité",
        "Rôle",
        "Salons",
        "Langue",
        "Appareil",
        "Pays",
        "Vu en dernier",
        "Secondes cumulées",
        "Micro",
        "Salons de cet appareil",
    ]


def test_one_row_per_person_across_their_salons(db):
    _event(db, "a@example.com", "salon-a")
    _event(db, "a@example.com", "salon-b", role="guest")
    rows = participant_report.collect(db)
    assert len(rows) == 1
    assert rows[0]["Salons"] == 2
    assert rows[0]["Rôle"] == "guest + host"


def test_devices_and_countries_accumulate(db):
    """Somebody who hosts from a laptop and joins from a phone is both, and a report that kept
    only the last would answer a question nobody asked."""
    _event(db, "a@example.com", "salon-a", device="windows", country="CA")
    _event(db, "a@example.com", "salon-b", device="iphone", country="FR")
    row = participant_report.collect(db)[0]
    assert row["Appareil"] == "iphone, windows"
    assert row["Pays"] == "CA, FR"


def test_the_most_recent_person_comes_first(db):
    _event(db, "old@example.com", "salon-a", entered=NOW)
    _event(db, "new@example.com", "salon-b", entered=NOW + timedelta(hours=2))
    assert participant_report.collect(db)[0]["Contact"] == "new@example.com"


def test_absent_values_read_as_absent_not_as_zero(db):
    """A dash, never a zero or a blank. Zero seconds would claim somebody held conversations of
    no length, which is a different statement from having no account at all."""
    _event(db, "a@example.com", "salon-a")
    row = participant_report.collect(db)[0]
    assert row["Langue"] == "—"
    assert row["Appareil"] == "—"
    assert row["Pays"] == "—"
    assert row["Secondes cumulées"] == "—"


# ─── The metered time, and what it is not ────────────────────────────────────

def test_seconds_come_from_the_account(db):
    user = User(email="a@example.com", trial_seconds_used=600, billed_seconds=120)
    db.add(user)
    db.commit()
    _event(db, "a@example.com", "salon-a")
    assert participant_report.collect(db)[0]["Secondes cumulées"] == 720


def test_a_guest_with_no_account_has_no_seconds(db):
    """Metered time is a property of an account. A guest who never registered has none, and
    inventing a zero would make them look like somebody who talked for no time."""
    _event(db, "guest@example.com", "salon-a", role="guest")
    assert participant_report.collect(db)[0]["Secondes cumulées"] == "—"


def test_the_caveats_travel_with_the_report(db):
    """Both weak columns are named in the body. A reader who takes "Pays" for a measured
    location, or the seconds for the sum of these salons, would be wrong — and the report is
    the only place that can tell them."""
    _event(db, "a@example.com", "salon-a")
    text = participant_report.as_text(participant_report.collect(db))
    assert "region du navigateur" in text
    assert "sur le COMPTE" in text


# ─── Rendering ───────────────────────────────────────────────────────────────

def test_an_empty_report_says_so_rather_than_showing_a_bare_table(db):
    assert "Aucune participation" in participant_report.as_text([])
    assert "Aucune participation" in participant_report.as_html([])


def test_the_html_escapes_what_strangers_supplied(db):
    """These addresses come from anybody who signs up. One landing unescaped in the
    administrator's mail client is an injection into their own inbox."""
    _event(db, "<script>alert(1)</script>@example.com", "salon-a")
    rendered = participant_report.as_html(participant_report.collect(db))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_the_text_table_lines_up(db):
    _event(db, "short@example.com", "salon-a")
    _event(db, "a-much-longer-address@example.com", "salon-b")
    lines = participant_report.as_text(participant_report.collect(db)).split("\n")
    header, rule = lines[2], lines[3]
    assert len(rule) == len(header), "the rule must match the header it underlines"


# ─── Sending ─────────────────────────────────────────────────────────────────

def test_sending_reaches_ses_with_both_parts(db):
    _event(db, "a@example.com", "salon-a")
    client = MagicMock()
    with patch("boto3.client", return_value=client):
        result = participant_report.send(db, "admin@example.com")
    assert result == {"status": "ok", "contacts": 1}
    body = client.send_email.call_args.kwargs["Message"]["Body"]
    # Both parts, because a mail client that refuses the markup must still get the table.
    assert "Text" in body and "Html" in body
    assert client.send_email.call_args.kwargs["Destination"]["ToAddresses"] == [
        "admin@example.com"
    ]


def test_a_failed_send_is_reported_rather_than_raised(db):
    """This runs on a schedule with nobody watching. An exception would surface as a Lambda
    error and tell nobody anything useful; a status can be read in the logs."""
    _event(db, "a@example.com", "salon-a")
    client = MagicMock()
    client.send_email.side_effect = RuntimeError("SES said no")
    with patch("boto3.client", return_value=client):
        result = participant_report.send(db, "admin@example.com")
    assert result["status"] == "send_failed"
    assert result["contacts"] == 1


def test_the_addresses_never_reach_the_log(db, caplog):
    """The report is what carries the personal data. Writing it to CloudWatch as well would
    copy it into a second store with its own retention."""
    _event(db, "private@example.com", "salon-a")
    with patch("boto3.client", return_value=MagicMock()):
        with caplog.at_level("INFO"):
            participant_report.send(db, "admin@example.com")
    assert "private@example.com" not in caplog.text


# ─── The microphone, and the question it answers ─────────────────────────────

def test_a_microphone_that_never_worked_reads_no(db):
    _event(db, "a@example.com", "salon-a")
    assert participant_report.collect(db)[0]["Micro"] == "non"


def test_a_microphone_that_worked_once_reads_yes(db):
    """Ever, not currently: somebody who mutes themselves before leaving has still been heard."""
    db.add(
        SalonEvent(
            participant_identity="a@example.com:salon-a",
            email="a@example.com",
            user_type="host",
            salon_name="salon-a",
            entered_at=NOW,
            microphone_enabled=True,
        )
    )
    db.commit()
    assert participant_report.collect(db)[0]["Micro"] == "oui"


def test_one_working_salon_is_enough_across_several(db):
    """Aggregated like the devices: a host whose microphone worked in one salon and failed in
    another has a microphone that works, and the failure is about that salon."""
    _event(db, "a@example.com", "salon-a")
    db.add(
        SalonEvent(
            # The same identity in a second salon, which is how a host appears: one account,
            # many rooms.
            participant_identity="a@example.com",
            email="a@example.com",
            user_type="host",
            salon_name="salon-b",
            entered_at=NOW,
            microphone_enabled=True,
        )
    )
    db.commit()
    assert participant_report.collect(db)[0]["Micro"] == "oui"


def test_the_two_states_are_distinguishable_in_the_report(db):
    """The whole point. Both rows have no language; only the microphone column separates
    "never tried" from "tried and was not heard"."""
    _event(db, "silent@example.com", "salon-a")
    db.add(
        SalonEvent(
            participant_identity="tried@example.com:salon-b",
            email="tried@example.com",
            user_type="host",
            salon_name="salon-b",
            entered_at=NOW + timedelta(hours=1),
            microphone_enabled=True,
        )
    )
    db.commit()
    rows = {r["Contact"]: r for r in participant_report.collect(db)}
    assert rows["silent@example.com"]["Langue"] == "—"
    assert rows["tried@example.com"]["Langue"] == "—"
    assert rows["silent@example.com"]["Micro"] == "non"
    assert rows["tried@example.com"]["Micro"] == "oui"


def test_how_to_read_it_travels_with_the_report(db):
    _event(db, "a@example.com", "salon-a")
    text = participant_report.as_text(participant_report.collect(db))
    assert "jamais essaye" in text
    assert "sans etre entendu" in text


def test_a_guest_invited_twice_is_two_lines(db):
    """The consequence of keying on the identity, stated so it is a decision and not a surprise.

    A guest gets a fresh identity per invitation, so somebody invited to two salons appears
    twice. That is what the rooms saw: two invitations, two participants, no way to know they
    were the same person unless they gave an address."""
    _event(db, "", "salon-a", identity="guest-111", role="guest")
    _event(db, "", "salon-b", identity="guest-222", role="guest")
    rows = participant_report.collect(db)
    assert len(rows) == 2


def test_an_anonymous_guest_is_shown_by_their_room_label(db):
    """Never a bare UUID. The report has to let somebody recognise who a line is about, and the
    room label is what the other participants actually saw."""
    _event(db, "", "salon-a", identity="guest-3f2a1b6c-0000-4000-8000-000000000000", role="guest")
    contact = participant_report.collect(db)[0]["Contact"]
    assert contact.startswith("Guest ")
    assert "0000-4000" not in contact


# ─── The returning device ────────────────────────────────────────────────────
#
# An anonymous invitation mints a fresh identity every visit, so one person coming back five
# times looked like five people. A random token the browser keeps is what separates them.

def test_a_device_seen_once_reads_one(db):
    _event(db, "", "salon-a", identity="guest-1", role="guest", token="11111111-1111-4111-8111-111111111111")
    assert participant_report.collect(db)[0]["Salons de cet appareil"] == 1


def test_the_same_browser_returning_is_visible(db):
    """Two invitations, two identities, one browser. Without the token these are two strangers;
    with it, they are one visitor who came back."""
    token = "22222222-2222-4222-8222-222222222222"
    _event(db, "", "salon-a", identity="guest-1", role="guest", token=token)
    _event(db, "", "salon-b", identity="guest-2", role="guest", token=token)
    rows = participant_report.collect(db)
    assert len(rows) == 2, "still two participations, which is what the rooms saw"
    assert all(r["Salons de cet appareil"] == 2 for r in rows)


def test_two_browsers_are_not_conflated(db):
    _event(db, "", "salon-a", identity="guest-1", role="guest", token="33333333-3333-4333-8333-333333333333")
    _event(db, "", "salon-b", identity="guest-2", role="guest", token="44444444-4444-4444-8444-444444444444")
    assert all(r["Salons de cet appareil"] == 1 for r in participant_report.collect(db))


def test_no_token_reads_as_absent_not_as_one(db):
    """Private browsing refuses storage, and a telephone participant has no browser at all.
    A 1 there would claim a device was recognised when none was."""
    _event(db, "", "salon-a", identity="guest-1", role="guest")
    assert participant_report.collect(db)[0]["Salons de cet appareil"] == "—"


def test_the_limits_of_the_measure_travel_with_it(db):
    """Somebody reading "3" must know it means three visits from one browser, not from one
    person. The report is the only place that can say so."""
    _event(db, "", "salon-a", identity="guest-1", role="guest", token="55555555-5555-4555-8555-555555555555")
    text = participant_report.as_text(participant_report.collect(db))
    assert "navigateurs" in text
    assert "navigation privee" in text


def test_the_device_count_is_hidden_for_anybody_identified(db):
    """Two accounts signed in on one laptop share a browser token. Attributing its count to
    either of them would credit salons they never attended — so for anybody with contact details
    the column is blank, and Salons answers the question instead."""
    token = "99999999-9999-4999-8999-999999999999"
    _event(db, "one@example.com", "salon-a", identity="acct-1", token=token)
    _event(db, "two@example.com", "salon-b", identity="acct-2", token=token)
    rows = participant_report.collect(db)
    assert all(r["Salons de cet appareil"] == "—" for r in rows)
    # Each account still reports its own salons correctly, which is the honest answer for them.
    assert all(r["Salons"] == 1 for r in rows)


def test_the_device_count_still_shows_for_the_anonymous(db):
    """The case it was built for, and the only one where nothing else can answer."""
    token = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    _event(db, "", "salon-a", identity="guest-a", role="guest", token=token)
    _event(db, "", "salon-b", identity="guest-b", role="guest", token=token)
    assert all(
        r["Salons de cet appareil"] == 2 for r in participant_report.collect(db)
    )


def test_two_anonymous_visitors_on_one_browser_are_irreducibly_conflated(db):
    """Stated as a test because it is a limit, not a bug: nothing distinguishes two people who
    share a browser and give no address. The report says so in its own body."""
    token = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    _event(db, "", "salon-a", identity="guest-x", role="guest", token=token)
    _event(db, "", "salon-b", identity="guest-y", role="guest", token=token)
    rows = participant_report.collect(db)
    assert len(rows) == 2, "two participations, because the rooms saw two"
    assert all(r["Salons de cet appareil"] == 2 for r in rows), "one browser, counted once"
    assert "un meme portable comptent pour un" in participant_report.as_text(rows)
