import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import './thinking.css';

type Dish = { dish_name: string; baseline_qty: number; recommended_qty?: number; waste_cost: number; waste_qty: number; sellout_rate: number; reason?: string; risk?: string };
type Analysis = { analysis_id: string; status: string; progress: number; message: string; metrics: Record<string, number | string>; baseline: { dishes?: Dish[]; weekday?: Record<string, number> }; result?: { executive_summary: string; key_findings: { title: string; evidence: string; metric: string; confidence: string }[]; dish_recommendations: Dish[]; action_items: { priority: string; action: string; expected_impact: string }[]; limitations: string[] }; task_id?: string; error?: string };

const money = (value: unknown) => `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`;

function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [view, setView] = useState<'home' | 'workspace'>('home');
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [fileMessage, setFileMessage] = useState('');
  const [scenario, setScenario] = useState('');

  useEffect(() => {
    if (!analysis || ['COMPLETED', 'PARTIAL', 'FAILED', 'TIMED_OUT'].includes(analysis.status)) return;
    const timer = window.setInterval(async () => setAnalysis(await (await fetch(`/api/analyses/${analysis.analysis_id}`)).json()), 2000);
    return () => window.clearInterval(timer);
  }, [analysis]);

  const start = async (demo = true) => {
    const query = demo ? '?demo_mode=true' : `?demo_mode=false&upload_id=${uploadId}`;
    const response = await fetch(`/api/analyses${query}`, { method: 'POST' });
    if (!response.ok) { setFileMessage('无法创建分析任务，请先完成数据校验。'); return; }
    setAnalysis(await response.json()); setView('workspace');
  };

  const validate = async (file: File) => {
    const form = new FormData(); form.append('file', file);
    setFileMessage('正在校验数据…');
    const response = await fetch('/api/datasets/validate', { method: 'POST', body: form });
    const body = await response.json();
    if (!response.ok) { setFileMessage(typeof body.detail === 'string' ? body.detail : '字段校验未通过，请下载模板核对。'); return; }
    setUploadId(body.upload_id); setFileMessage(`已通过校验：${body.rows} 条记录，可开始分析。`);
  };

  const thinkingText = (status?: string) => ({
    VALIDATING: '正在检查你的经营数据',
    COMPUTING_BASELINE: '正在计算损耗、售罄和基础备餐量',
    UPLOADING: '正在把数据安全交给分析引擎',
    CONNECTING: '正在连接 InfiniSynapse',
    ANALYZING: '正在识别星期、天气和菜品需求关系',
    READING_RESULTS: '正在整理明日备餐建议',
  } as Record<string, string>)[status || ''] || '正在组织分析结果';

  const runScenario = async (value: string) => {
    if (!analysis) return; setScenario(value);
    const response = await fetch(`/api/analyses/${analysis.analysis_id}/scenarios`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scenario: value }) });
    setAnalysis(await response.json());
  };

  if (view === 'home') return <main className="shell"><nav><span className="logo">惜食智备</span><span className="nav-note">Data-backed kitchen decisions</span></nav><section className="hero"><div><p className="eyebrow">AI 备餐减损助手</p><h1>让每一份备餐<br/><em>都有数据依据</em></h1><p className="lead">上传销售、备餐和损耗数据，找出浪费原因，生成明天每道菜该准备多少份。</p><div className="actions"><button className="primary" onClick={() => start(true)}>使用演示数据 →</button><label className="secondary">上传经营数据<input type="file" accept=".csv,.xlsx" onChange={e => e.target.files?.[0] && validate(e.target.files[0])}/></label></div>{fileMessage && <p className="file-message">{fileMessage}{uploadId && <button className="link" onClick={() => start(false)}>开始分析</button>}</p>}</div><div className="hero-card"><span>明日建议</span><strong>少备 36 份</strong><small>预计减少浪费 <b>¥427</b></small><div className="mini-bars"><i style={{height:'72%'}}/><i style={{height:'42%'}}/><i style={{height:'57%'}}/><i style={{height:'31%'}}/><i style={{height:'48%'}}/></div><small>损耗趋势 · 近 7 天</small></div></section><section className="value-grid"><Value title="减少浪费" text="识别长期多备和异常损耗菜品" icon="↘"/><Value title="降低成本" text="把损耗换算成每天可节省金额" icon="¥"/><Value title="避免售罄" text="结合星期、天气和活动调整备餐" icon="✓"/></section><footer>本地基础计算 + InfiniSynapse 深度分析 · 建议仅供经营决策参考</footer></main>;

  const metrics = analysis?.metrics || {};
  const dishes = analysis?.result?.dish_recommendations || analysis?.baseline?.dishes || [];
  const weekday = Object.entries(analysis?.baseline?.weekday || {});
  return <main className="shell workspace"><nav><button className="back" onClick={() => setView('home')}>← 惜食智备</button><span className="status"><i className={analysis?.status === 'COMPLETED' ? 'green' : 'amber'} />{analysis?.message}</span></nav><header className="workspace-head"><div><p className="eyebrow">某大学第二食堂 · 分析工作台</p><h2>明日，厨房应该准备什么？</h2></div><div className="task-id">{analysis?.task_id ? `InfiniSynapse Task · ${analysis.task_id.slice(0, 8)}…` : '本地基础分析'}</div></header>{analysis?.status !== 'COMPLETED' && analysis?.status !== 'PARTIAL' && <div className="progress"><div style={{width:`${analysis?.progress || 0}%`}}/><span>{analysis?.progress || 0}%</span></div>}<section className="metric-grid"><Metric label="损耗成本" value={money(metrics.waste_cost)} tone="red"/><Metric label="损耗率" value={`${(Number(metrics.waste_rate || 0) * 100).toFixed(1)}%`} tone="red"/><Metric label="售罄率" value={`${(Number(metrics.sellout_rate || 0) * 100).toFixed(1)}%`} tone="green"/><Metric label="预计可节省" value={money(metrics.estimated_saving)} tone="blue"/></section><section className="content-grid"><div className="panel chart-panel"><div className="panel-title"><h3>损耗集中在哪些菜？</h3><span>按成本排序</span></div>{(analysis?.baseline?.dishes || []).slice(0, 5).map((dish, index) => <div className="bar-row" key={dish.dish_name}><label>{dish.dish_name}</label><div className="bar"><i style={{width:`${Math.max(8, Math.min(100, dish.waste_cost / Number(metrics.waste_cost || 1) * 100))}%`}}/></div><b>{money(dish.waste_cost)}</b><small>{index + 1}</small></div>)}<div className="weekday"><span>星期损耗</span>{weekday.map(([day, value]) => <div key={day}><i style={{height:`${Math.max(8, Math.min(100, Number(value) / Math.max(...weekday.map(x => Number(x[1])), 1) * 100))}%`}}/><small>{day.slice(0, 3)}</small></div>)}</div></div><div className="panel insight-panel"><div className="panel-title"><h3>AI 发现</h3><span className="badge">{analysis?.status === 'COMPLETED' ? 'InfiniSynapse' : '基础分析'}</span></div><p className="summary">{analysis?.result?.executive_summary || '分析完成后，这里会显示损耗原因和备餐策略。'}</p>{(analysis?.result?.key_findings || []).map(item => <div className="finding" key={item.title}><b>{item.title}</b><span>{item.evidence}</span><em>{item.metric}</em></div>)}</div></section><section className="panel plan-panel"><div className="panel-title"><div><h3>明日备餐计划</h3><span>建议量已限制在基础量 ±20% 安全范围内</span></div><div className="scenario-buttons"><button onClick={() => runScenario('下雨')}>下雨</button><button onClick={() => runScenario('客流 +20%')}>客流 +20%</button><button onClick={() => runScenario('预算 -10%')}>预算 -10%</button></div></div>{scenario && <p className="scenario-note">当前情景：{scenario}</p>}<div className="table"><div className="tr th"><span>菜品</span><span>原计划</span><span>建议备餐</span><span>调整</span><span>原因</span></div>{dishes.map(dish => <div className="tr" key={dish.dish_name}><span><b>{dish.dish_name}</b><small>{dish.risk || '按历史数据分析'}</small></span><span>{dish.baseline_qty}</span><span className="recommend">{dish.recommended_qty ?? dish.baseline_qty}</span><span className={(dish.recommended_qty || dish.baseline_qty) < dish.baseline_qty ? 'down' : 'up'}>{(dish.recommended_qty ?? dish.baseline_qty) - dish.baseline_qty > 0 ? '+' : ''}{(dish.recommended_qty ?? dish.baseline_qty) - dish.baseline_qty}</span><span>{dish.reason || '等待 AI 深度分析'}</span></div>)}</div></section><section className="bottom-grid"><div className="panel"><div className="panel-title"><h3>今日行动清单</h3></div>{(analysis?.result?.action_items || []).map(item => <div className="action" key={item.action}><b className={item.priority}>{item.priority}</b><span>{item.action}<small>{item.expected_impact}</small></span></div>)}</div><div className="panel report-card"><h3>带走这份分析</h3><p>把明日备餐建议、证据和行动清单保存下来。</p><a href={`/api/analyses/${analysis?.analysis_id}/downloads/md`}>下载 Markdown 报告 ↗</a><a href={`/api/analyses/${analysis?.analysis_id}/downloads/json`}>下载结构化 JSON ↗</a></div></section><footer>任务状态：{analysis?.status} · {analysis?.error || '数据仅用于演示，不构成精确预测'}</footer></main>;
}

function Value({title, text, icon}: {title: string; text: string; icon: string}) { return <div className="value"><span>{icon}</span><div><b>{title}</b><p>{text}</p></div></div>; }
function Metric({label, value, tone}: {label:string; value:string; tone:string}) { return <div className={`metric ${tone}`}><span>{label}</span><strong>{value}</strong></div>; }

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
