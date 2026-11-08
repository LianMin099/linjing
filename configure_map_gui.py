"""Masked desktop fields avoid terminal paste/getpass incompatibilities."""
import tkinter as tk
from tkinter import messagebox, ttk

from configure_map import check_git_exclusion
from map_config import CONFIG_PATH, save_config, validate_config


def main():
    root = tk.Tk()
    root.title('邻境 · 配置网页地图')
    root.geometry('560x360')
    root.minsize(500, 340)
    panel = ttk.Frame(root, padding=24)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='配置网页地图', font=('Microsoft YaHei', 17, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='从高德「邻境网页地图」复制两项内容，分别粘贴到下方。').pack(anchor='w', pady=(8, 16))
    entries = []
    for label in ('Web端（JS API）Key', '对应的安全密钥'):
        ttk.Label(panel, text=label).pack(anchor='w')
        entry = ttk.Entry(panel, show='*', font=('Segoe UI', 12))
        entry.pack(fill='x', pady=(5, 12))
        entries.append(entry)
    status = tk.StringVar(value='支持 Ctrl+V 粘贴。显示星号代表已输入，不会自动提交。')
    ttk.Label(panel, textvariable=status, wraplength=490).pack(anchor='w', pady=(0, 8))
    ttk.Label(panel, text='仅保存到本机 data/amap.local.json（不加密），排除 Git 上传。',
              wraplength=490).pack(anchor='w')

    def save():
        try:
            check_git_exclusion()
            config = validate_config({'js_key': entries[0].get().strip(),
                                      'security_code': entries[1].get().strip()})
            if CONFIG_PATH.exists() and not messagebox.askyesno(
                    '替换已有配置', '本机已有地图配置，是否替换？', parent=root):
                status.set('已取消替换，原配置保留。')
                return
            save_config(config)
        except ValueError as error:
            status.set(str(error))
            return
        except Exception:
            # Do not expose credentials through exception text or tracebacks.
            status.set('保存失败：请检查 Git 是否可用、项目文件夹是否可写。窗口将保持打开。')
            return
        for entry in entries:
            entry.delete(0, 'end')
        status.set('配置已保存。可以关闭此窗口，并告诉 Codex「配置好了」。')
        messagebox.showinfo('保存成功', '配置已保存到本机。地图接入仍待完成。', parent=root)

    ttk.Button(panel, text='保存配置', command=save).pack(anchor='e', pady=(14, 0))
    # Avoid Tk's default callback traceback, which may include user input.
    root.report_callback_exception = lambda *_: status.set('操作未完成，请重试。未显示任何密钥内容。')
    entries[0].focus_set()
    root.mainloop()


if __name__ == '__main__':
    main()
