/** Camera capture via getUserMedia - no file picker. */

const CameraCapture = {
  stream: null,

  async start(videoEl) {
    this.stop();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Camera API not available in this browser");
    }
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });
    videoEl.srcObject = this.stream;
    await videoEl.play();
  },

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
  },

  snap(videoEl, canvasEl) {
    const w = videoEl.videoWidth || 1280;
    const h = videoEl.videoHeight || 720;
    canvasEl.width = w;
    canvasEl.height = h;
    const ctx = canvasEl.getContext("2d");
    ctx.drawImage(videoEl, 0, 0, w, h);
    return canvasEl.toDataURL("image/jpeg", 0.85);
  },
};

async function getGeo() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve({ latitude: null, longitude: null });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
        }),
      () => resolve({ latitude: null, longitude: null }),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  });
}

window.GFSCamera = { CameraCapture, getGeo };
