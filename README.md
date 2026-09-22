# 羽化面板 插件与脚本

> 羽化面板（yuhua-panel）插件与脚本私人仓库

## 目录结构

```
plugins/
├── 回收猿旧衣服回收.py               # 主脚本（羽化/青龙双兼容）
├── 回收猿旧衣服回收依赖.txt          # 依赖说明
└── 回收猿旧衣服回收插件配置文件.json # 羽化面板插件配置（表单定义）
```

## 回收猿旧衣服回收插件

- 功能：自动登录、每日签到、福利任务汇总、余额查询、自动提现、PushPlus 推送
- 环境：羽化面板（直接导入） / 青龙面板（环境变量）双兼容
- 依赖：`pip install requests requests[socks]`

### 配置项

| 配置键 | 说明 | 必填 |
|---|---|---|
| YYB_SERVER | YYB 服务列表，格式 `地址@账号ID`，一行一个 | ✅ |
| YYB_API_KEY | YYB 服务密钥 | 选填 |
| PLUSPLUS_TOKEN | PushPlus 推送 token | 选填 |
| PROXY_API | 品赞代理 API | 选填 |
| PROXY_TYPE | 代理类型 http/socks5，默认 http | ✅ |
| HSY_CHANNEL_ID | 渠道 ID，默认 wx1008 | ✅ |
| HSY_WITHDRAW_MIN | 最低提现金额，默认 1 | ✅ |

### 导入羽化面板

1. 插件管理 → 导入插件
2. 选择 `回收猿旧衣服回收插件配置文件.json`（或手动新建插件，填 main 为 `回收猿旧衣服回收.py`）
3. 按表单填写配置并保存

### 青龙面板运行

```bash
# 设置环境变量后运行
export YYB_SERVER='http://127.0.0.1:8000@user_openid'
export YYB_API_KEY='your_key'
python3 回收猿旧衣服回收.py
```

## 更新日志

- 2026-09-23：初始化仓库，上传回收猿旧衣服回收插件 v1.0.0；修正配置文件 main 字段
