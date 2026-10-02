import asyncio
from unittest import mock

import aiohttp
import pytest
from aiohttp.test_utils import make_mocked_request

from nipulate import server
from nipulate.hub import Hub
from nipulate.input import FakeBackend
from nipulate.pairing import MAX_FAILURES, Pairing
from nipulate.protocol import KEYS, MAX_MESSAGE_BYTES
from nipulate.server import _is_pc, create_app

URL = "http://192.168.1.9:8787/"


@pytest.fixture
async def setup(aiohttp_client, tmp_path):
    hub = Hub(FakeBackend(), Pairing(tmp_path / "config.json"), "test", verbose=True, out=lambda line: None)
    client = await aiohttp_client(create_app(hub, URL))
    return hub, client


def origin(client) -> dict:
    return {"Origin": f"http://{client.host}:{client.port}"}


async def hello(client, token, client_id="phone1", **extra):
    ws = await client.ws_connect("/ws", headers=origin(client))
    await ws.send_json({"t": "hello", "k": token, "id": client_id, **extra})
    return ws, await ws.receive_json()


async def roundtrip(ws):
    """Ping and wait for the pong, so every earlier message has been handled."""
    await ws.send_json({"t": "ping", "ping": 7})
    while True:
        msg = await ws.receive_json()
        if msg["t"] == "pong":
            return


async def closed(ws) -> bool:
    """True once the server closes the socket; other messages on the way are skipped."""
    while True:
        msg = await ws.receive(timeout=5)
        if msg.type != aiohttp.WSMsgType.TEXT:
            return msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING)


# ---- authentication ------------------------------------------------------------


async def test_paired_phone_drives_input(setup):
    hub, client = setup
    ws, reply = await hello(client, hub.pairing.token)
    assert reply["t"] == "ok" and "k" not in reply
    assert reply["vol"] == {"level": hub.backend.level, "muted": False}
    await ws.send_json({"t": "set", "sens": 1})
    await ws.send_json({"t": "m", "dx": 5, "dy": -3, "dt": 100})
    await ws.send_json({"t": "key", "k": "play_pause"})
    await ws.send_json({"t": "button", "b": "left"})
    await roundtrip(ws)
    assert hub.backend.events == [
        ("move", 5, -3),
        ("keys", KEYS["play_pause"][1]),
        ("button", "left", True), ("button", "left", False),
    ]
    await ws.close()


async def test_wrong_token_is_refused_and_closed(setup):
    hub, client = setup
    ws, reply = await hello(client, "not-the-token")
    assert reply["t"] == "denied" and reply["reason"] == "token"
    assert await closed(ws)
    assert hub.phones == {}


async def test_input_before_hello_is_refused(setup):
    hub, client = setup
    ws = await client.ws_connect("/ws", headers=origin(client))
    await ws.send_json({"t": "key", "k": "play_pause"})
    assert (await ws.receive_json())["reason"] == "hello"
    assert await closed(ws)
    assert hub.backend.events == []


async def test_silent_sockets_are_dropped(setup, monkeypatch):
    monkeypatch.setattr(server, "AUTH_TIMEOUT_S", 0.05)
    _, client = setup
    ws = await client.ws_connect("/ws", headers=origin(client))
    assert (await ws.receive_json())["reason"] == "hello"
    assert await closed(ws)


async def test_failed_attempts_are_rate_limited(setup):
    hub, client = setup
    for _ in range(MAX_FAILURES):
        ws, _ = await hello(client, "wrong")
        await ws.close()
    ws, reply = await hello(client, hub.pairing.token)
    assert reply["reason"] == "limited" and reply["retry"] > 0
    await ws.close()


async def test_pairing_code_returns_the_token(setup):
    hub, client = setup
    code = hub.pairing.code
    ws = await client.ws_connect("/ws", headers=origin(client))
    await ws.send_json({"t": "pair", "code": code, "id": "iphone-app", "standalone": True})
    reply = await ws.receive_json()
    assert reply["t"] == "ok" and reply["k"] == hub.pairing.token
    assert hub.pairing.code != code  # used up
    assert hub.pairing.devices["iphone-app"]["label"].endswith("(Home Screen app)")
    await ws.close()


async def test_wrong_pairing_code_is_refused(setup):
    hub, client = setup
    wrong = "000000" if hub.pairing.code != "000000" else "111111"
    ws = await client.ws_connect("/ws", headers=origin(client))
    await ws.send_json({"t": "pair", "code": wrong, "id": "x"})
    assert (await ws.receive_json())["reason"] == "code"
    assert await closed(ws)


async def test_foreign_origin_is_refused(setup):
    hub, client = setup
    with pytest.raises(aiohttp.WSServerHandshakeError) as e:
        await client.ws_connect("/ws", headers={"Origin": "http://evil.example"})
    assert e.value.status == 403


# ---- connected phones ---------------------------------------------------------------


async def test_bad_messages_are_ignored(setup):
    hub, client = setup
    ws, _ = await hello(client, hub.pairing.token)
    await ws.send_str("not json")
    await ws.send_json({"t": "key", "k": "VK_F4"})
    await ws.send_json({"t": "key", "k": "mute"})
    await roundtrip(ws)
    assert hub.backend.events == [("keys", KEYS["mute"][1])]
    await ws.close()


async def test_oversized_messages_drop_the_connection(setup):
    hub, client = setup
    ws, _ = await hello(client, hub.pairing.token)
    await ws.send_json({"t": "text", "s": "x" * (MAX_MESSAGE_BYTES + 10)})
    assert await closed(ws)
    assert hub.backend.events == []


async def test_disconnect_releases_a_drag(setup):
    hub, client = setup
    ws, _ = await hello(client, hub.pairing.token)
    await ws.send_json({"t": "button", "b": "left", "a": "down"})
    await roundtrip(ws)
    assert hub.backend.held == {"left"}
    await ws.close()
    for _ in range(50):  # the server notices the close asynchronously
        if not hub.phones:
            break
        await asyncio.sleep(0.01)
    assert hub.backend.held == set()


async def test_second_tab_takes_over_and_the_first_is_told(setup):
    hub, client = setup
    first, _ = await hello(client, hub.pairing.token, "same-id")
    second, reply = await hello(client, hub.pairing.token, "same-id")
    assert reply["t"] == "ok"
    told = [msg.json() async for msg in first]  # ends when the server closes the old connection
    assert {"t": "replaced"} in told
    assert hub.phones["same-id"].ws is not None
    await second.close()


async def test_typing_reaches_the_backend(setup):
    hub, client = setup
    ws, _ = await hello(client, hub.pairing.token)
    await ws.send_json({"t": "text", "s": "héllo 👋"})
    await roundtrip(ws)
    assert ("text", "héllo 👋") in hub.backend.events
    await ws.close()


async def test_lock(setup):
    hub, client = setup
    ws, _ = await hello(client, hub.pairing.token)
    await ws.send_json({"t": "lock"})
    await roundtrip(ws)
    assert hub.backend.locked
    await ws.close()


# ---- PC page ---------------------------------------------------------------------------


async def test_reset_signs_phones_out(setup):
    hub, client = setup
    old = hub.pairing.token
    ws, _ = await hello(client, old)
    resp = await client.post("/api/reset", headers=origin(client))
    assert resp.status == 200
    told = [msg.json() async for msg in ws]
    assert {"t": "reset"} in told
    again, reply = await hello(client, old)
    assert reply["reason"] == "token"
    await again.close()


async def test_pc_page_gets_status_and_log(setup):
    hub, client = setup
    pc = await client.ws_connect("/ws/pc", headers=origin(client))
    first = await pc.receive_json()
    assert first["t"] == "hello" and first["code"] == hub.pairing.code
    assert first["pair_url"] == f"{URL}#k={hub.pairing.token}"
    phone, _ = await hello(client, hub.pairing.token)
    while True:
        msg = await pc.receive_json()
        if msg["t"] == "status" and msg["connected"] == 1:
            break
    assert msg["paired"][0]["connected"] is True
    await phone.close()
    await pc.close()


@pytest.mark.parametrize("path", ["/pc", "/api/pc", "/qr.svg"])
async def test_pc_endpoints_work_from_this_pc(setup, path):
    _, client = setup
    assert (await client.get(path)).status == 200


@pytest.mark.parametrize("path", ["/pc", "/api/pc", "/qr.svg"])
async def test_pc_endpoints_refuse_other_host_names(setup, path):
    # A DNS-rebinding page would reach 127.0.0.1 under its own host name.
    _, client = setup
    assert (await client.get(path, headers={"Host": "evil.example:8787"})).status == 403


@pytest.mark.parametrize("path", ["/api/stop", "/api/reset"])
async def test_pc_actions_refuse_other_origins(setup, path):
    hub, client = setup
    token = hub.pairing.token
    resp = await client.post(path, headers={"Origin": "http://evil.example"})
    assert resp.status == 403
    assert hub.pairing.token == token


async def test_pc_socket_refuses_other_origins(setup):
    _, client = setup
    with pytest.raises(aiohttp.WSServerHandshakeError):
        await client.ws_connect("/ws/pc", headers={"Origin": "http://evil.example"})


def _request_from(ip: str, host: str = "127.0.0.1:8787"):
    transport = mock.Mock()
    transport.get_extra_info.side_effect = lambda name, default=None: (ip, 50000) if name == "peername" else default
    return make_mocked_request("GET", "/api/pc", headers={"Host": host}, transport=transport)


def test_only_loopback_counts_as_this_pc():
    assert _is_pc(_request_from("127.0.0.1"))
    assert _is_pc(_request_from("::1", "[::1]:8787"))
    assert not _is_pc(_request_from("192.168.1.20"))
    assert not _is_pc(_request_from("192.168.1.20", "localhost:8787"))


async def test_health_has_no_secrets(setup):
    hub, client = setup
    data = await (await client.get("/api/health")).json()
    assert data["app"] == "nipulate"
    assert hub.pairing.token not in str(data) and hub.pairing.code not in str(data)


@pytest.mark.parametrize("path", ["/", "/pc", "/static/remote.js", "/static/manifest.json", "/api/health"])
async def test_responses_are_uncached(setup, path):
    _, client = setup
    resp = await client.get(path)
    assert resp.status == 200
    assert resp.headers["Cache-Control"] == "no-cache"
