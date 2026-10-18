# -*- coding: utf-8 -*-
# @Author  : mrx19830705865@gmail.com
# @Time    : 2023/12/2 12:52
# @Desc    : 时间相关的工具函数

import re
import time
import sys
import os
from datetime import datetime, timedelta, timezone

# 处理相对导入问题
try:
    from .decorators import run_safe_model
    from .log import logger
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.decorators import run_safe_model
    from utils.log import logger


def get_current_timestamp() -> int:
    """
    获取当前的时间戳(13 位)：1701493264496
    :return:
    """
    return int(time.time() * 1000)


def get_current_time() -> str:
    """
    获取当前的时间：'2023-12-02 13:01:23'
    :return:
    """
    return time.strftime('%Y-%m-%d %X', time.localtime())


def get_current_date() -> str:
    """
    获取当前的日期：'2023-12-02'
    :return:
    """
    return time.strftime('%Y-%m-%d', time.localtime())


def get_time_str_from_unix_time(unixtime):
    """
    unix 整数类型时间戳  ==> 字符串日期时间
    :param unixtime:
    :return:
    """
    if int(unixtime) > 1000000000000:
        unixtime = int(unixtime) / 1000
    return time.strftime('%Y-%m-%d %X', time.localtime(unixtime))


def get_date_str_from_unix_time(unixtime):
    """
    unix 整数类型时间戳  ==> 字符串日期
    :param unixtime:
    :return:
    """
    if int(unixtime) > 1000000000000:
        unixtime = int(unixtime) / 1000
    return time.strftime('%Y-%m-%d', time.localtime(unixtime))


def get_unix_time_from_time_str(time_str):
    """
    字符串时间 ==> unix 整数类型时间戳，精确到秒
    :param time_str:
    :return:
    """
    try:
        format_str = "%Y-%m-%d %H:%M:%S"
        tm_object = time.strptime(str(time_str), format_str)
        return int(time.mktime(tm_object))
    except Exception as e:
        return 0
    pass


def get_unix_timestamp():
    return int(time.time())


def get_timestamp(unit: str = "milli"):
    """
    根据给定的单位获取当前时间 (Get the current time based on the given unit)

    Args:
        unit (str): 时间单位，可以是 "milli"、"sec"、"min" 等
            (The time unit, which can be "milli", "sec", "min", etc.)

    Returns:
        int: 根据给定单位的当前时间 (The current time based on the given unit)
    """

    now = datetime.utcnow() - datetime(1970, 1, 1)
    if unit == "milli":
        return int(now.total_seconds() * 1000)
    elif unit == "sec":
        return int(now.total_seconds())
    elif unit == "min":
        return int(now.total_seconds() / 60)
    else:
        raise ValueError("Unsupported time unit")

def rfc2822_to_china_datetime(rfc2822_time):
    # 定义RFC 2822格式
    rfc2822_format = "%a %b %d %H:%M:%S %z %Y"

    # 将RFC 2822时间字符串转换为datetime对象
    dt_object = datetime.strptime(rfc2822_time, rfc2822_format)

    # 将datetime对象的时区转换为中国时区
    dt_object_china = dt_object.astimezone(timezone(timedelta(hours=8)))
    return dt_object_china.strftime('%Y-%m-%d %H:%M:%S')


def rfc2822_to_timestamp(rfc2822_time):
    # 定义RFC 2822格式
    rfc2822_format = "%a %b %d %H:%M:%S %z %Y"

    # 将RFC 2822时间字符串转换为datetime对象
    dt_object = datetime.strptime(rfc2822_time, rfc2822_format)

    # 将datetime对象转换为UTC时间
    dt_utc = dt_object.replace(tzinfo=timezone.utc)

    # 计算UTC时间对应的Unix时间戳
    timestamp = int(dt_utc.timestamp())

    return timestamp


def get_video_duration(video_duration_text: str):
    duration = 0
    if video_duration_text:
        time_parts = video_duration_text.split(':')
        if len(time_parts) == 2:
            minute, second = time_parts
            duration = int(minute) * 60 + int(second)
        elif len(time_parts) == 3:
            hour, minute, second = time_parts
            duration = int(hour) * 3600 + int(minute) * 60 + int(second)
        else:
            duration = 0
    return duration

_regexs = {}

def get_info(html, regexs, allow_repeat=True, fetch_one=False, split=None):
    regexs = isinstance(regexs, str) and [regexs] or regexs

    infos = []
    for regex in regexs:
        if regex == "":
            continue

        if regex not in _regexs.keys():
            _regexs[regex] = re.compile(regex, re.S)

        if fetch_one:
            infos = _regexs[regex].search(html)
            if infos:
                infos = infos.groups()
            else:
                continue
        else:
            infos = _regexs[regex].findall(str(html))

        if len(infos) > 0:
            # print(regex)
            break

    if fetch_one:
        infos = infos if infos else ("",)
        return infos if len(infos) > 1 else infos[0]
    else:
        infos = allow_repeat and infos or sorted(set(infos), key=infos.index)
        infos = split.join(infos) if split else infos
        return infos

def transform_lower_num(data_str: str):
    num_map = {
        "一": "1",
        "二": "2",
        "两": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "七": "7",
        "八": "8",
        "九": "9",
        "十": "0",
    }
    pattern = f'[{"|".join(num_map.keys())}|零]'
    res = re.search(pattern, data_str)
    if not res:
        #  如果字符串中没有包含中文数字 不做处理 直接返回
        return data_str

    data_str = data_str.replace("0", "零")
    for n in num_map:
        data_str = data_str.replace(n, num_map[n])

    re_data_str = re.findall(r"\d+", data_str)
    for i in re_data_str:
        if len(i) == 3:
            new_i = i.replace("0", "")
            data_str = data_str.replace(i, new_i, 1)
        elif len(i) == 4:
            new_i = i.replace("10", "")
            data_str = data_str.replace(i, new_i, 1)
        elif len(i) == 2 and int(i) < 10:
            new_i = int(i) + 10
            data_str = data_str.replace(i, str(new_i), 1)
        elif len(i) == 1 and int(i) == 0:
            new_i = int(i) + 10
            data_str = data_str.replace(i, str(new_i), 1)

    return data_str.replace("零", "0")

@run_safe_model("format_date")
def format_date(date, old_format="", new_format="%Y-%m-%d %H:%M:%S"):
    """
    @summary: 格式化日期格式
    ---------
    @param date: 日期 eg：2017年4月17日 3时27分12秒
    @param old_format: 原来的日期格式 如 '%Y年%m月%d日 %H时%M分%S秒'
        %y 两位数的年份表示（00-99）
        %Y 四位数的年份表示（000-9999）
        %m 月份（01-12）
        %d 月内中的一天（0-31）
        %H 24小时制小时数（0-23）
        %I 12小时制小时数（01-12）
        %M 分钟数（00-59）
        %S 秒（00-59）
    @param new_format: 输出的日期格式
    ---------
    @result: 格式化后的日期，类型为字符串 如2017-4-17 03:27:12
    """
    if not date:
        return ""

    if not old_format:
        regex = r"(\d+)"
        numbers = get_info(date, regex, allow_repeat=True)
        formats = ["%Y", "%m", "%d", "%H", "%M", "%S"]
        old_format = date
        for i, number in enumerate(numbers[:6]):
            if i == 0 and len(number) == 2:  # 年份可能是两位 用小%y
                old_format = old_format.replace(
                    number, formats[i].lower(), 1
                )  # 替换一次 '2017年11月30日 11:49' 防止替换11月时，替换11小时
            else:
                old_format = old_format.replace(number, formats[i], 1)  # 替换一次

    try:
        date_obj = datetime.strptime(date, old_format)
        if "T" in date and "Z" in date:
            date_obj += timedelta(hours=8)
            date_str = date_obj.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = date_obj.strftime(new_format)

    except Exception as e:
        logger.error("日期格式化出错，old_format = %s 不符合 %s 格式" % (old_format, date))
        date_str = date

    return date_str

@run_safe_model("format_time")
def format_time(release_time, date_format="%Y-%m-%d %H:%M:%S"):
    """
    >>> format_time("2个月前")
    '2021-08-15 16:24:21'
    >>> format_time("2月前")
    '2021-08-15 16:24:36'
    >>> format_time("6 days ago")
    '2021-08-15 16:24:36'
    >>> format_time("2 years ago")
    '2021-08-15 16:24:36'
    >>> format_time("yesterday")
    '2021-08-15 16:24:36'
    """
    release_time = transform_lower_num(release_time)
    release_time = release_time.replace("日", "天").replace("/", "-")

    # 处理中文时间格式
    if "年前" in release_time:
        years = re.compile(r"(\d+)\s*年前").findall(release_time)
        years_ago = datetime.now() - timedelta(
            days=int(years[0]) * 365
        )
        release_time = years_ago.strftime("%Y-%m-%d %H:%M:%S")

    elif "月前" in release_time:
        months = re.compile(r"(\d+)[\s个]*月前").findall(release_time)
        months_ago = datetime.now() - timedelta(
            days=int(months[0]) * 30
        )
        release_time = months_ago.strftime("%Y-%m-%d %H:%M:%S")

    elif "周前" in release_time:
        weeks = re.compile(r"(\d+)\s*周前").findall(release_time)
        weeks_ago = datetime.now() - timedelta(days=int(weeks[0]) * 7)
        release_time = weeks_ago.strftime("%Y-%m-%d %H:%M:%S")

    elif "天前" in release_time:
        ndays = re.compile(r"(\d+)\s*天前").findall(release_time)
        days_ago = datetime.now() - timedelta(days=int(ndays[0]))
        release_time = days_ago.strftime("%Y-%m-%d %H:%M:%S")

    elif "小时前" in release_time:
        nhours = re.compile(r"(\d+)\s*小时前").findall(release_time)
        hours_ago = datetime.now() - timedelta(hours=int(nhours[0]))
        release_time = hours_ago.strftime("%Y-%m-%d %H:%M:%S")

    elif "分钟前" in release_time:
        nminutes = re.compile(r"(\d+)\s*分钟前").findall(release_time)
        minutes_ago = datetime.now() - timedelta(
            minutes=int(nminutes[0])
        )
        release_time = minutes_ago.strftime("%Y-%m-%d %H:%M:%S")

    # 处理英文时间格式
    elif re.search(r"\b(years?|months?|weeks?|days?|hours?|minutes?)\s+ago\b", release_time, re.IGNORECASE):
        # 处理 years ago
        years = re.compile(r"(\d+)\s*years?\s+ago", re.IGNORECASE).findall(release_time)
        if years:
            years_ago = datetime.now() - timedelta(days=int(years[0]) * 365)
            release_time = years_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理 months ago
        elif re.search(r"(\d+)\s*months?\s+ago", release_time, re.IGNORECASE):
            months = re.compile(r"(\d+)\s*months?\s+ago", re.IGNORECASE).findall(release_time)
            months_ago = datetime.now() - timedelta(days=int(months[0]) * 30)
            release_time = months_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理 weeks ago
        elif re.search(r"(\d+)\s*weeks?\s+ago", release_time, re.IGNORECASE):
            weeks = re.compile(r"(\d+)\s*weeks?\s+ago", re.IGNORECASE).findall(release_time)
            weeks_ago = datetime.now() - timedelta(days=int(weeks[0]) * 7)
            release_time = weeks_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理 days ago
        elif re.search(r"(\d+)\s*days?\s+ago", release_time, re.IGNORECASE):
            days = re.compile(r"(\d+)\s*days?\s+ago", re.IGNORECASE).findall(release_time)
            days_ago = datetime.now() - timedelta(days=int(days[0]))
            release_time = days_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理 hours ago
        elif re.search(r"(\d+)\s*hours?\s+ago", release_time, re.IGNORECASE):
            hours = re.compile(r"(\d+)\s*hours?\s+ago", re.IGNORECASE).findall(release_time)
            hours_ago = datetime.now() - timedelta(hours=int(hours[0]))
            release_time = hours_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # 处理 minutes ago
        elif re.search(r"(\d+)\s*minutes?\s+ago", release_time, re.IGNORECASE):
            minutes = re.compile(r"(\d+)\s*minutes?\s+ago", re.IGNORECASE).findall(release_time)
            minutes_ago = datetime.now() - timedelta(minutes=int(minutes[0]))
            release_time = minutes_ago.strftime("%Y-%m-%d %H:%M:%S")

    # 处理中文相对日期词汇
    elif "前天" in release_time:
        today = datetime.now().date()
        yesterday = today - timedelta(days=2)
        release_time = release_time.replace("前天", str(yesterday))

    elif "昨天" in release_time:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        release_time = release_time.replace("昨天", str(yesterday))

    elif "今天" in release_time:
        release_time = release_time.replace("今天", get_current_date())

    elif "刚刚" in release_time:
        release_time = get_current_time()

    # 处理英文相对日期词汇
    elif re.search(r"\bday before yesterday\b", release_time, re.IGNORECASE):
        today = datetime.now().date()
        day_before_yesterday = today - timedelta(days=2)
        release_time = release_time.replace(release_time, str(day_before_yesterday))

    elif re.search(r"\byesterday\b", release_time, re.IGNORECASE):
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        release_time = release_time.replace(release_time, str(yesterday))

    elif re.search(r"\btoday\b", release_time, re.IGNORECASE):
        release_time = release_time.replace(release_time, get_current_date())

    elif re.search(r"\b(just now|recently)\b", release_time, re.IGNORECASE):
        release_time = get_current_time()

    elif re.search(r"^\d\d:\d\d", release_time):
        release_time = get_current_date() + " " + release_time

    elif not re.compile(r"\d{4}").findall(release_time):
        month = re.compile(r"\d{1,2}").findall(release_time)
        current_date = get_current_date()
        current_year = current_date.split('-')[0]
        current_month = current_date.split('-')[1]
        if month and int(month[0]) <= int(current_month):
            release_time = current_year + "-" + release_time
        else:
            release_time = str(int(current_year) - 1) + "-" + release_time

    # 把日和小时粘在一起的拆开
    template = re.compile(r"(\d{4}-\d{1,2}-\d{2})(\d{1,2})")
    release_time = re.sub(template, r"\1 \2", release_time)
    release_time = format_date(release_time, new_format=date_format)

    return release_time

if __name__ == '__main__':
    # 示例用法
    # _rfc2822_time = "Sat Dec 23 17:12:54 +0800 2023"
    # print(rfc2822_to_china_datetime(_rfc2822_time))
    print(format_time("1小时前"))
