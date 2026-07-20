from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Backend provider model discovery endpoint.
replace_once(
    "backend/agentcad/api_v2.py",
    "from .models import (\n",
    "from .models import (\n",
)
replace_once(
    "backend/agentcad/api_v2.py",
    "from .service import (\n",
    "from .provider_discovery import discover_provider_models\nfrom .service import (\n",
)
replace_once(
    "backend/agentcad/api_v2.py",
    "    @router.post(\"/agent/provider/test\")\n    def test_provider(request: ProviderConfig):\n",
    "    @router.post(\"/agent/provider/models\")\n"
    "    def list_provider_models(request: ProviderConfig):\n"
    "        started = perf_counter()\n"
    "        if diagnostics is not None:\n"
    "            diagnostics.emit(\n"
    "                \"llm.provider_models.started\",\n"
    "                base_url=request.base_url,\n"
    "                timeout_seconds=request.timeout_seconds,\n"
    "                api_key_present=bool(request.api_key),\n"
    "            )\n"
    "        try:\n"
    "            result = discover_provider_models(request)\n"
    "        except PlannerError as exc:\n"
    "            if diagnostics is not None:\n"
    "                diagnostics.emit(\n"
    "                    \"llm.provider_models.failed\",\n"
    "                    base_url=request.base_url,\n"
    "                    duration_ms=round((perf_counter() - started) * 1000, 2),\n"
    "                    error_code=exc.code,\n"
    "                    provider_status=exc.provider_status,\n"
    "                    error=exc,\n"
    "                )\n"
    "            raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc\n"
    "        if diagnostics is not None:\n"
    "            diagnostics.emit(\n"
    "                \"llm.provider_models.completed\",\n"
    "                base_url=result.get(\"base_url\"),\n"
    "                duration_ms=round((perf_counter() - started) * 1000, 2),\n"
    "                model_count=result.get(\"count\"),\n"
    "            )\n"
    "        return result\n\n"
    "    @router.post(\"/agent/provider/test\")\n"
    "    def test_provider(request: ProviderConfig):\n",
)

# Frontend API model list type and method.
replace_once(
    "frontend/src/api.ts",
    "export type DocumentStatus = { id: string; revision: number; updated_at: string };\n",
    "export type ProviderModelsResult = {\n"
    "  ok: boolean;\n"
    "  base_url: string;\n"
    "  models: Array<{ id: string; owned_by: string | null }>;\n"
    "  count: number;\n"
    "  latency_ms: number;\n"
    "};\n\n"
    "export type DocumentStatus = { id: string; revision: number; updated_at: string };\n",
)
replace_once(
    "frontend/src/api.ts",
    "  testProvider: (provider: ProviderConfig) => request<ProviderTestResult>(\"/agent/provider/test\", { method: \"POST\", body: JSON.stringify(provider) }),\n",
    "  listProviderModels: (provider: ProviderConfig) => request<ProviderModelsResult>(\"/agent/provider/models\", { method: \"POST\", body: JSON.stringify(provider) }),\n"
    "  testProvider: (provider: ProviderConfig) => request<ProviderTestResult>(\"/agent/provider/test\", { method: \"POST\", body: JSON.stringify(provider) }),\n",
)

# App provider presets, automatic model discovery and persistent Agent panel.
replace_once(
    "frontend/src/App.tsx",
    "import { api, ApiError, type ProviderConfig, type ProviderTestResult } from \"./api\";\n",
    "import { api, ApiError, type ProviderConfig, type ProviderTestResult } from \"./api\";\n"
    "import { PROVIDER_PRESETS, presetForBaseUrl } from \"./providerPresets\";\n",
)
replace_once(
    "frontend/src/App.tsx",
    "  const [providerTestError, setProviderTestError] = useState(\"\");\n",
    "  const [providerTestError, setProviderTestError] = useState(\"\");\n"
    "  const [providerPreset, setProviderPreset] = useState(\"custom\");\n"
    "  const [availableModels, setAvailableModels] = useState<Array<{ id: string; owned_by: string | null }>>([]);\n"
    "  const [loadingModels, setLoadingModels] = useState(false);\n"
    "  const [modelDiscoveryError, setModelDiscoveryError] = useState(\"\");\n",
)
replace_once(
    "frontend/src/App.tsx",
    "  const scopedContext = () => {\n",
    "  const selectProviderPreset = (presetId: string) => {\n"
    "    setProviderPreset(presetId);\n"
    "    const preset = PROVIDER_PRESETS.find((item) => item.id === presetId);\n"
    "    if (preset && preset.id !== \"custom\") setBaseUrl(preset.baseUrl);\n"
    "    if (presetId === \"custom\") setBaseUrl((current) => current);\n"
    "    setAvailableModels([]);\n"
    "    setModelDiscoveryError(\"\");\n"
    "    setProviderTest(null);\n"
    "  };\n\n"
    "  const discoverProviderModels = async (silent = false) => {\n"
    "    if (!baseUrl.trim()) return;\n"
    "    setLoadingModels(true);\n"
    "    setModelDiscoveryError(\"\");\n"
    "    try {\n"
    "      const result = await api.listProviderModels({\n"
    "        base_url: baseUrl.trim(),\n"
    "        api_key: apiKey.trim() || undefined,\n"
    "        timeout_seconds: timeoutSeconds,\n"
    "      });\n"
    "      setAvailableModels(result.models);\n"
    "      if (result.models.length) {\n"
    "        setModel((current) => result.models.some((item) => item.id === current) ? current : result.models[0].id);\n"
    "      } else if (!silent) {\n"
    "        setModelDiscoveryError(\"服务连接成功，但 /models 没有返回可用模型。仍可手工输入模型名称。\");\n"
    "      }\n"
    "    } catch (error) {\n"
    "      setAvailableModels([]);\n"
    "      setModelDiscoveryError(error instanceof ApiError ? error.message : String(error));\n"
    "    } finally {\n"
    "      setLoadingModels(false);\n"
    "    }\n"
    "  };\n\n"
    "  useEffect(() => {\n"
    "    const preset = PROVIDER_PRESETS.find((item) => item.id === providerPreset);\n"
    "    if (!baseUrl.trim() || (preset?.requiresApiKey && !apiKey.trim())) {\n"
    "      setAvailableModels([]);\n"
    "      return;\n"
    "    }\n"
    "    const timer = window.setTimeout(() => { void discoverProviderModels(true); }, 450);\n"
    "    return () => window.clearTimeout(timer);\n"
    "  }, [baseUrl, apiKey, providerPreset, timeoutSeconds]);\n\n"
    "  const scopedContext = () => {\n",
)
old_details = '''            <details>
              <summary>自定义模型 API（可选）</summary>
              <label>Base URL（可含自定义端口）<input value={baseUrl} onChange={(event: ChangeEvent<HTMLInputElement>) => setBaseUrl(event.target.value)} placeholder="例如 http://127.0.0.1:11434/v1" /></label>
              <label>Model<input value={model} onChange={(event: ChangeEvent<HTMLInputElement>) => setModel(event.target.value)} placeholder="qwen3-coder" /></label>
              <label>API Key<div className="secret-input-row"><input type={showApiKey ? "text" : "password"} value={apiKey} onChange={(event: ChangeEvent<HTMLInputElement>) => setApiKey(event.target.value)} placeholder="sk-...；本地无鉴权服务可留空" autoComplete="off" spellCheck={false} /><button type="button" onClick={() => setShowApiKey(!showApiKey)}>{showApiKey ? "隐藏" : "显示"}</button></div></label>
              <label>超时（秒）<input type="number" min={10} max={600} value={timeoutSeconds} onChange={(event: ChangeEvent<HTMLInputElement>) => setTimeoutSeconds(Math.min(600, Math.max(10, Number(event.target.value) || 120)))} /></label>
              <div className="provider-actions"><button type="button" onClick={() => void testCustomProvider()} disabled={testingProvider || !baseUrl.trim() || !model.trim()}>{testingProvider ? "正在测试…" : "测试连接"}</button></div>
              {providerTest ? <div className={`provider-test provider-test-${providerTest.model_available === false ? "warning" : "success"}`}><strong>{providerTest.message}</strong><span>{providerTest.model} · {providerTest.latency_ms} ms · {providerTest.method}</span></div> : null}
              {providerTestError ? <div className="provider-test provider-test-error">{providerTestError}</div> : null}
              <p>API Key 仅保存在当前页面内存，并随测试或生成请求发送，不写入数据库或浏览器存储。</p>
            </details>'''
new_details = '''            <details open>
              <summary>模型服务</summary>
              <label>服务预设<select value={providerPreset} onChange={(event: ChangeEvent<HTMLSelectElement>) => selectProviderPreset(event.target.value)}>{PROVIDER_PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}</select></label>
              <label>Base URL<input value={baseUrl} onChange={(event: ChangeEvent<HTMLInputElement>) => { setBaseUrl(event.target.value); setProviderPreset(presetForBaseUrl(event.target.value)); }} placeholder="例如 http://127.0.0.1:11434/v1" /></label>
              <label>API Key<div className="secret-input-row"><input type={showApiKey ? "text" : "password"} value={apiKey} onChange={(event: ChangeEvent<HTMLInputElement>) => setApiKey(event.target.value)} placeholder="只需输入当前服务的 API Key；本地服务可留空" autoComplete="off" spellCheck={false} /><button type="button" onClick={() => setShowApiKey(!showApiKey)}>{showApiKey ? "隐藏" : "显示"}</button></div></label>
              {loadingModels ? <div className="provider-model-status">正在读取模型列表…</div> : null}
              {availableModels.length ? <label>可用模型<select value={availableModels.some((item) => item.id === model) ? model : ""} onChange={(event: ChangeEvent<HTMLSelectElement>) => setModel(event.target.value)}><option value="" disabled>选择模型</option>{availableModels.map((item) => <option key={item.id} value={item.id}>{item.id}{item.owned_by ? ` · ${item.owned_by}` : ""}</option>)}</select></label> : null}
              <label>Model name（可手工覆盖）<input value={model} onChange={(event: ChangeEvent<HTMLInputElement>) => setModel(event.target.value)} placeholder="从列表选择，或直接输入模型名称" /></label>
              <label>超时（秒）<input type="number" min={10} max={600} value={timeoutSeconds} onChange={(event: ChangeEvent<HTMLInputElement>) => setTimeoutSeconds(Math.min(600, Math.max(10, Number(event.target.value) || 120)))} /></label>
              <div className="provider-actions"><button type="button" onClick={() => void discoverProviderModels()} disabled={loadingModels || !baseUrl.trim()}>{loadingModels ? "读取中…" : "刷新模型列表"}</button><button type="button" onClick={() => void testCustomProvider()} disabled={testingProvider || !baseUrl.trim() || !model.trim()}>{testingProvider ? "正在测试…" : "测试连接"}</button></div>
              {modelDiscoveryError ? <div className="provider-test provider-test-error">{modelDiscoveryError}</div> : null}
              {providerTest ? <div className={`provider-test provider-test-${providerTest.model_available === false ? "warning" : "success"}`}><strong>{providerTest.message}</strong><span>{providerTest.model} · {providerTest.latency_ms} ms · {providerTest.method}</span></div> : null}
              {providerTestError ? <div className="provider-test provider-test-error">{providerTestError}</div> : null}
              <p>预设只填写公开 Base URL。API Key 仅保存在当前页面内存，并随模型列表、测试或生成请求发送，不写入数据库或浏览器存储。</p>
            </details>'''
replace_once("frontend/src/App.tsx", old_details, new_details)
replace_once(
    "frontend/src/App.tsx",
    "          {rightPanel === \"agent\" ? <section className=\"agent-panel\" role=\"tabpanel\">\n",
    "          <section className=\"agent-panel\" role=\"tabpanel\" hidden={rightPanel !== \"agent\"}>\n",
)
replace_once(
    "frontend/src/App.tsx",
    "            <div className=\"agent-note\">自动完成会在服务端结构化校验失败后连续重规划，并在检测到重复错误或达到 5 次上限时停止。手动预览仍可用于审查每个语义操作。</div>\n          </section> : null}\n",
    "            <div className=\"agent-note\">自动完成会在服务端结构化校验失败后连续重规划，并在检测到重复错误或达到 5 次上限时停止。切换属性、图层或历史面板不会中断正在执行的请求。</div>\n          </section>\n",
)

# Grid-aware micro-dogleg collapse in semantic routes.
replace_once(
    "backend/agentcad/semantic_compiler_engine.py",
    "        normalized = self._normalize_waypoint_connector(compiled, operation)\n",
    "        normalized = self._normalize_waypoint_connector(\n"
    "            compiled, operation, document.canvas.grid_size\n"
    "        )\n",
)
replace_once(
    "backend/agentcad/semantic_compiler_engine.py",
    "        operation: ConnectPortsOperation,\n    ) -> list[Operation]:\n",
    "        operation: ConnectPortsOperation,\n        grid_size: float,\n    ) -> list[Operation]:\n",
)
replace_once(
    "backend/agentcad/semantic_compiler_engine.py",
    "            points = cls._orthogonalize_route(connector.points)\n",
    "            orthogonal = cls._orthogonalize_route(connector.points)\n"
    "            points = cls._collapse_micro_doglegs(\n"
    "                orthogonal, tolerance=max(2.0, grid_size)\n"
    "            )\n",
)
replace_once(
    "backend/agentcad/semantic_compiler_engine.py",
    '                "requested_waypoints": [\n                    point.model_dump(mode="json") for point in operation.waypoints\n                ],\n',
    '                "requested_waypoints": [\n                    point.model_dump(mode="json") for point in operation.waypoints\n                ],\n                "micro_dogleg_points_removed": max(0, len(orthogonal) - len(points)),\n',
)
insert_anchor = '''    @classmethod
    def _dedupe_route_points(cls, points: list[Point]) -> list[Point]:
'''
insert_method = '''    @classmethod
    def _collapse_micro_doglegs(cls, points: list[Point], tolerance: float) -> list[Point]:
        """Remove local orthogonal stair-steps while preserving larger intentional detours."""
        result = cls._simplify_collinear_route(cls._dedupe_route_points(points))
        changed = True
        while changed and len(result) >= 4:
            changed = False
            for start_index in range(len(result) - 3):
                max_end = min(len(result) - 1, start_index + 4)
                for end_index in range(max_end, start_index + 2, -1):
                    start = result[start_index]
                    end = result[end_index]
                    middle = result[start_index + 1 : end_index]
                    horizontal = (
                        abs(start.y - end.y) <= POINT_EPSILON
                        and all(abs(point.y - start.y) <= tolerance for point in middle)
                    )
                    vertical = (
                        abs(start.x - end.x) <= POINT_EPSILON
                        and all(abs(point.x - start.x) <= tolerance for point in middle)
                    )
                    if not horizontal and not vertical:
                        continue
                    replacement = Point(x=end.x, y=start.y) if horizontal else Point(x=start.x, y=end.y)
                    result = [
                        *result[: start_index + 1],
                        replacement,
                        *result[end_index + 1 :],
                    ]
                    result = cls._simplify_collinear_route(cls._dedupe_route_points(result))
                    changed = True
                    break
                if changed:
                    break
        return result

'''
replace_once(
    "backend/agentcad/semantic_compiler_engine.py",
    insert_anchor,
    insert_method + insert_anchor,
)
old_loop = '''        for compiled_operation in compiled:
            if not isinstance(compiled_operation, AddElementOperation):
                continue
            element = compiled_operation.element
            if element.type == "connector" and element.id in main_segment_ids:
                element.metadata["main_route_id"] = main_route_id
            if element.metadata.get("assembly") == "instrument_tap":
                element.metadata["parent_main_route_id"] = main_route_id
                element.metadata["main_connector_id"] = operation.main_connector_id
                element.metadata["split_segment_id"] = actual.id
'''
new_loop = '''        for compiled_index, compiled_operation in enumerate(compiled):
            if not isinstance(compiled_operation, AddElementOperation):
                continue
            element = compiled_operation.element.model_copy(deep=True)
            if element.type == "connector" and element.id in main_segment_ids:
                before_count = len(element.points)
                element.points = self._collapse_micro_doglegs(
                    element.points,
                    tolerance=max(2.0, document.canvas.grid_size),
                )
                element.metadata["main_route_id"] = main_route_id
                removed = before_count - len(element.points)
                if removed > 0:
                    element.metadata["micro_dogleg_points_removed"] = removed
            if element.metadata.get("assembly") == "instrument_tap":
                element.metadata["parent_main_route_id"] = main_route_id
                element.metadata["main_connector_id"] = operation.main_connector_id
                element.metadata["split_segment_id"] = actual.id
            compiled[compiled_index] = AddElementOperation(element=element)
'''
replace_once("backend/agentcad/semantic_compiler_engine.py", old_loop, new_loop)

# Minimal UI styling for provider discovery.
style_path = Path("frontend/src/issue1.css")
style = style_path.read_text(encoding="utf-8")
style += "\n.provider-model-status { border-radius: 6px; padding: 7px; color: #1d4ed8; background: #dbeafe; font-size: 10px; }\n.agent-panel[hidden] { display: none; }\n"
style_path.write_text(style, encoding="utf-8")
