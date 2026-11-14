"""隔离目录检查六个 Windows 启动脚本是否依赖本机 Python 路径。"""
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


SCRIPTS = {
    '开始验证.cmd': 'probe_amap.py',
    '打开真实地点查询.cmd': 'run_pilot.py',
    '打开邻境演示.cmd': 'demo_web.py',
    '查看银行候选.cmd': 'probe_amap.py',
    '核验两个地点.cmd': 'probe_amap.py',
    '配置地图.cmd': 'configure_map_gui.py',
}


def main():
    root = Path(__file__).parent
    with TemporaryDirectory(prefix='linjing-launchers-') as directory:
        folder = Path(directory)
        # 替身只记录参数，不调用地图接口，也不打开窗口。
        (folder / 'python.cmd').write_text('@echo off\r\necho %*>>"%LINJING_LAUNCH_LOG%"\r\n', encoding='ascii')
        log = folder / 'launch.log'
        environment = os.environ.copy()
        environment['PATH'] = str(folder) + os.pathsep + environment['PATH']
        environment['LINJING_LAUNCH_LOG'] = str(log)
        for script, expected in SCRIPTS.items():
            shutil.copy2(root / script, folder / script)
            result = subprocess.run(['cmd', '/d', '/c', str(folder / script)], cwd=folder,
                                    env=environment, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
            if result.returncode:
                raise AssertionError('{} exited {}'.format(script, result.returncode))
            lines = log.read_text(encoding='utf-8').splitlines() if log.exists() else []
            if not lines or expected not in lines[-1]:
                raise AssertionError('{} did not dispatch {}'.format(script, expected))
        missing = environment.copy()
        missing['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        result = subprocess.run(['cmd', '/d', '/c', str(folder / '开始验证.cmd')], cwd=folder,
                                env=missing, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        if result.returncode != 1:
            raise AssertionError('缺少 Python 时没有返回明确错误')
        print('通过：六个 .cmd 在隔离目录均使用 PATH 中的 python 并调用对应入口。')
        print('缺少 Python 时，开始验证脚本返回安装提示和非零状态。')
        print('此项仅检查启动参数；接口、浏览器和 GUI 功能另行验证。')


if __name__ == '__main__':
    main()
