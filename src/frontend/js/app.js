/**
 * AgentCAD 前端应用 v4 — 修复版
 * 
 * 修复：
 * - e_shiftPressed 不再依赖全局 event
 * - 符号正确渲染（position/offset 修正）
 * - 图元 ID 字段统一
 * - 符号库面板正确显示
 * - 拖拽放置正常工作
 */

(function () {
    "use strict";

    // ==================== 状态 ====================
    var state = {
        currentTool: "line",
        color: "black",
        linewidth: 1.0,
        layer: "default",
        
        // 视图变换
        viewOffsetX: 0,
        viewOffsetY: 0,
        viewScale: 1,
        
        // 绘制状态
        isDrawing: false,
        startPoint: null,
        tempPoints: [],
        
        // 编辑状态
        selectedIds: new Set(),
        isDragging: false,
        dragStartX: 0,
        dragStartY: 0,
        
        // 框选
        isBoxSelecting: false,
        boxSelectStart: null,
        boxSelectEnd: null,
        
        // 平移
        isPanning: false,
        panStartX: 0,
        panStartY: 0,
        panOffsetStartX: 0,
        panOffsetStartY: 0,
        
        // 图元数据
        primitives: [],
        history: [],
        redoStack: [],
        
        // 设置
        gridSize: 20,
        snapToGrid: true,
        
        // 符号库
        stencilPanelVisible: false,
        symbolLibrary: null,
        
        // 最后点击位置（用于文字）
        lastClickPos: null,
    };

    // ==================== DOM 引用 ====================
    var canvas = document.getElementById("cad-canvas");
    var ctx = canvas.getContext("2d");
    var coordDisplay = document.getElementById("coord-display");
    var statusMessage = document.getElementById("status-message");
    var statusHelp = document.getElementById("status-help");

    // ==================== 初始化 ====================
    function init() {
        bindEvents();
        refreshLayers();
        updateStats();
        setStatus("就绪 — 选择工具开始绘图");
        loadPrimitives();
        loadSymbolLibrary();
        redrawAll();
    }

    // ==================== 加载符号库 ====================
    function loadSymbolLibrary() {
        fetch("/api/v1/symbols/library")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success && data.data) {
                    state.symbolLibrary = data.data;
                    renderStencilPalette();
                }
            })
            .catch(function(e) {
                console.warn("符号库加载失败:", e);
            });
    }

    // ==================== 渲染符号面板 ====================
    function renderStencilPalette() {
        var container = document.getElementById("stencil-categories");
        if (!container || !state.symbolLibrary) return;
        container.innerHTML = "";

        var categories = state.symbolLibrary.categories || {};
        var names = state.symbolLibrary.names || {};
        var symbols = state.symbolLibrary.symbols || {};

        var catNames = Object.keys(categories);
        for (var ci = 0; ci < catNames.length; ci++) {
            var catName = catNames[ci];
            var symbolTypes = categories[catName];

            var catDiv = document.createElement("div");
            catDiv.className = "stencil-category";

            var header = document.createElement("div");
            header.className = "stencil-category-header";
            header.innerHTML = '<span>' + catName + '</span><span class="arrow">▼</span>';

            var itemsDiv = document.createElement("div");
            itemsDiv.className = "stencil-category-items";

            header.addEventListener("click", function() {
                header.classList.toggle("collapsed");
                itemsDiv.classList.toggle("collapsed");
            });

            for (var si = 0; si < symbolTypes.length; si++) {
                (function(stype) {
                    var item = document.createElement("div");
                    item.className = "stencil-item";
                    item.draggable = true;
                    item.dataset.symbolType = stype;

                    // 缩略图
                    var thumbCanvas = document.createElement("canvas");
                    thumbCanvas.width = 40;
                    thumbCanvas.height = 40;
                    drawSymbolThumbnail(thumbCanvas.getContext("2d"), stype, 40, 40);
                    item.appendChild(thumbCanvas);

                    // 名称
                    var labelSpan = document.createElement("span");
                    labelSpan.textContent = names[stype] || stype;
                    item.appendChild(labelSpan);

                    // 拖拽事件
                    item.addEventListener("dragstart", function(e) {
                        state.draggingSymbol = stype;
                        e.dataTransfer.setData("text/plain", stype);
                        e.dataTransfer.effectAllowed = "copy";
                    });
                    item.addEventListener("dragend", function() {
                        state.draggingSymbol = null;
                    });

                    itemsDiv.appendChild(item);
                })(symbolTypes[si]);
            }

            catDiv.appendChild(header);
            catDiv.appendChild(itemsDiv);
            container.appendChild(catDiv);
        }

        // 画布接受放置
        var canvasContainer = document.querySelector(".canvas-container");
        if (canvasContainer) {
            canvasContainer.addEventListener("dragover", function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
            });
            canvasContainer.addEventListener("drop", function(e) {
                e.preventDefault();
                var symbolType = e.dataTransfer.getData("text/plain");
                if (!symbolType || !state.symbolLibrary) return;

                var rect = canvas.getBoundingClientRect();
                var sx = e.clientX - rect.left;
                var sy = e.clientY - rect.top;
                var worldPos = screenToWorld(sx, sy);

                var symInfo = symbols[symbolType];
                var w = symInfo ? symInfo.width : 60;
                var h = symInfo ? symInfo.height : 60;

                createIndustrialSymbol(symbolType, worldPos[0] - w / 2, worldPos[1] - h / 2);
            });
        }
    }

    // ==================== 绘制符号缩略图 ====================
    function drawSymbolThumbnail(ctx, symbolType, w, h) {
        ctx.clearRect(0, 0, w, h);
        ctx.strokeStyle = "#333";
        ctx.lineWidth = 1.5;
        ctx.fillStyle = "none";

        var cx = w / 2, cy = h / 2;

        switch (symbolType) {
            case "ball_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy); ctx.lineTo(cx - 8, cy);
                ctx.lineTo(cx + 8, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 8, 2); ctx.lineTo(cx, cy); ctx.lineTo(cx - 8, h - 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx + 8, 2); ctx.lineTo(cx, cy); ctx.lineTo(cx + 8, h - 2);
                ctx.stroke();
                break;
            case "butterfly_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy); ctx.lineTo(cx - 10, cy);
                ctx.lineTo(cx + 10, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 10, 2); ctx.lineTo(cx, cy); ctx.lineTo(cx - 10, h - 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx + 10, 2); ctx.lineTo(cx, cy); ctx.lineTo(cx + 10, h - 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(cx, cy, 4, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case "check_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy); ctx.lineTo(cx - 5, cy);
                ctx.lineTo(cx + 5, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 5, 2); ctx.lineTo(w - 4, cy); ctx.lineTo(cx - 5, h - 2);
                ctx.stroke();
                break;
            case "globe_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy); ctx.lineTo(cx - 5, cy);
                ctx.lineTo(cx + 5, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 5, h * 0.3); ctx.lineTo(cx, cy); ctx.lineTo(cx - 5, h * 0.7);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx + 5, h * 0.3); ctx.lineTo(cx, cy); ctx.lineTo(cx + 5, h * 0.7);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 8, h * 0.25 - 4); ctx.lineTo(cx + 8, h * 0.25 - 4);
                ctx.stroke();
                break;
            case "gate_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy); ctx.lineTo(cx - 5, cy);
                ctx.lineTo(cx + 5, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 5, 2); ctx.lineTo(cx, cy); ctx.lineTo(cx - 5, h - 2);
                ctx.lineTo(cx + 5, 2); ctx.closePath();
                ctx.stroke();
                break;
            case "control_valve":
                ctx.beginPath();
                ctx.moveTo(4, cy + 10); ctx.lineTo(cx - 5, cy + 10);
                ctx.lineTo(cx + 5, cy + 10); ctx.lineTo(w - 4, cy + 10);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 5, cy + 3); ctx.lineTo(cx, cy + 10); ctx.lineTo(cx - 5, cy + 17);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx + 5, cy + 3); ctx.lineTo(cx, cy + 10); ctx.lineTo(cx + 5, cy + 17);
                ctx.stroke();
                ctx.strokeRect(cx - 10, 2, 20, cy + 1);
                break;
            case "temperature_indicator":
            case "pressure_indicator":
            case "flow_indicator":
                ctx.beginPath();
                ctx.arc(cx, cy, w / 2 - 3, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case "gas_tank":
                ctx.beginPath();
                ctx.arc(cx, h * 0.25, w / 2 - 6, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(w / 2 - 6, h * 0.25); ctx.lineTo(w / 2 - 6, h * 0.75);
                ctx.moveTo(w / 2 + 6, h * 0.25); ctx.lineTo(w / 2 + 6, h * 0.75);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(cx, h * 0.75, w / 2 - 6, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case "buffer_tank":
                ctx.beginPath();
                ctx.moveTo(w * 0.25, h * 0.2); ctx.lineTo(w * 0.75, h * 0.2);
                ctx.moveTo(w * 0.25, h * 0.8); ctx.lineTo(w * 0.75, h * 0.8);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(w * 0.25, h / 2, h / 2 - 4, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(w * 0.75, h / 2, h / 2 - 4, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case "purification_cabinet":
                ctx.strokeRect(4, 4, w - 8, h - 8);
                ctx.beginPath();
                ctx.moveTo(w / 3, 4); ctx.lineTo(w / 3, h - 4);
                ctx.moveTo(2 * w / 3, 4); ctx.lineTo(2 * w / 3, h - 4);
                ctx.stroke();
                break;
            case "centrifugal_pump":
                ctx.beginPath();
                ctx.arc(cx, cy, w / 2 - 6, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx - 4, 2); ctx.lineTo(cx + 4, h * 0.4);
                ctx.moveTo(2, cy); ctx.lineTo(cx - 4, cy);
                ctx.stroke();
                break;
            case "reciprocating_pump":
                ctx.beginPath();
                ctx.moveTo(10, h * 0.3); ctx.lineTo(w - 10, cy); ctx.lineTo(10, h * 0.7);
                ctx.closePath();
                ctx.stroke();
                ctx.beginPath();
                ctx.arc(cx, cy, 6, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case "fan":
                ctx.beginPath();
                ctx.arc(cx, cy, w / 2 - 6, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx, 4); ctx.lineTo(cx, h - 4);
                ctx.moveTo(4, cy); ctx.lineTo(w - 4, cy);
                ctx.stroke();
                break;
            case "high_temp_fan":
                ctx.strokeRect(6, 6, w - 12, h - 12);
                ctx.beginPath();
                ctx.arc(cx, cy, w / 2 - 14, 0, Math.PI * 2);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(cx, 6 + (h - 12) / 2 - (w - 28) / 2);
                ctx.lineTo(cx, 6 + (h - 12) / 2 + (w - 28) / 2);
                ctx.moveTo(6 + (w - 12) / 2 - (h - 28) / 2, cy);
                ctx.lineTo(6 + (w - 12) / 2 + (h - 28) / 2, cy);
                ctx.stroke();
                break;
            case "exhaust_cabinet":
                ctx.strokeRect(4, 4, w - 8, h - 8);
                break;
            case "control_cabinet":
                ctx.strokeRect(4, 4, w - 8, h - 8);
                ctx.strokeRect(8, 8, w - 16, h * 0.4);
                break;
            case "system_interface":
                ctx.strokeRect(4, 4, w * 0.55, h - 8);
                ctx.beginPath();
                ctx.moveTo(w * 0.55, 4); ctx.lineTo(w - 4, h / 2); ctx.lineTo(w * 0.55, h - 4);
                ctx.closePath();
                ctx.stroke();
                break;
        }
    }

    // ==================== 创建工业符号 ====================
    function createIndustrialSymbol(symbolType, x, y) {
        fetch("/api/v1/draw/symbol", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                symbol_type: symbolType,
                x: x,
                y: y,
                label: state.symbolLibrary ? (state.symbolLibrary.names[symbolType] || "") : "",
                color: state.color,
                linewidth: state.linewidth,
                layer: state.layer,
            }),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success && data.data) {
                state.primitives.push(data.data);
                updateStats();
                redrawAll();
                var names = state.symbolLibrary ? state.symbolLibrary.names : {};
                setStatus("已放置符号: " + (names[symbolType] || symbolType));
            }
        })
        .catch(function(e) {
            console.error("创建符号失败:", e);
            setStatus("创建符号失败");
        });
    }

    // ==================== 事件绑定 ====================
    function bindEvents() {
        // 工具按钮
        var tools = ["line", "circle", "rect", "polyline", "arc", "text", "select"];
        for (var i = 0; i < tools.length; i++) {
            var btn = document.getElementById("btn-" + tools[i]);
            if (btn) btn.addEventListener("click", (function(t) { return function() { switchTool(t); }; })(tools[i]));
        }

        // 符号库面板切换
        var stencilBtn = document.getElementById("btn-stencil-toggle");
        if (stencilBtn) stencilBtn.addEventListener("click", toggleStencilPanel);

        // 操作按钮
        document.getElementById("btn-undo").addEventListener("click", undo);
        document.getElementById("btn-redo").addEventListener("click", redo);
        document.getElementById("btn-clear").addEventListener("click", clearCanvas);
        document.getElementById("btn-export-svg").addEventListener("click", exportSVG);
        document.getElementById("btn-add-layer").addEventListener("click", addLayer);

        // 属性
        document.getElementById("prop-color").addEventListener("change", function(e) {
            state.color = e.target.value;
        });
        document.getElementById("prop-linewidth").addEventListener("input", function(e) {
            state.linewidth = parseFloat(e.target.value);
            document.getElementById("prop-linewidth-val").textContent = state.linewidth.toFixed(1);
        });

        // Canvas 鼠标事件
        canvas.addEventListener("mousedown", onMouseDown);
        canvas.addEventListener("mousemove", onMouseMove);
        canvas.addEventListener("mouseup", onMouseUp);
        canvas.addEventListener("dblclick", onDblClick);
        canvas.addEventListener("wheel", onWheel, { passive: false });
        canvas.addEventListener("contextmenu", onContextMenu);
        canvas.addEventListener("mouseleave", function() {
            state.isDragging = false;
        });

        // 键盘事件
        document.addEventListener("keydown", onKeyDown);

        // 文字弹窗
        document.getElementById("text-confirm").addEventListener("click", confirmText);
        document.getElementById("text-cancel").addEventListener("click", closeModal);
        document.getElementById("text-input").addEventListener("keydown", function(e) {
            if (e.key === "Enter") confirmText();
        });
    }

    // ==================== 符号库面板切换 ====================
    function toggleStencilPanel() {
        state.stencilPanelVisible = !state.stencilPanelVisible;
        var panel = document.getElementById("stencil-panel");
        var btn = document.getElementById("btn-stencil-toggle");
        if (panel) {
            if (state.stencilPanelVisible) {
                panel.classList.remove("hidden");
            } else {
                panel.classList.add("hidden");
            }
        }
        if (btn) {
            btn.classList.toggle("active", state.stencilPanelVisible);
        }
    }

    // ==================== 工具切换 ====================
    function switchTool(tool) {
        state.currentTool = tool;
        state.isDrawing = false;
        state.isDragging = false;
        state.startPoint = null;
        state.tempPoints = [];

        if (tool === "select") {
            state.selectedIds.clear();
        }

        document.querySelectorAll(".tool-btn").forEach(function(btn) { btn.classList.remove("active"); });
        var btn = document.getElementById("btn-" + tool);
        if (btn) btn.classList.add("active");

        var hints = {
            line: "点击起点，再点击终点 | 空格拖拽平移 | 滚轮缩放",
            circle: "点击圆心，再点击圆周上的点",
            rect: "点击左上角，再点击右下角",
            polyline: "连续点击添加顶点，双击或右键闭合",
            arc: "点击圆心，点击半径，设定角度",
            text: "点击放置文字",
            select: "点击选中图元，拖拽移动，Shift多选",
        };
        setStatus(hints[tool] || "");
    }

    // ==================== 坐标变换 ====================
    function screenToWorld(sx, sy) {
        return [
            (sx - state.viewOffsetX) / state.viewScale,
            (sy - state.viewOffsetY) / state.viewScale,
        ];
    }

    function worldToScreen(wx, wy) {
        return [
            wx * state.viewScale + state.viewOffsetX,
            wy * state.viewScale + state.viewOffsetY,
        ];
    }

    function snapToGrid(val) {
        if (!state.snapToGrid) return val;
        return Math.round(val / state.gridSize) * state.gridSize;
    }

    // ==================== 鼠标事件 ====================
    function getMousePos(e) {
        var rect = canvas.getBoundingClientRect();
        var sx = e.clientX - rect.left;
        var sy = e.clientY - rect.top;
        var wp = screenToWorld(sx, sy);
        return {
            sx: sx, sy: sy,
            wx: state.snapToGrid ? snapToGrid(wp[0]) : wp[0],
            wy: state.snapToGrid ? snapToGrid(wp[1]) : wp[1],
        };
    }

    function onMouseDown(e) {
        var pos = getMousePos(e);

        // 中键或空格 → 平移
        if (e.button === 1 || (e.button === 0 && e.code === "Space")) {
            state.isPanning = true;
            state.panStartX = pos.sx;
            state.panStartY = pos.sy;
            state.panOffsetStartX = state.viewOffsetX;
            state.panOffsetStartY = state.viewOffsetY;
            canvas.style.cursor = "grabbing";
            return;
        }

        if (e.button === 0) {
            // 记录最后点击位置
            state.lastClickPos = [pos.wx, pos.wy];
            
            if (state.currentTool === "select") {
                handleSelectClick(pos, e);
            } else {
                handleDrawClick(pos);
            }
        }
    }

    function onMouseMove(e) {
        var pos = getMousePos(e);
        coordDisplay.textContent = "X: " + Math.round(pos.wx) + ", Y: " + Math.round(pos.wy);

        if (state.isPanning) {
            state.viewOffsetX = state.panOffsetStartX + (pos.sx - state.panStartX);
            state.viewOffsetY = state.panOffsetStartY + (pos.sy - state.panStartY);
            redrawAll();
            return;
        }

        if (state.isDragging && state.selectedIds.size > 0) {
            handleDragMove(pos);
            return;
        }

        if (state.isDrawing) {
            handleDrawMove(pos);
        }
    }

    function onMouseUp(e) {
        if (state.isPanning) {
            state.isPanning = false;
            canvas.style.cursor = state.currentTool === "select" ? "default" : "crosshair";
            return;
        }
        if (state.isDragging) {
            state.isDragging = false;
            return;
        }
    }

    function onDblClick(e) {
        var pos = getMousePos(e);
        if (state.currentTool === "polyline" && state.tempPoints.length >= 3) {
            state.tempPoints.push(state.tempPoints[0]);
            finishPolyline();
        }
    }

    function onWheel(e) {
        e.preventDefault();
        var pos = getMousePos(e);
        var delta = e.deltaY > 0 ? 0.9 : 1.1;
        var newScale = Math.max(0.1, Math.min(10, state.viewScale * delta));
        state.viewOffsetX = pos.sx - pos.wx * newScale;
        state.viewOffsetY = pos.sy - pos.wy * newScale;
        state.viewScale = newScale;
        redrawAll();
    }

    function onContextMenu(e) {
        e.preventDefault();
        var pos = getMousePos(e);
        if (state.currentTool === "polyline" && state.tempPoints.length >= 2) {
            state.tempPoints.push(state.tempPoints[0]);
            finishPolyline();
        }
    }

    // ==================== 选择逻辑 ====================
    function handleSelectClick(pos, e) {
        var hit = findPrimitiveAt(pos.wx, pos.wy);
        var shiftKey = e && e.shiftKey;
        
        if (hit) {
            var hitId = hit.id || hit.unique_id;
            if (shiftKey) {
                if (state.selectedIds.has(hitId)) {
                    state.selectedIds.delete(hitId);
                } else {
                    state.selectedIds.add(hitId);
                }
            } else {
                state.selectedIds.clear();
                state.selectedIds.add(hitId);
            }
            state.isDragging = true;
            state.dragStartX = pos.wx;
            state.dragStartY = pos.wy;
        } else {
            if (!shiftKey) {
                state.selectedIds.clear();
                state.isBoxSelecting = true;
                state.boxSelectStart = pos;
                state.boxSelectEnd = pos;
            }
        }
        redrawAll();
    }

    function handleDragMove(pos) {
        var dx = pos.wx - state.dragStartX;
        var dy = pos.wy - state.dragStartY;
        for (var i = 0; i < state.primitives.length; i++) {
            var p = state.primitives[i];
            var pid = p.id || p.unique_id;
            if (state.selectedIds.has(pid)) {
                offsetPrimitive(p, dx, dy);
            }
        }
        state.dragStartX = pos.wx;
        state.dragStartY = pos.wy;
        redrawAll();
    }

    // ==================== 画图逻辑 ====================
    function handleDrawClick(pos) {
        state.isDrawing = true;
        state.startPoint = [pos.wx, pos.wy];
        state.tempPoints = [[pos.wx, pos.wy]];
    }

    function handleDrawMove(pos) {
        if (!state.isDrawing || !state.startPoint) return;
        redrawAll();
        ctx.save();
        applyViewTransform();
        ctx.strokeStyle = state.color;
        ctx.lineWidth = state.linewidth;
        ctx.setLineDash([5, 5]);

        if (state.currentTool === "line") {
            ctx.beginPath();
            ctx.moveTo(state.startPoint[0], state.startPoint[1]);
            ctx.lineTo(pos.wx, pos.wy);
            ctx.stroke();
        } else if (state.currentTool === "circle") {
            var r = Math.sqrt((pos.wx - state.startPoint[0])*(pos.wx - state.startPoint[0]) + (pos.wy - state.startPoint[1])*(pos.wy - state.startPoint[1]));
            ctx.beginPath();
            ctx.arc(state.startPoint[0], state.startPoint[1], r, 0, Math.PI * 2);
            ctx.stroke();
        } else if (state.currentTool === "rect") {
            ctx.strokeRect(
                Math.min(state.startPoint[0], pos.wx),
                Math.min(state.startPoint[1], pos.wy),
                Math.abs(pos.wx - state.startPoint[0]),
                Math.abs(pos.wy - state.startPoint[1])
            );
        } else if (state.currentTool === "polyline") {
            state.tempPoints.push([pos.wx, pos.wy]);
            ctx.beginPath();
            ctx.moveTo(state.tempPoints[0][0], state.tempPoints[0][1]);
            for (var i = 1; i < state.tempPoints.length; i++) {
                ctx.lineTo(state.tempPoints[i][0], state.tempPoints[i][1]);
            }
            ctx.lineTo(pos.wx, pos.wy);
            ctx.stroke();
        }
        ctx.restore();
    }

    // ==================== 图元查找 ====================
    function findPrimitiveAt(wx, wy) {
        for (var i = state.primitives.length - 1; i >= 0; i--) {
            var p = state.primitives[i];
            if (p.type === "line" && containsPoint_Line(p, wx, wy)) return p;
            if (p.type === "circle" && containsPoint_Circle(p, wx, wy)) return p;
            if (p.type === "rectangle" && containsPoint_Rect(p, wx, wy)) return p;
            if (p.type === "polyline" && containsPoint_Polyline(p, wx, wy)) return p;
            if (p.type === "text") return p;
            if (p.type === "industrial_symbol" && containsPoint_Symbol(p, wx, wy)) return p;
        }
        return null;
    }

    function containsPoint_Line(p, x, y) {
        var dx = p.end[0] - p.start[0], dy = p.end[1] - p.start[1];
        var lsq = dx*dx + dy*dy;
        if (lsq === 0) return (x-p.start[0])*(x-p.start[0]) + (y-p.start[1])*(y-p.start[1]) <= 25;
        var t = Math.max(0, Math.min(1, ((x-p.start[0])*dx+(y-p.start[1])*dy)/lsq));
        var px = p.start[0]+t*dx, py = p.start[1]+t*dy;
        return (x-px)*(x-px) + (y-py)*(y-py) <= 25;
    }

    function containsPoint_Circle(p, x, y) {
        var d = Math.sqrt((x-p.center[0])*(x-p.center[0]) + (y-p.center[1])*(y-p.center[1]));
        return Math.abs(d - p.radius) <= 5;
    }

    function containsPoint_Rect(p, x, y) {
        var l = Math.min(p.x1,p.x2), r = Math.max(p.x1,p.x2);
        var t = Math.min(p.y1,p.y2), b = Math.max(p.y1,p.y2);
        return (Math.abs(y-t)<=5 && x>=l && x<=r) || (Math.abs(y-b)<=5 && x>=l && x<=r) ||
               (Math.abs(x-l)<=5 && y>=t && y<=b) || (Math.abs(x-r)<=5 && y>=t && y<=b);
    }

    function containsPoint_Polyline(p, x, y) {
        for (var i = 0; i < p.points.length - 1; i++) {
            var p1 = p.points[i], p2 = p.points[i+1];
            var dx = p2[0]-p1[0], dy = p2[1]-p1[1];
            var lsq = dx*dx+dy*dy;
            if (lsq === 0) { if ((x-p1[0])*(x-p1[0])+(y-p1[1])*(y-p1[1]) <= 25) return true; continue; }
            var t = Math.max(0, Math.min(1, ((x-p1[0])*dx+(y-p1[1])*dy)/lsq));
            var px = p1[0]+t*dx, py = p1[1]+t*dy;
            if ((x-px)*(x-px)+(y-py)*(y-py) <= 25) return true;
        }
        return false;
    }

    function containsPoint_Symbol(p, x, y) {
        // 符号位置：优先用 position，其次用 x/y
        var sx, sy;
        if (p.position && Array.isArray(p.position)) {
            sx = p.position[0];
            sy = p.position[1];
        } else {
            sx = p.x !== undefined ? p.x : 0;
            sy = p.y !== undefined ? p.y : 0;
        }
        var w = p.width || 60;
        var h = p.height || 60;
        return x >= sx && x <= sx + w && y >= sy && y <= sy + h;
    }

    function offsetPrimitive(prim, dx, dy) {
        if (prim.type === "line") {
            prim.start[0] += dx; prim.start[1] += dy;
            prim.end[0] += dx; prim.end[1] += dy;
        } else if (prim.type === "circle") {
            prim.center[0] += dx; prim.center[1] += dy;
        } else if (prim.type === "rectangle") {
            prim.x1 += dx; prim.y1 += dy; prim.x2 += dx; prim.y2 += dy;
        } else if (prim.type === "polyline") {
            for (var i = 0; i < prim.points.length; i++) {
                prim.points[i][0] += dx; prim.points[i][1] += dy;
            }
        } else if (prim.type === "text") {
            prim.position[0] += dx; prim.position[1] += dy;
        } else if (prim.type === "industrial_symbol") {
            // 同步更新 position、x、y
            if (prim.position && Array.isArray(prim.position)) {
                prim.position[0] += dx;
                prim.position[1] += dy;
            }
            prim.x = (prim.x || 0) + dx;
            prim.y = (prim.y || 0) + dy;
        }
    }

    // ==================== 完成多段线 ====================
    function finishPolyline() {
        if (state.tempPoints.length < 2) return;
        sendApi("draw/polyline", { points: state.tempPoints, color: state.color, linewidth: state.linewidth, layer: state.layer })
            .then(function(data) {
                if (data.success && data.data) {
                    state.primitives.push(data.data);
                    updateStats();
                }
            });
        state.isDrawing = false;
        state.tempPoints = [];
        redrawAll();
    }

    // ==================== 渲染 ====================
    function redrawAll() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        drawGrid();

        ctx.save();
        applyViewTransform();

        for (var i = 0; i < state.primitives.length; i++) {
            var prim = state.primitives[i];
            if (!prim.visible) continue;
            var pid = prim.id || prim.unique_id;
            var isSelected = state.selectedIds.has(pid);
            drawPrimitive(prim, isSelected);
        }

        ctx.restore();

        // 框选矩形
        if (state.isBoxSelecting && state.boxSelectStart && state.boxSelectEnd) {
            ctx.save();
            ctx.strokeStyle = "#cba6f7";
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 4]);
            var bx = Math.min(state.boxSelectStart.sx, state.boxSelectEnd.sx);
            var by = Math.min(state.boxSelectStart.sy, state.boxSelectEnd.sy);
            var bw = Math.abs(state.boxSelectEnd.sx - state.boxSelectStart.sx);
            var bh = Math.abs(state.boxSelectEnd.sy - state.boxSelectStart.sy);
            ctx.strokeRect(bx, by, bw, bh);
            ctx.restore();
        }
    }

    function drawGrid() {
        ctx.save();
        ctx.strokeStyle = "#e8e8e8";
        ctx.lineWidth = 0.5;
        var step = state.gridSize * state.viewScale;
        if (step < 5) { ctx.restore(); return; }
        var offX = state.viewOffsetX % step;
        var offY = state.viewOffsetY % step;
        ctx.beginPath();
        for (var x = offX; x < canvas.width; x += step) {
            ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height);
        }
        for (var y = offY; y < canvas.height; y += step) {
            ctx.moveTo(0, y); ctx.lineTo(canvas.width, y);
        }
        ctx.stroke();
        ctx.restore();
    }

    function applyViewTransform() {
        ctx.translate(state.viewOffsetX, state.viewOffsetY);
        ctx.scale(state.viewScale, state.viewScale);
    }

    function drawPrimitive(prim, selected) {
        ctx.strokeStyle = prim.color || "black";
        ctx.fillStyle = "none";
        ctx.lineWidth = prim.linewidth || 1;

        if (selected) {
            ctx.save();
            ctx.strokeStyle = "#cba6f7";
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 4]);
        }

        try {
            if (prim.type === "line") {
                ctx.beginPath();
                ctx.moveTo(prim.start[0], prim.start[1]);
                ctx.lineTo(prim.end[0], prim.end[1]);
                ctx.stroke();
            } else if (prim.type === "circle") {
                ctx.beginPath();
                ctx.arc(prim.center[0], prim.center[1], prim.radius, 0, Math.PI * 2);
                ctx.stroke();
            } else if (prim.type === "rectangle") {
                ctx.strokeRect(prim.x1, prim.y1, prim.x2 - prim.x1, prim.y2 - prim.y1);
            } else if (prim.type === "polyline") {
                ctx.beginPath();
                ctx.moveTo(prim.points[0][0], prim.points[0][1]);
                for (var i = 1; i < prim.points.length; i++) {
                    ctx.lineTo(prim.points[i][0], prim.points[i][1]);
                }
                ctx.stroke();
            } else if (prim.type === "text") {
                ctx.fillStyle = prim.color || "black";
                ctx.font = (prim.font_size || 12) + "px sans-serif";
                ctx.fillText(prim.content, prim.position[0], prim.position[1]);
            } else if (prim.type === "industrial_symbol") {
                drawIndustrialSymbol(prim);
            }
        } finally {
            if (selected) {
                ctx.restore();
            }
        }

        // 绘制标签
        if (prim.label) {
            ctx.save();
            ctx.fillStyle = prim.color || "black";
            ctx.font = "11px sans-serif";
            var lx, ly;
            if (prim.position && Array.isArray(prim.position)) {
                lx = prim.position[0];
                ly = prim.position[1] - 6;
            } else {
                lx = prim.x || 0;
                ly = prim.y || 0;
            }
            ctx.fillText(prim.label, lx, ly);
            ctx.restore();
        }
    }

    function drawIndustrialSymbol(prim) {
        var shapes = prim.path_shapes || [];
        if (shapes.length === 0) return;
        
        // 符号位置：优先用 position，其次用 x/y
        var sx, sy;
        if (prim.position && Array.isArray(prim.position)) {
            sx = prim.position[0];
            sy = prim.position[1];
        } else {
            sx = prim.x !== undefined ? prim.x : 0;
            sy = prim.y !== undefined ? prim.y : 0;
        }
        var w = prim.width || 60;
        var h = prim.height || 60;
        // 偏移量：让符号中心对齐到 (sx, sy)
        var ox = sx - w / 2;
        var oy = sy - h / 2;

        ctx.strokeStyle = prim.color || "black";
        ctx.lineWidth = prim.linewidth || 1;
        ctx.setLineDash([]);

        for (var si = 0; si < shapes.length; si++) {
            var shape = shapes[si];
            if (shape.type === "line") {
                var pts = shape.points;
                ctx.beginPath();
                ctx.moveTo(pts[0][0] + ox, pts[0][1] + oy);
                for (var pi = 1; pi < pts.length; pi++) {
                    ctx.lineTo(pts[pi][0] + ox, pts[pi][1] + oy);
                }
                ctx.stroke();
            } else if (shape.type === "circle") {
                ctx.beginPath();
                ctx.arc(shape.cx + ox, shape.cy + oy, shape.r, 0, Math.PI * 2);
                ctx.stroke();
            } else if (shape.type === "polygon") {
                var pts = shape.points;
                ctx.beginPath();
                ctx.moveTo(pts[0][0] + ox, pts[0][1] + oy);
                for (var pi = 1; pi < pts.length; pi++) {
                    ctx.lineTo(pts[pi][0] + ox, pts[pi][1] + oy);
                }
                ctx.closePath();
                ctx.stroke();
            } else if (shape.type === "rectangle") {
                var pts = shape.points;
                ctx.strokeRect(pts[0][0] + ox, pts[0][1] + oy,
                              Math.abs(pts[1][0] - pts[0][0]), Math.abs(pts[1][1] - pts[0][1]));
            }
        }
    }

    // ==================== API 调用 ====================
    function sendApi(endpoint, data) {
        return fetch("/api/v1/" + endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        }).then(function(r) { return r.json(); });
    }

    function loadPrimitives() {
        fetch("/api/v1/primitives")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success && data.data) {
                    state.primitives = data.data.primitives || [];
                    updateStats();
                    redrawAll();
                }
            })
            .catch(function(e) {
                console.warn("加载图元失败:", e);
            });
    }

    // ==================== 操作 ====================
    function undo() {
        sendApi("undo", {})
            .then(function(data) {
                if (data.success) loadPrimitives();
            });
    }

    function redo() {
        sendApi("redo", {})
            .then(function(data) {
                if (data.success) loadPrimitives();
            });
    }

    function clearCanvas() {
        if (!confirm("确定要清空画布吗？")) return;
        fetch("/api/v1/clear", { method: "DELETE" })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) {
                    state.primitives = [];
                    state.selectedIds.clear();
                    updateStats();
                    redrawAll();
                    setStatus("画布已清空");
                }
            });
    }

    function exportSVG() {
        fetch("/api/v1/export/svg")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.svg) {
                    var blob = new Blob([data.svg], { type: "image/svg+xml" });
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement("a");
                    a.href = url;
                    a.download = "agentcad_export.svg";
                    a.click();
                    URL.revokeObjectURL(url);
                    setStatus("SVG已导出");
                }
            })
            .catch(function(e) {
                console.error("导出失败:", e);
            });
    }

    // ==================== 图层 ====================
    function refreshLayers() {
        fetch("/api/v1/layers")
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var layerList = document.getElementById("layer-list");
                var layerSelect = document.getElementById("prop-layer");
                if (layerList) layerList.innerHTML = "";
                if (layerSelect) layerSelect.innerHTML = "";

                var defaultOpt = document.createElement("option");
                defaultOpt.value = "default";
                defaultOpt.textContent = "default";
                if (layerSelect) layerSelect.appendChild(defaultOpt);

                if (data.success) {
                    var layers = data.layers || [];
                    for (var i = 0; i < layers.length; i++) {
                        var layer = layers[i];
                        if (layerList) {
                            var div = document.createElement("div");
                            div.className = "layer-item";
                            div.innerHTML = '<span class="layer-name">' + layer.name + '</span>' +
                                '<span class="layer-toggle ' + (layer.visible ? 'visible' : '') + '" data-layer="' + layer.name + '">👁</span>';
                            (function(lname) {
                                div.querySelector(".layer-toggle").addEventListener("click", function() {
                                    fetch("/api/v1/layers/" + lname + "/visibility", { method: "PATCH" });
                                    this.classList.toggle("visible");
                                });
                            })(layer.name);
                            layerList.appendChild(div);
                        }
                        if (layerSelect) {
                            var opt = document.createElement("option");
                            opt.value = layer.name;
                            opt.textContent = layer.name;
                            layerSelect.appendChild(opt);
                        }
                    }
                }
            })
            .catch(function(e) {
                console.warn("刷新图层失败:", e);
            });
    }

    function addLayer() {
        var name = prompt("输入新图层名称:");
        if (!name) return;
        sendApi("layers", { name: name, visible: true })
            .then(function() { refreshLayers(); });
    }

    // ==================== 文字弹窗 ====================
    function confirmText() {
        var input = document.getElementById("text-input");
        var content = input ? input.value.trim() : "";
        if (!content) return;
        var modal = document.getElementById("text-modal");
        if (modal) modal.classList.add("hidden");

        var x = state.lastClickPos ? state.lastClickPos[0] : 0;
        var y = state.lastClickPos ? state.lastClickPos[1] : 0;
        
        sendApi("draw/text", { content: content, x: x, y: y, color: state.color, layer: state.layer })
            .then(function(data) {
                if (data.success && data.data) {
                    state.primitives.push(data.data);
                    updateStats();
                    redrawAll();
                }
            });
        state.isDrawing = false;
    }

    function closeModal() {
        var modal = document.getElementById("text-modal");
        if (modal) modal.classList.add("hidden");
        state.isDrawing = false;
    }

    // ==================== 键盘事件 ====================
    function onKeyDown(e) {
        // Delete 删除选中
        if ((e.key === "Delete" || e.key === "Backspace") && state.currentTool === "select" && state.selectedIds.size > 0) {
            e.preventDefault();
            for (var i = state.primitives.length - 1; i >= 0; i--) {
                var p = state.primitives[i];
                var pid = p.id || p.unique_id;
                if (state.selectedIds.has(pid)) {
                    deletePrimitive(pid);
                    state.selectedIds.delete(pid);
                }
            }
            redrawAll();
            updateStats();
        }
        // Ctrl+Z 撤销
        if ((e.ctrlKey || e.metaKey) && e.key === "z") {
            e.preventDefault();
            undo();
        }
        // Ctrl+Y 重做
        if ((e.ctrlKey || e.metaKey) && e.key === "y") {
            e.preventDefault();
            redo();
        }
    }

    function deletePrimitive(id) {
        fetch("/api/v1/primitives/" + id, { method: "DELETE" })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.success) loadPrimitives();
            });
    }

    // ==================== 工具函数 ====================
    function updateStats() {
        var countEl = document.getElementById("stat-count");
        var undoEl = document.getElementById("stat-undo");
        if (countEl) countEl.textContent = state.primitives.length;
        if (undoEl) undoEl.textContent = state.history.length;
    }

    function setStatus(msg) {
        if (statusMessage) statusMessage.textContent = msg;
    }

    // ==================== 启动 ====================
    window.addEventListener("DOMContentLoaded", init);
})();
