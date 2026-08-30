"""
server.py
WebSocket FPV server
Copyright (C) 2023  Aiden Bohlander

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import argparse
import asyncio
import base64
import functools
import http.server
import logging
import socket
import threading
import time
from pathlib import Path

import cv2
import websockets

HOST = "0.0.0.0"       # listen on all interfaces so other devices on the LAN can connect
WS_PORT = 8000         # WebSocket stream port
WEB_PORT = 8080        # HTTP port: serves cam.html, /stream.mjpg, /snapshot.jpg
CAMERA_INDEX = 0
TARGET_FPS = 30
JPEG_QUALITY = 80

WEB_ROOT = Path(__file__).resolve().parent

log = logging.getLogger("fpv-server")


def configure_logging(verbose=False):
    """Quiet by default (errors only); -v/--verbose enables the full activity log."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("websockets").setLevel(
        logging.INFO if verbose else logging.WARNING
    )


# --------------------------------------------------------------------------
# Shared frame buffer: one capture thread fills it, any number of consumers
# (WebSocket clients, MJPEG clients) read from it.
# --------------------------------------------------------------------------
class FrameHub:
    def __init__(self):
        self._cond = threading.Condition()
        self._jpeg = None
        self._seq = 0
        self._stop = threading.Event()

    def publish(self, jpeg_bytes):
        with self._cond:
            self._jpeg = jpeg_bytes
            self._seq += 1
            self._cond.notify_all()

    def get(self, last_seq, timeout=5.0):
        """Block until a frame newer than last_seq is available.

        Returns (seq, jpeg_bytes), or (last_seq, None) on timeout.
        """
        with self._cond:
            if not self._cond.wait_for(
                lambda: self._seq != last_seq or self._stop.is_set(), timeout
            ):
                return last_seq, None
            return self._seq, self._jpeg

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    @property
    def stopped(self):
        return self._stop.is_set()


hub = FrameHub()


def open_camera(warn=True):
    """Open the capture device. Returns the VideoCapture or None."""
    cam = cv2.VideoCapture(CAMERA_INDEX)
    if not cam.isOpened():
        if warn:
            log.error(
                "Could not open camera index %s. On macOS, grant camera access to "
                "your terminal in System Settings > Privacy & Security > Camera. "
                "Retrying silently until it becomes available.",
                CAMERA_INDEX,
            )
        return None
    width = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    log.info("Camera %s opened (%dx%d)", CAMERA_INDEX, width, height)
    return cam


def capture_loop():
    """Continuously grab frames, JPEG-encode them, and publish to the hub."""
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    frame_interval = 1.0 / TARGET_FPS
    camera = None
    warned_open = False
    warned_empty = False
    while not hub.stopped:
        if camera is None:
            camera = open_camera(warn=not warned_open)
            if camera is None:
                warned_open = True  # only report the open failure once
                time.sleep(2.0)  # retry until permission is granted / camera appears
                continue
            warned_open = False
        success, frame = camera.read()
        if not success:
            if not warned_empty:
                log.warning("Camera read failed; will keep retrying")
                warned_empty = True
            camera.release()
            camera = None
            time.sleep(1.0)
            continue
        warned_empty = False
        ok, buffer = cv2.imencode(".jpg", frame, encode_params)
        if ok:
            hub.publish(buffer.tobytes())
        time.sleep(frame_interval)
    if camera is not None:
        camera.release()


# --------------------------------------------------------------------------
# WebSocket stream (original protocol: base64 data-URI strings, one per frame)
# --------------------------------------------------------------------------
async def handle_ws(websocket):
    peer = websocket.remote_address
    log.info("WebSocket client connected: %s", peer)
    last_seq = 0
    frames_sent = 0
    try:
        while True:
            last_seq, jpeg = await asyncio.to_thread(hub.get, last_seq)
            if jpeg is None:
                continue
            uri = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
            await websocket.send(uri)
            frames_sent += 1
    except websockets.ConnectionClosed:
        log.info("WebSocket client left: %s (%d frames)", peer, frames_sent)
    except Exception:
        log.exception("WebSocket stream error for %s", peer)


# --------------------------------------------------------------------------
# HTTP: static files + MJPEG stream + single snapshot
# --------------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("HTTP %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/stream.mjpg":
            self.stream_mjpeg()
        elif path == "/snapshot.jpg":
            self.send_snapshot()
        else:
            super().do_GET()

    def send_snapshot(self):
        _, jpeg = hub.get(0, timeout=5.0)
        if jpeg is None:
            self.send_error(503, "No frame available")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(jpeg)

    def stream_mjpeg(self):
        self.send_response(200)
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=frame"
        )
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Connection", "close")
        self.end_headers()
        log.info("MJPEG client connected: %s", self.address_string())
        last_seq = 0
        frames = 0
        try:
            while not hub.stopped:
                last_seq, jpeg = hub.get(last_seq, timeout=5.0)
                if jpeg is None:
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(b"Content-Length: %d\r\n\r\n" % len(jpeg))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                frames += 1
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            log.info(
                "MJPEG client left: %s (%d frames)", self.address_string(), frames
            )


def lan_ip():
    """Best-effort guess of this machine's LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_http_server():
    handler = functools.partial(Handler, directory=str(WEB_ROOT))
    httpd = http.server.ThreadingHTTPServer((HOST, WEB_PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main():
    threading.Thread(target=capture_loop, daemon=True).start()
    start_http_server()
    ip = lan_ip()
    async with websockets.serve(handle_ws, HOST, WS_PORT):
        # Always shown, regardless of log level.
        print(
            f"Viewer (browser):   http://{ip}:{WEB_PORT}/cam.html\n"
            f"MJPEG (VLC/OBS):    http://{ip}:{WEB_PORT}/stream.mjpg\n"
            f"Snapshot:           http://{ip}:{WEB_PORT}/snapshot.jpg\n"
            f"WebSocket stream:   ws://{ip}:{WS_PORT}/\n"
            "Ctrl+C to stop.  (-v for activity logging)",
            flush=True,
        )
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenCV FPV / webcam streaming server")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="log connections, frame counts, and camera status",
    )
    args = parser.parse_args()
    configure_logging(args.verbose)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        hub.stop()
