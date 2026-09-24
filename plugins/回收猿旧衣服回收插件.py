# [title: 回收猿旧衣服回收]
# [language: python]
# [rule: ^(回收猿)(登录|查询|运行|管理|清理|更新|检测)((?:\s+\S+)*)$]
# [disable:false]
# [open_source: false]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public:true]
# [version: 1.0.0]
# [price: 0]
# [author: 呆呆插件改造版]
# [service: ]
# [description: ❶♻️回收猿旧衣服回收小程序，支持多账号签到、福利任务、余额查询、自动提现<br>❷对接呆呆面板与青龙面板双平台；账号格式：备注#YYB_SERVER#YYB_API_KEY#PLUSPLUS_TOKEN#PROXY_API#PROXY_TYPE#HSY_CHANNEL_ID#HSY_WITHDRAW_MIN<br>❸指令：『回收猿登录』粘贴导入账号、『回收猿运行』执行全部任务、『回收猿查询』仅查询账号状态、『回收猿管理』账号管理、『回收猿清理』清空账号、『回收猿更新』同步面板变量、『回收猿检测』校验账号配置<br>❹依赖YYB服务获取wx.code完成登录，支持代理、PushPlus推送]
# [param: {"required":false,"key":"s_hsy.s_hsy_qlname","bool":false,"placeholder":"Host丨ClientID丨ClientSecret","name":"对接青龙","desc":"各参数之间用中文符丨分割，例如: http://127.0.0.1:5700/丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_hsy.s_hsy_ddname","bool":false,"placeholder":"Host丨app_key丨app_secret","name":"对接呆呆面板","desc":"留空则使用青龙面板。各参数之间用中文符丨分割，例如: http://127.0.0.1:5700丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_hsy.s_hsy_osname","bool":false,"placeholder":"hsyAccount","name":"环境变量名","desc":"同步到青龙/呆呆的变量名称，默认 hsyAccount"}]
# [param: {"required":false,"key":"s_hsy.s_hsy_proxy_global","bool":false,"placeholder":"http://127.0.0.1:7890","name":"全局代理地址","desc":"可选，http/socks5，优先使用账号内独立代理配置"}]
# -*- coding: utf-8 -*-
"""
呆呆插件版｜回收猿旧衣服回收
原脚本功能完整移植，YYB鉴权、签到、任务、自动提现、pushplus推送
"""
import os
import re
import sys
import json
import time
import random
import hashlib
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
BUCKET = 's_hsy'
BUCKET_USER = 's_hsy_user'
APPID = "wxadd84841bd31a665"
APP_PLATFORM = "hsywx"
BASE_URL = "https://www.52bjy.com"
APPKEY = "1079fb245839e765"
SECRET = "UppwYkfBlk"
MERCHANT_ID = "2"
REQUEST_TIMEOUT = 30
PROXY_RETRY_TIMES = 3
PROXY_VALIDATE_URL = "http://httpbin.org/ip"
PROXY_FETCH_INTERVAL = 3
ENABLE_DIRECT_FALLBACK = True
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2541c37) XWEB/25364 "
    f"miniProgram/{APPID}"
)

# 兼容yyb_account_guard 不存在情况
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

def safe_int(value, default=0):
    try:
        return int(float(value or default))
    except Exception:
        return default

def safe_float(value, default=0.0):
    try:
        return float(value or default)
    except Exception:
        return default

def json_preview(data, limit=600):
    try:
        return json.dumps(data, ensure_ascii=False)[:limit]
    except Exception:
        return str(data)[:limit]

def resp_ok(resp):
    return bool(resp.get("isSucess") or resp.get("is_success"))

def safe_data(resp):
    d = resp.get("data")
    return d if isinstance(d, dict) else {}

def direct_session():
    s = requests.Session()
    s.trust_env = False
    return s

# =====================签名、YYB、网络请求封装=====================
def parse_yyb_entry(raw):
    value = str(raw or "").strip()
    if "@" not in value:
        raise ValueError("YYB_SERVER格式应为 地址@账号ID或OpenID")
    endpoint, ref = value.split("@",1)
    endpoint = endpoint.strip().rstrip("/")
    ref = ref.strip()
    if not endpoint or not ref:
        raise ValueError("YYB_SERVER缺少地址或账号标识")
    if not endpoint.startswith(("http://","https://")):
        endpoint = f"http://{endpoint}"
    return endpoint, ref

def get_code(yyb_server, yyb_api_key):
    try:
        endpoint, ref = parse_yyb_entry(yyb_server)
        url = f"{endpoint}/wxapp/getCode"
        headers = {"X-API-Key": yyb_api_key} if yyb_api_key else {}
        resp = direct_session().post(url, json={"ref":ref,"app_id":APPID}, headers=headers, timeout=20)
        data = resp.json()
        result = data.get("data") or {}
        result = result.get("result") if isinstance(result,dict) else {}
        code = result.get("code")
        if data.get("code")!=0 or not code:
            return None, f"获取code失败:{json_preview(data)}"
        return str(code), None
    except Exception as e:
        return None, f"获取code异常:{str(e)}"

def js_encode(value):
    encoded = quote(str(value), safe="-_.~")
    encoded = encoded.replace("!","%21").replace("'","%27").replace("(","%28").replace(")","%29").replace("*","%2A")
    return encoded

def hsy_query_value(value):
    text = str(value)
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return js_encode(text)
    return text

def hsy_sign(params):
    qs = "&".join(f"{k}={hsy_query_value(v)}" for k,v in sorted(params.items()))
    return hashlib.md5((qs+SECRET).encode("utf-8")).hexdigest()

def build_api_url(php, params):
    d = dict(params)
    d.pop("php",None)
    d.setdefault("appkey",APPKEY)
    q = "&".join(f"{k}={hsy_query_value(v)}" for k,v in sorted(d.items()))
    sign = hsy_sign(d)
    return f"{BASE_URL}/api/app/{php}.php?{q}&sign={sign}"

def common_headers(token=None):
    hd = {
        "User-Agent":USER_AGENT,
        "Accept":"*/*",
        "Content-Type":"application/json",
        "EnvConnection":"test",
        "Referer":f"https://servicewechat.com/{APPID}/134/page-frame.html",
        "Accept-Language":"zh-CN,zh;q=0.9"
    }
    if token:
        hd["auth"] = token
    return hd

def parse_json(resp):
    for enc in ("utf-8","gbk"):
        try:
            return json.loads(resp.content.decode(enc))
        except Exception:
            continue
    return {"code":-1,"message":f"JSON解析失败:{resp.text[:200]}"}

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

def send_pushplus(token, title, content):
    if not token:
        return
    try:
        requests.post("https://www.pushplus.plus/send",json={"token":token,"title":title,"content":content,"template":"txt"},timeout=10)
    except Exception:
        pass

# =====================账号业务类=====================
class HsyUser:
    def __init__(self, index, cfg_str):
        self.index = index
        self.name = ""
        self.yyb_server = ""
        self.yyb_api_key = ""
        self.pushplus_token = ""
        self.proxy_api = ""
        self.proxy_type = "http"
        self.hsy_channel_id = "wx1008"
        self.hsy_withdraw_min = 1.0
        self.logs = []
        self.token = None
        self.username = None
        self.cache_key = ""
        self._parse(cfg_str)
        self.proxies = None
        self.proxy_ip = ""

    def _parse(self, cfg_str):
        parts = cfg_str.split("#",7)
        if len(parts)!=8:
            self.name = cfg_str.strip()
            self.log(f"⚠️账号格式错误:{mask_str(cfg_str)}")
            return
        self.name,self.yyb_server,self.yyb_api_key,self.pushplus_token,self.proxy_api,self.proxy_type,self.hsy_channel_id,self.hsy_withdraw_min = [x.strip() for x in parts]
        self.cache_key = self.yyb_server
        self.hsy_withdraw_min = safe_float(self.hsy_withdraw_min,1.0)

    def log(self, msg):
        line = f"[{_now()}] 账号[{self.index}][{self.name}] {msg}"
        print(line)
        self.logs.append(line)

    def load_cache(self):
        raw = middleware.bucketGet(BUCKET, f"token_{self.cache_key}")
        if not raw:
            return None,None
        try:
            j = json.loads(raw)
            exp_ts = datetime.fromisoformat(j["expireTime"]).timestamp()*1000
            if time.time()*1000 < exp_ts - 3600*1000:
                return j["token"], j["username"]
        except Exception:
            pass
        return None,None

    def save_cache(self, token, username):
        exp = datetime.fromtimestamp(time.time()+7*24*3600).isoformat()
        d = {"token":token,"username":username,"expireTime":exp,"updateTime":_now()}
        middleware.bucketSet(BUCKET, f"token_{self.cache_key}", json.dumps(d,ensure_ascii=False))

    def login(self):
        tk,un = self.load_cache()
        if tk and un:
            self.log("✅读取本地缓存token")
            self.token,self.username = tk,un
            #简单校验
            try:
                url = build_api_url("user",{"action":"userinfo","app":APP_PLATFORM,"auth":tk,"merchant_id":MERCHANT_ID,"username":un})
                rj = parse_json(request_with_proxy("GET",url,proxies=self.proxies,headers=common_headers(tk)))
                if resp_ok(rj):
                    self.log("✅缓存token校验通过")
                    return True
            except Exception:
                self.log("⚠️缓存token失效，重新获取code")
        code,err = get_code(self.yyb_server, self.yyb_api_key)
        if err or not code:
            self.log(f"❌{err}")
            return False
        login_url = (
            f"{BASE_URL}/api/app/hsy.php?action=auth&appkey={APPKEY}&channel={self.hsy_channel_id}"
            f"&code={code}&inviter=&iv=&merchant_id={MERCHANT_ID}&login_source=scan&method=weixin_bind&version=2"
        )
        resp = request_with_proxy("POST",login_url,proxies=self.proxies,
            data={"encryptedData":""},
            headers={"User-Agent":USER_AGENT,"Content-Type":"application/x-www-form-urlencoded","EnvConnection":"test","Referer":f"https://servicewechat.com/{APPID}/134/page-frame.html"})
        j = parse_json(resp)
        inner = safe_data(j)
        tk = inner.get("jiufy_auth") or inner.get("token") or inner.get("accessToken")
        un = inner.get("username","")
        if not tk:
            self.log(f"❌登录换token失败:{json_preview(j)}")
            return False
        self.token,self.username = str(tk),str(un)
        self.save_cache(self.token,self.username)
        self.log("✅登录成功，已缓存token")
        return True

    def api_get(self, php, params):
        url = build_api_url(php,params)
        resp = request_with_proxy("GET",url,proxies=self.proxies,headers=common_headers(self.token))
        return parse_json(resp)

    def fetch_task_list(self):
        resp = self.api_get("promotion",{"action":"tasklist","app":APP_PLATFORM,"merchant_id":MERCHANT_ID,"type":"welfare","username":self.username})
        data = resp.get("data") or []
        return [x for x in data if isinstance(x,dict)]

    def summarize_task(self,tasks):
        if not tasks:
            return "无福利任务"
        done = sum(1 for x in tasks if safe_int(x.get("is_done"))==1)
        pend = [str(x.get("title") or x.get("type")) for x in tasks if safe_int(x.get("is_done"))!=1]
        txt = f"{done}/{len(tasks)}已完成"
        if pend:
            txt += "，待完成："+"、".join(pend[:4])+("..." if len(pend)>4 else "")
        return txt

    def execute(self, query_only=False):
        self.log("---开始账号处理---")
        self.proxies,self.proxy_ip = get_valid_proxy(self.proxy_api,self.proxy_type,self.name)
        if self.proxies:
            self.log(f"🌐使用代理，出口ip:{self.proxy_ip}")
        time.sleep(random.randint(2,5))
        if not self.login():
            self.log("❌账号登录失败，跳过")
            return {"success":False,"signMsg":"-","taskMsg":"-","balance":"-","withdrawMsg":"-","error":"登录失败"}
        res = {"success":True,"signMsg":"","taskMsg":"","balance":"","withdrawMsg":"","error":""}
        #签到
        sign_info = self.api_get("hsy",{"action":"user","app":APP_PLATFORM,"merchant_id":MERCHANT_ID,"method":"getsigninfo","username":self.username,"version":"4"})
        if resp_ok(sign_info):
            sd = safe_data(sign_info)
            has_sign = safe_int(sd.get("hassign"))
            turn = safe_int(sd.get("thisturn"))
            if has_sign==1:
                res["signMsg"] = f"今日已签到，连续{turn}天"
                self.log(f"✅{res['signMsg']}")
            else:
                sig_resp = self.api_get("hsy",{"action":"user","app":APP_PLATFORM,"merchant_id":MERCHANT_ID,"method":"qiandao","username":self.username,"version":"4"})
                if resp_ok(sig_resp):
                    aw = safe_data(sig_resp).get("qiandao_award","?")
                    res["signMsg"] = f"签到成功，连续{turn+1}天，奖励+{aw}"
                    self.log(f"✅{res['signMsg']}")
                else:
                    res["signMsg"] = sig_resp.get("message","签到请求失败")
                    self.log(f"⚠️{res['signMsg']}")
        else:
            res["signMsg"] = sign_info.get("message","查询签到状态失败")
            self.log(f"⚠️{res['signMsg']}")
        #任务
        tasks = self.fetch_task_list()
        res["taskMsg"] = self.summarize_task(tasks)
        self.log(f"🧧{res['taskMsg']}")
        if query_only:
            res["balance"]="【查询模式】跳过余额提现"
            res["withdrawMsg"]="【查询模式】跳过余额提现"
            self.log("📋查询模式结束")
            return res
        #余额
        center_resp = self.api_get("hsy",{"action":"user","merchant_id":MERCHANT_ID,"method":"center","username":self.username})
        if not resp_ok(center_resp):
            res["balance"] = center_resp.get("message","获取余额失败")
            self.log(f"⚠️{res['balance']}")
            return res
        cd = safe_data(center_resp)
        award = safe_float(cd.get("award"))
        signday = safe_int(cd.get("day"))
        res["balance"] = f"奖励金{award:.2f}元，累计签到{signday}天"
        self.log(f"💰{res['balance']}")
        #提现逻辑
        award_resp = self.api_get("envcash",{"action":"awardlist","genre":"0","merchant_id":MERCHANT_ID,"type":"award","username":self.username})
        if not resp_ok(award_resp):
            res["withdrawMsg"] = award_resp.get("message","提现信息查询失败")
            self.log(f"⚠️{res['withdrawMsg']}")
            return res
        ai = safe_data(award_resp)
        award_amt = safe_float(ai.get("award_amount"))
        freeze_amt = safe_float(ai.get("freeze_amount"))
        cash_min = max(safe_float(ai.get("award_cash")), self.hsy_withdraw_min)
        cash_most = safe_float(ai.get("award_cash_most")) or award_amt
        remain_cnt = safe_int(ai.get("user_remain_counter"))
        cash_block = safe_int(ai.get("cash_block"))
        withdrawable = round(award_amt - freeze_amt,2)
        if cash_block ==1:
            res["withdrawMsg"] = "账号提现被限制"
            self.log(f"⚠️{res['withdrawMsg']}")
            return res
        if remain_cnt <=0:
            res["withdrawMsg"] = "本周提现次数用尽"
            self.log(f"⚠️{res['withdrawMsg']}")
            return res
        if withdrawable < cash_min:
            res["withdrawMsg"] = f"可提现{withdrawable:.2f}元，未达最低{cash_min:g}元"
            self.log(f"⚠️{res['withdrawMsg']}")
            return res
        amount = min(withdrawable, cash_most)
        self.log(f"💸发起提现{amount:.2f}元，剩余次数{remain_cnt}")
        wd_resp = self.api_get("envcash",{"action":"add","amount":f"{amount:.2f}","app":"wx","merchant_id":MERCHANT_ID,"type":"award","username":self.username,"version":"2"})
        if resp_ok(wd_resp):
            pkg = safe_data(wd_resp).get("package_info")
            res["withdrawMsg"] = f"提现{amount:.2f}元已提交"+("，微信确认收款或24h自动到账" if pkg else "，预计24h到账")
        else:
            res["withdrawMsg"] = wd_resp.get("message","提现调用失败")
        self.log(f"💸{res['withdrawMsg']}")
        return res

# =====================呆呆中间件SDK 青龙/呆呆OpenAPI部分=====================
import middleware
senderID = middleware.getSenderID()
sender = middleware.Sender(senderID)
userid = sender.getUserID()
imtype = sender.getImtype()

def get_config():
    qlname = middleware.bucketGet(BUCKET, 's_hsy_qlname') or ''
    ddname = middleware.bucketGet(BUCKET, 's_hsy_ddname') or ''
    osname = middleware.bucketGet(BUCKET, 's_hsy_osname') or 'hsyAccount'
    proxy_g = middleware.bucketGet(BUCKET, 's_hsy_proxy_global') or ''
    return qlname, ddname, osname, proxy_g

s_hsy_qlname, s_hsy_ddname, s_hsy_osname, s_hsy_proxy_global = get_config()

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
    if len(s_hsy_ddname)>0:
        arr = s_hsy_ddname.split('丨')
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
    if len(s_hsy_qlname)==0:
        sender.reply("❌未配置青龙或呆呆面板参数")
        exit(0)
    arr = s_hsy_qlname.split('丨')
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
        "remarks":f"回收猿:{remark_mark}|user:{uid}|呆呆插件"
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
        "remarks":f"回收猿:{remark_mark}|user:{uid}|呆呆插件"
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
    return "&".join(f"{a['name']}#{a['yyb_server']}#{a['yyb_api_key']}#{a['pushplus_token']}#{a['proxy_api']}#{a['proxy_type']}#{a['hsy_channel_id']}#{a['hsy_withdraw_min']}" for a in accs)

def sync_to_panel(accs):
    if not (s_hsy_qlname or s_hsy_ddname):
        return False,"未配置面板，仅本地保存"
    if not accs:
        try:
            QLurl,qltoken = seekql()
            eid = allenvs(s_hsy_osname, userid)
            if eid is not None:
                delenvs(eid)
        except Exception:
            pass
        return True,"已清空面板变量"
    try:
        QLurl,qltoken = seekql()
        val = build_env_value(accs)
        Addenvs(s_hsy_osname, val, userid, userid)
        return True,"同步成功"
    except Exception as e:
        return False,f"同步异常:{str(e)}"

# =====================交互指令函数=====================
def hsy_login():
    sender.reply("""
=====回收猿登录导入账号=====
粘贴账号，每行一个
格式：备注#YYB_SERVER#YYB_API_KEY#PLUSPLUS_TOKEN#PROXY_API#PROXY_TYPE#HSY_CHANNEL_ID#HSY_WITHDRAW_MIN
示例：小号#http://xxx@ref#apikey##http://xxx#http#wx1008#1
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
        sp = line.split("#",7)
        if len(sp)!=8:
            skip+=1
            continue
        name,yyb_s,yyb_k,pp,p_api,p_t,cid,wmin = [x.strip() for x in sp]
        #去重，依据yyb_server作为唯一key
        accs = [x for x in accs if x.get("yyb_server")!=yyb_s]
        accs.append({
            "name":name,"yyb_server":yyb_s,"yyb_api_key":yyb_k,
            "pushplus_token":pp,"proxy_api":p_api,"proxy_type":p_t or "http",
            "hsy_channel_id":cid or "wx1008","hsy_withdraw_min":wmin or "1"
        })
        add+=1
    save_accounts(accs)
    ok,msg = sync_to_panel(accs)
    sender.reply(f"""
✅新增/更新:{add}个
⏭️格式错误跳过:{skip}个
📦当前账号总数:{len(accs)}
🔄面板同步:{msg}
发送「回收猿运行」执行任务
发送「回收猿查询」仅查询状态
""")

def _run_all(query_only):
    accs = load_accounts()
    if not accs:
        return "❌暂无账号，请先发送「回收猿登录」导入账号",[]
    summary_lines = []
    notify_content = f"♻️回收猿任务 {'查询' if query_only else '执行'}结果\n时间:{_now()}\n------\n"
    all_push_token = set()
    for idx,acc in enumerate(accs,1):
        cfg = f"{acc['name']}#{acc['yyb_server']}#{acc['yyb_api_key']}#{acc['pushplus_token']}#{acc['proxy_api']}#{acc['proxy_type']}#{acc['hsy_channel_id']}#{acc['hsy_withdraw_min']}"
        u = HsyUser(idx, cfg)
        print(f"\n{'='*50}\n账号[{idx}/{len(accs)}]{u.name}\n{'='*50}")
        res = u.execute(query_only=query_only)
        if acc.get("pushplus_token"):
            all_push_token.add(acc["pushplus_token"])
        icon = "✅" if res["success"] else "❌"
        line = f"{icon}{mask_str(u.name)} |签到:{res['signMsg']} |任务:{res['taskMsg']} |余额:{res['balance']} |提现:{res['withdrawMsg']}"
        summary_lines.append(line)
        notify_content += f"\n【账号{idx}】{u.name}\n签到:{res['signMsg']}\n任务:{res['taskMsg']}\n余额:{res['balance']}\n提现:{res['withdrawMsg']}\n结果:{'成功' if res['success'] else '失败'}\n"
        if idx < len(accs):
            time.sleep(2)
    out_text = ("【回收猿查询】" if query_only else "【回收猿运行】") + f"共{len(accs)}个账号\n" + "\n".join(summary_lines)
    for pt in all_push_token:
        send_pushplus(pt,"♻️回收猿任务通知", notify_content)
    return out_text, list(all_push_token)

def hsy_query():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先回收猿登录导入")
        return
    sender.reply("🔎正在查询全部账号状态...")
    out,_ = _run_all(query_only=True)
    sender.reply(out)

def hsy_run():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先回收猿登录导入")
        return
    sender.reply("🚀开始执行回收猿签到+任务+提现...")
    out,_ = _run_all(query_only=False)
    sender.reply(out)

def hsy_manage():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号")
        return
    buf = ["====回收猿账号管理====",f"共{len(accs)}个账号"]
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

def hsy_clean():
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

def hsy_update():
    accs = load_accounts()
    ok,msg = sync_to_panel(accs)
    if accs:
        sender.reply(f"✅本地{len(accs)}个账号同步面板：{msg}\n面板定时任务触发「回收猿运行」执行每日任务")
    else:
        sender.reply(f"⚠️本地无账号 {msg}")

def hsy_check():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先导入账号")
        return
    sender.reply("🔎检测账号配置有效性（仅做登录尝试）")
    lines = []
    for idx,a in enumerate(accs,1):
        cfg = f"{a['name']}#{a['yyb_server']}#{a['yyb_api_key']}#{a['pushplus_token']}#{a['proxy_api']}#{a['proxy_type']}#{a['hsy_channel_id']}#{a['hsy_withdraw_min']}"
        u = HsyUser(idx, cfg)
        ok = u.login()
        lines.append(f"•{mask_str(u.name)} {'✅配置可登录' if ok else '❌登录失败'}")
    sender.reply("====回收猿账号检测====\n"+"\n".join(lines))

# =====================指令路由&入口=====================
def handle_command(msg):
    msg = str(msg or "").strip()
    if "登录" in msg or "登陆" in msg:
        hsy_login()
    elif "运行" in msg:
        hsy_run()
    elif "查询" in msg:
        hsy_query()
    elif "管理" in msg:
        hsy_manage()
    elif "清理" in msg:
        hsy_clean()
    elif "更新" in msg:
        hsy_update()
    elif "检测" in msg:
        hsy_check()
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
