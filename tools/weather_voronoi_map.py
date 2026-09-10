"""
天氣測站 Voronoi 勢力範圍視覺化（一次性佐證工具，非產品程式）
==============================================================
抓即時三源 → 算雨量站(100)/氣象站(25)的 Voronoi 勢力範圍 → 產互動 HTML 地圖：
  - 每個 YouBike 站落在哪個測站的 Voronoi 區域，就用那個測站的天氣數值
  - 地圖疊：雨量站 Voronoi 層 / 氣象站 Voronoi 層 / YouBike 站點 / 測站點
  - 點 YouBike 站 → 顯示它對應的雨量站與氣象站 + 當下數值

用法：.venv/bin/python tools/weather_voronoi_map.py
輸出：tools/weather_voronoi_map.html（直接用瀏覽器開）

資料源（各打一次即時快照）：
  YouBike：新北開放資料 010e5b15
  雨量站：CWA O-A0002-001（新北約100站，Past10Min/Now 雨量）
  氣象站：CWA O-A0003-001（新北約25站，氣溫/濕度/天氣現象）
※ 政府平台 SSL 憑證問題 → verify=False（比照 youbike_official）。key 從 .env 讀，不寫進輸出。
"""
from __future__ import annotations
import sys, os, json, csv, io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import httpx
import numpy as np
from scipy.spatial import Voronoi

KEY = os.environ.get("CWA_WEATHER_API_KEY", "")

# 新北市大致經緯度包絡框（裁 Voronoi 用，避免無限延伸）
BBOX = {"lat_min": 24.6, "lat_max": 25.35, "lng_min": 121.2, "lng_max": 122.05}


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


# ── 1. 抓 YouBike 站 ──
def fetch_youbike() -> list[dict]:
    url = ("https://data.ntpc.gov.tw/api/datasets/"
           "010e5b15-3823-4b20-b401-b1cf000550c5/csv/file")
    r = httpx.get(url, timeout=60, follow_redirects=True, verify=False)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("\ufeff"))))
    out = []
    for row in rows:
        lat, lng = _f(row.get("lat")), _f(row.get("lng"))
        if lat is None or lng is None:
            continue
        out.append({
            "id": (row.get("sno") or "").strip(),
            "name": (row.get("sna") or "").replace("YouBike2.0_", "").strip(),
            "district": (row.get("sarea") or "").strip(),
            "lat": lat, "lng": lng,
            "bikes": _f(row.get("sbi_quantity"), 0),
            "total": _f(row.get("tot_quantity"), 0),
        })
    return out


# ── 2. 抓 CWA 測站 ──
def _wgs84(geo: dict):
    for c in geo.get("Coordinates", []):
        if c.get("CoordinateName") == "WGS84":
            return _f(c.get("StationLatitude")), _f(c.get("StationLongitude"))
    cs = geo.get("Coordinates", [])
    if cs:
        return _f(cs[0].get("StationLatitude")), _f(cs[0].get("StationLongitude"))
    return None, None


def fetch_cwa(code: str, extract) -> list[dict]:
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/{code}"
    r = httpx.get(url, params={"Authorization": KEY, "format": "JSON"},
                  timeout=30, verify=False)
    r.raise_for_status()
    stations = r.json().get("records", {}).get("Station", [])
    out = []
    for s in stations:
        geo = s.get("GeoInfo", {})
        if "新北" not in geo.get("CountyName", ""):
            continue
        lat, lng = _wgs84(geo)
        if lat is None or lng is None:
            continue
        rec = {"name": s.get("StationName", "?"), "town": geo.get("TownName", ""),
               "lat": lat, "lng": lng}
        rec.update(extract(s.get("WeatherElement", {}), s.get("RainfallElement", {})))
        out.append(rec)
    return out


def rain_extract(we, re):
    return {
        "now": _f(re.get("Now", {}).get("Precipitation"), 0),
        "past10": _f(re.get("Past10Min", {}).get("Precipitation"), 0),
        "past1hr": _f(re.get("Past1hr", {}).get("Precipitation"), 0),
    }


def weather_extract(we, re):
    return {
        "weather": we.get("Weather", "-"),
        "temp": _f(we.get("AirTemperature"), None),
        "humidity": _f(we.get("RelativeHumidity"), None),
        "now_rain": _f(we.get("Now", {}).get("Precipitation"), 0),
    }


# ── 3. Voronoi（裁到 bbox）──
def voronoi_polygons(points: list[dict]):
    """回每個點的 Voronoi 多邊形（裁到 BBOX）。用鏡像點法讓邊界多邊形封閉。"""
    pts = np.array([[p["lng"], p["lat"]] for p in points])
    # 鏡像四邊，讓所有真實點的 cell 都有界
    lo = np.array([BBOX["lng_min"], BBOX["lat_min"]])
    hi = np.array([BBOX["lng_max"], BBOX["lat_max"]])
    mirrors = []
    for x, y in pts:
        mirrors += [[2 * lo[0] - x, y], [2 * hi[0] - x, y],
                    [x, 2 * lo[1] - y], [x, 2 * hi[1] - y]]
    allpts = np.vstack([pts, mirrors])
    vor = Voronoi(allpts)
    polys = []
    for i in range(len(pts)):
        region = vor.regions[vor.point_region[i]]
        if not region or -1 in region:
            polys.append(None)
            continue
        poly = [[vor.vertices[v][0], vor.vertices[v][1]] for v in region]
        # 裁到 bbox（簡單夾）
        poly = [[min(max(x, lo[0]), hi[0]), min(max(y, lo[1]), hi[1])] for x, y in poly]
        polys.append(poly)   # [lng,lat] 順序
    return polys


def nearest_idx(lat, lng, stations):
    arr = np.array([[s["lat"], s["lng"]] for s in stations])
    d = (arr[:, 0] - lat) ** 2 + (arr[:, 1] - lng) ** 2
    return int(np.argmin(d))


def main():
    if not KEY:
        print("✗ 讀不到 CWA_WEATHER_API_KEY（.env）"); sys.exit(1)
    print("抓 YouBike 即時…", flush=True)
    yb = fetch_youbike()
    print(f"  {len(yb)} 站", flush=True)
    print("抓雨量站 O-A0002-001…", flush=True)
    rain = fetch_cwa("O-A0002-001", rain_extract)
    print(f"  新北 {len(rain)} 站", flush=True)
    print("抓氣象站 O-A0003-001…", flush=True)
    wx = fetch_cwa("O-A0003-001", weather_extract)
    print(f"  新北 {len(wx)} 站", flush=True)

    print("算 Voronoi…", flush=True)
    rain_poly = voronoi_polygons(rain)
    wx_poly = voronoi_polygons(wx)

    # 每個 YouBike 站對應最近雨量站/氣象站
    for p in yb:
        ri = nearest_idx(p["lat"], p["lng"], rain)
        wi = nearest_idx(p["lat"], p["lng"], wx)
        p["rain_station"] = rain[ri]["name"]
        p["rain_past10"] = rain[ri]["past10"]
        p["rain_now"] = rain[ri]["now"]
        p["wx_station"] = wx[wi]["name"]
        p["temp"] = wx[wi]["temp"]
        p["humidity"] = wx[wi]["humidity"]
        p["weather"] = wx[wi]["weather"]

    out = ROOT / "tools" / "weather_voronoi_map.html"
    html = render_html(yb, rain, rain_poly, wx, wx_poly)
    out.write_text(html, encoding="utf-8")
    print(f"\n✓ 輸出 {out}")
    print(f"  YouBike {len(yb)} 站 / 雨量站 {len(rain)} / 氣象站 {len(wx)}")


def render_html(yb, rain, rain_poly, wx, wx_poly):
    data = {
        "youbike": yb,
        "rain": [{"name": s["name"], "town": s["town"], "lat": s["lat"], "lng": s["lng"],
                  "past10": s["past10"], "now": s["now"], "poly": rain_poly[i]}
                 for i, s in enumerate(rain)],
        "wx": [{"name": s["name"], "town": s["town"], "lat": s["lat"], "lng": s["lng"],
                "temp": s["temp"], "humidity": s["humidity"], "weather": s["weather"],
                "poly": wx_poly[i]} for i, s in enumerate(wx)],
    }
    payload = json.dumps(data, ensure_ascii=False)
    return _HTML_TEMPLATE.replace("__DATA__", payload)


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>新北 YouBike × 天氣測站 Voronoi 勢力範圍</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body{margin:0;height:100%;font-family:system-ui,"PingFang TC",sans-serif}
  #map{height:100%}
  .panel{position:absolute;top:10px;right:10px;z-index:1000;background:#fff;
    padding:12px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);font-size:13px;color:#222;max-width:260px}
  .panel h3{margin:0 0 8px;font-size:14px;color:#0d47a1}
  .panel label{display:block;margin:4px 0;cursor:pointer}
  .legend{margin-top:8px;font-size:12px;color:#555;line-height:1.6}
  .sw{display:inline-block;width:12px;height:12px;margin-right:5px;vertical-align:middle;border:1px solid #888}
</style></head><body>
<div id="map"></div>
<div class="panel">
  <h3>天氣測站勢力範圍（Voronoi）</h3>
  <label><input type="checkbox" id="ckRainPoly" checked> 雨量站範圍（100 站）</label>
  <label><input type="checkbox" id="ckWxPoly"> 氣象站範圍（25 站）</label>
  <label><input type="checkbox" id="ckRainPt" checked> 雨量站點</label>
  <label><input type="checkbox" id="ckWxPt"> 氣象站點</label>
  <label><input type="checkbox" id="ckYouBike" checked> YouBike 站（點看天氣來源）</label>
  <div class="legend">
    <div><span class="sw" style="background:#4fc3f7;opacity:.25"></span>雨量站區域</div>
    <div><span class="sw" style="background:#ffb74d;opacity:.25"></span>氣象站區域</div>
    <div><span class="sw" style="background:#1565c0"></span>YouBike 站</div>
  </div>
  <div class="legend" id="stat"></div>
</div>
<script>
const DATA = __DATA__;
const map = L.map('map').setView([25.01, 121.55], 11);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
  {attribution:'© OpenStreetMap © CARTO', maxZoom:19}).addTo(map);

function polyLayer(arr, color){
  const g = L.layerGroup();
  arr.forEach(s=>{
    if(!s.poly) return;
    const latlngs = s.poly.map(c=>[c[1],c[0]]);
    L.polygon(latlngs,{color:color,weight:1,fillColor:color,fillOpacity:.18})
      .bindTooltip(s.name+(s.town?(' / '+s.town):''),{sticky:true}).addTo(g);
  });
  return g;
}
function ptLayer(arr, color, fmt){
  const g = L.layerGroup();
  arr.forEach(s=>{
    L.circleMarker([s.lat,s.lng],{radius:4,color:color,fillColor:color,fillOpacity:.9,weight:1})
      .bindPopup('<b>'+s.name+'</b><br>'+fmt(s)).addTo(g);
  });
  return g;
}

const rainPoly = polyLayer(DATA.rain,'#0288d1').addTo(map);
const wxPoly   = polyLayer(DATA.wx,'#f57c00');
const rainPt   = ptLayer(DATA.rain,'#0277bd', s=>('過去10分 '+s.past10+' mm｜當下 '+s.now+' mm')).addTo(map);
const wxPt     = ptLayer(DATA.wx,'#e65100', s=>(s.weather+'｜'+(s.temp??'-')+'°C｜濕度 '+(s.humidity??'-')+'%'));

const ybGroup = L.layerGroup();
DATA.youbike.forEach(p=>{
  // 依可借量上色（空=紅/少=橘/正常=綠），加白邊+較大半徑，方便點選
  const ratio = p.total>0 ? p.bikes/p.total : 0;
  const fill = p.bikes<=0 ? '#d32f2f' : (ratio<0.2 ? '#f57c00' : (ratio>0.85 ? '#7b1fa2' : '#1565c0'));
  L.circleMarker([p.lat,p.lng],{radius:5,color:'#fff',weight:1.2,
      fillColor:fill,fillOpacity:.95,pane:'markerPane'})
   .bindPopup('<b>'+p.name+'</b>（'+p.district+'）<br>'+
     '<b>目前可借 '+p.bikes+' / 總柱 '+p.total+'</b>'+
     '<hr style="margin:4px 0">'+
     '<b>天氣來源（最近測站）</b><br>'+
     '雨量站：'+p.rain_station+'<br>&nbsp;&nbsp;過去10分 '+p.rain_past10+' mm｜當下 '+p.rain_now+' mm<br>'+
     '氣象站：'+p.wx_station+'<br>&nbsp;&nbsp;'+p.weather+'｜'+(p.temp??'-')+'°C｜濕度 '+(p.humidity??'-')+'%')
   .addTo(ybGroup);
});
ybGroup.addTo(map);
// YouBike 點提到最上層，避免被 Voronoi 多邊形蓋住點不到
map.on('overlayadd baselayerchange', ()=>ybGroup.eachLayer(l=>l.bringToFront&&l.bringToFront()));

function raiseYb(){ybGroup.eachLayer(l=>l.bringToFront&&l.bringToFront());}
function bind(id,layer){document.getElementById(id).onchange=e=>{
  if(e.target.checked) map.addLayer(layer); else map.removeLayer(layer);
  raiseYb();};}
bind('ckRainPoly',rainPoly); bind('ckWxPoly',wxPoly);
bind('ckRainPt',rainPt); bind('ckWxPt',wxPt); bind('ckYouBike',ybGroup);
raiseYb();  // 初始就把 YouBike 點提到最上層

document.getElementById('stat').innerHTML =
  'YouBike '+DATA.youbike.length+' 站<br>雨量站 '+DATA.rain.length+'｜氣象站 '+DATA.wx.length;
</script></body></html>"""


if __name__ == "__main__":
    main()
