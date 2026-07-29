from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .engine import DataValidationError, compute_baseline, demo_frame, read_table
from .infinisynapse import InfiniSynapseClient
from .models import AIResult, AnalysisStatus, ScenarioRequest
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("APP_DATA_DIR", str(ROOT / "storage")))
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
store = Store(DATA_ROOT)
client = InfiniSynapseClient()
app = FastAPI(title="惜食智备", version="0.1.0")


def _payload(analysis_id: str) -> dict[str, Any]:
    value = store.get(analysis_id)
    if not value:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return {"analysis_id": analysis_id, "metrics": value.get("baseline", {}).get("metrics", {}), **value}


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": "惜食智备", "infinisynapse_configured": client.configured}


@app.get("/api/demo")
def demo() -> dict[str, Any]:
    baseline = compute_baseline(demo_frame())
    return {"source": "某大学第二食堂 · 30 天演示数据", **baseline}


@app.get("/api/template.csv")
def template() -> Response:
    content = "date,meal_period,dish_name,prepared_qty,sold_qty,unit_price,unit_cost,waste_qty,weather,event_name,footfall\n2026-07-01,lunch,番茄炒蛋,100,92,8,3,8,sunny,,320\n"
    return Response(content=content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=xishizhibei-template.csv"})


@app.post("/api/datasets/validate")
async def validate_dataset(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    if not file.filename or Path(file.filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=422, detail="仅支持 CSV 或 XLSX 文件")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {MAX_UPLOAD // 1024 // 1024} MB")
    upload_id = uuid.uuid4().hex
    path = DATA_ROOT / f"upload-{upload_id}{Path(file.filename).suffix.lower()}"
    path.write_bytes(data)
    try:
        frame = read_table(path)
    except DataValidationError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"upload_id": upload_id, "filename": file.filename, "rows": len(frame), "columns": list(frame.columns), "preview": json.loads(frame.head(10).to_json(orient="records", date_format="iso")), "metrics": compute_baseline(frame)["metrics"]}


@app.post("/api/analyses")
async def create_analysis(upload_id: str | None = None, demo_mode: bool = True) -> dict[str, Any]:
    analysis_id = uuid.uuid4().hex
    if demo_mode or not upload_id:
        frame = demo_frame()
        source = ROOT / "data" / "demo.csv"
    else:
        source = next(DATA_ROOT.glob(f"upload-{upload_id}.*"), None)
        if source is None or not source.exists():
            raise HTTPException(status_code=404, detail="上传数据不存在")
        try:
            frame = read_table(source)
        except DataValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors) from exc
    payload = {"source_name": "演示数据" if demo_mode else source.name, "baseline": compute_baseline(frame), "result": None, "task_id": None, "error": None}
    store.create(analysis_id, payload)
    asyncio.create_task(_run_analysis(analysis_id, frame, source.name))
    return _payload(analysis_id)


async def _set_progress(analysis_id: str, frame, status: str, progress: int, message: str, extra: dict[str, Any] | None = None) -> None:
    current = store.get(analysis_id) or {}
    payload = {key: value for key, value in current.items() if key not in {"status", "progress", "message", "updated_at"}}
    if extra:
        payload.update(extra)
    store.update(analysis_id, AnalysisStatus(status), progress, message, payload)


def _fallback_result(baseline: dict[str, Any]) -> AIResult:
    dishes = []
    for row in baseline["dishes"]:
        delta = -max(2, round(row["waste_qty"] / 6)) if row["waste_qty"] > row["recent_avg_sold"] else max(2, round(row["sellout_rate"] * 8))
        recommended = max(0, row["baseline_qty"] + delta)
        maximum = round(row["baseline_qty"] * 1.2)
        minimum = round(row["baseline_qty"] * 0.8)
        recommended = max(minimum, min(maximum, recommended))
        dishes.append({"dish_name": row["dish_name"], "baseline_qty": row["baseline_qty"], "recommended_qty": recommended, "reason": "根据近 7 天销量、损耗与售罄情况生成安全范围内建议", "risk": "雨天或临时活动可能造成客流偏差"})
    top = baseline["top_waste"][0] if baseline["top_waste"] else {"dish_name": "暂无", "waste_cost": 0}
    return AIResult.model_validate({"executive_summary": f"当前数据的损耗成本约 ¥{baseline['metrics']['waste_cost']:.0f}；建议优先调整 {top['dish_name']} 的备餐量。", "key_findings": [{"title": "损耗集中在少数菜品", "evidence": f"{top['dish_name']} 的历史损耗成本最高", "metric": f"¥{top['waste_cost']:.0f}", "confidence": "medium"}], "dish_recommendations": dishes, "action_items": [{"priority": "high", "action": f"明日优先复核 {top['dish_name']} 的备餐量", "expected_impact": f"预计减少约 ¥{baseline['metrics']['estimated_saving']:.0f} 损耗"}, {"priority": "medium", "action": "午餐开餐后 40 分钟检查高波动菜品余量", "expected_impact": "降低提前售罄与临时补餐风险"}], "limitations": ["当前为本地基础分析；配置 API Key 后将补充 InfiniSynapse 深度归因。"]})


async def _run_analysis(analysis_id: str, frame, source_name: str) -> None:
    baseline = compute_baseline(frame)
    try:
        await _set_progress(analysis_id, frame, "COMPUTING_BASELINE", 20, "正在计算损耗、售罄和基础备餐量")
        await asyncio.sleep(0.1)
        prompt = f"你是食堂经营分析师。请读取附件 {source_name}，结合以下本地确定性结果进行复核：{json.dumps(baseline, ensure_ascii=False)}。必须在工作区生成 analysis_result.json 和 report.md。analysis_result.json 必须严格符合 executive_summary、key_findings、dish_recommendations、action_items、limitations 结构，所有推荐量只能在 baseline_qty 的 ±20% 内。解释星期、天气、活动和菜品需求关系，给出明日备餐及行动清单。"
        csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
        if client.configured:
            task_id, result, error = await client.analyze(csv_bytes, prompt, lambda status, progress, message: _set_progress(analysis_id, frame, status, progress, message))
            if result:
                await _set_progress(analysis_id, frame, "COMPLETED", 100, "分析完成", {"result": result.model_dump(mode="json"), "task_id": task_id, "error": None})
            else:
                fallback = _fallback_result(baseline)
                await _set_progress(analysis_id, frame, "PARTIAL", 100, "基础分析完成，InfiniSynapse 深度分析未完成", {"result": fallback.model_dump(mode="json"), "task_id": task_id, "error": error})
        else:
            fallback = _fallback_result(baseline)
            await _set_progress(analysis_id, frame, "PARTIAL", 100, "基础分析完成（未配置 API Key）", {"result": fallback.model_dump(mode="json"), "error": "未配置 INFINISYNAPSE_API_KEY"})
    except TimeoutError:
        await _set_progress(analysis_id, frame, "TIMED_OUT", 100, "分析超时", {"result": _fallback_result(baseline).model_dump(mode="json"), "error": "InfiniSynapse 请求超过 180 秒"})
    except Exception as exc:  # noqa: BLE001
        await _set_progress(analysis_id, frame, "PARTIAL", 100, "分析出现异常，已保留本地结果", {"result": _fallback_result(baseline).model_dump(mode="json"), "error": str(exc)})


@app.get("/api/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict[str, Any]:
    return _payload(analysis_id)


@app.post("/api/analyses/{analysis_id}/scenarios")
async def scenario(analysis_id: str, body: ScenarioRequest) -> dict[str, Any]:
    current = store.get(analysis_id)
    if not current:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    baseline = current.get("baseline", {})
    result = current.get("result") or _fallback_result(baseline).model_dump(mode="json")
    factor = 1.0
    if "下雨" in body.scenario:
        factor = 1.12
    elif "20%" in body.scenario:
        factor = 1.2
    elif "10%" in body.scenario:
        factor = 0.9
    for item in result.get("dish_recommendations", []):
        item["recommended_qty"] = round(item["recommended_qty"] * factor)
        item["reason"] = f"情景「{body.scenario}」下按 {factor:.0%} 需求系数调整"
    result["executive_summary"] = f"情景模拟：{body.scenario}。已根据需求系数 {factor:.0%} 重新计算备餐建议。"
    current["result"] = result
    current["scenario"] = body.scenario
    store.update(analysis_id, AnalysisStatus(current["status"]), current["progress"], "情景模拟完成", {key: value for key, value in current.items() if key not in {"status", "progress", "message", "updated_at"}})
    return _payload(analysis_id)


@app.get("/api/analyses/{analysis_id}/report")
def report(analysis_id: str) -> Response:
    current = _payload(analysis_id)
    result = current.get("result") or {}
    text = f"# 惜食智备分析报告\n\n## 摘要\n{result.get('executive_summary', '')}\n\n## 关键发现\n" + "\n".join(f"- **{item['title']}**：{item['evidence']}（{item['metric']}）" for item in result.get("key_findings", [])) + "\n\n## 明日行动\n" + "\n".join(f"- [{item['priority']}] {item['action']}：{item['expected_impact']}" for item in result.get("action_items", []))
    return Response(content=text, media_type="text/markdown", headers={"Content-Disposition": f"attachment; filename={analysis_id}.md"})


@app.get("/api/analyses/{analysis_id}/downloads/{format}")
def download(analysis_id: str, format: str) -> Response:
    current = _payload(analysis_id)
    if format == "json":
        return JSONResponse(current)
    if format == "md":
        return report(analysis_id)
    raise HTTPException(status_code=404, detail="仅支持 md 或 json")


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        return FileResponse(candidate if candidate.is_file() and dist.resolve() in candidate.parents else dist / "index.html")
