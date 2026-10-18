# -*- coding: utf-8 -*-
# @Author : 若
# @Time : 2025/4/21 上午11:16
import random
import re
import sys
from typing import Dict, List, Optional, Tuple, Union
import urllib
from zlib import crc32


def convert_string_to_date(date_str: str) -> str:
    # 确保输入字符串长度为8
    if len(date_str) != 8:
        raise ValueError("日期字符串必须为8位，格式为YYYYMMDD")

    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

def cookie_str_to_dict(cookies_str: str) -> dict:
    """将cookie字符串转换为字典"""
    if not cookies_str:
        raise Exception("No cookies available")
    cookie_dict = {}
    for c in cookies_str.split(';'):
        name, value = c.split('=',maxsplit=1)
        cookie_dict[name.strip()] = value.strip()
    return cookie_dict


def params_str_to_dict(params_str: str) -> dict:
    """将参数字符串转换为字典
    Args:
        params_str: 参数字符串，格式为key1=value1&key2=value2
        
    Returns:
        参数字典
    """
    if not params_str:
        return {}
    
    params_dict = {}
    for param in params_str.split('&'):
        if '=' in param:
            key, value = param.split('=', 1)
            params_dict[key] = value
    return params_dict


def dict_to_params_str(params_dict: dict) -> str:
    """将字典转换为参数字符串
    Args:
        params_dict: 参数字典
        
    Returns:
        参数字符串
    """
    if not params_dict:
        return ""
    return '&'.join([f"{k}={v}" for k, v in params_dict.items()])


def extract_text_from_html(html: str) -> str:
    """
    解析 HTML，提取并返回其中的纯文本内容，去除所有 HTML 标签以及 script 和 style 标签中的内容。
    参数:
        html (str): 包含 HTML 内容的字符串。
    返回:
        str: 提取后的纯文本字符串。如果输入为空，则返回空字符串。
    注意:
        - 使用正则表达式匹配并移除 script、style 标签及其内容，然后移除所有其它标签。
    """
    if not html:
        return ""

    # Remove script and style elements
    clean_html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
    # Remove all other tags
    clean_text = re.sub(r'<[^>]+>', '', clean_html).strip()
    return clean_text
        

def convert_cookies(cookies: Optional[List]) -> Tuple[str, Dict]:
    if not cookies:
        return "", {}
    cookies_str = ";".join([f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies])
    cookie_dict = dict()
    for cookie in cookies:
        cookie_dict[cookie.get('name')] = cookie.get('value')
    return cookies_str, cookie_dict

def extract_url_params_to_dict(url: str) -> Dict:
    """Extract URL parameters to dict"""
    url_params_dict = dict()
    if not url:
        return url_params_dict
    parsed_url = urllib.parse.urlparse(url)
    url_params_dict = dict(urllib.parse.parse_qsl(parsed_url.query))
    return url_params_dict

def gen_random_str(randomlength: int) -> str:
    """
    根据传入长度产生随机字符串 (Generate a random string based on the given length)

    Args:
        randomlength (int): 需要生成的随机字符串的长度 (The length of the random string to be generated)

    Returns:
        str: 生成的随机字符串 (The generated random string)
    """

    base_str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(base_str) for _ in range(randomlength))

def extract_valid_urls(inputs: Union[str, List[str]]) -> Union[str, List[str], None]:
    """从输入中提取有效的URL (Extract valid URLs from input)

    Args:
        inputs (Union[str, list[str]]): 输入的字符串或字符串列表 (Input string or list of strings)

    Returns:
        Union[str, list[str]]: 提取出的有效URL或URL列表 (Extracted valid URL or list of URLs)
    """
    url_pattern = re.compile(r"https?://\S+")

    # 如果输入是单个字符串
    if isinstance(inputs, str):
        match = url_pattern.search(inputs)
        return match.group(0) if match else None

    # 如果输入是字符串列表
    elif isinstance(inputs, list):
        valid_urls = []

        for input_str in inputs:
            matches = url_pattern.findall(input_str)
            if matches:
                valid_urls.extend(matches)

        return valid_urls

def split_filename(text: str, os_limit: dict) -> str:
    """
    根据操作系统的字符限制分割文件名，并用 '......' 代替。

    Args:
        text (str): 要计算的文本
        os_limit (dict): 操作系统的字符限制字典

    Returns:
        str: 分割后的文本
    """
    # 获取操作系统名称和文件名长度限制
    os_name = sys.platform
    filename_length_limit = os_limit.get(os_name, 200)

    # 计算中文字符长度（中文字符长度*3）
    chinese_length = sum(1 for char in text if "\u4e00" <= char <= "\u9fff") * 3
    # 计算英文字符长度
    english_length = sum(1 for char in text if char.isalpha())
    # 计算下划线数量
    num_underscores = text.count("_")

    # 计算总长度
    total_length = chinese_length + english_length + num_underscores

    # 如果总长度超过操作系统限制或手动设置的限制，则根据限制进行分割
    if total_length > filename_length_limit:
        split_index = min(total_length, filename_length_limit) // 2 - 6
        split_text = text[:split_index] + "......" + text[-split_index:]
        return split_text
    else:
        return text
    
    
def download_file(url: str, filename: str):
    import requests
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def generate_hash(value: str) -> str:
    """根据字符串生成唯一ID (使用CRC32，速度快且确定性)
    
    为什么不用Python内置hash()：
    - Python 3.3+ 默认启用hash随机化，每次启动进程后相同字符串可能产生不同hash值
    - 这会导致Bloom Filter去重失效
    
    CRC32优势：
    - 速度比MD5快5-10倍
    - 结果确定性，跨进程/跨会话保持一致
    - 返回8位hex字符串，足够用于去重场景
    """
    if not value:
        return ""

    # CRC32返回32位整数，转为8位hex字符串
    return format(crc32(value.encode('utf-8')) & 0xffffffff, '08x')