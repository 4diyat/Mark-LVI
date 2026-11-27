"""A manual retry wakes real network backoff, never quota/other waits."""
import asyncio
import threading
import time

from core.retry_control import RetryControl


def test_manual_retry_interrupts_one_network_wait_and_clears_countdown():
    async def run():
        retry = RetryControl()
        task = asyncio.create_task(retry.wait(5, allow_manual=True))
        await asyncio.sleep(0)
        deadline, allowed = retry.snapshot()
        assert allowed and 0 < deadline - time.monotonic() <= 5
        results = []
        thread = threading.Thread(target=lambda: results.append(retry.request()))
        thread.start(); thread.join()
        assert results == [True]
        assert not retry.request()
        assert await asyncio.wait_for(task, 1) is True
        assert retry.snapshot() == (None, False)
    asyncio.run(run())


def test_manual_retry_cannot_bypass_other_backoff_and_cleans_on_cancel():
    async def run():
        retry = RetryControl()
        task = asyncio.create_task(retry.wait(10, allow_manual=False))
        await asyncio.sleep(0)
        assert not retry.request()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert retry.snapshot() == (None, False)
        assert not retry.request()
    asyncio.run(run())


def test_timeout_does_not_claim_a_manual_retry():
    async def run():
        retry = RetryControl()
        assert not await retry.wait(.01, allow_manual=True)
        assert retry.snapshot() == (None, False)
    asyncio.run(run())
