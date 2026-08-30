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

## Running as a service on a Raspberry Pi

To start the server automatically at boot, install it as a systemd service.

1. Clone the repo and create the virtualenv (the service runs the venv's
   Python directly, so this step is required):
   ```
   git clone https://github.com/dmoulton/opencv-fpv-server.git
   cd opencv-fpv-server
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
   On 32-bit Raspberry Pi OS, `pip` pulls OpenCV from piwheels automatically.
   If the build is slow or fails, use the system package instead:
   `sudo apt install python3-opencv` and create the venv with
   `python3 -m venv --system-site-packages .venv`.

2. Make sure the user that will run the service can access the camera:
   ```
   sudo usermod -aG video "$USER"
   ```

3. Install and enable the service:
   ```
   ./deploy/install-service.sh
   ```
   The script writes `/etc/systemd/system/opencv-fpv-server.service` pointing
   at this checkout and the invoking user, then enables and starts it. It
   needs `sudo` (it will prompt).

   Prefer to do it by hand? Edit the paths and `User=` in
   [`deploy/opencv-fpv-server.service`](deploy/opencv-fpv-server.service),
   then:
   ```
   sudo cp deploy/opencv-fpv-server.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now opencv-fpv-server
   ```

**Managing the service:**
```
sudo systemctl status opencv-fpv-server     # is it running?
sudo systemctl restart opencv-fpv-server    # after pulling new code
sudo systemctl stop opencv-fpv-server
sudo systemctl disable opencv-fpv-server    # stop starting at boot
journalctl -u opencv-fpv-server -f          # live logs
```
To see verbose logs, add `-v` to the `ExecStart=` line in the unit file
(there is a commented example in the template), then
`sudo systemctl daemon-reload && sudo systemctl restart opencv-fpv-server`.
