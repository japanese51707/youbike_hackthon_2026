import { CompassOutlined, DesktopOutlined, MobileOutlined, WarningOutlined } from "@ant-design/icons";
import { ScatterplotLayer } from "@deck.gl/layers";
import { Alert, Button, Empty, Segmented, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import RiderFaultModal from "../components/rider/RiderFaultModal.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import { fetchFaultSummaries } from "../api/riderFaultApi.js";
import { formatFaultSummary } from "../utils/riderFaultReports.js";
import { createStationGaugeLayer } from "../components/map/layers/stationGaugeLayer.js";
import presentationConfig from "../config/presentation.json";
import useDashboardData from "../hooks/useDashboardData.js";
import useGeolocation from "../hooks/useGeolocation.js";
import { stationStatusLabels } from "../utils/formatters.js";
import { getStationColor } from "../utils/mapPresentation.js";
import {
  deriveServiceGrade,
  isInRiderServiceArea,
  recommendNearbyStations,
  SERVICE_GRADES,
  walkDirectionsUrl,
} from "../utils/riderStations.js";

const FALLBACK_ORIGIN = { lat: 25.01427, lng: 121.46256 };
const PHONE_UI_KEY = "rider-phone-ui";
const INTENT_OPTIONS = [
  { value: "rent", label: "我要借車" },
  { value: "return", label: "我要還車" },
];

export default function RiderPage() {
  const dashboard = useDashboardData({ lite: true });
  const geo = useGeolocation();
  const [intent, setIntent] = useState("rent");
  const [searchOrigin, setSearchOrigin] = useState(FALLBACK_ORIGIN);
  const [moving, setMoving] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [focusTarget, setFocusTarget] = useState(null);
  const [locateNote, setLocateNote] = useState(null);
  const [faultOpen, setFaultOpen] = useState(false);
  const [faultSummaries, setFaultSummaries] = useState({});
  const [phoneUi, setPhoneUi] = useState(() => {
    try {
      return sessionStorage.getItem(PHONE_UI_KEY) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(PHONE_UI_KEY, phoneUi ? "1" : "0");
    } catch {
      /* ignore quota / private mode */
    }
    document.body.classList.toggle("rider-phone-preview", phoneUi);
    return () => document.body.classList.remove("rider-phone-preview");
  }, [phoneUi]);

  useEffect(() => {
    if (geo.locating) setLocateNote(null);
  }, [geo.locating]);

  const reloadFaults = useCallback(() => {
    fetchFaultSummaries().then(setFaultSummaries).catch(() => {});
  }, []);

  useEffect(() => {
    reloadFaults();
    const timer = window.setInterval(reloadFaults, 15000);
    return () => window.clearInterval(timer);
  }, [reloadFaults]);

  const stations = dashboard.data?.stations ?? [];
  const advice = useMemo(
    () => recommendNearbyStations({ stations, origin: searchOrigin, intent }),
    [stations, searchOrigin, intent],
  );
  const selected =
    stations.find((row) => row.station_id === selectedId) ??
    advice.items.find((row) => row.station_id === selectedId) ??
    null;
  const faultStations = useMemo(() => {
    const seen = new Set();
    const rows = [];
    for (const row of [selected, ...advice.items, ...advice.unavailable]) {
      if (!row?.station_id || seen.has(row.station_id)) continue;
      seen.add(row.station_id);
      rows.push(row);
    }
    return rows;
  }, [selected, advice.items, advice.unavailable]);

  useEffect(() => {
    if (!geo.coords) return;
    const origin = { lat: geo.coords.lat, lng: geo.coords.lng };
    if (!isInRiderServiceArea(origin, stations)) {
      setLocateNote("定位落到新北／臺北服務範圍外（桌機常被 IP 判到外縣市），已留在地圖上，請改拖中心搜尋。");
      return;
    }
    setLocateNote(null);
    setSearchOrigin(origin);
    setFocusTarget({
      id: `gps-${geo.coords.at ?? Date.now()}`,
      longitude: origin.lng,
      latitude: origin.lat,
      zoom: 16,
    });
  }, [geo.coords, stations]);

  const onCameraMove = useCallback(() => setMoving(true), []);
  const onCameraIdle = useCallback(({ lat, lng }) => {
    setMoving(false);
    setSearchOrigin((prev) => {
      if (Math.abs(prev.lat - lat) < 1e-5 && Math.abs(prev.lng - lng) < 1e-5) return prev;
      return { lat, lng };
    });
  }, []);

  const layers = useMemo(() => {
    const recommended = new Set(advice.items.map((row) => row.station_id));
    return [
      new ScatterplotLayer({
        id: "rider-grade-halo",
        data: stations,
        pickable: false,
        stroked: true,
        getPosition: (station) => [Number(station.lng), Number(station.lat)],
        getFillColor: (station) => deriveServiceGrade(station).halo,
        getLineColor: (station) => {
          const grade = deriveServiceGrade(station);
          return grade.key === "neighbor" ? [160, 160, 160, 90] : grade.halo;
        },
        getRadius: (station) => deriveServiceGrade(station).haloRadius,
        radiusUnits: "pixels",
        lineWidthMinPixels: 2,
      }),
      createStationGaugeLayer({
        id: "rider-stations",
        data: stations,
        dimension: "status",
        getColor: (station) => getStationColor(station, "status"),
        onSelectStation: setSelectedId,
        sizePixels: (station) => {
          const grade = deriveServiceGrade(station);
          if (recommended.has(station.station_id)) return grade.key === "neighbor" ? 42 : 50;
          return grade.key === "core" ? 36 : grade.key === "priority" ? 32 : 26;
        },
      }),
    ];
  }, [stations, advice.items]);

  const getTooltip = ({ object }) => {
    if (!object?.station_name) return null;
    const grade = deriveServiceGrade(object);
    return {
      text: `${object.station_name}\n${grade.label}（依站名推估，可能有誤差）｜${grade.hint}\n${stationStatusLabels[object.status] ?? object.status}｜可借 ${object.available_bikes}／可還 ${object.available_docks}`,
    };
  };

  const toolbar = (
    <div className="rider-toolbar">
      <div>
        <Typography.Title level={phoneUi ? 4 : 3}>附近找車</Typography.Title>
        {phoneUi ? null : (
          <Typography.Text type="secondary">
            把地圖中心對準要找的地方，停下來才會更新附近推薦。排序以步行距離為主，庫存與站點等級只做小幅參考。等級依站名與規模推估，與實際調度會有誤差。
          </Typography.Text>
        )}
      </div>
      <div className="rider-toolbar-actions">
        <Segmented size={phoneUi ? "small" : "middle"} value={intent} options={INTENT_OPTIONS} onChange={setIntent} />
        <Button size={phoneUi ? "small" : "middle"} icon={<CompassOutlined />} loading={geo.locating} onClick={geo.locate}>
          {phoneUi ? "定位" : "回到我的位置"}
        </Button>
        <Button size={phoneUi ? "small" : "middle"} icon={<WarningOutlined />} onClick={() => setFaultOpen(true)}>
          通報故障
        </Button>
        {phoneUi ? null : (
          <Button icon={<MobileOutlined />} onClick={() => setPhoneUi(true)}>
            手機 UI
          </Button>
        )}
      </div>
    </div>
  );

  const main = (
    <div className="rider-main">
      <div className="rider-map">
        <SharedMap
          ariaLabel="附近 YouBike 站點地圖"
          className="map-fill"
          initialViewState={{
            ...presentationConfig.maps.dashboard,
            longitude: FALLBACK_ORIGIN.lng,
            latitude: FALLBACK_ORIGIN.lat,
            zoom: 14,
          }}
          focusTarget={focusTarget}
          layers={layers}
          getTooltip={getTooltip}
          onCameraMove={onCameraMove}
          onCameraIdle={onCameraIdle}
          overlay={
            <>
              <div className="rider-legend">
                <div className="rider-legend-title">站點等級</div>
                {Object.values(SERVICE_GRADES).map((grade) => (
                  <div key={grade.key} className="rider-legend-item">
                    <span
                      className={`rider-legend-dot rider-legend-${grade.key}`}
                      style={{ background: `rgba(${grade.halo.join(",")})` }}
                    />
                    <span>
                      {grade.label}
                      <small>{grade.hint}</small>
                    </span>
                  </div>
                ))}
                {phoneUi ? null : (
                  <div className="rider-legend-note">目前依站名與規模推估，與實際調度會有誤差。圖釘顏色仍是可借／可還狀態。</div>
                )}
              </div>
              <div className={`rider-aim${moving ? " is-moving" : ""}`} aria-hidden="true">
                <span className="rider-aim-range" />
                <span className="rider-aim-pin" />
                <span className="rider-aim-label">{moving ? "移動中，停下來再搜尋" : "以地圖中心搜尋"}</span>
              </div>
            </>
          }
        />
      </div>

      <aside className="rider-list" aria-label="推薦站點">
        {dashboard.loading && !stations.length ? (
          <Empty description="站況載入中" />
        ) : advice.items.length === 0 ? (
          <Empty description={intent === "return" ? "附近暫時沒有可還車位" : "附近暫時沒有可借車輛"} />
        ) : (
          advice.items.map((row, index) => {
            const href = walkDirectionsUrl(searchOrigin, row);
            const active = selected?.station_id === row.station_id;
            return (
              <button
                key={row.station_id}
                type="button"
                className={`rider-card${active ? " is-active" : ""}`}
                onClick={() => setSelectedId(row.station_id)}
              >
                <div className="rider-card-head">
                  <span className="rider-rank">{index + 1}</span>
                  <strong>{row.station_name}</strong>
                  <Tag color={row.grade.color}>{row.grade.label}</Tag>
                </div>
                <div className="rider-card-meta">
                  {row.reasons.map((reason) => (
                    <span key={reason}>{reason}</span>
                  ))}
                  {formatFaultSummary(faultSummaries[row.station_id]) ? (
                    <span className="rider-card-fault">{formatFaultSummary(faultSummaries[row.station_id])}</span>
                  ) : null}
                </div>
                {href ? (
                  <div className="rider-card-actions">
                    <Button size="small" type="primary" href={href} target="_blank" rel="noreferrer">
                      步行導航
                    </Button>
                  </div>
                ) : null}
              </button>
            );
          })
        )}

        {advice.unavailable.length ? (
          <div className="rider-unavailable">
            <Typography.Text type="secondary">附近目前不可用</Typography.Text>
            {advice.unavailable.map((row) => (
              <div key={row.station_id}>
                {row.station_name} · {row.grade.label} · 步行約 {row.walkMin} 分
              </div>
            ))}
          </div>
        ) : null}
      </aside>
    </div>
  );

  return (
    <div className={`fixed-page rider-page${phoneUi ? " is-phone" : ""}`}>
      {phoneUi ? (
        <Button className="rider-phone-exit" icon={<DesktopOutlined />} onClick={() => setPhoneUi(false)}>
          桌面 UI
        </Button>
      ) : null}
      <div className={phoneUi ? "rider-phone-stage" : "rider-shell"}>
        <div className={phoneUi ? "rider-phone" : "rider-shell-inner"}>
          {phoneUi ? <div className="rider-phone-notch" aria-hidden="true" /> : null}
          {toolbar}
          {geo.error || locateNote ? (
            <Alert type="info" showIcon className="rider-banner" title={geo.error || locateNote} />
          ) : null}
          {main}
          {phoneUi ? <div className="rider-phone-home" aria-hidden="true" /> : null}
        </div>
      </div>
      <RiderFaultModal
        open={faultOpen}
        stations={faultStations}
        defaultStationId={selected?.station_id || advice.items[0]?.station_id}
        summaries={faultSummaries}
        onClose={() => setFaultOpen(false)}
        onSubmitted={reloadFaults}
      />
    </div>
  );
}
