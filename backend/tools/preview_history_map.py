"""
歷史流動地圖預覽工具（讀 S3 真實資料）
========================================
用主辦提供的 S3 真實歷史資料（每 30 分鐘一筆），把預設 10 站畫在新北市地圖上，
底部時間軸滑桿可拖曳/播放，觀察這些站點在指定日期一整天（48 個時間點）的流動。

與 preview_map.py 的差異：
  - preview_map.py：用 mock 假資料（手工成品資料）
  - 本工具：用 S3 真實歷史資料，時間軸是「真的一整天的變化」

用法：
    python backend/tools/preview_history_map.py                # 預設 2026-06-15
    python backend/tools/preview_history_map.py 2026-06-20     # 指定日期
    → 產出 output/history_preview.html，用瀏覽器開

資料來源：s3://youbike-hackathon-2026/youbike_data/year_month=YYYY-MM/data.parquet
"""

import io
import json
import sys
from pathlib import Path

try:
    import boto3
    import pyarrow.parquet as pq
    import folium
except ImportError as e:
    raise SystemExit(f"缺套件：{e}（需 boto3 / pyarrow / folium）")

ROOT = Path(__file__).parent.parent.parent
OUT = ROOT / "output" / "history_preview.html"
BUCKET = "youbike-hackathon-2026"

# 預設 10 站（對齊原 mock，換成 S3 真實存在的站名）
STATIONS = [
    "捷運南勢角站(4號出口)", "捷運景安站", "板橋車站",
    "三重國民運動中心", "新莊國民運動中心", "蘆洲國民運動中心",
    "永和國小", "捷運土城站(1號出口)", "三井Outlet", "捷運大坪林站(1號出口)",
]


def usage_to_color(usage: float) -> str:
    """借用率 0~100 → 漸層色（紅→橘→綠→藍→紫）。低=缺車(紅)，高=太滿(紫)。"""
    u = max(0, min(100, usage))
    if u < 15:
        return "#d7191c"
    elif u < 30:
        return "#fdae61"
    elif u < 70:
        return "#1a9641"
    elif u < 85:
        return "#2c7fb8"
    else:
        return "#7b3294"


def load_day(date: str) -> dict:
    """讀 S3 指定日期、10 站的當日資料，整理成 {站名: {座標, frames[48]}}。"""
    month = date[:7]  # YYYY-MM
    key = f"youbike_data/year_month={month}/data.parquet"
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    df = pq.read_table(io.BytesIO(obj["Body"].read())).to_pandas()

    df["日期"] = df["日期"].astype(str)
    day_df = df[df["日期"].str.startswith(date) & df["場站名稱"].isin(STATIONS)].copy()

    result = {}
    for name in STATIONS:
        sub = day_df[day_df["場站名稱"] == name].sort_values("日期")
        if sub.empty:
            continue
        first = sub.iloc[0]
        frames = []
        for _, r in sub.iterrows():
            t = r["日期"][11:16]  # HH:MM
            frames.append({
                "time": t,
                "available_bikes": int(r["可借車數"]),
                "available_docks": int(r["可還位數"]),
                "usage_rate": round(float(r["借用率"]), 1),
                "total": int(r["總車柱數"]),
            })
        result[name] = {
            "lat": float(first["緯度"]),
            "lng": float(first["經度"]),
            "district": first["行政區"],
            "total": int(first["總車柱數"]),
            "frames": frames,
        }
    return result


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-06-15"
    print(f"讀 S3 資料：{date}，{len(STATIONS)} 站 ...")
    data = load_day(date)
    if not data:
        raise SystemExit(f"該日期無資料：{date}")

    # 時間軸格數（用第一站的 frames 數，正常 48）
    n_frames = max(len(v["frames"]) for v in data.values())
    times = [f["time"] for f in next(iter(data.values()))["frames"]]

    center = [
        sum(v["lat"] for v in data.values()) / len(data),
        sum(v["lng"] for v in data.values()) / len(data),
    ]
    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")

    payload = json.dumps({"date": date, "times": times, "stations": data}, ensure_ascii=False)
    map_var = m.get_name()

    # 漸層說明條
    legend = """
    <div style="position:fixed;bottom:150px;right:20px;z-index:1000;background:white;
    padding:12px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:13px;font-family:sans-serif;">
    <b>借用率漸層（真實歷史資料）</b>
    <div style="width:200px;height:14px;margin:6px 0;border-radius:3px;
    background:linear-gradient(to right,#d7191c,#fdae61,#1a9641,#2c7fb8,#7b3294);"></div>
    <div style="display:flex;justify-content:space-between;width:200px;color:#555;">
      <span>0%<br>快空</span><span>50%<br>正常</span><span>100%<br>快滿</span>
    </div>
    <div style="color:#888;margin-top:6px;">圈越大=容量越大</div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    # 時間軸控制器 + JS
    js = """
    <div id="tl-box" style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
    z-index:1100;background:white;padding:14px 18px;border-radius:10px;
    box-shadow:0 2px 12px rgba(0,0,0,.28);font-family:sans-serif;font-size:13px;width:600px;max-width:94vw;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <b>🕒 歷史流動時間軸（S3 真實資料）</b>
        <span id="tl-meta" style="color:#666;"></span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <button id="tl-play" style="font-size:14px;padding:3px 12px;cursor:pointer;">▶ 播放</button>
        <input id="tl-slider" type="range" min="0" max="0" value="0" step="1" style="flex:1;">
        <b id="tl-time" style="min-width:50px;text-align:right;font-size:15px;">--:--</b>
      </div>
      <div id="tl-detail" style="margin-top:8px;color:#444;line-height:1.5;max-height:130px;overflow:auto;font-size:12px;"></div>
    </div>
    <script>
    // 等 folium 的地圖初始化完成後再跑（否則 map 變數還沒定義，整段會報錯）
    window.addEventListener('load', function(){
      var TL = __PAYLOAD__;
      var map = __MAP__;
      var names = Object.keys(TL.stations);
      var slider = document.getElementById('tl-slider');
      var timeEl = document.getElementById('tl-time');
      var detailEl = document.getElementById('tl-detail');
      var metaEl = document.getElementById('tl-meta');
      var playBtn = document.getElementById('tl-play');
      slider.max = TL.times.length - 1;
      metaEl.textContent = TL.date + '｜' + names.length + ' 站｜每30分鐘';

      function colorOf(u){
        u = Math.max(0, Math.min(100, u));
        if(u<15) return '#d7191c'; if(u<30) return '#fdae61';
        if(u<70) return '#1a9641'; if(u<85) return '#2c7fb8'; return '#7b3294';
      }

      // 畫該站「一整天借用率曲線」的 SVG 折線圖（點站點時彈出）
      function dayChartSVG(name, st, curIdx){
        var W = 340, H = 160, padL = 34, padB = 22, padT = 24, padR = 10;
        var plotW = W - padL - padR, plotH = H - padT - padB;
        var frames = st.frames;
        var n = frames.length;
        // 座標點：x 依時間索引、y 依借用率(0~100)
        function px(i){ return padL + (n<=1 ? 0 : i/(n-1)*plotW); }
        function py(u){ return padT + (1 - Math.max(0,Math.min(100,u))/100) * plotH; }
        // 折線
        var pts = frames.map(function(f,i){ return px(i)+','+py(f.usage_rate); }).join(' ');
        // 面積填色（折線下方）
        var area = 'M'+px(0)+','+py(0)+' L'+ frames.map(function(f,i){return px(i)+','+py(f.usage_rate);}).join(' L') +
                   ' L'+px(n-1)+','+(padT+plotH)+' L'+px(0)+','+(padT+plotH)+' Z';
        // Y 軸格線 0/50/100
        var grid = '';
        [0,50,100].forEach(function(v){
          var y = py(v);
          grid += '<line x1="'+padL+'" y1="'+y+'" x2="'+(W-padR)+'" y2="'+y+'" stroke="#eee" stroke-width="1"/>';
          grid += '<text x="'+(padL-4)+'" y="'+(y+3)+'" font-size="9" fill="#999" text-anchor="end">'+v+'</text>';
        });
        // X 軸標籤（每 6 小時 = 每 12 格）
        var xlabels = '';
        [0,12,24,36,47].forEach(function(i){
          if(i<n){ xlabels += '<text x="'+px(i)+'" y="'+(H-6)+'" font-size="9" fill="#999" text-anchor="middle">'+frames[i].time+'</text>'; }
        });
        // 當前時間游標（紅色垂直線 + 點）
        var cursor = '';
        if(curIdx != null && curIdx < n){
          var cx = px(curIdx), cy = py(frames[curIdx].usage_rate);
          cursor = '<line x1="'+cx+'" y1="'+padT+'" x2="'+cx+'" y2="'+(padT+plotH)+'" stroke="#e4572e" stroke-width="1.5" stroke-dasharray="3"/>'
                 + '<circle cx="'+cx+'" cy="'+cy+'" r="4" fill="#e4572e"/>';
        }
        return '<div style="font-family:sans-serif;">'
          + '<b style="font-size:13px;">'+name+'</b>'
          + '<div style="color:#888;font-size:11px;margin:2px 0 4px;">'+st.district+'｜容量 '+st.total+'｜借用率一日變化（%）</div>'
          + '<svg width="'+W+'" height="'+H+'" style="background:#fafafa;border-radius:6px;">'
          + grid
          + '<path d="'+area+'" fill="#1a964122"/>'
          + '<polyline points="'+pts+'" fill="none" stroke="#1a9641" stroke-width="2"/>'
          + cursor + xlabels
          + '</svg></div>';
      }

      var markers = {};
      names.forEach(function(name){
        var st = TL.stations[name];
        var radius = 8 + Math.min(20, st.total) / 2;   // 容量越大圈越大
        var mk = L.circleMarker([st.lat, st.lng], {
          radius: radius, color:'#333', weight:1, fillColor:'#ccc', fillOpacity:0.85
        }).addTo(map);
        // 點站點 → 彈出該站一整天的曲線圖（用當前時間軸位置標游標）
        mk.bindPopup(dayChartSVG(name, st, 0), {maxWidth: 380, minWidth: 360});
        markers[name] = {mk: mk, radius: radius};
      });

      function render(i){
        timeEl.textContent = TL.times[i] || '--:--';
        var lines = [];
        names.forEach(function(name){
          var st = TL.stations[name];
          var fr = st.frames[i];
          if(!fr) return;
          var mk = markers[name].mk;
          mk.setStyle({fillColor: colorOf(fr.usage_rate)});
          mk.bindTooltip(name + '｜借用率 ' + fr.usage_rate + '%｜可借 ' + fr.available_bikes,
            {permanent:false});
          // 若該站 popup 開著，更新曲線圖的紅色游標到當前時間
          if(mk.isPopupOpen()){
            mk.setPopupContent(dayChartSVG(name, st, i));
          }
          lines.push('<b>'+name+'</b>（'+st.district+'）：可借 '+fr.available_bikes
            +' / 可還 '+fr.available_docks+'｜借用率 '+fr.usage_rate+'%');
        });
        detailEl.innerHTML = lines.join('<br>');
      }

      slider.addEventListener('input', function(){ render(parseInt(this.value)); });

      var playing=false, timer=null;
      playBtn.addEventListener('click', function(){
        playing = !playing;
        playBtn.textContent = playing ? '⏸ 暫停' : '▶ 播放';
        if(playing){
          timer = setInterval(function(){
            var v = (parseInt(slider.value)+1) % TL.times.length;
            slider.value = v; render(v);
          }, 500);
        } else { clearInterval(timer); }
      });

      render(0);
    });
    </script>
    """
    js = js.replace("__PAYLOAD__", payload).replace("__MAP__", map_var)
    m.get_root().html.add_child(folium.Element(js))

    OUT.parent.mkdir(exist_ok=True)
    m.save(str(OUT))
    print(f"✅ 地圖已產出：{OUT}")
    print(f"   日期：{date}｜{len(data)} 站｜{n_frames} 個時間點（每30分鐘）")
    print(f"   用瀏覽器開，拖曳底部滑桿或按播放看一整天流動")


if __name__ == "__main__":
    main()
