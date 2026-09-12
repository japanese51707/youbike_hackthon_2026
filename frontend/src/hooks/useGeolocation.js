import { useCallback, useState } from "react";

function locateErrorMessage(err) {
  if (err?.code === 1) return "沒有定位權限，請在瀏覽器允許位置存取";
  if (err?.code === 2) return "目前拿不到位置，請確認定位已開啟";
  if (err?.code === 3) return "定位逾時，請再試一次";
  if (!globalThis.isSecureContext) return "定位需要本機或 HTTPS";
  return err?.message || "定位失敗，可改拖地圖中心搜尋";
}

function readPosition(highAccuracy, timeoutMs) {
  return new Promise((resolve, reject) => {
    globalThis.navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: highAccuracy,
      timeout: timeoutMs,
      maximumAge: highAccuracy ? 0 : 60000,
    });
  });
}

export default function useGeolocation() {
  const [coords, setCoords] = useState(null);
  const [error, setError] = useState(null);
  const [locating, setLocating] = useState(false);
  const [source, setSource] = useState("none");

  const locate = useCallback(() => {
    if (!globalThis.navigator?.geolocation) {
      setError("這台裝置沒有定位功能");
      return;
    }
    setLocating(true);
    setError(null);
    readPosition(true, 12000)
      .then((position) => {
        setCoords({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          at: Date.now(),
        });
        setSource("gps");
        setLocating(false);
      })
      .catch((err) => {
        setError(locateErrorMessage(err));
        setLocating(false);
      });
  }, []);

  return { coords, error, locating, source, locate };
}
