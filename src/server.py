"""
AgentCAD 服务入口
启动命令: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from engine.canvas import DrawingCanvas
from api.routes import router, set_canvas

# 创建全局画布实例
app_canvas = DrawingCanvas(width=1280, height=720)
set_canvas(app_canvas)

# 创建 FastAPI 应用
app = FastAPI(
    title="AgentCAD",
    description="AI Agent 驱动的轻量级 CAD 绘图系统",
    version="0.1.0",
)

# CORS 支持（允许跨域调用 API）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)

# 挂载前端静态文件
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/health")
def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "service": "AgentCAD",
        "version": "0.1.0",
        "primitives_count": len(app_canvas.get_all_primitives()),
        "history_size": app_canvas.history_size,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
