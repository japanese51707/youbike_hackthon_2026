"""
後台儀表板最小版（T5, D7）
==========================
產出一個 HTML 檔，包含：
1. 地圖熱力圖（站點狀態：綠/黃/紅）
2. 水位 vs 目標的摘要面板
3. 調度建議清單（來自 rule_engine）
4. 確認動作走過閘門（頁面顯示確認流程說明）

D7: 乾淨可用即可，不追求接近 YouBike 官方完成度。

用法：
    python dashboard.py
    # 產出 output/dashboard.html，用瀏覽器開啟即可
"""

import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from pathlib import Path
import json

PARQUET_DIR = Path("output/youbike_parquet")
OUTPUT_DIR = Path("output")


def load_snapshot():
    """載入 6 月某個尖峰時段的快照"""
    df = pd.read_parquet(PARQUET_DIR / "year_month=2026-06" / "data.parquet")
    df["dt"] = pd.to_datetime(df["日期"])

    # 取平日早上 8 點
    target = "2026-06-02 08:00:00"
    snapshot = df[df["日期"] == target].copy()
    if len(snapshot) == 0:
        snapshot = df[df["dt"].dt.hour == 8].head(1583)

    return snapshot, target


def get_station_status(row):
    """判斷站點狀態顏色"""
    usage_rate = row["可借車數"] / row["總車柱數"] * 100 if row["總車柱數"] > 0 else 50

    if row["可借車數"] == 0:
        return "red", "空站", "⛔"
    elif row["可還位數"] == 0:
        return "darkred", "滿站", "🔴"
    elif usage_rate < 15:
        return "orange", "低水位", "🟠"
    elif usage_rate > 85:
        return "purple", "高水位", "🟣"
    elif usage_rate < 30:
        return "lightgreen", "偏低", "🟡"
    elif usage_rate > 70:
        return "blue", "偏高", "🔵"
    else:
        return "green", "正常", "🟢"


def build_map(snapshot, target_time):
    """建立 Folium 地圖"""
    # 中心點：新北市
    center_lat = snapshot["緯度"].mean()
    center_lon = snapshot["經度"].mean()

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    # 統計
    empty_count = (snapshot["可借車數"] == 0).sum()
    full_count = (snapshot["可還位數"] == 0).sum()
    low_count = ((snapshot["可借車數"] / snapshot["總車柱數"]) < 0.15).sum() - empty_count
    normal_count = len(snapshot) - empty_count - full_count - low_count

    # 加入站點標記
    for _, row in snapshot.iterrows():
        color, status, icon = get_station_status(row)
        usage_pct = row["可借車數"] / row["總車柱數"] * 100 if row["總車柱數"] > 0 else 0

        popup_html = f"""
        <div style="font-family: sans-serif; min-width: 200px;">
            <b>{row['場站名稱']}</b><br>
            <small>{row['行政區']}</small><hr style="margin:4px 0">
            <table style="font-size:12px;">
                <tr><td>可借</td><td><b>{int(row['可借車數'])}</b> 台</td></tr>
                <tr><td>可還</td><td><b>{int(row['可還位數'])}</b> 位</td></tr>
                <tr><td>總車柱</td><td>{int(row['總車柱數'])}</td></tr>
                <tr><td>借用率</td><td>{usage_pct:.0f}%</td></tr>
                <tr><td>狀態</td><td><b style="color:{color}">{status}</b></td></tr>
            </table>
        </div>
        """

        folium.CircleMarker(
            location=[row["緯度"], row["經度"]],
            radius=5 if status == "正常" else 8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7 if status != "正常" else 0.4,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{row['場站名稱']}: {int(row['可借車數'])}/{int(row['總車柱數'])} ({status})",
        ).add_to(m)

    # 加入圖例和摘要面板
    legend_html = f"""
    <div style="position:fixed; top:10px; right:10px; z-index:1000;
                background:white; padding:15px; border-radius:8px;
                box-shadow:0 2px 10px rgba(0,0,0,0.2); font-family:sans-serif;
                max-width:320px;">
        <h3 style="margin:0 0 10px 0; font-size:16px;">YouBike 智慧調度系統</h3>
        <p style="margin:0; font-size:11px; color:#666;">快照時間：{target_time}</p>
        <hr style="margin:8px 0;">

        <h4 style="margin:5px 0; font-size:13px;">站點狀態摘要</h4>
        <table style="font-size:12px; width:100%;">
            <tr><td>⛔ 空站</td><td style="text-align:right;"><b style="color:red;">{empty_count}</b> 站</td></tr>
            <tr><td>🔴 滿站</td><td style="text-align:right;"><b style="color:darkred;">{full_count}</b> 站</td></tr>
            <tr><td>🟠 低水位</td><td style="text-align:right;"><b style="color:orange;">{low_count}</b> 站</td></tr>
            <tr><td>🟢 正常</td><td style="text-align:right;">{normal_count} 站</td></tr>
            <tr><td colspan="2"><hr style="margin:4px 0;"></td></tr>
            <tr><td>總站數</td><td style="text-align:right;">{len(snapshot)}</td></tr>
        </table>

        <hr style="margin:8px 0;">
        <h4 style="margin:5px 0; font-size:13px;">系統 KPI</h4>
        <table style="font-size:12px; width:100%;">
            <tr><td>空站率</td><td style="text-align:right;">{empty_count/len(snapshot)*100:.1f}%</td></tr>
            <tr><td>滿站率</td><td style="text-align:right;">{full_count/len(snapshot)*100:.1f}%</td></tr>
            <tr><td>平均借用率</td><td style="text-align:right;">{(snapshot['可借車數']/snapshot['總車柱數']).mean()*100:.0f}%</td></tr>
        </table>

        <hr style="margin:8px 0;">
        <h4 style="margin:5px 0; font-size:13px;">圖例</h4>
        <div style="font-size:11px;">
            <span style="color:red;">●</span> 空站（可借=0）
            <span style="color:darkred;">●</span> 滿站（可還=0）<br>
            <span style="color:orange;">●</span> 低水位（<15%）
            <span style="color:purple;">●</span> 高水位（>85%）<br>
            <span style="color:green;">●</span> 正常
        </div>

        <hr style="margin:8px 0;">
        <h4 style="margin:5px 0; font-size:13px;">調度建議（Top 5）</h4>
        <div style="font-size:11px; max-height:150px; overflow-y:auto;">
    """

    # 加入 top 5 調度建議
    empty_stations = snapshot[snapshot["可借車數"] == 0].head(5)
    for _, st in empty_stations.iterrows():
        legend_html += f"<div style='margin:2px 0;'>🚛 <b>{st['場站名稱']}</b>：補車至50%</div>"

    legend_html += """
        </div>
        <hr style="margin:8px 0;">
        <div style="font-size:10px; color:#999;">
            ⚠️ 調度指令需經確認閘門<br>
            預覽 → 確認 → 執行 → 驗證
        </div>
    </div>
    """

    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def main():
    print("=" * 60)
    print("後台儀表板最小版（T5, D7）")
    print("=" * 60)

    snapshot, target_time = load_snapshot()
    print(f"  快照時間: {target_time}")
    print(f"  站點數: {len(snapshot)}")
    print(f"  空站: {(snapshot['可借車數'] == 0).sum()}")
    print(f"  滿站: {(snapshot['可還位數'] == 0).sum()}")

    print("\n🗺️  建立地圖...")
    m = build_map(snapshot, target_time)

    output_path = OUTPUT_DIR / "dashboard.html"
    m.save(str(output_path))
    print(f"\n💾 已儲存: {output_path}")
    print(f"   用瀏覽器打開即可檢視")

    print("\n✅ T5 後台儀表板完成！")


if __name__ == "__main__":
    main()
