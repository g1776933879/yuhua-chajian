# [title: pd仪表盘监控]
# [icon: https://cdn.jsdelivr.net/gh/lhz03/img@8b8c57f2b4173a6ec2b5c7e58db07be1158e0e16/2025/02/20/f63f99f95da0cf1fb83949c22061cbfb.png]
# [rule: ^拼豆菜单$|^拼豆仪表盘$|^拼豆状态$|^拼豆卡密.*$|^拼豆统计$|^拼豆排行.*$|^拼豆新图$|^拼豆公告$|^拼豆分类$|^拼豆帮助$]
# [language: python]
# [disable: false]
# [public: true]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb]
# [author: Agnes]
# [open_source: false]
# [priority: 9999999999999999999]
# [version: 2.0.0]
# [price: 0]
# [service: ]
# [description: 拼豆图纸管理插件：仪表盘统计、卡密生成查询、排行榜、新图监控等功能]

import urllib.request
import urllib.parse
import json
import time
import ssl
import re
import http.cookiejar
import middleware

SITE_URL = 'https://pd.xsqapp.top'
ADMIN_USER = 'admin'
ADMIN_PASS = 'admin888'
REFRESH_INTERVAL = 120

_cache = {}
_last_refresh = 0
_opener = None
_admin_csrf = None
_admin_login_ts = 0

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


def _get_opener():
    global _opener
    if _opener is not None:
        return _opener
    jar = http.cookiejar.CookieJar()
    _opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=_ssl_ctx)
    )
    _opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
    return _opener


def _admin_login():
    global _admin_csrf, _admin_login_ts
    now = time.time()
    if _admin_csrf and now - _admin_login_ts < 3600:
        return True
    try:
        opener = _get_opener()
        req = urllib.request.Request(f'{SITE_URL}/admin/')
        resp = opener.open(req, timeout=15)
        resp.read()

        login_data = json.dumps({'username': ADMIN_USER, 'password': ADMIN_PASS}).encode('utf-8')
        login_req = urllib.request.Request(
            f'{SITE_URL}/api/admin/login/',
            data=login_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        login_resp = opener.open(login_req, timeout=15)
        login_text = login_resp.read().decode('utf-8')
        result = json.loads(login_text)
        if result.get('success'):
            _admin_csrf = result.get('csrf_token', '')
            _admin_login_ts = now
            return True
        return False
    except Exception as e:
        print('[pd仪表盘] 后台登录失败: ', e)
        return False


def _admin_api(path, method='GET', data=None):
    if not _admin_login():
        return None
    try:
        opener = _get_opener()
        body = None
        headers = {'X-CSRF-Token': _admin_csrf}
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        url = f'{SITE_URL}/api/admin{path}'
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        resp = opener.open(req, timeout=15)
        text = resp.read().decode('utf-8')
        return json.loads(text)
    except Exception as e:
        print('[pd仪表盘] 后台API失败 ', path, ': ', e)
        return None


def _public_api(path):
    try:
        url = f'{SITE_URL}{path}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15, context=_ssl_ctx)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print('[pd仪表盘] 公开API失败 ', path, ': ', e)
        return None


def get_dashboard_data():
    global _cache, _last_refresh
    now = time.time()
    if now - _last_refresh < REFRESH_INTERVAL and _cache:
        return _cache
    data = {'announcements': [], 'categories': [], 'gallery_stats': {}, 'admin_stats': {}, 'cards': {}}

    ann = _public_api('/api/announcements/')
    if ann and 'announcements' in ann:
        data['announcements'] = ann['announcements']

    cats = _public_api('/api/categories/')
    if cats:
        data['categories'] = cats

    gallery = _public_api('/api/gallery/')
    if gallery and 'images' in gallery:
        data['gallery_stats'] = {
            'total_images': gallery.get('total', 0),
            'recent_images': gallery['images'][:5]
        }

    stats = _admin_api('/stats')
    if stats:
        data['admin_stats'] = stats

    cards = _admin_api('/cards?page=1')
    if cards:
        data['cards'] = {
            'total': cards.get('total', 0),
            'recent': cards.get('cards', [])[:5]
        }

    _cache = data
    _last_refresh = now
    return data


def generate_cards(days, count, prefix='', fmt=12):
    result = _admin_api('/cards/generate', 'POST', {
        'days': days,
        'count': count,
        'prefix': prefix,
        'format': fmt
    })
    if result and result.get('success'):
        return result.get('codes', [])
    return None


def query_cards(search='', page=1):
    return _admin_api(f'/cards?page={page}&search={urllib.parse.quote(search)}')


def format_dashboard_message(data):
    lines = ['📊 **拼豆图纸仪表盘**', '']

    if data.get('admin_stats'):
        s = data['admin_stats']
        lines.append('📈 **站点统计**')
        lines.append(f"   总用户: {s.get('total_users', 0)} | 今日新增: {s.get('today_users', 0)}")
        lines.append(f"   今日UV: {s.get('today_uv', 0)} | 昨日UV: {s.get('yesterday_uv', 0)}")
        lines.append(f"   总UV: {s.get('total_uv', 0)}")
        lines.append(f"   可用卡密: {s.get('active_cards', 0)}")
        lines.append(f"   公开图纸: {s.get('public_images', 0)}")
        lines.append('')

    if data.get('announcements'):
        lines.append('📢 **最新公告**')
        ann = data['announcements'][0]
        lines.append(f"  {ann.get('title', '')}")
        lines.append(f"  {ann.get('content', '')[:80]}...")
        lines.append('')

    if data.get('categories'):
        lines.append(f"📁 **分类**: {len(data['categories'])} 个")
        lines.append("   " + ", ".join(c['name'] for c in data['categories'][:6]))
        lines.append('')

    if data.get('gallery_stats'):
        stats = data['gallery_stats']
        lines.append('🖼️ **图库数据**')
        lines.append(f"   总图纸数: {stats.get('total_images', 0)}")
        if stats.get('recent_images'):
            lines.append('   最新图纸:')
            for img in stats['recent_images'][:3]:
                lines.append(f"   - {img.get('original_name', '未知')} ({img.get('category_name', '')})")
                lines.append(f"     尺寸:{img.get('grid_size', 0)} 颜色:{img.get('color_count', 0)} 下载:{img.get('downloads_count', 0)}")
        lines.append('')

    return '\n'.join(lines)


def format_card_result(codes):
    lines = ['✅ **卡密生成成功**', '']
    for code in codes:
        lines.append(f'`{code}`')
    lines.append('')
    lines.append(f'共生成 {len(codes)} 个卡密')
    return '\n'.join(lines)


def format_card_list(cards_data):
    if cards_data:
        cards = cards_data.get('cards', [])
    else:
        cards = []
    if not cards:
        return '暂无卡密数据'
    lines = ['🔑 **卡密列表**', '']
    for c in cards[:10]:
        status = '✅可用' if c.get('status') == 0 else '❌已用'
        user = c.get('used_by_name') or c.get('used_by') or '-'
        lines.append(f"{status} `{c.get('code', '')}` {c.get('days', 0)}天 用户:{user}")
    lines.append('')
    total = cards_data.get('total', len(cards))
    lines.append(f'共 {total} 个卡密')
    return '\n'.join(lines)


def format_rank_message(sort_type):
    gallery = _public_api(f'/api/gallery?sort={sort_type}&page=1')
    if not gallery or 'images' not in gallery:
        return '获取排行榜失败'
    label = '下载榜' if sort_type == 'downloads' else '点赞榜'
    lines = [f'🏆 **拼豆{label}**', '']
    for i, img in enumerate(gallery['images'][:10]):
        lines.append(f"{i + 1}. {img.get('original_name', '未知')} ({img.get('category_name', '')})")
        lines.append(f"   💾{img.get('downloads_count', 0)} 次下载 | ❤️{img.get('likes_count', 0)} | {img.get('grid_size', 0)}×{img.get('grid_size', 0)} {img.get('color_count', 0)}色")
    return '\n'.join(lines)


def main():
    sender = middleware.Sender(middleware.getSenderID())
    message = str(sender.getMessage() or '').strip()

    if message in ('拼豆菜单', '拼豆仪表盘', '拼豆状态'):
        data = get_dashboard_data()
        sender.reply(format_dashboard_message(data))
        return

    if message == '拼豆统计':
        data = get_dashboard_data()
        if data.get('admin_stats'):
            s = data['admin_stats']
            lines = ['📈 **拼豆站点统计**', '']
            lines.append(f"👥 总用户: {s.get('total_users', 0)}")
            lines.append(f"🆕 今日新增: {s.get('today_users', 0)}")
            lines.append(f"👀 今日UV: {s.get('today_uv', 0)}")
            lines.append(f"📊 昨日UV: {s.get('yesterday_uv', 0)}")
            lines.append(f"🌐 总UV: {s.get('total_uv', 0)}")
            lines.append(f"🔑 可用卡密: {s.get('active_cards', 0)}")
            lines.append(f"🖼️ 公开图纸: {s.get('public_images', 0)}")
            sender.reply('\n'.join(lines))
            return
        sender.reply('❌ 获取统计数据失败')
        return

    if message.startswith('拼豆卡密生成'):
        parts = message.split()
        days = int(parts[1]) if len(parts) > 1 else 30
        count = int(parts[2]) if len(parts) > 2 else 1
        prefix = parts[3] if len(parts) > 3 else ''
        try:
            codes = generate_cards(days, count, prefix)
            if codes:
                sender.reply(format_card_result(codes))
            else:
                sender.reply('❌ 卡密生成失败')
        except Exception as e:
            sender.reply(f'❌ 卡密生成失败: {str(e)[:100]}')
        return

    if message in ('拼豆卡密列表', '拼豆卡密查询'):
        cards_data = query_cards()
        sender.reply(format_card_list(cards_data))
        return

    if message == '拼豆排行下载':
        sender.reply(format_rank_message('downloads'))
        return

    if message in ('拼豆排行点赞', '拼豆排行'):
        sender.reply(format_rank_message('likes'))
        return

    if message == '拼豆公告':
        data = get_dashboard_data()
        if data.get('announcements'):
            ann = data['announcements'][0]
            sender.reply(f"📢 {ann.get('title', '')}\n\n{ann.get('content', '')}")
            return
        sender.reply('暂无公告')
        return

    if message == '拼豆分类':
        data = get_dashboard_data()
        if data.get('categories'):
            cats = [f"{i + 1}. {c['name']}" for i, c in enumerate(data['categories'])]
            sender.reply('📁 分类列表:\n' + '\n'.join(cats))
            return
        sender.reply('暂无分类数据')
        return

    if message == '拼豆新图':
        data = get_dashboard_data()
        if data.get('gallery_stats') and data['gallery_stats'].get('recent_images'):
            lines = ['🆕 **最新图纸**', '']
            for img in data['gallery_stats']['recent_images'][:5]:
                lines.append(f"📌 {img.get('original_name', '未知')}")
                lines.append(f"   分类:{img.get('category_name', '-')} 尺寸:{img.get('grid_size', 0)}×{img.get('grid_size', 0)}")
                lines.append(f"   颜色:{img.get('color_count', 0)} 下载:{img.get('downloads_count', 0)} 作者:{img.get('nickname', '-')}")
                lines.append('')
            sender.reply('\n'.join(lines))
            return
        sender.reply('暂无新图数据')
        return

    if message == '拼豆帮助':
        lines = ['📖 **拼豆插件使用帮助**', '']
        lines += [
            '`拼豆菜单` - 显示仪表盘',
            '`拼豆统计` - 站点统计数据',
            '`拼豆卡密生成 [天数] [数量] [前缀]` - 生成卡密',
            '   示例: 拼豆卡密生成 30 10 VIP',
            '`拼豆卡密列表` - 查看卡密列表',
            '`拼豆排行下载` - 下载排行榜',
            '`拼豆排行点赞` - 点赞排行榜',
            '`拼豆新图` - 最新图纸',
            '`拼豆公告` - 最新公告',
            '`拼豆分类` - 分类列表'
        ]
        sender.reply('\n'.join(lines))
        return

    sender.reply('发送 `拼豆帮助` 查看可用指令')
    sender.setContinue()


if __name__ == '__main__':
    main()
