"""Admission and drain: which Salons this instance hosts, and when it stops taking more."""
import asyncio

import pytest

from src.lifecycle import DrainingError, SalonRegistry


def test_a_fresh_instance_hosts_nothing_and_accepts_work():
    registry = SalonRegistry()

    assert registry.hosted == ()
    assert registry.hosted_count == 0
    assert registry.draining is False


def test_accepting_a_salon_records_it():
    registry = SalonRegistry()

    registry.accept("salon-1")
    registry.accept("salon-2")

    assert registry.hosted_count == 2
    assert set(registry.hosted) == {"salon-1", "salon-2"}


def test_accepting_the_same_salon_twice_is_not_two_salons():
    registry = SalonRegistry()

    registry.accept("salon-1")
    registry.accept("salon-1")

    assert registry.hosted_count == 1


def test_releasing_a_salon_removes_it():
    registry = SalonRegistry()
    registry.accept("salon-1")

    registry.release("salon-1")

    assert registry.hosted_count == 0


def test_releasing_a_salon_this_instance_never_hosted_is_harmless():
    """A late release after a takeover must not crash the instance that lost the Salon."""
    SalonRegistry().release("salon-unknown")


def test_draining_refuses_new_salons():
    registry = SalonRegistry()
    registry.begin_drain()

    with pytest.raises(DrainingError):
        registry.accept("salon-1")

    assert registry.hosted_count == 0


def test_draining_lets_the_salons_already_hosted_finish():
    """Drain is graceful: what is running keeps running, only new arrivals are refused."""
    registry = SalonRegistry()
    registry.accept("salon-1")

    registry.begin_drain()

    assert registry.draining is True
    assert registry.hosted == ("salon-1",)


def test_begin_drain_is_idempotent():
    registry = SalonRegistry()
    registry.begin_drain()
    registry.begin_drain()

    assert registry.draining is True


async def test_wait_until_empty_returns_at_once_when_nothing_is_hosted():
    assert await SalonRegistry().wait_until_empty(timeout=5) is True


async def test_wait_until_empty_returns_when_the_last_salon_is_released():
    registry = SalonRegistry()
    registry.accept("salon-1")
    registry.accept("salon-2")
    registry.begin_drain()

    async def finish():
        await asyncio.sleep(0)
        registry.release("salon-1")
        await asyncio.sleep(0)
        registry.release("salon-2")

    task = asyncio.create_task(finish())
    assert await registry.wait_until_empty(timeout=5) is True
    await task


async def test_wait_until_empty_gives_up_after_the_timeout():
    """A Salon that never ends must not hold the task past the ECS stop timeout."""
    registry = SalonRegistry()
    registry.accept("salon-1")
    registry.begin_drain()

    assert await registry.wait_until_empty(timeout=0.01) is False
    assert registry.hosted_count == 1


async def test_a_salon_accepted_before_the_drain_can_still_be_released_after_it():
    registry = SalonRegistry()
    registry.accept("salon-1")
    registry.begin_drain()
    registry.release("salon-1")

    assert registry.hosted_count == 0
    assert await registry.wait_until_empty(timeout=5) is True
