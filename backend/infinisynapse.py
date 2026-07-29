from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any

import httpx

from .models import AIResult


class InfiniSynapseClient:
    def __init__(self) -> None:
        self.base = os.getenv("INFINISYNAPSE_BASE_URL", "https://app.infinisynapse.cn").rstrip("/")
        self.key = os.getenv("INFINISYNAPSE_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}", "x-lang": "zh_CN"}

    async def analyze(self, csv_bytes: bytes, prompt: str, on_progress) -> tuple[str, AIResult | None, str | None]:
        if not self.configured:
            return "", None, "未配置 INFINISYNAPSE_API_KEY"
        task_id, conn_id = str(uuid.uuid4()), str(uuid.uuid4())
        timeout = httpx.Timeout(180.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            upload = await client.post(
                f"{self.base}/api/tools/taskUpload/{task_id}?subdir=upload_documents&naming=original",
                headers=self.headers(), files={"file": ("cafeteria.csv", csv_bytes, "text/csv")},
            )
            upload.raise_for_status()
            uploaded = upload.json().get("data", upload.json())
            await on_progress("UPLOADING", 35, "数据已上传，等待分析引擎")
            files = [{"name": uploaded.get("name", "cafeteria.csv"), "size": uploaded.get("size", len(csv_bytes)), "type": "text/csv", "logicalPath": uploaded.get("logicalPath", "upload_documents/cafeteria.csv"), "fileType": "data", "assetId": uploaded.get("assetId")}]
            await on_progress("CONNECTING", 42, "正在连接 InfiniSynapse 分析流")
            event_url = f"{self.base}/api/ai/events?connId={conn_id}"
            message_url = f"{self.base}/api/ai/message"
            async with client.stream("GET", event_url, headers={**self.headers(), "Accept": "text/event-stream"}) as _events:
                created = await client.post(message_url, headers={**self.headers(), "Content-Type": "application/json"}, json={"type": "newTask", "taskId": task_id, "connId": conn_id, "text": prompt, "files": files, "images": [], "autoApprovalSettings": {"maxRequests": 1000, "maxSubAgentRequests": 500, "databaseReturnLimit": 200, "delegateMaxConcurrency": 5, "enableNotifications": True, "debugMode": False, "enableWebSearch": False, "enableReadImage": False, "enableBrowser": False, "enableNativeToolCalling": True}, "chatSettings": {"mode": "act"}})
                if not created.is_success:
                    detail = created.text[:300].replace("\n", " ")
                    return task_id, None, f"创建 InfiniSynapse 任务失败（HTTP {created.status_code}）：{detail}"
                await on_progress("ANALYZING", 50, "InfiniSynapse 正在识别损耗原因和需求模式")
                # 保持 SSE 连接满足官方推荐链路，同时用任务消息接口做恢复性轮询。
                # 某些代理会缓冲 SSE 空行，单纯等待 SSE 会让任务看似永久停在分析中。
                completed = False
                for _ in range(36):
                    messages = await client.get(f"{self.base}/api/ai_task/getUiMessageById?id={task_id}", headers=self.headers())
                    raw_messages = messages.text if messages.is_success else ""
                    if "completion_result" in raw_messages:
                        completed = True
                        break
                    if '"type":"error"' in raw_messages or '"type": "error"' in raw_messages:
                        return task_id, None, "InfiniSynapse 返回分析错误"
                    await asyncio.sleep(5)
                if not completed:
                    return task_id, None, "InfiniSynapse 任务超过 180 秒仍未返回完成事件"
            await on_progress("READING_RESULTS", 88, "正在读取分析报告")
            workspace = await client.get(f"{self.base}/api/ai_task/getTaskWorkspace/{task_id}", headers=self.headers())
            workspace.raise_for_status()
            files_found = workspace.json().get("data", workspace.json()).get("files", [])
            for item in files_found:
                name = item.get("path", item.get("name", ""))
                if name.endswith("analysis_result.json"):
                    preview = await client.post(f"{self.base}/api/ai_task/previewFile", headers={**self.headers(), "Content-Type": "application/json"}, json={"taskId": task_id, "fileName": name})
                    if preview.is_success:
                        value = preview.json().get("data", preview.json()).get("content", "")
                        parsed = _extract_json(value)
                        if parsed:
                            return task_id, AIResult.model_validate(parsed), None
            return task_id, None, "任务完成但未找到符合契约的 analysis_result.json"


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None
