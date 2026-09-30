#!/usr/bin/env python3
"""Stream docker images from 131 to the GPU box (10.148.4.21), laptop-mediated.

The two machines are firewall-isolated (different zones) and cannot reach each
other; this laptop is the only host that can talk to both — 131 via the
JumpServer ssh alias ``wenge-ragflow-131``, the GPU box via MAnywhere. The GPU
box's own dockerhub pulls are rate-limited, so we source from 131, which already
holds the exact RAGFlow-stack images.

Pipe shape:

    ssh 131 "docker save IMG | pigz | base64"   (base64 survives the JumpServer;
        raw binary does NOT — the gateway truncates binary streams, verified)
      → laptop: base64 -d > temp.tgz, integrity-checked with ``gzip -t``
      → sftp the temp file to newbox:/tmp, then ``docker load -i`` there

Why base64: the JumpServer that fronts 131 silently drops bytes from raw binary
ssh streams (an 8 GB save lost ~80 KB and every gzip failed). base64 text passes
intact — same reason scp is blocked and deploy/README uses base64. pigz (present
on 131, 64 cores) parallel-compresses so the slow gateway moves fewer bytes.

``docker load`` restores the original repo:tag, so no retag step is needed.

Credentials: the GPU box password comes from GCN_NEWBOX_PW (never hardcoded).
Run:  GCN_NEWBOX_PW=... uv run --with paramiko python code/deploy/transfer_images.py [img ...]
"""

import os
import subprocess
import sys
import tempfile
import time

import paramiko

NEWBOX_HOST = "10.148.4.21"
NEWBOX_USER = "root"
JUMP_ALIAS = "wenge-ragflow-131"  # ssh config alias routed through JumpServer

# 131 already has these exact tags (verified). ragflow last — it is the big one.
DEFAULT_IMAGES = [
    "valkey/valkey:8",
    "pgsty/minio:RELEASE.2026-03-25T00-00-00Z",
    "mysql:8.0.39",
    "elasticsearch:8.11.3",
    "infiniflow/ragflow:v0.26.1",
]

CHUNK = 1 << 20  # 1 MiB


def connect_newbox():
    pw = os.environ.get("GCN_NEWBOX_PW")
    if not pw:
        raise SystemExit("GCN_NEWBOX_PW is required (GPU box root password)")
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(NEWBOX_HOST, username=NEWBOX_USER, password=pw,
                timeout=30, banner_timeout=40)
    return cli


def already_present(cli, image):
    _, out, _ = cli.exec_command(
        f'docker image inspect {image} >/dev/null 2>&1 && echo YES || echo NO')
    return out.read().decode().strip() == "YES"


def _exec(cli, cmd, timeout=600):
    _, out, err = cli.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "ignore")
    e = err.read().decode("utf-8", "ignore")
    rc = out.channel.recv_exit_status()
    return rc, o, e


def transfer(cli, image, idx, tmpdir):
    """131 -> laptop (base64 through gateway) -> sftp -> docker load. Returns tuple."""
    t0 = time.time()
    local_tgz = os.path.join(tmpdir, f"gcn_img_{idx}.tgz")
    remote_tgz = f"/tmp/gcn_img_{idx}.tgz"

    # stage A: pull to laptop as base64-over-ssh, decode locally. The JumpServer
    # intermittently injects a banner line into stdout, which corrupts base64, so
    # the payload is fenced between unique markers and an awk pass keeps only the
    # bytes between them before decoding. gzip -t then proves integrity.
    begin, end = "__GCN_B64_BEGIN__", "__GCN_B64_END__"
    remote = (f"echo {begin}; docker save {image} 2>/dev/null | pigz | base64; "
              f"echo {end}")
    with open(local_tgz, "wb") as fh:
        enc = subprocess.Popen(["ssh", JUMP_ALIAS, remote], stdout=subprocess.PIPE)
        mid = subprocess.Popen(
            ["awk", f"/{begin}/{{f=1;next}} /{end}/{{f=0}} f"],
            stdin=enc.stdout, stdout=subprocess.PIPE)
        dec = subprocess.Popen(["base64", "-d"], stdin=mid.stdout, stdout=fh)
        enc.stdout.close()
        mid.stdout.close()
        dec.wait()
        mid.wait()
        enc.wait()
    if enc.returncode != 0 or dec.returncode != 0:
        return False, 0, time.time() - t0, "stage A (131->laptop) failed"
    if subprocess.run(["gzip", "-t", local_tgz]).returncode != 0:
        return False, os.path.getsize(local_tgz), time.time() - t0, "local gzip corrupt"
    sent = os.path.getsize(local_tgz)

    # stage B: sftp the verified file to the newbox, load, clean up
    sftp = cli.open_sftp()
    sftp.put(local_tgz, remote_tgz)
    sftp.close()
    os.remove(local_tgz)
    rc, out, err = _exec(cli, f"docker load -i {remote_tgz} 2>&1; rm -f {remote_tgz}")
    ok = rc == 0 and "Loaded image" in out
    return ok, sent, time.time() - t0, out.strip().replace("\n", " | ")


def main():
    images = sys.argv[1:] or DEFAULT_IMAGES
    cli = connect_newbox()
    tmpdir = os.environ.get("GCN_TMPDIR", tempfile.gettempdir())
    print(f"target {NEWBOX_HOST}; {len(images)} image(s); tmp={tmpdir}")
    for i, img in enumerate(images):
        if already_present(cli, img):
            print(f"[skip] {img} already on target")
            continue
        # The JumpServer sometimes returns a banner instead of running the
        # command, corrupting the stream; gzip -t catches it. Retry until a
        # command-executing connection lands (they are common).
        ok = False
        for attempt in range(1, 9):
            print(f"[send] {img} (try {attempt}/8) ...", flush=True)
            ok, sent, secs, out = transfer(cli, img, i, tmpdir)
            mb = sent / 1024 / 1024
            rate = mb / secs if secs else 0
            status = "OK" if ok else "FAIL"
            print(f"[{status}] {img}  {mb:.0f}MB in {secs:.0f}s ({rate:.1f} MB/s)  {out}",
                  flush=True)
            if ok:
                break
        if not ok:
            print("  aborting: transfer failed after 8 tries", flush=True)
            break
    cli.close()


if __name__ == "__main__":
    main()
