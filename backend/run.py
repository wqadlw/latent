"""启动脚本（同时作为 PyInstaller 打包入口）。

实际逻辑全部委托给 ``app.main.main()`` —— 避免这里和 main.py 各写一份
端口/版本/自检逻辑，导致两处漂移（v2 就出现过：main.py 与 README 版本号不一致）。
"""
import multiprocessing

from app.main import main

if __name__ == "__main__":
    # PyInstaller onefile 打包后，子进程/多进程场景需要，必须放在最前
    multiprocessing.freeze_support()
    main()
