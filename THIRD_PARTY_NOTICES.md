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

Names identify interoperability targets only. No official brand assets are
included; the existing icon is an original drawing.

Unofficial community integration for Home Assistant.
Not affiliated with, maintained by, or endorsed by Yeedi,
Ecovacs or Home Assistant.
