# -*- coding: utf-8 -*-
"""
00_fetch_data.py — 补齐 Lending Club 原始数据（免登录直链）

背景：Lending Club 官网公布的 LoanStats 文件是【按季度/半年切分】的，
     不是一个大文件。想画 vintage 账龄曲线，必须把 2007–2018 的整条
     队列序列凑齐，所以这里一次性把全部 16 个文件下下来。

文件名规律（来自 LC 官网下载页）：
    2007–2011  LoanStats3a.csv.zip     ← 半年/多年混合，跨年
    2012–2013  LoanStats3b.csv.zip
    2014       LoanStats3c.csv.zip
    2015       LoanStats3d.csv.zip
    2016–2018  LoanStats_YYYYQn.csv.zip （每季一个，共 12 个）

为什么用直链而不是 Kaggle：直链免登录、可脚本化、可重跑；
Kaggle 那个 accepted_2007_to_2018Q4.csv 是同一批数据的合并版，但要登录，
而且体积 1.6GB 全塞一个文件，反而不如分批下载好管。

用法：
    python code/00_fetch_data.py          只下缺的
    python code/00_fetch_data.py --check  只探测链接通不通，不下载

产物：data/raw/LoanStats*.csv.zip   （原始文件只读，解压在 01_build_loans.py 里做）
"""
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

RAW_DIR = db.path('data', 'raw')
BASE_URL = 'https://resources.lendingclub.com/'

# 全部 16 个文件。3a/3b/3c/3d 是 LC 早期的分段命名，2016 起改成按季度。
FILES = [
    'LoanStats3a.csv.zip',       # 2007-2011
    'LoanStats3b.csv.zip',       # 2012-2013
    'LoanStats3c.csv.zip',       # 2014
    'LoanStats3d.csv.zip',       # 2015
    'LoanStats_2016Q1.csv.zip',
    'LoanStats_2016Q2.csv.zip',
    'LoanStats_2016Q3.csv.zip',
    'LoanStats_2016Q4.csv.zip',
    'LoanStats_2017Q1.csv.zip',
    'LoanStats_2017Q2.csv.zip',
    'LoanStats_2017Q3.csv.zip',
    'LoanStats_2017Q4.csv.zip',
    'LoanStats_2018Q1.csv.zip',
    'LoanStats_2018Q2.csv.zip',
    'LoanStats_2018Q3.csv.zip',
    'LoanStats_2018Q4.csv.zip',
]

WORKERS = 5          # 并发数。实测单连接慢，并发能明显缩短总时长
TIMEOUT = 60
RETRY = 3


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def is_good_zip(path):
    """已存在且是完整 zip 才跳过。半截文件（之前下崩的）会被判为坏的，重下。"""
    if not os.path.exists(path):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.testzip() is None
    except Exception:
        return False


def fetch(name):
    """下单个文件。返回 (文件名, 结果文字, 字节数)。"""
    dst = os.path.join(RAW_DIR, name)
    if is_good_zip(dst):
        return name, '已存在', os.path.getsize(dst)

    url = BASE_URL + name
    last_err = None
    for attempt in range(1, RETRY + 1):
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urlopen(req, timeout=TIMEOUT) as resp:
                data = resp.read()
            if len(data) < 1000:            # 几百字节的一定是错误页不是数据
                raise ValueError(f'响应只有 {len(data)} 字节，像错误页')
            # 先写临时文件再改名：中途崩了不会留下一个看着像完整的半截文件
            tmp = dst + '.part'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, dst)
            return name, '下载完成', len(data)
        except Exception as e:
            last_err = e
            if attempt < RETRY:
                time.sleep(2 * attempt)
    return name, f'失败：{last_err}', 0


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    check_only = '--check' in sys.argv

    log(f'目标目录 {RAW_DIR}')
    log(f'待处理 {len(FILES)} 个文件，并发 {WORKERS}'
        + ('（只探测不下载）' if check_only else ''))

    t0 = time.time()
    todo = [f for f in FILES if not is_good_zip(os.path.join(RAW_DIR, f))]
    have = len(FILES) - len(todo)
    log(f'已有 {have} 个，待下 {len(todo)} 个')

    if check_only:
        for name in todo:
            try:
                req = Request(BASE_URL + name, method='HEAD',
                              headers={'User-Agent': 'Mozilla/5.0'})
                with urlopen(req, timeout=TIMEOUT) as resp:
                    size = resp.headers.get('Content-Length')
                    print(f'  {name:<32s} {resp.status}  '
                          f'{int(size)/1048576:.1f} MB' if size else f'  {name} {resp.status}')
            except Exception as e:
                print(f'  {name:<32s} 不可用：{e}')
        return

    failed = []
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch, name): name for name in todo}
        for fut in as_completed(futs):
            name, result, nbytes = fut.result()
            done += 1
            if nbytes == 0:
                failed.append(name)
            log(f'  [{done}/{len(todo)}] {name:<32s} {result}'
                + (f'（{nbytes/1048576:.1f} MB）' if nbytes else ''))

    total = sum(os.path.getsize(os.path.join(RAW_DIR, f))
                for f in FILES if os.path.exists(os.path.join(RAW_DIR, f)))
    log(f'完成：{len(FILES)-len(failed)}/{len(FILES)} 个，'
        f'合计 {total/1048576:.1f} MB，耗时 {(time.time()-t0)/60:.1f} 分钟')
    if failed:
        log('以下文件没下成，重跑本脚本会自动补：')
        for f in failed:
            log(f'    {f}')


if __name__ == '__main__':
    main()
