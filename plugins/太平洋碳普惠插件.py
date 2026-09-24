# [title: 太平洋碳普惠]
# [language: python]
# [rule: ^(碳普惠)(登录|查询|运行|管理|清理|更新|检测)((?:\s+\S+)*)$]
# [disable:false]
# [open_source: false]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public:true]
# [version: 1.0.0]
# [price: 0]
# [author: 呆呆插件改造版]
# [service: ]
# [description: ❶🌱太平洋碳普惠小程序，YYB获取微信code，SM2加密通信；签到、关注公众号、点赞排行榜、看视频、生日积分、抽奖查询、收取待领取积分、积分查询<br>❷对接呆呆面板与青龙面板双平台；账号格式：备注#YYB_SERVER#PLUSPLUS_TOKEN#PROXY_API#PROXY_TYPE<br>❸指令：『碳普惠登录』粘贴导入账号、『碳普惠运行』执行全部任务、『碳普惠查询』仅查询账号状态、『碳普惠管理』账号管理、『碳普惠清理』清空账号、『碳普惠更新』同步面板变量、『碳普惠检测』校验账号配置<br>❹支持品赞代理、单账号独立pushplus推送，token密钥缓存，失效自动刷新，依赖gmssl库]
# [param: {"required":false,"key":"s_tph.s_tph_qlname","bool":false,"placeholder":"Host丨ClientID丨ClientSecret","name":"对接青龙","desc":"各参数之间用中文符丨分割，例如: http://127.0.0.1:5700/丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_tph.s_tph_ddname","bool":false,"placeholder":"Host丨app_key丨app_secret","name":"对接呆呆面板","desc":"留空则使用青龙面板。各参数之间用中文符丨分割，例如: http://127.0.0.1:5700丨abcdef丨abcdef"}]
# [param: {"required":false,"key":"s_tph.s_tph_osname","bool":false,"placeholder":"tphAccount","name":"环境变量名","desc":"同步到青龙/呆呆的变量名称，默认 tphAccount"}]
# [param: {"required":false,"key":"s_tph.s_tph_proxy_global","bool":false,"placeholder":"http://127.0.0.1:7890","name":"全局代理地址","desc":"可选，http/socks5，优先使用账号内独立代理配置"}]
# -*- coding: utf-8 -*-
"""
呆呆插件版｜太平洋碳普惠
完整移植原脚本业务：YYB获取code、SM2国密加解密、签到、关注、点赞、视频、生日、抽奖、收取积分、代理、pushplus推送
token、密钥缓存在插件bucket，失效自动刷新
依赖：gmssl
"""
import os
import re
import sys
import json
import time
import random
import traceback
import uuid
import string
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
BUCKET = 's_tph'
BUCKET_USER = 's_tph_user'
APPID = "wxc62da17526f8b4d0"
BASE_URL = "https://cfp.cpic.com.cn"
LOGIN_URL = f"{BASE_URL}/api/auth/register/userLogin"
TRACE_URL = f"{BASE_URL}/api/http/trace/getHttpTraceId"
SIGN_SAVE_URL = f"{BASE_URL}/api/saveSignLog"
SIGN_LOG_URL = f"{BASE_URL}/api/querySignLog"
SIGN_FLAG_URL = f"{BASE_URL}/api/signFlag"
ATTENTION_IS_URL = f"{BASE_URL}/api/auth/register/queryUserIsAttention"
ATTENTION_INTEGRAL_URL = f"{BASE_URL}/api/auth/register/queryAttentionIntegral"
TOP_POINTS_URL = f"{BASE_URL}/api/topDistributePoints"
VIDEO_SERIES_URL = f"{BASE_URL}/api/getVideoSeriesDataNew"
VIDEO_LIST_URL = f"{BASE_URL}/api/getVideoDataNew"
VIDEO_SAVE_URL = f"{BASE_URL}/api/saveVideoIntegralNew"
BIRTHDAY_URL = f"{BASE_URL}/api/getUserBirthDay"
BIRTHDAY_SAVE_URL = f"{BASE_URL}/api/saveUserBirthDayIntegral"
DRAW_NUM_URL = f"{BASE_URL}/api/active/prize/queryDrawNum"
PENDING_INTEGRAL_URL = f"{BASE_URL}/api/getTphPendingIntegralDetail"
COLLECT_INTEGRAL_URL = f"{BASE_URL}/api/updateTphIntegral"
FAIL_INTEGRAL_URL = f"{BASE_URL}/api/getAboutFailIntegralDetail"
TASK_LIST_URL = f"{BASE_URL}/api/carbon/scenario/search"
ACTIVE_CODE = "16298e9663dc4a8b"

PROXY_RETRY_TIMES = 3
PROXY_VALIDATE_URL = "http://httpbin.org/ip"
PROXY_FETCH_INTERVAL = 3
ENABLE_DIRECT_FALLBACK = True
REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 "
    "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
    "MiniProgramEnv/Windows WindowsWechat"
)
REFERER = f"https://servicewechat.com/{APPID}/156/page-frame.html"

try:
    from gmssl.sm2 import CryptSM2
except ImportError:
    CryptSM2 = None

try:
    from yyb_account_guard import filter_accounts, update_from_result
except ImportError:
    def filter_accounts(lst, app_id, log):
        return [i for i in lst if i.strip()]
    def update_from_result(server, result, app_id):
        pass

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

def is_hex(text):
    if not isinstance(text, str) or len(text) < 192 or len(text) % 2:
        return False
    try:
        int(text[:32], 16)
        int(text[-32:], 16)
    except ValueError:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in text[:64])

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

def sm2_encrypt(public_key, plain_text):
    public_key = public_key.strip()
    if public_key.startswith("04") and len(public_key) == 130:
        public_key = public_key[2:]
    crypt = CryptSM2(private_key="", public_key=public_key, mode=1)
    return crypt.encrypt(plain_text.encode("utf-8")).hex()

def sm2_decrypt(private_key, cipher_hex):
    try:
        private_key = private_key.strip()
        if len(private_key) > 64:
            private_key = private_key[-64:]
        crypt = CryptSM2(private_key=private_key, public_key="", mode=1)
        plain = crypt.decrypt(bytes.fromhex(cipher_hex))
        if plain is None:
            return None
        return plain.decode("utf-8")
    except Exception:
        return None

def gen_local_token():
    return uuid.uuid4().hex + "".join(random.choices(string.ascii_lowercase, k=6))

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

def common_headers(token = "", openid = "", trace_id = ""):
    hd = {
        "User-Agent": USER_AGENT,
        "xweb_xhr": "1",
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "*/*",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": REFERER,
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if trace_id:
        hd["httpTraceId"] = trace_id
    if openid:
        hd["openid"] = openid
    if token:
        hd["token"] = token
    return hd

# =====================账号业务类=====================
class TphUser:
    def __init__(self, index, cfg_str):
        self.index = index
        self.name = ""
        self.yyb_server = ""
        self.pushplus_token = ""
        self.proxy_api = ""
        self.proxy_type = "http"
        self.logs = []
        self.token = ""
        self.openid = ""
        self.unionid = ""
        self.user_code = ""
        self.branch_code = ""
        self.public_key = ""
        self.private_key = ""
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

    def get_trace_id(self):
        try:
            resp = request_with_proxy("POST", TRACE_URL, proxies=self.proxies, server=self.yyb_server,
                headers=common_headers(self.token, self.openid), json={"source":"tph"})
            j = resp.json()
            return (j.get("data") or {}).get("httpTraceId", "")
        except Exception:
            return ""

    def api_post(self, url, payload, need_encrypt=True):
        trace_id = self.get_trace_id()
        hd = common_headers(self.token, self.openid, trace_id)
        if need_encrypt:
            if not self.public_key:
                return {"code":-1,"msg":"缺少加密公钥"}
            body = {"param": sm2_encrypt(self.public_key, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))}
        else:
            body = payload
        resp = request_with_proxy("POST", url, headers=hd, json=body, proxies=self.proxies, server=self.yyb_server)
        try:
            result = resp.json()
        except Exception:
            return {"code":-1,"msg":f"JSON解析失败:{resp.text[:300]}"}
        data = result.get("data")
        if isinstance(data, str) and is_hex(data) and self.private_key:
            plain = sm2_decrypt(self.private_key, data)
            if plain is not None:
                try:
                    result["data"] = json.loads(plain)
                except Exception:
                    result["data"] = plain
        return result

    def login(self):
        if CryptSM2 is None:
            self.log("❌缺少gmssl依赖，无法执行SM2加密")
            return False
        cache_data = self.load_cache()
        if cache_data:
            self.token = cache_data["token"]
            self.openid = cache_data["openid"]
            self.unionid = cache_data["unionid"]
            self.user_code = cache_data["userCode"]
            self.branch_code = cache_data["branchCode"]
            self.public_key = cache_data["appFirstMake"]
            self.private_key = cache_data["rearEndUse"]
            self.log("✅读取缓存token")
            try:
                rj = self.api_post(PENDING_INTEGRAL_URL, {"userCode":self.user_code,"unionId":self.unionid})
                if rj.get("code")==200:
                    self.log("✅缓存token校验通过")
                    return True
            except Exception:
                self.log("⚠️缓存token失效，重新获取code")
        code,err = get_code(self.yyb_server)
        if err or not code:
            self.log(f"❌{err}")
            return False
        self.log("🔐 [登录] 使用 code 换 token")
        payload = {
            "wechatCode": code,
            "sourceType": "share_point",
            "shareType": "point",
            "shareUserUserCode": "",
            "shareUserUnionId": "",
        }
        resp = request_with_proxy("POST", LOGIN_URL, proxies=self.proxies, server=self.yyb_server,
            headers=common_headers(gen_local_token(), ""), json=payload)
        try:
            j = resp.json()
        except Exception:
            j = {"raw":resp.text[:800]}
        if j.get("code") != 200:
            self.log(f"❌登录失败:{json_preview(j)}")
            return False
        data = j.get("data") or {}
        self.public_key = data.get("appFirstMake", "")
        self.private_key = data.get("rearEndUse", "")
        if not self.private_key or not isinstance(data.get("response"), str):
            self.log(f"❌未返回密钥或加密响应:{json_preview(j)}")
            return False
        plain = sm2_decrypt(self.private_key, data["response"])
        if plain is None:
            self.log("❌登录响应解密失败")
            return False
        try:
            info = json.loads(plain)
        except Exception:
            self.log(f"❌解密结果非JSON:{plain[:200]}")
            return False
        self.token = info.get("token","")
        self.openid = info.get("openid","")
        self.unionid = info.get("unionid","")
        self.user_code = info.get("userCode","")
        self.branch_code = (info.get("thcUserInfo") or {}).get("branchCode","")
        if not self.token:
            self.log(f"❌未识别token字段:{json_preview(info)}")
            return False
        expire_time = datetime.fromtimestamp(time.time()+24*3600).isoformat()
        self.save_cache({
            "token":self.token,
            "openid":self.openid,
            "unionid":self.unionid,
            "userCode":self.user_code,
            "branchCode":self.branch_code,
            "appFirstMake":self.public_key,
            "rearEndUse":self.private_key,
            "expireTime":expire_time,
            "updateTime":_now()
        })
        self.log("✅登录成功，已缓存token与密钥")
        return True

    def task_sign(self):
        resp = self.api_post(SIGN_SAVE_URL, {"unionId":self.unionid,"userCode":self.user_code})
        code = resp.get("code")
        msg = resp.get("msg") or ""
        if code ==200:
            self.log(f"✅[签到]签到成功:{msg or '获得积分'}")
            return f"签到成功 {msg}".strip()
        if "重复签到" in msg or "已签" in msg:
            self.log(f"⚠️[签到]{msg}")
            return msg
        self.log(f"⚠️[签到]签到失败:{msg or json_preview(resp,200)}")
        return msg or "签到失败"

    def task_sign_status(self):
        try:
            resp = self.api_post(SIGN_LOG_URL, {"userCode":self.user_code,"unionId":self.unionid,"branchCode":self.branch_code})
            if resp.get("code") !=200:
                return "签到日历查询失败"
            data = resp.get("data")
            if isinstance(data, list):
                signed = sum(1 for item in data if isinstance(item,dict) and str(item.get("signFlag","")) in ("1","true","True"))
                return f"已签到 {signed} 天"
            return "签到日历获取成功"
        except Exception as e:
            self.log(f"⚠️[签到]日历查询异常:{e}")
            return "签到日历查询异常"

    def task_attention(self):
        try:
            is_resp = self.api_post(ATTENTION_IS_URL, {"unionId":self.unionid,"userCode":self.user_code})
            int_resp = self.api_post(ATTENTION_INTEGRAL_URL, {"unionId":self.unionid,"userCode":self.user_code})
            is_att = is_resp.get("data") if is_resp.get("code")==200 else None
            int_dat = int_resp.get("data") if int_resp.get("code")==200 else None
            self.log(f"📮[关注]关注状态:{is_att}，可得积分:{int_dat}")
            return f"关注状态 {is_att} / 积分 {int_dat}"
        except Exception as e:
            self.log(f"⚠️[关注]异常:{e}")
            return "关注任务异常"

    def current_time_type(self):
        hour = datetime.now().hour
        if hour <6: return 1
        if hour <12: return 2
        if hour <18: return3
        return4

    def task_top_points(self):
        ttype = self.current_time_type()
        texts = []
        for save_flag in (False, True):
            resp = self.api_post(TOP_POINTS_URL, {"userCode":self.user_code,"unionId":self.unionid,"savePoinsFlag":save_flag,"sendTimeType":ttype})
            code = resp.get("code")
            msg = resp.get("msg") or ""
            stage = "查询" if not save_flag else "领取"
            if code ==200:
                self.log(f"👍[点赞]{stage}:{msg}")
                texts.append(msg.strip())
            else:
                self.log(f"⚠️[点赞]{stage}失败:{msg or json_preview(resp,200)}")
                texts.append(msg or "失败")
            time.sleep(1)
        return " / ".join(texts) if texts else "点赞任务失败"

    def parse_video_length(self, value):
        if isinstance(value,(int,float)):
            return int(value) or30
        text = str(value or "").strip()
        if ":" in text:
            try:
                parts = [int(p) for p in text.split(":")]
                total =0
                for p in parts:
                    total = total*60 +p
                return total or30
            except ValueError:
                return30
        try:
            return int(float(value)) or30
        except ValueError:
            return30

    def task_video(self):
        try:
            series_resp = self.api_post(VIDEO_SERIES_URL, {"branchCode":self.branch_code}, need_encrypt=False)
            series_list = series_resp.get("data") if series_resp.get("code")==200 else None
            if isinstance(series_list, dict):
                series_list = series_list.get("list") or series_list.get("seriesList") or []
            if not isinstance(series_list, list) or not series_list:
                self.log(f"⚠️[视频]系列获取失败:{series_resp.get('msg') or '无系列'}")
                return "视频系列获取失败"
            watched =0
            for series in series_list[:4]:
                if not isinstance(series, dict): continue
                sname = series.get("seriesName") or series.get("name") or ""
                if not sname: continue
                list_resp = self.api_post(VIDEO_LIST_URL, {
                    "branchCode":self.branch_code,
                    "userCode":self.user_code,
                    "unionId":self.unionid,
                    "seriesName":sname
                })
                if list_resp.get("code")!=200:
                    self.log(f"⚠️[视频]{sname}:{list_resp.get('msg') or '列表获取失败'}")
                    continue
                videos = list_resp.get("data") or []
                if isinstance(videos, dict):
                    videos = videos.get("list") or videos.get("videoList") or []
                if not isinstance(videos, list): continue
                for video in videos[:8]:
                    if not isinstance(video,dict): continue
                    if str(video.get("integralStatus",""))=="1" or str(video.get("isGetIntegral",""))=="1":
                        continue
                    wl = self.parse_video_length(video.get("videoLength"))
                    save_resp = self.api_post(VIDEO_SAVE_URL,{
                        "userCode":self.user_code,
                        "unionId":self.unionid,
                        "videoConfigId":video.get("videoConfigId") or video.get("id"),
                        "videoSubCategory":video.get("videoSubCategory",""),
                        "watchLength":wl,
                        "isAlert":"0",
                        "isAgree":"",
                        "branchCode":self.branch_code,
                        "seriesName":sname,
                        "flag":video.get("flag","")
                    })
                    if save_resp.get("code")==200:
                        watched +=1
                        self.log(f"🎬[视频]观看上报成功:{video.get('videoName') or video.get('videoConfigId')} +{video.get('integral') or ''}")
                    else:
                        msg = save_resp.get("msg") or ""
                        if msg and "重复" not in msg and "已" not in msg:
                            self.log(f"⚠️[视频]{video.get('videoName') or ''}:{msg}")
                    time.sleep(random.randint(1,2))
            self.log(f"🎬[视频]本次观看上报 {watched} 个")
            return f"观看上报 {watched} 个"
        except Exception as e:
            self.log(f"⚠️[视频]异常:{e}")
            return "视频任务异常"

    def task_birthday(self):
        try:
            resp = self.api_post(BIRTHDAY_URL, {"userCode":self.user_code,"unionId":self.unionid})
            if resp.get("code")!=200:
                return "生日信息获取失败"
            data = safe_data(resp)
            if not isinstance(data, dict):
                return "无生日信息"
            is_get = data.get("isGet")
            birthday = data.get("birthday") or data.get("birthDay") or ""
            if is_get in (1,"1",True):
                return "生日积分已领取"
            month_day = datetime.now().strftime("%m-%d")
            if birthday and month_day in str(birthday):
                save_resp = self.api_post(BIRTHDAY_SAVE_URL, {"userCode":self.user_code,"unionId":self.unionid})
                if save_resp.get("code")==200:
                    self.log("🎂[生日]生日积分领取成功")
                    return "生日积分领取成功"
                return save_resp.get("msg") or "生日积分领取失败"
            return f"非生日月({birthday})"
        except Exception as e:
            self.log(f"⚠️[生日]异常:{e}")
            return "生日任务异常"

    def task_draw_num(self):
        resp = self.api_post(DRAW_NUM_URL, {"active_code":ACTIVE_CODE,"user_code":self.user_code,"unionId":self.unionid})
        if resp.get("code")==200:
            num = resp.get("data")
            if isinstance(num, bool):
                num =1 if num else0
            self.log(f"🎰[抽奖]当前可抽奖次数:{num}")
            return f"可抽奖 {num} 次"
        msg = resp.get("msg") or "抽奖次数查询失败"
        self.log(f"⚠️[抽奖]{msg}")
        return msg

    def task_collect(self):
        try:
            pending_resp = self.api_post(PENDING_INTEGRAL_URL, {"userCode":self.user_code,"unionId":self.unionid})
            if pending_resp.get("code")!=200:
                return pending_resp.get("msg") or "待领取查询失败"
            data = safe_data(pending_resp)
            items = data.get("tphPendingIntegralDetail") if isinstance(data,dict) else None
            if isinstance(data, list):
                items = data
            items = [x for x in (items or []) if isinstance(x,dict) and str(x.get("inFlag","0"))=="0" and x.get("id")]
            if not items:
                self.log("🧺[收取]暂无可收取能量")
                return "无可收取能量"
            collected =0
            for item in items:
                r = self.api_post(COLLECT_INTEGRAL_URL, {"userCode":self.user_code,"unionId":self.unionid,"id":item.get("id")})
                if r.get("code")==200:
                    collected +=1
                    self.log(f"🧺[收取]+{item.get('integral')} {item.get('sysSourceSubcategory') or '能量'}")
                else:
                    self.log(f"⚠️[收取]{r.get('msg') or '收取失败'}")
                time.sleep(1)
            self.log(f"🧺[收取]共收取 {collected} 笔")
            return f"收取 {collected} 笔"
        except Exception as e:
            self.log(f"⚠️[收取]异常:{e}")
            return "收取异常"

    def task_integral(self):
        pending_text = "-"
        fail_text = "-"
        try:
            p_resp = self.api_post(PENDING_INTEGRAL_URL, {"userCode":self.user_code,"unionId":self.unionid})
            if p_resp.get("code")==200:
                d = safe_data(p_resp)
                pending_text = str(d.get("tphPendingIntegralDetail") or d.get("integral") or d.get("pendingIntegral") or d)
                self.log(f"💰[积分]待领取积分:{pending_text}")
        except Exception as e:
            self.log(f"⚠️[积分]待领取查询异常:{e}")
        try:
            f_resp = self.api_post(FAIL_INTEGRAL_URL, {"userCode":self.user_code,"unionId":self.unionid})
            if f_resp.get("code")==200:
                d = safe_data(f_resp)
                fail_text = str(d.get("aboutFailIntegral",0))
                self.log(f"⏳[积分]即将失效积分:{fail_text}")
        except Exception as e:
            self.log(f"⚠️[积分]失效查询异常:{e}")
        return pending_text, fail_text

    def task_task_list(self):
        try:
            resp = self.api_post(TASK_LIST_URL, {
                "typeValue":"TAN_CATEGORY",
                "branchCode":self.branch_code,
                "unionId":self.unionid,
                "userCode":self.user_code
            })
            if resp.get("code")!=200:
                return resp.get("msg") or "任务列表获取失败"
            data = safe_data(resp)
            task_list = data.get("list") or data.get("taskList") or []
            if not isinstance(task_list, list):
                return "任务列表为空"
            self.log(f"📋[任务]获取到 {len(task_list)} 个低碳任务场景")
            return f"任务场景 {len(task_list)} 个"
        except Exception as e:
            self.log(f"⚠️[任务]异常:{e}")
            return "任务列表异常"

    def execute(self, query_only=False):
        self.log("---开始账号处理---")
        self.proxies,self.proxy_ip = get_valid_proxy(self.proxy_api,self.proxy_type,self.name)
        if self.proxies:
            self.log(f"🌐使用代理，出口ip:{self.proxy_ip}")
        time.sleep(random.randint(2,5))
        if not self.login():
            self.log("❌账号登录失败，跳过")
            return {"success":False,"signMsg":"-","signStatus":"-","attentionMsg":"-","topMsg":"-","videoMsg":"-","collectMsg":"-","birthdayMsg":"-","drawMsg":"-","taskMsg":"-","pendingIntegral":"-","failIntegral":"-","error":"登录失败"}
        res = {
            "success":True,"signMsg":"","signStatus":"","attentionMsg":"","topMsg":"","videoMsg":"",
            "collectMsg":"","birthdayMsg":"","drawMsg":"","taskMsg":"","pendingIntegral":"","failIntegral":"","error":""
        }
        res["signMsg"] = self.task_sign()
        self.log(f"📝签到:{res['signMsg']}")
        time.sleep(random.randint(1,3))
        res["signStatus"] = self.task_sign_status()
        self.log(f"📅签到状态:{res['signStatus']}")
        time.sleep(random.randint(1,2))
        res["attentionMsg"] = self.task_attention()
        self.log(f"📮关注:{res['attentionMsg']}")
        time.sleep(random.randint(1,2))
        res["topMsg"] = self.task_top_points()
        self.log(f"👍点赞:{res['topMsg']}")
        time.sleep(random.randint(1,2))
        res["videoMsg"] = self.task_video()
        self.log(f"🎬视频:{res['videoMsg']}")
        time.sleep(random.randint(1,2))
        res["collectMsg"] = self.task_collect()
        self.log(f"🧺收取:{res['collectMsg']}")
        time.sleep(random.randint(1,2))
        res["birthdayMsg"] = self.task_birthday()
        self.log(f"🎂生日:{res['birthdayMsg']}")
        time.sleep(random.randint(1,2))
        res["drawMsg"] = self.task_draw_num()
        self.log(f"🎰抽奖:{res['drawMsg']}")
        time.sleep(random.randint(1,2))
        res["taskMsg"] = self.task_task_list()
        self.log(f"📋任务:{res['taskMsg']}")
        if query_only:
            res["pendingIntegral"] = "【查询模式】跳过积分详细操作"
            res["failIntegral"] = "【查询模式】跳过积分详细操作"
            self.log("📋查询模式结束")
            return res
        res["pendingIntegral"], res["failIntegral"] = self.task_integral()
        self.log(f"💰待领取积分:{res['pendingIntegral']}")
        self.log(f"⏳即将失效:{res['failIntegral']}")
        return res

# =====================呆呆中间件SDK 青龙/呆呆OpenAPI部分=====================
import middleware
senderID = middleware.getSenderID()
sender = middleware.Sender(senderID)
userid = sender.getUserID()
imtype = sender.getImtype()

def get_config():
    qlname = middleware.bucketGet(BUCKET, 's_tph_qlname') or ''
    ddname = middleware.bucketGet(BUCKET, 's_tph_ddname') or ''
    osname = middleware.bucketGet(BUCKET, 's_tph_osname') or 'tphAccount'
    proxy_g = middleware.bucketGet(BUCKET, 's_tph_proxy_global') or ''
    return qlname, ddname, osname, proxy_g

s_tph_qlname, s_tph_ddname, s_tph_osname, s_tph_proxy_global = get_config()

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
    if len(s_tph_ddname)>0:
        arr = s_tph_ddname.split('丨')
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
    if len(s_tph_qlname)==0:
        sender.reply("❌未配置青龙或呆呆面板参数")
        exit(0)
    arr = s_tph_qlname.split('丨')
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
        "remarks":f"碳普惠:{remark_mark}|user:{uid}|呆呆插件"
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
        "remarks":f"碳普惠:{remark_mark}|user:{uid}|呆呆插件"
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
    if not (s_tph_qlname or s_tph_ddname):
        return False,"未配置面板，仅本地保存"
    if not accs:
        try:
            QLurl,qltoken = seekql()
            eid = allenvs(s_tph_osname, userid)
            if eid is not None:
                delenvs(eid)
        except Exception:
            pass
        return True,"已清空面板变量"
    try:
        QLurl,qltoken = seekql()
        val = build_env_value(accs)
        Addenvs(s_tph_osname, val, userid, userid)
        return True,"同步成功"
    except Exception as e:
        return False,f"同步异常:{str(e)}"

# =====================交互指令函数=====================
def tph_login():
    sender.reply("""
=====碳普惠登录导入账号=====
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
发送「碳普惠运行」执行任务
发送「碳普惠查询」仅查询状态
""")

def _run_all(query_only):
    accs = load_accounts()
    if not accs:
        return "❌暂无账号，请先发送「碳普惠登录」导入账号",[]
    summary_lines = []
    notify_content = f"🌱碳普惠任务 {'查询' if query_only else '执行'}结果\n时间:{_now()}\n------\n"
    all_push_token = set()
    for idx,acc in enumerate(accs,1):
        cfg = f"{acc['name']}#{acc['yyb_server']}#{acc['pushplus_token']}#{acc['proxy_api']}#{acc['proxy_type']}"
        u = TphUser(idx, cfg)
        print(f"\n{'='*50}\n账号[{idx}/{len(accs)}]{u.name}\n{'='*50}")
        res = u.execute(query_only=query_only)
        if acc.get("pushplus_token"):
            all_push_token.add(acc["pushplus_token"])
        icon = "✅" if res["success"] else "❌"
        line = f"{icon}{mask_str(u.name)} |签到:{res['signMsg']} |签到状态:{res['signStatus']} |关注:{res['attentionMsg']} |点赞:{res['topMsg']} |视频:{res['videoMsg']} |收取:{res['collectMsg']} |生日:{res['birthdayMsg']} |抽奖:{res['drawMsg']} |任务:{res['taskMsg']} |待领积分:{res['pendingIntegral']} |失效积分:{res['failIntegral']}"
        summary_lines.append(line)
        notify_content += f"\n【账号{idx}】{u.name}\n签到:{res['signMsg']}\n签到状态:{res['signStatus']}\n关注:{res['attentionMsg']}\n点赞:{res['topMsg']}\n视频:{res['videoMsg']}\n收取:{res['collectMsg']}\n生日:{res['birthdayMsg']}\n抽奖:{res['drawMsg']}\n任务:{res['taskMsg']}\n待领积分:{res['pendingIntegral']}\n失效积分:{res['failIntegral']}\n结果:{'成功' if res['success'] else '失败'}\n"
        if idx < len(accs):
            time.sleep(2)
    out_text = ("【碳普惠查询】" if query_only else "【碳普惠运行】") + f"共{len(accs)}个账号\n" + "\n".join(summary_lines)
    for pt in all_push_token:
        send_pushplus(pt,"🌱碳普惠任务通知", notify_content)
    return out_text, list(all_push_token)

def tph_query():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先碳普惠登录导入")
        return
    sender.reply("🔎正在查询全部账号状态...")
    out,_ = _run_all(query_only=True)
    sender.reply(out)

def tph_run():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先碳普惠登录导入")
        return
    sender.reply("🚀开始执行碳普惠全部任务...")
    out,_ = _run_all(query_only=False)
    sender.reply(out)

def tph_manage():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号")
        return
    buf = ["====碳普惠账号管理====",f"共{len(accs)}个账号"]
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

def tph_clean():
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

def tph_update():
    accs = load_accounts()
    ok,msg = sync_to_panel(accs)
    if accs:
        sender.reply(f"✅本地{len(accs)}个账号同步面板：{msg}\n面板定时任务触发「碳普惠运行」执行每日任务")
    else:
        sender.reply(f"⚠️本地无账号 {msg}")

def tph_check():
    accs = load_accounts()
    if not accs:
        sender.reply("❌暂无账号，请先导入账号")
        return
    sender.reply("🔎检测账号配置有效性（仅做登录尝试）")
    lines = []
    for idx,a in enumerate(accs,1):
        cfg = f"{a['name']}#{a['yyb_server']}#{a['pushplus_token']}#{a['proxy_api']}#{a['proxy_type']}"
        u = TphUser(idx, cfg)
        ok = u.login()
        lines.append(f"•{mask_str(u.name)} {'✅配置可登录' if ok else '❌登录失败'}")
    sender.reply("====碳普惠账号检测====\n"+"\n".join(lines))

# =====================指令路由&入口=====================
def handle_command(msg):
    msg = str(msg or "").strip()
    if "登录" in msg or "登陆" in msg:
        tph_login()
    elif "运行" in msg:
        tph_run()
    elif "查询" in msg:
        tph_query()
    elif "管理" in msg:
        tph_manage()
    elif "清理" in msg:
        tph_clean()
    elif "更新" in msg:
        tph_update()
    elif "检测" in msg:
        tph_check()
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
