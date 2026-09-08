import { AimOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Tag, Typography } from "antd";
import { useMemo } from "react";

// 缺口／溢出排行榜（戰情面板）：依「目前站況」列出高風險站點，點擊定位地圖。
// 全部使用既有站點欄位（status/available_bikes/available_docks/total_docks），
// 標示為「目前狀態」而非預測，避免宣稱模型輸出。

const TOP_N = 5;
const DEFICIT_STATUS = new Set(["empty", "low"]);
const SURPLUS_STATUS = new Set(["full", "high"]);

function rankDeficit(stations) {
  return stations
    .filter((s) => DEFICIT_STATUS.has(s.status))
    .sort((a, b) => Number(a.available_bikes) - Number(b.available_bikes))
    .slice(0, TOP_N);
}

function rankSurplus(stations) {
  return stations
    .filter((s) => SURPLUS_STATUS.has(s.status))
    .sort((a, b) => Number(a.available_docks) - Number(b.available_docks))
    .slice(0, TOP_N);
}

function RankRow({ station, metricLabel, metricValue, tone, onFocus }) {
  return (
    <div className="rank-row">
      <div className="rank-row-main">
        <span className="rank-dot" style={{ background: tone }} />
        <div>
          <Typography.Text className="rank-name">{station.station_name}</Typography.Text>
          <div className="rank-sub mono">
            {station.district}｜{metricLabel} {metricValue}
          </div>
        </div>
      </div>
      <Button
        size="small"
        type="text"
        icon={<AimOutlined />}
        onClick={() => onFocus(station)}
      >
        定位
      </Button>
    </div>
  );
}

export default function DeficitRankingPanel({ stations, onFocus, embedded = false }) {
  const deficit = useMemo(() => rankDeficit(stations), [stations]);
  const surplus = useMemo(() => rankSurplus(stations), [stations]);

  const body = (
    <div className="ranking-columns">
        <div>
          <div className="ranking-heading">
            <Tag color="red">缺車待補</Tag>
          </div>
          {deficit.length ? (
            deficit.map((station) => (
              <RankRow
                key={station.station_id}
                station={station}
                metricLabel="可借"
                metricValue={`${station.available_bikes} 台`}
                tone={station.status === "empty" ? "#ff6b6b" : "#ffa94d"}
                onFocus={onFocus}
              />
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="無缺車站點" />
          )}
        </div>
        <div>
          <div className="ranking-heading">
            <Tag color="purple">滿站待取</Tag>
          </div>
          {surplus.length ? (
            surplus.map((station) => (
              <RankRow
                key={station.station_id}
                station={station}
                metricLabel="可還"
                metricValue={`${station.available_docks} 位`}
                tone={station.status === "full" ? "#9775fa" : "#4dabf7"}
                onFocus={onFocus}
              />
            ))
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="無滿站站點" />
          )}
        </div>
      </div>
  );

  if (embedded) return body;
  return (
    <Card className="ranking-panel" title="缺口 / 溢出排行榜" extra={<Tag>目前狀態</Tag>}>
      {body}
    </Card>
  );
}
