"""Masked desktop fields avoid terminal paste/getpass incompatibilities."""
import tkinter as tk
from tkinter import messagebox, ttk

from configure_map import check_git_exclusion
from map_config import CONFIG_PATH, load_config, save_config, validate_config


def main():
    root = tk.Tk()
    root.title('邻境 · 配置网页地图')
    root.geometry('560x440')
    root.minsize(500, 420)
    panel = ttk.Frame(root, padding=24)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='配置网页地图', font=('Microsoft YaHei', 17, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='已有配置的字段可留空，仅填写需要新增或替换的 Key。').pack(anchor='w', pady=(8, 16))
    entries = []
    for label in ('Web端（JS API）Key', '对应的安全密钥', 'Web 服务 Key（地点搜索和坐标转换）'):
        ttk.Label(panel, text=label).pack(anchor='w')
        entry = ttk.Entry(panel, show='*', font=('Segoe UI', 12))
        entry.pack(fill='x', pady=(5, 12))
        entries.append(entry)
    status = tk.StringVar(value='支持 Ctrl+V 粘贴。已有前两项时，只需填写第三项。')
    ttk.Label(panel, textvariable=status, wraplength=490).pack(anchor='w', pady=(0, 8))
    ttk.Label(panel, text='仅保存到本机 data/amap.local.json（不加密），排除 Git 上传。',
              wraplength=490).pack(anchor='w')

    def save():
        try:
            check_git_exclusion()
            existing = load_config() or {}
            config = validate_config({
                'js_key': entries[0].get().strip() or existing.get('js_key', ''),
                'security_code': entries[1].get().strip() or existing.get('security_code', ''),
                'web_key': entries[2].get().strip() or existing.get('web_key', ''),
            })
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
        status.set('配置已保存。关闭此窗口并重新启动应用即可。')
        messagebox.showinfo('保存成功', '配置已保存到本机。关闭旧的查询窗口后重新打开邻境。', parent=root)

    ttk.Button(panel, text='保存配置', command=save).pack(anchor='e', pady=(14, 0))
    # Avoid Tk's default callback traceback, which may include user input.
    root.report_callback_exception = lambda *_: status.set('操作未完成，请重试。未显示任何密钥内容。')
    entries[0].focus_set()
    root.mainloop()


if __name__ == '__main__':
    main()
