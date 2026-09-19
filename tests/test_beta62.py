"""Original synthetic equality/privacy and explicit LZMA1 filter crosschecks."""
import base64
import json
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_coordinator import coordinator
from tests.test_beta6 import client, major, minor, encoded, ROBOT, MID
from tests.test_beta61 import pixel_client
from custom_components.yeedi_vac_max import client as client_module
from custom_components.yeedi_vac_max.raw_map import safe_status, EMPTY_PIECE
from custom_components.yeedi_vac_max.zero_pixel_diagnostics import (
    ZeroPixelProbe, alternate_decode, empty_probe, safe_export)
from custom_components.yeedi_vac_max.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.parametrize('crcs,empty,zero,distinct,same,nonempty_same',[
    ((), '0','0','0',False,False),
    ((EMPTY_PIECE,)*4,'2-8','0','1',True,False),
    ((0,)*4,'0','2-8','1',True,True),
    ((87654321,)*4,'0','0','1',True,True),
    ((EMPTY_PIECE,0,87654321,87654321),'1','1','2-8',False,False),
    ((EMPTY_PIECE,87654321,87654321),'1','0','2-8',False,True),
])
def test_crc_structure(crcs,empty,zero,distinct,same,nonempty_same):
    p = ZeroPixelProbe()
    p.major(crcs)
    result = p.finish()
    assert result['crc_structure_checked']
    assert result['known_empty_sentinel_count_bucket']==empty
    assert result['zero_crc_count_bucket']==zero
    assert result['distinct_crc_count_bucket']==distinct
    assert result['all_crc_values_same']==same
    assert result['nonempty_crc_values_same']==nonempty_same
    assert '87654321' not in json.dumps(result) and str(EMPTY_PIECE) not in json.dumps(result)


@pytest.mark.parametrize('pieces,zero,identical,nonzero',[
    ([],False,False,'0'), ([b'\0'*4]*3,True,True,'0'),
    ([b'\0'*4,b'\1'*4],False,False,'1'), ([b'\1'*4]*3,False,True,'2-8')])
def test_piece_aggregation(pieces,zero,identical,nonzero):
    p = ZeroPixelProbe()
    for value in pieces:
        p.decoded(value)
    result = p.finish()
    assert result['all_decoded_pieces_zero'] is zero
    assert result['all_decoded_pieces_identical'] is identical
    assert result['nonzero_decoded_piece_count_bucket']==nonzero
    assert not p._decoded


def test_encoded_equality_transient_only():
    p = ZeroPixelProbe()
    for value in ('PRIVATE_PAYLOAD','PRIVATE_PAYLOAD','OTHER_PRIVATE'):
        p.encoded(value)
    assert all(isinstance(value,bytes) and len(value)==32 for value in p._encoded)
    result = p.finish()
    assert not result['all_encoded_payloads_identical']
    assert result['distinct_encoded_payload_count_bucket']=='2-8'
    assert not p._encoded and 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('pixels',[b'\0'*4,b'\1\2\3\4',b'\0'*100,b'\xff'*16])
def test_raw_crosscheck_matches_primary(pixels):
    result = alternate_decode(encoded(pixels),pixels)
    assert result == dict(alternate_decode_success=True, alternate_matches_primary=True,
                          alternate_nonzero_pixels_present=any(pixels))


def test_crosscheck_reports_difference_without_returning_pixels():
    result = alternate_decode(encoded(b'\1'*4),b'\0'*4)
    assert result['alternate_decode_success'] and not result['alternate_matches_primary']
    assert result['alternate_nonzero_pixels_present']
    assert all(type(x) is bool for x in result.values())


@pytest.mark.parametrize('value',[None,'','@@@','x'*524289,base64.b64encode(b'short').decode()],
                         ids=['null','empty','invalid','oversized','short'])
def test_bad_crosscheck_safe(value):
    assert not any(alternate_decode(value,b'\0'*4).values())


@pytest.mark.parametrize('change',['properties','dictionary','size','truncated','trailing'])
def test_crosscheck_strict_limits(change):
    wire = base64.b64decode(encoded())
    if change=='properties': wire = b'\xff'+wire[1:]
    if change=='dictionary': wire = wire[:1]+struct.pack('<I',1<<30)+wire[5:]
    if change=='size': wire = wire[:5]+struct.pack('<I',999999)+wire[9:]
    if change=='truncated': wire = wire[:10]
    if change=='trailing': wire += b'PRIVATE'
    assert not any(alternate_decode(base64.b64encode(wire).decode(),b'\1\2\3\0').values())


async def test_zero_load_crosscheck_once_no_new_reads(monkeypatch):
    c = pixel_client(0)
    crosscheck = Mock(wraps=alternate_decode)
    monkeypatch.setattr(client_module,'alternate_decode',crosscheck)
    status = safe_status()
    assert await c.load_raw_map(ROBOT,MID,None,status) is None
    crosscheck.assert_called_once()
    assert [call.args[1] for call in c.command.call_args_list].count('getMajorMap')==2
    assert [call.args[1] for call in c.command.call_args_list].count('getMinorMap')==3
    assert status['failure_stage']=='no_visible_pixels'
    probe = status['zero_pixel_probe']
    for key in ('crc_structure_checked','all_decoded_pieces_zero','all_decoded_pieces_identical',
                'all_encoded_payloads_identical','alternate_decode_success','alternate_matches_primary'):
        assert probe[key]
    assert not probe['alternate_nonzero_pixels_present']


async def test_diagnostic_crosscheck_failure_never_replaces_pixels(monkeypatch):
    monkeypatch.setattr(client_module,'alternate_decode',lambda *args: {
        'alternate_decode_success':False,'alternate_matches_primary':False,
        'alternate_nonzero_pixels_present':False})
    status = safe_status()
    result = await client().load_raw_map(ROBOT,MID,None,status)
    assert result and status['image_generated']
    assert not status['zero_pixel_probe']['alternate_decode_success']


async def test_crosscheck_exception_is_isolated(monkeypatch):
    def fail(*args):
        raise RuntimeError('PRIVATE')
    monkeypatch.setattr(client_module,'alternate_decode',fail)
    status = safe_status()
    assert await client().load_raw_map(ROBOT,MID,None,status)
    assert status['failure_stage']=='none'


async def test_cached_pieces_compared_without_extra_crosscheck(monkeypatch):
    c = client()
    previous = await c.load_raw_map(ROBOT,MID,None,safe_status())
    crosscheck = Mock(wraps=alternate_decode)
    monkeypatch.setattr(client_module,'alternate_decode',crosscheck)
    c.command.reset_mock()
    status = safe_status()
    assert await c.load_raw_map(ROBOT,MID,previous,status) is previous
    crosscheck.assert_not_called()
    assert c.command.await_count==2
    assert status['zero_pixel_probe']['decoded_piece_count_bucket']=='2-8'
    assert status['zero_pixel_probe']['distinct_encoded_payload_count_bucket']=='0'
    assert not status['zero_pixel_probe']['all_encoded_payloads_identical']


async def test_export_no_private_values_or_fingerprints(coordinator,caplog):
    status = safe_status()
    await pixel_client(0).load_raw_map(ROBOT,MID,None,status)
    coordinator.spatial['vac'].raw_status = status
    output = await async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
    report = output['zero_pixel_probe'][0]
    assert set(report)==set(empty_probe()) and report['alternate_matches_primary']
    text = json.dumps(output)+caplog.text
    for private in ('PRIVATE','1295764014','sha256','digest','pieceIndex',encoded(b'\0'*4)):
        assert private not in text
    polluted = {key:'PRIVATE' for key in empty_probe()}
    polluted['raw'] = b'PRIVATE'
    assert safe_export(polluted)==empty_probe()
