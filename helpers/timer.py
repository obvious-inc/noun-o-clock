import asyncio


class AsyncTimer:
    def __init__(self, timeout=2, callback=None):
        self._timeout = timeout
        self._callback = callback
        if callback:
            self._task = asyncio.ensure_future(self._job())
        else:
            self._task = None

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self._callback()

    def cancel(self):
        if hasattr(self, "_task") and self._task is not None:
            self._task.cancel()
