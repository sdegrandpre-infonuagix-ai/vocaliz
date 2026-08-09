"""Commands run from the production environment, reachable no other way.

Nothing here is imported by a router, and a test in `tests/test_reactivation.py` fails the
build if one ever is. Access to the environment is the access control: there is no
administrator accounts table and no administrator authentication, which means there is none
to build and none to get wrong.
"""
