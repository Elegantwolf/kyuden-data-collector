"""CSV/JSON export."""
import json
import logging
from datetime import date, datetime
import pandas as pd

logger = logging.getLogger(__name__)

def save_dataset(data, prefix, ext):
    if not data:
        logger.warning(f"{prefix} 没有数据可保存")
        return None
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{prefix}_{ts}.{ext}"
    if ext == 'csv':
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
    else:
        json_data = []
        for item in data:
            obj = item.copy()
            if isinstance(obj.get('date'), date):
                obj['date'] = obj['date'].isoformat()
            if isinstance(obj.get('timestamp'), datetime):
                obj['timestamp'] = obj['timestamp'].isoformat()
            json_data.append(obj)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    logger.info(f"保存文件: {filename}")
    return filename

def save_results(daily=None, hourly=None, save_format='both'):
    if save_format not in ('csv', 'json', 'both', 'none'):
        raise ValueError("未知导出格式")
    results = {}
    # 新增：支持 'none' 以关闭保存
    if save_format in ['csv','both']:
        if daily is not None:
            results['daily_csv'] = save_dataset(daily, 'kyuden_daily', 'csv')
        if hourly is not None:
            results['hourly_csv'] = save_dataset(hourly, 'kyuden_hourly', 'csv')
    if save_format in ['json','both']:
        if daily is not None:
            results['daily_json'] = save_dataset(daily, 'kyuden_daily', 'json')
        if hourly is not None:
            results['hourly_json'] = save_dataset(hourly, 'kyuden_hourly', 'json')
    if save_format == 'none':
        logger.info("已关闭文件保存（save_format=none）")
    return results
