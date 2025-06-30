import requests
from bs4 import BeautifulSoup
import hashlib
import time
from datetime import datetime, timedelta
import json
import os
from urllib.parse import quote

from urllib3.exceptions import ConnectTimeoutError

from logger import Logger

# ===== 配置区 =====
CONFIG = {
    # 监控目标（北领地签证公告页面）
    "target_url": "https://theterritory.com.au/migrate/migrate-to-work/northern-territory-government-visa-nomination",

    # 企业微信配置
    "wecom": {
        "corp_id": "ww8142d74a8ce580bd",  # 企业ID
        "corp_secret": "CSrgAXRHckq289P1SLDWmg8WQO2xRclp2Gd2asA6D18",  # 应用Secret
        "agent_id": 1000002,  # 应用AgentID
    },

    # 监控参数
    "check_interval": 300,  # 检查间隔(秒)
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "storage_file": "last_state.json",  # 状态存储文件
    "log_file": "visa_monitor.log",  # 日志文件路径（新增）
    "max_log_size": 10 * 1024 * 1024,  # 单个日志文件最大10MB（新增）
    "backup_log_count": 3  # 保留3个历史日志文件（新增）
}

# ===== 企业微信通知模块 =====
class WeComNotifier:
    def __init__(self, config):
        self.corp_id = config["corp_id"]
        self.corp_secret = config["corp_secret"]
        self.agent_id = config["agent_id"]
        self.token = None
        self.token_expire = None

    def refresh_token(self):
        """刷新Access Token"""
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corp_id}&corpsecret={self.corp_secret}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("errcode") == 0:
            self.token = data["access_token"]
            self.token_expire = datetime.now() + timedelta(seconds=data["expires_in"] - 300)  # 提前5分钟刷新
            return True
        raise Exception(f"获取Token失败: {data.get('errmsg')}")

    def send(self, title, content, url=None):
        """发送Markdown消息"""
        if not self.token or datetime.now() >= self.token_expire:
            self.refresh_token()

        # 构建Markdown内容
        md_content = f"**{title}**\n{content}"
        if url:
            md_content += f"\n[查看详情]({url})"

        payload = {
            "touser": "@all",
            "msgtype": "markdown",
            "agentid": self.agent_id,
            "markdown": {"content": md_content},
            "enable_duplicate_check": 1,
            "duplicate_check_interval": 1800  # 30分钟内重复消息不发送
        }

        resp = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": self.token},
            json=payload,
            timeout=15
        )
        result = resp.json()
        if result.get("errcode") != 0:
            raise Exception(f"发送失败: {result.get('errmsg')}")


# ===== 网页监控模块 =====
class VisaMonitor:
    def __init__(self):
        self.logger = Logger(
            log_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "visa_monitor.log"),  # 用户主目录下的日志文件
            max_size=10 * 1024 * 1024,  # 10MB
            backup_count=3,         # 保留3个历史文件
            level="INFO"
        )
        self.notifier = WeComNotifier(CONFIG["wecom"])
        self.headers = {"User-Agent": CONFIG["user_agent"]}
        self.last_state = self.load_state()
        self.initial_delay = 1
        self.backoff_factor = 2

    def send_bark(self, title, content, device_key):
        """
        发送Bark通知
        :param device_key: Bark App中获取的Key（如"abcd1234"）
        """
        base_url = f"https://api.day.app/{device_key}"
        url = f"{base_url}/{quote(title)}/{quote(content)}"

        # 可选参数（根据需要添加）
        params = {
            "sound": "minuet",  # 通知铃声（默认bell）
            "icon": "https://example.com/icon.png",  # 通知图标
            "group": "visa_monitor",  # 通知分组
            "level": "timeSensitive"  # 即时推送（iOS15+）
        }

        response = requests.get(url, params=params)
        if response.json().get("code") == 200:
            self.logger.info("Bark通知发送成功")
        else:
            self.logger.error(f"发送失败: {response.text}")

    def fetch_page(self):
        """获取网页内容"""
        max_retries = 10
        retry_count = 0
        while retry_count <= max_retries:
            try:
                resp = requests.get(
                    CONFIG["target_url"],
                    headers=self.headers,
                    timeout=20,
                    allow_redirects=True
                )
                resp.raise_for_status()
                return resp.text
            except (requests.exceptions.ConnectionError, requests.Timeout) as e:
                # 仅处理连接类异常（含10054）
                retry_count += 1
                if retry_count > max_retries:
                    self.logger.error(f"最终请求失败（重试{retry_count}次后）: {str(e)}")
                    return None
                # 计算等待时间（指数退避：1s → 2s → 4s → 8s...）
                delay = self.initial_delay * (self.backoff_factor ** (retry_count - 1))
                self.logger.info(f"第{retry_count}次重试（等待{delay}秒后）...")
                time.sleep(delay)
            except Exception as e:
                self.logger.error(f"页面获取失败: {str(e)}")
                return None

    def parse_content(self, html):
        """解析公告内容"""
        soup = BeautifulSoup(html, 'html.parser')

        # 核心内容选择器（根据实际页面调整）
        content_area = soup.select_one("main article") or soup.select_one(".content-wrapper")
        if not content_area:
            raise Exception("无法定位公告内容区域")

        # 提取关键信息
        title = soup.title.get_text(strip=True) if soup.title else "北领地签证公告"
        date = self.extract_date(soup)
        text = self.clean_text(content_area.get_text("\n", strip=True))

        return {
            "title": title,
            "date": date or datetime.now().strftime("%Y-%m-%d"),
            "content": text,
            "url": CONFIG["target_url"],
            "hash": hashlib.md5(text.encode()).hexdigest()
        }

    def extract_date(self, soup):
        """智能提取日期"""
        for selector in [
            'time[datetime]',
            '.published-date',
            'meta[property="article:published_time"]',
            'span.date'
        ]:
            elem = soup.select_one(selector)
            if elem:
                return elem.get("datetime") or elem.get_text(strip=True)
        return None

    def clean_text(self, text):
        """清理文本内容"""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:20])  # 最多保留20行

    def load_state(self):
        """加载上次状态"""
        if os.path.exists(CONFIG["storage_file"]):
            with open(CONFIG["storage_file"], "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_state(self, data):
        """保存当前状态"""
        with open(CONFIG["storage_file"], "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def compare_content(self, old, new):
        """比较内容差异"""
        if not old:
            return "首次检测到公告内容"

        if old["hash"] == new["hash"]:
            return None

        # 生成简化版差异报告
        old_lines = old["content"].splitlines()
        new_lines = new["content"].splitlines()

        diff = []
        for line in new_lines:
            if line not in old_lines and len(line) > 10:  # 过滤短行
                diff.append(f"• {line}")
                if len(diff) >= 3:  # 最多显示3条差异
                    break

        return "主要变更:\n" + "\n".join(diff) if diff else "内容有更新"

    def log(self, message, level="info"):
        """日志记录"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level.upper()}: {message}")

    def run(self):
        """启动监控"""
        times = 0
        self.logger.info(f"开始监控 {CONFIG['target_url']}")
        try:
            while True:
                times += 1
                self.logger.info(f"当前监控轮次：{times}, 当前时间: {datetime.now()}")
                try:
                    html = self.fetch_page()
                    if html:
                        current = self.parse_content(html)
                        changes = self.compare_content(self.last_state, current)

                        if changes:
                            self.logger.info(f"检测到更新: {current['title']}")
                            self.send_bark("alarm", changes, "LJnXEdnVYB4yEDW2cXQuSb")
                            self.send_bark("alarm", changes, "hpqcbhJG9xxc4wtNm7s4o")
                            self.save_state(current)
                        else:
                            self.logger.info("内容无变化")

                    self.last_state = current or self.last_state
                except Exception as e:
                    self.logger.error(f"监控异常: {str(e)}")

                time.sleep(CONFIG["check_interval"])

        except KeyboardInterrupt:
            self.logger.error("监控服务已手动停止")


# ===== 主程序 =====
if __name__ == "__main__":
    monitor = VisaMonitor()
    monitor.run()
