"""启动脚本（同时作为 PyInstaller 打包入口）"""
import multiprocessing
import uvicorn
from app.main import app, open_browser
import threading

if __name__ == "__main__":
    # PyInstaller onefile 打包后，子进程/多进程场景需要，放在最前
    multiprocessing.freeze_support()
    host = "127.0.0.1"
    port = 8765
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("  多行业提示词矩阵管理系统 v2.0.0")
    print("=" * 60)
    print(f"  服务地址: {url}")
    print(f"  API文档:  {url}/docs")
    print(f"  默认账号: admin / admin123")
    print("=" * 60)
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
