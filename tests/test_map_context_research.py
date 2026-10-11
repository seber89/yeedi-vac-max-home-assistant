"""Original synthetic protocol-boundary tests; no proposed runtime change."""
import pytest

from tests.test_beta6 import client, major, minor, encoded, ROBOT, MID
from custom_components.yeedi_vac_max.raw_map import MapChanged, safe_status


async def test_minor_request_has_only_documented_context():
    c = client()
    result = await c.load_raw_map(ROBOT, MID, None, safe_status())
    assert result
    calls = c.command.await_args_list
    assert calls[0].args[1] == calls[-1].args[1] == 'getMajorMap'
    requests = [call.args[2] for call in calls if call.args[1] == 'getMinorMap']
    assert requests == [dict(mid=MID, pieceIndex=i, type='ol') for i in (0, 2, 3)]
    assert all(not call.kwargs.get('writing', False) for call in calls)


@pytest.mark.parametrize('changes', [
    {'value': '12,1295764014,33,44'}, {'pixel': 25}, {'mid': 'OTHER_MAP'},
])
async def test_observable_major_generation_change_rejects_entire_build(changes):
    c = client()
    original = c.command.side_effect
    major_reads = 0
    async def response(robot, name, data=None, **kwargs):
        nonlocal major_reads
        if name == 'getMajorMap':
            major_reads += 1
            if major_reads == 2:
                return {'data': major(**changes)}
        return await original(robot, name, data, **kwargs)
    c.command.side_effect = response
    status = safe_status()
    with pytest.raises(MapChanged):
        await c.load_raw_map(ROBOT, MID, None, status)
    assert not status['generation_verified']
    assert not status['image_generated']


async def test_minor_from_other_map_cannot_be_assembled():
    c = client()
    original = c.command.side_effect
    async def response(robot, name, data=None, **kwargs):
        if name == 'getMinorMap':
            return {'data': minor(data['pieceIndex'], mid='OTHER_MAP')}
        return await original(robot, name, data, **kwargs)
    c.command.side_effect = response
    with pytest.raises(MapChanged):
        await c.load_raw_map(ROBOT, MID, None, safe_status())


async def test_unobservable_minor_revision_is_not_independently_verified():
    """Same documented identities cannot prove undocumented payload revision."""
    c = client()
    previous = await c.load_raw_map(ROBOT, MID, None, safe_status())
    original = c.command.side_effect
    async def response(robot, name, data=None, **kwargs):
        if name == 'getMinorMap':
            return {'data': minor(data['pieceIndex'], pieceValue=encoded(bytes(4)))}
        return await original(robot, name, data, **kwargs)
    c.command.side_effect = response
    status = safe_status()
    # Fresh-like build (no prior pieces): stable Major metadata, valid zero payloads.
    assert await c.load_raw_map(ROBOT, MID, None, status) is None
    assert status['generation_verified']
    assert status['failure_stage'] == 'no_visible_pixels'
    # Normal cache semantics remain explicit: unchanged Major can reuse last-good.
    c.command.reset_mock()
    assert await c.load_raw_map(ROBOT, MID, previous, safe_status()) is previous
    assert [call.args[1] for call in c.command.await_args_list] == ['getMajorMap', 'getMajorMap']
