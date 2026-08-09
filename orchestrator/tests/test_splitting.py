"""Cutting a long intervention into messages somebody else can get a word into.

The point is not the number. It is that a participant who talks for two minutes without
pausing should not own the conversation for two minutes: the journal is read in order, so
one enormous message is a period during which nobody else can be heard by anybody.

Where the cut falls is the whole craft. A sentence boundary is a place a listener expects
a pause anyway, so the seam is inaudible. Mid-word is never acceptable — it is audibly
broken, and in a language the listener does not read it is unrecoverable.
"""
from src.journal import MAX_MESSAGE_CHARACTERS, split_intervention


def test_a_short_intervention_is_left_whole():
    assert split_intervention("Bonjour tout le monde.") == ("Bonjour tout le monde.",)


def test_nothing_splits_into_nothing():
    assert split_intervention("") == ()
    assert split_intervention("   ") == ()


def test_the_default_is_the_five_hundred_of_the_story():
    assert MAX_MESSAGE_CHARACTERS == 500


def test_no_piece_exceeds_the_maximum():
    text = " ".join(f"Voici la phrase numéro {n}." for n in range(200))

    pieces = split_intervention(text, max_chars=120)

    assert pieces
    assert all(len(piece) <= 120 for piece in pieces)


def test_a_cut_falls_on_a_sentence_boundary():
    text = "Première phrase ici. Deuxième phrase ici. Troisième phrase ici."

    pieces = split_intervention(text, max_chars=45)

    assert all(piece.endswith((".", "!", "?", "…")) for piece in pieces)


def test_nothing_of_what_was_said_is_lost():
    """A cut redistributes the words. It never drops one, and never invents one."""
    text = "Première phrase. Deuxième phrase. Troisième phrase. Quatrième phrase."

    pieces = split_intervention(text, max_chars=40)

    assert " ".join(pieces) == text


def test_the_pieces_stay_in_the_order_they_were_said():
    text = "Un. Deux. Trois. Quatre. Cinq. Six."

    pieces = split_intervention(text, max_chars=12)

    assert pieces == ("Un. Deux.", "Trois.", "Quatre.", "Cinq. Six.")


def test_a_question_mark_ends_a_sentence_too():
    text = "Tu viens ? Je pars maintenant. On se voit là-bas !"

    pieces = split_intervention(text, max_chars=20)

    assert pieces[0] == "Tu viens ?"


def test_a_sentence_longer_than_the_maximum_is_cut_between_words():
    """A speaker who never punctuates still has to be cut somewhere, and between words is
    the least bad place left."""
    text = "alors " * 60

    pieces = split_intervention(text.strip(), max_chars=50)

    assert all(len(piece) <= 50 for piece in pieces)
    assert all(not piece.startswith(" ") and not piece.endswith(" ") for piece in pieces)
    assert " ".join(pieces).split() == text.split()


def test_no_cut_ever_falls_inside_a_word():
    text = "anticonstitutionnellement " * 20

    pieces = split_intervention(text.strip(), max_chars=60)

    for piece in pieces:
        for word in piece.split():
            assert word == "anticonstitutionnellement"


def test_a_single_word_longer_than_the_maximum_is_cut_rather_than_lost():
    """The last resort, and it is still better than the alternatives. A URL read aloud, or
    a compound in a language that does not use spaces: dropping it loses content, and
    keeping it whole would break the promise that no message exceeds the maximum."""
    text = "a" * 130

    pieces = split_intervention(text, max_chars=50)

    assert all(len(piece) <= 50 for piece in pieces)
    assert "".join(pieces) == text


def test_whitespace_between_sentences_is_not_carried_into_a_piece():
    text = "Première phrase.      Deuxième phrase."

    pieces = split_intervention(text, max_chars=20)

    assert pieces == ("Première phrase.", "Deuxième phrase.")


def test_an_ellipsis_is_not_three_sentence_endings():
    """Cutting after each dot of "..." would produce two empty pieces and a listener
    hearing a stutter."""
    text = "Je ne sais pas... enfin, peut-être."

    assert split_intervention(text, max_chars=500) == (text,)


def test_a_decimal_point_does_not_end_a_sentence():
    """"Il en reste 3.5" is one sentence, and cutting it gives "Il en reste 3." — which is
    a different and wrong number."""
    text = "Il en reste 3.5 pour aujourd'hui."

    assert split_intervention(text, max_chars=500) == (text,)


def test_a_cut_between_sentences_prefers_the_later_boundary():
    """Greedy on purpose: fewer, fuller pieces mean fewer seams for a listener to hear."""
    text = "Un. Deux. Trois."

    assert split_intervention(text, max_chars=10) == ("Un. Deux.", "Trois.")


def test_an_overlong_word_flushes_what_was_already_gathered():
    """The words before it were fine; they are their own piece rather than being dragged
    into the hard cut that follows."""
    text = "court " + "z" * 40

    pieces = split_intervention(text, max_chars=20)

    assert pieces[0] == "court"
    assert all(len(piece) <= 20 for piece in pieces)
    assert "".join(pieces[1:]) == "z" * 40


def test_an_overlong_sentence_after_short_ones_does_not_swallow_them():
    """The short sentences keep their own piece; the long one is cut between words on its
    own, so the seam falls where it was always going to."""
    text = "Un. Deux. " + " ".join(["alors"] * 30) + "."

    pieces = split_intervention(text, max_chars=40)

    assert pieces[0] == "Un. Deux."
    assert all(len(piece) <= 40 for piece in pieces)
