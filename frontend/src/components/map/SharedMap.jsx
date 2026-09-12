import { MapboxOverlay } from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  isAllowedBasemapRequest,
  mapConfig,
} from "../../config/mapConfig.js";
import { createBasemapStyle } from "../../config/darkBasemapStyle.js";
import { createNoBasemapStyle } from "../../config/noBasemapStyle.js";
import { useAppearance } from "../../theme/ThemeProvider.jsx";
import { applyMapAppearance } from "./applyMapAppearance.js";
import BasemapStatus from "./BasemapStatus.jsx";

const BLOCKED_RESOURCE_URL = "data:application/octet-stream;base64,";

// 自訂「2D」控制鈕：一鍵把 pitch/bearing 歸零，回到正北俯視（ADR-204 地圖互動）。
class Reset2DControl {
  onAdd(map) {
    this._map = map;
    this._container = document.createElement("div");
    this._container.className = "maplibregl-ctrl maplibregl-ctrl-group";
    this._button = document.createElement("button");
    this._button.type = "button";
    this._button.title = "回復 2D 俯視";
    this._button.setAttribute("aria-label", "回復 2D 俯視");
    this._button.className = "shared-map-2d-btn";
    this._button.textContent = "2D";
    this._onClick = () =>
      map.easeTo({ pitch: 0, bearing: 0, duration: 300 });
    this._button.addEventListener("click", this._onClick);
    this._container.appendChild(this._button);
    return this._container;
  }

  onRemove() {
    this._button?.removeEventListener("click", this._onClick);
    this._container?.parentNode?.removeChild(this._container);
    this._map = undefined;
  }
}

export default function SharedMap({
  ariaLabel,
  className = "",
  focusTarget = null,
  getTooltip,
  initialViewState,
  layers,
  overlay = null,
  onCameraMove,
  onCameraIdle,
}) {
  const { mode, colors } = useAppearance();
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const themedTooltip = useCallback((info) => {
    const result = getTooltip?.(info);
    if (!result) return null;
    const content = typeof result === "string" ? { text: result } : result;
    return { ...content, style: { ...content.style, background: colors.overlay, color: colors.text, border: `1px solid ${colors.border}`, borderRadius: "10px", padding: "10px 12px", boxShadow: `0 4px 16px ${colors.shadow}` } };
  }, [getTooltip, colors]);
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const overlayPropsRef = useRef({ layers, getTooltip: themedTooltip });
  const fallbackAppliedRef = useRef(false);
  const [basemapStatus, setBasemapStatus] = useState("loading");
  const [fallbackReason, setFallbackReason] = useState(null);

  overlayPropsRef.current = { layers, getTooltip: themedTooltip };
  const onCameraMoveRef = useRef(onCameraMove);
  const onCameraIdleRef = useRef(onCameraIdle);
  onCameraMoveRef.current = onCameraMove;
  onCameraIdleRef.current = onCameraIdle;
  const focusTargetRef = useRef(focusTarget);
  focusTargetRef.current = focusTarget;

  useEffect(() => {
    if (!containerRef.current) return undefined;

    const startsOffline = navigator.onLine === false;
    fallbackAppliedRef.current = startsOffline;
    setBasemapStatus(startsOffline ? "no-basemap" : "loading");
    setFallbackReason(startsOffline ? "瀏覽器目前離線" : null);

    let disposed = false;
    let styleLoadTimer;
    let resourceLoadTimer;
    let resourceErrorTimestamps = [];
    let styleReady = false;
    let map;
    let overlay;

    const clearStyleLoadTimer = () => {
      if (styleLoadTimer) {
        window.clearTimeout(styleLoadTimer);
        styleLoadTimer = undefined;
      }
    };
    const clearResourceLoadTimer = () => {
      if (resourceLoadTimer) {
        window.clearTimeout(resourceLoadTimer);
        resourceLoadTimer = undefined;
      }
    };
    const resetResourceErrors = () => {
      resourceErrorTimestamps = [];
    };
    const clearRuntimeTimers = () => {
      clearStyleLoadTimer();
      clearResourceLoadTimer();
      resetResourceErrors();
    };
    const switchToNoBasemap = (reason) => {
      if (disposed || fallbackAppliedRef.current || !map) return;
      fallbackAppliedRef.current = true;
      clearRuntimeTimers();
      setFallbackReason(reason);
      setBasemapStatus("no-basemap");
      try {
        map.setStyle(createNoBasemapStyle(modeRef.current));
      } catch {
        setFallbackReason("本地 no-basemap 初始化失敗");
        setBasemapStatus("map-unavailable");
      }
    };
    const transformRequest = (url) => {
      if (isAllowedBasemapRequest(url)) {
        return { url };
      }
      queueMicrotask(() => switchToNoBasemap("底圖來源不在允許清單"));
      return { url: BLOCKED_RESOURCE_URL };
    };

    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: startsOffline ? createNoBasemapStyle(modeRef.current) : createBasemapStyle(modeRef.current),
        center: [initialViewState.longitude, initialViewState.latitude],
        zoom: initialViewState.zoom,
        bearing: initialViewState.bearing ?? 0,
        pitch: initialViewState.pitch ?? 0,
        attributionControl: false,
        transformRequest,
      });
      map.addControl(
        new maplibregl.NavigationControl({ visualizePitch: true }),
        "top-right",
      );
      map.addControl(new Reset2DControl(), "top-right");
      mapRef.current = map;
    } catch {
      map?.remove();
      setFallbackReason("WebGL 地圖初始化失敗");
      setBasemapStatus("map-unavailable");
      return undefined;
    }

    const ensureOverlay = () => {
      if (overlay) return true;
      try {
        overlay = new MapboxOverlay({
          interleaved: false,
          ...overlayPropsRef.current,
        });
        map.addControl(overlay);
        overlayRef.current = overlay;
        return true;
      } catch {
        fallbackAppliedRef.current = true;
        clearRuntimeTimers();
        overlayRef.current = null;
        setFallbackReason("Deck.gl 圖層初始化失敗");
        setBasemapStatus("map-unavailable");
        return false;
      }
    };

    const handleStyleLoad = () => {
      applyMapAppearance(map, modeRef.current, fallbackAppliedRef.current);
      styleReady = true;
      clearStyleLoadTimer();
      if (fallbackAppliedRef.current) {
        ensureOverlay();
        return;
      }
      clearResourceLoadTimer();
      resourceLoadTimer = window.setTimeout(
        () => switchToNoBasemap("底圖資源載入逾時"),
        mapConfig.resourceLoadTimeoutMs,
      );
    };
    const handleMapLoad = () => {
      clearStyleLoadTimer();
      clearResourceLoadTimer();
      resetResourceErrors();
      if (!ensureOverlay() || fallbackAppliedRef.current) return;
      setFallbackReason(null);
      setBasemapStatus("ready");
      const pending = focusTargetRef.current;
      if (pending && Number.isFinite(pending.longitude) && Number.isFinite(pending.latitude)) {
        map.jumpTo({
          center: [pending.longitude, pending.latitude],
          zoom: Number.isFinite(pending.zoom) ? pending.zoom : map.getZoom(),
        });
      }
      handleCameraIdle();
    };
    const handleMapError = () => {
      if (fallbackAppliedRef.current) return;
      if (!styleReady) {
        switchToNoBasemap("OpenFreeMap style 載入失敗");
        return;
      }

      const now = Date.now();
      resourceErrorTimestamps = resourceErrorTimestamps.filter(
        (timestamp) => now - timestamp <= mapConfig.resourceErrorWindowMs,
      );
      resourceErrorTimestamps.push(now);
      if (
        resourceErrorTimestamps.length >= mapConfig.resourceErrorThreshold
      ) {
        switchToNoBasemap("底圖資源連續載入失敗");
      }
    };
    const handleOffline = () => switchToNoBasemap("瀏覽器目前離線");
    const cameraPayload = () => {
      const center = map.getCenter();
      return { lat: center.lat, lng: center.lng, zoom: map.getZoom() };
    };
    const handleCameraMove = () => onCameraMoveRef.current?.(cameraPayload());
    const handleCameraIdle = () => onCameraIdleRef.current?.(cameraPayload());

    map.on("style.load", handleStyleLoad);
    map.on("load", handleMapLoad);
    map.on("error", handleMapError);
    map.on("move", handleCameraMove);
    map.on("moveend", handleCameraIdle);
    window.addEventListener("offline", handleOffline);
    const resizeObserver = new ResizeObserver(() => {
      if (!disposed) map.resize();
    });
    resizeObserver.observe(containerRef.current);

    if (!startsOffline) {
      styleLoadTimer = window.setTimeout(
        () => switchToNoBasemap("OpenFreeMap style 載入逾時"),
        mapConfig.styleLoadTimeoutMs,
      );
    }

    return () => {
      disposed = true;
      clearRuntimeTimers();
      window.removeEventListener("offline", handleOffline);
      map.off("style.load", handleStyleLoad);
      map.off("load", handleMapLoad);
      map.off("error", handleMapError);
      map.off("move", handleCameraMove);
      map.off("moveend", handleCameraIdle);
      resizeObserver.disconnect();
      overlay?.setProps({ layers: [] });
      overlayRef.current = null;
      mapRef.current = null;
      map.remove();
    };
  }, [
    initialViewState.bearing,
    initialViewState.latitude,
    initialViewState.longitude,
    initialViewState.pitch,
    initialViewState.zoom,
  ]);

  useEffect(() => {
    overlayRef.current?.setProps({ layers, getTooltip: themedTooltip });
  }, [themedTooltip, layers]);

  useEffect(() => {
    if (mapRef.current) applyMapAppearance(mapRef.current, mode, fallbackAppliedRef.current);
  }, [mode]);

  // 外部（例如缺口排行榜）觸發平滑飛越到指定站點。
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusTarget) return;
    const { longitude, latitude, zoom } = focusTarget;
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;
    map.flyTo({
      center: [longitude, latitude],
      zoom: Number.isFinite(zoom) ? zoom : map.getZoom(),
      duration: 800,
      essential: true,
    });
  }, [focusTarget?.id, focusTarget?.longitude, focusTarget?.latitude, focusTarget?.zoom]);

  return (
    <div className={`shared-map ${className}`} role="region" aria-label={ariaLabel}>
      <div ref={containerRef} className="shared-map-canvas" />
      {overlay}
      <BasemapStatus status={basemapStatus} reason={fallbackReason} />
    </div>
  );
}
