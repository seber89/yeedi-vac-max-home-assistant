# Post-RC.20: Cached transport and Minor request context

Research baseline: 0.2.0-rc.20, 99cbbd9ea2d06cf3ce3215f3d2725da78a952036.
Decision: **no evidence-backed RC.21 runtime patch or hardware-decisive new
diagnostic**. Runtime and version remain RC.20. No device was contacted in this
research. Only public sources and original local synthetic tests were used.

## Hardware evidence supplied by the owner

Normal discovery times out on CachedMapInfo and selects a Major fallback.
Independent getMapInfo_V2 current ID matches. This is not a using observation.
Fresh and normal builds repeatedly receive nonempty compressed Minor payloads,
decode without errors, and assemble only zero bytes. Last-good persists. Earlier
builds have produced visible geometry, so this does not establish a broken codec.

## Exact transport and timeout boundaries

maps -> command(getCachedMapInfo) -> authenticate (token check/auth lock) ->
_device_request -> _request (request semaphore, aiohttp POST, JSON parse) ->
command_body -> maps data.info validation. Endpoint iot/devmanager.do; ordinary
JSON command envelope, empty data, existing DE session, normal TLS verification.

maps has a 40-second outer timeout. HTTP attempts each have a 15-second limit;
at most two read attempts and one one-second delay. Authentication/semaphore
waiting is inside the outer budget. The coordinator holds the device lock
before these methods; command does not reacquire it. No local event wait exists.

An HTTP-layer TimeoutError ultimately becomes CommandTimeout and permits legacy
fallback. An outer TimeoutError propagates without that fallback. A portal
errno=500 or 4200 is instead DeviceOffline, not CommandTimeout. These distinct
routes currently collapse to broader public outcomes in some observations.
The RC.20 selected major_fallback specifically identifies the CommandTimeout
route, but cannot prove whether the wait occurred in authentication, semaphore,
connect or response. Even CommandTimeout can originate in authentication.
The exact hardware cause is therefore **not known**. We do not infer a received
server timeout response or event-only behavior from a timeout enum.

Success/invalid JSON, rejected portal/device status and outer timeout are
distinguishable in code; precise send/receive phases are not retained. Adding
such instrumentation would clarify latency but would not decide the zero-Minor
cause after the confirmed current-ID match, so it is not added.

## Pinned protocol sources (facts only)

- [JS map commands, f1ae56e](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/commands/map.js):
  getCachedMapInfo has no command data; getMajorMap has no command data;
  getMinorMap uses mid, pieceIndex and type=ol. Outline maps use ol;
  other named layers are distinct. Yeedi current discovery uses
  getMapInfo_V2 with type=0 and no mid. No revision token is in these requests.
- [JS dispatcher, same pin](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/ecovacsMessageDispatcher.js):
  classic getMapInfo returns status and triggers onMapInfo. CachedMapInfo push
  handling also exists. This is not proof that the target's cached HTTP response
  is necessarily ACK-only or that an HTTP push receiver is available here.
- [Python cached command](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/commands/json/map/cached_map_info.py)
  and [cached message, be8cbbd](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/messages/json/map/cached_map_info.py):
  direct-response and onCachedMapInfo handling share map-list semantics,
  data.info contains mid/using. This supports both interfaces, not universal
  direct availability on 04z443.
- [Python Minor command, same pin](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/commands/json/map/__init__.py):
  independently confirms mid/type/pieceIndex and pieceValue response fields.
  [Major event metadata](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/messages/json/map/__init__.py)
  uses mid and the value list. These references do not document a per-Minor
  revision credential for this target.

No source establishes that unknown cached using causes zero Minor values when
the independent current ID matches. There is no evidence-backed additional
read-only using route in the existing architecture. This cached investigation
is therefore closed as non-decisive, not declared impossible for all devices.

## Major/Minor context and proof limits

parse_major validates mid, square piece/cell dimensions, pixel resolution and
bounded value-list integers. The value-list slots determine pieceIndex; values
are cache-comparison CRC metadata, not request IDs. EMPTY_PIECE slots are omitted.
No public required token is discarded from the documented Minor request.

load_raw_map reads Major, requests required slots with exactly the documented
fields, validates response mid/type/index and decoded length, then reads Major
again and requires exact parsed equality. Different IDs, dimensions, resolution
or CRC-list values reject the build. Cached reuse requires matching identity,
dimensions/resolution and per-slot CRC. Fresh passes no previous pieces.
No zero build overwrites last-good. prepare_raw_map's status response supplies
no independently documented using or generation proof and is discarded.

An important remaining hypothesis is **stable Major metadata with Minor data
from a different or placeholder source context**. Existing transport provides
no independently authenticated per-piece revision, so it cannot distinguish
that hypothesis from genuine zero data. This is not proof of a server defect,
missing parameter or cache bug. Extra fields must not be invented. Historical
piece counts do not identify a layer or prove quality; no private historical
wire samples exist here to establish a different successful request profile.

## Original synthetic tests and decision

tests/test_map_context_research.py checks the exact documented request fields,
rejects changed Major CRC/resolution/ID and a foreign Minor map, and demonstrates
the stable-Major/zero-Minor proof boundary. It also verifies unchanged Major can
reuse a good cached image whereas a fresh zero build fails. These are research
tests passing existing code, **not fail-first evidence of a fix**.
Existing RC.14/19/20 tests cover zero builds, retained last-good, context changes,
invalid cached lists, bounded probes and no redundant discovery read.

No runtime modification is justified. No more cleaning run or cached-timeout RC
is requested. Next prerequisite: a manufacturer/pinned target-specific source
documenting another Minor context field, or a safely TLS-verified authenticated
event path with lawful, privacy-preserving structural evidence that it carries
the missing map source. The prior safe-MQTT gate remains closed; no insecure
capture, credentials, map dump, TLS bypass or setMajorMap experiment is proposed.
