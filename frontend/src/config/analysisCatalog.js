// 戰情室分析型錄：每個分析的顯示名稱、一句話用途、白話說明（給 info/問號用）、學科、資料誠實度標註。
// 目的：讓不熟空間分析的人也看得懂「這在分析什麼」。
//
// dataMode：
//   real     = 由既有站點資料誠實現算
//   method   = 統計方法展示（目前 mock 站數少，僅示意，非可靠推論）
//   pending  = 待接真實資料源（未提供者不假造）

export const ANALYSIS_CATALOG = [
  {
    key: "gauge",
    name: "站點標記",
    discipline: "即時狀態",
    dataMode: "real",
    purpose: "各站可借比例與狀態",
    info: "YouBike 風格水滴標記：綠色正常租借、橘色無車可借、紅色車位滿載、灰色暫停營運。弧線數量代表可借比例；電輔車有確定資料時才加閃電。調度緊急度另行呈現。",
  },
  {
    key: "kde",
    name: "壓力熱力圖（KDE）",
    discipline: "空間統計",
    dataMode: "real",
    purpose: "需求/壓力集中在哪",
    info: "核密度估計（Kernel Density Estimation）：把各站的壓力（缺口/使用率）擴散成連續的熱區，顏色越亮代表該區域壓力越集中。用來找出需要關注的熱區，而不只是單點。",
  },
  {
    key: "voronoi",
    name: "勢力範圍（Voronoi）＋熱點顯著性",
    discipline: "空間統計",
    dataMode: "method",
    purpose: "每站服務領域＋壓力群聚強度",
    info: "Voronoi（泰森多邊形）把地圖切成每個站點負責的「勢力範圍」。顏色依 Getis-Ord Gi* 的 z 值連續漸層：越紅表示鄰近壓力越高、越藍越低、灰代表接近全市平均。右側解讀仍用 |z|≥1.96／2.58 算顯著熱冷點。站數達 50 以上改標實算；少於 50 仍只是方法展示。",
  },
  {
    key: "density",
    name: "容量密度（Hexagon）",
    discipline: "GIS",
    dataMode: "real",
    purpose: "站點容量的空間密度基底",
    info: "把區域切成六邊形網格，依落在格內站點的容量（柱位數）堆疊高度與顏色，當作背景對比，看哪裡站點/容量密集。",
  },
  {
    key: "coverage",
    name: "覆蓋缺口",
    discipline: "運輸規劃",
    dataMode: "real",
    purpose: "哪裡離站太遠、待布點",
    info: "在地圖鋪格點，計算每個格點到最近站點的距離；距離越大代表該處越可能是服務死角。用來評估未來該在哪裡增設站點。",
  },
  {
    key: "network",
    name: "鄰近網路＋中心性",
    discipline: "網路科學",
    dataMode: "method",
    purpose: "找出樞紐站",
    info: "用站點的地理鄰近關係建成一張網路（連到最近的幾個站），計算每個站的中心性（連結強度）；中心性越高代表越像樞紐、影響範圍越大。（無真實 OD 流量，以鄰近關係示意）",
  },
  {
    key: "catchment",
    name: "服務集水區",
    discipline: "運輸規劃",
    dataMode: "real",
    purpose: "可服務範圍覆蓋",
    info: "以每站為圓心畫出服務半徑（集水區），看整體覆蓋與重疊。半徑可調。真正的等時圈（isochrone）需要路網資料，此處以直線半徑近似。",
  },
  {
    key: "flow",
    name: "調度/流向弧線",
    discipline: "網路科學",
    dataMode: "method",
    purpose: "站間流動/調度航段",
    info: "沒有真實 trip OD。現在用調度建議做「同區最近、一對一」的取→補示意配對，可讀距離與同區占比，但不能當成真實車流或派車路線。",
  },
];

// 待接真實資料源才能做的進階分析（誠實列出、不假造）
export const PENDING_ANALYSES = [
  "真實 OD 流向（需 trip 起訖資料）",
  "公平性指數 BEI（需人口/社經資料）",
  "交通壓力 LTS / 自行車道鄰近（需自行車道資料）",
  "潛在需求估計（需人口/運量代理）",
];
