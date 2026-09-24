# [title: 小米钱包视频福利]
# [language: python]
# [rule: ^(米包)(登录|登陆|查询|管理|清理|运行|更新|检测|扫码)((?:\s+\S+)*)$]
# [disable:false]
# [open_source: false]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public:true]
# [version: 1.0.0]
# [price: 0]
# [author: 逆向改造版(基于小米钱包V1 + 联通插件范式)]
# [service: ]
# [description: ❶小米钱包「视频福利」活动脚本，支持浏览任务 / 下载(EMI广告)任务 / 首次访问抽奖，全程免费、无授权收费墙。<br>❷对接呆呆面板与青龙面板双平台：登录支持【扫码登录 / 账号密码登录 / 手动Cookie登录】三种方式（『米包登录』选择，『米包扫码』直接扫码），可一键同步到青龙/呆呆环境变量，由面板定时跑量。<br>❸指令：『米包登录』选择登录方式、『米包扫码』直接扫码登录、『米包查询』查任务进度、『米包运行』执行全部任务、『米包管理』管理账号、『米包清理』删除账号、『米包更新』重新同步面板变量、『米包检测』校验账号有效性。<br>❹账号格式：账号名#userid#passToken#oaid#ua（每行一个，可多行）]

# [param: {"required":false,"key":"s_mibao.s_mibao_qlname","bool":false,"placeholder":"Host丨ClientID丨ClientSecret","name":"对接青龙","desc":"各参数之间用中文符丨分割，例如: http://127.0.0.1:5700/丨abcdef-ghijk丨abcdefghijklmnopqrs_tuvw"}]
# [param: {"required":false,"key":"s_mibao.s_mibao_ddname","bool":false,"placeholder":"Host丨app_key丨app_secret","name":"对接呆呆面板","desc":"留空则使用青龙面板。各参数之间用中文符丨分割，例如: http://127.0.0.1:5700丨abcdef-ghijk丨abcdefghijklmnopqrs_tuvw"}]
# [param: {"required":false,"key":"s_mibao.s_mibao_osname","bool":false,"placeholder":"xiaomiAccount","name":"环境变量名","desc":"同步到青龙/呆呆的变量名称，默认 xiaomiAccount"}]
# [param: {"required":false,"key":"s_mibao.s_mibao_proxy","bool":false,"placeholder":"http://127.0.0.1:7890","name":"代理地址","desc":"可选，格式 http:// 或 socks5://，留空直连"}]

# -*- coding: utf-8 -*-
"""
小米钱包视频福利 —— 呆呆面板 / 青龙面板 双平台插件（免费无授权版）

相比原「米包」付费插件，本版本：
  * 彻底移除授权收费墙（原付费授权 / 支付 / 积分兑换相关逻辑已全部删除）；本插件默认永久可用。
  * 直接内嵌「小米钱包视频福利」任务逻辑（浏览 / 下载EMI广告 / 首次访问抽奖）。
  * 复用联通插件的 呆呆面板 middleware SDK 与 青龙 Open API 接入范式。

账号来源采用 passToken 方式（与 小米钱包视频福利.py 一致）：
  格式  账号名#userid#passToken#oaid#ua
  存放  每个用户在 bucket 's_mibao_user' 下存一份账号列表(JSON)
  同步  可一键把全部账号拼成 xiaomiAccount 同步到 青龙/呆呆 环境变量
"""
import os
import re
import sys
import json
import time
import random
import uuid
import requests
import urllib3
import hashlib
import base64
import urllib.parse
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCRIPT_VERSION = "v1.0.0"

# ============================================================
# 全局配置
# ============================================================
BUCKET = 's_mibao'                 # 配置 / 账号 存放 bucket 前缀
BUCKET_USER = 's_mibao_user'        # 每个用户 → 账号列表(JSON) 的 bucket

globalConfig = {
    "enable_video_welfare": True,
    "vw_config": {
        "run_firstin_draw": True,   # 首次访问抽奖
        "run_browse_task": True,    # 浏览任务
        "run_emi_ad_task": True,    # 下载(EMI广告)任务
    },
    "enable_notify": False,         # 推送通知（需配置 XM_NOTIFY_URL）
}

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


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _now():
    return datetime.now().strftime('%H:%M:%S')


# ============================================================
# 小米账号任务类（内嵌自 小米钱包视频福利.py，适配插件环境）
# ============================================================
class XiaomiUser:
    def __init__(self, index, config_str):
        self.index = index
        self.name = ""
        self.user_id = ""
        self.pass_token = ""
        self.oaid = ""
        self.ua = ""
        self.logs = []           # 本轮日志（用于汇总回复）
        self.notify_logs = []
        self._parse(config_str)

        self.base_url = "https://m.jr.airstarfinance.net/mp/api/generalActivity"
        self.video_base_url = "https://m.jr.airstarfinance.net/mp/api/video"
        self.tid = str(uuid.uuid4())
        self.activity_code = "2211-videoWelfare"
        self.jrairstar_ph = ""
        self.c_user_id = ""

        self.session = requests.Session()
        self.session.verify = False
        proxy = os.environ.get("XM_PROXY", "")
        self.proxies = {"http": proxy, "https": proxy} if proxy else {}

        self.headers = {
            "Host": "m.jr.airstarfinance.net",
            "Connection": "keep-alive",
            "Accept": "application/json, text/plain, */*",
            "Cache-Control": "no-cache",
            "User-Agent": self.ua or "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://m.jr.airstarfinance.net",
            "X-Requested-With": "com.mipay.wallet",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cookie": "",
        }

        self.user_task_id = None
        self.task_id = None
        self.task_code = None
        self.brows_task_id = None
        self.brows_click_url_id = None
        self.complete_status = None
        self.remain_chance = 0
        self.period_complete_count = 0
        self.period_count = 0
        self.emi_task_id = None
        self.emi_task_code = None
        self.emi_ad_info_id = None
        self.emi_brows_click_url_id = None
        self.emi_tasks = []

        self.user_extra = {
            "platformType": 1,
            "com.miui.player": "4.39.0.3",
            "com.miui.video": "v2026090890(MiVideo-UN)",
            "com.mipay.wallet": "6.98.0.5484.2643",
        }

    def _parse(self, config_str):
        parts = config_str.split("#", 4)
        if len(parts) != 5:
            self.name = config_str.strip()
            self.log(f"⚠️ 账号格式错误(应为 账号名#userid#passToken#oaid#ua): {mask_str(config_str)}")
            return
        self.name, self.user_id, self.pass_token, self.oaid, self.ua = [p.strip() for p in parts]

    def log(self, msg, notify=False):
        full = f"账号[{self.index}][{self.name}] {msg}"
        line = f"[{_now()}] {full}"
        print(line)
        self.logs.append(line)
        if notify:
            self.notify_logs.append(str(msg))

    def _ok(self, result):
        return bool(result) and (result.get("success") or result.get("code") == 0)

    def _dumps(self, obj):
        return json.dumps(obj, separators=(",", ":"))

    def _task_gap(self, tip="任务间隔", lo=10, hi=15):
        wait_s = random.randint(lo, hi)
        self.log(f"⏳ {tip}等待 {wait_s} 秒...")
        time.sleep(wait_s)

    def _request(self, method, api, params=None, data=None, base=None):
        url = f"{(base or self.base_url)}/{api}"
        try:
            resp = self.session.request(
                method, url, params=params, data=data, headers=self.headers,
                verify=False, timeout=60, proxies=self.proxies,
            )
            return resp.json()
        except Exception as e:
            self.log(f"请求异常 [{api}]: {e}")
            return None

    # ---------- Cookie 刷新(passToken → 钱包Cookie) ----------
    def refresh_cookies(self):
        if not self.pass_token or not self.user_id:
            self.log("❌ 缺少 passToken/userId，无法刷新 Cookie")
            return False
        login_url = ("https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fapi.jr.airstarfinance.net%2Fsts%3Fsign%3D1dbHuyAmee0NAZ2xsRw5vhdVQQ8%253D%26followup%3Dhttps%253A%252F%252Fm.jr.airstarfinance.net%252Fmp%252Fapi%252Flogin%253Ffrom%253Dmipay_indexicon_TVcard%2526deepLinkEnable%253Dfalse%2526requestUrl%253Dhttps%25253A%25252F%25252Fm.jr.airstarfinance.net%25252Fmp%25252Factivity%25252FvideoActivity%25253Ffrom%25253Dmipay_indexicon_TVcard%252526_noDarkMode%25253Dtrue%252526_transparentNaviBar%25253Dtrue%252526cUserId%25253Dusyxgr5xjumiQLUoAKTOgvi858Q%252526_statusBarHeight%25253D137&sid=jrairstar&_group=DEFAULT&_snsNone=true&_loginType=ticket")
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0"
        try:
            r1 = self.session.get(
                login_url,
                headers={"User-Agent": ua, "Cookie": f"passToken={self.pass_token}; userId={self.user_id};"},
                allow_redirects=False, timeout=60, proxies=self.proxies,
            )
            for c in r1.cookies:
                if c.name == "cUserId":
                    self.c_user_id = c.value
                    break
            location_url = r1.headers.get("Location")
            if not location_url:
                self.log("❌ 获取重定向URL失败")
                return False
            r2 = self.session.get(
                location_url, headers={"User-Agent": ua},
                allow_redirects=False, timeout=60, proxies=self.proxies,
            )
            cookies = {}
            for name, value in r2.cookies.items():
                cookies[name] = value
        except Exception as e:
            self.log(f"❌ 刷新 ck 异常: {e}")
            return False

        if "serviceToken" not in cookies:
            self.log("❌ 获取cookie失败")
            return False
        token = cookies["serviceToken"]
        slh = cookies.get("jrairstar_slh") or ""
        ph = cookies.get("jrairstar_ph") or ""
        if ph:
            self.jrairstar_ph = ph
        self.headers["Cookie"] = (
            f"cUserId={self.c_user_id}; "
            f"jrairstar_serviceToken={token}; "
            f"jrairstar_slh={slh}; "
            f"jrairstar_ph={self.jrairstar_ph}"
        )
        self.log("✅ token刷新成功")
        return True

    # ---------- 公共参数 ----------
    def _common_fields(self):
        return {
            "activityCode": self.activity_code,
            "app": "com.mipay.wallet",
            "oaid": self.oaid,
            "versionCode": "20577630",
            "versionName": "6.98.0.5484.2643",
            "isNfcPhone": "true",
            "channel": "mipay_indexV2icon_TVcard",
            "deviceType": "2",
            "system": "1",
            "visitEnvironment": "2",
            "userExtra": self._dumps(self.user_extra),
            "jrairstar_ph": self.jrairstar_ph,
        }

    def _yimi_data(self, tag_id="1.140.4.1"):
        ua = self.headers.get("User-Agent") or ""
        return self._dumps({
            "clientInfo": {
                "deviceInfo": {
                    "androidVersion": "14",
                    "device": "",
                    "miuiVersion": 816,
                    "miuiVersionName": "V816",
                    "model": "",
                    "restrictImei": "true",
                    "screenHeight": 868,
                    "screenWidth": 412,
                },
                "userInfo": {
                    "androidId": "",
                    "connectionType": "WIFI",
                    "oaid": self.oaid or "",
                    "country": "CN",
                    "isPersonalizedAdEnabled": True,
                    "language": "zh-rCN",
                    "ua": ua,
                },
                "appInfo": {
                    "packageName": "com.mipay.wallet",
                    "version": "6.98.0.5484.2643",
                },
                "context": {"eid": "", "packageNameList": ""},
                "impRequests": [{"adsCount": 1, "tagId": tag_id}],
            }
        })

    # ---------- 活动接口 ----------
    def visit_index(self):
        data = {**self._common_fields(), "comeFromComponent": "false"}
        result = self._request("POST", "visitIndex", params={"tid": self.tid}, data=data)
        if self._ok(result):
            self.log("✅ 进入活动页面成功")
        else:
            self.log(f"❌ 进入活动页面失败: {(result or {}).get('error') or result}")
        return result

    def get_task_list(self):
        data = {**self._common_fields(), "pagination": "0", "dataType": "0"}
        result = self._request("POST", "getTaskList", params={"tid": self.tid}, data=data)
        if self._ok(result):
            tasks = ((result.get("value") or {}).get("taskInfoList") or [])
            names = "、".join(t.get("taskName") or "?" for t in tasks)
            self.log(f"✅ 获取任务列表成功: {len(tasks)} 个 ({names})")
        else:
            self.log(f"❌ 获取任务列表失败: {(result or {}).get('error') or result}")
        return result

    def get_task(self):
        data = {
            **self._common_fields(),
            "pagination": "0",
            "dataType": "0",
            "isTablet": "false",
            "taskCode": "BROWSE_GROUP_TASK1",
            "componentStatus": "0",
            "comeFromComponent": "false",
        }
        result = self._request("POST", "getTask", params={"tid": self.tid}, data=data)
        if self._ok(result):
            info = ((result.get("value") or {}).get("taskInfo") or {})
            url_info = info.get("generalActivityUrlInfo") or {}
            self.task_id = str(info.get("taskId") or "")
            self.task_code = str(info.get("taskCode") or "")
            self.brows_task_id = str(url_info.get("id") or "")
            self.brows_click_url_id = str(url_info.get("browsClickUrlId") or "")
            self.complete_status = info.get("completeStatus")
            self.remain_chance = safe_int(info.get("remainChance") or 0)
            self.period_complete_count = safe_int(info.get("periodCompleteCount") or 0)
            self.period_count = safe_int(info.get("periodCount") or 0)
            uid = info.get("userTaskId")
            if uid not in (None, "", 0, "0"):
                self.user_task_id = str(uid)
            self.log(f"✅ 获取浏览任务: {info.get('taskName')} | 进度：{self.period_complete_count}/{self.period_count}")
        else:
            self.log(f"❌ 获取浏览任务失败: {(result or {}).get('error') or result}")
        return result

    def click_task(self):
        if not all([self.task_id, self.task_code, self.brows_task_id, self.brows_click_url_id]):
            self.log("❌ 点击浏览任务失败: 缺少任务参数")
            return None
        params = {
            "tid": self.tid,
            **self._common_fields(),
            "taskId": self.task_id,
            "taskCode": self.task_code,
            "newBrowsTask": "true",
            "browsTaskId": self.brows_task_id,
            "browsClickUrlId": self.brows_click_url_id,
        }
        result = self._request("GET", "clickTask", params=params)
        if self._ok(result):
            self.log("✅ 点击浏览任务成功")
        else:
            self.log(f"❌ 点击浏览任务失败: {(result or {}).get('error') or result}")
        return result

    def complete_task(self):
        if not all([self.task_id, self.task_code, self.brows_task_id, self.brows_click_url_id]):
            self.log("❌ 完成任务失败: 缺少任务参数，请先调用 get_task")
            return None
        params = {
            "tid": self.tid,
            **self._common_fields(),
            "taskId": self.task_id,
            "taskCode": self.task_code,
            "browsTaskId": self.brows_task_id,
            "browsClickUrlId": self.brows_click_url_id,
            "clickEntryType": "",
            "adInfoId": "",
            "triggerId": "",
            "festivalStatus": "0",
            "isTablet": "false",
        }
        result = self._request("GET", "completeTask", params=params)
        if self._ok(result):
            self.user_task_id = str(result.get("value") or "")
            self.log("✅ 完成浏览任务成功")
        else:
            self.log(f"❌ 完成浏览任务失败: {(result or {}).get('error') or result}")
        return result

    def luckDraw(self, task_code=None):
        if not self.user_task_id:
            self.log("❌ 抽奖失败: 缺少 userTaskId")
            return None
        params = {
            "tid": self.tid,
            **self._common_fields(),
            "imei": "",
            "userTaskId": self.user_task_id,
        }
        if task_code:
            params["taskCode"] = task_code
        result = self._request("GET", "luckDraw", params=params)
        if self._ok(result):
            prize = (result.get("value") or {}).get("prizeInfo") or {}
            self.log(f"✅ 抽奖成功: {prize.get('prizeName')}")
        else:
            self.log(f"❌ 抽奖失败: {(result or {}).get('error') or result}")
        return result

    def update_task_status(self):
        data = {"jrairstar_ph": self.jrairstar_ph}
        result = self._request(
            "POST", "updateUserContinueAdTaskStatus",
            params={"tid": self.tid}, data=data, base=self.video_base_url,
        )
        if self._ok(result):
            self.log("✅ 更新下载任务状态成功")
        else:
            self.log(f"❌ 更新下载任务状态失败: {(result or {}).get('error') or result}")
        return result

    def get_EmiAd_task(self):
        data = {
            **self._common_fields(),
            "pagination": "0",
            "dataType": "0",
            "taskCode": "NEW_USER_CAMPAIGN",
            "isRetry": "false",
            "isManualRetry": "false",
            "taskId": "",
            "mobileDeviceType": "0",
            "yimiData": self._yimi_data(),
        }
        result = self._request(
            "POST", "getEmiAdUrlV2", params={"tid": self.tid}, data=data, base=self.video_base_url
        )
        if self._ok(result):
            tasks = ((result.get("value") or {}).get("tasks") or {})
            self.emi_tasks = []
            for code in ("NEW_USER_CAMPAIGN", "NEW_USER_CAMPAIGN_2"):
                info = tasks.get(code)
                if not info:
                    continue
                status = info.get("completeStatus")
                continue_status = info.get("newAdContinueTaskStatus")
                can_retry = info.get("canRetry")
                name = info.get("taskName") or code
                self.log(f"   - {name}")
                if status == 2 and continue_status == 2:
                    self.log(f"⏭️ {name} 下载任务已完成，跳过")
                    continue
                if not ((status == 1 and can_retry) or status == 2):
                    self.log(f"⏭️ {name} 状态不可执行，跳过")
                    continue
                ads = info.get("adInfos") or []
                ad_id = str((ads[0].get("id") if ads else "") or info.get("adInfoId") or "")
                if not ad_id:
                    self.log(f"⏭️ {name} 缺少参数，跳过")
                    continue
                self.emi_tasks.append({
                    "name": name,
                    "task_id": str(info.get("taskId") or ""),
                    "task_code": str(info.get("taskCode") or code),
                    "ad_info_id": ad_id,
                    "brows_click_url_id": str(info.get("browsClickUrlId") or "0"),
                })
            self.log(f"✅ 可执行下载任务 {len(self.emi_tasks)} 个")
        else:
            self.log(f"❌ 获取下载任务失败: {(result or {}).get('error') or result}")
        return result

    def click_EmiAd_task(self):
        if not all([self.emi_task_id, self.emi_task_code, self.emi_ad_info_id]):
            self.log("❌ 点击下载任务失败: 缺少可执行任务参数")
            return None
        data = {
            **self._common_fields(),
            "browsClickUrlId": self.emi_brows_click_url_id or "0",
            "taskCode": self.emi_task_code,
            "taskId": self.emi_task_id,
            "adInfoId": self.emi_ad_info_id,
        }
        result = self._request(
            "POST", "clickEmiNewTaskV2", params={"tid": self.tid}, data=data, base=self.video_base_url
        )
        if self._ok(result):
            value = result.get("value") or {}
            self.emi_brows_click_url_id = str(
                value.get("browsClickUrlId") or self.emi_brows_click_url_id or ""
            )
            self.log("✅ 点击下载任务成功")
        else:
            self.log(f"❌ 点击下载任务失败: {(result or {}).get('error') or result}")
        return result

    def complete_EmiAd_task(self):
        if not all([self.emi_task_id, self.emi_task_code, self.emi_brows_click_url_id]):
            self.log("❌ 完成下载任务失败: 缺少任务参数")
            return None
        data = {
            **self._common_fields(),
            "taskCode": self.emi_task_code,
            "taskId": self.emi_task_id,
            "browsTaskId": "",
            "browsClickUrlId": self.emi_brows_click_url_id,
            "adInfoId": "",
            "triggerId": "",
        }
        result = self._request(
            "POST", "completeTaskV2", params={"tid": self.tid}, data=data, base=self.video_base_url
        )
        self.user_task_id = None
        if self._ok(result):
            value = result.get("value")
            if isinstance(value, (dict, list)):
                self.log("⏭️ 完成下载任务成功，需第二天执行领奖，跳过抽奖")
            elif value not in (None, "", 0, "0"):
                self.user_task_id = str(value)
                self.log("✅ 完成下载任务成功")
            else:
                self.log("⏭️ 完成下载任务成功，无有效 userTaskId，跳过抽奖")
        else:
            self.log(f"❌ 完成下载任务失败: {(result or {}).get('error') or result}")
        return result

    # ---------- 流程编排 ----------
    def _do_firstin_draw(self):
        result = self.get_task_list()
        if not self._ok(result):
            return
        tasks = ((result.get("value") or {}).get("taskInfoList") or [])
        firstin = next((t for t in tasks if t.get("taskCode") == "FINANCE_FIRSTIN"), None)
        if not firstin:
            self.log("⏭️ 未找到首次访问任务")
            return
        remain = safe_int(firstin.get("remainChance") or 0)
        uid = firstin.get("userTaskId")
        self.log("🎯 首次访问任务状态查询")
        if remain != 1:
            self.log("⏭️ 首次访问奖励已领取，跳过抽奖")
            return
        if uid in (None, "", 0, "0"):
            self.log("❌ 首次访问抽奖跳过: 缺少 userTaskId")
            return
        self.user_task_id = str(uid)
        self.log("🎲 首次访问抽奖")
        self.luckDraw()

    def _set_emi_task(self, task):
        self.emi_task_id = task["task_id"]
        self.emi_task_code = task["task_code"]
        self.emi_ad_info_id = task["ad_info_id"]
        self.emi_brows_click_url_id = task["brows_click_url_id"]
        self.user_task_id = None

    def _maybe_draw_browse(self):
        if self.remain_chance != 1:
            return
        if not self.user_task_id:
            self.log("❌ 抽奖跳过: 缺少 userTaskId")
            return
        self.log("🎲 浏览抽奖")
        self.luckDraw()
        self.remain_chance = 0

    def _do_browse_once(self):
        if self.complete_status == 3:
            self.log("⏭️ 浏览任务已完成，停止继续浏览")
            return False
        if not all([self.task_id, self.task_code, self.brows_task_id, self.brows_click_url_id]):
            self.log("❌ 浏览参数不足，跳过本轮")
            return False
        if not self._ok(self.click_task()):
            return False
        self._task_gap("浏览等待", lo=10, hi=20)
        return self._ok(self.complete_task())

    def _browse_flow(self):
        self.log("\n--- 浏览任务 ---")
        if not self._ok(self.get_task()):
            return
        if self.remain_chance == 1:
            self._maybe_draw_browse()
            self.get_task()
        if self.complete_status == 3:
            self.log("⏭️ 浏览任务今日已完成，跳过")
            return
        if self.complete_status in (1, 2):
            left = max((self.period_count or 2) - (self.period_complete_count or 0), 0)
            if self.complete_status == 1 and left <= 0:
                left = self.period_count or 2
            self.log(f"📋 浏览待执行轮次: {left}")
            for i in range(left):
                self.log(f"\n>>> 浏览轮次 [{i + 1}/{left}]")
                if not self._do_browse_once():
                    break
                if not self._ok(self.get_task()):
                    break
                self._maybe_draw_browse()
                if self.complete_status == 3:
                    self.log("✅ 浏览任务已全部完成")
                    break
                if i < left - 1:
                    self._task_gap("浏览轮次间隔")
        else:
            self.log(f"⏭️ 未知浏览状态 completeStatus={self.complete_status}，跳过")

    def _emi_flow(self):
        self._task_gap("进入下载任务前")
        self.log("\n--- 下载任务 ---")
        self.update_task_status()
        time.sleep(1)
        if self._ok(self.get_EmiAd_task()) and self.emi_tasks:
            for i, task in enumerate(self.emi_tasks, 1):
                if i > 1:
                    self._task_gap("下载任务间隔")
                self.log(f"\n>>> 下载任务 [{i}/{len(self.emi_tasks)}] {task['name']}")
                self._set_emi_task(task)
                if not self._ok(self.click_EmiAd_task()):
                    continue
                self._task_gap("下载任务等待", lo=45, hi=60)
                if self._ok(self.complete_EmiAd_task()) and self.user_task_id:
                    self.luckDraw(task_code=self.emi_task_code or "NEW_USER_CAMPAIGN")
        else:
            self.log("⏭️ 跳过下载任务")

    def execute_daily_tasks(self, query_only=False):
        if not globalConfig.get("enable_video_welfare", True):
            self.log("⏭️ 视频福利总开关关闭，跳过")
            return
        cfg = globalConfig.get("vw_config", {})

        if not self._ok(self.visit_index()):
            self.log("❌ 进入活动页失败，终止本账号")
            return

        if query_only:
            self.log("📋 [查询模式] 仅查询任务状态")
            self.get_task_list()
            self.get_task()
            return

        if cfg.get("run_firstin_draw", True):
            self.log("\n--- 首次访问 ---")
            self._do_firstin_draw()
            self._task_gap("首次访问后")
        else:
            self.log("⏭️ 首次访问抽奖已关闭")

        if cfg.get("run_browse_task", True):
            self._browse_flow()
        else:
            self.log("⏭️ 浏览任务已关闭")

        if cfg.get("run_emi_ad_task", True):
            self._emi_flow()
        else:
            self.log("⏭️ 下载任务已关闭")

        self.log("✅ 全部流程执行完毕")


# ============================================================
# 呆呆面板 middleware SDK + 青龙/呆呆 Open API 接入（范式来自联通插件）
# ============================================================
import middleware  # 呆呆面板运行时注入的 SDK 模块

senderID = middleware.getSenderID()
sender = middleware.Sender(senderID)
userid = sender.getUserID()
imtype = sender.getImtype()
uservalue = middleware.bucketGet(bucket=BUCKET_USER, key=userid)


def get_config():
    """读取插件配置（面板参数）"""
    qlname = middleware.bucketGet(BUCKET, 's_mibao_qlname') or ''
    ddname = middleware.bucketGet(BUCKET, 's_mibao_ddname') or ''
    osname = middleware.bucketGet(BUCKET, 's_mibao_osname') or 'xiaomiAccount'
    proxy = middleware.bucketGet(BUCKET, 's_mibao_proxy') or ''
    return qlname, ddname, osname, proxy


s_mibao_qlname, s_mibao_ddname, s_mibao_osname, s_mibao_proxy = get_config()

# 面板连接态（seekql 写）
QLurl = ""
qltoken = ""
PANEL_KIND = "ql"
PANEL_BASE = ""


def _resp_ok(rj):
    """青龙 code==200 判成功；呆呆 success!=false 或 code 200/201/0"""
    if not isinstance(rj, dict):
        return False
    if 'code' in rj:
        return str(rj.get('code')) in ('200', '201', '0', '0000')
    if 'success' in rj:
        return rj.get('success') is not False
    return True


def _env_id(env):
    return env.get('id') if env.get('id') is not None else env.get('ID')


def DDtoken(host, app_key, app_secret):
    """获取呆呆面板 token"""
    try:
        url = host.rstrip('/') + '/api/open-api/token'
        response = requests.post(url, json={"app_key": app_key, "app_secret": app_secret},
                                 headers={"Content-Type": "application/json"},
                                 timeout=20, proxies={"http": None, "https": None})
        if response.status_code != 200:
            sender.reply(f"""
=====请求失败=====
❌ 呆呆面板认证请求失败
------------------
状态码: {response.status_code}
==================""")
            exit(0)
        result = response.json()
        data = result.get('data') or {}
        if not data.get('access_token'):
            sender.reply("""
=====认证失败=====
❌ 获取呆呆Token失败
------------------
请检查:
• app_key 是否正确
• app_secret 是否正确
==================""")
            exit(0)
        return data['access_token']
    except requests.exceptions.RequestException:
        sender.reply("""
=====网络错误=====
❌ 连接呆呆面板失败
------------------
请检查:
• 呆呆地址是否正确
• 网络是否正常
==================""")
        exit(0)


def QLtoken(QLurl, ClientID, ClientSecret):
    """获取青龙 token"""
    try:
        url = f'{QLurl}/open/auth/token?client_id={ClientID}&client_secret={ClientSecret}'
        response = requests.get(url, proxies={"http": None, "https": None})
        if response.status_code != 200:
            sender.reply(f"""
=====请求失败=====
❌ 青龙API请求失败
------------------
状态码: {response.status_code}
==================""")
            exit(0)
        result = response.json()
        if "token" in result.get('data', {}):
            return result['data']['token']
        else:
            sender.reply("""
=====认证失败=====
❌ 获取Token失败
------------------
请检查:
• ClientID是否正确
• ClientSecret是否正确
• 应用是否有权限
==================""")
            exit(0)
    except requests.exceptions.RequestException:
        sender.reply("""
=====网络错误=====
❌ 连接青龙面板失败
==================""")
        exit(0)


def seekql():
    """解析面板配置，返回 (QLurl, qltoken)，并设置全局 PANEL_KIND / PANEL_BASE"""
    global QLurl, qltoken, PANEL_KIND, PANEL_BASE
    try:
        # 优先呆呆面板
        if len(s_mibao_ddname) > 0:
            ddlist = s_mibao_ddname.split('丨')
            if len(ddlist) != 3:
                sender.reply("""
=====格式错误=====
❌ 呆呆配置格式错误
------------------
正确格式:
Host丨app_key丨app_secret
==================""")
                exit(0)
            QLurl = ddlist[0].strip().rstrip('/')
            AppKey = ddlist[1].strip()
            AppSecret = ddlist[2].strip()
            if not all([QLurl, AppKey, AppSecret]):
                sender.reply("❌ 呆呆配置参数不完整")
                exit(0)
            if not QLurl.startswith(('http://', 'https://')):
                sender.reply("❌ 呆呆地址格式错误")
                exit(0)
            qltoken = DDtoken(host=QLurl, app_key=AppKey, app_secret=AppSecret)
            PANEL_KIND = 'dd'
            PANEL_BASE = QLurl + '/api'
            return QLurl, qltoken

        if len(s_mibao_qlname) == 0:
            sender.reply("""
=====配置错误=====
❌ 未配置面板信息
------------------
请在插件配置中填写(二选一):
• 对接青龙: Host丨ClientID丨ClientSecret
• 对接呆呆: Host丨app_key丨app_secret
==================""")
            exit(0)

        qllist = s_mibao_qlname.split('丨')
        if len(qllist) != 3:
            sender.reply("""
=====格式错误=====
❌ 青龙配置格式错误
------------------
正确格式:
Host丨ClientID丨ClientSecret
==================""")
            exit(0)
        QLurl = qllist[0].strip().rstrip('/')
        ClientID = qllist[1].strip()
        ClientSecret = qllist[2].strip()
        if not all([QLurl, ClientID, ClientSecret]):
            sender.reply("❌ 青龙配置参数不完整")
            exit(0)
        if not QLurl.startswith(('http://', 'https://')):
            sender.reply("❌ 青龙地址格式错误")
            exit(0)
        try:
            qltoken = QLtoken(QLurl=QLurl, ClientID=ClientID, ClientSecret=ClientSecret)
            PANEL_KIND = "ql"
            PANEL_BASE = QLurl + "/open"
            return QLurl, qltoken
        except Exception as e:
            raise Exception(f"获取Token失败: {str(e)}")
    except Exception as e:
        sender.reply(f"""
=====连接失败=====
❌ 无法连接面板
------------------
{str(e)}
==================""")
        exit(0)


def delenvs(id):
    if id is None or not QLurl or not qltoken:
        return
    headers = {
        "Authorization": "Bearer" + ' ' + qltoken,
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    if PANEL_KIND == 'dd':
        requests.delete(f"{PANEL_BASE}/envs/{id}", headers=headers, proxies={"http": None, "https": None})
    else:
        requests.delete(f"{PANEL_BASE}/envs", headers=headers, json=[id], proxies={"http": None, "https": None})


def allenvs(osname, account):
    if not QLurl or not qltoken:
        return None
    url = f"{PANEL_BASE}/envs"
    headers = {
        "Authorization": "Bearer" + ' ' + qltoken,
        "accept": "application/json"
    }
    response = requests.get(url=url, headers=headers, proxies={"http": None, "https": None}).json()
    if _resp_ok(response):
        envslist = response.get('data') or []
        for envs in envslist:
            envname = envs.get('name')
            remarks = envs.get('remarks')
            if remarks is None:
                continue
            if osname == envname and str(account) in remarks:
                return _env_id(envs)
        return None
    else:
        sender.reply('连接面板获取变量失败')
        exit(0)


def QLupdate(osname, value, account, qlid, phone, owner_id):
    data = {
        "value": value,
        "name": osname,
        "remarks": f'米包:{account}丨用户:{owner_id}丨手机:{phone}丨小米钱包视频福利'
    }
    headers = {
        "Authorization": "Bearer" + ' ' + qltoken,
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    if PANEL_KIND == 'dd':
        response = requests.put(f"{PANEL_BASE}/envs/{qlid}", headers=headers, json=data, proxies={"http": None, "https": None})
    else:
        data["id"] = qlid
        response = requests.put(f"{PANEL_BASE}/envs", headers=headers, data=json.dumps(data), proxies={"http": None, "https": None})
    if response.status_code in (200, 201):
        response_json = response.json()
        data = response_json.get('data')
        if data is None:
            exit(0)
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            exit(0)
        return _env_id(data)
    else:
        sender.reply('更新变量失败，请联系管理员处理')
        exit(0)


def QLzt(osname, value, account, phone, owner_id):
    try:
        env = {
            "value": value,
            "name": osname,
            "remarks": f'米包:{account}丨用户:{owner_id}丨手机:{phone}丨小米钱包视频福利'
        }
        headers = {
            "Authorization": f"Bearer {qltoken}",
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = env if PANEL_KIND == 'dd' else [env]
        response = requests.post(f"{PANEL_BASE}/envs", headers=headers, json=payload, proxies={"http": None, "https": None})
        if response.status_code not in (200, 201):
            sender.reply(f"""
=====添加变量失败=====
❌ 请求失败
状态码: {response.status_code}
==================""")
            exit(0)
        result = response.json()
        if not _resp_ok(result):
            sender.reply(f"""
=====添加变量失败=====
❌ 面板返回错误
错误信息: {result.get('message') or result.get('error')}
==================""")
            exit(0)
        if "value must be unique" in response.text:
            return
        data = result.get('data')
        if isinstance(data, list):
            if not data or not isinstance(data[0], dict):
                sender.reply("=====添加变量失败=====\n❌ 面板返回数据异常")
                exit(0)
            return _env_id(data[0])
        if isinstance(data, dict):
            return _env_id(data)
        sender.reply("=====添加变量失败=====\n❌ 面板返回数据异常")
        exit(0)
    except Exception as e:
        sender.reply(f"""
=====系统错误=====
❌ 添加面板变量失败
------------------
{str(e)}
==================""")
        exit(0)


def Addenvs(osname, value, account, phone, owner_id):
    if not QLurl or not qltoken:
        return
    qlid = allenvs(osname, account)
    if qlid is None:
        QLzt(osname, value, account, phone, owner_id)
    else:
        QLupdate(osname, value, account, qlid, phone, owner_id)


# ============================================================
# 账号存储工具
# ============================================================
def load_accounts():
    """读取当前用户账号列表：返回 list[dict]"""
    raw = middleware.bucketGet(bucket=BUCKET_USER, key=userid) or '[]'
    try:
        accs = json.loads(raw)
        if not isinstance(accs, list):
            accs = []
    except Exception:
        accs = []
    return accs


def save_accounts(accs):
    middleware.bucketSet(BUCKET_USER, userid, json.dumps(accs, ensure_ascii=False))


def build_env_value(accs):
    """把账号列表拼成 xiaomiAccount 形式（& 分隔）"""
    return "&".join(
        f"{a.get('name','')}#{a.get('user_id','')}#{a.get('pass_token','')}#{a.get('oaid','')}#{a.get('ua','')}"
        for a in accs
    )


def sync_to_panel(accs):
    """把全部账号同步到面板（单变量 xiaomiAccount，含全部账号）"""
    global QLurl, qltoken
    if not (s_mibao_qlname or s_mibao_ddname):
        return False, "未配置面板(青龙/呆呆)，仅本地保存"
    if not accs:
        # 无账号则删除已存在的变量
        try:
            QLurl, qltoken = seekql()
            eid = allenvs(s_mibao_osname, userid)
            if eid is not None:
                delenvs(eid)
        except Exception:
            pass
        return True, "已清空面板变量"
    try:
        QLurl, qltoken = seekql()
        value = build_env_value(accs)
        Addenvs(osname=s_mibao_osname, value=value, account=userid, phone=userid, owner_id=userid)
        return True, "已同步到面板"
    except Exception as e:
        return False, f"同步失败: {str(e)}"


# ============================================================
# 小米账号登录（三种方式，免费无授权）
#   1) 扫码登录     —— account.xiaomi.com 二维码流程
#   2) 账号密码登录 —— serviceLoginAuth2（sid=miui_vip_a）
#   3) 手动Cookie登录 —— 提交 passToken#userId 或 完整 Cookie 串
# 三者最终都得到 passToken + userId，经 refresh_cookies 换钱包 Cookie，
# 并统一存入 账号名#userid#passToken#oaid#ua 格式。
# ============================================================
ANDROID_UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36"


def _parse_xiaomi_json(text):
    """小米接口常返回 &&&START&&& 前缀的 JSONP，去掉前缀再解析"""
    if isinstance(text, (bytes, bytearray)):
        text = text.decode("utf-8", "ignore")
    cleaned = text.lstrip('&').lstrip('START').lstrip('&')
    return json.loads(cleaned)


def parse_cookie_string(cookie_str):
    """把 'k=v; k2=v2' 形式的 Cookie 串解析成 dict"""
    cookies = {}
    for item in (cookie_str or "").split(';'):
        item = item.strip()
        if not item or '=' not in item:
            continue
        k, v = item.split('=', 1)
        cookies[k.strip()] = v.strip()
    return cookies


class XiaomiAuthError(Exception):
    """账号密码登录异常，kind 标记失败类型: captcha / pwd_wrong / other"""
    def __init__(self, message, kind="other"):
        super().__init__(message)
        self.kind = kind


def _xiaomi_password_auth(user, password):
    """账号密码登录：POST serviceLoginAuth2 拿 passToken/userId。
    返回 (pass_token, user_id)；失败抛 XiaomiAuthError(kind=...)。"""
    data = {
        'qs': '%3F_json%3Dtrue%26sid%3Dmiui_vip_a%26_locale%3Dzh_CN',
        'callback': 'https://api-alpha.vip.miui.com/sts',
        '_json': 'true',
        '_sign': 'eQzFP7RKdHfN0VKBbp86ZVzlgq0=',
        'user': user,
        'hash': hashlib.md5(password.encode()).hexdigest().upper(),
        'sid': 'miui_vip_a',
        '_locale': 'zh_CN',
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 14; 2210132C Build/UKQ1.230705.002) APP/xiaomi.vipaccount APPV/20231107 MK/WGlhb21p IDEzIFBybw== SDKV/5.1.0.release.13 PassportSDK/5.1.0.release.15 passport-ui/5.1.0.release.15',
        'Host': 'account.xiaomi.com',
        'Connection': 'Keep-Alive',
    }
    resp = requests.post(
        'https://account.xiaomi.com/pass/serviceLoginAuth2',
        data=data, headers=headers,
        cookies={'deviceId': 'S13aukyf5y2jecCG'}, timeout=30,
    )
    if resp.status_code != 200:
        raise XiaomiAuthError('登录请求失败', 'other')
    if not resp.text:
        raise XiaomiAuthError('服务器返回空响应', 'other')
    try:
        result = _parse_xiaomi_json(resp.text)
    except json.JSONDecodeError:
        raise XiaomiAuthError(f'解析响应失败: {resp.text[:120]}', 'other')
    status = result.get('code', -1)
    message = result.get('desc', '未知错误')
    pass_token = result.get('passToken')
    user_id = str(result.get('userId', ''))
    if status == 0 and pass_token and user_id:
        return pass_token, user_id
    if status == 87001 or '验证码' in message or result.get('securityStatus') == 16 or '安全验证' in message:
        raise XiaomiAuthError(f'需要安全验证(验证码): {message}', 'captcha')
    if status == 70016 or '用户名或密码不正确' in message or '密码错误' in message:
        raise XiaomiAuthError('用户名或密码不正确', 'pwd_wrong')
    raise XiaomiAuthError(f'登录失败: {message}', 'other')


def _store_login(name, pass_token, user_id, src="登录"):
    """统一把账号(passToken方式)存入账号列表并同步面板。"""
    user_id = str(user_id)
    acc = {"name": name, "user_id": user_id, "pass_token": pass_token, "oaid": "", "ua": ANDROID_UA}
    accs = load_accounts()
    accs = [a for a in accs if a.get("user_id") != user_id]
    accs.append(acc)
    save_accounts(accs)
    u = XiaomiUser(1, f"{name}#{user_id}#{pass_token}#{''}#{ANDROID_UA}")
    ok = u.refresh_cookies()
    ok2, msg = sync_to_panel(accs)
    sender.reply(f"""
====={src}登录成功=====
✅ 账号: {mask_str(user_id)}
{'✅ Cookie刷新成功' if ok else '⚠️ Cookie刷新失败(运行时会自动重试)'}
📦 当前共: {len(accs)} 个账号
🔄 面板同步: {msg}
------------------
发送「米包运行」执行任务""")


# ---------- 1) 扫码登录 ----------
def mi_qr_get():
    """获取小米扫码登录二维码：返回 (qr_img_bytes, lp_url, qr_url)"""
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0")
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Referer': 'https://account.xiaomi.com/',
        'User-Agent': ua,
        'X-Requested-With': 'XMLHttpRequest',
    }
    dc = str(int(time.time() * 1000))
    qr_url_request = (
        "https://account.xiaomi.com/longPolling/loginUrl"
        "?_group=DEFAULT&_qrsize=240"
        "&qs=%253Fcallback%253Dhttps%25253A%25252F%25252Faccount.xiaomi.com%25252Fsts%25253Fsign%25253DZvAtJIzsDsFe60LdaPa76nNNP58%2525253D%252526followup%25253Dhttps%25253A%2525252F%2525252Faccount.xiaomi.com%2525252Fpass%2525252Fauth%2525252Fsecurity%2525252Fhome%252526sid%25253Dpassport"
        "&sid=passport&needTheme=false&showActiveX=false"
        "&serviceParam=%7B%22checkSafePhone%22:false,%22checkSafeAddress%22:false,%22lsrp_score%22:0.0%7D"
        "&_locale=zh_CN"
        "&_sign=2%26V1_passport%26BUcblfwZ4tX84axhVUaw8t6yi2E%3D"
        f"&_dc={dc}"
    )
    resp = requests.get(qr_url_request, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"获取二维码请求失败: HTTP {resp.status_code}")
    data = _parse_xiaomi_json(resp.text)
    qr_url = data.get('qr')
    lp_url = data.get('lp')
    if not qr_url or not lp_url:
        raise Exception(f"获取二维码失败: {data}")
    qr_img = requests.get(qr_url, headers=headers, timeout=30).content
    return qr_img, lp_url, qr_url


def mi_qr_poll(lp_url, timeout=120):
    """轮询 lp 地址直到用户扫码授权。返回含 passToken/userId 的 dict 或 None(超时)。"""
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0")
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'Referer': 'https://account.xiaomi.com/',
        'User-Agent': ua,
        'X-Requested-With': 'XMLHttpRequest',
    }
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            rr = requests.get(lp_url, headers=headers, timeout=30)
            if rr.status_code == 200 and rr.text:
                data = _parse_xiaomi_json(rr.text)
                if data.get('code') == 0:
                    pass_token = data.get('passToken')
                    user_id = str(data.get('userId', ''))
                    if pass_token and user_id:
                        return {"passToken": pass_token, "userId": user_id}
        except Exception:
            pass
        time.sleep(3)
    return None


# ============================================================
# 指令实现
# ============================================================
def mi_qrcode():
    """米包扫码：生成二维码 → 用户扫码授权 → 自动存账号(passToken方式)"""
    sender.reply("=====米包扫码登录=====\n正在生成二维码，请稍候...")
    try:
        qr_img, lp_url, qr_url = mi_qr_get()
    except Exception as e:
        sender.reply(f"❌ 生成二维码失败: {str(e)}")
        return
    # 优先直接发送图片 URL（对齐参考插件）；失败回退 base64
    sent = False
    try:
        sender.replyImage(qr_url)
        sent = True
    except Exception:
        pass
    if not sent:
        try:
            sender.replyImage(base64.b64encode(qr_img).decode())
            sent = True
        except Exception:
            sender.reply(f"⚠️ 图片发送失败，请用浏览器打开二维码:\n{qr_url}")
    sender.reply("📱 请用小米APP / 米家APP 扫描上方二维码并授权（约2分钟内有效）...")

    login_result = mi_qr_poll(lp_url, timeout=120)
    if not login_result or not login_result.get("passToken") or not login_result.get("userId"):
        sender.reply("⌛ 等待扫码超时未授权，可重新发送「米包扫码」重试。")
        return

    pass_token = login_result["passToken"]
    user_id = str(login_result["userId"])
    name = f"扫码-{mask_str(user_id)}"
    _store_login(name, pass_token, user_id, src="扫码")


def mi_login():
    """米包登录：登录方式选择菜单（扫码 / 账号密码 / 手动Cookie / 高级粘贴）"""
    menu = """
=====米包登录=====
请选择登录方式:
[1] 扫码登录
[2] 账号密码登录
[3] 手动Cookie登录
[4] 粘贴完整账号行(高级)
------------------
回复序号选择，回复 'q' 退出"""
    sender.reply(menu)
    choice = sender.listen(60000)
    if not choice or choice.strip().lower() == 'q':
        sender.reply("✅ 已退出登录流程")
        return
    choice = choice.strip()
    if choice == '1':
        mi_qrcode()
    elif choice == '2':
        mi_password_login()
    elif choice == '3':
        mi_cookie_login()
    elif choice == '4':
        mi_login_paste()
    else:
        sender.reply('❌ 无效的选择')


def mi_login_paste():
    """高级：直接粘贴完整账号行 账号名#userid#passToken#oaid#ua（每行一个）"""
    sender.reply("""
=====粘贴完整账号行(高级)=====
请粘贴小米账号，每行一个:
格式: 账号名#userid#passToken#oaid#ua
示例: 我的小号#123456789#abcd-efgh#oaid串#Mozilla/5.0...
------------------
支持多行批量；回复 'q' 退出""")
    user_input = sender.listen(300000)
    if not user_input:
        sender.reply("❌ 输入超时")
        return
    if user_input.strip().lower() == 'q':
        sender.reply("✅ 已退出操作")
        return

    accs = load_accounts()
    added = 0
    skipped = 0
    for line in user_input.replace("&", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("#", 4)
        if len(parts) != 5:
            skipped += 1
            continue
        name, uid, pt, oaid, ua = [p.strip() for p in parts]
        # 去重：同一 user_id 覆盖
        accs = [a for a in accs if a.get("user_id") != uid]
        accs.append({"name": name, "user_id": uid, "pass_token": pt, "oaid": oaid, "ua": ua})
        added += 1

    save_accounts(accs)
    ok, msg = sync_to_panel(accs)
    sender.reply(f"""
=====登录成功=====
✅ 新增/更新: {added} 个
⏭️ 跳过(格式错): {skipped} 个
📦 当前共: {len(accs)} 个账号
🔄 面板同步: {msg}
------------------
发送「米包运行」执行任务
发送「米包查询」查看进度
发送「米包管理」管理账号""")


# ---------- 2) 账号密码登录 ----------
def mi_password_login():
    """米包账号密码登录：输入手机号/邮箱 + 密码 → serviceLoginAuth2 拿 passToken。"""
    sender.reply("""
=====账号密码登录=====
请输入小米账号(手机号/邮箱):
回复 'q' 退出""")
    user = sender.listen(120000)
    if not user or user.strip().lower() == 'q':
        sender.reply("✅ 已退出登录流程")
        return
    user = user.strip()
    sender.reply("请输入密码:\n回复 'q' 退出")
    password = sender.listen(120000)
    if not password or password.strip().lower() == 'q':
        sender.reply("✅ 已退出登录流程")
        return
    password = password.strip()

    try:
        pass_token, user_id = _xiaomi_password_auth(user, password)
    except XiaomiAuthError as e:
        if e.kind == 'captcha':
            sender.reply(f"⚠️ 账号 {mask_str(user)} 需要安全验证(验证码)，已自动切换到扫码登录模式\n{str(e)}")
            mi_qrcode()
            return
        elif e.kind == 'pwd_wrong':
            sender.reply(f"❌ {str(e)}\n可发送「米包扫码」使用扫码登录，或重新发送「米包登录」选择账号密码重试。")
            return
        else:
            sender.reply(f"❌ 登录失败: {str(e)}")
            return

    # 免费版不保存密码，仅保存 passToken
    _store_login(user, pass_token, user_id, src="账号密码")


# ---------- 3) 手动Cookie登录 ----------
def mi_cookie_login():
    """米包手动Cookie登录：提交 passToken#userId 或 完整 Cookie 串（含 passToken/userId）。"""
    sender.reply("""
=====手动Cookie登录=====
请提交抓包获取的Cookie
支持格式：
1. 完整Cookie字符串(包含 passToken 和 userId)
2. passToken#userId 格式
------------------
示例：
passToken=xxx; userId=yyy
或
xxx#yyy
------------------
请输入Cookie:""")
    cookie_input = sender.listen(120000)
    if not cookie_input or cookie_input.strip().lower() == 'q':
        sender.reply('✅ 已取消登录')
        return
    cookie_input = cookie_input.strip()
    pass_token = ''
    user_id = ''
    if '#' in cookie_input:
        parts = cookie_input.split('#')
        if len(parts) == 2:
            pass_token, user_id = parts[0].strip(), parts[1].strip()
        else:
            sender.reply('❌ Cookie格式错误，使用#分隔时应为: passToken#userId')
            return
    elif 'passToken=' in cookie_input and 'userId=' in cookie_input:
        cookies = parse_cookie_string(cookie_input)
        pass_token = cookies.get('passToken', '').strip()
        user_id = cookies.get('userId', '').strip()
    else:
        sender.reply('❌ Cookie格式不正确，请确保包含 passToken 和 userId')
        return
    if not pass_token or not user_id:
        sender.reply('❌ 无法提取 passToken 或 userId，请检查Cookie格式')
        return
    sender.reply(f"🔄 正在验证Cookie...\n👤 UserID: {mask_str(user_id)}")
    u = XiaomiUser(1, f"手动#{user_id}#{pass_token}#{''}#{ANDROID_UA}")
    if not u.refresh_cookies():
        sender.reply('❌ Cookie验证失败，请确认Cookie是否正确或已过期')
        return
    sender.reply('✅ Cookie验证成功！\n请输入账号备注名(用于管理区分):')
    name = sender.listen(60000)
    if not name:
        name = f"Cookie-{mask_str(user_id)}"
    else:
        name = name.strip()
    _store_login(name, pass_token, user_id, src="手动Cookie")


def _run_accounts(accs, query_only):
    """执行/查询全部账号，返回汇总文本"""
    if s_mibao_proxy:
        os.environ["XM_PROXY"] = s_mibao_proxy

    summary = []
    for i, a in enumerate(accs, 1):
        cfg_str = f"{a.get('name','')}#{a.get('user_id','')}#{a.get('pass_token','')}#{a.get('oaid','')}#{a.get('ua','')}"
        u = XiaomiUser(i, cfg_str)
        print(f"\n{'='*40}\n🔄 账号 [{i}/{len(accs)}] {u.name}\n{'='*40}")
        if not u.refresh_cookies():
            u.log("Cookie刷新失败，跳过该账号")
            summary.append(f"• {mask_str(u.name)} ❌ Cookie刷新失败")
            continue
        u.execute_daily_tasks(query_only=query_only)
        # 取最后几条日志作为汇总
        tail = u.logs[-3:] if u.logs else []
        summary.append(f"• {mask_str(u.name)} " + (" | ".join(tail[-1:]) if tail else "已完成"))

    header = "【米包查询】" if query_only else "【米包运行】"
    result = header + f" 共 {len(accs)} 个账号\n" + "\n".join(summary)
    return result


def mi_query():
    """米包查询：仅查询任务进度"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「米包登录」")
        return
    sender.reply(f"🔎 正在查询 {len(accs)} 个账号(仅查询)...")
    result = _run_accounts(accs, query_only=True)
    sender.reply(result)


def mi_run():
    """米包运行：执行全部视频福利任务"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「米包登录」")
        return
    sender.reply(f"🚀 正在执行 {len(accs)} 个账号的视频福利任务...")
    result = _run_accounts(accs, query_only=False)
    sender.reply(result)


def mi_manage():
    """米包管理：列出账号，可删除单个 / 清空"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「米包登录」")
        return
    lines = ["=====米包管理=====", f"当前共 {len(accs)} 个账号:"]
    for i, a in enumerate(accs, 1):
        lines.append(f"[{i}] {mask_str(a.get('name',''))} (uid:{mask_str(a.get('user_id',''))})")
    lines.append("------------------")
    lines.append("回复数字删除对应账号")
    lines.append("回复 'all' 清空全部")
    lines.append("回复 'q' 退出")
    sender.reply("\n".join(lines))

    choice = sender.listen(60000)
    if not choice:
        sender.reply("❌ 输入超时")
        return
    choice = choice.strip().lower()
    if choice == 'q':
        sender.reply("✅ 已退出操作")
        return
    if choice == 'all':
        save_accounts([])
        ok, msg = sync_to_panel([])
        sender.reply(f"✅ 已清空全部账号\n🔄 面板同步: {msg}")
        return
    try:
        idx = int(choice)
        if not 1 <= idx <= len(accs):
            sender.reply("❌ 无效的选择")
            return
        removed = accs.pop(idx - 1)
        save_accounts(accs)
        ok, msg = sync_to_panel(accs)
        sender.reply(f"✅ 已删除 {mask_str(removed.get('name',''))}\n🔄 面板同步: {msg}")
    except ValueError:
        sender.reply("❌ 无效的选择")


def mi_clean():
    """米包清理：删除全部账号（与管理的 all 一致，保留独立指令）"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 没有可清理的账号")
        return
    sender.reply(f"⚠️ 确认清空全部 {len(accs)} 个账号吗？(y/n)")
    confirm = sender.listen(30000)
    if not confirm:
        sender.reply("❌ 输入超时")
        return
    if confirm.strip().lower() not in ('y', 'yes', '是'):
        sender.reply("✅ 已取消")
        return
    save_accounts([])
    ok, msg = sync_to_panel([])
    sender.reply(f"✅ 已清空全部账号\n🔄 面板同步: {msg}")


def mi_update():
    """米包更新：重新将账号同步到面板变量（适配面板端重新拉起脚本）"""
    accs = load_accounts()
    ok, msg = sync_to_panel(accs)
    if accs:
        if ok:
            sender.reply(f"✅ 已重新同步 {len(accs)} 个账号到面板\n🔄 {msg}\n\n提示: 在面板里用定时任务触发「米包运行」即可每日跑量。")
        else:
            sender.reply(f"⚠️ 同步未完成: {msg}\n本地仍保存 {len(accs)} 个账号。\n在插件配置里填好青龙/呆呆信息后可再次发送「米包更新」。")
    else:
        sender.reply(f"⚠️ 本地无账号，{msg}")


def mi_check():
    """米包检测：校验每个账号 Cookie 是否可刷新（无授权、纯连通性检查）"""
    accs = load_accounts()
    if not accs:
        sender.reply("❌ 你还没有账号，请先发送「米包登录」")
        return
    sender.reply(f"🔎 正在检测 {len(accs)} 个账号有效性...")
    lines = []
    for i, a in enumerate(accs, 1):
        cfg_str = f"{a.get('name','')}#{a.get('user_id','')}#{a.get('pass_token','')}#{a.get('oaid','')}#{a.get('ua','')}"
        u = XiaomiUser(i, cfg_str)
        ok = u.refresh_cookies()
        lines.append(f"• {mask_str(u.name)} {'✅ 有效' if ok else '❌ 失效'}")
    sender.reply("=====米包检测=====\n" + "\n".join(lines))


# ============================================================
# 指令路由
# ============================================================
def handle_command(message):
    message = str(message or '').strip()
    if '登录' in message or '登陆' in message:
        mi_login()
    elif '扫码' in message:
        mi_qrcode()
    elif '运行' in message:
        mi_run()
    elif '查询' in message:
        mi_query()
    elif '管理' in message:
        mi_manage()
    elif '清理' in message:
        mi_clean()
    elif '更新' in message:
        mi_update()
    elif '检测' in message:
        mi_check()
    else:
        sender.setContinue()


def main():
    """主函数（免费版：无授权校验、无外部 shouquan kill-switch）"""
    try:
        message = sender.getMessage().strip()
        handle_command(message)
    except Exception as e:
        sender.reply(f"❌ 运行出错: {str(e)}")


if __name__ == "__main__":
    main()
