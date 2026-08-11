"""A guest's email is never the host's own remembered address.

Reported live: filling one of the two guest-email fields from browser memory populated
both of them with the same value. Neither field carries a `name` attribute for a browser to
tell them apart, and neither opted out of autofill, so a browser had nothing to distinguish
"this contact" from "that other contact" — or from the host's own saved address.
"""
import pathlib

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"


def _host_source() -> str:
    return (WEB / "host.html").read_text(encoding="utf-8")


def _input_tag(source: str, input_id: str) -> str:
    start = source.index(f'id="{input_id}"')
    # Back up to the tag's own opening angle bracket, then forward to its close.
    tag_start = source.rindex("<input", 0, start)
    return source[tag_start : source.index(">", start) + 1]


def test_the_first_guest_email_field_opts_out_of_autofill():
    tag = _input_tag(_host_source(), "guest-email")
    assert 'autocomplete="off"' in tag


def test_the_second_guest_email_field_opts_out_of_autofill():
    tag = _input_tag(_host_source(), "guest-email-2")
    assert 'autocomplete="off"' in tag
