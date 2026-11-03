# CyberVision Phone Camera (MVP)

Android companion camera publisher for the Python traffic-surveillance server.

## Features

- CameraX rear-camera preview.
- JPEG frames sent as binary WebSocket messages with an API key in the handshake.
- CameraX `STRATEGY_KEEP_ONLY_LATEST` and client-side rate limit of 10 frames per second.
- Visible preview and status, with explicit Start and Stop buttons.
- HTTPS URLs are automatically upgraded to WSS.

## Build

Open this directory in Android Studio with JDK 17 and Android SDK 36, then build the `app` debug variant. GitHub Actions also builds the debug APK. The Android module is new and has not yet been verified on a physical phone.

## Connect to Colab

1. Start the current Colab notebook and copy the HTTPS Cloudflare/ngrok URL.
2. Enter the URL, camera ID (for example `road-01`) and the exact same API key as the dashboard.
3. Start the stream in the phone app.
4. In the dashboard Live tab, enter `phone-camera:road-01` and start analysis.

WebSocket endpoint: `/api/v1/phone/stream/{camera_id}`. Payloads are JPEG frames up to 4 MiB. The server keeps only the newest frame in a one-slot queue and records dropped-frame counts.

## Network modes

- **Internet:** phone sends WSS to the public HTTPS tunnel or a deployed HTTPS/WSS endpoint.
- **Same Wi-Fi:** use WS to a local Python host LAN address when the server runs on that host.
- **USB:** Colab cannot access an Android device over direct USB/ADB. USB tethering can provide network connectivity. A direct ADB/USB bridge is only possible when Python runs on the connected PC.

## MVP limits

- Keep the app visible while streaming; a persistent Android foreground camera service has not been added yet.
- The first transport is JPEG/WebSocket for a small proof-of-concept. It is less bandwidth-efficient than hardware H.264 over WebRTC/WHIP/MediaMTX.
- Adaptive bitrate, camera rotation metadata, front/rear switching, and long-running background streaming remain future improvements.
