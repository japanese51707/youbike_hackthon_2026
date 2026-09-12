import { useCallback, useState } from "react";

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
    globalThis.navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoords({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        });
        setSource("gps");
        setLocating(false);
      },
      (err) => {
        setError(err?.message || "定位失敗，可改用示範位置");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    );
  }, []);

  return { coords, error, locating, source, locate };
}
