# [title: 菜单]
# [language: python]
# [rule: ^菜单$]
# [platform: qq,qb,wx,gw,sb,wb,tg,tb,qx,xy,ip]
# [public: true]
# [priority: 999999]
# [version: 1.2.3]
# [author: 枕风听晚]
# [description: 自动扫描同目录 Python 插件的元数据并生成菜单，无需手工维护指令列表。]
# [param: {"required":false,"key":"auto_menu.title","bool":false,"placeholder":"主人，请选择功能","name":"菜单标题","desc":"菜单顶部显示的标题"}]
# [param: {"required":false,"key":"auto_menu.footer","bool":false,"placeholder":"发送对应指令即可使用","name":"菜单页脚","desc":"菜单底部显示的提示"}]
# [param: {"required":false,"key":"auto_menu.hidden","bool":false,"placeholder":"插件名1,插件名2","name":"隐藏插件","desc":"不在菜单展示的插件标题，多个用逗号分隔"}]
# [param: {"required":false,"key":"auto_menu.plugin_dir","bool":false,"placeholder":"/root/yuhua-panel/data/plugins","name":"插件目录","desc":"可选的额外插件目录；默认自动扫描菜单所在目录和面板默认目录"}]

import json
import os
import re
from pathlib import Path

import middleware

BUCKET = "auto_menu"
SCRIPT_BUCKET = "plugins_script"
HEADER_LIMIT = 200
sender = middleware.Sender(middleware.getSenderID())


def config(key, default=""):
    return str(middleware.bucketGet(BUCKET, key) or default).strip()


def meta_values(text, key):
    # 兼容“#[rule: ...] 匹配规则”等标签闭合后仍带说明文字的旧式元数据。
    pattern = rf"^#\s*\[{re.escape(key)}\s*:\s*(.*)\]\s*.*$"
    return [item.strip() for item in re.findall(pattern, text, re.M | re.I) if item.strip()]


def meta_value(text, key):
    values = meta_values(text, key)
    return values[0] if values else ""


def script_text(raw):
    """兼容数据桶直接存源码及 JSON 包装源码两种结构。"""
    if raw in (None, ""):
        return ""
    text = str(raw)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return text
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("content", "script", "code", "source", "data"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return text


def read_bucket_script(key):
    try:
        return script_text(middleware.bucketGet(SCRIPT_BUCKET, key))
    except Exception:
        return ""


def split_alternatives(value):
    parts, start, depth = [], 0, 0
    for index, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "|" and depth == 0:
            parts.append(value[start:index]); start = index + 1
    parts.append(value[start:])
    return parts


def expand_expression(value):
    """递归展开普通文字、选择组和顶层分支。"""
    branches = split_alternatives(value)
    if len(branches) > 1:
        result = []
        for branch in branches:
            result.extend(expand_expression(branch.removeprefix("^").removesuffix("$")))
        return result
    results, index = [""], 0
    while index < len(value):
        if value[index] == "(":
            depth, end = 1, index + 1
            while end < len(value) and depth:
                depth += (value[end] == "(") - (value[end] == ")")
                end += 1
            if depth:
                return []
            inner = value[index + 1:end - 1]
            choices = [" … "] if inner in (".*", ".+") else expand_expression(inner)
            if not choices:
                return []
            results = [prefix + choice for prefix in results for choice in choices]
            index = end
            continue
        if value.startswith((".*", ".+"), index):
            results = [prefix + " … " for prefix in results]
            index += 2
            continue
        char = value[index]
        if char in "^$":
            index += 1
            continue
        if char == "\\" or char in "[]{}?+*":
            return []
        results = [prefix + char for prefix in results]
        index += 1
    return results


def simple_commands(rule):
    """展开顶层多分支、嵌套选择组及尾随通配符。"""
    value = rule.strip().replace("(?:", "(")
    if not value or "http" in value.lower() or "\\." in value:
        return []
    commands = expand_expression(value)
    return list(dict.fromkeys(" ".join(item.split()) for item in commands if item.strip()))[:50]


def description_commands(description):
    match = re.search(r"指令[：:]\s*([^。；<]+)", description)
    if not match:
        return []
    values = re.split(r"[、，,\s]+", match.group(1).strip())
    return [item for item in values if item and len(item) <= 20]


def is_auto_rule(rule):
    """仅过滤明确的链接/媒体自动触发规则，避免误伤含转义符的普通命令。"""
    lowered = rule.lower()
    return any(mark in lowered for mark in ("http://", "https://", "https?://", "cq:image", "cq:video"))


def rule_commands(rule):
    commands = simple_commands(rule)
    if commands:
        return commands
    # 复杂参数规则至少提取开头的中文命令词，如“天气\\s+城市”。
    value = rule.removeprefix("^").lstrip("(")
    match = re.match(r"([\u4e00-\u9fffA-Za-z0-9_-]{2,})", value)
    return [match.group(1) + " …"] if match else []


def plugin_info(key, source):
    header = "\n".join(source.splitlines()[:HEADER_LIMIT])
    title = meta_value(header, "title") or str(key).rsplit("/", 1)[-1].removesuffix(".py")
    if title == "菜单":
        return None
    hidden = {x.strip() for x in re.split(r"[,，]", config("hidden")) if x.strip()}
    if title in hidden or meta_value(header, "menu_hidden").lower() == "true":
        return None
    rules = meta_values(header, "rule")
    visible_rules = [rule for rule in rules if not is_auto_rule(rule)]
    description = meta_value(header, "description")
    commands = []
    for rule in visible_rules:
        commands.extend(rule_commands(rule))
    commands = list(dict.fromkeys(commands or description_commands(description)))[:30]
    # 无 rule 的脚本不是消息插件；纯链接/媒体监听插件按要求隐藏。
    if not rules or not visible_rules:
        return None
    try:
        order = int(meta_value(header, "menu_order") or "100")
    except ValueError:
        order = 100
    return {"title": title, "commands": commands, "order": order}


def read_file_script(path):
    try:
        return path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return ""


def plugin_directories():
    """优先当前脚本目录，并兼容面板固定插件目录及自定义目录。"""
    values = []
    if "__file__" in globals():
        values.append(Path(__file__).resolve().parent)
    values.append(Path(os.getcwd()))
    custom = config("plugin_dir")
    if custom:
        values.append(Path(custom).expanduser())
    values.append(Path("/root/yuhua-panel/data/plugins"))
    result = []
    for path in values:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in result:
            result.append(resolved)
    return result


def merge_plugin(target, info):
    """同标题合并命令，数据桶与文件任一有记录都不会遗漏。"""
    if not info:
        return
    title = info["title"]
    if title not in target:
        target[title] = info
        return
    old = target[title]
    old["commands"] = list(dict.fromkeys(old["commands"] + info["commands"]))[:50]
    old["order"] = min(old["order"], info["order"])


def scan_plugins():
    found = {}
    try:
        keys = middleware.bucketAllKeys(SCRIPT_BUCKET) or []
    except Exception:
        keys = []
    for key in keys:
        source = read_bucket_script(key)
        if source:
            merge_plugin(found, plugin_info(key, source))
    for directory in plugin_directories():
        for path in directory.glob("*.py"):
            source = read_file_script(path)
            if source:
                merge_plugin(found, plugin_info(path.name, source))
    return sorted(found.values(), key=lambda item: (item["order"], item["title"]))


def split_reply(text, limit=3500):
    parts, current = [], []
    length = 0
    for line in text.splitlines():
        size = len(line) + 1
        if current and length + size > limit:
            parts.append("\n".join(current)); current, length = [], 0
        current.append(line); length += size
    if current:
        parts.append("\n".join(current))
    return parts


def main():
    plugins = scan_plugins()
    if not plugins:
        sender.reply("❌ 未扫描到可展示的插件")
        return
    lines = [f"====={config('title', '主人，请选择功能')}====="]
    for index, plugin in enumerate(plugins, 1):
        lines.append(f"\n[{index}] {plugin['title']}")
        if plugin["commands"]:
            lines.extend(f"  ▫️ {command}" for command in plugin["commands"])
    lines.extend(["\n------------------", config("footer", "发送对应指令即可使用"), "=================="])
    for part in split_reply("\n".join(lines)):
        sender.reply(part)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sender.reply(f"❌ 菜单生成失败: {str(exc)}")
