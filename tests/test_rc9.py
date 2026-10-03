"""Original request-profile regression, no external fixtures."""
from unittest.mock import AsyncMock
from urllib.parse import urlsplit, parse_qs

import pytest

from custom_components.yeedi_vac_max.client import YeediClient
from custom_components.yeedi_vac_max.clean_log_map import CleanLogError, safe_probe
from tests.test_rc8 import URL, ROBOT


@pytest.mark.parametrize('logs', [[], [{'ts':42,'imageUrl':URL}]])
async def test_yeedi_950_exact_query_and_country(logs):
    client = YeediClient(None,'private','secret','DE','resource')
    client.authenticate = AsyncMock()
    client._request = AsyncMock(return_value={'ret':'ok','logs':logs})
    if logs:
        assert await client.clean_logs(ROBOT,safe_probe()) == URL
    else:
        with pytest.raises(CleanLogError,match='no_records'):
            await client.clean_logs(ROBOT,safe_probe())
    client._request.assert_awaited_once()
    args, kwargs = client._request.call_args
    assert args[0] == 'POST'
    parsed = urlsplit(args[1])
    assert (parsed.scheme,parsed.netloc,parsed.path) == ('https','portal-eu.ecouser.net','/api/lg/log.do')
    assert parse_qs(parsed.query,strict_parsing=True) == {'cv':['1.94.76'],'t':['a'],'av':['1.3.0']}
    assert kwargs == {'retry':True,'json':{'auth':client._auth(),'did':ROBOT.did,
        'country':'DE','td':'GetCleanLogs','resource':ROBOT.resource}}
