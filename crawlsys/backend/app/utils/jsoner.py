def SearchJsonKey(sjson, key, find_all=False):
    """
    递归查找JSON结构中指定key的值
    
    Args:
        sjson: JSON数据结构 (dict, list, 或其他类型)
        key: 要查找的键名 (str)
        find_all: 是否返回所有匹配的值 (bool), 默认False只返回第一个匹配
    
    Returns:
        如果find_all=False: 返回第一个匹配的值，未找到返回None
        如果find_all=True: 返回所有匹配值的列表
    """
    if find_all:
        results = []
        _search_all_keys(sjson, key, results)
        return results
    else:
        return _search_first_key(sjson, key)


def _search_first_key(sjson, key):
    """查找第一个匹配的key值"""
    if isinstance(sjson, dict):
        # 直接查找当前层级
        if key in sjson:
            return sjson[key]
        
        # 递归查找子层级
        for value in sjson.values():
            result = _search_first_key(value, key)
            if result is not None:
                return result
    
    elif isinstance(sjson, list):
        # 遍历列表中的每个元素
        for item in sjson:
            result = _search_first_key(item, key)
            if result is not None:
                return result
    
    return None


def _search_all_keys(sjson, key, results):
    """查找所有匹配的key值"""
    if isinstance(sjson, dict):
        # 检查当前层级
        if key in sjson:
            results.append(sjson[key])
        
        # 递归查找子层级
        for value in sjson.values():
            _search_all_keys(value, key, results)
    
    elif isinstance(sjson, list):
        # 遍历列表中的每个元素
        for item in sjson:
            _search_all_keys(item, key, results)


def SearchJsonKeyPath(sjson, key):
    """
    查找JSON结构中指定key的路径
    
    Args:
        sjson: JSON数据结构
        key: 要查找的键名
    
    Returns:
        包含所有匹配路径的列表，每个路径是键名列表
    """
    paths = []
    _find_key_paths(sjson, key, [], paths)
    return paths


def _find_key_paths(sjson, target_key, current_path, paths):
    """递归查找key的路径"""
    if isinstance(sjson, dict):
        for k, v in sjson.items():
            new_path = current_path + [k]
            if k == target_key:
                paths.append(new_path)
            _find_key_paths(v, target_key, new_path, paths)
    
    elif isinstance(sjson, list):
        for i, item in enumerate(sjson):
            new_path = current_path + [f"[{i}]"]
            _find_key_paths(item, target_key, new_path, paths)