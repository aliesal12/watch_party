#!/usr/bin/env python3
"""
serve.py - Range-aware static HTTP file server (Layer 1: transport).

Serves the RAW, UNTOUCHED bytes of a video file over HTTP with full
HTTP range-request (206 Partial Content) support, so a remote VLC can
open the URL like a local file and SEEK anywhere instantly.

NO transcoding, NO re-encoding, NO quality loss - the remote viewer
decodes a bit-for-bit identical stream. This is the whole point.

Stdlib only (no pip installs needed).

Usage:
    python serve.py                       # serve current dir on 0.0.0.0:8000
    python serve.py --dir "D:\\Movies" --port 8000
    python serve.py --dir "D:\\Movies" --port 8000 --token mysecret

If --token is given, every request must include ?token=mysecret
(a tiny guard so random port-scanners can't pull your movie).
"""

import argparse
import os
import socketserver
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class RangeRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler + HTTP Range support so VLC can seek.

    Python's SimpleHTTPRequestHandler does not honor the Range header,
    which makes remote seeking fail. We override send_head to emit
    206 Partial Content with Content-Range when a Range header is present.
    """

    # set by the factory in main()
    required_token = None

    # ---- optional token gate ---------------------------------------
    def _token_ok(self):
        if not self.required_token:
            return True
        qs = parse_qs(urlparse(self.path).query)
        return qs.get("token", [None])[0] == self.required_token

    def _strip_query(self):
        # SimpleHTTPRequestHandler.translate_path already ignores the
        # query, but be explicit and keep self.path clean for logging.
        return urlparse(self.path).path

    def do_GET(self):
        if not self._token_ok():
            self.send_error(HTTPStatus.FORBIDDEN, "Missing or bad token")
            return
        super().do_GET()

    def do_HEAD(self):
        if not self._token_ok():
            self.send_error(HTTPStatus.FORBIDDEN, "Missing or bad token")
            return
        super().do_HEAD()

    # ---- the actual range logic ------------------------------------
    def send_head(self):
        path = self.translate_path(self._strip_query())

        if os.path.isdir(path):
            # allow simple directory listing so you can find the file name
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            file_len = fs.st_size
            ctype = self.guess_type(path)
            range_header = self.headers.get("Range")

            if range_header is None:
                # whole-file response
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(file_len))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.end_headers()
                return f

            # parse "bytes=START-END" (END optional)
            start, end = self._parse_range(range_header, file_len)
            if start is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_len}")
                self.end_headers()
                f.close()
                return None

            length = end - start + 1
            f.seek(start)
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            # hand back a limited reader so copyfile sends only `length` bytes
            return _LimitedReader(f, length)
        except Exception:
            f.close()
            raise

    @staticmethod
    def _parse_range(range_header, file_len):
        """Return (start, end) inclusive byte offsets, or (None, None)."""
        units, _, rng = range_header.partition("=")
        if units.strip().lower() != "bytes":
            return None, None
        # we only support a single range (VLC sends single ranges)
        rng = rng.split(",")[0].strip()
        if "-" not in rng:
            return None, None
        start_s, _, end_s = rng.partition("-")
        try:
            if start_s == "":
                # suffix range: last N bytes  ("bytes=-500")
                n = int(end_s)
                if n <= 0:
                    return None, None
                start = max(0, file_len - n)
                end = file_len - 1
            else:
                start = int(start_s)
                end = int(end_s) if end_s else file_len - 1
        except ValueError:
            return None, None

        if start > end or start >= file_len:
            return None, None
        end = min(end, file_len - 1)
        return start, end


class _LimitedReader:
    """Wrap a file object so .read() never returns more than `remaining`
    bytes total. copyfile() in the handler streams from this."""

    def __init__(self, fileobj, remaining):
        self._f = fileobj
        self._remaining = remaining

    def read(self, amt=-1):
        if self._remaining <= 0:
            return b""
        if amt is None or amt < 0:
            amt = self._remaining
        amt = min(amt, self._remaining)
        data = self._f.read(amt)
        self._remaining -= len(data)
        return data

    def close(self):
        self._f.close()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description="Range-aware static file server for VLC streaming.")
    ap.add_argument("--dir", default=".", help="Directory containing the video file(s).")
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default: all interfaces).")
    ap.add_argument("--port", type=int, default=8000, help="TCP port to serve on (Port A).")
    ap.add_argument("--token", default=None, help="Optional ?token=... required on every request.")
    args = ap.parse_args()

    directory = os.path.abspath(args.dir)
    if not os.path.isdir(directory):
        raise SystemExit(f"--dir is not a directory: {directory}")

    handler_cls = partial(RangeRequestHandler, directory=directory)
    # stash token on the class (partial can't set class attrs)
    RangeRequestHandler.required_token = args.token

    httpd = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"Serving (raw, range-enabled) {directory}")
    print(f"  on http://{args.host}:{args.port}/")
    if args.token:
        print(f"  token required: append ?token={args.token} to the URL")
    print("Friend opens in VLC:  Media -> Open Network Stream -> "
          f"http://<your-public-ip>:{args.port}/<filename>"
          + (f"?token={args.token}" if args.token else ""))
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping file server.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
