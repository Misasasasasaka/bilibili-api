"""二维码登录的离线回归测试，不使用真实账号或网络。"""

import json
from unittest.mock import AsyncMock, Mock, patch

from bilibili_api import BiliAPIResponse, LoginError, NetworkException, login_v2


async def _check_state(data, cookies=None, api_code=0, http_code=200):
    response = BiliAPIResponse(
        code=http_code,
        headers={},
        cookies=cookies or {},
        raw=json.dumps({"code": api_code, "data": data}).encode(),
        url="https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
    )
    client = Mock(request=AsyncMock(return_value=response))
    qr = login_v2.QrCodeLogin()
    with patch.object(login_v2, "get_client", return_value=client):
        try:
            state = await qr.check_state()
        except (LoginError, NetworkException):
            assert not qr.has_done()
            raise
    client.request.assert_awaited_once()
    assert client.request.call_args.kwargs["params"]["source"] == "main-fe-header"
    return state, qr


async def test_web_cookie_only_success():
    for url in (None, "", "https://www.bilibili.com/"):
        data = {"code": 0, "refresh_token": "test-refresh"}
        if url is not None:
            data["url"] = url
        state, qr = await _check_state(
            data,
            {
                "SESSDATA": "test%2Fsession%2Ctoken",
                "bili_jct": "test-csrf",
                "DedeUserID": "123",
                "buvid3": "test-buvid3",
                "buvid4": "test-buvid4",
            },
        )
        assert state == login_v2.QrCodeLoginEvents.DONE
        credential = qr.get_credential()
        assert credential.sessdata == "test%2Fsession%2Ctoken"
        assert credential.bili_jct == "test-csrf"
        assert credential.dedeuserid == "123"
        assert credential.ac_time_value == "test-refresh"
        assert credential.buvid3 == "test-buvid3"
        assert credential.buvid4 == "test-buvid4"


async def test_web_legacy_url_success():
    state, qr = await _check_state(
        {
            "code": 0,
            "url": "https://passport.bilibili.com/crossDomain?"
            "SESSDATA=test%2Fsession%2Ctoken%3D&bili_jct=test-csrf&DedeUserID=123",
            "refresh_token": "test-refresh",
        }
    )
    assert state == login_v2.QrCodeLoginEvents.DONE
    credential = qr.get_credential()
    assert credential.sessdata == "test%2Fsession%2Ctoken%3D"
    assert credential.bili_jct == "test-csrf"
    assert credential.dedeuserid == "123"
    assert credential.ac_time_value == "test-refresh"


async def test_web_cookies_override_url():
    _, qr = await _check_state(
        {
            "code": 0,
            "url": "https://passport.bilibili.com/?"
            "SESSDATA=old&bili_jct=test-csrf&DedeUserID=123",
        },
        {"SESSDATA": "new%2Fsession", "bili_jct": ""},
    )
    credential = qr.get_credential()
    assert credential.sessdata == "new%2Fsession"
    assert credential.bili_jct == "test-csrf"
    assert credential.dedeuserid == "123"


async def test_web_pending_states():
    for code, expected in (
        (86101, login_v2.QrCodeLoginEvents.SCAN),
        (86090, login_v2.QrCodeLoginEvents.CONF),
        (86038, login_v2.QrCodeLoginEvents.TIMEOUT),
    ):
        state, qr = await _check_state({"code": code})
        assert state == expected
        assert not qr.has_done()


async def test_web_missing_credentials_are_rejected():
    for cookies in ({}, {"SESSDATA": "test"}, {"bili_jct": "test"}):
        try:
            await _check_state({"code": 0}, cookies)
        except LoginError:
            pass
        else:
            raise AssertionError("不完整的凭据不应被当作登录成功")


async def test_web_unknown_state_is_rejected():
    try:
        await _check_state({"code": 99999})
    except LoginError:
        pass
    else:
        raise AssertionError("未知状态不应被当作登录成功")


async def test_web_api_error_is_rejected():
    try:
        await _check_state(None, api_code=-400)
    except LoginError:
        pass
    else:
        raise AssertionError("接口错误不应被当作登录成功")


async def test_web_http_error_is_rejected():
    try:
        await _check_state(None, http_code=503)
    except NetworkException:
        pass
    else:
        raise AssertionError("HTTP 错误不应被当作登录成功")
