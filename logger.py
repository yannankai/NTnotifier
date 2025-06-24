import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

class Logger:
    def __init__(self, log_file, max_size=10 * 1024 * 1024, backup_count=3, level="INFO"):
        """
        初始化日志类
        :param log_file: 日志文件路径（如："logs/visa_monitor.log"）
        :param max_size: 单个日志文件最大大小（字节），默认10MB
        :param backup_count: 保留的历史日志文件数量，默认3个
        :param level: 日志级别（"DEBUG"/"INFO"/"WARNING"/"ERROR"/"CRITICAL"），默认INFO
        """
        self.log_file = log_file
        self.max_size = max_size
        self.backup_count = backup_count
        self.level = level.upper()

        # 自动创建日志文件所在目录
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # 配置日志格式（与原print一致：[时间] 级别: 消息）
        self.formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 初始化日志器
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(getattr(logging, self.level))

        # 清空原有处理器（避免重复添加）
        if self.logger.handlers:
            self.logger.handlers = []

        # 添加控制台处理器（输出到终端）
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self.formatter)
        self.logger.addHandler(console_handler)

        # 添加文件处理器（滚动存储）
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_size,
            backupCount=self.backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)

    def info(self, message):
        """记录INFO级别日志"""
        self.logger.info(message)

    def error(self, message):
        """记录ERROR级别日志"""
        self.logger.error(message)

    def warning(self, message):
        """记录WARNING级别日志"""
        self.logger.warning(message)

    def debug(self, message):
        """记录DEBUG级别日志"""
        self.logger.debug(message)

    def critical(self, message):
        """记录CRITICAL级别日志"""
        self.logger.critical(message)
