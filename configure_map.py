"""Interactive setup; credentials stay in the ignored local data directory."""
import getpass
from pathlib import Path
import subprocess
import warnings

from map_config import CONFIG_PATH, save_config


def check_git_exclusion():
    root = Path(__file__).resolve().parent
    relative = CONFIG_PATH.relative_to(root).as_posix()
    ignored = subprocess.run(['git', 'check-ignore', '--quiet', relative], cwd=str(root),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', relative], cwd=str(root),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if ignored.returncode != 0 or tracked.returncode != 1:
        raise ValueError('未能确认配置文件已排除 Git 上传，暂不保存。请让 Codex 检查。')


def main():
    print('邻境 · 网页地图配置')
    print('请从高德「邻境网页地图」复制 Web端(JS API) Key 和对应安全密钥。')
    print('输入不显示字符，粘贴后按回车。不要发送到聊天或截图中。')
    print('配置以本地文件保存到 data/amap.local.json，不加密，不纳入 Git。')
    print('本工具只保存配置，不发送网络请求，也不代表地图已接通。')
    try:
        check_git_exclusion()
        if CONFIG_PATH.exists():
            if input('已有配置。输入 YES 替换，直接回车取消：').strip() != 'YES':
                print('已取消，保留原配置。')
                return 0
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            key = getpass.getpass('粘贴网页地图 Key：').strip()
            code = getpass.getpass('粘贴对应的安全密钥：').strip()
        save_config({'js_key': key, 'security_code': code})
        print('配置已保存。请告诉 Codex「配置好了」，不要发送具体值。')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\n已取消，未保存新配置。')
    except getpass.GetPassWarning:
        print('当前窗口不支持隐藏输入。请双击配置地图.cmd，在终端中输入。')
    except ValueError as error:
        print(str(error))
    except OSError:
        print('无法检查 Git 或写入配置文件，请确认 Git 可用及文件夹可写。')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
