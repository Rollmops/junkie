import contextlib

import pytest

from junkie import Junkie, AsyncJunkie


@contextlib.asynccontextmanager
async def async_test():
    yield "hello from async context manager"

@pytest.mark.asyncio
async def test_async_support():
    my_junkie = AsyncJunkie({"text": async_test})

    async with my_junkie.inject("text") as text:
        assert "hello from async context manager" == text
