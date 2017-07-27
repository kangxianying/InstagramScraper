# InstagramScraper

Usage: scraper.py [options]

Options:
  -h, --help            show this help message and exit                     | 帮助信息
  -u USER, --user=USER  User name to download                               | 设置抓取的用户名
  -p PATH, --path=PATH  Path to save images(default: ./<user>               | 保存路径
  -n NUM, --num=NUM     Max number to download(set -1 to download all)      | 设置下载数量
  -t THREAD, --thread=THREAD
                        Download thread(s).(Do not set it over 10!)         | 下载进程数
  -P, --proxy           Use proxy(default proxy: http://127.0.0.1:1080)     | 是否使用代理
