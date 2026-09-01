#!/bin/sh
# Always force the Tor proxy by its Docker service hostname — every other argument
# passed to `docker compose run onionsearch ...` is forwarded straight through via
# "$@". Even if this line were somehow skipped, the `isolated` Docker network (see
# docker-compose.yml) still has no route to the internet at all, so there is no
# other path this container's traffic could take.
exec onionsearch "$@" --proxy tor:9050
