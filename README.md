# 惜食智备

让每一份备餐都有数据依据。一个面向校园食堂、小餐馆和团餐经营者的 AI 备餐减损助手。

## 本地启动

```bash
cd xishizhibei
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn backend.app:app --reload --port 8000
```

前端开发：

```bash
cd frontend
npm install
npm run dev
```

没有配置 `INFINISYNAPSE_API_KEY` 时，应用仍会运行本地确定性分析，并明确显示“基础分析”；配置 Key 后才会走真实 Server API 链路。

## Docker 部署

```bash
cp .env.example .env
# 在 .env 写入 INFINISYNAPSE_API_KEY
docker compose up --build -d
```

打开 `http://localhost:8000`。部署时为 `/app/storage` 挂载持久化磁盘。

## 比赛材料

完整的接口、数据契约、InfiniSynapse 调用流程、验收清单和 Demo 台词见 [XiShiZhiBei_MVP_Implementation_Spec_CN.md](XiShiZhiBei_MVP_Implementation_Spec_CN.md)。
