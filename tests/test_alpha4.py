"""Synthetic timing and privacy regression tests; no hardware responses."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_coordinator import coordinator
from custom_components.yeedi_vac_max import client as cloud
from custom_components.yeedi_vac_max import coordinator as module
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom


def test_map_budget_covers_complete_read_retry():
    assert cloud.READ_RETRY_BUDGET == 31
    assert cloud.READ_RETRY_BUDGET < module.MAP_READ_TIMEOUT <= 40
    assert 60 < module.MAP_ERROR_BACKOFF < module.MAP_INTERVAL


async def test_second_http_read_completes_inside_map_budget(coordinator, monkeypatch):
    original_sleep, original_timeout = asyncio.sleep, asyncio.timeout
    budgets, attempts = [], []
    def scaled_timeout(seconds):
        budgets.append(seconds)
        return original_timeout(seconds / 100)
    async def scaled_sleep(seconds):
        await original_sleep(seconds / 100)
    class Response:
        status = 200
        async def json(self, **kwargs):
            return {"ret": "ok", "resp": {"body": {"data": {"info": []}}}}
    class Request:
        async def __aenter__(self):
            await original_sleep(.15)
            if len(attempts) == 1:
                raise TimeoutError
            return Response()
        async def __aexit__(self, *args):
            pass
    def request(*args, **kwargs):
        attempts.append(kwargs["timeout"].total)
        return Request()
    c = cloud.YeediClient(SimpleNamespace(request=request), "synthetic", "synthetic", "DE", "synthetic")
    c.authenticate = AsyncMock()
    c.positions = AsyncMock(return_value=(None, None))
    coordinator.client = c
    monkeypatch.setattr(asyncio, "sleep", scaled_sleep)
    monkeypatch.setattr(asyncio, "timeout", scaled_timeout)
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert attempts == [15, 15]
    assert module.MAP_READ_TIMEOUT in budgets
    assert coordinator.spatial["vac"].metadata_valid


@pytest.mark.parametrize("error", [cloud.CloudError("synthetic"), TimeoutError()])
async def test_failed_map_backoff_then_retry(coordinator, monkeypatch, error):
    now = [10000.]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    coordinator.client.maps.side_effect = error
    await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial["vac"]
    assert state.next_map_refresh == now[0] + module.MAP_ERROR_BACKOFF
    assert not state.metadata_valid and not state.rooms_valid
    now[0] += 60
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.client.maps.await_count == 1
    now[0] += module.MAP_ERROR_BACKOFF
    coordinator.client.maps.side_effect = None
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.client.maps.await_count == 2
    assert state.next_map_refresh == now[0] + module.MAP_INTERVAL


@pytest.mark.parametrize("active", [False, True])
async def test_success_keeps_hour_cache_and_gates_rooms(coordinator, monkeypatch, active):
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 10000.))
    coordinator.client.maps.return_value = (YeediMap("synthetic", None, active),)
    coordinator.client.rooms.return_value = (YeediRoom("synthetic", "Synthetic"),)
    await coordinator._spatial_refresh(coordinator.robots[0])
    state = coordinator.spatial["vac"]
    assert state.next_map_refresh == 13600
    assert state.metadata_valid
    assert coordinator.client.rooms.await_count == int(active)
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.client.maps.await_count == 1


async def test_room_failure_uses_backoff(coordinator, monkeypatch):
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 10000.))
    coordinator.client.maps.return_value = (YeediMap("synthetic", None, True),)
    coordinator.client.rooms.side_effect = cloud.CloudError("synthetic")
    await coordinator._spatial_refresh(coordinator.robots[0])
    assert coordinator.spatial["vac"].next_map_refresh == 10000 + module.MAP_ERROR_BACKOFF
