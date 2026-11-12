import subprocess
import sys
import time
import os

if __name__ == "__main__":
    # 启动server子进程
    server_proc = subprocess.Popen([sys.executable, "server.py"], cwd=os.getcwd())
    time.sleep(1.5)  # 等服务端启动完毕
    # 启动gui
    gui_proc = subprocess.Popen([sys.executable, "gui.py"], cwd=os.getcwd())

    # 等待gui退出，然后关闭server
    gui_proc.wait()
    server_proc.terminate()
    server_proc.wait()
