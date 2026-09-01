# OnionSearch, sandboxed. This container is deliberately given NO route to the
# internet at all (see docker-compose.yml's `isolated` network) — its only possible
# network destination is the `tor` service on the same compose stack. Even if
# OnionSearch's own code had a proxy bug, there is no path out of this container
# except through Tor: the isolation is enforced by the Docker network namespace, not
# by trusting the application's proxy configuration.
FROM python:3.12-slim

RUN pip install --no-cache-dir onionsearch

WORKDIR /output
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
