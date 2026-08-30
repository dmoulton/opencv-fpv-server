# opencv-fpv-server
WebSockets based python FPV server, ideal for use with Raspberry Pi.


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
