# Ocean gateway

`ocean-gateway install` installs the official OmniRoute 3.8.51 npm release in
`$PREFIX/opt/ocean-gateway`. Its release integrity is checked against the pinned
SHA-512 value. No npm lifecycle hooks are executed. Provider adapters, token
refresh, request translation and quota enforcement remain in upstream OmniRoute.

`ocean-gateway serve` runs it in the foreground, bound to `127.0.0.1:20129`.
Ocean's Android foreground service owns this process when launched by Connect.
`start`, `status`, and `stop` are available for terminal use. Gateway state and
randomly generated management/encryption secrets are private to
`$PREFIX/var/lib/ocean-gateway`, with directory mode 0700 and files mode 0600.

This package adds a command; it does not replace other installed packages.
Sources: official Node.js through Ocean's signed package catalogue and the
official OmniRoute npm release. No binaries, patches, or recipes are obtained
from another terminal distribution.
