# [title: 商联道小程序]
# [language: python]
# [rule: ^(商联道)(登录|查询|运行|管理|清理|更新|检测)((?:\s+\S+)*)$]
# [disable:false]
# [open_source: false]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public:true]
# [version: 1.0.0]
# [price: 0]
# [author: 呆呆插件改造版]
# [service: ]
# [description: ❶🏮商联道小程序，YYB获取微信code，签到、激励视频、健康文章、广场发帖、好友聊天、全勤奖、余额查询、自动提现<br>❷对接呆呆面板与青龙面板双平台；账号格式：备注#YYB_SERVER#PLUSPLUS_TOKEN#PROXY_API#PROXY_TYPE<br>❸指令：『商联道登录』粘贴导入账号、『商联道运行』执行全部任务、『商联道查询』仅查询账号状态、『商联道管理』账号管理、『商联道清理』清空账号、『商联道更新』同步面板变量、『商联道检测』校验账号配置<br>❹支持品赞代理、单账号独立pushplus推送，token/reward_session缓存，失效自动刷新]
# [param: {"required":false,"key":"s_sld.s_sld_qlname","bool":false,"placeholder":"Host丨ClientID丨ClientSecret","name":"对接青龙","desc":"各参数之间用中文符丨分割，例如: http://127.0.0.1:5700/丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_sld.s_sld_ddname","bool":false,"placeholder":"Host丨app_key丨app_secret","name":"对接呆呆面板","desc":"留空则使用青龙面板。各参数之间用中文符丨分割，例如: http://127.0.0.1:5700丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_sld.s_sld_osname","bool":false,"placeholder":"sldAccount","name":"环境变量名","desc":"同步到青龙/呆呆的变量名称，默认 sldAccount"}]
# [param: {"required":false,"key":"s_sld.s_sld_proxy_global","bool":false,"placeholder":"http://127.0.0.1:7890","name":"全局代理地址","desc":"可选，http/socks5，优先使用账号内独立代理配置"}]
# -*- coding: utf-8 -*-
"""
呆呆插件版｜商联道小程序
完整移植原脚本全部业务：YYB code获取、签名、签到、广告、文章、发帖、聊天、全勤、自动提现、代理、pushplus推送
token与reward_session缓存在插件bucket，自动刷新
"""
import os
import re
import sys
import json
import time
import random
import string
import hashlib
import hmac
import traceback
from datetime import datetime
from urllib.parse import quote
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SCRIPT_VERSION = "v1.0.0"
BUCKET = 's_sld'
BUCKET_USER = 's_sld_user'
APPID = "wx31a4573b0bf1fcb3"
BASE_URL = "https://mini.shangliandao.cn"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
REWARD_SESSION_REFRESH_URL = f"{BASE_URL}/api/auth/reward-session/refresh"
PROFILE_URL = f"{BASE_URL}/api/user/profile"
POINTS_URL = f"{BASE_URL}/api/points"
SIGN_DETAIL_URL = f"{BASE_URL}/api/rewards/sign-in-detail"
SIGN_IN_URL = f"{BASE_URL}/api/rewards/sign-in"
HOME_REWARD_CONFIG_URL = f"{BASE_URL}/api/rewards/home-reward-config"
HOME_REWARD_STATUS_URL = f"{BASE_URL}/api/rewards/home-reward-status"
AD_CHALLENGE_URL = f"{BASE_URL}/api/rewards/ad-challenge"
AD_COMPLETE_URL = f"{BASE_URL}/api/rewards/ad-complete"
AD_REWARD_RETRY_URL = f"{BASE_URL}/api/rewards/ad-reward-retry"
DAILY_TASK_STATUS_URL = f"{BASE_URL}/api/daily-task/status"
DAILY_TASK_FULL_REWARD_CLAIM_URL = f"{BASE_URL}/api/daily-task/full-reward/claim"
ARTICLE_LIST_PAGE_URL = f"{BASE_URL}/api/article/list-page"
ARTICLE_TODAY_STATS_URL = f"{BASE_URL}/api/article/today-stats"
SOCIAL_POSTS_URL = f"{BASE_URL}/api/social/posts"
SOCIAL_CONVERSATIONS_URL = f"{BASE_URL}/api/social/conversations"
SOCIAL_MESSAGES_URL = f"{BASE_URL}/api/social/messages"
GOLDEN_BEAN_WITHDRAW_STATUS_URL = f"{BASE_URL}/api/user/golden-bean/withdraw/status"
GOLDEN_BEAN_WITHDRAW_APPLY_URL = f"{BASE_URL}/api/user/golden-bean/withdraw/apply"

PROXY_RETRY_TIMES = 3
PROXY_VALIDATE_URL = "http://httpbin.org/ip"
PROXY_FETCH_INTERVAL = 3
ENABLE_DIRECT_FALLBACK = True
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2541923) XWEB/19823"
)
NONCE_CHARS = string.ascii_letters + string.digits + "_-"
POST_CONTENT_POOL = [
    "今天天气不错，来广场逛逛，顺便分享一个生活小妙招：衣服沾上油渍可以先用洗洁精干搓再洗，亲测有效！",
    "分享一个健康小知识：饭后不要马上坐下，靠墙站十分钟，对消化和体态都有帮助。",
    "最近在学收纳整理，桌面清爽了心情都变好了，推荐大家试试断舍离。",
    "早睡早起真的有用，坚持了一周感觉白天精神好多了，一起加油。",
    "买菜的时候发现应季的蔬菜水果又新鲜又便宜，大家平时喜欢买什么？",
]

# 兼容yyb_account_guard
try:
    from yyb_account_guard import filter_accounts, update_from_result
except ImportError:
    def filter_accounts(lst, app_id, log):
        return [i for i in lst if i.strip()]
    def update_from_result(server, result, app_id):
        pass

# =====================工具函数=====================
def mask_str(s, head=3, tail=2):
    if not s:
        return ""
    s = str(s)
    if len(s) <= head + tail:
        return "*" * len(s)
    return s[:head] + "*" * (len(s) - head - tail) + s[-tail:]

def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default

def safe_int(value, default=0):
    try:
        return int(float(value or default))
    except Exception:
        return default

def json_preview(data, limit=600):
    try:
        return json.dumps(data, ensure_ascii=False)[:limit]
    except Exception:
        return str(data)[:limit]

def safe_data(resp):
    d = resp.get("data")
    return d if isinstance(d, dict) else {}

def direct_session():
    s = requests.Session()
    s.trust_env = False
    return s

def parse_yyb_entry(raw):
    raw = str(raw or "").strip()
    if "@" not in raw:
        server = raw.rstrip("/")
        if "://" in server:
            server = server.split("://",1)[1]
        return server, ""
    server, ref = raw.split("@",1)
    server = server.strip().rstrip("/")
    if "://" in server:
        server = server.split("://",1)[1]
    ref = ref.strip()
    return server, ref

def get_code(entry):
    server, ref = parse_yyb_entry(entry)
    if not server:
        return None, "server为空"
    if not ref:
        url = f"http://{server}/login"
        try:
            resp = direct_session().get(url, params={"appId":APPID}, timeout=20)
            j = resp.json()
            if j.get("err")==0 and j.get("code"):
                return str(j["code"]), None
            return None, f"获取code失败:{json_preview(j)}"
        except Exception as e:
            return None, f"获取code异常:{str(e)}"
    url = f"http://{server}/wxapp/getCode"
    try:
        resp = direct_session().post(url, json={"ref":ref,"app_id":APPID}, timeout=20)
        j = resp.json()
        res = j.get("data") or {}
        if isinstance(res, dict):
            res = res.get("result") or res
        code = res.get("code")
        if not code and isinstance(j.get("result"), dict):
            code = j["result"].get("code")
        if not code and isinstance(j.get("code"), str):
            code = j.get("code")
        if not code:
            return None, f"获取code失败:{json_preview(j)}"
        return str(code), None
    except Exception as e:
        return None, f"获取code异常:{str(e)}"

# 签名相关
def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def hmac_sha256_hex(key, message):
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()

def encode_component(value):
    return quote(str(value), safe="")

def canonical_query(params):
    pairs = []
    for key in sorted((params or {}).keys()):
        raw = (params or {})[key]
        if raw is None:
            text = ""
        elif raw is True:
            text = "1"
        elif raw is False:
            text = "0"
        else:
            text = str(raw)
        pairs.append(f"{encode_component(key)}={encode_component(text)}")
    pairs.sort()
    return "&".join(pairs)

def make_nonce():
    return "".join(random.choice(NONCE_CHARS) for _ in range(24))

def make_device_id():
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    num = int(time.time()*1000)
    b36 = ""
    while num>0:
        b36 = digits[num%36] + b36
        num //=36
    rand_hex = f"{random.getrandbits(64):016x}{random.getrandbits(64):016x}"
    return f"sx-{b36}-{rand_hex}"[:64]

def build_sign_headers(method, path, body_text, query, token, device_id, reward_session):
    method_up = (method or "GET").upper()
    body_sha = sha256_hex("" if method_up in ("GET","HEAD") else body_text)
    ts = str(int(time.time()))
    query_text = canonical_query(query)
    headers = {}
    if token:
        nonce = make_nonce()
        msg = "\n".join([method_up, path, query_text, body_sha, ts, nonce, device_id or ""])
        headers["X-Mini-Request-Ts"] = ts
        headers["X-Mini-Request-Nonce"] = nonce
        headers["X-Mini-Request-Body-Sha256"] = body_sha
        headers["X-Mini-Request-Sign"] = hmac_sha256_hex(token, msg)
        session_id = str((reward_session or {}).get("session_id") or "").strip()
        secret = str((reward_session or {}).get("secret") or "").strip()
        if session_id and secret:
            r_ts = str(int(time.time()))
            r_nonce = make_nonce()
            r_msg = "\n".join([method_up, path, query_text, body_sha, r_ts, r_nonce, device_id or "", session_id])
            headers["X-Reward-Session-Id"] = session_id
            headers["X-Reward-Ts"] = r_ts
            headers["X-Reward-Nonce"] = r_nonce
            headers["X-Reward-Body-Sha256"] = body_sha
            headers["X-Reward-Sign"] = hmac_sha256_hex(secret, r_msg)
    return headers

def common_headers(token=None):
    hd = {
        "User-Agent":USER_AGENT,
        "Content-Type":"application/json",
        "Accept":"*/*",
        "xweb_xhr":"1",
        "Referer":f"https://servicewechat.com/{APPID}/52/page-frame.html",
        "Accept-Language":"zh-CN,zh;q=0.9",
    }
    if token:
        hd["Authorization"] = f"Bearer {token}"
    return hd

def extract_token(data):
    if not isinstance(data, dict):
        return None
    inner = data.get("data")
    candidates = []
    if isinstance(inner, dict):
        candidates.append(inner.get("token"))
        user = inner.get("user")
        if isinstance(user, dict):
            candidates.append(user.get("token"))
    for item in candidates:
        if item and item != "null":
            return str(item)
    return None

def parse_proxy_response(text):
    if not isinstance(text,str):
        text = json.dumps(text,ensure_ascii=False)
    text = text.strip()
    if not text:
        return None
    try:
        d = json.loads(text)
        po = None
        if isinstance(d.get("data"),list) and d["data"]:
            po = d["data"][0]
        elif isinstance(d.get("data"),dict):
            po = d["data"]
        elif d.get("ip") and d.get("port"):
            po = d
        elif isinstance(d.get("result"),dict):
            po = d["result"]
        if po:
            host = po.get("ip") or po.get("host")
            port = po.get("port")
            if host and port:
                return {"host":str(host),"port":int(port),"username":po.get("user") or po.get("username") or "","password":po.get("pass") or po.get("password") or ""}
    except Exception:
        pass
    if ":" in text:
        sp = text.split(":")
        if len(sp)>=2:
            return {"host":sp[0],"port":int(sp[1]),"username":sp[2] if len(sp)>2 else "","password":sp[3] if len(sp)>3 else ""}
    return None

def build_proxy_dict(proxy_info, proxy_type):
    if not proxy_info:
        return None
    host = proxy_info["host"]
    port = proxy_info["port"]
    un = proxy_info.get("username","")
    pw = proxy_info.get("password","")
    auth = f"{quote(un)}:{quote(pw)}@" if un and pw else ""
    scheme = "socks5" if proxy_type=="socks5" else "http"
    pu = f"{scheme}://{auth}{host}:{port}"
    return {"http":pu,"https":pu}

def validate_proxy(proxies):
    if not proxies:
        return False,""
    try:
        r = requests.get(PROXY_VALIDATE_URL,proxies=proxies,timeout=15)
        if r.status_code==200:
            ip = r.json().get("origin","未知")
            return True,ip
    except Exception:
        pass
    return False,""

def get_valid_proxy(proxy_api, proxy_type, acc_name):
    if not proxy_api:
        return None,""
    for idx in range(1,PROXY_RETRY_TIMES+1):
        try:
            resp = direct_session().get(proxy_api,timeout=15)
            pi = parse_proxy_response(resp.text)
            if not pi:
                continue
            px = build_proxy_dict(pi, proxy_type)
            ok,ip = validate_proxy(px)
            if ok:
                return px,ip
        except Exception:
            pass
        time.sleep(2)
    return None,""

def request_with_proxy(method, url, proxies=None, server="",**kwargs):
    kwargs.setdefault("timeout",REQUEST_TIMEOUT)
    if proxies:
        try:
            return requests.request(method,url,proxies=proxies,**kwargs)
        except Exception as e:
            if not ENABLE_DIRECT_FALLBACK:
                raise
    s = direct_session()
    return s.request(method,url,**kwargs)

def send_pushplus(token, title, content):
    if not token:
        return
    try:
        requests.post("https://www.pushplus.plus/send",json={"token":token,"title":title,"content":content,"template":"txt"},timeout=10)
    except Exception:
        pass

# =====================账号业务类=====================
class SldUser:
    def __init__(self, index, cfg_str):
        self.index = index
        self.name = ""
        self.yyb_server = ""
        self.pushplus_token = ""
        self.proxy_api = ""
        self.proxy_type = "http"
        self.logs = []
        self.token = None
        self.device_id = None
        self.reward_session = None
        self.cache_key = ""
        self.proxies = None
        self.proxy_ip = ""
        self._parse(cfg_str)

    def _parse(self, cfg_str):
        parts = cfg_str.split("#",4)
        if len(parts)!=5:
            self.name = cfg_str.strip()
            self.log(f"⚠️账号格式错误:{mask_str(cfg_str)}")
            return
        self.name,self.yyb_server,self.pushplus_token,self.proxy_api,self.proxy_type = [x.strip() for x in parts]
        self.cache_key = self.yyb_server
        self.proxy_type = self.proxy_type or "http"

    def log(self, msg):
        line = f"[{_now()}] 账号[{self.index}][{self.name}] {msg}"
        print(line)
        self.logs.append(line)

    def load_cache(self):
        raw = middleware.bucketGet(BUCKET, f"token_{self.cache_key}")
        if not raw:
            return None
        try:
            j = json.loads(raw)
            exp_ts = datetime.fromisoformat(j["expireTime"]).timestamp()*1000
            if time.time()*1000 < exp_ts - 3600*1000:
                return j
        except Exception:
            pass
        return None

    def save_cache(self, entry):
        middleware.bucketSet(BUCKET, f"token_{self.cache_key}", json.dumps(entry,ensure_ascii=False))

    def refresh_reward_session(self):
        self.log("🔄刷新奖励会话")
        payload = {"device_id":self.device_id}
        body_text = json.dumps(payload, separators=(",",":"), ensure_ascii=False)
        path = REWARD_SESSION_REFRESH_URL.split(BASE_URL,1)[-1].split("?",1)[0]
        hd = common_headers(self.token)
        hd["X-Device-Id"] = self.device_id
        hd.update(build_sign_headers("POST", path, body_text, None, self.token, self.device_id, None))
        resp = request_with_proxy("POST", REWARD_SESSION_REFRESH_URL, proxies=self.proxies, data=body_text.encode("utf-8"), headers=hd)
        j = resp.json()
        data = safe_data(j)
        session = data.get("reward_session")
        if j.get("status")==200 and isinstance(session,dict) and session.get("session_id") and session.get("secret"):
            self.reward_session = session
            self.log("✅奖励会话刷新成功")
            return True
        self.log(f"⚠️奖励会话刷新失败:{json_preview(j)}")
        return False

    def reward_session_valid(self):
        if not self.reward_session or not self.reward_session.get("session_id") or not self.reward_session.get("secret"):
            return False
        try:
            expires_at = safe_float(self.reward_session.get("expires_at"))
            if expires_at and expires_at <= time.time()*1000 + 30000:
                return False
        except Exception:
            return False
        return True

    def api_request(self, method, url, payload=None, query=None):
        method_up = method.upper()
        path = url.split(BASE_URL,1)[-1].split("?",1)[0]
        body_text = ""
        if method_up not in ("GET","HEAD") and payload is not None:
            body_text = json.dumps(payload, separators=(",",":"), ensure_ascii=False)
        hd = common_headers(self.token)
        hd["X-Device-Id"] = self.device_id
        hd.update(build_sign_headers(method_up, path, body_text, query, self.token, self.device_id, self.reward_session))
        kwargs = {"headers":hd, "proxies":self.proxies}
        if method_up in ("GET","HEAD"):
            if query:
                kwargs["params"] = query
        else:
            kwargs["data"] = body_text.encode("utf-8")
        resp = request_with_proxy(method_up, url,**kwargs)
        try:
            return resp.json()
        except Exception:
            return {"status":-1,"msg":f"JSON解析失败:{resp.text[:300]}"}

    def login(self):
        cache_data = self.load_cache()
        if cache_data:
            self.token = cache_data["token"]
            self.device_id = cache_data.get("deviceId") or make_device_id()
            self.reward_session = cache_data.get("rewardSession")
            self.log("✅读取缓存token")
            try:
                rj = self.api_request("GET", PROFILE_URL)
                if rj.get("status")==200:
                    if not self.reward_session_valid():
                        self.refresh_reward_session()
                        cache_data["rewardSession"] = self.reward_session
                        self.save_cache(cache_data)
                    self.log("✅缓存token校验通过")
                    return True
            except Exception:
                self.log("⚠️缓存token失效，重新获取code")
        code,err = get_code(self.yyb_server)
        if err or not code:
            self.log(f"❌{err}")
            return False
        self.device_id = make_device_id()
        payload = {"code":code, "device_id":self.device_id}
        body_text = json.dumps(payload, separators=(",",":"), ensure_ascii=False)
        hd = common_headers()
        resp = request_with_proxy("POST", LOGIN_URL, proxies=self.proxies, headers=hd, data=body_text.encode("utf-8"))
        try:
            j = resp.json()
        except Exception:
            j = {"raw":resp.text[:800]}
        self.token = extract_token(j)
        if not self.token:
            self.log(f"❌code换token失败:{json_preview(j)}")
            return False
        inner = safe_data(j)
        self.reward_session = inner.get("reward_session")
        if self.reward_session:
            expires_in = safe_float(self.reward_session.get("expires_in")) or 7*24*3600
            self.reward_session["expires_at"] = time.time()*1000 + expires_in*1000
        expire_time = datetime.fromtimestamp(time.time()+7*24*3600).isoformat()
        self.save_cache({
            "token":self.token,
            "expireTime":expire_time,
            "updateTime":_now(),
            "deviceId":self.device_id,
            "rewardSession":self.reward_session
        })
        self.log("✅登录成功，已缓存token")
        return True

    def task_sign(self):
        detail = self.api_request("GET", SIGN_DETAIL_URL)
        if detail.get("status")!=200:
            return f"获取签到信息失败:{detail.get('msg') or json_preview(detail,200)}"
        d = safe_data(detail)
        if d.get("signed_today"):
            return f"今日已签到，连续 {safe_int(d.get('consecutive_days',0))} 天"
        ticket = str(d.get("sign_ticket") or "").strip()
        if not ticket:
            return "签到票据缺失"
        time.sleep(random.uniform(1,2))
        resp = self.api_request("POST", SIGN_IN_URL, payload={"sign_ticket":ticket})
        if resp.get("status")==200:
            rd = safe_data(resp)
            beans = safe_float(rd.get("golden_beans")) + safe_float(rd.get("first_sign_bonus"))
            streak = safe_int(rd.get("streak_day"),1)
            extra = "，含首次签到奖励" if rd.get("is_first_sign") else ""
            return f"签到成功 +{beans:.0f} 金豆{extra}，连续 {streak} 天"
        return f"签到失败:{resp.get('msg') or json_preview(resp,200)}"

    def task_ad(self):
        status = self.api_request("GET", HOME_REWARD_STATUS_URL)
        if status.get("status")!=200:
            return f"获取广告状态失败:{status.get('msg') or json_preview(status,200)}"
        d = safe_data(status)
        remain = safe_int(d.get("ad_remaining_today"),0)
        min_watch = safe_int(d.get("min_watch_seconds"),15)
        if remain <=0:
            return f"今日广告已完成（{safe_int(d.get('ad_count_today',0))}/{safe_int(d.get('ad_daily_limit',20))}）"
        total = 0.0
        watched = 0
        data = d
        for r in range(remain):
            ad_page_session = str(data.get("ad_page_session") or "").strip()
            ad_ticket = str(data.get("ad_ticket") or "").strip()
            if not ad_page_session or not ad_ticket:
                status = self.api_request("GET", HOME_REWARD_STATUS_URL)
                data = safe_data(status)
                ad_page_session = str(data.get("ad_page_session") or "").strip()
                ad_ticket = str(data.get("ad_ticket") or "").strip()
                if not ad_page_session or not ad_ticket:
                    break
            chal = self.api_request("POST", AD_CHALLENGE_URL, payload={"scene":"home_reward","ad_page_session":ad_page_session,"ad_ticket":ad_ticket})
            chal_token = str(safe_data(chal).get("challenge_token") or "").strip()
            if not chal_token:
                self.log(f"⚠️广告第{r+1}次票据失败:{json_preview(chal,200)}")
                break
            watch_sec = min_watch + random.randint(15,22)
            self.log(f"⏳广告第{r+1}/{remain}次，模拟观看{watch_sec}s")
            time.sleep(watch_sec)
            comp_payload = {"scene":"home_reward","watch_seconds":watch_sec,"challenge_token":chal_token,"ad_page_session":ad_page_session}
            comp = self.api_request("POST", AD_COMPLETE_URL, payload=comp_payload)
            cd = safe_data(comp)
            if comp.get("status")==50305 and cd.get("biz_no"):
                time.sleep(1.5)
                comp = self.api_request("POST", AD_REWARD_RETRY_URL, payload={"biz_no":cd["biz_no"]})
                cd = safe_data(comp)
            if comp.get("status")!=200:
                self.log(f"⚠️广告第{r+1}次记录失败:{comp.get('msg') or json_preview(comp,200)}")
                break
            amt = safe_float(cd.get("amount"))
            total += amt
            watched +=1
            self.log(f"✅广告第{r+1}次完成 +{amt:.0f}金豆")
            time.sleep(random.uniform(3,6))
            status = self.api_request("GET", HOME_REWARD_STATUS_URL)
            data = safe_data(status)
            if safe_int(data.get("ad_remaining_today"),0) <=0:
                break
        return f"观看广告 {watched} 次，+{total:.0f} 金豆"

    def pick_quiz_answer(self, article):
        quiz = article.get("quiz") or {}
        opts = quiz.get("options") or []
        if not opts:
            return "A"
        content = str(article.get("content") or "")
        best_id = str(opts[0].get("id") or "A")
        best_score = -1
        for o in opts:
            t = str(o.get("text") or "")
            score = sum(1 for ch in t if ch in content)
            if score>best_score:
                best_score = score
                best_id = str(o.get("id") or best_id)
        return best_id

    def run_one_article(self, article_id):
        detail = self.api_request("GET", f"{BASE_URL}/api/article/{article_id}")
        if detail.get("status")!=200:
            return False,0.0,f"文章详情失败:{detail.get('msg') or ''}"
        art = safe_data(detail)
        read_session_id = str(art.get("read_session_id") or "").strip()
        read_dur = safe_int(art.get("read_duration"),30)
        if not read_session_id:
            return False,0.0,"阅读会话缺失"
        quiz_ticket = ""
        hb_interval =10
        for _ in range(read_dur//hb_interval +3):
            time.sleep(hb_interval)
            hb = self.api_request("POST", f"{BASE_URL}/api/article/{article_id}/heartbeat", payload={"read_session_id":read_session_id})
            ts = safe_data(hb).get("today_status") or {}
            if ts.get("is_qualified"):
                quiz_ticket = str(ts.get("quiz_ticket") or "").strip()
                if quiz_ticket:
                    break
        if not quiz_ticket:
            return False,0.0,"阅读时长未达标"
        ans = self.pick_quiz_answer(art)
        q_resp = self.api_request("POST", f"{BASE_URL}/api/article/{article_id}/quiz", payload={"answer":ans,"read_session_id":read_session_id,"quiz_ticket":quiz_ticket})
        if q_resp.get("status")!=200:
            return False,0.0,f"答题失败:{q_resp.get('msg') or ''}"
        qd = safe_data(q_resp)
        beans = safe_float(qd.get("bean_amount"))
        correct = qd.get("quiz_correct")
        self.log(f"{'✅' if correct else '⚠️'}文章{article_id}答题{'正确' if correct else '错误(安慰奖)'} +{beans:.0f}金豆")
        if qd.get("double_enabled") and not qd.get("bean_doubled"):
            chal = self.api_request("POST", AD_CHALLENGE_URL, payload={"scene":"article_reward_double","session_id":str(article_id)})
            chal_tk = str(safe_data(chal).get("challenge_token") or "").strip()
            if chal_tk:
                watch_sec = 30 + random.randint(3,10)
                self.log(f"⏳文章{article_id}双倍广告等待{watch_sec}s")
                time.sleep(watch_sec)
                comp = self.api_request("POST", AD_COMPLETE_URL, payload={"scene":"article_reward_double","watch_seconds":watch_sec,"challenge_token":chal_tk,"session_id":str(article_id)})
                double_ticket = str(safe_data(comp).get("double_ticket") or "").strip()
                if double_ticket:
                    dr = self.api_request("POST", f"{BASE_URL}/api/article/{article_id}/double-reward", payload={"double_ticket":double_ticket})
                    if dr.get("status")==200:
                        doubled = safe_float(safe_data(dr).get("doubled_amount"))
                        beans += doubled
                        self.log(f"✅文章{article_id}双倍奖励 +{doubled:.0f}金豆")
        return True,beans,""

    def task_article(self, need_cnt):
        if need_cnt <=0:
            return "已完成"
        list_resp = self.api_request("GET", ARTICLE_LIST_PAGE_URL, query={"page":1,"limit":10})
        if list_resp.get("status")!=200:
            return f"文章列表失败:{list_resp.get('msg') or ''}"
        articles = safe_data(list_resp).get("list") or []
        candidates = [a for a in articles if isinstance(a,dict) and not a.get("read_today")]
        if not candidates:
            return "今日文章均已读完"
        done =0
        total =0.0
        for art in candidates[:need_cnt]:
            ok,beans,err = self.run_one_article(safe_int(art.get("id")))
            if ok:
                done +=1
                total += beans
            else:
                self.log(f"⚠️文章{art.get('id')} {err}")
            time.sleep(random.uniform(2,4))
        return f"完成 {done}/{need_cnt} 篇，+{total:.0f} 金豆"

    def task_post(self):
        content = random.choice(POST_CONTENT_POOL)
        resp = self.api_request("POST", SOCIAL_POSTS_URL, payload={"scene":"plaza","content":content,"media_type":0})
        if resp.get("status")==200:
            rd = safe_data(resp).get("golden_bean_reward") or {}
            beans = safe_float(rd.get("beans"))
            suffix = f" +{beans:.0f} 金豆" if beans>0 else ""
            return f"发帖成功{suffix}"
        return f"发帖失败:{resp.get('msg') or json_preview(resp,200)}"

    def task_chat(self):
        cid = None
        for scene in ("treehouse","plaza","offline_store"):
            conv = self.api_request("GET", SOCIAL_CONVERSATIONS_URL, query={"scene":scene,"page":1})
            if conv.get("status")!=200:
                continue
            cd = safe_data(conv)
            items = cd.get("list") if isinstance(cd,dict) else cd
            if not isinstance(items,list):
                items = []
            for item in items:
                if isinstance(item,dict) and item.get("id"):
                    cid = item.get("id")
                    break
            if cid:
                break
        if not cid:
            return "无会话，跳过（需先有好友/匹配）"
        payload = {
            "conversation_id":cid,
            "client_msg_id":f"cm_{int(time.time()*1000)}_{random.randint(1,9999)}",
            "msg_type":"text",
            "content":"你好呀，日常打卡~"
        }
        resp = self.api_request("POST", SOCIAL_MESSAGES_URL, payload=payload)
        if resp.get("status")==200:
            return "聊天消息发送成功"
        return f"聊天失败:{resp.get('msg') or json_preview(resp,200)}"

    def task_full_reward(self):
        status = self.api_request("GET", DAILY_TASK_STATUS_URL)
        if status.get("status")!=200:
            return f"任务状态失败:{status.get('msg') or ''}", {}
        sd = safe_data(status)
        if sd.get("full_reward_claimed"):
            return "全勤奖今日已领取", sd
        if not sd.get("can_claim_full_reward"):
            return f"任务 {safe_int(sd.get('completed_count',0))}/{safe_int(sd.get('total_count',0))}，全勤奖待达成", sd
        payload = {"date":str(sd.get("date") or ""),"full_reward_ticket":str(sd.get("full_reward_ticket") or "")}
        resp = self.api_request("POST", DAILY_TASK_FULL_REWARD_CLAIM_URL, payload=payload)
        if resp.get("status")==200:
            beans = safe_float(safe_data(resp).get("reward_beans"))
            return f"全勤奖领取成功 +{beans:.0f} 金豆", safe_data(resp)
        return f"全勤奖领取失败:{resp.get('msg') or json_preview(resp,200)}", sd

    def task_withdraw(self):
        status = self.api_request("GET", GOLDEN_BEAN_WITHDRAW_STATUS_URL)
        if status.get("status")!=200:
            return "-", f"提现状态失败:{status.get('msg') or ''}"
        sd = safe_data(status)
        balance = str(sd.get("golden_bean_balance") or "0")
        withdrawable = str(sd.get("withdrawable_yuan") or "0.00")
        if sd.get("withdrawn_today"):
            return balance, "今日已提现"
        if not sd.get("can_withdraw"):
            return balance, f"可提现 {withdrawable} 元，未达门槛 {sd.get('withdraw_min_yuan','0.10')} 元"
        ticket = str(sd.get("withdraw_ticket") or "").strip()
        if not ticket:
            return balance, "提现票据缺失"
        resp = self.api_request("POST", GOLDEN_BEAN_WITHDRAW_APPLY_URL, payload={"withdraw_ticket":ticket})
        rd = safe_data(resp)
        if resp.get("status")!=200:
            return balance, f"提现申请失败:{resp.get('msg') or json_preview(resp,200)}"
        st = str(rd.get("status") or "")
        if st == "manual_review":
            return balance, "提现申请已提交审核"
        if st == "success":
            return balance, f"提现成功 {withdrawable} 元"
        if rd.get("transfer"):
            return balance, f"提现发起（{withdrawable} 元），需在微信确认收款"
        return balance, f"提现状态: {st or json_preview(rd,200)}"

    def execute(self, query_only=False):
        self.log("---开始账号处理---")
        self.proxies,self.proxy_ip = get_valid_proxy(self.proxy_api,self.proxy_type,self.name)
        if self.proxies:
            self.log(f"🌐使用代理，出口ip:{self.proxy_ip}")
        time.sleep(random.randint(2,5))
        if not self.login():
            self.log("❌账号登录失败，跳过")
            return {"success":False,"signMsg":"-","adMsg":"-","articleMsg":"-","postMsg":"-","chatMsg":"-","fullRewardMsg":"-","balance":"-","withdrawMsg":"-","error":"登录失败"}
        res = {"success":True,"signMsg":"","adMsg":"","articleMsg":"","postMsg":"","chatMsg":"","fullRewardMsg":"","balance":"","withdrawMsg":"","error":""}
        res["signMsg"] = self.task_sign()
        self.log(f"📝签到:{res['signMsg']}")
        task_status = self.api_request("GET", DAILY_TASK_STATUS_URL)
        tasks = safe_data(task_status).get("tasks") or []
        task_map = {t.get("key"):t for t in tasks if isinstance(t,dict)}
        watch_task = task_map.get("watch_ad") or {}
        if watch_task.get("completed"):
            res["adMsg"] = f"已完成（{safe_int(watch_task.get('current',0))}/{safe_int(watch_task.get('target',20))}）"
        else:
            res["adMsg"] = self.task_ad()
        self.log(f"📺广告:{res['adMsg']}")
        art_task = task_map.get("health_article") or {}
        art_need = max(0, safe_int(art_task.get("target",3)) - safe_int(art_task.get("current",0)))
        if art_task.get("completed") or art_need <=0:
            res["articleMsg"] = f"已完成（{safe_int(art_task.get('current',0))}/{safe_int(art_task.get('target',3))}）"
        else:
            res["articleMsg"] = self.task_article(art_need)
        self.log(f"📖文章:{res['articleMsg']}")
        post_task = task_map.get("publish_post") or {}
        if post_task.get("completed"):
            res["postMsg"] = "今日已发帖"
        else:
            res["postMsg"] = self.task_post()
        self.log(f"✍️发帖:{res['postMsg']}")
        chat_task = task_map.get("friend_chat") or {}
        if chat_task.get("completed"):
            res["chatMsg"] = "今日已互动"
        else:
            res["chatMsg"] = self.task_chat()
        self.log(f"💬聊天:{res['chatMsg']}")
        res["fullRewardMsg"],_ = self.task_full_reward()
        self.log(f"🎁全勤:{res['fullRewardMsg']}")
        if query_only:
            res["balance"] = "【查询模式】跳过余额提现"
            res["withdrawMsg"] = "【查询模式】跳过余额提现"
            self.log("📋查询模式结束")
            return res
        res["balance"], res["withdrawMsg"] = self.task_withdraw()
        self.log(f"💰余额:{res['balance']}金豆")
        self.log(f"💸提现:{res['withdrawMsg']}")
        return res

# =====================呆呆中间件SDK 青龙/呆呆OpenAPI部分=====================
import middleware
senderID = middleware.getSenderID()
sender = middleware.Sender(senderID)
userid = sender.getUserID()
imtype = sender.getImtype()

def get_config():
    qlname = middleware.bucketGet(BUCKET, 's_sld_qlname') or ''
    ddname = middleware.bucketGet(BUCKET, 's_sld_ddname') or ''
    osname = middleware.bucketGet(BUCKET, 's_sld_osname') or 'sldAccount'
    proxy_g = middleware.bucketGet(BUCKET, 's_sld_proxy_global') or ''
    return qlname, ddname, osname, proxy_g

s_sld_qlname, s_sld_ddname, s_sld_osname, s_sld_proxy_global = get_config()

QLurl = ""
qltoken = ""
PANEL_KIND = "ql"
PANEL_BASE = ""

def _resp_ok(rj):
    if not isinstance(rj,dict):
        return False
    if 'code' in rj:
        return str(rj.get('code')) in ('200','201','0','0000')
    if 'success' in rj:
        return rj.get('success') is not False
    return True

def _env_id(env):
    return env.get('id') if env.get('id') is not None else env.get('ID')

def DDtoken(host, app_key, app_secret):
    try:
        url = host.rstrip('/') + '/api/open-api/token'
        resp = requests.post(url, json={"app_key":app_key,"app_secret":app_secret}, headers={"Content-Type":"application/json"}, timeout=20, proxies={"http":None,"https":None})
        if resp.status_code!=200:
            sender.reply(f"""
=====请求失败=====
❌呆呆面板认证请求失败
状态码:{resp.status_code}
""")
            exit(0)
        res = resp.json()
        access_token = (res.get("data") or {}).get("access_token")
        if not access_token:
            sender.reply("❌获取呆呆token失败，检查app_key/app_secret")
            exit(0)
        return access_token
    except Exception:
        sender.reply("❌连接呆呆面板网络异常")
        exit(0)

def QLtoken(QLurl, ClientID, ClientSecret):
    try:
        url = f'{QLurl}/open/auth/token?client_id={ClientID}&client_secret={ClientSecret}'
        resp = requests.get(url, proxies={"http":None,"https":None}, timeout=20)
        if resp.status_code!=200:
            sender.reply(f"❌青龙请求失败，状态码{resp.status_code}")
            exit(0)
        res = resp.json()
        token = (res.get("data") or {}).get("token")
        if not token:
            sender.reply("❌获取青龙token失败，检查clientId/secret")
            exit(0)
        return token
    except Exception:
        sender.reply("❌连接青龙面板网络异常")
        exit(0)

def seekql():
    global QLurl,qltoken,PANEL_KIND,PANEL_BASE
    if len(s_sld_ddname)>0:
        arr = s_sld_ddname.split('丨')
        if len(arr)!=3:
            sender.reply("❌呆呆配置格式错误，Host丨app_key丨app_secret")
            exit(0)
        QLurl,ak,sk = [x.strip() for x in arr]
        if not QLurl.startswith(("http://","https://")):
            sender.reply("❌呆呆地址必须http/https开头")
            exit(0)
        qltoken = DDtoken(QLurl,ak,sk)
        PANEL_KIND = "dd"
        PANEL_BASE = QLurl + "/api"
        return QLurl,qltoken
    if len(s_sld_qlname)==0:
        sender.reply("❌未配置青龙或呆呆面板参数")
        exit(0)
    arr = s_sld_qlname.split('丨')
    if len(arr)!=3:
        sender.reply("❌青龙配置格式错误，Host丨ClientID丨ClientSecret")
        exit(0)
    QLurl,cid,csec = [x.strip() for x in arr]
    if not QLurl.startswith(("http://","https://")):
        sender.reply("❌青龙地址必须http/https开头")
        exit(0)
    qltoken = QLtoken(QLurl,cid,csec)
    PANEL_KIND = "ql"
    PANEL_BASE = QLurl + "/open"
    return QLurl,qltoken

def delenvs(env_id):
    if env_id is None or not QLurl or not qltoken:
        return
    headers = {"Authorization":f"Bearer {qltoken}","accept":"application/json","Content-Type":"application/json"}
    if PANEL_KIND == "dd":
        requests.delete(f"{PANEL_BASE}/envs/{env_id}", headers=headers, proxies={"http":None,"https":None})
    else:
        requests.delete(f"{PANEL_BASE}/envs", headers=headers, json=[env_id], proxies={"http":None,"https":None})

def allenvs(osname, mark):
    if not QLurl or not qltoken:
        return None
    headers = {"Authorization":f"Bearer {qltoken}","accept":"application/json"}
    resp = requests.get(f"{PANEL_BASE}/envs", headers=headers, proxies={"http":None,"https":None}, timeout=20)
    res = resp.json()
    if not _resp_ok(res):
        sender.reply("❌获取面板变量失败")
        exit(0)
    env_list = res.get("data") or []
    for env in env_list:
        if env.get("name")==osname and mark in str(env.get("remarks","")):
            return _env_id(env)
    return None

def QLupdate(osname, value, remark_mark, eid, uid):
    headers = {"Authorization":f"Bearer {qltoken}","accept":"application/json","Content-Type":"application/json"}
    payload = {
        "name":osname,
        "value":value,
        "remarks":f"商联道:{remark_mark}|user:{uid}|呆呆插件"
    }
    if PANEL_KIND == "dd":
        r = requests.put(f"{PANEL_BASE}/envs/{eid}", json=payload, headers=headers, proxies={"http":None,"https":None})
    else:
        payload["id"] = eid
        r = requests.put(f"{PANEL_BASE}/envs", data=json.dumps(payload), headers=headers, proxies={"http":None,"https":None})
    if r.status_code not in (200,201):
        sender.reply("❌更新环境变量失败")
        exit(0)

def QLzt(osname, value, remark_mark, uid):
    headers = {"Authorization":f"Bearer {qltoken}","accept":"application/json","Content-Type":"application/json"}
    payload = {
        "name":osname,
        "value":value,
        "remarks":f"商联道:{remark_mark}|user:{uid}|呆呆插件"
    }
    send_body = payload if PANEL_KIND=="dd" else [payload]
    r = requests.post(f"{PANEL_BASE}/envs", json=send_body, headers=headers, proxies={"http":None,"https":None})
    if r.status_code not in (200,201):
        sender.reply(f"❌新增变量失败，状态{r.status_code}")
        exit(0)
    res = r.json()
    if not _resp_ok(res):
        sender.reply(f"❌面板返回错误:{res}")
        exit(0)

def Addenvs(osname, value, remark_mark, uid):
    if not QLurl or not qltoken:
        return
    eid = allenvs(osname, remark_mark)
    if eid is None:
        QLzt(osname, value, remark_mark, uid)
    else:
        QLupdate(osname, value, remark_mark, eid, uid)

# =====================账号存储工具=====================
def load_accounts():
    raw = middleware.bucketGet(BUCKET_USER, key=userid) or "[]"
    try:
        arr = json.loads(raw)
        if not isinstance(arr,list):
            arr = []
    except Exception:
        arr = []
    return arr

def save_accounts(acc_list):
    middleware.bucketSet(BUCKET_USER, userid, json.dumps(acc_list, ensure_ascii=False))

def build_env_value(accs):
    return "&".join(f"{a['name']}#{a['yyb_server']}#{a['pushplus_token']}#{a['proxy_api']}#{a['proxy_type']}" for a in accs)

def sync_to_panel(accs):
    if not (s_sld_qlname or s_sld_ddname):
        return False,"未配置面板，仅本地保存"
    if not accs:
        try:
            QLurl,qltoken = seekql()
            eid = allenvs(s_sld_osname, userid)
            if eid is not None:
                delenvs(eid)
        except Exception:
            pass
        return True,"已清空面板变量"
    try:
        QLurl,qltoken = seekql()
        val = build_env_value(accs)
        Addenvs(s_sld_osname, val, userid, userid)
        return True,"同步成功"
    except Exception as e:
        return False,f"同步异常:{str(e)}"

# =====================交互指令函数=====================
def sld_login():
    sender.reply("""
=====商联道登录导入账号=====
粘贴账号，每行一个
格式：备注#YYB_SERVER#PLUSPLUS_TOKEN#PROXY_API#PROXY_TYPE
示例：小号#http://xxx@ref##http://xxx#http
空字段保留##
支持多行批量；回复q退出
""")
    text = sender.listen(300000)
    if not text or text.strip().lower()=="q":
        sender.reply("✅退出导入")
        return
    accs = load_accounts()
    add=0
    skip=0
    for line in text.replace("&","\n").splitlines():
        line = line.strip()
        if not line:
            continue
        sp = line.split("#",4)
        if len(sp)!=5:
            skip+=1
            continue
        name,yyb_s,pp,p_api,p_t = [x.strip() for x in sp]
        accs = [x for x in accs if x.get("yyb_server")!=yyb_s]
        accs.append({
            "name":name,"yyb_server":yyb_s,"pushplus_token":pp,
            "proxy_api":p_api,"proxy_type":p_t or "http"
        })
        add+=1
    save_accounts(accs)
    ok,msg = sync_to_panel(accs)
    sender.reply(f"""
✅新增/更新:{add}个
⏭️格式错误跳过:{skip}个
📦当前账号总数:{len(accs)}
🔄面板同步:{msg}
发送「商联道运行」执行任务
发送「商联道查询」仅查询状态
""")

def _run_all(query_only):
    accs = load_accounts()
    if not accs:
        return "❌暂无账号，请先发送「商联道登录」导入账号",[]
    summary_lines = []
    notify_content = f"🏮商联道任务 {'查询' if query_only else '执行'}结果\n时间:{_now()}\n------\n"
    all_push_token = set()
    for idx,acc in enumerate(accs,1):
        cfg = f"{acc['name']}#{acc['yyb_server']}#{acc['pushplus_token']}#{acc['proxy_api']}#{acc['proxy_type']}"
        u = SldUser(idx, cfg)
        print(f"\n{'='*50}\n账号[{idx}/{len(accs)}]{u.name}\n{'='*50}")
        res = u.execute(query_only=query_only)
        if acc.get("pushplus_token"):
            all_push_token.add(acc["pushplus_token"])
        icon = "✅" if res["success"] else "❌"
        line = f"{icon}{mask_str(u.name)} |签到:{res['signMsg']} |广告:{res['adMsg']} |文章:{res['articleMsg']} |发帖:{res['postMsg']} |聊天:{res['chatMsg']} |全勤:{res['fullRewardMsg']} |余额:{res['balance']} |提现:{res['withdrawMsg']}"
        summary_lines.append(line)
        notify_content += f"\n【账号{idx}】{u.name}\n签到:{res['signMsg']}\n广告:{res['adMsg']}\n文章:{res['articleMsg']}\n发帖:{res['postMsg']}\n聊天:{res['chatMsg']}\n全勤:{res['fullRewardMsg']}\n余额:{res['balance']}\n提现:{res['withdrawMsg']}\n结果:{'成功' if res['success'] else '失败'}\n"
        if idx < len(accs):
            time.sleep(2)
    out_text = ("【商联道查询】" if query_only else "【商联道运行】") + f"共{len(accs)}个账号\n" + "\n".join(summary_lines)
    for pt in all_push_token:
        send_pushplus(pt,"🏮商联道任务通知", notify_content)
    return out_text, list(all_push_token)

def sld_query():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先商联道登录导入")
        return
    sender.reply("🔎正在查询全部账号状态...")
    out,_ = _run_all(query_only=True)
    sender.reply(out)

def sld_run():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先商联道登录导入")
        return
    sender.reply("🚀开始执行商联道签到+全部任务+提现...")
    out,_ = _run_all(query_only=False)
    sender.reply(out)

def sld_manage():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号")
        return
    buf = ["====商联道账号管理====",f"共{len(accs)}个账号"]
    for i,a in enumerate(accs,1):
        buf.append(f"[{i}] {mask_str(a.get('name'))} |{mask_str(a.get('yyb_server'),4,2)}")
    buf.append("回复数字删除对应账号，all清空全部，q退出")
    sender.reply("\n".join(buf))
    sel = sender.listen(60000)
    if not sel:
        sender.reply("❌输入超时")
        return
    sel = sel.strip().lower()
    if sel=="q":
        sender.reply("✅退出管理")
        return
    if sel=="all":
        save_accounts([])
        ok,msg = sync_to_panel([])
        sender.reply(f"✅全部账号已清空\n🔄面板同步:{msg}")
        return
    try:
        n = int(sel)
        if not 1<=n<=len(accs):
            sender.reply("❌序号超出范围")
            return
        popitem = accs.pop(n-1)
        save_accounts(accs)
        ok,msg = sync_to_panel(accs)
        sender.reply(f"✅已删除{mask_str(popitem['name'])}\n🔄面板同步:{msg}")
    except ValueError:
        sender.reply("❌输入无效")

def sld_clean():
    accs = load_accounts()
    if not accs:
        sender.reply("❌没有账号可清理")
        return
    sender.reply(f"⚠️确认清空全部{len(accs)}个账号？y/n")
    c = sender.listen(30000)
    if not c or c.strip().lower() not in ("y","yes","是"):
        sender.reply("✅已取消清理")
        return
    save_accounts([])
    ok,msg = sync_to_panel([])
    sender.reply(f"✅全部账号已清空\n🔄面板同步:{msg}")

def sld_update():
    accs = load_accounts()
    ok,msg = sync_to_panel(accs)
    if accs:
        sender.reply(f"✅本地{len(accs)}个账号同步面板：{msg}\n面板定时任务触发「商联道运行」执行每日任务")
    else:
        sender.reply(f"⚠️本地无账号 {msg}")

def sld_check():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先导入账号")
        return
    sender.reply("🔎检测账号配置有效性（仅做登录尝试）")
    lines = []
    for idx,a in enumerate(accs,1):
        cfg = f"{a['name']}#{a['yyb_server']}#{a['pushplus_token']}#{a['proxy_api']}#{a['proxy_type']}"
        u = SldUser(idx, cfg)
        ok = u.login()
        lines.append(f"•{mask_str(u.name)} {'✅配置可登录' if ok else '❌登录失败'}")
    sender.reply("====商联道账号检测====\n"+"\n".join(lines))

# =====================指令路由&入口=====================
def handle_command(msg):
    msg = str(msg or "").strip()
    if "登录" in msg or "登陆" in msg:
        sld_login()
    elif "运行" in msg:
        sld_run()
    elif "查询" in msg:
        sld_query()
    elif "管理" in msg:
        sld_manage()
    elif "清理" in msg:
        sld_clean()
    elif "更新" in msg:
        sld_update()
    elif "检测" in msg:
        sld_check()
    else:
        sender.setContinue()

def main():
    try:
        text = sender.getMessage().strip()
        handle_command(text)
    except Exception as e:
        sender.reply(f"❌插件运行异常:{str(e)}")

if __name__ == "__main__":
    main()
