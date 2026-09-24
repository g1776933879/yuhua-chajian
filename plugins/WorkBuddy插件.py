# [title: WorkBuddy签到]
# [language: python]
# [rule: ^([wW][bB])(登录|登陆|短信|添加|查询|运行|管理|清理|更新|检测|续期|积分|任务|玩法|领奖|帮助)((?:\s+\S+)*)$]
# [disable:false]
# [open_source: false]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public:true]
# [version: 1.0.0]
# [price: 0]
# [author: 逆向改造版(基于 WorkBuddy Daily + 小米钱包插件范式)]
# [service: ]
# [description: ❶WorkBuddy(cn) 全能签到插件：Token 自动续期、💰积分 / 📊用量 / 🌱成长查询、✅成长任务、🎮互动玩法、🎁自动领奖，全程免费、无授权收费墙。<br>❷对接呆呆面板与青龙面板双平台：登录支持【短信验证码登录 / Token登录(粘贴 手机号:AT:RT) / 批量粘贴账号行】三种方式，可一键同步到青龙/呆呆环境变量，由面板定时跑量。<br>❸指令：『wb登录』选择登录方式、『wb短信』直接短信登录、『wb添加』批量粘贴账号、『wb查询』查积分/用量/成长/任务、『wb运行』执行全流程、『wb任务』只跑成长任务、『wb玩法』只跑互动玩法、『wb领奖』只领奖、『wb续期』刷新Token、『wb管理』管理账号、『wb清理』清空账号、『wb更新』重新同步面板变量、『wb检测』校验账号有效性、『wb帮助』查看说明。<br>❹账号格式：手机号:AT:RT（每行一个，可多行；AT 可留空，运行时用 RT 自动换发）]

# [param: {"required":false,"key":"s_wb.s_wb_qlname","bool":false,"placeholder":"Host丨ClientID丨ClientSecret","name":"对接青龙","desc":"各参数之间用中文符丨分割，例如: http://127.0.0.1:5700/丨abcdef-ghijk丨abcdefghijklmnopqrs_tuvw"}]
# [param: {"required":false,"key":"s_wb.s_wb_ddname","bool":false,"placeholder":"Host丨app_key丨app_secret","name":"对接呆呆面板","desc":"留空则使用青龙面板。各参数之间用中文符丨分割，例如: http://127.0.0.1:5700丨abcdef-ghijk丨abcdefghijklmnopqrs_tuvw"}]
# [param: {"required":false,"key":"s_wb.s_wb_osname","bool":false,"placeholder":"WORKBUDDY_REFRESH_TOKEN","name":"环境变量名","desc":"同步到青龙/呆呆的变量名称，默认 WORKBUDDY_REFRESH_TOKEN"}]
# [param: {"required":false,"key":"s_wb.s_wb_proxy","bool":false,"placeholder":"http://127.0.0.1:7890","name":"代理地址","desc":"可选，格式 http:// 或 socks5://，留空直连"}]
# [param: {"required":false,"key":"s_wb.s_wb_push","bool":false,"placeholder":"PushPlus Token","name":"运行报告推送","desc":"可选，填写 PushPlus token，『wb运行』结束后推送汇总报告"}]

# -*- coding: utf-8 -*-
"""
WorkBuddy 签到 —— 呆呆面板 / 青龙面板 双平台插件（免费无授权版）

能力来源：workbuddy_daily.py（续期 / 积分 / 用量 / 成长 / 任务 / 玩法 / 领奖）
面板范式：小米钱包视频福利插件（呆呆 middleware SDK + 青龙/呆呆 Open API）

账号模型（与 workbuddy_daily.py 完全一致）：
   环境变量行   手机号:AT:RT        （AT 可留空，运行时用 RT 换发）
   本地存储     bucket s_wb_user → {userid: [{name, phone, at, rt, updated}, ...]}
   面板同步     单个变量 WORKBUDDY_REFRESH_TOKEN，多个账号换行分隔

⚠️ RT 是唯一续期凭据：每次刷新服务端会换发新 RT，脚本会即时写回本地并同步面板，
   因此「面板变量」既是输入也是产物，不要手动改里面的 AT。

登录实现与 workbuddy_login.py 严格对齐：
   POST /v2/plugin/login/send-sms   下发验证码（纯 Chrome UA，不带 Electron 标识）
   POST /v2/plugin/login/token      提交验证码换 accessToken / refreshToken
   登录成功后立即用 RT 调一次刷新接口做可用性校验（等价于 --verify）

本地调试（无面板环境时 middleware 自动降级为 CLI stub）：
   python WorkBuddy_青龙呆呆插件.py wb帮助
   python WorkBuddy_青龙呆呆插件.py wb短信 13800138000 123456
"""
import os
import re
import sys
import json
import time
import uuid
import base64
import hashlib
import urllib3
import requests
import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_VERSION = "v1.0.0"

# ============================================================
# 面板运行时：呆呆 middleware SDK（本地调试时自动降级为 CLI stub）
# ============================================================
try:
    import middleware            # 呆呆面板运行时注入
    _HAS_MW = True
except Exception:
    middleware = None
    _HAS_MW = False


class _LocalSender(object):
    """本地 CLI 调试用的 Sender 替身（面板里不会走到这里）"""
    def __init__(self):
        self._msg = " ".join(sys.argv[1:]) or os.environ.get("WB_LOCAL_MSG", "")

    def getUserID(self):
        return os.environ.get("WB_LOCAL_USER", "local")

    def getImtype(self):
        return "cli"

    def getMessage(self):
        return self._msg

    def reply(self, text):
        print(text)

    def replyImage(self, *a, **k):
        pass

    def listen(self, timeout=60000):
        try:
            return input("> ")
        except EOFError:
            return None

    def setContinue(self):
        pass


_LOCAL_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_wb_local_bucket.json")


def _local_bucket_get(bucket, key):
    try:
        d = json.load(open(_LOCAL_STORE, encoding="utf-8"))
    except Exception:
        d = {}
    return (d.get(bucket) or {}).get(key)


def _local_bucket_set(bucket, key, value):
    try:
        d = json.load(open(_LOCAL_STORE, encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault(bucket, {})[key] = value
    try:
        json.dump(d, open(_LOCAL_STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass


if _HAS_MW:
    _senderID = middleware.getSenderID()
    sender = middleware.Sender(_senderID)
    userid = sender.getUserID()
    imtype = sender.getImtype()

    def bucket_get(bucket, key):
        try:
            return middleware.bucketGet(bucket=bucket, key=key)
        except Exception:
            return None

    def bucket_set(bucket, key, value):
        try:
            return middleware.bucketSet(bucket, key, value)
        except Exception:
            return None
else:
    sender = _LocalSender()
    userid = sender.getUserID()
    imtype = sender.getImtype()
    bucket_get = _local_bucket_get
    bucket_set = _local_bucket_set

BUCKET = "s_wb"             # 插件配置
BUCKET_USER = "s_wb_user"   # 每个用户 → 账号列表(JSON)

# 青龙定时模式专用：RT 轮换必须持久化到脚本目录，否则下次运行旧 RT 已失效
# （与 workbuddy_daily.py 的 wb_refresh_tokens.json 同一套模型）
REFRESH_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wb_refresh_tokens.json")

# ============================================================
# WorkBuddy 接口常量（移植自 workbuddy_daily.py）
# ============================================================
BASE = "https://www.workbuddy.cn"
REFRESH_URL = "https://copilot.tencent.com/v2/plugin/auth/token/refresh"
SEND_SMS_URL = BASE + "/v2/plugin/login/send-sms"
LOGIN_URL = BASE + "/v2/plugin/login/token"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) WorkBuddy/5.5.4 Chrome/138.0.7204.251 Electron/37.10.3 Safari/537.36")
# 登录接口专用 UA（与 workbuddy_login.py 保持一致：插件登录走纯浏览器指纹，不带 Electron 标识）
LOGIN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/138.0.7204.251 Safari/537.36")
WRITE_GAP = 1.5

QQ_TPL = "cb_y5Dy46tPQGGWtueMxXbe"
THEME_KEY = "theme-tkmw7j"
LIB_DOC_URL = "https://www.workbuddy.cn/space/d/o0KWYeynteVv06UnAZqIFm"

TASK_NAME_CN = {
    "create_canvas": "设计创意模式", "playbook_prompt": "探索优秀灵感", "RichMeow_Chat": "桌面端对话",
    "Library_read": "体验资料库", "Expert_lighthouse": "腾讯轻量云专家", "Expert_Philanthropy": "公益专家",
    "Hp_Appearance": "和平精英主题", "Buddy_App": "发现应用", "Buddy_App_QQ": "企鹅教师助手",
    "Model_chat_GLM5.2": "GLM-5.2模型对话", "black_cat": "夜猫子活动", "Expert_team_use_3": "召唤3次专家团",
    "first_buddy": "领取Buddy", "chat_5": "和AI聊天5次", "skill_1": "尝鲜热门技能",
    "expert_5": "召唤5次专家", "template_5": "使用5个模板", "automation_1": "设置自动化任务",
    "workstation_expert": "工作台搭建师", "wb_wechat_oa_subscribe_task": "关注公众号",
    "Sequential_Tasks_1": "小程序对话", "Sequential_Tasks_2": "小程序专家对话", "school_season": "校园日活动",
}

STATUS_CN = {"not_accepted": "未接受", "accepted": "进行中", "completed": "待领奖",
             "claimed": "已领奖", "failed": "失败"}

# 小程序埋点协议（对齐上游 workbuddy2api-panel）
MP_HEADER = {"X-Client-Platform": "miniprogram",
             "User-Agent": "Mozilla/5.0 (Linux; Android 14; MicroMessenger/8.0.49 WeChat/0.8.0 "
                           "MiniProgramEnv/android; wkbrowser xweb)"}
MP_REPORT_HEADERS = {
    "Content-Type": "application/json", "Accept": "application/json",
    "X-Client-Product": "workbuddy-mp", "X-Client-Version": "2.4.0",
    "X-Client-Platform": "mp-weixin", "X-Platform": "wechatmp",
}
SCHOOL_EXPERT_CATEGORY = "16-BackToSchool"

# ============================================================
# 通用工具
# ============================================================
def mask_str(s, head=3, tail=2):
    if not s:
        return ""
    s = str(s)
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]


def _now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def beijing_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


def within_night_window():
    try:
        h = beijing_now().hour
        return h >= 23 or h < 8
    except Exception:
        return None


def _proxies():
    p = (globals().get("s_wb_proxy") or "").strip()
    return {"http": p, "https": p} if p else {}


def task_cn(code):
    return TASK_NAME_CN.get(code, code)


# ============================================================
# Token 解析 / 续期
# ============================================================
def _jwt_payload(tok):
    try:
        pay = tok.split(".")[1]
        pay += "=" * (-len(pay) % 4)
        return json.loads(base64.urlsafe_b64decode(pay))
    except Exception:
        return {}


def jwt_user(tok):
    return _jwt_payload(tok).get("preferred_username", "") or ""


def uid_of(tok):
    return _jwt_payload(tok).get("sub", "") or ""


def nickname_of(tok):
    return _jwt_payload(tok).get("nickname", "") or "用户"


def token_alive(at, margin=300):
    """AT 是否仍在有效期内（默认留 5 分钟余量）"""
    try:
        return int(_jwt_payload(at).get("exp", 0)) - time.time() > margin
    except Exception:
        return False


def refresh_one(rt):
    """用 RT 换发新 AT/RT，返回 (at, rt, err)"""
    try:
        s = requests.Session()
        s.trust_env = False
        r = s.post(REFRESH_URL, json={}, timeout=20, verify=False, proxies=_proxies(),
                   headers={"X-Refresh-Token": rt, "X-Auth-Refresh-Source": "plugin",
                            "Content-Type": "application/json"})
        d = r.json()
        inner = d.get("data") or {}
        if d.get("code") == 0 and inner.get("accessToken"):
            return inner["accessToken"], (inner.get("refreshToken") or rt), ""
        return "", "", str(d.get("msg", ""))[:120]
    except Exception as e:
        return "", "", str(e)[:80]


def parse_account_line(line):
    """解析一行账号：手机号:AT:RT / 手机号:RT / AT:RT / 纯RT → (phone, at, rt)"""
    line = (line or "").strip()
    if not line:
        return "", "", ""
    parts = line.split(":")
    if len(parts) >= 3 and not parts[0].startswith("eyJ"):
        return parts[0].strip(), parts[1].strip(), ":".join(parts[2:]).strip()
    if len(parts) == 2:
        a, b = parts[0].strip(), parts[1].strip()
        if a.startswith("eyJ"):                 # AT:RT
            return (jwt_user(a) or ""), a, b
        if b.startswith("eyJ"):                 # 手机号:AT（无 RT，无法续期）
            return a, b, ""
        return a, "", b                          # 手机号:RT
    if line.startswith("eyJ"):                   # 纯 RT
        return "", "", line
    return "", "", ""


# ============================================================
# WorkBuddy 账号（业务封装）
# ============================================================
class WBUser(object):
    def __init__(self, index, acc):
        self.index = index
        self.name = acc.get("name", "") or acc.get("phone", "")
        self.phone = acc.get("phone", "")
        self.at = acc.get("at", "")
        self.rt = acc.get("rt", "")
        self.logs = []
        self.acc = acc
        self.uid = ""
        self.nick = ""
        self.session = None
        self.streak_days = None

    # ---------- 日志 ----------
    def log(self, msg):
        line = "[%s][%s] %s" % (_now(), self.name, msg)
        print(line)
        self.logs.append(line)

    # ---------- 凭据 ----------
    def ensure_token(self, force=False):
        """保证 AT 可用（必要时用 RT 续期），返回 True/False；续期成功会写回 self.acc"""
        if self.at and token_alive(self.at) and not force:
            return True
        if not self.rt:
            self.log("❌ 缺少 RT（刷新令牌），无法续期，请重新登录")
            return False
        at, rt, err = refresh_one(self.rt)
        if not at:
            self.log("❌ 续期失败: %s" % (err or "未知错误"))
            return False
        self.at, self.rt = at, rt
        self.acc["at"], self.acc["rt"] = at, rt
        self.acc["updated"] = time.strftime("%Y-%m-%d %H:%M")
        self.log("🔑 Token 已续期（新 RT 已保存）")
        return True

    def api(self):
        if self.session is not None:
            return self.session
        self.uid = uid_of(self.at)
        self.nick = nickname_of(self.at)
        s = requests.Session()
        s.trust_env = False
        s.headers.update({"Authorization": "Bearer " + self.at, "Content-Type": "application/json",
                          "Accept": "application/json, text/plain, */*", "Origin": BASE,
                          "Referer": BASE + "/profile/growth-center", "User-Agent": UA,
                          "X-User-Id": self.uid})
        self.session = s
        return s

    # ---------- 基础请求 ----------
    def get(self, path, **kw):
        try:
            return self.api().get(BASE + path, timeout=25, verify=False, proxies=_proxies(), **kw)
        except Exception as e:
            self.log("   请求异常[%s]: %s" % (path, str(e)[:50]))
            return None

    def post(self, path, body=None, **kw):
        try:
            return self.api().post(BASE + path, json=body or {}, timeout=25,
                                   verify=False, proxies=_proxies(), **kw)
        except Exception as e:
            self.log("   请求异常[%s]: %s" % (path, str(e)[:50]))
            return None

    def jget(self, path, **kw):
        r = self.get(path, **kw)
        try:
            return r.json()
        except Exception:
            return {}

    def jpost(self, path, body=None, **kw):
        r = self.post(path, body, **kw)
        try:
            return r.json()
        except Exception:
            return {}

    # ---------- 任务状态 ----------
    def tasks(self, headers=None):
        d = self.jget("/v2/activity/growth/tasks", headers=headers)
        return (d.get("data") or {}).get("tasks", []) or []

    def prog(self, code, headers=None):
        for t in self.tasks(headers=headers):
            if isinstance(t, dict) and t.get("task_code") == code:
                pr = t.get("progress") or {}
                return t.get("accept_status", ""), pr.get("current"), pr.get("target")
        return None, None, None

    # ---------- 💰积分 / 📊用量 / 🌱成长 ----------
    def query_credits(self):
        try:
            r = self.jpost("/billing/meter/get-user-resource-summary")
            pkgs = (r.get("data") or {}).get("Packages", []) or []
            out = []
            for i, p in enumerate(pkgs):
                def clean(v):
                    v = str(v or "0")
                    return v.rstrip("0").rstrip(".") if "." in v else v
                out.append("%s剩余%s(共%s,已用%s)" % ("主套餐" if i == 0 else "加量包%d" % i,
                                                     clean(p.get("CycleRemainCapacity")),
                                                     clean(p.get("CycleTotalCapacity")),
                                                     clean(p.get("CycleUsedCapacity"))))
            return "；".join(out) if out else "暂无套餐"
        except Exception as e:
            return "查询失败:" + str(e)[:40]

    def query_usage(self):
        try:
            r = self.jpost("/billing/meter/get-user-resource")
            resp = ((r.get("data") or {}).get("Response") or {}).get("Data") or {}
            return "共%s类资源，已使用%s次" % (resp.get("TotalCount", "?"), resp.get("TotalDosage", "?"))
        except Exception:
            return "用量数据延迟2-3小时"

    def query_growth(self):
        prof = (self.jget("/v2/activity/growth/profile").get("data") or {})
        energy = (self.jget("/v2/activity/growth/energy").get("data") or {}).get("balance")
        streak = ((self.jget("/v2/activity/growth/streak").get("data") or {}).get("streak") or {})
        self.streak_days = streak.get("days")
        try:
            cells = (self.jget("/v2/activity/growth/heatmap").get("data") or {}).get("cells", [])
            signed = sum(1 for c in cells if isinstance(c, dict) and c.get("score", 0) > 0)
        except Exception:
            signed = "?"
        return "等级%s 连签%s天 能量%s 累签%s天" % (prof.get("level", "?"), streak.get("days", "?"),
                                                energy, signed)

    # ---------- 埋点上报 ----------
    def derive_id(self, salt):
        return hashlib.md5(("%s:%s" % (salt, self.uid)).encode()).hexdigest()[:36]

    def report(self, events):
        mid = self.derive_id("machine")
        out = []
        for e in events:
            env = {"timestamp": int(time.time() * 1000), "reportDelay": 0,
                   "userId": self.uid, "userNickname": self.nick,
                   "ideName": "WorkBuddy", "ideType": "WorkBuddy", "ideVersion": "5.5.6",
                   "machineId": mid, "sessionId": self.derive_id("session"),
                   "mode": "CLOUD", "userAgent": UA, "os": "Win32", "arch": "x64",
                   "osVersion": "10.0.26220", "timezone": "Asia/Shanghai",
                   "product": "SaaS", "releaseDate": 1789036585355,
                   "commit": "5f9692923c93033111c51ad7b003eb80204a9b75",
                   "extName": "workbuddy-desktop", "extVersion": "5.5.6",
                   "cpuCores": 20, "memorySize": 24}
            env.update(e)
            out.append(env)
        try:
            s = requests.Session(); s.trust_env = False
            return s.post(BASE + "/v2/report", json=out, timeout=15, verify=False,
                          proxies=_proxies()).status_code
        except Exception:
            return 0

    def report_web_event(self, event_code, page_url, element_id, element_name):
        ev = {"eventCode": event_code, "timestamp": int(time.time() * 1000), "reportDelay": 0,
              "pageURL": page_url, "elementId": element_id, "elementName": element_name,
              "os": "Win32", "arch": "", "osVersion": "10.0", "userAgent": UA,
              "machineId": self.derive_id("webmachine"), "userId": self.uid, "userNickname": self.nick}
        body = {"common": {"userId": self.uid, "userNickname": self.nick, "ideName": "web",
                           "ideType": "web", "machineId": self.derive_id("webmachine"),
                           "mode": "CLOUD", "userAgent": UA, "os": "Win32",
                           "timezone": "Asia/Shanghai"}, "events": [ev]}
        try:
            s = requests.Session(); s.trust_env = False
            return s.post(BASE + "/v2/report", json=body, timeout=15, verify=False,
                          proxies=_proxies()).status_code
        except Exception:
            return 0

    def report_desktop(self, events):
        now = int(time.time() * 1000)
        fp = {"timezone": "Asia/Shanghai", "reportDelay": 2000,
              "userId": self.uid, "username": self.nick, "userNickname": self.nick,
              "product": "SaaS", "releaseDate": 1789036585355,
              "commit": "5f9692923c93033111c51ad7b003eb80204a9b75",
              "ideName": "WorkBuddy", "ideType": "WorkBuddy", "ideVersion": "5.5.6",
              "machineId": self.derive_id("machine"), "sessionId": self.derive_id("session"),
              "extName": "workbuddy-desktop", "extVersion": "5.5.6",
              "os": "win32", "arch": "x64", "osVersion": "10.0.26220",
              "cpuCores": 20, "memorySize": 24, "timestamp": now, "presentAt": now}
        arr = []
        for e in events:
            m = dict(e); m.update(fp); arr.append(m)
        body = {"common": {"userId": self.uid, "userNickname": self.nick, "ideName": "WorkBuddy",
                           "ideType": "WorkBuddy", "machineId": fp["machineId"], "mode": "LOCAL",
                           "userAgent": UA, "os": "win32", "timezone": "Asia/Shanghai"},
                "events": arr}
        try:
            s = requests.Session(); s.trust_env = False
            return s.post(BASE + "/v2/report", json=body, timeout=15, verify=False,
                          proxies=_proxies()).status_code
        except Exception:
            return 0

    def webchat(self, conv_name, prompt):
        """真实对话（webchat），返回 (conv_id, 回复文本)"""
        try:
            conv = self.jpost("/console/webchat/conversations",
                              {"name": conv_name + "-" + str(uuid.uuid4())[:8]})
            conv_id = (conv.get("data") or {}).get("conversationId", "")
            payload = {"messages": [{"role": "user", "content": prompt}], "model": "glm-5.2",
                       "stream": True, "conversationId": conv_id}
            headers = dict(self.api().headers)
            headers["Accept"] = "text/event-stream"
            txt = ""
            s = requests.Session(); s.trust_env = False
            with s.post(BASE + "/console/chat/completions", json=payload, timeout=90, verify=False,
                        headers=headers, stream=True, proxies=_proxies()) as r:
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith("data: "):
                        d = line[6:]
                        if d.strip() in ("[DONE]", "[完成]", "[✅完成]"):
                            break
                        try:
                            for c in json.loads(d).get("choices", []):
                                cp = c.get("delta", {}).get("content", "")
                                if cp:
                                    txt += cp
                        except Exception:
                            pass
            return conv_id, txt
        except Exception:
            return "", ""

    # ---------- ✅ 任务 ----------
    def t_sign(self):
        d = self.jpost("/v2/billing/meter/daily-checkin")
        if d.get("code") in (0, 200):
            dd = d.get("data") or {}
            self.log("   ✅签到 +%s积分 连签%s天" % (dd.get("credit", "?"), dd.get("streak_days", "?")))
        else:
            self.log("   ✅签到: %s" % (str(d.get("msg", ""))[:40] or "已签到"))

    def _accept_with_verify(self, code):
        for _ in (1, 2):
            r = self.post("/v2/activity/growth/tasks/accept", {"task_codes": [code]})
            try:
                d = r.json()
                results = (d.get("data") or {}).get("results") or []
                status = (results[0].get("status") or "") if results else (d.get("msg") or "")
            except Exception:
                status = ""
            time.sleep(2)
            if self.prog(code)[0] not in (None, "not_accepted"):
                return True
            time.sleep(WRITE_GAP)
        return False

    def t_accept_all(self):
        todo = [t.get("task_code") for t in self.tasks()
                if isinstance(t, dict) and t.get("accept_status") == "not_accepted"]
        if not todo:
            return
        try:
            d = self.jpost("/v2/activity/growth/tasks/accept", {"task_codes": todo})
            ok = 0
            for x in ((d.get("data") or {}).get("results") or []):
                if isinstance(x, dict) and x.get("status") == "accepted":
                    ok += 1
            self.log("   📋批量接受 %d 项 → 成功 %d" % (len(todo), ok))
        except Exception as e:
            self.log("   📋批量接受异常: %s" % str(e)[:60])
        time.sleep(2)
        pending = [c for c in todo if self.prog(c)[0] in (None, "not_accepted")]
        if not pending:
            self.log("   ✅ 全部登记生效（%d 项）" % len(todo))
            return
        self.log("   🔁 %d 项未落账，逐个重试..." % len(pending))
        still = [c for c in pending if not self._accept_with_verify(c)]
        if still:
            self.log("   ⚠️ 仍无法登记 %d 项: %s" % (len(still), ",".join(still[:8])))
        else:
            self.log("   ✅ 重试后全部登记生效")

    def t_chat_n(self, code, n, prompts):
        for i in range(n):
            st, cur, tgt = self.prog(code)
            if st in ("completed", "claimed") or (cur or 0) >= (tgt or n):
                break
            conv_id, txt = self.webchat(code, prompts[i % len(prompts)])
            if txt:
                now = int(time.time() * 1000)
                rid = "cmb-" + str(uuid.uuid4())
                common = {"userId": self.uid, "userNickname": self.nick, "ideName": "web-Agents",
                          "ideType": "web-Agents", "machineId": self.derive_id("machine"),
                          "mode": "CLOUD", "userAgent": UA, "os": "Win32", "timezone": "Asia/Shanghai"}
                self.report([
                    {"eventCode": "chat_request_send", "timestamp": now, "reportDelay": 0, **common,
                     "conversationId": conv_id, "requestId": rid, "requestModelId": "glm-5.2",
                     "requestModelName": "GLM-5.2", "inputLength": len(prompts[i % len(prompts)]),
                     "customAgentName": ""},
                    {"eventCode": "chat_request_response", "timestamp": now + 100, "reportDelay": 0,
                     **common, "conversationId": conv_id, "requestId": rid,
                     "requestModelId": "glm-5.2", "requestModelName": "GLM-5.2", "toolCallCount": 0,
                     "inputToken": max(1, len(prompts[i % len(prompts)]) // 4),
                     "outputToken": max(1, len(txt) // 4),
                     "totalToken": max(2, (len(prompts[i % len(prompts)]) + len(txt)) // 4)},
                    {"eventCode": "chat_message_send", "timestamp": now + 50, "reportDelay": 0,
                     **common, "conversationId": conv_id, "requestId": rid,
                     "messageId": "cmb-" + str(uuid.uuid4()), "requestModelId": "glm-5.2",
                     "requestModelName": "GLM-5.2", "historyCount": 1, "isContextTruncated": False,
                     "currentStepCount": 1, "traceId": rid, "rootRequestId": rid,
                     "parentConversationId": conv_id, "agentName": "cli", "agentType": "main"}])
            time.sleep(4)
        st, cur, tgt = self.prog(code)
        self.log("   %s(%s): %s %s/%s" % (code, task_cn(code), st, cur, tgt))

    def t_canvas_automation(self):
        st, _, _ = self.prog("create_canvas")
        if st not in ("completed", "claimed"):
            self.report([{"eventCode": "agent_task_created", "source": "CLOUD", "name": "",
                          "mode": "craft", "requestModelId": "default", "task_mode": "design"},
                         {"eventCode": "wbx_design_canvas_task_create"}])
            time.sleep(3)
        st, _, _ = self.prog("automation_1")
        if st not in ("completed", "claimed"):
            self.report([{"eventCode": "agent_task_created", "source": "CLOUD", "name": "",
                          "mode": "craft", "requestModelId": "default", "task_mode": "automation",
                          "isAutomationBackground": True},
                         {"eventCode": "automated_task_create_suc", "action": "create"},
                         {"eventCode": "automated_task_execute", "action": "execute"}])
            time.sleep(3)
        st, _, _ = self.prog("playbook_prompt")
        if st not in ("completed", "claimed"):
            self.report([{"eventCode": "playbook_prompt_send", "ext1": str(uuid.uuid4()),
                          "requestId": str(uuid.uuid4()), "id": "01-ProductDesign", "name": "产品设计",
                          "type": "other", "promptLength": 30, "isOfficial": 1,
                          "source": "growth-center"}])
            time.sleep(3)
        self.log("   设计/自动化/灵感: %s / %s / %s" % (self.prog("create_canvas")[0],
                                                       self.prog("automation_1")[0],
                                                       self.prog("playbook_prompt")[0]))

    def t_expert_5(self):
        st0, cur0, tgt0 = self.prog("expert_5")
        need = 0 if st0 in ("completed", "claimed") else max(0, (tgt0 or 5) - (cur0 or 0))
        for i in range(need):
            st, cur, tgt = self.prog("expert_5")
            if st in ("completed", "claimed") or (cur or 0) >= (tgt or 5):
                break
            eid = "expert-" + str(uuid.uuid4())[:8]
            self.report([
                {"eventCode": "expert_summoned", "id": eid, "name": "Expert", "type": "agent",
                 "expertTitle": "", "expertType": "agent"},
                {"eventCode": "expert_actual_use", "id": eid, "name": "Expert", "type": "",
                 "expertType": "agent", "source": "builtin", "version": "", "cost": 0,
                 "characterCount": 12, "conversationId": "conv-" + str(uuid.uuid4()),
                 "requestId": str(uuid.uuid4()), "messageId": "msg-" + str(uuid.uuid4()),
                 "requestModelId": "deepseek-v4-flash", "requestModelName": "DeepSeek V4 Flash"}])
            time.sleep(3)
        st, cur, tgt = self.prog("expert_5")
        self.log("   召唤5次专家: %s %s/%s" % (st, cur, tgt))

    def t_template_5(self):
        scenes = [("01-ProductDesign", "产品设计"), ("02-Marketing", "营销文案"),
                  ("03-DataAnalysis", "数据分析"), ("04-CodeReview", "代码审查"),
                  ("05-Report", "报告撰写")]
        for tid, tname in scenes:
            st, cur, tgt = self.prog("template_5")
            if st in ("completed", "claimed") or (cur or 0) >= (tgt or 5):
                break
            self.report([
                {"eventCode": "agent_task_created", "source": "CLOUD", "name": "", "mode": "craft",
                 "requestModelId": "default", "action": tid, "has_template": True,
                 "template_id": tid, "template_name": tname},
                {"eventCode": "agent_task_created_with_template", "templateId": tid,
                 "templateName": tname, "isCustomModel": True, "id": tid, "name": tname},
                {"eventCode": "playbook_prompt_send", "ext1": str(uuid.uuid4()),
                 "requestId": str(uuid.uuid4()), "id": tid, "name": tname, "type": "other",
                 "promptLength": 30, "isOfficial": 1, "source": "growth-center"}])
            time.sleep(2)
        st, cur, tgt = self.prog("template_5")
        self.log("   使用5个模板: %s %s/%s" % (st, cur, tgt))

    def t_buddy_apps(self):
        for task in ("Buddy_App", "Buddy_App_QQ"):
            st, _, _ = self.prog(task)
            if st in ("completed", "claimed"):
                continue
            bid = QQ_TPL if "QQ" in task else "buddy-app-default"
            bname = "企鹅教师助手" if "QQ" in task else "发现应用"
            evs = [{"eventCode": "buddyapp_discover_click", "mode": "LOCAL", "buddyId": bid, "buddyName": bname},
                   {"eventCode": "buddyapp_show", "mode": "LOCAL", "buddyId": bid, "buddyName": bname,
                    "elementId": bid, "elementName": bname, "position": 2},
                   {"eventCode": "buddyapp_enter_click", "mode": "LOCAL", "buddyId": bid, "buddyName": bname,
                    "elementId": bid, "elementName": bname, "position": 2, "isFirstPage": "1"},
                   {"eventCode": "buddyapp_auth_confirm_click", "mode": "LOCAL", "buddyId": bid,
                    "buddyName": bname, "elementId": bid, "elementName": bname},
                   {"eventCode": "buddyapp_bindaccount_skip_click", "mode": "LOCAL", "buddyId": bid,
                    "buddyName": bname, "elementId": bid, "elementName": bname}]
            self.report_desktop(evs)
            time.sleep(WRITE_GAP)
        self.log("   发现应用/企鹅教师助手: %s / %s" % (self.prog("Buddy_App")[0],
                                                      self.prog("Buddy_App_QQ")[0]))

    def t_theme(self):
        st, _, _ = self.prog("Hp_Appearance")
        if st is None:
            return
        if st in ("completed", "claimed"):
            return
        d = self.jpost("/portal/user-asset/appearance/set",
                       {"kind": "theme", "resource_key": THEME_KEY})
        if d.get("code") == 0:
            time.sleep(2)
            self.report([{"eventCode": "appearance_skin_apply", "action": "apply",
                          "source": "settings_close", "id": THEME_KEY, "vipLevel": "free",
                          "series": "craft", "type": "personal"}])
            time.sleep(6)
        self.log("   和平精英主题: %s" % self.prog("Hp_Appearance")[0])

    def t_library(self):
        st, _, _ = self.prog("Library_read")
        if st is None or st in ("completed", "claimed"):
            return
        self.report_web_event("web_element_click", LIB_DOC_URL,
                              "library_doc_intro_click", "WorkBuddy资料库介绍")
        time.sleep(6)
        self.log("   体验资料库: %s" % self.prog("Library_read")[0])

    def t_black_cat(self):
        st, _, _ = self.prog("black_cat")
        if st in ("completed", "claimed"):
            return
        if not within_night_window():
            self.log("   夜猫子: 仅23:00-08:00计数，当前北京时间%d点，跳过" % beijing_now().hour)
            return
        prompts = ["今天天气怎么样？", "1+1等于几？", "讲个笑话"]
        for attempt in range(3):
            conv_id, txt = self.webchat("night", prompts[attempt % len(prompts)])
            if txt:
                self.report([{"eventCode": "chat_request_send", "timestamp": int(time.time() * 1000),
                              "conversationId": conv_id, "requestId": "cmb-" + str(uuid.uuid4()),
                              "requestModelId": "glm-5.2", "requestModelName": "GLM-5.2",
                              "inputLength": 14}])
                self.log("   夜猫子: 第%d次对话 ✅（回复%d字）" % (attempt + 1, len(txt)))
                break
            time.sleep(5)
        st, cur, tgt = self.prog("black_cat")
        self.log("   夜猫子: %s %s/%s" % (st, cur, tgt))

    # ---------- 小程序任务（+400c+15e） ----------
    def mp_machine_id(self):
        h = hashlib.md5(("mp:%s" % self.uid).encode()).hexdigest()
        return "%s-%s-%s-%s-%s" % (h[:8], h[8:12], h[12:16], h[16:20], h[20:32])

    def mp_report(self, events):
        now = int(time.time() * 1000)
        base = {"timestamp": now, "ideType": "WorkBuddy_MP", "ideVersion": "2.4.0",
                "extName": "workbuddy-mp", "extVersion": "2.4.0", "product": "SaaS",
                "ideName": "wx_app_cloud", "platform": "mini_program", "os": "windows",
                "osVersion": "11", "arch": "x64", "machineId": self.mp_machine_id(),
                "timezone": "Asia/Shanghai", "userId": self.uid, "userNickname": self.nick}
        arr = []
        for e in events:
            m = dict(base); m.update(e); arr.append(m)
        hdr = dict(MP_REPORT_HEADERS)
        hdr["Authorization"] = "Bearer " + self.at
        if self.uid:
            hdr["X-User-Id"] = self.uid
        try:
            s = requests.Session(); s.trust_env = False
            return s.post("https://www.codebuddy.cn/v2/report", json=arr, headers=hdr,
                          timeout=20, verify=False, proxies=_proxies()).status_code
        except Exception:
            return 0

    def _mp_do_task(self, code, label, events_fn):
        st, cur, tgt = self.prog(code, headers=MP_HEADER)
        if st is None:
            self.log("   %s: mp 口径未下发，跳过" % label)
            return
        if st in ("completed", "claimed"):
            if st == "completed":
                self._mp_claim(code)
            else:
                self.log("   %s: 已领取，跳过" % label)
            return
        if st == "not_accepted":
            d = self.jpost("/v2/activity/growth/tasks/accept", {"task_codes": [code]}, headers=MP_HEADER)
            results = (d.get("data") or {}).get("results") or []
            if not (results and results[0].get("status") == "accepted"):
                self.log("   %s: accept 失败，跳过" % label)
                return
            time.sleep(WRITE_GAP)
        try:
            evs = events_fn()
            code_http = self.mp_report(evs)
            self.log("   %s: 判据已上报（HTTP %s，%d 事件）" % (label, code_http, len(evs)))
            time.sleep(2.5)
            st2, cur2, tgt2 = self.prog(code, headers=MP_HEADER)
            if st2 in ("completed", "claimed"):
                self.log("   %s: ✅ 已完成 %s/%s" % (label, cur2, tgt2))
                if st2 == "completed":
                    self._mp_claim(code)
            else:
                self.log("   %s: %s %s/%s（服务端暂未关联）" % (label, st2, cur2, tgt2))
        except Exception as e:
            self.log("   %s: 失败 %s" % (label, str(e)[:60]))

    def _mp_claim(self, code):
        r = self.post("/activity/growth/tasks/%s/claim" % code, {}, headers=MP_HEADER)
        try:
            d = r.json().get("data", {})
            self.log("   🎁领奖[%s]: %s" % (code, "已领过" if d.get("already_claimed")
                                            else "+%s积分+%s能量" % (d.get("credit"), d.get("energy"))))
        except Exception:
            pass

    def t_mp_tasks(self):
        def ev_chat():
            rid = "wb2api-" + str(uuid.uuid4())
            cid = "wbmp-" + str(uuid.uuid4())
            return [{"eventCode": "chat_request_send", "inputLength": 14, "isPlan": False,
                     "isAutoExecuteTerminal": False, "isAutoModify": False, "codebaseEnable": False,
                     "maxToken": 0, "maxSteps": 500, "temperature": 0, "maxRetries": 0,
                     "mentionContexts": [], "knowledgeId": [], "knowledgeName": [],
                     "codebaseId": "", "mentionContextCount": 0, "command": "", "recommendId": "",
                     "skillId": "", "skillCount": 0, "totalCount": 0, "traceId": rid,
                     "rootRequestId": rid, "parentConversationId": cid, "conversationId": cid,
                     "messageId": "msg-" + rid[-8:], "agentName": "mp", "agentType": "main",
                     "codebuddy.session_id": cid, "codebuddy.conversation_request_id": rid}]

        def ev_expert():
            rid = "wb2api-" + str(uuid.uuid4())
            cid = "wbmp-" + str(uuid.uuid4())
            eid = "expert-school-01"
            ename = "开学季助手"
            base_chat = {"eventCode": "chat_request_send", "inputLength": 14, "isPlan": False,
                         "isAutoExecuteTerminal": False, "isAutoModify": False, "codebaseEnable": False,
                         "maxToken": 0, "maxSteps": 500, "temperature": 0, "maxRetries": 0,
                         "mentionContexts": [], "knowledgeId": [], "knowledgeName": [],
                         "codebaseId": "", "mentionContextCount": 0, "command": "", "recommendId": "",
                         "skillId": "", "skillCount": 0, "totalCount": 0, "traceId": rid,
                         "rootRequestId": rid, "parentConversationId": cid, "conversationId": cid,
                         "messageId": "msg-" + rid[-8:], "agentName": "mp", "agentType": "main",
                         "expertId": eid, "expertName": ename,
                         "codebuddy.session_id": cid, "codebuddy.conversation_request_id": rid}
            return [
                {"eventCode": "expert_summon_click", "id": eid, "name": eid, "expertTitle": ename,
                 "type": SCHOOL_EXPERT_CATEGORY, "position": 0},
                {"eventCode": "expert_summoned", "id": eid, "name": eid, "expertTitle": ename},
                {"eventCode": "expert_actual_use", "id": eid, "name": eid, "expertTitle": ename,
                 "type": SCHOOL_EXPERT_CATEGORY, "characterCount": 14, "expertType": "builtin"},
                base_chat]

        self._mp_do_task("Sequential_Tasks_1", "小程序对话", ev_chat)
        self._mp_do_task("Sequential_Tasks_2", "小程序专家对话", ev_expert)
        self._mp_do_task("school_season", "校园日活动", ev_chat)

    def t_unknown_tasks(self):
        known = set(TASK_NAME_CN.keys())
        for t in self.tasks():
            if not isinstance(t, dict):
                continue
            code = t.get("task_code", "")
            st = t.get("accept_status", "")
            if code in known or st in ("claimed", "completed"):
                continue
            desc = str(t.get("task_desc", ""))[:40]
            title = str(t.get("title", ""))
            if "subscribe" in code.lower() or "公众号" in (title + desc):
                self.log("   ⚠️需手动: %s %s — 需微信扫码关注公众号" % (code, title))
            elif "donat" in code.lower() or "捐款" in desc or "公益" in title:
                self.log("   ⚠️需手动: %s %s — 涉及真实捐款" % (code, title))
            else:
                self.log("   ⚠️未覆盖新任务: %s %s (%s)" % (code, title, desc))

    # ---------- 🎮 互动玩法 ----------
    def p_lottery(self):
        try:
            d = self.jget("/v2/activity/growth/lottery/chances")
            cd = d.get("data") or {}
            chances = cd.get("balance", cd.get("chances", cd.get("remaining", 0)))
            if not chances or chances <= 0:
                self.log("   🎰抽奖: 无次数")
                return
            won = []
            for i in range(int(chances)):
                if i > 0:
                    time.sleep(2)
                rr = self.jpost("/v2/activity/growth/lottery/draw",
                                {"client_token": "draw-" + str(uuid.uuid4())})
                if rr.get("code") == 0:
                    won.append(str((rr.get("data") or {}).get("prize_name", "?")))
                else:
                    break
            self.log("   🎰抽奖: %s" % ("、".join(won) if won else "无结果"))
        except Exception as e:
            self.log("   🎰抽奖异常: %s" % str(e)[:50])

    def p_blindbox(self):
        try:
            q = self.jget("/v2/activity/growth/buddy/quota")
            qd = q.get("data") or {}
            affordable = qd.get("affordable", 0)
            if not affordable or affordable <= 0:
                self.log("   📦盲盒: 能量不足 (%s/10)" % qd.get("balance", "?"))
                return
            got = []
            for _ in range(min(affordable, 5)):
                rr = self.jpost("/v2/activity/growth/buddy/open", {"count": 1})
                if rr.get("code") != 0:
                    break
                results = (rr.get("data") or {}).get("results", [])
                if results:
                    it = results[0]
                    ins = it.get("instance", {}) or {}
                    tpl = it.get("template", {}) or {}
                    got.append("%s(%s)" % (ins.get("name", tpl.get("name", "?")),
                                           ins.get("rarity", tpl.get("rarity", ""))))
                time.sleep(1.5)
            self.log("   📦盲盒: %s" % ("、".join(got) if got else "开启失败"))
        except Exception as e:
            self.log("   📦盲盒异常: %s" % str(e)[:50])

    def p_buddy_info(self):
        try:
            r = self.jget("/v2/activity/growth/buddy/info")
            if r.get("code") == 0:
                b = (r.get("data") or {}).get("buddy", r.get("data") or {}) or {}
                self.log("   🐱Buddy: %s (%s)%s" % (b.get("name", "?"), b.get("rarity", ""),
                                                    ", " + str(b.get("personality", "")) if b.get("personality") else ""))
        except Exception:
            pass

    def p_travel(self):
        try:
            vis = self.jget("/v2/activity/growth/buddy/visible")
            if vis.get("code") == 0:
                vd = vis.get("data") or {}
                if not vd.get("buddy_visible", True) or not vd.get("has_buddy", True):
                    self.log("   🐾旅行: 无Buddy，跳过")
                    return
            st = self.jget("/v2/activity/growth/buddy/travel/status")
            if st.get("code") != 0:
                self.log("   🐾旅行: 状态获取失败")
                return
            sd = st.get("data") or {}
            state = sd.get("state", "idle")
            if state == "arrived":
                rr = self.jpost("/v2/activity/growth/buddy/travel/claim")
                if rr.get("code") == 0:
                    self.log("   🐾旅行: 🎉领取礼物 +%s积分" % (rr.get("data") or {}).get("reward_credit", 0))
                else:
                    self.log("   🐾旅行: 领取失败 %s" % str(rr.get("msg", ""))[:40])
                return
            if state == "traveling":
                remain = max(0, (sd.get("arrive_at", 0) - sd.get("server_now", 0)) // 60)
                self.log("   🐾旅行: 旅行中，约%s分钟后到达" % remain)
                return
            if sd.get("daily_limit_reached"):
                self.log("   🐾旅行: 今日次数已用尽")
                return
            cfg = self.jget("/v2/activity/growth/buddy/travel/config")
            locs = (cfg.get("data") or {}).get("locations", [])
            if not locs:
                self.log("   🐾旅行: 无目的地")
                return
            rr = self.jpost("/v2/activity/growth/buddy/travel/depart",
                            {"location_id": locs[0].get("id")})
            if rr.get("code") == 0:
                rd = rr.get("data") or {}
                self.log("   🐾旅行: ✅已出发，约%s小时后到达" %
                         max(0, (rd.get("arrive_at", 0) - rd.get("server_now", 0)) // 3600))
            else:
                self.log("   🐾旅行: 出发失败 %s" % str(rr.get("msg", ""))[:40])
        except Exception as e:
            self.log("   🐾旅行异常: %s" % str(e)[:50])

    def p_redeem(self):
        days = self.streak_days
        for tier, need, label in (("7d", 7, "入门"), ("14d", 14, "进阶"), ("28d", 28, "巅峰")):
            if days is not None and days < need:
                continue
            rr = self.jpost("/v2/activity/growth/redeem",
                            {"tier": tier, "client_token": "redeem-" + tier + "-" + str(uuid.uuid4())})
            code = rr.get("code", -1)
            if code == 0:
                d = rr.get("data") or {}
                self.log("   🎁兑换%s档: +%s积分 +%s能量 +%s抽奖" % (
                    label, d.get("credit_granted", 0), d.get("energy_granted", 0), d.get("chances_granted", 0)))
            elif code == 409:
                self.log("   🎁兑换%s档: 已兑换过" % label)

    def p_badges(self):
        try:
            r = self.jget("/v2/activity/growth/badges")
            badges = (r.get("data") or {}).get("badges") or (r.get("data") or {}).get("list") or []
            self.log("   🏅徽章: %s个" % sum(1 for b in badges if isinstance(b, dict) and b.get("earned")))
        except Exception:
            pass

    def p_gift(self):
        try:
            r = self.jpost("/billing/meter/claim-gift")
            if r.get("code") == 0:
                self.log("   🎊新手礼包: +%s积分" % (r.get("data") or {}).get("credit", "?"))
        except Exception:
            pass
        try:
            r = self.jpost("/billing/meter/claim-compensation")
            if r.get("code") == 0:
                self.log("   🎊补偿领取: +%s积分" % (r.get("data") or {}).get("credit", "?"))
        except Exception:
            pass

    def p_makeup(self):
        try:
            hm = (self.jget("/v2/activity/growth/heatmap").get("data") or {}).get("cells", [])
            bal = ((self.jget("/v2/activity/growth/streak").get("data") or {}).get("makeup_cards") or {}).get("balance", 0)
            yesterday = (beijing_now().date() - datetime.timedelta(days=1)).isoformat()
            missed = None
            for c in hm:
                if str(c.get("date", ""))[:10] == yesterday and not c.get("score", 0):
                    missed = yesterday
                    break
            if missed and bal > 0:
                r = self.jpost("/v2/activity/growth/makeup-cards/use", {"target_date": missed})
                self.log("   🩹补签%s: %s" % (missed, "成功，连签保住" if r.get("code") == 0 else str(r.get("msg", ""))[:40]))
            elif missed:
                self.log("   🩹昨日(%s)漏签但无补签卡" % missed)
            else:
                self.log("   🩹无漏签，无需补签")
        except Exception as e:
            self.log("   🩹补签检查异常: %s" % str(e)[:50])

    def p_first_buddy(self):
        st, _, _ = self.prog("first_buddy")
        if st in ("completed", "claimed"):
            return
        try:
            self.report([{"eventCode": "buddy_agreement_view", "timestamp": int(time.time() * 1000)}])
            time.sleep(2)
            self.post("/v2/activity/growth/buddy/agreement", {"agree": True})
            time.sleep(WRITE_GAP)
            r = self.jpost("/v2/activity/growth/buddy/first")
            d = r.get("data") or {}
            self.log("   🐱首只Buddy: %s (credit=+%s energy=+%s)" % (
                "成功" if r.get("code") == 0 else str(r.get("msg", ""))[:40],
                d.get("credit", 0), d.get("energy", 0)))
        except Exception as e:
            self.log("   🐱首只Buddy异常: %s" % str(e)[:40])

    # ---------- 🎁 领奖 ----------
    def claim_all(self):
        n = 0
        for t in self.tasks():
            if isinstance(t, dict) and t.get("accept_status") == "completed":
                code = t.get("task_code", "")
                r = self.post("/activity/growth/tasks/%s/claim" % code, {})
                if r is not None and r.status_code == 400:
                    r = self.post("/activity/growth/tasks/%s/claim" % code, {},
                                  headers={"Origin": BASE, "Referer": BASE + "/profile/growth-center",
                                           "x-client-platform": "web"})
                try:
                    d = r.json().get("data", {})
                    self.log("   🎁领奖[%s]: %s" % (task_cn(code), "已领过" if d.get("already_claimed")
                                                    else "+%s积分+%s能量" % (d.get("credit"), d.get("energy"))))
                except Exception:
                    self.log("   🎁领奖[%s]: 失败" % task_cn(code))
                n += 1
                time.sleep(1)
        if n == 0:
            self.log("   无待领奖励")

    # ---------- 编排 ----------
    def run(self, mode="all"):
        """mode: all / task / play / claim / query"""
        if not self.ensure_token():
            return {"ok": False, "note": self.name, "detail": "Token 不可用"}
        self.log("╭─ 👤 %s（%s）" % (self.name, mask_str(self.phone)))
        credits = self.query_credits()
        usage = self.query_usage()
        growth = self.query_growth()
        self.log("💰 积分: %s" % credits)
        self.log("📊 用量: %s" % usage)
        self.log("🌱 成长: %s" % growth)

        if mode == "query":
            tl = [{"code": t.get("task_code", ""), "status": t.get("accept_status", ""),
                   "cur": (t.get("progress") or {}).get("current"),
                   "tgt": (t.get("progress") or {}).get("target")}
                  for t in self.tasks() if isinstance(t, dict)]
            return {"ok": True, "note": self.name, "credits": credits, "usage": usage,
                    "growth": growth, "tasks": tl}

        if mode in ("all", "task"):
            self.log("  ✅ ── 成长任务 ──")
            self.t_accept_all()
            self.t_sign()
            self.t_canvas_automation()
            self.t_expert_5()
            self.t_template_5()
            self.t_buddy_apps()
            self.t_theme()
            self.t_library()
            self.t_chat_n("Model_chat_GLM5.2", 1, ["你好，请介绍一下你自己"])
            self.t_chat_n("chat_5", 5, ["你好", "今天天气怎么样？", "1+1等于几？", "Python是什么？", "推荐一本好书"])
            self.t_black_cat()
            self.t_mp_tasks()
            self.t_unknown_tasks()

        if mode in ("all", "play"):
            self.log("  🎮 ── 互动玩法 ──")
            self.p_lottery()
            self.p_blindbox()
            self.p_buddy_info()
            self.p_travel()
            self.p_redeem()
            self.p_badges()
            self.p_gift()
            self.p_makeup()
            self.p_first_buddy()

        if mode in ("all", "task", "play", "claim"):
            self.log("  🎁 ── 领奖 ──")
            self.claim_all()

        ts = self.tasks()
        done = sum(1 for t in ts if isinstance(t, dict) and t.get("accept_status") in ("claimed", "completed"))
        rest = [task_cn(t.get("task_code", "")) for t in ts
                if isinstance(t, dict) and t.get("accept_status") not in ("claimed", "completed")]
        self.log("🏁 %s: 完成%s/%s，剩余: %s" % (self.name, done, len(ts), "、".join(rest) if rest else "无"))
        return {"ok": True, "note": self.name, "credits": credits, "usage": usage,
                "growth": growth, "done": done, "total": len(ts), "rest": rest}


# ============================================================
# 面板配置 & 青龙/呆呆 Open API（范式来自小米钱包插件）
# ============================================================
def get_config():
    qlname = bucket_get(BUCKET, "s_wb_qlname") or ""
    ddname = bucket_get(BUCKET, "s_wb_ddname") or ""
    osname = bucket_get(BUCKET, "s_wb_osname") or "WORKBUDDY_REFRESH_TOKEN"
    proxy = bucket_get(BUCKET, "s_wb_proxy") or ""
    push = bucket_get(BUCKET, "s_wb_push") or ""
    return qlname, ddname, osname.strip() or "WORKBUDDY_REFRESH_TOKEN", proxy, push


s_wb_qlname, s_wb_ddname, s_wb_osname, s_wb_proxy, s_wb_push = get_config()

QLurl = ""
qltoken = ""
PANEL_KIND = "ql"
PANEL_BASE = ""


def _resp_ok(rj):
    if not isinstance(rj, dict):
        return False
    if "code" in rj:
        return str(rj.get("code")) in ("200", "201", "0", "0000")
    if "success" in rj:
        return rj.get("success") is not False
    return True


def _env_id(env):
    return env.get("id") if env.get("id") is not None else env.get("ID")


def DDtoken(host, app_key, app_secret):
    try:
        r = requests.post(host.rstrip("/") + "/api/open-api/token",
                          json={"app_key": app_key, "app_secret": app_secret},
                          headers={"Content-Type": "application/json"},
                          timeout=20, proxies={"http": None, "https": None})
        if r.status_code != 200:
            raise RuntimeError("呆呆面板认证失败 HTTP %s" % r.status_code)
        data = r.json().get("data") or {}
        if not data.get("access_token"):
            raise RuntimeError("获取呆呆Token失败，请检查 app_key / app_secret")
        return data["access_token"]
    except requests.exceptions.RequestException:
        raise RuntimeError("连接呆呆面板失败，请检查地址/网络")


def QLtoken(QLurl_, ClientID, ClientSecret):
    try:
        r = requests.get("%s/open/auth/token?client_id=%s&client_secret=%s" % (QLurl_, ClientID, ClientSecret),
                         proxies={"http": None, "https": None}, timeout=20)
        if r.status_code != 200:
            raise RuntimeError("青龙API请求失败 HTTP %s" % r.status_code)
        data = r.json().get("data") or {}
        if "token" not in data:
            raise RuntimeError("获取青龙Token失败，请检查 ClientID / ClientSecret")
        return data["token"]
    except requests.exceptions.RequestException:
        raise RuntimeError("连接青龙面板失败，请检查地址/网络")


def seekql():
    """解析面板配置并鉴权，设置全局 PANEL_KIND / PANEL_BASE"""
    global QLurl, qltoken, PANEL_KIND, PANEL_BASE
    try:
        if len(s_wb_ddname) > 0:
            dd = s_wb_ddname.split("丨")
            if len(dd) != 3:
                raise RuntimeError("呆呆配置格式错误，应为 Host丨app_key丨app_secret")
            host, ak, as_ = dd[0].strip().rstrip("/"), dd[1].strip(), dd[2].strip()
            if not all([host, ak, as_]) or not host.startswith(("http://", "https://")):
                raise RuntimeError("呆呆配置参数不完整或地址格式错误")
            qltoken = DDtoken(host, ak, as_)
            QLurl, PANEL_KIND, PANEL_BASE = host, "dd", host + "/api"
            return QLurl, qltoken
        if len(s_wb_qlname) == 0:
            raise RuntimeError("未配置面板信息（青龙或呆呆二选一）")
        ql = s_wb_qlname.split("丨")
        if len(ql) != 3:
            raise RuntimeError("青龙配置格式错误，应为 Host丨ClientID丨ClientSecret")
        host, cid, csec = ql[0].strip().rstrip("/"), ql[1].strip(), ql[2].strip()
        if not all([host, cid, csec]) or not host.startswith(("http://", "https://")):
            raise RuntimeError("青龙配置参数不完整或地址格式错误")
        qltoken = QLtoken(host, cid, csec)
        QLurl, PANEL_KIND, PANEL_BASE = host, "ql", host + "/open"
        return QLurl, qltoken
    except Exception as e:
        sender.reply("=====连接失败=====\n❌ 无法连接面板\n------------------\n%s\n==================" % str(e))
        raise


def _headers():
    return {"Authorization": "Bearer " + qltoken, "accept": "application/json",
            "Content-Type": "application/json"}


def delenvs(env_id):
    if env_id is None or not QLurl or not qltoken:
        return
    if PANEL_KIND == "dd":
        requests.delete("%s/envs/%s" % (PANEL_BASE, env_id), headers=_headers(),
                        proxies={"http": None, "https": None}, timeout=20)
    else:
        requests.delete("%s/envs" % PANEL_BASE, headers=_headers(), json=[env_id],
                        proxies={"http": None, "https": None}, timeout=20)


def allenvs(osname, account):
    """定位变量 id：先按 remarks 里的用户标识精确匹配；
    匹配不到时，若同名变量**恰好只有一个**（用户在面板手建的、无 remarks），复用它，
    避免每次同步都新建同名变量导致重复堆积。同名多个则不动（可能是别人的）。"""
    if not QLurl or not qltoken:
        return None
    r = requests.get("%s/envs" % PANEL_BASE, headers=_headers(),
                     proxies={"http": None, "https": None}, timeout=20).json()
    if not _resp_ok(r):
        raise RuntimeError("连接面板获取变量失败")
    envs = r.get("data") or []
    for env in envs:
        if env.get("name") == osname and str(account) in str(env.get("remarks") or ""):
            return _env_id(env)
    same_name = [e for e in envs if e.get("name") == osname]
    if len(same_name) == 1:
        return _env_id(same_name[0])
    return None


def QLupdate(osname, value, account, env_id):
    data = {"value": value, "name": osname,
            "remarks": "WB:%s丨WorkBuddy签到" % account}
    if PANEL_KIND == "dd":
        r = requests.put("%s/envs/%s" % (PANEL_BASE, env_id), headers=_headers(), json=data,
                         proxies={"http": None, "https": None}, timeout=20)
    else:
        d = dict(data); d["id"] = env_id
        r = requests.put("%s/envs" % PANEL_BASE, headers=_headers(), json=d,
                         proxies={"http": None, "https": None}, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError("更新面板变量失败 HTTP %s" % r.status_code)
    d2 = r.json().get("data")
    if isinstance(d2, list):
        d2 = d2[0] if d2 else None
    return _env_id(d2) if d2 else None


def QLzt(osname, value, account):
    env = {"value": value, "name": osname, "remarks": "WB:%s丨WorkBuddy签到" % account}
    payload = env if PANEL_KIND == "dd" else [env]
    r = requests.post("%s/envs" % PANEL_BASE, headers=_headers(), json=payload,
                      proxies={"http": None, "https": None}, timeout=20)
    if r.status_code not in (200, 201):
        raise RuntimeError("添加变量失败 HTTP %s" % r.status_code)
    res = r.json()
    if not _resp_ok(res):
        raise RuntimeError("面板返回错误: %s" % (res.get("message") or res.get("error")))
    d = res.get("data")
    if isinstance(d, list):
        return _env_id(d[0]) if d and isinstance(d[0], dict) else None
    return _env_id(d) if isinstance(d, dict) else None


def Addenvs(osname, value, account):
    if not QLurl or not qltoken:
        return
    env_id = allenvs(osname, account)
    if env_id is None:
        QLzt(osname, value, account)
    else:
        QLupdate(osname, value, account, env_id)


# ============================================================
# 账号存储 & 面板同步
# ============================================================
def load_accounts():
    raw = bucket_get(BUCKET_USER, userid) or "[]"
    try:
        accs = json.loads(raw)
        if not isinstance(accs, list):
            accs = []
    except Exception:
        accs = []
    return accs


def save_accounts(accs):
    bucket_set(BUCKET_USER, userid, json.dumps(accs, ensure_ascii=False))


def build_env_value(accs):
    """拼成 WORKBUDDY_REFRESH_TOKEN：每行 手机号:AT:RT"""
    return "\n".join("%s:%s:%s" % (a.get("phone", ""), a.get("at", ""), a.get("rt", ""))
                     for a in accs if a.get("rt"))


def sync_to_panel(accs):
    """把全部账号同步到面板（单变量，多账号换行分隔）"""
    if not (s_wb_qlname or s_wb_ddname):
        return False, "未配置面板(青龙/呆呆)，仅本地保存"
    try:
        seekql()
        value = build_env_value(accs)
        if not value:
            env_id = allenvs(s_wb_osname, userid)
            if env_id is not None:
                delenvs(env_id)
            return True, "已清空面板变量"
        Addenvs(osname=s_wb_osname, value=value, account=userid)
        return True, "已同步到面板变量 %s" % s_wb_osname
    except Exception as e:
        return False, "同步失败: %s" % str(e)[:80]


def upsert_account(accs, phone, at, rt, name=""):
    """按手机号去重覆盖"""
    key = phone or (jwt_user(at) if at else "")
    accs = [a for a in accs if (a.get("phone") or "") != key]
    accs.append({"name": name or mask_str(phone or key), "phone": key, "at": at, "rt": rt,
                 "updated": time.strftime("%Y-%m-%d %H:%M")})
    return accs


def store_login(phone, at, rt, name="", src="登录", verified=None):
    """登录成功后的统一落库 + 面板同步"""
    accs = upsert_account(load_accounts(), phone, at, rt, name)
    save_accounts(accs)
    ok, msg = sync_to_panel(accs)
    who = jwt_user(at) or phone
    vtxt = {True: "✅ 可用", False: "⚠️ 不可用（不影响登录，续期会重试）",
            None: "—"}.get(verified, "—")
    sender.reply("""
=====%s成功=====
✅ 账号: %s
👤 身份: %s
🔑 AT 有效期至: %s
🔄 RT 校验: %s
📦 当前共: %d 个账号
🌐 面板同步: %s
------------------
发送「wb查询」查看积分/用量/成长
发送「wb运行」执行全流程""" % (src, mask_str(phone), mask_str(who), _exp_str(at), vtxt, len(accs), msg))


def _exp_str(at):
    try:
        return datetime.datetime.fromtimestamp(int(_jwt_payload(at).get("exp", 0))).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


# ============================================================
# 短信登录（移植自 workbuddy_login.py 插件接口）
# ============================================================
def _sms_headers():
    """登录接口请求头（与 workbuddy_login.py 一致，UA 用纯 Chrome 指纹）"""
    return {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
            "Origin": BASE, "Referer": BASE + "/", "User-Agent": LOGIN_UA}


def send_sms(phone):
    """发送短信验证码，返回 (ok, 提示信息)；失败信息带排查建议"""
    try:
        s = requests.Session(); s.trust_env = False
        r = s.post(SEND_SMS_URL, headers=_sms_headers(), json={"phone": phone},
                   timeout=20, verify=False, proxies=_proxies())
        d = r.json()
    except Exception as e:
        return False, "请求异常: %s" % str(e)[:80]
    if d.get("code") == 0:
        return True, "已发送，有效期 %s 秒" % ((d.get("data") or {}).get("expires_in", 300))
    msg = str(d.get("msg", "未知错误"))[:80]
    low = msg.lower()
    if "keycloak spi" in low or "400" in low:
        msg += "（手机号格式有误，或该号码暂不支持短信登录）"
    elif "频繁" in msg or "frequent" in low or "too many" in low:
        msg += "（发送过于频繁，请稍后再试）"
    return False, msg


def sms_login(phone, code):
    """手机号+验证码登录，返回 ({at, rt}, err)"""
    try:
        s = requests.Session(); s.trust_env = False
        r = s.post(LOGIN_URL, headers=_sms_headers(),
                   json={"login_method": "phone", "phone": phone, "sms_code": code},
                   timeout=30, verify=False, proxies=_proxies())
        d = r.json()
    except Exception as e:
        return None, "请求异常: %s" % str(e)[:80]
    if d.get("code") != 0:
        msg = str(d.get("msg", "登录失败"))[:80]
        low = msg.lower()
        if "code" in low or "验证码" in msg or "expire" in low:
            msg += "（验证码可能已过期或输入有误，请重新发送后尽快输入）"
        return None, msg
    data = d.get("data") or {}
    at = data.get("accessToken") or data.get("access_token") or ""
    rt = data.get("refreshToken") or data.get("refresh_token") or ""
    if not at or not rt:
        return None, "响应缺少 accessToken / refreshToken"
    return {"at": at, "rt": rt}, ""


def verify_rt(rt):
    """用 RT 调一次刷新接口，确认凭据真的能续期（等价于 workbuddy_login.py --verify）"""
    return refresh_one(rt)[0] != ""


def wb_sms_login(args=None):
    """短信验证码登录：手机号 → 验证码 → AT/RT
    支持直接带参：wb短信 13800138000 123456（面板 / 命令行均可）
    """
    args = args or []
    phone = args[0] if args and re.match(r"^1\d{10}$", str(args[0]).strip()) else ""
    code = args[1] if len(args) > 1 and str(args[1]).strip().isdigit() else ""

    if not phone:
        sender.reply("=====短信登录=====\n请输入 WorkBuddy 手机号:\n（也可直接发送: wb短信 手机号 验证码）\n回复 'q' 退出")
        phone = sender.listen(120000)
        if not phone or phone.strip().lower() == "q":
            sender.reply("✅ 已取消登录")
            return
        phone = phone.strip()
    if not re.match(r"^1\d{10}$", phone):
        sender.reply("❌ 手机号格式不正确（应为 11 位手机号）")
        return

    ok, msg = send_sms(phone)
    if not ok:
        sender.reply("❌ 验证码发送失败: %s" % msg)
        return
    if not code:
        sender.reply("📮 验证码已发送至 %s（%s）\n请输入收到的验证码:\n回复 'q' 退出" % (mask_str(phone), msg))
        code = sender.listen(180000)
        if not code or code.strip().lower() == "q":
            sender.reply("✅ 已取消登录")
            return
        code = code.strip()

    res, err = sms_login(phone, code)
    if not res:
        sender.reply("❌ 登录失败: %s" % err)
        return
    # 与 workbuddy_login.py --verify 一致：落库前先验一次 RT 可用性
    verified = verify_rt(res["rt"])
    if not verified:
        sender.reply("⚠️ RT 校验未通过（登录成功但续期失败），仍已保存，请用「wb续期」再试")
    store_login(phone, res["at"], res["rt"], src="短信", verified=verified)


def wb_token_login():
    """Token 登录：粘贴 手机号:AT:RT（可多行，支持 手机号:RT / AT:RT）"""
    sender.reply("""
=====Token登录=====
请粘贴账号（每行一个）:
格式: 手机号:AT:RT
------------------
示例:
13800138000:eyJhbGci...AT...:eyJhbGci...RT...
------------------
也支持: 手机号:RT（AT 留空，运行时自动换发）
多行可批量导入；回复 'q' 退出""")
    user_input = sender.listen(300000)
    if not user_input or user_input.strip().lower() == "q":
        sender.reply("✅ 已取消")
        return
    accs = load_accounts()
    added, skipped, no_rt = 0, 0, 0
    for line in user_input.replace("@", "\n").replace("&", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        phone, at, rt = parse_account_line(line)
        if not rt:
            skipped += 1
            continue
        if not at:
            new_at, new_rt, err = refresh_one(rt)
            if not new_at:
                no_rt += 1
                skipped += 1
                continue
            at, rt = new_at, new_rt
        if not phone:
            phone = jwt_user(at) or ("acct-%d" % (len(accs) + 1))
        accs = upsert_account(accs, phone, at, rt, "")
        added += 1
    save_accounts(accs)
    ok, msg = sync_to_panel(accs)
    sender.reply("""
=====导入完成=====
✅ 新增/更新: %d 个
⏭️ 跳过(格式错或RT失效): %d 个%s
📦 当前共: %d 个账号
🔄 面板同步: %s
------------------
发送「wb运行」执行全流程""" % (added, skipped, "（其中 %d 个 RT 无法续期）" % no_rt if no_rt else "", len(accs), msg))


def wb_login():
    """登录方式选择菜单"""
    sender.reply("""
=====WorkBuddy登录=====
请选择登录方式:
[1] 短信验证码登录
[2] Token登录（粘贴 手机号:AT:RT）
[3] 批量粘贴账号行（高级）
------------------
回复序号选择，回复 'q' 退出""")
    choice = sender.listen(60000)
    if not choice or choice.strip().lower() == "q":
        sender.reply("✅ 已退出登录流程")
        return
    c = choice.strip()
    if c == "1":
        wb_sms_login()
    elif c == "2":
        wb_token_login()
    elif c == "3":
        wb_token_login()
    else:
        sender.reply("❌ 无效的选择")


# ============================================================
# 青龙定时模式（无 middleware 环境：面板 task 直接调脚本）
#   账号来源优先级：本地 RT 存储(轮换后的最新) > 环境变量 WORKBUDDY_REFRESH_TOKEN
#   每次续期后把新 RT 写回本地存储，保证下次运行不会因 RT 轮换而失效
# ============================================================
def store_load():
    try:
        d = json.load(open(REFRESH_STORE, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def store_save(store):
    try:
        json.dump(store, open(REFRESH_STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        print("⚠️ RT 存储写入失败: %s" % str(e)[:60])
        return False


def load_accounts_from_env():
    """定时模式账号来源：本地 RT 存储 + 环境变量（环境变量里的新 RT 自动并入）"""
    store = store_load()
    raw = os.environ.get(s_wb_osname, "") or ""
    if s_wb_osname != "WORKBUDDY_REFRESH_TOKEN":
        raw = raw or os.environ.get("WORKBUDDY_REFRESH_TOKEN", "")
    for line in (raw or "").replace("@", "\n").splitlines():
        phone, at, rt = parse_account_line(line)
        if not rt:
            continue
        key = phone or (jwt_user(at) or "") or ("acct-%d" % (len(store) + 1))
        if key not in store or store[key].get("refresh_token") != rt:
            store[key] = {"refresh_token": rt, "access_token": at,
                          "updated": time.strftime("%Y-%m-%d %H:%M")}
    if store:
        store_save(store)
    return [{"name": k, "phone": k, "at": (v or {}).get("access_token", ""),
             "rt": (v or {}).get("refresh_token", ""), "updated": (v or {}).get("updated", "-")}
            for k, v in store.items() if (v or {}).get("refresh_token")]


def scheduled_run():
    """青龙/无面板环境下的定时执行入口"""
    mode = (os.environ.get("WB_MODE", "") or "").strip().lower()
    if mode not in ("all", "task", "play", "claim", "query"):
        mode = "all"
    accs = load_accounts_from_env()
    if not accs:
        print("❌ 未读到账号。青龙请在环境变量 %s 中填写：手机号:AT:RT（多行用换行分隔）" % s_wb_osname)
        print("   也可用环境变量 WORKBUDDY_REFRESH_TOKEN，或让脚本在同目录生成 %s" % REFRESH_STORE)
        return
    print("╔══════════════════════════════════════╗")
    print("║ 🌱 WorkBuddy 定时模式 %s │ %d 个账号 ║" % (mode.ljust(5), len(accs)))
    print("╚══════════════════════════════════════╝")
    results = []
    store = store_load()
    for i, a in enumerate(accs, 1):
        u = WBUser(i, a)
        try:
            results.append(u.run(mode))
        except Exception as e:
            u.log("❌ 运行异常: %s" % str(e)[:80])
            results.append({"ok": False, "note": u.name, "detail": str(e)[:60]})
        # 关键：把续期后轮换的新 RT 落盘，否则下次运行旧 RT 失效
        key = a.get("phone") or a.get("name")
        if key and a.get("rt"):
            store[key] = {"refresh_token": a["rt"], "access_token": a.get("at", ""),
                          "updated": time.strftime("%Y-%m-%d %H:%M")}
        time.sleep(2)
    store_save(store)
    text = _format_report(results, mode)
    print("\n" + text)
    _push(text, "WorkBuddy 定时报告")
    print("\n📁 RT 已持久化: %s" % REFRESH_STORE)


# ============================================================
# 指令实现
# ============================================================
def _run_all(accs, mode):
    results = []
    for i, a in enumerate(accs, 1):
        u = WBUser(i, a)
        try:
            results.append(u.run(mode))
        except Exception as e:
            u.log("❌ 运行异常: %s" % str(e)[:80])
            results.append({"ok": False, "note": u.name, "detail": str(e)[:60]})
        time.sleep(2)
    # 续期后 RT 可能已轮换，写回并同步面板
    save_accounts(accs)
    return results


def _format_report(results, mode):
    title = {"all": "🚀 WorkBuddy 运行报告", "task": "✅ 成长任务报告",
             "play": "🎮 互动玩法报告", "claim": "🎁 领奖报告",
             "query": "🔎 查询报告"}.get(mode, "WorkBuddy 报告")
    lines = [title, "共 %d 个账号" % len(results), ""]
    for r in results:
        if not r.get("ok"):
            lines.append("• %s ❌ %s" % (mask_str(r.get("note", "")), r.get("detail", "失败")))
            continue
        if mode == "query":
            lines.append("• %s\n   💰%s\n   📊%s\n   🌱%s" % (mask_str(r.get("note", "")), r.get("credits"),
                                                             r.get("usage"), r.get("growth")))
        else:
            lines.append("• %s  ✅%s/%s\n   💰%s" % (mask_str(r.get("note", "")), r.get("done", 0),
                                                     r.get("total", 0), r.get("credits", "")))
    return "\n".join(lines)


def _push(text, title):
    if not s_wb_push:
        return
    try:
        requests.post("https://www.pushplus.plus/send",
                      json={"token": s_wb_push, "title": title, "content": text, "template": "txt"},
                      timeout=15, proxies={"http": None, "https": None})
    except Exception:
        pass


def wb_query():
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「wb登录」")
        return
    sender.reply("🔎 正在查询 %d 个账号（积分/用量/成长/任务）..." % len(accs))
    results = _run_all(accs, "query")
    # 任务明细直接复用查询阶段已拉到的列表，避免二次建对象（否则续期出的新 RT 会丢）
    lines = []
    for r in results:
        if not r.get("ok"):
            lines.append("• %s ❌ %s" % (mask_str(r.get("note", "")), r.get("detail", "Token 不可用")))
            continue
        lines.append("• %s" % mask_str(r.get("note", "")))
        for t in r.get("tasks") or []:
            lines.append("   - %s: %s %s/%s" % (task_cn(t.get("code", "")),
                                                STATUS_CN.get(t.get("status", ""), t.get("status", "")),
                                                t.get("cur", "-"), t.get("tgt", "-")))
    text = _format_report(results, "query") + "\n\n📋 任务明细:\n" + "\n".join(lines)
    sender.reply(text)
    _push(text, "WorkBuddy 查询报告")


def wb_run(mode="all"):
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「wb登录」")
        return
    tip = {"all": "全流程（续期→查询→任务→玩法→领奖）", "task": "成长任务", "play": "互动玩法", "claim": "领奖"}[mode]
    sender.reply("🚀 正在执行 %d 个账号：%s ..." % (len(accs), tip))
    results = _run_all(accs, mode)
    ok, msg = sync_to_panel(accs)
    text = _format_report(results, mode) + "\n\n🔄 面板同步: %s" % msg
    sender.reply(text)
    _push(text, "WorkBuddy 运行报告")


def wb_renew():
    """强制续期全部账号 Token（RT 轮换后自动同步面板）"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「wb登录」")
        return
    lines = []
    for i, a in enumerate(accs, 1):
        u = WBUser(i, a)
        okk = u.ensure_token(force=True)
        lines.append("• %s %s" % (mask_str(a.get("phone", "") or a.get("name", "")),
                                  "✅ 已续期（新RT已保存）" if okk else "❌ 续期失败"))
    save_accounts(accs)
    ok, msg = sync_to_panel(accs)
    sender.reply("=====Token续期=====\n%s\n------------------\n🔄 面板同步: %s" % ("\n".join(lines), msg))


def wb_check():
    """检测账号有效性"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「wb登录」")
        return
    lines = []
    for i, a in enumerate(accs, 1):
        u = WBUser(i, a)
        okk = u.ensure_token()
        if not okk:
            lines.append("• %s ❌ 凭据失效，请重新登录" % mask_str(a.get("phone", "")))
            continue
        try:
            prof = (u.jget("/v2/activity/growth/profile").get("data") or {})
            lines.append("• %s ✅ 有效（等级%s）" % (mask_str(a.get("phone", "")), prof.get("level", "?")))
        except Exception:
            lines.append("• %s ⚠️ 凭据可用但接口异常" % mask_str(a.get("phone", "")))
    save_accounts(accs)
    sender.reply("=====账号检测=====\n%s" % "\n".join(lines))


def wb_manage():
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「wb登录」")
        return
    lines = ["=====账号管理=====", "当前共 %d 个账号:" % len(accs)]
    for i, a in enumerate(accs, 1):
        lines.append("[%d] %s（更新:%s）" % (i, mask_str(a.get("phone", "") or a.get("name", "")),
                                            a.get("updated", "-")))
    lines += ["------------------", "回复数字删除对应账号", "回复 'all' 清空全部", "回复 'q' 退出"]
    sender.reply("\n".join(lines))
    choice = sender.listen(60000)
    if not choice:
        sender.reply("❌ 输入超时")
        return
    choice = choice.strip().lower()
    if choice == "q":
        sender.reply("✅ 已退出操作")
        return
    if choice == "all":
        save_accounts([])
        ok, msg = sync_to_panel([])
        sender.reply("✅ 已清空全部账号\n🔄 面板同步: %s" % msg)
        return
    try:
        idx = int(choice)
        if not 1 <= idx <= len(accs):
            sender.reply("❌ 无效的选择")
            return
        removed = accs.pop(idx - 1)
        save_accounts(accs)
        ok, msg = sync_to_panel(accs)
        sender.reply("✅ 已删除 %s\n🔄 面板同步: %s" % (mask_str(removed.get("phone", "")), msg))
    except ValueError:
        sender.reply("❌ 无效的选择")


def wb_clean():
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 没有可清理的账号")
        return
    sender.reply("⚠️ 确认清空全部 %d 个账号吗？(y/n)" % len(accs))
    confirm = sender.listen(30000)
    if not confirm or confirm.strip().lower() not in ("y", "yes", "是"):
        sender.reply("✅ 已取消")
        return
    save_accounts([])
    ok, msg = sync_to_panel([])
    sender.reply("✅ 已清空全部账号\n🔄 面板同步: %s" % msg)


def wb_update():
    """重新同步面板变量（面板端重新拉起脚本/变量被误删时用）"""
    accs = load_accounts()
    ok, msg = sync_to_panel(accs)
    if not accs:
        sender.reply("⚠️ 本地无账号，%s" % msg)
        return
    if ok:
        sender.reply("✅ 已重新同步 %d 个账号到面板\n🔄 %s\n\n提示: 面板定时任务里配置环境变量 %s 后即可每日跑量。"
                     % (len(accs), msg, s_wb_osname))
    else:
        sender.reply("⚠️ 同步未完成: %s\n本地仍保存 %d 个账号。" % (msg, len(accs)))


def wb_help():
    sender.reply("""
=====WorkBuddy签到 %s=====
🔐 wb登录    登录方式菜单（短信 / Token）
📱 wb短信    短信验证码登录
             （也可: wb短信 手机号 验证码 一步直登）
➕ wb添加    Token登录·批量粘贴账号
🔎 wb查询    💰积分 📊用量 🌱成长 ✅任务
🚀 wb运行    全流程（续期→查询→任务→玩法→领奖）
✅ wb任务    只跑成长任务
🎮 wb玩法    只跑互动玩法（抽奖/盲盒/旅行/兑换…）
🎁 wb领奖    只领取已完成任务的奖励
🔑 wb续期    强制刷新全部 Token
🩺 wb检测    校验账号有效性
📋 wb管理    查看/删除账号
🧹 wb清理    清空全部账号
🔄 wb更新    重新同步青龙/呆呆变量
❓ wb帮助    本说明
------------------
账号格式: 手机号:AT:RT（面板变量 %s）
面板定时任务建议: 0 7,12 * * *
夜猫子任务需另排: 30 23 * * *
------------------
⚠️ 账号较多时请勿用「wb运行」在聊天里硬跑（面板插件有执行超时），
   改为同步变量后用面板定时任务跑；青龙下脚本会自动进入定时模式。""" % (SCRIPT_VERSION, s_wb_osname))


# ============================================================
# 指令路由
# ============================================================
def handle_command(message):
    m = str(message or "").strip()
    # 去掉指令前缀（wb / wb 查询 两种写法），只按关键字路由
    kw = re.sub(r"^\s*[wW][bB]\s*", "", m)
    # 参数从剥离前缀后的剩余里取：wb短信 138xxx 123456 → ["138xxx", "123456"]
    args = kw.split()[1:] if len(kw.split()) > 1 else []
    if "帮助" in kw or kw == "":
        wb_help()
    elif "短信" in kw:
        wb_sms_login(args)
    elif "添加" in kw:
        wb_token_login()
    elif "登录" in kw or "登陆" in kw:
        wb_login()
    elif "续期" in kw:
        wb_renew()
    elif "检测" in kw:
        wb_check()
    elif "查询" in kw or "积分" in kw:
        wb_query()
    elif "领奖" in kw:
        wb_run("claim")
    elif "玩法" in kw:
        wb_run("play")
    elif "任务" in kw:
        wb_run("task")
    elif "运行" in kw:
        wb_run("all")
    elif "管理" in kw:
        wb_manage()
    elif "清理" in kw:
        wb_clean()
    elif "更新" in kw:
        wb_update()
    else:
        sender.setContinue()


def _cli_args():
    """命令行参数（本地调试/青龙手动执行）：返回去掉脚本名后的参数列表"""
    return [a for a in sys.argv[1:] if not a.endswith(".py")]


def main():
    try:
        msg = (sender.getMessage() or "").strip()
        # 青龙定时场景：没有 middleware、也没有任何指令 → 进入定时模式
        # （青龙面板不提供 middleware 交互，task xxx.py 调用时 argv 里没有指令）
        if not _HAS_MW and not msg:
            if _cli_args():
                handle_command(" ".join(_cli_args()))
            else:
                scheduled_run()
            return
        handle_command(msg)
    except Exception as e:
        try:
            sender.reply("❌ 运行出错: %s" % str(e)[:200])
        except Exception:
            print("❌ 运行出错: %s" % e)


if __name__ == "__main__":
    main()
