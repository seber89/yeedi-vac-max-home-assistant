# Third-party notices and interoperability provenance

This repository remains MIT licensed. LICENSE is unchanged.

The following GPL-3.0 projects were consulted solely for interoperability facts
(command names, request/response fields, application identifiers, device generation):

- [mrbungle64/ecovacs-deebot.js](https://github.com/mrbungle64/ecovacs-deebot.js),
  revision `f1ae56e69d409c5e02f72d4ea313024aa146363e`.
- [DeebotUniverse/client.py](https://github.com/DeebotUniverse/client.py),
  revision `be8cbbda9159e8b750efc4727eccf66ae5ff80bf`.
- [gyordanov/client.py](https://github.com/gyordanov/client.py),
  revision `07d93928a1d556aae711b41335afbddd5bd61551`.

Their source code, parsers, renderers, tests and fixtures are not included,
translated, or used as runtime dependencies here. The implementation and
synthetic tests are independently written. See docs/PROTOCOL.md for facts and
limitations. No third-party decompressor or map renderer is shipped.
aiohttp is supplied by Home Assistant; no new runtime dependencies are added.

Beta 5 additionally checks the same pinned references for MQTT connection/topic
facts and the MajorMap CRC-list / empty-piece sentinel / MinorMap request fields.
No algorithms, decoders, renderers, classes, fixtures or tests are ported.
In Beta 5, MQTT was intentionally not implemented: a secure complete connection configuration
for this Yeedi setup is not sufficiently verified (see docs/PROTOCOL.md).

Beta 6.3 adds an original, isolated passive MQTT diagnostic after verification of
session/topic facts and explicit owner approval of the scoped TLS exception.
MQTT framing follows the public OASIS MQTT 3.1.1 specification, not a copied
client implementation. Python asyncio/ssl/lzma only; no new runtime dependency.
aiomqtt was evaluated but is not shipped or required. No foreign dispatcher,
MQTT classes, decoder, tests or fixtures are included. See docs/PROTOCOL.md for
the precise scope, security limitation and protocol sources.

Names identify interoperability targets only. No official brand assets are
included; the existing icon is an original drawing.

Beta 6 uses only format facts from the same pinned mapTemplate.js: the short
Legacy-LZMA header, square column-major tile/pixel layout and basic palette
semantics. No decoder/renderer/manager code or fixtures are ported. The bounded
Python decoder adapter and PNG writer are original; decompression uses Python's
standard-library lzma module. No new runtime dependency or MQTT implementation.

Unofficial community integration for Home Assistant.
Not affiliated with, maintained by, or endorsed by Yeedi,
Ecovacs or Home Assistant.
