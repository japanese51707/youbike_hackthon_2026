import { useMemo, useState } from "react";
import { DISTRICT_MAP_VIEW, DISTRICT_SHAPES } from "../../utils/districtPressureMap.js";
import { districtPressureLevel } from "../../utils/serviceBoard.js";

const LEVEL_LABEL = { green: "穩定", yellow: "留意", red: "加壓", none: "無站況" };

export default function DistrictPressureMap({ districts, onSelect, highlight, onHover }) {
  const [hover, setHover] = useState(null);
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

  const setActive = (name) => {
    setHover(name);
    onHover?.(name);
  };

  return (
    <div className="slb-map">
      <div className="slb-map-legend" aria-label="壓力色例">
        <span className="is-green">綠 {counts.green} 穩定</span>
        <span className="is-yellow">黃 {counts.yellow} 留意</span>
        <span className="is-red">紅 {counts.red} 加壓</span>
      </div>
      <div className="slb-map-frame">
      <svg
        className="slb-map-svg"
        viewBox={`0 0 ${DISTRICT_MAP_VIEW.w} ${DISTRICT_MAP_VIEW.h}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="新北市各區壓力"
      >
        {DISTRICT_SHAPES.map((shape) => {
          const row = byName.get(shape.district);
          const level = row ? districtPressureLevel(row.problems, row.count) : "none";
          const selectable = Boolean(row);
          return (
            <path
              key={shape.district}
              className={`slb-map-poly is-${level}${active === shape.district ? " is-hover" : ""}`}
              d={shape.d}
              tabIndex={selectable ? 0 : undefined}
              role={selectable ? "button" : undefined}
              aria-label={`${shape.district} ${LEVEL_LABEL[level]}`}
              onMouseEnter={() => setActive(shape.district)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(shape.district)}
              onBlur={() => setActive(null)}
              onClick={() => selectable && onSelect?.(row)}
              onKeyDown={(event) => {
                if (selectable && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  onSelect?.(row);
                }
              }}
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
      </div>
      <div className="slb-map-hint">
        {active
          ? `${active}｜${LEVEL_LABEL[hoverLevel]}`
            + (hoverRow ? `｜空 ${hoverRow.empty}／滿 ${hoverRow.full}｜點開看站` : "｜沒有 YouBike 站況")
          : "紅黃綠為該區空滿佔比；點選行政區看站名"}
      </div>
    </div>
  );
}
