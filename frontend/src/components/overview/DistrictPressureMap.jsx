import { ExpandOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  DISTRICT_MAP_FIT,
  DISTRICT_SHAPES,
  isFitView,
  lerpMapView,
  panMapView,
  viewForDistrict,
  zoomMapView,
} from "../../utils/districtPressureMap.js";
import { districtPressureLevel } from "../../utils/serviceBoard.js";

const LEVEL_LABEL = { green: "穩定", yellow: "留意", red: "加壓", none: "無站況" };
const WHEEL_ZOOM_IN = 0.88;
const WHEEL_ZOOM_OUT = 1.14;
const ZOOM_MS = 420;
const WHEEL_MS = 220;
const DRAG_THRESHOLD = 6;

function districtFromTarget(target) {
  let node = target;
  while (node && node !== document && node.getAttribute) {
    const name = node.getAttribute("data-district");
    if (name) return name;
    node = node.parentNode;
  }
  return null;
}

export default function DistrictPressureMap({
  districts,
  highlight,
  selected,
  onHover,
  onSelectDistrict,
  onReset,
}) {
  const [hover, setHover] = useState(null);
  const [view, setView] = useState(DISTRICT_MAP_FIT);
  const frameRef = useRef(null);
  const dragRef = useRef(null);
  const viewRef = useRef(view);
  const animRef = useRef(null);
  const holdHoverRef = useRef(null);
  viewRef.current = view;

  const active = highlight || hover;
  const byName = useMemo(() => {
    const map = new Map();
    for (const row of districts ?? []) map.set(row.district, row);
    return map;
  }, [districts]);

  const counts = useMemo(() => {
    const tally = { green: 0, yellow: 0, red: 0, none: 0 };
    for (const shape of DISTRICT_SHAPES) {
      const row = byName.get(shape.district);
      const level = row ? districtPressureLevel(row.problems, row.count) : "none";
      tally[level] += 1;
    }
    return tally;
  }, [byName]);

  const hoverRow = active ? byName.get(active) : null;
  const hoverLevel = hoverRow
    ? districtPressureLevel(hoverRow.problems, hoverRow.count)
    : active
      ? "none"
      : null;
  const fit = isFitView(view);

  const goToView = (next, duration = ZOOM_MS) => {
    const from = { ...viewRef.current };
    const to = { ...next };
    if (animRef.current) cancelAnimationFrame(animRef.current);
    if (duration <= 0 || (from.w === to.w && from.x === to.x && from.y === to.y && from.h === to.h)) {
      viewRef.current = to;
      setView(to);
      return;
    }
    const started = performance.now();
    const tick = (now) => {
      const t = (now - started) / duration;
      if (t >= 1) {
        animRef.current = null;
        viewRef.current = to;
        setView(to);
        return;
      }
      const frame = lerpMapView(from, to, t);
      viewRef.current = frame;
      setView(frame);
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
  };

  useEffect(() => () => {
    if (animRef.current) cancelAnimationFrame(animRef.current);
  }, []);

  useEffect(() => {
    goToView(selected ? viewForDistrict(selected) : { ...DISTRICT_MAP_FIT }, ZOOM_MS);
  }, [selected]);

  const setActive = (name) => {
    if (name && holdHoverRef.current === name) return;
    if (!name) holdHoverRef.current = null;
    setHover(name);
    onHover?.(name);
  };

  useEffect(() => {
    const node = frameRef.current;
    if (!node) return undefined;
    const onWheel = (event) => {
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const current = viewRef.current;
      const x = current.x + ((event.clientX - rect.left) / rect.width) * current.w;
      const y = current.y + ((event.clientY - rect.top) / rect.height) * current.h;
      goToView(zoomMapView(current, {
        x,
        y,
        factor: event.deltaY > 0 ? WHEEL_ZOOM_OUT : WHEEL_ZOOM_IN,
      }), WHEEL_MS);
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    if (event.target.closest?.(".slb-map-reset")) return;
    dragRef.current = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      dragging: false,
    };
  };

  const onPointerMove = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;
    const shifted = Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y);
    if (!drag.dragging) {
      if (shifted < DRAG_THRESHOLD) return;
      drag.dragging = true;
      if (animRef.current) {
        cancelAnimationFrame(animRef.current);
        animRef.current = null;
      }
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    const node = frameRef.current;
    const rect = node?.getBoundingClientRect();
    if (!rect?.width || !rect.height) return;
    const current = viewRef.current;
    const dx = ((drag.x - event.clientX) / rect.width) * current.w;
    const dy = ((drag.y - event.clientY) / rect.height) * current.h;
    dragRef.current = { ...drag, x: event.clientX, y: event.clientY, dragging: true };
    const next = panMapView(current, { dx, dy });
    viewRef.current = next;
    setView(next);
  };

  const finishPointer = (event) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (drag.dragging) return;
    if (event.target.closest?.(".slb-map-reset")) return;
    const name = districtFromTarget(event.target);
    if (!name) return;
    holdHoverRef.current = name;
    setHover(null);
    onHover?.(null);
    if (typeof event.target?.blur === "function") event.target.blur();
    if (selected === name) goToView(viewForDistrict(name), ZOOM_MS);
    onSelectDistrict?.(name);
  };

  const resetCity = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragRef.current = null;
    goToView({ ...DISTRICT_MAP_FIT }, ZOOM_MS);
    onReset?.();
  };

  return (
    <div className="slb-map">
      <div className="slb-map-legend" aria-label="壓力色例">
        <span className="is-green">綠 {counts.green} 穩定</span>
        <span className="is-yellow">黃 {counts.yellow} 留意</span>
        <span className="is-red">紅 {counts.red} 加壓</span>
      </div>
      <div
        ref={frameRef}
        className={`slb-map-frame${fit ? "" : " is-zoomed"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishPointer}
        onPointerCancel={finishPointer}
      >
        <svg
          className="slb-map-svg"
          viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="新北市各區壓力，滾輪縮放"
        >
          {DISTRICT_SHAPES.map((shape) => {
            const row = byName.get(shape.district);
            const level = row ? districtPressureLevel(row.problems, row.count) : "none";
            const isHover = hover === shape.district || highlight === shape.district;
            return (
              <path
                key={shape.district}
                data-district={shape.district}
                className={`slb-map-poly is-${level}${isHover ? " is-hover" : ""}`}
                d={shape.d}
                aria-label={`${shape.district} ${LEVEL_LABEL[level]}`}
                onMouseEnter={() => setActive(shape.district)}
                onMouseLeave={() => setActive(null)}
              >
                <title>
                  {row
                    ? `${shape.district}｜${LEVEL_LABEL[level]}｜空 ${row.empty}／滿 ${row.full}`
                    : `${shape.district}｜目前沒有站況`}
                </title>
              </path>
            );
          })}
        </svg>
        <Button
          size="small"
          className="slb-map-reset"
          icon={<ExpandOutlined />}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={resetCity}
        >
          全市
        </Button>
      </div>
      <div className="slb-map-hint">
        {active
          ? `${active}｜${LEVEL_LABEL[hoverLevel]}`
            + (hoverRow ? `｜空 ${hoverRow.empty}／滿 ${hoverRow.full}` : "｜沒有 YouBike 站況")
          : "任何縮放下點一區都會對到該區；滾輪縮放，全市回整張新北"}
      </div>
    </div>
  );
}
