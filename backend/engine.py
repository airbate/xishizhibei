from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

REQUIRED = ["date", "meal_period", "dish_name", "prepared_qty", "sold_qty", "unit_price", "unit_cost"]
MEALS = {"breakfast", "lunch", "dinner"}


class DataValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        super().__init__("数据校验失败")
        self.errors = errors


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        frame = pd.read_excel(path)
    elif path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    else:
        raise DataValidationError([{"row": 0, "field": "file", "message": "仅支持 CSV 或 XLSX"}])
    return validate_table(frame)


def validate_table(frame: pd.DataFrame) -> pd.DataFrame:
    errors: list[dict[str, Any]] = []
    missing = [column for column in REQUIRED if column not in frame.columns]
    for column in missing:
        errors.append({"row": 0, "field": column, "message": "缺少必填字段"})
    if missing:
        raise DataValidationError(errors)
    if frame.empty:
        raise DataValidationError([{"row": 0, "field": "file", "message": "文件没有有效记录"}])

    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for index, value in result["date"].items():
        if pd.isna(value):
            errors.append({"row": int(index) + 2, "field": "date", "message": "日期无法解析"})
    for column in ["prepared_qty", "sold_qty", "unit_price", "unit_cost"]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
        for index, value in result[column].items():
            if pd.isna(value):
                errors.append({"row": int(index) + 2, "field": column, "message": "必须是数值"})
            elif value < 0:
                errors.append({"row": int(index) + 2, "field": column, "message": "不能为负数"})
    for index, row in result.iterrows():
        if row["meal_period"] not in MEALS:
            errors.append({"row": int(index) + 2, "field": "meal_period", "message": "必须是 breakfast/lunch/dinner"})
        if pd.notna(row["sold_qty"]) and pd.notna(row["prepared_qty"]) and row["sold_qty"] > row["prepared_qty"]:
            errors.append({"row": int(index) + 2, "field": "sold_qty", "message": "售出量不能大于备餐量"})
    if errors:
        raise DataValidationError(errors[:100])
    if result["date"].nunique() < 7:
        errors.append({"row": 0, "field": "date", "message": "至少需要覆盖 7 天"})
    if result["dish_name"].nunique() < 3:
        errors.append({"row": 0, "field": "dish_name", "message": "至少需要 3 个菜品"})
    if len(result) < 20:
        errors.append({"row": 0, "field": "file", "message": "至少需要 20 条有效记录"})
    if errors:
        raise DataValidationError(errors)

    result["waste_qty"] = pd.to_numeric(result.get("waste_qty", result["prepared_qty"] - result["sold_qty"]), errors="coerce").fillna(0).clip(lower=0)
    result["weather"] = result.get("weather", "unknown")
    result["event_name"] = result.get("event_name", "")
    result["footfall"] = pd.to_numeric(result.get("footfall", 0), errors="coerce").fillna(0)
    result["weekday"] = result["date"].dt.day_name()
    return result


def compute_baseline(frame: pd.DataFrame) -> dict[str, Any]:
    frame = frame.copy()
    total_prepared = float(frame["prepared_qty"].sum())
    total_sold = float(frame["sold_qty"].sum())
    total_waste = float(frame["waste_qty"].sum())
    waste_cost = float((frame["waste_qty"] * frame["unit_cost"]).sum())
    revenue = float((frame["sold_qty"] * frame["unit_price"]).sum())
    cost = float((frame["sold_qty"] * frame["unit_cost"]).sum())
    grouped = frame.groupby("dish_name", dropna=False)
    rows: list[dict[str, Any]] = []
    latest_date = frame["date"].max()
    for dish, group in grouped:
        recent = group[group["date"] >= latest_date - pd.Timedelta(days=7)]
        recent_mean = float(recent["sold_qty"].mean() if not recent.empty else group["sold_qty"].mean())
        same_weekday = group[group["weekday"] == latest_date.day_name()]
        weekday_mean = float(same_weekday["sold_qty"].mean() if not same_weekday.empty else recent_mean)
        baseline = round(0.65 * recent_mean + 0.35 * weekday_mean)
        low = math.ceil(float(group["sold_qty"].max()) * 0.8)
        high = math.ceil(float(group["sold_qty"].max()) * 1.2)
        baseline = max(low, min(high, baseline))
        avg_waste = float(group["waste_qty"].mean())
        sellout = float((group["sold_qty"] >= group["prepared_qty"] * 0.98).mean())
        rows.append({
            "dish_name": str(dish),
            "baseline_qty": baseline,
            "recent_avg_sold": round(recent_mean, 1),
            "waste_qty": round(float(group["waste_qty"].sum()), 1),
            "waste_cost": round(float((group["waste_qty"] * group["unit_cost"]).sum()), 2),
            "sellout_rate": round(sellout, 3),
            "avg_waste": round(avg_waste, 1),
        })
    rows.sort(key=lambda row: row["waste_cost"], reverse=True)
    return {
        "metrics": {
            "record_count": len(frame),
            "date_start": frame["date"].min().date().isoformat(),
            "date_end": frame["date"].max().date().isoformat(),
            "prepared_qty": int(total_prepared),
            "sold_qty": int(total_sold),
            "waste_qty": round(total_waste, 1),
            "waste_cost": round(waste_cost, 2),
            "waste_rate": round(total_waste / total_prepared if total_prepared else 0, 4),
            "sellout_rate": round(float((frame["sold_qty"] >= frame["prepared_qty"] * 0.98).mean()), 4),
            "estimated_saving": round(waste_cost * 0.22, 2),
            "gross_margin": round(revenue - cost, 2),
        },
        "dishes": rows,
        "top_waste": rows[:5],
        "weekday": frame.groupby("weekday")["waste_qty"].sum().round(1).to_dict(),
    }


def demo_frame() -> pd.DataFrame:
    path = Path(__file__).resolve().parents[1] / "data" / "demo.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        start = pd.Timestamp("2026-06-01")
        dishes = [("番茄炒蛋", 100, 8, 3), ("红烧茄子", 90, 7, 2.5), ("辣子鸡", 120, 12, 5), ("牛肉面", 80, 14, 6)]
        rows = []
        for day in range(30):
            date = start + pd.Timedelta(days=day)
            weather = "rainy" if day in {4, 11, 18, 25} else ("hot" if day % 7 in {2, 3} else "sunny")
            event = "社团活动" if day in {8, 22} else ""
            for meal in ["lunch", "dinner"]:
                for name, prepared, price, cost in dishes:
                    demand_factor = 1.12 if date.dayofweek in {4} else 1.0
                    demand_factor *= 1.08 if weather == "rainy" and name == "牛肉面" else 1.0
                    demand_factor *= 1.18 if event and name == "辣子鸡" else 1.0
                    sold = min(prepared, round(prepared * (0.78 + ((day * 7 + len(name)) % 17) / 100) * demand_factor))
                    if name == "红烧茄子":
                        sold = min(sold, prepared - 15)
                    rows.append({"date": date.date().isoformat(), "meal_period": meal, "dish_name": name, "prepared_qty": prepared, "sold_qty": sold, "unit_price": price, "unit_cost": cost, "weather": weather, "event_name": event, "footfall": 300 + (day % 5) * 15})
        pd.DataFrame(rows).to_csv(path, index=False)
    return read_table(path)
