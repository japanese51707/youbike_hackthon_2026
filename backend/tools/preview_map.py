"""
Mock 資料地圖預覽工具（臨時視覺化，非正式前端）
================================================
把 mock_data.json 的站點/調度建議/警示畫在新北市地圖上，
含漸層顏色（依借用率）+ 顏色說明條 + 可排序站點清單面板。
讓團隊直觀確認假資料是否合理，也給 C 做正式前端時的視覺參考。

用法：
    python backend/tools/preview_map.py
    → 產出 output/mock_preview.html，用瀏覽器開
"""

import json
from pathlib import Path

try:
    import folium
except ImportError:
    raise SystemExit("需要 folium：.venv/bin/pip install folium")

ROOT = Path(__file__).parent.parent.parent
MOCK = ROOT / "frontend" / "src" / "mock" / "mock_data.json"
OUT = ROOT / "output" / "mock_preview.html"


def usage_to_color(usage: float) -> str:
    """借用率 0~100 → 漸層色（紅→橘→綠→藍→紫）。低=缺車(紅)，高=太滿(紫)。"""
    u = max(0, min(100, usage))
    if u < 15:
        return "#d7191c"    # 紅：極低（快空）
    elif u < 30:
        return "#fdae61"    # 橘：偏低
    elif u < 70:
        return "#1a9641"    # 綠：正常
    elif u < 85:
        return "#2c7fb8"    # 藍：偏高
    else:
        return "#7b3294"    # 紫：極高（快滿）


def _add_timeline(m, data):
    """底部歷史時間軸滑桿：拖動切換時間點，即時更新涵蓋站點的顏色圓點與狀態。

    folium 產生的是靜態 HTML，這裡用純 JS 疊一層 Leaflet marker（獨立於現況標記），
    依 timeline.frames 逐格切換。正式前端由 C 用 React 做完整播放/拖曳。
    """
    timeline = data.get("timeline")
    if not timeline or not timeline.get("frames"):
        return

    stations = {s["station_id"]: s for s in data["stations"]}
    frames = timeline["frames"]
    # 只保留 timeline 有座標可畫的站
    coords = {sid: [stations[sid]["lat"], stations[sid]["lng"]]
              for f in frames for st in f["stations"]
              for sid in [st["station_id"]] if sid in stations}
    names = {sid: stations[sid]["station_name"] for sid in coords}

    payload = json.dumps({
        "district": timeline.get("district", ""),
        "date": timeline.get("date", ""),
        "frames": frames,
        "coords": coords,
        "names": names,
    }, ensure_ascii=False)

    map_var = m.get_name()

    js = """
    <div id="tl-box" style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
    z-index:1100;background:white;padding:12px 16px;border-radius:10px;
    box-shadow:0 2px 12px rgba(0,0,0,.28);font-family:sans-serif;font-size:13px;width:520px;max-width:92vw;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <b>🕒 歷史時間軸</b>
        <span id="tl-meta" style="color:#666;"></span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px;">
        <button id="tl-play" style="font-size:13px;padding:2px 10px;">▶ 播放</button>
        <input id="tl-slider" type="range" min="0" max="0" value="0" step="1" style="flex:1;">
        <b id="tl-time" style="min-width:48px;text-align:right;">--:--</b>
      </div>
      <div id="tl-detail" style="margin-top:8px;color:#444;line-height:1.5;"></div>
      <div style="color:#aaa;margin-top:4px;font-size:11px;">
        拖曳滑桿或按播放，觀察站點隨時間的變化（此為 mock 示範，正式前端由 C 做完整版）。
      </div>
    </div>
    <script>
    (function(){
      var TL = __PAYLOAD__;
      var map = __MAP__;
      var frames = TL.frames;
      var slider = document.getElementById('tl-slider');
      var timeEl = document.getElementById('tl-time');
      var detailEl = document.getElementById('tl-detail');
      var metaEl = document.getElementById('tl-meta');
      var playBtn = document.getElementById('tl-play');
      slider.max = frames.length - 1;
      metaEl.textContent = TL.district + '｜' + TL.date;

      function colorOf(u){
        u = Math.max(0, Math.min(100, u));
        if(u<15) return '#d7191c'; if(u<30) return '#fdae61';
        if(u<70) return '#1a9641'; if(u<85) return '#2c7fb8'; return '#7b3294';
      }

      // 為 timeline 涵蓋的站各建一個可更新的 marker（獨立圖層）
      var layer = L.layerGroup().addTo(map);
      var markers = {};
      Object.keys(TL.coords).forEach(function(sid){
        var mk = L.circleMarker(TL.coords[sid], {
          radius: 16, color:'#000', weight:2, fillColor:'#ccc', fillOpacity:0.9,
          dashArray:'4'
        }).addTo(layer);
        markers[sid] = mk;
      });

      function render(i){
        var fr = frames[i];
        timeEl.textContent = fr.time;
        var lines = [];
        fr.stations.forEach(function(st){
          var mk = markers[st.station_id];
          if(mk){
            mk.setStyle({fillColor: colorOf(st.usage_rate)});
            mk.setRadius(12 + (st.urgency_score||0)/100*10);  // 緊急度越高圈越大
            mk.bindTooltip(TL.names[st.station_id] + '｜' + st.usage_rate + '%｜緊急度' + (st.urgency_score||0),
              {permanent:false});
          }
          lines.push('<b>'+TL.names[st.station_id]+'</b>：可借 '+st.available_bikes
            +'｜借用率 '+st.usage_rate+'%｜緊急度 '+(st.urgency_score||0)+'（'+st.status+'）');
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
            var v = parseInt(slider.value);
            v = (v+1) % frames.length;
            slider.value = v; render(v);
          }, 1200);
        } else { clearInterval(timer); }
      });

      render(0);
    })();
    </script>
    """
    js = js.replace("__PAYLOAD__", payload).replace("__MAP__", map_var)
    m.get_root().html.add_child(folium.Element(js))


def main():
    data = json.loads(MOCK.read_text(encoding="utf-8"))
    stations = data["stations"]
    recs = data.get("recommendations", [])
    alerts = data.get("alerts", [])
    rec_ids = {r["station_id"] for r in recs}
    alert_ids = {a["station_id"] for a in alerts}

    center = [
        sum(s["lat"] for s in stations) / len(stations),
        sum(s["lng"] for s in stations) / len(stations),
    ]
    m = folium.Map(location=center, zoom_start=12, tiles="CartoDB positron")

    for s in stations:
        color = usage_to_color(s["usage_rate"])
        badges = []
        if s["station_id"] in rec_ids:
            badges.append("🚛需調度")
        if s["station_id"] in alert_ids:
            badges.append("⚠️警示")
        if not s.get("service_available", True):
            badges.append("⛔停用")
        if s.get("data_freshness") != "live":
            badges.append(f"📡{s.get('data_freshness')}")

        popup = folium.Popup(
            f"<b>{s['station_name']}</b><br>"
            f"{s['district']} / {s.get('area_type','')} / {s.get('terrain','')}<br>"
            f"借用率 <b>{s['usage_rate']}%</b><br>"
            f"可借 {s['available_bikes']} / 可還 {s['available_docks']} / 共 {s['total_docks']}<br>"
            f"{' '.join(badges)}",
            max_width=260,
        )
        folium.CircleMarker(
            location=[s["lat"], s["lng"]],
            radius=11,
            color="#333", weight=1,
            fill=True, fill_color=color, fill_opacity=0.85,
            popup=popup,
            tooltip=f"{s['station_name']}（{s['usage_rate']}%）{'｜'+' '.join(badges) if badges else ''}",
        ).add_to(m)

    # ── 漸層顏色說明條 + 標記說明（右下）──
    legend = """
    <div style="position:fixed;bottom:20px;right:20px;z-index:1000;background:white;
    padding:14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.2);font-size:13px;font-family:sans-serif;max-width:260px;">
    <b>借用率漸層</b>
    <div style="width:220px;height:16px;margin:6px 0;border-radius:3px;
    background:linear-gradient(to right,#d7191c,#fdae61,#1a9641,#2c7fb8,#7b3294);"></div>
    <div style="display:flex;justify-content:space-between;width:220px;color:#555;">
      <span>0%<br>快空</span><span>50%<br>正常</span><span>100%<br>快滿</span>
    </div>
    <hr style="margin:8px 0;">
    <b>標記說明</b>
    <div style="margin-top:4px;line-height:1.6;">
      <div><b>⚠️ 警示</b>＝<u>發現問題的通知</u>（站快空/滿）。給後台與機關看，就是題目要的警示功能。</div>
      <div><b>🚛 需調度</b>＝<u>解決問題的行動建議</u>（補/取幾台車）。給調度員執行。</div>
      <div style="color:#888;margin-top:4px;">比喻：⚠️=火災警報響了；🚛=派消防車的調度單。</div>
      <div style="margin-top:4px;">⛔停用　📡非即時資料</div>
    </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend))

    # ── 可排序站點清單面板（左上，可摺疊）──
    rows = []
    for s in stations:
        need = "🚛" if s["station_id"] in rec_ids else ""
        alert = "⚠️" if s["station_id"] in alert_ids else ""
        rows.append(
            f'<tr>'
            f'<td>{s["station_name"]}</td>'
            f'<td>{s["district"]}</td>'
            f'<td data-sort="{s["usage_rate"]}">{s["usage_rate"]}%</td>'
            f'<td>{s["available_bikes"]}</td>'
            f'<td>{need}{alert}</td>'
            f'</tr>'
        )
    # 建議調度清單（依 priority_score 排序）
    rec_rows = "".join(
        f'<li>{r["priority_level"].upper()}｜<b>{r["station_name"]}</b>｜'
        f'{r["action"]} {r["quantity"]}台｜緊急度 {r["priority_score"]}｜{r["reason"]}</li>'
        for r in sorted(recs, key=lambda x: -x["priority_score"])
    )

    panel = """
    <div id="panel" style="position:fixed;top:12px;left:12px;z-index:1000;background:white;
    padding:12px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.25);font-family:sans-serif;
    font-size:12px;max-width:420px;max-height:80vh;overflow:auto;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <b style="font-size:14px;">站點總覽（mock 預覽）</b>
        <button onclick="var t=document.getElementById('tbl');t.style.display=t.style.display=='none'?'':'none';"
          style="font-size:11px;">摺疊/展開</button>
      </div>

      <div style="margin-top:8px;padding:8px;background:#fff6e5;border-radius:6px;">
        <b>🚛 建議調度清單（依緊急度）</b>
        <ol style="margin:6px 0 0 18px;padding:0;">__REC_ROWS__</ol>
      </div>

      <table id="tbl" style="margin-top:10px;border-collapse:collapse;width:100%;">
        <thead><tr style="background:#f0f0f0;cursor:pointer;">
          <th onclick="sortTable(0,false)">站名</th>
          <th onclick="sortTable(1,false)">區</th>
          <th onclick="sortTable(2,true)">借用率▼</th>
          <th onclick="sortTable(3,true)">可借</th>
          <th onclick="sortTable(4,false)">標記</th>
        </tr></thead>
        <tbody>__ROWS__</tbody>
      </table>
      <div style="color:#999;margin-top:6px;">點欄位標題可排序。此為臨時預覽，正式前端由 C 用 React 做。</div>
    </div>
    <script>
    function sortTable(col, numeric){
      var tb=document.querySelector('#tbl tbody');
      var rows=Array.from(tb.rows);
      var asc=tb.getAttribute('data-asc-'+col)!=='1';
      rows.sort(function(a,b){
        var x=numeric?parseFloat(a.cells[col].getAttribute('data-sort')||a.cells[col].innerText):a.cells[col].innerText;
        var y=numeric?parseFloat(b.cells[col].getAttribute('data-sort')||b.cells[col].innerText):b.cells[col].innerText;
        if(x<y)return asc?-1:1; if(x>y)return asc?1:-1; return 0;
      });
      rows.forEach(function(r){tb.appendChild(r);});
      tb.setAttribute('data-asc-'+col, asc?'1':'0');
    }
    </script>
    """
    panel = panel.replace("__REC_ROWS__", rec_rows).replace("__ROWS__", "".join(rows))
    m.get_root().html.add_child(folium.Element(panel))

    # ── 歷史時間軸（底部滑桿）──
    _add_timeline(m, data)

    OUT.parent.mkdir(exist_ok=True)
    m.save(str(OUT))
    print(f"✅ 地圖已產出：{OUT}")
    print(f"   站點：{len(stations)}｜需調度：{len(rec_ids)}｜警示：{len(alert_ids)}")
    tl = data.get("timeline", {})
    tl_frames = len(tl.get("frames", []))
    print(f"   時間軸：{tl.get('district','-')} {tl.get('date','')}｜{tl_frames} 個時間點")
    print("   新增：漸層顏色 + 顏色說明條(含警示vs調度說明) + 可排序清單 + 建議調度清單 + 歷史時間軸滑桿")


if __name__ == "__main__":
    main()
