# -*- coding:utf-8 -*-
import json
import os
import sys
import time
import random
import logging
from multiprocessing import Queue, Process
import queue
import requests
from bs4 import BeautifulSoup


class InstagramScraper:

    BASE_URL = 'https://www.instagram.com/{0}'

    QUERY_URL = 'https://www.instagram.com/graphql/query/' \
                '?query_id=17888483320059182&variables={"id":"%s","first":%d,"after":"%s"}'

    VIDEO_JSON = 'https://www.instagram.com/p/{short_code}/?__a=1'

    HEADERS = {
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/59.0.3071.115 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'DNT': '1',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-TW,zh;q=0.8,en-US;q=0.6,en;q=0.4,zh-CN;q=0.2',
    }

    PROXIES = {
        'http': '127.0.0.1:1080',
        'https': '127.0.0.1:1080'
    }

    logging.basicConfig(filename='logger.log')

    def __init__(self, user_name, path, max_num, enable_video, thread, use_proxy):
        self.url = self.BASE_URL.format(user_name)
        self.path = path
        self.max_num = max_num
        self.enable_video = enable_video
        # make dirs
        self.profile_path = os.path.join(path, 'UserProfile')
        if os.path.isdir(path):
            self.path = path
        else:
            os.makedirs(path)
            os.mkdir(self.profile_path)
        # set proxy
        if not use_proxy:
            self.proxies = {}
        else:
            self.proxies = self.PROXIES

        # multiprocessing
        self.thread = thread
        self.queue = Queue()
        self.downloading = True

        # get/update user profile
        self.count = Queue()
        self.profile = {}
        if os.path.isfile(os.path.join(self.profile_path, 'UserProfile.json')):
            self.profile = self.read_profile()
        self.last_start_url = self.profile.get('LastStartUrl', '')
        self.last_end_url = self.profile.get('LastEndUrl', '')
        self.get_profile()
        self.write_profile(self.profile)

        if len(os.listdir(self.path)) > 200:
            self.query_num = 24
        else:
            self.query_num = 12

    def get_profile(self):
        """Download profile and set first query"""
        self.stop_parsing = False
        r = requests.get(self.url, headers=self.HEADERS, proxies=self.proxies)
        if r.status_code == 200:
            r.encoding = 'utf8'
            self.cookies = r.cookies
            soup = BeautifulSoup(r.text, 'lxml')
            target = soup.body.findAll('script')[0]
            json_str = target.text[:-1].split('window._sharedData = ')[-1]
            self.profile = json.loads(json_str)['entry_data']['ProfilePage'][0]['user']
            media = self.profile.get('media', {})
            query = [{'url': node.get('display_src'),
                      'is_video': node.get('is_video', False),
                      'short_code': node.get('code', ''),
                      'time': int(node.get('date', time.time())),
                      'caption': node.get('caption', time.time())} for node in media.get('nodes', [{}])]
            if self.enable_video:
                vedio_targets = [self.get_vedio_target(target) for target in query if target['is_video']]
                query.extend(vedio_targets)
            for target in query:
                self.queue.put(target)
                if self.last_end_url == -1:
                    if self.last_start_url == target['url']:
                        self.stop_parsing = True
                        break
            self.last_start_url = query[0]['url']
            self.end_cursor = media.get('page_info').get('end_cursor')
            self.has_next_page = media.get('page_info').get('has_next_page')
        else:
            print('Unknown error! Try to restart...')
            time.sleep(1)
            return self.get_profile()

    def write_profile(self, data):
        """Save profile to path/UserProfile/UserProfile.json"""
        with open(os.path.join(self.profile_path, 'UserProfile.json'), 'w') as fp:
            user_name = data.get('username', '')
            full_name = data.get('full_name', '')
            biography = data.get('biography', '')
            follower = data.get('followed_by', {}).get('count', '')
            follows = data.get('follows', {}).get('count', '')
            self.uid = data.get('id', '')
            # last_update = data.get('media', {}).get('nodes', [{}])[0].get('id', '')
            profile = {
                'UserName': user_name,
                'FullName': full_name,
                'Biography': biography,
                'Follower': follower,
                'Follows': follows,
                'ID': self.uid
            }
            last_profile = self.read_profile()
            last_profile.update(profile)
            self.profile = last_profile
            profile_str = json.dumps(last_profile)
            fp.write(profile_str)

    def read_profile(self):
        """Dump dict from UserProfile.json"""
        with open(os.path.join(self.profile_path, 'UserProfile.json'), 'r', encoding='utf-8') as fp:
            if fp.read():
                with open(os.path.join(self.profile_path, 'UserProfile.json'), 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}

    def log_cursor(self):
        profile = self.read_profile()
        profile['LastStartUrl'] = self.last_start_url
        profile['LastEndUrl'] = self.last_end_url
        profile_str = json.dumps(profile)
        with open(os.path.join(self.profile_path, 'UserProfile.json'), 'w') as fp:
            fp.write(profile_str)

    def parse_json_1(self, text):
        data = json.loads(text).get('data').get('user').get('edge_owner_to_timeline_media')
        self.end_cursor = data.get('page_info').get('end_cursor')
        self.has_next_page = data.get('page_info').get('has_next_page')
        query = [
            {'url': node.get('node').get('display_url', ''),
             'is_video': node.get('node').get('is_video', False),
             'short_code': node.get('node').get('shortcode', ''),
             'time': int(node.get('node').get('taken_at_timestamp', time.time())),
             'caption': node.get('node').get('edge_media_to_caption').get('edges', [{}])[0].get('node').get('text', time.time())
             } for node in data.get('edges')]
        return query

    def parse_json_2(self, text):
        return json.loads(text).get('graphql').get('shortcode_media').get('video_url')

    def get_vedio_target(self, target):
        """Get vedio target from image target"""
        json_url = self.VIDEO_JSON.format(short_code=target['short_code'])
        res = self.request(json_url)
        vedio_tar = target
        vedio_tar['url'] = self.parse_json_2(res.text)
        return vedio_tar

    def request(self, url):
        return requests.get(url, cookies=self.cookies, headers=self.HEADERS, proxies=self.proxies)

    def get_next_query(self):
        """Get more query"""
        while self.count.qsize() <= self.max_num:
            try:
                if self.has_next_page and not self.stop_parsing:
                    url = self.QUERY_URL % (self.uid, self.query_num, self.end_cursor)
                    response = self.request(url)
                    query = self.parse_json_1(response.text)
                    for target in query:
                        if self.count.qsize() < self.max_num:
                            if self.enable_video and target['is_video']:
                                # 如果是视频则同时将视频加入队列
                                self.queue.put(self.get_vedio_target(target))
                            self.queue.put(target)
                            # 如果上次下载到了用户的最后一张照片，则这次只下载到上次开始的地方
                            if self.profile.get('LastEndUrl', '') == -1:
                                if target['url'] == self.profile.get('LastStartUrl', ''):
                                    while True:
                                        if self.queue.empty():
                                            self.last_end_url = -1
                                            self.stop()
                                            break
                                        time.sleep(5)

                            self.last_end_url = target['url']
                elif self.queue.empty():
                    self.last_end_url = -1
                    self.stop()
                    break
                else:
                    time.sleep(1)
            except KeyboardInterrupt:
                sys.exit(1)
            except Exception as e:
                logging.warning(e)
                pass
        self.stop()

    def download(self):
        """Download target in queue"""
        while self.count.qsize() <= self.max_num:
            try:
                target = self.queue.get(True, 1)
                if target['url']:
                    filename = target.get('caption')[:100] + '.' + target['url'].split('.')[-1]
                    for r in '\\/:*?"<>|\n':
                        filename = filename.replace(r, '_')
                    filepath = os.path.join(self.path, filename)
                    if not os.path.isfile(filepath):
                        response = self.request(target['url'])
                        if response.status_code == 200:
                            with open(filepath, 'wb') as fp:
                                fp.write(response.content)
                            os.utime(filepath, (target['time'], target['time']))
                            self.count.put(target['url'])
                        time.sleep(random.randrange(10, 40) / 10)
            except queue.Empty:
                time.sleep(3)
                continue
            except KeyboardInterrupt:
                sys.exit(1)
            except Exception as e:
                logging.warning(e)
                pass

    def run(self):
        try:
            self.downloaders = []
            get_query = Process(target=self.get_next_query)
            for i in range(self.thread):
                self.downloaders.append(Process(target=self.download))
            get_query.start()
            for downloader in self.downloaders:
                downloader.start()
            get_query.join()
            for downloader in self.downloaders:
                downloader.join()
        except Exception as e:
            logging.warning(e)
            sys.exit(1)

    def stop(self):
        self.log_cursor()
        print('Got %s new images.' % self.count.qsize())
        print('Now you can close me.')


if __name__ == '__main__':
    # 命令行参数解析
    import optparse
    parser = optparse.OptionParser()
    parser.add_option('--user', '-u', default='', help='User name to download')
    parser.add_option('--path', '-p', default='', help='Path to save images(default: ./<user>')
    parser.add_option('--num', '-n', default=100, help='Max number to download')
    parser.add_option('--video', '-v', action='store_true', default=False, help='Enable downloading video(default: off)')
    parser.add_option('--thread', '-t', default=4, help='Download thread(s).(Do not set it over 10!)')
    parser.add_option('--proxy', '-P', action='store_true', default=False,
                      help='Use proxy(default: off AND default proxy: http://127.0.0.1:1080)')
    opts, args = parser.parse_args()
    if not opts.user:
        print('Please set user to scrap!')
        parser.print_help()
        sys.exit(2)
    if not opts.path:
        opts.path = './' + opts.user
    if int(opts.thread) > 20:
        opts.thread = 20

    scraper = InstagramScraper(user_name=opts.user, path=opts.path, max_num=int(opts.num), enable_video=opts.video,
                               thread=int(opts.thread), use_proxy=opts.proxy)

    # change encode if on Windows
    import platform
    if platform.system() == 'Windows':
        os.system('chcp 65001')
        # import io
        # sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

    try:
        print('''
    User info:
        UserName: {0}
        FullName: {1}
        Biography: {2}
        Follower: {3}
        Follows: {4}
        '''.format(scraper.profile['UserName'],
                   scraper.profile['FullName'],
                   scraper.profile['Biography'],
                   scraper.profile['Follower'],
                   scraper.profile['Follows'],))
    except UnicodeEncodeError as e:
        logging.warning(e)
        pass

    print('''
    Scrap info:
        Path to save: {0}
        Max download numbers: {1}
        Download video: {2}
        Downloader thread: {3}
        User proxy: {4}
    '''.format(opts.path, opts.num, opts.video, opts.thread, opts.proxy))

    scraper.run()
