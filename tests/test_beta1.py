"""Original synthetic lifecycle, SVG, HA image API and privacy regressions."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import pytest
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError

from tests.test_coordinator import coordinator
from tests.test_stage2 import setup_rooms
from custom_components.yeedi_vac_max import PLATFORMS
from custom_components.yeedi_vac_max.coordinator import SpatialState
from custom_components.yeedi_vac_max.map_data import YeediMap, YeediRoom, RobotPosition, DockPosition
from custom_components.yeedi_vac_max.image import YeediMapImage, async_setup_entry
from custom_components.yeedi_vac_max.svg_map import render_map
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics

NS = '{http://www.w3.org/2000/svg}'
POLYGON = ((-20., -10.), (40., -10.), (40., 50.), (-20., 50.))


def image_state(c):
    setup_rooms(c)
    c.data = {'vac': {'online': True}}
    state = c.spatial['vac']
    state.rooms = (YeediRoom('PRIVATE_ID', 'PRIVATE_NAME', polygon=POLYGON),)
    return state


async def test_image_platform_and_one_entity_without_cloud(coordinator):
    assert Platform.IMAGE in PLATFORMS
    image_state(coordinator)
    add = Mock()
    await async_setup_entry(coordinator.hass, SimpleNamespace(runtime_data=coordinator), add)
    entities = list(add.call_args.args[0])
    assert len(entities) == 1 and entities[0].unique_id == 'vac_map'
    image = entities[0]
    assert image.content_type == 'image/svg+xml' and image.available
    assert await image.async_image() == await image.async_image()
    assert image.image_last_updated is not None
    coordinator.client.assert_not_awaited()
    assert not coordinator.client.mock_calls


@pytest.mark.parametrize('robot,dock', [(None,None), (RobotPosition(0,0),None),
    (None,DockPosition(100,100)), (RobotPosition(-100,-100,45),DockPosition(100,100))])
def test_svg_markers_viewbox_and_multiple_rooms(robot,dock):
    rooms = (YeediRoom('secret1','A',polygon=POLYGON),YeediRoom('secret2','B',polygon=POLYGON))
    svg = render_map(rooms,robot,dock)
    root = ET.fromstring(svg)
    assert len(root.findall(NS+'polygon')) == 2
    assert len({e.attrib['fill'] for e in root.findall(NS+'polygon')}) == 2
    assert bool(root.findall(".//*[@class='robot']")) == (robot is not None)
    assert bool(root.findall(".//*[@class='dock']")) == (dock is not None)
    x,y,w,h = map(float,root.attrib['viewBox'].split())
    for px,py in POLYGON + tuple((p.x,p.y) for p in (robot,dock) if p):
        assert x < px < x+w and y < py < y+h
    assert x < 0 and y < 0 and b'secret' not in svg


def test_svg_text_cannot_inject_xml():
    name = '<script onload="alert(1)">&\x00"\' malicious'
    root = ET.fromstring(render_map((YeediRoom('id',name,polygon=POLYGON),)))
    assert root.find(NS+'text').text == name.replace('\x00','')
    for element in root.iter():
        assert element.tag in {NS+k for k in ('svg','polygon','text','rect','circle')}
        assert not any(k.lower().startswith('on') or k in ('href','src','style') for k in element.attrib)
        assert not any('://' in v for v in element.attrib.values())


@pytest.mark.parametrize('rooms', [(), (YeediRoom('id','A'),),
    (YeediRoom('id','A',polygon=((float('nan'),0),(1,1),(2,0))),)])
def test_no_geometry_no_invented_image(rooms):
    assert render_map(rooms,RobotPosition(0,0),DockPosition(0,0)) is None


@pytest.mark.parametrize('field,value', [('metadata_valid',False),('rooms_valid',False),
    ('active_map',None),('rooms',()),('next_map_refresh',0)])
async def test_stale_image_not_served_even_before_callback(coordinator,field,value):
    state = image_state(coordinator)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert await image.async_image()
    setattr(state,field,value)
    assert await image.async_image() is None
    image._sync_image()
    assert not image.available and image._svg is None


@pytest.mark.parametrize('field,value', [('active_map',YeediMap('new',None,True)),
    ('rooms',(YeediRoom('new','new',polygon=POLYGON),)),
    ('robot_position',RobotPosition(7,8)),('dock_position',DockPosition(9,10))])
async def test_render_cache_invalidations(coordinator,field,value):
    state = image_state(coordinator)
    with patch('custom_components.yeedi_vac_max.image.render_map',wraps=render_map) as render:
        image = YeediMapImage(coordinator,coordinator.robots[0])
        first_time = image.image_last_updated
        for _ in range(3):
            await image.async_image()
            image._sync_image()
        assert render.call_count == 1
        setattr(state,field,value)
        image._sync_image()
        assert render.call_count == 2 and image.image_last_updated > first_time


async def test_same_map_new_rooms_blocks_selected_command(coordinator):
    vacuum = setup_rooms(coordinator)
    state = coordinator.spatial['vac']
    old = state.room_generation
    coordinator.client.rooms.return_value = (YeediRoom('3','Synthetic 3'),YeediRoom('9','New'))
    with pytest.raises(HomeAssistantError,match='mapping changed'):
        await vacuum.async_clean_segments(['3'])
    assert state.room_generation != old
    coordinator.client.command.assert_not_awaited()


async def test_same_rooms_keep_generation_and_refresh_before_write(coordinator):
    vacuum = setup_rooms(coordinator)
    state = coordinator.spatial['vac']
    old = state.room_generation
    calls = []
    async def rooms(*args):
        calls.append('rooms')
        return tuple(reversed(state.rooms))
    async def write(*args,**kwargs):
        calls.append('write')
    coordinator.client.rooms.side_effect = rooms
    coordinator.client.command.side_effect = write
    await vacuum.async_clean_segments(['3'])
    assert calls == ['rooms','write'] and state.room_generation == old


async def test_queue_checks_generation_captured_before_lock(coordinator):
    vacuum = setup_rooms(coordinator)
    lock = coordinator.commands['vac'].lock
    await lock.acquire()
    task = asyncio.create_task(vacuum.async_clean_segments(['3']))
    await asyncio.sleep(0)
    coordinator.spatial['vac'].rooms = (YeediRoom('3','Same'),YeediRoom('8','New'))
    lock.release()
    with pytest.raises(HomeAssistantError):
        await task
    coordinator.client.command.assert_not_awaited()


async def test_map_change_clears_before_new_room_read(coordinator):
    setup_rooms(coordinator)
    coordinator.client.maps.return_value = (YeediMap('newmap',None,True),)
    async def rooms(*args):
        state = coordinator.spatial['vac']
        assert state.rooms == () and not state.rooms_valid
        return (YeediRoom('8','New'),)
    coordinator.client.rooms.side_effect = rooms
    await coordinator._spatial_refresh(coordinator.robots[0],force=True)
    assert coordinator.rooms['vac'][0].room_id == '8'


async def test_refresh_notifies_mapping_issue(coordinator):
    vacuum = setup_rooms(coordinator)
    vacuum.registry_entry = SimpleNamespace(options={'vacuum':{'last_seen_segments':[
        {'id':r.room_id,'name':r.name,'group':'map-a'} for r in coordinator.spatial['vac'].rooms]}})
    vacuum.async_create_segments_issue = Mock()
    vacuum.async_write_ha_state = Mock()
    vacuum._handle_coordinator_update()
    vacuum.async_create_segments_issue.assert_not_called()
    coordinator.spatial['vac'].rooms = tuple(reversed(coordinator.spatial['vac'].rooms))
    vacuum._handle_coordinator_update()
    vacuum.async_create_segments_issue.assert_not_called()
    coordinator.spatial['vac'].rooms = (YeediRoom('8','New'),)
    vacuum._handle_coordinator_update()
    vacuum.async_create_segments_issue.assert_called_once()


async def test_reload_empty_state_and_privacy(coordinator,caplog):
    state = image_state(coordinator)
    state.active_map = YeediMap('PRIVATE_MAP',None,True)
    state.robot_position = RobotPosition(987654,123456)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    assert await image.async_image()
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    text = json.dumps(output)+caplog.text
    for private in ('PRIVATE','987654','123456','<svg','room_generation','fingerprint'):
        assert private not in text
    assert output['robots'][0]['has_room_polygons'] is True
    coordinator.spatial['vac'] = SpatialState()
    reloaded = YeediMapImage(coordinator,coordinator.robots[0])
    assert not reloaded.available and await reloaded.async_image() is None
    assert not coordinator.rooms['vac']


async def test_image_coordinator_callback_updates_state_not_http(coordinator):
    state = image_state(coordinator)
    image = YeediMapImage(coordinator,coordinator.robots[0])
    image.async_write_ha_state = Mock()
    first = image.state
    state.robot_position = RobotPosition(2,3)
    image._handle_coordinator_update()
    second = image.state
    assert first != second
    image.async_write_ha_state.assert_called_once()
    assert await image.async_image()
    assert image.state == second
    state.metadata_valid = False
    image._handle_coordinator_update()
    assert image._svg is None and not image.available


async def test_failed_room_preflight_never_writes_or_exposes_rooms(coordinator):
    from custom_components.yeedi_vac_max.client import CloudError
    vacuum = setup_rooms(coordinator)
    coordinator.client.rooms.side_effect = CloudError('synthetic')
    with pytest.raises(HomeAssistantError):
        await vacuum.async_clean_segments(['3'])
    coordinator.client.command.assert_not_awaited()
    assert not coordinator.rooms['vac']
    assert coordinator.spatial['vac'].metadata_valid
