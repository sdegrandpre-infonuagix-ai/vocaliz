"""The namespace Vocaliz writes its metadata under on Stripe objects.

Stripe metadata is a flat key space on an object we do not own. Stripe itself writes
there, so do Stripe apps and any other integration an operator connects to the account.
A bare `user_id` says nothing about whose user it is, and the day a second system writes
one, whichever wrote last wins — silently, on a Customer that bills real money.

The prefix used to be `salon_`, after the project this code came from. That name now
means something else entirely: a Salon is the conversation being billed for, so
`salon_user_id` read as "the user of a Salon" rather than "Salon's user id", and the
Salon's own key would have had to be `salon_salon_id`. Renaming the namespace to the
company removes the collision instead of working around it.

One helper rather than a constant others interpolate: a namespace applied by hand is
applied inconsistently, and the failure is invisible — the write succeeds, the key is
just wrong.
"""

NAMESPACE = "vocaliz"


def namespaced(**fields: object) -> dict[str, str]:
    """Prefix every key with the Vocaliz namespace; stringify every value.

    Stripe rejects non-string metadata values, and `None` is the common accident — an
    optional foreign key that happens to be absent. It becomes the empty string, which
    is what Stripe stores for "present but unset" and what a reader already handles.
    """
    return {
        f"{NAMESPACE}_{name}": "" if value is None else str(value)
        for name, value in fields.items()
    }
