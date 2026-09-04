import { MapboxOverlay } from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import {
  isAllowedBasemapRequest,
  mapConfig,
} from "../../config/mapConfig.js";
import { createDarkBasemapStyle } from "../../config/darkBasemapStyle.js";
import { createNoBasemapStyle } from "../../config/noBasemapStyle.js";
import BasemapStatus from "./BasemapStatus.jsx";

const BLOCKED_RESOURCE_URL = "data:application/octet-stream;base64,";

// 自訂「2D」控制鈕：一鍵把 pitch/bearing 歸零，回到正北俯視（ADR-014 地圖互動）。
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
  getTooltip,
  initialViewState,
  layers,
  overlay = null,
}) {
  const containerRef = useRef(null);
  const overlayRef = useRef(null);
  const overlayPropsRef = useRef({ layers, getTooltip });
  const fallbackAppliedRef = useRef(false);
  const [basemapStatus, setBasemapStatus] = useState("loading");
  const [fallbackReason, setFallbackReason] = useState(null);

  overlayPropsRef.current = { layers, getTooltip };

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
        map.setStyle(createNoBasemapStyle());
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
        style: startsOffline ? createNoBasemapStyle() : createDarkBasemapStyle(),
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

    map.on("style.load", handleStyleLoad);
    map.on("load", handleMapLoad);
    map.on("error", handleMapError);
    window.addEventListener("offline", handleOffline);

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
      overlay?.setProps({ layers: [] });
      overlayRef.current = null;
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
    overlayRef.current?.setProps({ layers, getTooltip });
  }, [getTooltip, layers]);

  return (
    <div className={`shared-map ${className}`} role="region" aria-label={ariaLabel}>
      <div ref={containerRef} className="shared-map-canvas" />
      {overlay}
      <BasemapStatus status={basemapStatus} reason={fallbackReason} />
    </div>
  );
}
