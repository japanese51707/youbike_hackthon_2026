"""
特徵組裝 pipeline（prediction.feature_pipeline）— P1
=====================================================
把 backend/features/ 的因子 + 站點歷史存量，組裝成可訓練/推論的特徵表。
這一層是**防洩漏約束的強制執行點**（ADR-013~016）。

★強制約束（不可繞過）：
  1. 計算窗口（ADR-013/014）：歷史統計/行為指紋/站點識別特徵，只用「目標時點之前」的資料。
     訓練時用訓練期；每列的站點識別特徵用「該列時點之前」的歷史（避免用到未來）。
  2. 缺失值（§5-1）：只 forward fill，禁 interpolate。
  3. 截斷標記（ADR-015）：目標 Δ=0 且同時空站(可借=0)或滿站(可還=0) → 標 is_censored。
     正常站的 Δ=0 不標（是真實低需求）。
  4. lag（ADR-013）：只往過去取。

目標變數：淨變化量 Δ = available_bikes(t+1) − available_bikes(t)（下一時段，30分）。
  規則引擎吃「到達存量」，等同 available(t) + 預測Δ；預測Δ的區間下界/上界即防空/防滿。

本模組先做「單站時序特徵 + 站點識別特徵 + 時間特徵」的最小可行組裝，
先拿到第一個誠實數字；環境類因子（天氣/POI等）待 baseline 出來後以消融決定加不加（F-08）。

對外暴露：
    build_training_frame(df, train_end, ...) -> (X, y, meta)
"""

from __future__ import annotations
import numpy as np
import pandas as pd

# 每 30 分一格
LAG_SLOTS = {"lag_30min": 1, "lag_1hr": 2, "lag_2hr": 4, "lag_1day": 48, "lag_1week": 336}

# 多視野（ADR-017）：格數 → 分鐘數。每 30 分一格，故 h 格 = h*30 分。
HORIZON_STEPS = {1: 30, 2: 60, 3: 90, 4: 120}


# ADR-018 ②③：站點主檔歸併 + 新舊站標記
COORD_DECIMALS = 4  # 經緯度取整位數（小數 4 位 ≈ 10 公尺），作為 station_key 主鍵


def _attach_station_key(df: pd.DataFrame) -> pd.DataFrame:
    """以經緯度(小數 4 位≈10 公尺)為主鍵歸併站點，處理編碼亂碼/改名造成的同站被拆。

    產生欄位：
      - station_key：canonical 站點主鍵字串 "lat_lng"（歸併後，同座標視為同站）
      - is_new_station：ADR-018 ③ 新舊站標記（訓練期結束後才首次出現 → 1）

    有座標缺失(NaN)的列，退回用場站名稱當 key（極少數，避免整列丟失）。
    """
    df = df.copy()
    lat_col = "緯度" if "緯度" in df.columns else "lat"
    lng_col = "經度" if "經度" in df.columns else "lng"
    lat = pd.to_numeric(df[lat_col], errors="coerce").round(COORD_DECIMALS)
    lng = pd.to_numeric(df[lng_col], errors="coerce").round(COORD_DECIMALS)
    key = lat.astype("string") + "_" + lng.astype("string")
    # 座標缺失退回站名（避免 NaN key 把不同站併在一起）
    key = key.where(lat.notna() & lng.notna(), other="name:" + df["場站名稱"].astype("string"))
    df["station_key"] = key
    return df


def _forward_fill_grid(g: pd.DataFrame) -> pd.DataFrame:
    """單站：補齊 30 分鐘時間格，缺值只 forward fill（禁 interpolate，防洩漏）。"""
    g = g.sort_values("dt").set_index("dt")
    full = pd.date_range(g.index.min(), g.index.max(), freq="30min")
    g = g.reindex(full)
    # 只 forward fill（用過去值補，不用未來）
    for col in ["available_bikes", "available_docks", "total_docks"]:
        g[col] = g[col].ffill()
    # 站點識別欄位維持（reindex 產生的 NaN 用同站唯一值補回）
    for col in ["場站名稱", "station_key", "is_new_station"]:
        if col in g.columns:
            g[col] = g[col].ffill().bfill()
    # 保留座標欄（天氣因子對照最近測站要用）——reindex 會產生 NaN，ffill 補回
    for col in ["經度", "緯度", "lat", "lng"]:
        if col in g.columns:
            g[col] = g[col].ffill().bfill()
    return g.reset_index(names="dt")


def _add_lag_and_target(g: pd.DataFrame) -> pd.DataFrame:
    """單站：加 lag（過去）、變化率、目標 Δ(t→t+1)、截斷標記。"""
    g = g.sort_values("dt").reset_index(drop=True)
    ab = g["available_bikes"]

    for name, k in LAG_SLOTS.items():
        g[name] = ab.shift(k)              # 過去值
    g["change_1hr"] = ab - ab.shift(2)     # 近1小時變化（過去）
    g["change_2hr"] = ab - ab.shift(4)
    # 逐格絕對變化（ADR-019 周轉量基礎）：|ab(t)-ab(t-1)|，用絕對值才是真周轉
    # （淨變化會被借出又還回相抵洗成 0）。後續在 build_training_frame 用訓練期累加算 turnover。
    g["abs_change_1step"] = (ab - ab.shift(1)).abs()

    # 多視野目標（ADR-017）：h 格後的「累積淨變化」= available(t+h) − available(t)
    #   每 30 分一格：h=1/2/3/4 對應 30/60/90/120 分鐘。直接對累積 Δ 訓練（分位數不可加）。
    for h, mins in HORIZON_STEPS.items():
        g[f"target_delta_{mins}"] = ab.shift(-h) - ab

    # 截斷標記（ADR-015）：以「30分視野目標」判定（可借=0 或 可還=0 且 Δ=0）
    # 注意 target_delta_30 末格為 NaN（shift(-1)），fillna(False) 讓其不算截斷（之後 dropna 會移除）
    at_empty = (g["available_bikes"] <= 0)
    at_full = (g["available_docks"] <= 0)
    censored = (g["target_delta_30"] == 0) & (at_empty | at_full)
    g["is_censored"] = censored.fillna(False).astype(int)

    return g


def _rain_level(precp: float) -> int:
    """雨量(mm/時) → 分級。資料無日照無法分晴/陰，故用雨量當天氣型態（對騎乘影響更直接）。
    0=無雨(晴到多雲) 1=小雨(<5) 2=中雨(5-15) 3=大雨(>=15)。缺測(-90以下)當無雨。"""
    if precp is None or precp <= -90 or precp < 0:
        return 0
    if precp == 0:
        return 0
    if precp < 5:
        return 1
    if precp < 15:
        return 2
    return 3


def attach_weather(frame: pd.DataFrame) -> pd.DataFrame:
    """全站批次併入天氣特徵（你的原則：外部全站取得，不逐站設參數）。

    每個 YouBike 站 → 最近氣象測站（weather.nearest_station，已建對照），
    取該測站逐時的 溫度/濕度/雨量/風速，對齊到 30 分格（逐時值填該小時兩個半時）。
    加衍生：溫度舒適度(倒U)、雨量分級(天氣型態)。缺值 forward fill（不用未來）。
    """
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent.parent))
    from features.weather import nearest_station, _load_station_year, _temp_comfort

    # 1. 全站 → 最近測站（一次算好，站數有限）。以 station_key 為主鍵（ADR-018）
    coords = frame.groupby("station_key").first().reset_index()
    st_map = {}
    for _, r in coords.iterrows():
        lat = r.get("緯度")
        if lat is None or pd.isna(lat):
            lat = r.get("lat")
        lng = r.get("經度")
        if lng is None or pd.isna(lng):
            lng = r.get("lng")
        # ★注意 float('nan') 在 Python 是 truthy，必須用 pd.notna 明確擋掉髒座標（ADR-018）
        # 座標無效的站(極少數)跳過→天氣欄留 NaN，由後續 ffill 處理，不讓整批崩潰
        if lat is not None and lng is not None and pd.notna(lat) and pd.notna(lng):
            st_map[r["station_key"]] = nearest_station(float(lat), float(lng))["station_id"]

    # 2. 逐測站讀天氣（快取），向量化組成查表（不逐列 append，避免慢）
    year = int(str(frame["dt"].iloc[0])[:4])
    wcols = ["temperature", "humidity", "precipitation", "wind_speed"]
    parts = []
    for sid in set(st_map.values()):
        try:
            wdf = _load_station_year(sid, year).reset_index()  # index 是 hourkey 字串 'YYYY-MM-DD HH'
        except Exception:
            continue
        keep = ["_hourkey"] + [c for c in wcols if c in wdf.columns]
        w = wdf[keep].copy()
        # 同小時多筆取第一筆
        w = w.groupby("_hourkey", as_index=False).first()
        # 缺測值(-90以下)轉 NaN（向量化）
        for c in wcols:
            if c in w.columns:
                w.loc[w[c] <= -90, c] = np.nan
        w["wsid"] = sid
        parts.append(w)
    wtab = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["_hourkey", "wsid"])

    # 3. frame 加測站 id + 小時鍵，join 天氣
    frame = frame.copy()
    frame["wsid"] = frame["station_key"].map(st_map)
    frame["_hourkey"] = frame["dt"].dt.strftime("%Y-%m-%d %H")
    frame = frame.merge(wtab, on=["wsid", "_hourkey"], how="left")

    # 4. 衍生特徵
    frame["temp_comfort"] = frame["temperature"].apply(
        lambda t: _temp_comfort(t) if pd.notna(t) else None)
    frame["rain_level"] = frame["precipitation"].apply(_rain_level)
    # 缺值 forward fill（同站時序，不用未來）。以 station_key 分組（ADR-018）
    for col in ["temperature", "humidity", "wind_speed", "temp_comfort"]:
        frame[col] = frame.groupby("station_key")[col].ffill()
    return frame.drop(columns=["wsid", "_hourkey"])


def attach_holiday(frame: pd.DataFrame) -> pd.DataFrame:
    """全市批次併入假日特徵（ADR-011 假日因子；全站共用，不分站）。

    假日是全市一致的「已知未來確定」因子（月曆早定好）。以「唯一日期」批次算好一張小表
    （1~6 月約 180 天），再 map 回 frame，效率高。
    特徵：is_holiday（放假）、is_national_holiday（國定假日，非單純週末）、
          is_long_weekend（連假，前後含當天連續 ≥3 天放假）。
    ★注意與既有 is_weekend/weekday 重疊：假日因子的邊際價值在「平日型假日」（如落在平日的
      春節/端午）與「補班的週六」——這些是 is_weekend 抓不到的部分。
    """
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent.parent))
    from features.calendar_holiday import get_holiday_feature

    frame = frame.copy()
    frame["_datekey"] = frame["dt"].dt.strftime("%Y%m%d")
    uniq = frame["_datekey"].dropna().unique()
    rows = []
    for dk in uniq:
        f = get_holiday_feature(dk)
        rows.append({"_datekey": dk,
                     "is_holiday": int(bool(f["is_holiday"])),
                     "is_national_holiday": int(bool(f["is_national_holiday"])),
                     "is_long_weekend": int(bool(f["is_long_weekend"]))})
    htab = pd.DataFrame(rows)
    frame = frame.merge(htab, on="_datekey", how="left")
    return frame.drop(columns=["_datekey"])


# POI 距離特徵欄（14 類）+ 區域類型類別碼，供 build_training_frame 引用
_POI_DIST_COLS = [
    "dist_metro_km", "dist_train_km", "dist_bus_terminal_km", "dist_school_km",
    "dist_mall_km", "dist_traditional_market_km", "dist_night_market_km",
    "dist_hospital_km", "dist_park_km", "dist_park_sports_km",
    "dist_park_forest_km", "dist_riverside_km", "dist_venue_km",
    "dist_sports_center_km",
]
# area_type 文字 → 類別碼（LightGBM 吃數值；label encode，順序不代表大小，模型用分裂處理）
_AREA_CODE = {"transit": 0, "school": 1, "commercial": 2, "leisure": 3,
              "medical": 4, "venue": 5, "sports": 6, "residential": 7, "mixed": 8}


def attach_poi(frame: pd.DataFrame) -> pd.DataFrame:
    """全站批次併入 POI 距離特徵 + 區域類型（ADR-012，14 類，靜態）。

    POI 距離是靜態的（站座標固定），故以唯一 station_key 算一次距離再 merge 回，效率高。
    特徵：到 14 類最近 POI 的距離(km) + area_type_code（區域類型類別碼）。
    """
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent.parent))
    from features.poi_distance import get_poi_feature

    frame = frame.copy()
    # 每站一組座標（用 groupby first 拿座標）
    coords = frame.groupby("station_key").first().reset_index()
    rows = []
    for _, r in coords.iterrows():
        lat = r.get("緯度")
        if lat is None or pd.isna(lat):
            lat = r.get("lat")
        lng = r.get("經度")
        if lng is None or pd.isna(lng):
            lng = r.get("lng")
        rec = {"station_key": r["station_key"]}
        if lat is not None and lng is not None and pd.notna(lat) and pd.notna(lng):
            f = get_poi_feature(float(lat), float(lng))
            for c in _POI_DIST_COLS:
                rec[c] = f.get(c)
            rec["area_type_code"] = _AREA_CODE.get(f.get("area_type"), 8)
        else:
            for c in _POI_DIST_COLS:
                rec[c] = None
            rec["area_type_code"] = 8  # mixed（座標缺失）
        rows.append(rec)
    ptab = pd.DataFrame(rows)
    return frame.merge(ptab, on="station_key", how="left")


def build_training_frame(
    df: pd.DataFrame,
    train_end: str,
    profile_by_station: dict | None = None,
    with_weather: bool = False,
    with_holiday: bool = False,
    with_poi: bool = False,
    dayoff_mode: bool = True,   # ADR-011 定案：is_weekend 升級 is_dayoff 為預設行為（消融可關）
):
    """組裝訓練特徵表。

    df：長格式，欄位含 場站名稱、日期(timestamp)、available_bikes/docks、total_docks。
    train_end：訓練期結束日（如 '2026-05-31'），用於分割 + 算站點識別特徵的窗口界線。
    profile_by_station：（可選）站點識別特徵，只能用訓練期算好的（防洩漏）。

    回傳 (frame, feature_cols)：frame 含特徵 + target_delta + is_censored + is_train。
    """
    df = df.copy()
    df["dt"] = pd.to_datetime(df["日期"] if "日期" in df.columns else df["timestamp"])
    if "available_bikes" not in df.columns:
        df = df.rename(columns={"可借車數": "available_bikes",
                                "可還位數": "available_docks",
                                "總車柱數": "total_docks"})

    # ADR-018 ①：時間戳統一。3~5 月來源帶秒(如 00:00:43)、且與 1/2/6 月整點不齊，
    # 一律 floor 到 30 分格，根除跨月接縫與未來跨站對齊風險。
    df["dt"] = df["dt"].dt.floor("30min")

    # ADR-018 ②：站點主檔歸併。schema 無站點 ID，只有場站名稱(字串)，且含編碼亂碼
    # (同座標不同名)。以經緯度(小數 4 位≈10 公尺)為主鍵 station_key 歸併，
    # 避免同一站被拆成兩份稀釋歷史/站點識別特徵。
    df = _attach_station_key(df)

    frames = []
    for key, g in df.groupby("station_key"):
        g = _forward_fill_grid(g)
        g = _add_lag_and_target(g)
        frames.append(g)
    frame = pd.concat(frames, ignore_index=True)

    # 時間特徵（衍生，無洩漏）
    frame["hour"] = frame["dt"].dt.hour
    frame["weekday"] = frame["dt"].dt.weekday
    frame["is_weekend"] = (frame["weekday"] >= 5).astype(int)
    frame["month"] = frame["dt"].dt.month
    frame["time_slot"] = frame["hour"] * 2 + (frame["dt"].dt.minute >= 30).astype(int)

    # dayoff_mode（ADR-011 假日因子的「修正既有特徵」做法，非加料）：
    # 把 is_weekend 升級為 is_dayoff——週末 OR 國定假日視為放假、補班日視為上班。
    # 讓「落在平日的春節/清明」與「補班的週六」被正確歸類（放假就是放假，不管週末或國定）。
    # ★特徵欄不變（仍叫 is_weekend），只改值，是乾淨對照；連 station_slot_p50 分組也按放假型態。
    if dayoff_mode:
        import sys as _sys
        from pathlib import Path as _P
        _sys.path.insert(0, str(_P(__file__).parent.parent))
        from features.calendar_holiday import get_holiday_feature
        dks = frame["dt"].dt.strftime("%Y%m%d")
        offmap = {dk: int(bool(get_holiday_feature(dk)["is_holiday"]))
                  for dk in dks.dropna().unique()}
        frame["is_weekend"] = dks.map(offmap).fillna(frame["is_weekend"]).astype(int)

    # 訓練/驗證切分（時間切分，ADR-002）
    train_end_ts = pd.to_datetime(train_end) + pd.Timedelta(days=1)
    frame["is_train"] = (frame["dt"] < train_end_ts).astype(int)

    # ADR-018 ③：新舊站標記。以 station_key 首次出現時間 ≥ 訓練期結束 → 新站(冷啟動)。
    # 用於評估分報「老站/新站」MAE，讓新站表現不被整體平均掩蓋（owner 核准分界=訓練期結束）。
    first_seen = frame.groupby("station_key")["dt"].transform("min")
    frame["is_new_station"] = (first_seen >= train_end_ts).astype(int)

    # 站點識別特徵（F-06）：該站 × day_type × time_slot 的「訓練期」歷史 P50 淨流量
    # ★只用訓練期算，避免洩漏（ADR-013/014 窗口約束）
    # ★以 station_key（歸併後主鍵）分組，避免亂碼站名把同站拆成兩份稀釋（ADR-018）
    train_part = frame[frame["is_train"] == 1].copy()
    train_part["dtype"] = train_part["is_weekend"]
    profile = (train_part.groupby(["station_key", "dtype", "time_slot"])["target_delta_30"]
               .median().rename("station_slot_p50").reset_index())
    frame["dtype"] = frame["is_weekend"]
    frame = frame.merge(profile, on=["station_key", "dtype", "time_slot"], how="left")

    # ADR-019：訓練期周轉量 + 樣本權重 + 決策層信心分級
    # ★防洩漏鐵律：turnover 只用訓練期(is_train==1)算，6 月驗證期不參與。
    #   turnover = 該站訓練期「逐格絕對變化 |ab(t)-ab(t-1)|」的平均（每格平均周轉量）。
    tp = frame[frame["is_train"] == 1]
    turnover = (tp.groupby("station_key")["abs_change_1step"]
                .mean().rename("station_turnover").reset_index())
    frame = frame.merge(turnover, on="station_key", how="left")
    # 新站等在訓練期沒資料 → turnover 為 NaN，補 0（低流量對待，權重最小）
    frame["station_turnover"] = frame["station_turnover"].fillna(0.0)
    # 樣本權重（三方案，train.py 消融時選用；此處三欄都備好）
    frame["w_equal"] = 1.0
    frame["w_log"] = np.log1p(frame["station_turnover"])       # log(1+turnover) 溫和
    frame["w_linear"] = frame["station_turnover"]              # 線性（看極端站是否主宰）
    # 決策層信心分級（機制 C，僅排序/標註，不進調度觸發—守 ADR-014）
    # 以訓練期 turnover 的三分位數分「低/中/高流量」
    q = tp.groupby("station_key")["abs_change_1step"].mean()
    if len(q) >= 3:
        lo, hi = q.quantile(0.33), q.quantile(0.67)
    else:
        lo, hi = 0.0, 0.0
    frame["confidence_tier"] = pd.cut(
        frame["station_turnover"], bins=[-1, lo, hi, float("inf")],
        labels=["low", "mid", "high"]).astype("string").fillna("low")

    feature_cols = [
        *LAG_SLOTS.keys(), "change_1hr", "change_2hr",
        "available_bikes", "available_docks", "total_docks",
        "hour", "weekday", "is_weekend", "month", "time_slot",
        "station_slot_p50",   # F-06 站點識別特徵（最強）
    ]

    # 消融用：可選擇性併入天氣因子（你的原則：全站批次取得）
    if with_weather:
        frame = attach_weather(frame)
        feature_cols += ["temperature", "humidity", "wind_speed",
                         "temp_comfort", "rain_level"]

    # 消融用：可選擇性併入假日因子（ADR-011，全市批次；is_weekend 之外的平日型假日/補班）
    if with_holiday:
        frame = attach_holiday(frame)
        feature_cols += ["is_holiday", "is_national_holiday", "is_long_weekend"]

    # 消融用：可選擇性併入 POI 距離因子（ADR-012，14 類靜態距離 + 區域類型）
    if with_poi:
        frame = attach_poi(frame)
        feature_cols += _POI_DIST_COLS + ["area_type_code"]

    return frame, feature_cols
