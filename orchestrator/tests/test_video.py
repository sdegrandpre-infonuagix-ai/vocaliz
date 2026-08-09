"""Video, muted, live.

It exists because the topology took something away. Nobody hears anybody's real voice any
more — every sentence arrives spoken by a model — so the oldest proof of identity there is,
recognising somebody by how they sound, is gone. Seeing them gives it back.

Everything else follows from that being the *only* job. It carries no sound, it travels a
path of its own so the absence of shared audio stays intact, it is never recorded, it is
off until somebody asks for it, and it is the first thing dropped when the connection
cannot carry everything.
"""
import pytest

from src.interprete import InterpreteFake, Participant
from src.journal import InMemoryJournalStore, SalonLog
from src.salon import (
    MAX_VIDEO_BITRATE_KBPS,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    InMemoryRoomProvisioner,
    InMemoryVideoPath,
    Salon,
)

MARIE = Participant(id="marie", language="fr", name="Marie")
HANS = Participant(id="hans", language="de", name="Hans")
# FR57. Reached the Salon by telephone: no camera, no screen, nothing to send or show.
CALLER = Participant(id="+15145550123", language="en", by_telephone=True)


async def translate(text, *, source, target):
    return f"{text} [{target}]"


@pytest.fixture
def video():
    return InMemoryVideoPath()


@pytest.fixture
def salon(video):
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    return Salon(log=log, rooms=InMemoryRoomProvisioner(), video=video)


async def _join(salon, participant, **kwargs):
    return await salon.join(participant, InterpreteFake(participant=participant), **kwargs)


# ── Off until somebody asks ───────────────────────────────────────────────────


async def test_video_is_off_when_somebody_joins(salon):
    """Opt-in, always. A camera that comes on by itself is a camera nobody consented to."""
    await _join(salon, MARIE)

    assert salon.video_on(MARIE.id) is False
    assert salon.publishing_video == ()


async def test_a_participant_can_turn_it_on(salon):
    await _join(salon, MARIE)

    await salon.enable_video(MARIE.id)

    assert salon.video_on(MARIE.id) is True
    assert salon.publishing_video == ("marie",)


async def test_a_participant_can_turn_it_off_again_at_any_moment(salon):
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.disable_video(MARIE.id)

    assert salon.video_on(MARIE.id) is False


async def test_turning_it_on_twice_publishes_one_track(salon, video):
    await _join(salon, MARIE)

    await salon.enable_video(MARIE.id)
    await salon.enable_video(MARIE.id)

    assert len(video.published) == 1


async def test_turning_it_off_when_it_was_never_on_is_harmless(salon):
    await _join(salon, MARIE)

    await salon.disable_video(MARIE.id)

    assert salon.video_on(MARIE.id) is False


async def test_somebody_who_is_not_here_has_no_video(salon):
    await salon.enable_video("nobody")

    assert salon.publishing_video == ()


async def test_leaving_takes_the_video_with_it(salon, video):
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.leave(MARIE.id)

    assert salon.publishing_video == ()
    assert video.published == ()


# ── No sound, and a path of its own ───────────────────────────────────────────


async def test_a_video_track_carries_no_audio(salon, video):
    """The whole promise in one assertion. Audio stays entirely in the interpreters' path;
    video never opens a second sound channel."""
    await _join(salon, MARIE)

    await salon.enable_video(MARIE.id)

    (track,) = video.tracks
    assert track.audio is False


async def test_video_does_not_travel_through_the_interpretation_rooms(salon, video):
    """A separate media path, so the absence of shared audio between participants stays
    intact and echo stays impossible by construction rather than by care."""
    await _join(salon, MARIE)
    room = await salon.room_of(MARIE.id)

    await salon.enable_video(MARIE.id)

    (track,) = video.tracks
    assert track.name != room.name


async def test_the_video_path_is_named_for_the_salon_not_the_room(salon, video):
    await _join(salon, MARIE)
    await _join(salon, HANS)

    await salon.enable_video(MARIE.id)
    await salon.enable_video(HANS.id)

    assert len({track.name for track in video.tracks}) == 2


# ── Never kept ────────────────────────────────────────────────────────────────


async def test_nothing_of_the_video_is_recorded(salon, video):
    """Lived live and then lost. NFR8 does not reach it: the text journal is what a
    takeover needs and what proves an advertisement was broadcast."""
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.aclose()

    assert video.recorded == ()


async def test_the_video_path_has_no_way_to_record(video):
    """Stated as an absence, which is the only way to state it: there is no method that
    could keep a frame."""
    import inspect

    surface = {name for name, _ in inspect.getmembers(type(video), callable)}
    forbidden = ("record", "save", "persist", "store", "archive")

    assert [n for n in surface if any(word in n.lower() for word in forbidden)] == []


# ── A vignette, and no more ───────────────────────────────────────────────────


def test_the_bitrate_is_capped_explicitly():
    """Never the SDK default, which climbs to 720p and multiplies the cost by seven for a
    job a thumbnail already does."""
    assert MAX_VIDEO_BITRATE_KBPS == 200
    assert VIDEO_HEIGHT == 240
    assert VIDEO_FPS == 15


async def test_every_track_is_published_at_the_cap(salon, video):
    await _join(salon, MARIE)

    await salon.enable_video(MARIE.id)

    (track,) = video.tracks
    assert track.bitrate_kbps == MAX_VIDEO_BITRATE_KBPS
    assert track.height == VIDEO_HEIGHT


# ── A telephone participant ───────────────────────────────────────────────────


async def test_a_telephone_participant_has_no_video_either_way(salon):
    """FR57. No camera and no screen: there is nothing to send and nothing to show."""
    await _join(salon, CALLER)

    await salon.enable_video(CALLER.id)

    assert salon.video_on(CALLER.id) is False
    assert salon.receives_video(CALLER.id) is False


async def test_the_others_are_told_a_participant_is_on_the_telephone(salon):
    """Otherwise their black tile reads as somebody who chose not to be seen, which is a
    different thing and invites a different judgement."""
    await _join(salon, MARIE)

    await _join(salon, CALLER)

    annonces = [
        line.text
        for line in salon.interpreter_of(MARIE.id).spoken
        if line.kind == "annonce"
    ]
    assert annonces != []


async def test_nobody_is_told_about_a_participant_who_is_not_on_the_telephone(salon):
    await _join(salon, MARIE)

    await _join(salon, HANS)

    assert salon.interpreter_of(MARIE.id).spoken == []


# ── An independent layer ──────────────────────────────────────────────────────


async def test_a_salon_where_only_some_have_video_works_normally(salon):
    """Nothing depends on it. A Salon with no video at all is the same Salon."""
    await _join(salon, MARIE)
    await _join(salon, HANS)
    await salon.enable_video(MARIE.id)

    await salon.ingest(MARIE.id, "Bonjour", language="fr")
    await salon.deliver_all()

    tours = [line for line in salon.interpreter_of(HANS.id).spoken if line.kind == "tour"]
    assert [line.text for line in tours] == ["Bonjour"]


async def test_a_salon_with_no_video_path_at_all_still_runs():
    """The layer is optional. A deployment without it loses the pictures and nothing else."""
    log = SalonLog(salon_id="salon-1", store=InMemoryJournalStore(), translate=translate)
    salon = Salon(log=log, rooms=InMemoryRoomProvisioner())
    await _join(salon, MARIE)

    await salon.enable_video(MARIE.id)

    assert salon.video_on(MARIE.id) is False
    assert len(await salon.ingest(MARIE.id, "Bonjour", language="fr")) == 1


# ── Driving mode, and a failing connection ────────────────────────────────────


async def test_driving_mode_suspends_video_in_both_directions(salon):
    """FR75. The screen is black, so there is nothing to look at — and a camera pointed at
    a windscreen is of no use to anybody."""
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.start_driving(MARIE.id)

    assert salon.video_on(MARIE.id) is False
    assert salon.receives_video(MARIE.id) is False


async def test_leaving_driving_mode_gives_back_what_was_on_before(salon):
    """Restored, not reset. Somebody who had their camera on before the drive did not
    choose to turn it off."""
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)
    await salon.start_driving(MARIE.id)

    await salon.stop_driving(MARIE.id)

    assert salon.video_on(MARIE.id) is True


async def test_leaving_driving_mode_does_not_turn_on_a_camera_nobody_asked_for(salon):
    await _join(salon, MARIE)
    await salon.start_driving(MARIE.id)

    await salon.stop_driving(MARIE.id)

    assert salon.video_on(MARIE.id) is False


async def test_video_cannot_be_turned_on_while_driving(salon):
    await _join(salon, MARIE)
    await salon.start_driving(MARIE.id)

    await salon.enable_video(MARIE.id)

    assert salon.video_on(MARIE.id) is False


async def test_video_is_dropped_before_audio_when_the_connection_cannot_carry_both(salon):
    """Always, and in that order. A conversation without pictures is still a conversation;
    pictures without a conversation are nothing."""
    await _join(salon, MARIE)
    await salon.enable_video(MARIE.id)

    await salon.shed_video(MARIE.id)

    assert salon.video_on(MARIE.id) is False
    assert MARIE.id in salon.participants
    assert len(await salon.ingest(MARIE.id, "toujours là", language="fr")) == 1


# ── Somebody who is not here ──────────────────────────────────────────────────


async def test_the_video_controls_are_silent_about_somebody_who_is_not_here(salon):
    """A dropped connection is often reported twice, and a control arriving for somebody
    who has already left must not take the Salon down with it."""
    await salon.disable_video("nobody")
    await salon.start_driving("nobody")
    await salon.stop_driving("nobody")
    await salon.shed_video("nobody")

    assert salon.participants == ()
    assert salon.receives_video("nobody") is False
