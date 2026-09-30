#!/usr/bin/env python3
"""Expose the ingest service on 131's host interface for the PM demo.

The service runs inside the RAGFlow container, reachable only on the docker
network. Publishing a new container port would mean recreating
docker-ragflow-cpu-1, which would interrupt RAGFlow itself — too much risk for
a demo. This forwards host:9800 to the container instead, touching nothing
that is already running.

Deliberately dependency-free (stdlib only, no socat/nginx changes) so it can
be dropped onto the host and started immediately. For the same reason it stays
compatible with 131's system interpreter, /usr/bin/python3 == 3.6.8 — hence no
``from __future__ import annotations``. Pointing systemd at the newer python in
/root/miniconda3 would work too, but that install belongs to someone else.

Installed as a systemd unit; see deploy/README.md. Manual run:
    nohup python3 /opt/gcn/demo_forward.py > /tmp/demo_forward.log 2>&1 &

Stop with: pkill -f '[d]emo_forward.py'   (the [d] stops the pattern matching
the killing command's own line, which otherwise takes out the caller's shell)
"""

import logging
import socket
import socketserver
import sys
import threading

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 9800
TARGET_HOST = "192.168.80.6"     # docker-ragflow-cpu-1 on the docker_ragflow net
TARGET_PORT = 9800
BUFFER = 65536

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s | %(message)s",
)
logger = logging.getLogger("forward")


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        client = self.request
        try:
            upstream = socket.create_connection((TARGET_HOST, TARGET_PORT),
                                                timeout=30)
        except OSError as exc:
            logger.warning("upstream unreachable: %s", exc)
            client.close()
            return

        # pump both directions until either side closes
        def pump(src, dst, label):
            try:
                while True:
                    data = src.recv(BUFFER)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                for sock in (src, dst):
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

        t = threading.Thread(target=pump, args=(client, upstream, "up"),
                             daemon=True)
        t.start()
        pump(upstream, client, "down")
        t.join(timeout=5)
        upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    logger.info("forwarding %s:%d -> %s:%d",
                LISTEN_HOST, LISTEN_PORT, TARGET_HOST, TARGET_PORT)
    try:
        with Server((LISTEN_HOST, LISTEN_PORT), Handler) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        logger.info("stopped")
    except OSError as exc:
        logger.error("cannot listen on %s:%d — %s", LISTEN_HOST, LISTEN_PORT, exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
