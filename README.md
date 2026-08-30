# opencv-fpv-server
WebSockets based python FPV server, ideal for use with Raspberry Pi.


**Setup:**

Use a virtual environment so the dependencies don't touch your system Python:
```
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
The `.venv/` directory is gitignored. Activate it in each new shell before
running the server; run `deactivate` when you're done.

**Usage:**
```
python3 server.py
```
Then open `http://<host>:8080/cam.html` in a browser. The server also exposes
an MJPEG stream at `/stream.mjpg` (for VLC, OBS, ffmpeg) and a still frame at
`/snapshot.jpg`.

**Logging:**

The server is quiet by default (errors only). Pass `-v` / `--verbose` to log
connections, client join/leave, frame counts, and camera status:
```
python3 server.py -v
```
