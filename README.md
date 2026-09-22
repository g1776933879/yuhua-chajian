# 羽化插件 · yuhua-chajian

> 羽化面板（yuhua-panel）私人插件与脚本仓库
> Owner: `g1776933879` · 创建: 2026-09-22

> **注**：仓库中文名「羽化插件」在 GitHub 上被转为 `yuhua-plugins`（GitHub 不支持非 ASCII 仓库名，会自动剥离为 `-`）。中文名仅存在于本 README 与本地目录。

---

## 目录结构

```
羽化插件/                      (GitHub: yuhua-plugins)
├── 插件/                      # 面板插件（可直接投喂面板使用）
│   ├── 菜单v5.py
│   ├── 菜单.py
│   └── pd_dashboard.py
├── 脚本/                      # 原始脚本源码
│   ├── js/                    # JavaScript 脚本（Node 运行）
│   │   └── .gitkeep
│   └── python/                # Python 脚本（Python 3.12 运行）
│       ├── hy-cp-yuhua-panel-plugins__菜单v5.py
│       ├── nanxiafenglai-yuhua-panel-plugins__菜单.py
│       └── xsq0428-yuhua-plugins__pd_dashboard.py
└── README.md
```

---

## 两个目录的区别

### `插件/`
**成品插件**，文件名为面板识别用的原名字。
面板插件目录对应 `~/yuhua-panel/data/plugins/`，丢进去重启面板即可加载。

| 文件 | 大小 | 说明 |
|---|---|---|
| `菜单v5.py` | 951 KB | 功能菜单插件（体积大，含内嵌资源） |
| `菜单.py` | 9.3 KB | 精简版菜单插件 |
| `pd_dashboard.py` | 12.4 KB | 拼豆仪表盘 |

### `脚本/`
**原始源码归档**，按语言分目录，文件名带来源前缀便于溯源。

**命名约定**：`<来源仓库>__<原文件名>`

| 文件 | 来源 |
|---|---|
| `hy-cp-yuhua-panel-plugins__菜单v5.py` | `hy-cp/yuhua-panel-plugins` |
| `nanxiafenglai-yuhua-panel-plugins__菜单.py` | `nanxiafenglai/yuhua-panel-plugins` |
| `xsq0428-yuhua-plugins__pd_dashboard.py` | `xsq0428/yuhua-plugins` |

> `脚本/js/` 目前为空，预留位置。以后有 JS 插件直接丢进去。

---

## 运行环境

羽化面板插件依赖：

- **Python 3.12**（`.py` 插件）
- **Node 24**（`.js` 插件）
- 面板数据目录：`~/yuhua-panel/data/`
- 面板管理后台：`http://127.0.0.1:6060/admin`

---

## 用法

**方式一：直接拷进面板**
```bash
cp 插件/*.py ~/yuhua-panel/data/plugins/
```

**方式二：从本仓库拉取**
```bash
git clone https://github.com/g1776933879/yuhua-chajian.git
cp yuhua-plugins/插件/*.py ~/yuhua-panel/data/plugins/
```

---

## 来源仓库

| 上游 | 镜像 |
|---|---|
| `hy-cp/yuhua-panel-plugins` | `g1776933879/hy-cp-yuhua-panel-plugins` |
| `nanxiafenglai/yuhua-panel-plugins` | `g1776933879/nanxiafenglai-yuhua-panel-plugins` |
| `xsq0428/yuhua-plugins` | `g1776933879/xsq0428-yuhua-plugins` |

同步器：`/root/yuhua-sync/sync-yuhua.sh`（每日 04:00 自动同步）

---

## ⚠️ 注意

本仓库为 **private**。**请勿改为 public** —— 内含面板插件源码，与个人部署环境强相关。

