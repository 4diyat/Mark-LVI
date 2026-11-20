"""Bounded assistant playback, preserving order under backpressure.

All functions here must run on the asyncio queue's owning event loop. The bound
covers only queued PCM slices, not provider/network or device buffers.
"""
import asyncio

# 24 kHz, 16-bit mono: each 2400-byte slice represents at most 50 ms.
SLICE_BYTES = 2400
MAX_SLICES = 200  # at most about 10 seconds of queued PCM


def drain(queue):
    count = 0
    while True:
        try:
            queue.get_nowait()
            count += 1
        except asyncio.QueueEmpty:
            return count


async def enqueue(queue, data, interrupted):
    """Wait for space, preserving every slice unless the user interrupts.

    A producer blocked in put() may resume after an interrupt drained the queue;
    re-check immediately after put and remove that stale slice before yielding.
    Returns False when interrupted. Cancelling the task propagates normally.
    """
    for offset in range(0, len(data), SLICE_BYTES):
        if interrupted():
            return False
        await queue.put(data[offset:offset + SLICE_BYTES])
        if interrupted():
            drain(queue)
            return False
    return True
