'''
MIT License
Copyright (c) 2026 Josh Schiavone

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

__version__ = 4

import sys
sys.dont_write_bytecode = True

import nltk

import requests
from bs4 import BeautifulSoup
import os
import time
import argparse
import random
import re
import json
import socket
import hashlib

from headers.agents import Headers
from banner.banner import Banner

from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.probability import FreqDist
from textblob import TextBlob

notice = '''
Note: 
    This tool is not to be used for illegal purposes.
    The author is not responsible for any misuse of Darkdump.
    May God bless you all.
    https://joshschiavone.com - https://github.com/josh0xA
'''

class Colors:
    W = '\033[0m'  # white 
    R = '\033[31m'  # red
    G = '\033[32m'  # green
    O = '\033[33m'  # orange
    B = '\033[34m'  # blue
    P = '\033[35m'  # purple
    C = '\033[36m'  # cyan
    GR = '\033[37m'  # gray
    BOLD = '\033[1m'
    END = '\033[0m'

class ResultSaver:
    """
    Collects scan results during a crawl and writes them to disk in the
    format inferred from the output filename extension.

    Supported formats
    -----------------
    .json  -- structured JSON array, one object per result
    .csv   -- RFC 4180 CSV with a header row
    .txt   -- human-readable plain-text report (default / fallback)

    Usage
    -----
    saver = ResultSaver("results.json", query="hacking", engine="ahmia")
    saver.add(title, description, site_url, scrape_data=None)
    saver.save()           # writes the file
    saver.print_summary()  # prints confirmation line to stdout
    """

    def __init__(self, filepath: str, query: str = '', engine: str = ''):
        self.filepath = filepath
        self.query = query
        self.engine = engine
        self.records: list = []
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.json':
            self.fmt = 'json'
        elif ext == '.csv':
            self.fmt = 'csv'
        else:
            self.fmt = 'txt'

    def add(self, title: str, description: str, site_url: str,
            scrape_data: dict = None):
        """Append one result. scrape_data is the dict returned by _scrape_site."""
        record = {
            'title': title,
            'description': description,
            'url': site_url,
        }
        if scrape_data:
            record.update(scrape_data)
        self.records.append(record)

    def save(self):
        """Write all collected records to self.filepath."""
        if not self.records:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        try:
            if self.fmt == 'json':
                self._save_json()
            elif self.fmt == 'csv':
                self._save_csv()
            else:
                self._save_txt()
        except Exception as e:
            print(f"{Colors.BOLD + Colors.R}[Save Error] Could not write to "
                  f"\'{self.filepath}\': {e}{Colors.END}")

    def print_summary(self):
        """Print a confirmation line after saving."""
        if not self.records:
            return
        print(
            f"\n{Colors.BOLD + Colors.C}[ Saved {len(self.records)} result(s) "
            f"-> {os.path.abspath(self.filepath)} ]{Colors.END}"
        )

    def _save_json(self):
        payload = {
            'query': self.query,
            'engine': self.engine,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'result_count': len(self.records),
            'results': self.records,
        }
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _save_csv(self):
        import csv as _csv
        # Build a superset of all field names present across all records
        fieldnames = ['title', 'description', 'url']
        for r in self.records:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)

        with open(self.filepath, 'w', newline='', encoding='utf-8') as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for record in self.records:
                # Flatten list/dict values to strings for CSV compatibility
                flat = {}
                for k, v in record.items():
                    flat[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                writer.writerow(flat)

    def _save_txt(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write("Darkdump Scan Report\n")
            f.write("=" * 60 + "\n")
            f.write(f"Query   : {self.query}\n")
            f.write(f"Engine  : {self.engine}\n")
            f.write(f"Time    : {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Results : {len(self.records)}\n")
            f.write("=" * 60 + "\n\n")
            for idx, r in enumerate(self.records, start=1):
                f.write(f"[{idx}] {r.get('title', 'No title')}\n")
                f.write(f"    URL         : {r.get('url', '')}\n")
                f.write(f"    Description : {r.get('description', '')}\n")
                if 'metadata' in r:
                    f.write(f"    Metadata    : {json.dumps(r['metadata'])}\n")
                if 'links_count' in r:
                    f.write(f"    Links found : {r['links_count']}\n")
                if 'emails' in r:
                    emails = r['emails']
                    f.write(f"    Emails      : {', '.join(emails) if emails else 'None'}\n")
                if 'documents' in r:
                    docs = r['documents']
                    f.write(f"    Documents   : {', '.join(docs) if docs else 'None'}\n")
                if 'images_gallery' in r:
                    f.write(f"    Images      : {r['images_gallery']}\n")
                f.write("\n")


class Configuration:
    DARKDUMP_ERROR_CODE_STANDARD = -1
    DARKDUMP_SUCCESS_CODE_STANDARD = 0
    DARKDUMP_MIN_DATA_RETRIEVE_LENGTH = 1
    DARKDUMP_RUNNING = False

    DARKDUMP_OS_UNIX_LINUX = False
    DARKDUMP_OS_WIN32_64 = False
    DARKDUMP_OS_DARWIN = False

    DARKDUMP_REQUESTS_SUCCESS_CODE = 200
    DARKDUMP_PROXY = False
    DARKDUMP_TOR_RUNNING = False

    descriptions = []
    urls = []

    __socks5init__ = "socks5h://localhost:9050"

    # --- Search engine definitions ---
    # Each engine dict keys:
    #   'base'        : clearnet base URL for nonce fetching, or None
    #   'api'         : clearnet search URL template with {query} placeholder, or None
    #   'onion'       : .onion search URL template with {query} placeholder
    #   'tor_required': True = onion-only, Tor proxy is mandatory
    #   'filtered'    : True = engine actively screens out illegal/abusive content
    #   'result_tag'  : (tag, class) tuple for BeautifulSoup result item selection
    #   'needs_nonce' : whether a hidden CSRF nonce must be fetched from base first
    #   'parser'      : internal fetcher method name (maps to _fetch_<parser>)
    #
    # Engine overview
    # ---------------
    # ahmia    - Clearnet + Tor. Tor Project-endorsed since 2014. Strict CSAM/abuse
    #            filtering. Requires a hidden CSRF nonce fetched from the homepage.
    #
    # notevil    - Tor-only. Ahmia fork with partial content filtering (strips the
    #              most extreme material while keeping a broader index than Ahmia).
    #              Click-count ranking. Results are <li class="result"> elements.
    #
    # tordex     - Clearnet + Tor. UNFILTERED uncensored index. Uses .onion when
    #              proxy is active, clearnet (tordex.cc/search) otherwise.
    #              Results use .container h5 a selector.
    #
    # tor66      - Tor-only. UNFILTERED crawled index with category directory.
    #              Results parsed from <b> elements following the first <hr>.
    #
    # onionland  - Tor-only. Minimal filtering; indexes Tor, I2P, and clearnet.
    #              Results use .result-block .title a with redirect URL decoding.
    SEARCH_ENGINES = {
        'ahmia': {
            'name': 'Ahmia',
            'base': 'https://ahmia.fi',
            'api': 'https://ahmia.fi/search/?q={query}',
            'onion': 'http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={query}',
            'tor_required': False,
            'filtered': True,
            'result_tag': ('li', 'result'),
            'needs_nonce': True,
            'parser': 'ahmia',
        },
        'notevil': {
            'name': 'Not Evil',
            'base': None,
            'api': None,
            'onion': 'http://notevil2ebbr5xjww6nryjta7bycbriyi2vh7an3wcuovlznvobykmad.onion',
            'tor_required': True,
            'filtered': True,
            'result_tag': ('li', 'result'),
            'needs_nonce': False,
            'parser': 'notevil',
        },
        'tordex': {
            'name': 'TorDex',
            'base': 'https://tordex.cc',
            # Clearnet endpoint (used when proxy is off)
            'api': 'https://tordex.cc/search?query={query}',
            # Onion endpoint (used when proxy/Tor is enabled)
            'onion': 'http://tordexpmg4xy32rfp4ovnz7zq5ujoejwq2u26uxxtkscgo5u3losmeid.onion/search?query={query}',
            'tor_required': False,   # clearnet works without Tor; onion used when -p supplied
            'filtered': False,
            'result_tag': ('h5', None),
            'needs_nonce': False,
            'parser': 'tordex',
        },
        'tor66': {
            'name': 'Tor66',
            'base': None,
            'api': None,
            'onion': 'http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={query}&sorttype=rel',
            'tor_required': True,
            'filtered': False,
            'result_tag': ('li', None),
            'needs_nonce': False,
            'parser': 'tor66',
        },
        'onionland': {
            'name': 'OnionLand',
            'base': None,
            'api': None,
            # v3 onion address confirmed in OnionSearch core.py (2024)
            'onion': 'http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={query}&page=1',
            'tor_required': True,
            'filtered': False,  # Minimal content filtering
            'result_tag': ('div', 'result-block'),
            'needs_nonce': False,
            'parser': 'onionland',
        },
        'excavator': {
            'name': 'Excavator',
            'base': None,
            'api': None,
            'onion': 'http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion',
            'tor_required': True,
            'filtered': False,
            'result_tag': ('div', 'result'),
            'needs_nonce': False,
            'parser': 'excavator',
        },
    }

    VALID_ENGINES = list(SEARCH_ENGINES.keys())


class Platform(object):
    def __init__(self, execpltf):
        self.execpltf = execpltf

    def get_operating_system_descriptor(self):
        cfg = Configuration()
        clr = Colors()

        if self.execpltf:
            if sys.platform == "linux" or sys.platform == "linux2":
                cfg.DARKDUMP_OS_UNIX_LINUX = True
                print(clr.BOLD + clr.W + "Operating System: " + clr.G + sys.platform + clr.END)
            if sys.platform == "win64" or sys.platform == "win32":
                cfg.DARKDUMP_OS_WIN32_64 = True
                print(clr.BOLD + clr.W + "Operating System: " + clr.G + sys.platform + clr.END)
            if sys.platform == "darwin":
                cfg.DARKDUMP_OS_DARWIN = True
                print(clr.BOLD + clr.W + "Operating System: " + clr.G + sys.platform + clr.END)
        else:
            pass

    def clean_screen(self):
        if self.execpltf:
            if sys.platform in ("linux", "linux2", "darwin"):
                os.system('clear')
            else:
                os.system('cls')

    def check_tor_connection(self, proxy_config):
        test_url = 'https://check.torproject.org/api/ip'
        try:
            response = requests.get(test_url, proxies=proxy_config, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if data.get('IsTor', False):
                    print(f"{Colors.BOLD + Colors.G}Tor service is active.{Colors.END}")
                    print(f"{Colors.BOLD + Colors.P}Current IP Address via Tor: {Colors.END}{data.get('IP')}")
                    return True
            print(f"{Colors.BOLD + Colors.R}Connection successful but not through Tor.{Colors.END}")
            return False
        except Exception as e:
            print(f"{Colors.BOLD + Colors.R}Tor is inactive or not configured properly: {str(e)}{Colors.END}")
            return False


class AhmiaBlacklist:
    """
    Fetches and caches Ahmia's MD5-hashed .onion blacklist.
    The list is refreshed at most once per hour within a process.

    """
    BLACKLIST_URL = 'https://ahmia.fi/blacklist/banned/'
    TTL = 3600  # seconds

    _hashes: set = set()
    _fetched_at: float = 0.0

    @classmethod
    def load(cls) -> None:
        """Fetch the blacklist if the cache is stale."""
        if time.time() - cls._fetched_at < cls.TTL and cls._hashes:
            return
        try:
            resp = requests.get(cls.BLACKLIST_URL, timeout=15)
            resp.raise_for_status()
            cls._hashes = {line.strip() for line in resp.text.splitlines() if len(line.strip()) == 32}
            cls._fetched_at = time.time()
        except Exception:
            # If the fetch fails, keep whatever we had (or nothing).
            pass

    @classmethod
    def is_banned(cls, url: str) -> bool:
        """Return True if the .onion hostname of *url* is on the blacklist."""
        if not cls._hashes:
            return False
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ''
            if not host.endswith('.onion'):
                return False
            md5 = hashlib.md5(host.encode()).hexdigest()
            return md5 in cls._hashes
        except Exception:
            return False


class Darkdump(object):


    @staticmethod
    def _filter_blacklisted(results: list) -> list:
        """Remove any result whose .onion hostname is on Ahmia's blacklist."""
        AhmiaBlacklist.load()
        return [r for r in results if not AhmiaBlacklist.is_banned(r.get('site_url', ''))]

    def clean_text(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        text = re.sub(r'[\r\n]+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
        return text.strip()

    def extract_keywords(self, text):
        clean_text = self.clean_text(text)
        stop_words = set(stopwords.words('english'))
        word_tokens = word_tokenize(clean_text.lower())
        filtered_text = [w for w in word_tokens if w.isalnum() and w not in stop_words]
        freq_dist = FreqDist(filtered_text)
        return list(freq_dist)[:18]

    def analyze_text(self, text):
        words = word_tokenize(text)
        stop_words = set(stopwords.words('english'))
        filtered_words = [w for w in words if w.lower() not in stop_words and w.isalnum()]
        freq_dist = FreqDist(filtered_words)
        top_words = freq_dist.most_common(10)
        blob = TextBlob(text)
        sentiment = blob.sentiment
        return {
            'top_words': top_words,
            'sentiment': {
                'polarity': sentiment.polarity,
                'subjectivity': sentiment.subjectivity,
            },
        }

    def sanitize_filename(self, url):
        keepcharacters = (' ', '.', '_', '-')
        return "".join(c for c in url if c.isalnum() or c in keepcharacters).rstrip()

    def generate_html(self, image_urls, base_url):
        filename = self.sanitize_filename(base_url) + '.html'
        filepath = os.path.join('dd_scrape_image_dump', filename)
        os.makedirs('dd_scrape_image_dump', exist_ok=True)
        html_content = '<html><head><title>Image Gallery</title></head><body>'
        for url in image_urls:
            html_content += f'<img src="{url}" alt="Image" style="padding: 10px; height: 200px;"><br>'
        html_content += '</body></html>'
        with open(filepath, 'w') as f:
            f.write(html_content)
        return filepath

    def extract_links(self, soup):
        return [a['href'] for a in soup.find_all('a', href=True)]

    def extract_metadata(self, soup):
        meta_data = {}
        for meta in soup.find_all('meta'):
            meta_name = meta.get('name') or meta.get('property')
            if meta_name:
                meta_data[meta_name] = meta.get('content')
        return meta_data

    def extract_emails(self, soup):
        text = soup.get_text()
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        return email_pattern.findall(text)

    def extract_document_links(self, soup):
        doc_types = [
            '.pdf', '.doc', '.docx', '.xlsx', '.xls', '.ppt', '.pptx',
            '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp', '.epub',
            '.mobi', '.log', '.msg', '.wpd', '.wps', '.tex', '.vsd',
            '.xml', '.json', '.xps', '.md', '.code', '.mp3', '.wav',
            '.mp4', '.avi', '.mov', '.flv', '.wma', '.aac', '.dll',
            '.exe', '.zip', '.tar', '.gz', '.rar', '.7z', '.bz2',
            '.vmdk', '.iso', '.bin', '.img', '.dmg',
        ]
        return [
            a['href'] for a in soup.find_all('a', href=True)
            if any(a['href'].endswith(dt) for dt in doc_types)
        ]

    def _fetch_ahmia(self, query, amount, headers, proxy_config=None):
        """
        Fetch results from Ahmia (clearnet by default; routes through Tor when
        proxy_config is supplied). Handles the hidden CSRF nonce on the homepage.
        Result markup: <li class="result"> containing <a>, <cite>, <p>.
        """
        engine = Configuration.SEARCH_ENGINES['ahmia']
        # Upstream darkdump uses timeout=15 here, but Ahmia's search endpoint can
        # legitimately take 10-15s for a broad query (observed 14.7s for "hacking") —
        # every other engine in this file already uses 20-30s. Bumped to match.
        req_kwargs = {'headers': headers, 'timeout': 30}
        if proxy_config:
            req_kwargs['proxies'] = proxy_config

        homepage = requests.get(engine['base'], **req_kwargs)
        if homepage.status_code != 200:
            raise Exception(f"Couldn't fetch {engine['base']} (HTTP {homepage.status_code})")

        soup = BeautifulSoup(homepage.content, 'html.parser')
        nonce_el = soup.select_one('#searchForm input[type="hidden"]')
        if nonce_el is None:
            raise Exception("Couldn't find nonce on Ahmia homepage")

        nonce = f"&{nonce_el.attrs['name']}={nonce_el.attrs['value']}"
        url = engine['api'].format(query=query) + nonce

        page = requests.get(url, **req_kwargs)
        if page.status_code != 200:
            raise Exception(f"Ahmia search request failed (HTTP {page.status_code})")

        soup = BeautifulSoup(page.content, 'html.parser')
        result_page = soup.find(id='ahmiaResultsPage')
        if result_page is None:
            raise Exception("Couldn't extract results container from Ahmia")

        tag, cls = engine['result_tag']
        raw = result_page.find_all(tag, class_=cls)
        results = []
        for item in raw[:amount]:
            cite  = item.find('cite')
            a_tag = item.find('a')
            p_tag = item.find('p')
            site_url = cite.text.strip() if cite else ''
            if "http://" not in site_url and "https://" not in site_url:
                site_url = "http://" + site_url
            results.append({
                'title':       a_tag.text.strip() if a_tag else 'No title available',
                'description': p_tag.text.strip() if p_tag else 'No description available',
                'site_url':    site_url,
            })
        return results

    def _fetch_notevil(self, query, amount, headers, proxy_config):
        """
        Fetch results from Not Evil via its .onion address (Tor required).

        Not Evil has changed its search path across versions. We try the known
        paths in order and use whichever returns a 200.
        Result markup: <li class="result"> containing <a> and <p>.
        """
        engine   = Configuration.SEARCH_ENGINES['notevil']
        base     = engine['onion']
        encoded  = requests.utils.quote(query)
        engine_host = base.split('/')[2]

        search_paths = [
            f"/search?q={encoded}",
            f"/?q={encoded}",
            f"/index.php?q={encoded}",
            f"/search?phrase={encoded}",
        ]

        response = None
        for path in search_paths:
            try:
                r = requests.get(base + path, headers=headers, proxies=proxy_config, timeout=30)
                if r.status_code == 200:
                    response = r
                    break
            except Exception:
                continue

        if response is None:
            raise Exception("Not Evil: no search path returned a valid response")

        soup = BeautifulSoup(response.content, 'html.parser')
        results = []

        tag, cls = engine['result_tag']
        raw = soup.find_all(tag, class_=cls)

        # Fallback: scan for .onion links if expected markup isn't present
        if not raw:
            for a_tag in soup.find_all('a', href=lambda h: h and '.onion' in h and engine_host not in h):
                if len(results) >= amount:
                    break
                site_url    = a_tag['href'].strip()
                title       = a_tag.get_text(strip=True) or 'No title available'
                parent      = a_tag.parent
                description = parent.get_text(' ', strip=True).replace(title, '').strip()
                description = description[:200] if description else 'No description available'
                results.append({
                    'title':       title,
                    'description': description,
                    'site_url':    site_url,
                })
            return results

        for item in raw[:amount]:
            a_tag = item.find('a', href=True)
            p_tag = item.find('p')
            if not a_tag:
                continue
            site_url = a_tag['href'].strip()
            if site_url and 'http' not in site_url:
                site_url = 'http://' + site_url
            results.append({
                'title':       a_tag.get_text(strip=True) or 'No title available',
                'description': p_tag.get_text(strip=True) if p_tag else 'No description available',
                'site_url':    site_url,
            })
        return results

    def _fetch_tordex(self, query, amount, headers, proxy_config=None):
        """
        Fetch results from TorDex.

        Uses the .onion endpoint when a Tor proxy_config is supplied, otherwise
        falls back to the clearnet endpoint (tordex.cc/search) — both serve
        identical HTML. The HTML structure uses .container h5 a for results.

        NOTE: TorDex is completely unfiltered. Results may include illegal or
        harmful content. Use only for legitimate research purposes.
        """
        engine = Configuration.SEARCH_ENGINES['tordex']
        q = requests.utils.quote(query)

        if proxy_config:
            url = engine['onion'].format(query=q)
            response = requests.get(url, headers=headers, proxies=proxy_config, timeout=30)
        else:
            url = engine['api'].format(query=q)
            response = requests.get(url, headers=headers, timeout=20)

        if response.status_code != 200:
            raise Exception(f"TorDex request failed (HTTP {response.status_code})")

        soup = BeautifulSoup(response.content, 'html.parser')
        results = []

        # Primary: .container h5 a
        anchors = soup.select('.container h5 a')

        if not anchors:
            for a_tag in soup.find_all('a', href=lambda h: h and '.onion' in h):
                if len(results) >= amount:
                    break
                site_url    = a_tag['href'].strip()
                title       = a_tag.get_text(strip=True) or 'No title available'
                parent      = a_tag.parent
                description = parent.get_text(' ', strip=True).replace(title, '').strip()
                description = description[:200] if description else 'No description available'
                results.append({'title': title, 'description': description, 'site_url': site_url})
            return results

        for a_tag in anchors[:amount]:
            site_url = a_tag['href'].strip()
            if site_url and 'http' not in site_url:
                site_url = 'http://' + site_url
            title = a_tag.get_text(strip=True) or 'No title available'
            h5    = a_tag.parent
            p_tag = h5.find_next_sibling('p') if h5 else None
            description = p_tag.get_text(strip=True) if p_tag else 'No description available'
            results.append({
                'title':       title,
                'description': description,
                'site_url':    site_url,
            })
        return results

    def _fetch_tor66(self, query, amount, headers, proxy_config):
        """
        Fetch results from Tor66 via its .onion address (Tor required).

        Tor66 renders search results as <b> elements that follow the first <hr>
        divider on the page. Each result <b> contains an <a href> with the title
        and URL. This selector is confirmed by OnionSearch core.py:
            soup.find('hr').find_all_next('b')

        Fallback: any <a> pointing to a .onion href.

        NOTE: Tor66 is completely unfiltered. Results may include illegal or
        harmful content. Use only for legitimate research purposes.
        """
        engine = Configuration.SEARCH_ENGINES['tor66']
        url = engine['onion'].format(query=requests.utils.quote(query))
        response = requests.get(url, headers=headers, proxies=proxy_config, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Tor66 request failed (HTTP {response.status_code})")

        soup = BeautifulSoup(response.content, 'html.parser')
        results = []

        # Primary: <b> blocks that follow the first <hr> separator
        hr = soup.find('hr')
        b_tags = hr.find_all_next('b') if hr else []

        if not b_tags:
            # Fallback: scan all .onion hrefs
            for a_tag in soup.find_all('a', href=lambda h: h and '.onion' in h):
                if len(results) >= amount:
                    break
                site_url    = a_tag['href'].strip()
                title       = a_tag.get_text(strip=True) or 'No title available'
                parent      = a_tag.parent
                description = parent.get_text(' ', strip=True).replace(title, '').strip()
                description = description[:200] if description else 'No description available'
                results.append({'title': title, 'description': description, 'site_url': site_url})
            return results

        for b_tag in b_tags:
            if len(results) >= amount:
                break
            a_tag = b_tag.find('a', href=True)
            if not a_tag:
                continue
            site_url = a_tag['href'].strip()
            if site_url and 'http' not in site_url:
                site_url = 'http://' + site_url
            title = a_tag.get_text(strip=True) or 'No title available'
            # Description text sits directly after the <b> block as a text node or <br>
            desc_parts = []
            for sibling in b_tag.next_siblings:
                tag_name = getattr(sibling, 'name', None)
                if tag_name == 'b':
                    break   # next result block starts
                if tag_name == 'br':
                    continue
                text = sibling.get_text(strip=True) if tag_name else str(sibling).strip()
                if text:
                    desc_parts.append(text)
                    if len(' '.join(desc_parts)) >= 200:
                        break
            description = ' '.join(desc_parts)[:200] or 'No description available'
            results.append({
                'title':       title,
                'description': description,
                'site_url':    site_url,
            })
        return results

    def _fetch_onionland(self, query, amount, headers, proxy_config):
        """
        Fetch results from OnionLand via its .onion address (Tor required).

        OnionLand indexes Tor, I2P, and clearnet. We filter to .onion results only
        since Darkdump is a dark web tool. Results use .result-block .title a;
        the destination URL is double-encoded as the 'l' query param in the href
        (confirmed by OnionSearch core.py: unquote(unquote(get_parameter(href, 'l')))).

        Description text sits in the first <p> tag inside the .result-block that
        is NOT the URL line — we skip any <p> whose text looks like a raw URL.

        NOTE: OnionLand does minimal content filtering. Results may include
        harmful or illegal content. Use only for legitimate research.
        """
        from urllib.parse import urlparse, parse_qs, unquote as _unquote

        engine = Configuration.SEARCH_ENGINES['onionland']
        url = engine['onion'].format(query=requests.utils.quote(query))
        response = requests.get(url, headers=headers, proxies=proxy_config, timeout=30)
        if response.status_code != 200:
            raise Exception(f"OnionLand request failed (HTTP {response.status_code})")

        soup = BeautifulSoup(response.text, 'html5lib')
        results = []

        for a_tag in soup.select('.result-block .title a'):
            if len(results) >= amount:
                break

            # Skip ad links
            href = a_tag.get('href', '')
            if href.startswith('/ads/'):
                continue

            # Extract destination URL — double-encoded in the 'l' query param
            try:
                qs = parse_qs(urlparse(href).query)
                raw = qs.get('l', [''])[0]
                site_url = _unquote(_unquote(raw))
            except Exception:
                site_url = ''

            if not site_url:
                continue

            # Only keep .onion results — skip I2P (.i2p) and clearnet
            if '.onion' not in site_url:
                continue

            title = a_tag.get_text(strip=True) or 'No title available'

            # Description: find the first <p> in the result block that isn't
            # just a URL or the site address line
            description = 'No description available'
            block = a_tag.find_parent(class_='result-block')
            if block:
                for p in block.find_all('p'):
                    text = p.get_text(strip=True)
                    # Skip empty, very short, or raw-URL paragraphs
                    if text and len(text) > 20 and not text.startswith('http'):
                        description = text[:200]
                        break
                # Fallback: grab all non-link text from the block
                if description == 'No description available':
                    all_text = block.get_text(' ', strip=True)
                    # Strip the title from the block text to leave the snippet
                    snippet = all_text.replace(title, '').strip()
                    snippet = re.sub(r'https?://\S+', '', snippet).strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                    if len(snippet) > 20:
                        description = snippet[:200]

            results.append({
                'title':       title,
                'description': description,
                'site_url':    site_url,
            })

        return results

    def _fetch_excavator(self, query, amount, headers, proxy_config):
        """
        Fetch results from Excavator via its .onion address (Tor required).

        Probes known search paths in order since the exact endpoint may vary.
        Parses generic result containers and falls back to scanning .onion hrefs.
        """
        engine      = Configuration.SEARCH_ENGINES['excavator']
        base        = engine['onion']
        encoded     = requests.utils.quote(query)
        engine_host = base.split('/')[2]

        search_paths = [
            f"/search?q={encoded}",
            f"/search?query={encoded}",
            f"/?q={encoded}",
            f"/index.php?q={encoded}",
        ]

        response = None
        for path in search_paths:
            try:
                r = requests.get(base + path, headers=headers, proxies=proxy_config, timeout=30)
                if r.status_code == 200:
                    response = r
                    break
            except Exception:
                continue

        if response is None:
            raise Exception("Excavator: no search path returned a valid response")

        soup    = BeautifulSoup(response.text, 'html5lib')
        results = []

        tag, cls = engine['result_tag']
        raw = soup.find_all(tag, class_=cls) if cls else soup.find_all(tag)

        for item in raw:
            if len(results) >= amount:
                break
            a_tag = item.find('a', href=True)
            if not a_tag:
                continue
            href = a_tag['href'].strip()
            if '.onion' not in href or engine_host in href:
                continue
            site_url = href if href.startswith('http') else 'http://' + href
            title    = a_tag.get_text(strip=True) or 'No title available'

            description = 'No description available'
            for p in item.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 20 and not text.startswith('http'):
                    description = text[:200]
                    break
            if description == 'No description available':
                snippet = re.sub(r'https?://\S+', '', item.get_text(' ', strip=True))
                snippet = re.sub(r'\s+', ' ', snippet).replace(title, '').strip()
                if len(snippet) > 20:
                    description = snippet[:200]

            results.append({'title': title, 'description': description, 'site_url': site_url})

        # Fallback: scan all .onion hrefs on the page
        if not results:
            for a_tag in soup.find_all('a', href=lambda h: h and '.onion' in h and engine_host not in h):
                if len(results) >= amount:
                    break
                href     = a_tag['href'].strip()
                site_url = href if href.startswith('http') else 'http://' + href
                title    = a_tag.get_text(strip=True) or 'No title available'
                parent   = a_tag.parent
                snippet  = parent.get_text(' ', strip=True).replace(title, '').strip()
                description = snippet[:200] if len(snippet) > 20 else 'No description available'
                results.append({'title': title, 'description': description, 'site_url': site_url})

        return results

    def _scrape_site(self, site_url, headers, proxy_config, scrape_images, debug_mode, idx):
        """
        Scrape a single onion site for metadata, links, emails, documents,
        and optionally images. Returns a dict for ResultSaver, or None on failure.
        """
        try:
            site_response = requests.get(site_url, headers=headers, proxies=proxy_config, timeout=20)
            site_soup     = BeautifulSoup(site_response.content, 'html.parser')
            metadata      = self.extract_metadata(site_soup)
            links         = self.extract_links(site_soup)
            emails        = self.extract_emails(site_soup)
            documents     = self.extract_document_links(site_soup)

            images_gallery_path = None
            image_urls          = []
            images_str          = ""
            if scrape_images:
                images     = site_soup.find_all('img')
                image_urls = [img['src'] for img in images if img.get('src')]
                image_urls = [u if u.startswith('http') else site_url + u for u in image_urls]
                if image_urls:
                    html_path           = self.generate_html(image_urls, site_url)
                    images_gallery_path = os.path.abspath(html_path)
                    images_str = (
                        f"{Colors.BOLD}| Images Gallery: {Colors.END}"
                        f"{Colors.G}{images_gallery_path}{Colors.END}\n"
                    )

            print('-' * 50)
            print(f"{Colors.BOLD}{idx}.\n --- [+] Website: {Colors.END}{Colors.P}{site_url}{Colors.END}")
            print(f"{Colors.BOLD}| Metadata: {Colors.END}{Colors.G}{json.dumps(metadata)}{Colors.END}")
            print(f"{Colors.BOLD}| Links Found: {Colors.END}{Colors.G}{len(links)}{Colors.END}")
            print(f"{Colors.BOLD}| Emails Found: {Colors.END}{Colors.G}{', '.join(emails) if emails else 'No emails found.'}{Colors.END}")
            print(f"{Colors.BOLD}| Documents Found: {Colors.END}{Colors.G}{', '.join(documents) if documents else 'No document links found.'}{Colors.END}")

            if scrape_images:
                if image_urls:
                    print(images_str)
                else:
                    print(f"{Colors.BOLD + Colors.GR} No images found. Skipping parse. {Colors.END}")

            scrape_data = {
                'metadata':    metadata,
                'links_count': len(links),
                'emails':      emails,
                'documents':   documents,
            }
            if images_gallery_path:
                scrape_data['images_gallery'] = images_gallery_path
            return scrape_data

        except Exception as e:
            print(f"{Colors.BOLD + Colors.O} Dead onion, skipping...: {site_url} {Colors.END}")
            if debug_mode:
                print(f"{Colors.BOLD + Colors.R}[DEBUG] Exception: {e}{Colors.END}")
            return None

    def crawl(self, query, amount, engine_key='ahmia', use_proxy=False,
              scrape_sites=False, scrape_images=False, debug_mode=False,
              output_file=None, dedupe=False):

        engine_key = engine_key.lower()
        if engine_key not in Configuration.SEARCH_ENGINES:
            print(f"{Colors.BOLD + Colors.R}Unknown engine '{engine_key}'. "
                  f"Valid options: {', '.join(Configuration.VALID_ENGINES)}{Colors.END}")
            return

        engine  = Configuration.SEARCH_ENGINES[engine_key]
        headers = {'User-Agent': random.choice(Headers.user_agents)}
        proxy_config = {
            'http':  Configuration.__socks5init__,
            'https': Configuration.__socks5init__,
        } if use_proxy else {}

        # Tor-only engines: auto-enable proxy if the user forgot -p
        if engine['tor_required'] and not use_proxy:
            print(
                f"{Colors.BOLD + Colors.O}Warning: {engine['name']} is a Tor-only search engine. "
                f"Enabling proxy automatically.{Colors.END}"
            )
            proxy_config = {
                'http':  Configuration.__socks5init__,
                'https': Configuration.__socks5init__,
            }
            use_proxy = True

        # Warn and confirm when using an unfiltered engine
        if not engine.get('filtered', True):
            print(
                f"\n{Colors.BOLD + Colors.R}[!] WARNING: {engine['name']} is an unfiltered search engine.{Colors.END}\n"
                f"{Colors.BOLD + Colors.O}    Results may include illegal, harmful, or disturbing content.\n"
                f"    This tool is intended for legitimate research purposes only.{Colors.END}\n"
            )
            try:
                confirm = input(f"{Colors.BOLD}    Continue with {engine['name']}? [y/N]: {Colors.END}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = 'n'
            if confirm != 'y':
                print(f"{Colors.BOLD + Colors.R}Aborted.{Colors.END}")
                return
            print()

        # clearnet_only engines must never go through Tor
        is_clearnet_only = engine.get('clearnet_only', False)
        if is_clearnet_only and use_proxy:
            print(
                f"{Colors.BOLD + Colors.O}Note: {engine['name']} is a clearnet-only engine. "
                f"Ignoring proxy flag.{Colors.END}"
            )
            proxy_config = {}
            use_proxy = False

        if (scrape_sites or use_proxy) and not is_clearnet_only:
            if Platform(True).check_tor_connection(proxy_config) is False:
                return

        print(f"{Colors.BOLD + Colors.C}[ Engine: {engine['name']} ]{Colors.END}\n")

        # Dispatch to the correct fetcher
        results = []
        try:
            if engine_key == 'ahmia':
                results = self._fetch_ahmia(query, amount, headers,
                                            proxy_config if use_proxy else None)
            elif engine_key == 'notevil':
                results = self._fetch_notevil(query, amount, headers, proxy_config)
            elif engine_key == 'tordex':
                results = self._fetch_tordex(query, amount, headers, proxy_config)
            elif engine_key == 'tor66':
                results = self._fetch_tor66(query, amount, headers, proxy_config)
            elif engine_key == 'onionland':
                results = self._fetch_onionland(query, amount, headers, proxy_config)
            elif engine_key == 'excavator':
                results = self._fetch_excavator(query, amount, headers, proxy_config)
        except Exception as e:
            print(f"{Colors.BOLD + Colors.R}Error fetching results from {engine['name']}: {e}{Colors.END}")
            return

        results = self._filter_blacklisted(results) # Extremely important as this increases safe searching

        if not results:
            print(f"{Colors.BOLD + Colors.O}No results returned from {engine['name']}.{Colors.END}")
            return

        saver      = ResultSaver(output_file, query=query, engine=engine_key) if output_file else None
        seen_urls  = set()
        seen_meta  = set()   # fingerprints for metadata-based deduplication

        if dedupe:
            print(f"{Colors.BOLD + Colors.C}[ Deduplication: ON — results with identical title+description will be hidden ]{Colors.END}\n")

        for idx, result in enumerate(results, start=1):
            site_url    = result['site_url']
            title       = result['title']
            description = result['description']

            if not site_url or site_url in seen_urls:
                continue

            # Metadata-based deduplication: fingerprint on normalised title +
            # description. Different URLs that share the same content (mirrors,
            # re-indexed duplicates) are suppressed when --unique is active.
            if dedupe:
                fingerprint = (
                    re.sub(r'\s+', ' ', title.strip().lower()),
                    re.sub(r'\s+', ' ', description.strip().lower()),
                )
                if fingerprint in seen_meta:
                    if debug_mode:
                        print(f"{Colors.BOLD + Colors.GR}[DEDUPE] Skipping duplicate metadata: {site_url}{Colors.END}")
                    continue
                seen_meta.add(fingerprint)

            seen_urls.add(site_url)

            try:
                if scrape_sites:
                    print(f"{Colors.BOLD}{idx}. --- [+] Website: {Colors.END}{Colors.P}{title}{Colors.END}")
                    print(f"{Colors.BOLD}| Information: {Colors.END}{Colors.G}{description}{Colors.END}")
                    print(f"{Colors.BOLD}| Onion Link: {Colors.END}{Colors.G}{site_url}{Colors.END}")
                    scrape_data = self._scrape_site(
                        site_url, headers, proxy_config, scrape_images, debug_mode, idx
                    )
                    if saver:
                        saver.add(title, description, site_url, scrape_data)
                else:
                    print(f"{Colors.BOLD}{idx}. --- [+] Website: {Colors.END}{Colors.P}{title}{Colors.END}")
                    print(f"{Colors.BOLD}\t Information: {Colors.END}{Colors.G}{description}{Colors.END}")
                    print(f"{Colors.BOLD}| Onion Link: {Colors.END}{Colors.G}{site_url}{Colors.END}\n")
                    if saver:
                        saver.add(title, description, site_url)

            except KeyboardInterrupt:
                print(f"{Colors.BOLD + Colors.R} Quitting... {Colors.END}")
                break

        if saver:
            saver.save()
            saver.print_summary()


    def breach_intel(self, target: str, amount: int = 10, engine_key: str = 'ahmia',
                     use_proxy: bool = False, debug_mode: bool = False,
                     output_file: str = None, deep_scrape: bool = False,
                     query_delay: float = 1.5):
        """
        Advanced breach and credential leak intelligence scan.

        Features
        --------
        - Smart query generation  : detects email / domain / username / keyword
                                    and builds tailored query sets including
                                    paste-site operators, file extensions, hash
                                    type hints, and username permutations.
        - Result analysis         : regex-extracts credential artefacts (emails,
                                    MD5/SHA-1/SHA-256/bcrypt hashes, passwords
                                    adjacent to the target) from result snippets.
        - Severity classification : categorises each hit as CRITICAL / HIGH /
                                    MEDIUM / INFO based on URL / title / snippet
                                    signals (paste sites, combolists, markets).
        - Deep scrape mode        : when deep_scrape=True, follows each hit URL
                                    through Tor and extracts full page metadata.
        - Rate limiting           : configurable per-query delay to avoid engine
                                    rate-limits (default 1.5 s).
        - Structured output       : saves a richer JSON/CSV/TXT report that
                                    includes severity, artefacts, and categories.

        Usage
        -----
        python3 darkdump.py --breach -q "example.com" -e ahmia
        python3 darkdump.py --breach -q "admin@corp.com" -e notevil -p --breach-deep
        python3 darkdump.py --breach -q "john_doe" -e tor66 -o report.json
        """
        import time as _time
        import hashlib as _hashlib

        is_email  = '@' in target and '.' in target.split('@')[-1]
        is_domain = '.' in target and not is_email and ' ' not in target

        target_type = 'email' if is_email else 'domain' if is_domain else 'keyword'

        username_variants = []
        if is_email:
            user, domain = target.split('@', 1)
            for sep in ['.', '_', '-', '']:
                parts = re.split(r'[._\-]', user)
                if len(parts) >= 2:
                    username_variants.append(sep.join(parts))
            username_variants = list(dict.fromkeys(username_variants))  # dedupe
        elif not is_domain:
            # Normalise common separators for username permutations
            base = re.sub(r'[._\-\s]+', '', target)
            username_variants = [base, target.replace(' ', '_'),
                                  target.replace(' ', '.'), target.replace(' ', '-')]
            username_variants = list(dict.fromkeys(username_variants))

        queries = []

        if is_email:
            user, domain = target.split('@', 1)
            # Direct hits
            queries += [
                f'"{target}" leak',
                f'"{target}" breach',
                f'"{target}" credentials',
                f'"{target}" dump',
                f'"{target}" password',
                f'"{target}" combolist',
                f'"{target}" database',
                f'"{domain}" breach emails',
                f'"{domain}" combolist',
                f'"{domain}" credential dump',
                f'"{domain}" data leak .sql',
                f'"{domain}" employee passwords',
            ]
            # Username variant hits
            for v in username_variants[:3]:
                if v != user:
                    queries.append(f'"{v}" "{domain}" password')
            # Hash / paste context
            queries += [
                f'"{target}" md5',
                f'"{target}" sha1',
                f'"{target}" sha256',
                f'"{target}" pastebin',
            ]

        elif is_domain:
            queries += [
                f'"{target}" breach',
                f'"{target}" leak',
                f'"{target}" credentials dump',
                f'"{target}" database leak',
                f'"{target}" combolist',
                f'"{target}" employee passwords',
                f'"{target}" data dump',
                f'"{target}" hacked',
                f'"{target}" .sql dump',
                f'"{target}" plaintext passwords',
                f'"{target}" stealer logs',
                f'"{target}" infostealer',
                f'"{target}" credential stuffing',
                f'"{target}" leaked database 2024',
                f'"{target}" leaked database 2025',
            ]

        else:
            queries += [
                f'"{target}" password leak',
                f'"{target}" credentials',
                f'"{target}" breach',
                f'"{target}" dump',
                f'"{target}" combolist',
                f'"{target}" leaked database',
                f'"{target}" pastebin',
                f'"{target}" stealer',
            ]
            for v in username_variants[:3]:
                if v != target:
                    queries.append(f'"{v}" password')

        # Deduplicate while preserving order
        seen_q = set()
        queries = [q for q in queries if not (q in seen_q or seen_q.add(q))]

        EMAIL_RE    = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
        MD5_RE      = re.compile(r'\b[0-9a-fA-F]{32}\b')
        SHA1_RE     = re.compile(r'\b[0-9a-fA-F]{40}\b')
        SHA256_RE   = re.compile(r'\b[0-9a-fA-F]{64}\b')
        BCRYPT_RE   = re.compile(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}')
        # Password patterns: "password: VALUE" or "pass:VALUE" adjacent to target
        PASS_RE     = re.compile(
            r'(?:password|passwd|pass|pwd)\s*[:=]\s*([^\s,;\|]{4,64})',
            re.IGNORECASE
        )

        def extract_artefacts(text):
            artefacts = {}
            emails  = EMAIL_RE.findall(text)
            if emails:
                artefacts['emails'] = list(dict.fromkeys(emails))[:10]
            hashes = []
            for pat, htype in [(MD5_RE, 'md5'), (SHA1_RE, 'sha1'),
                               (SHA256_RE, 'sha256'), (BCRYPT_RE, 'bcrypt')]:
                found = pat.findall(text)
                for h in found[:5]:
                    hashes.append({'type': htype, 'value': h})
            if hashes:
                artefacts['hashes'] = hashes
            passwords = PASS_RE.findall(text)
            if passwords:
                artefacts['password_hints'] = list(dict.fromkeys(passwords))[:5]
            return artefacts

        CRITICAL_SIGNALS = [
            'combolist', 'credential dump', 'stealer log', 'infostealer',
            'plaintext password', 'cracked', 'fullz', 'combo', 'config'
        ]
        HIGH_SIGNALS = [
            'breach', 'leak', 'dump', 'database', 'hacked', 'exposed',
            'pastebin', 'paste', '.sql', 'data leak'
        ]
        MEDIUM_SIGNALS = [
            'password', 'credentials', 'account', 'login', 'access'
        ]

        PASTE_PATTERNS  = ['paste', 'bin', 'ghostbin', 'hastebin', 'dpaste', 'rentry']
        MARKET_PATTERNS = ['market', 'shop', 'store', 'vendor']
        FORUM_PATTERNS  = ['forum', 'board', 'chan', 'thread', 'post', 'discuss']
        LEAK_PATTERNS   = ['leak', 'breach', 'dump', 'combolist', 'database', 'stealer']

        def classify_severity(title, description, url):
            combined = (title + ' ' + description + ' ' + url).lower()
            for sig in CRITICAL_SIGNALS:
                if sig in combined:
                    return 'CRITICAL'
            for sig in HIGH_SIGNALS:
                if sig in combined:
                    return 'HIGH'
            for sig in MEDIUM_SIGNALS:
                if sig in combined:
                    return 'MEDIUM'
            return 'INFO'

        def classify_category(title, url):
            combined = (title + ' ' + url).lower()
            if any(p in combined for p in PASTE_PATTERNS):
                return 'paste-site'
            if any(p in combined for p in MARKET_PATTERNS):
                return 'market'
            if any(p in combined for p in FORUM_PATTERNS):
                return 'forum'
            if any(p in combined for p in LEAK_PATTERNS):
                return 'leak-index'
            return 'other'

        SEVERITY_COLOR = {
            'CRITICAL': Colors.BOLD + Colors.R,
            'HIGH':     Colors.BOLD + Colors.O,
            'MEDIUM':   Colors.BOLD + Colors.C,
            'INFO':     Colors.GR,
        }

        engine = Configuration.SEARCH_ENGINES[engine_key]
        proxy_config = {
            'http':  Configuration.__socks5init__,
            'https': Configuration.__socks5init__,
        } if use_proxy else {}

        if engine['tor_required'] and not use_proxy:
            proxy_config = {
                'http':  Configuration.__socks5init__,
                'https': Configuration.__socks5init__,
            }
            use_proxy = True
            print(f"{Colors.BOLD + Colors.O}Tor proxy enabled automatically for {engine['name']}.{Colors.END}")

        if use_proxy:
            if Platform(True).check_tor_connection(proxy_config) is False:
                return

        print(
            f"\n{Colors.BOLD + Colors.C}[ Breach Intel Scan ]{Colors.END}\n"
            f"{Colors.BOLD}Target     : {Colors.END}{Colors.P}{target}{Colors.END}\n"
            f"{Colors.BOLD}Type       : {Colors.END}{target_type}\n"
            f"{Colors.BOLD}Engine     : {Colors.END}{engine_key}\n"
            f"{Colors.BOLD}Queries    : {Colors.END}{len(queries)}\n"
            f"{Colors.BOLD}Deep scrape: {Colors.END}{'on' if deep_scrape else 'off'}\n"
            f"{Colors.BOLD}Query delay: {Colors.END}{query_delay}s\n"
        )

        all_results = []
        seen_urls   = set()
        dd          = Darkdump()

        for q_idx, query in enumerate(queries, start=1):
            print(f"{Colors.BOLD + Colors.C}[{q_idx}/{len(queries)}]{Colors.END} {query}")

            try:
                headers = {'User-Agent': random.choice(Headers.user_agents)}
                results = []

                if engine_key == 'ahmia':
                    results = dd._fetch_ahmia(query, amount, headers,
                                              proxy_config if use_proxy else None)
                elif engine_key == 'notevil':
                    results = dd._fetch_notevil(query, amount, headers, proxy_config)
                elif engine_key == 'tordex':
                    results = dd._fetch_tordex(query, amount, headers, proxy_config)
                elif engine_key == 'tor66':
                    results = dd._fetch_tor66(query, amount, headers, proxy_config)
                elif engine_key == 'onionland':
                    results = dd._fetch_onionland(query, amount, headers, proxy_config)
                elif engine_key == 'excavator':
                    results = dd._fetch_excavator(query, amount, headers, proxy_config)

                results = dd._filter_blacklisted(results)

                new_count = 0
                for result in results:
                    site_url    = result.get('site_url', '')
                    title       = result.get('title', 'No title available')
                    description = result.get('description', 'No description available')

                    if not site_url or site_url in seen_urls:
                        continue
                    seen_urls.add(site_url)
                    new_count += 1

                    # ── Analysis ───────────────────────────────────────────
                    severity   = classify_severity(title, description, site_url)
                    category   = classify_category(title, site_url)
                    artefacts  = extract_artefacts(title + ' ' + description)
                    scrape_data = None

                    # ── Deep scrape ─────────────────────────────────────────
                    if deep_scrape:
                        try:
                            scrape_data = dd._scrape_site(
                                site_url, headers, proxy_config,
                                scrape_images=False, debug_mode=debug_mode,
                                idx=len(all_results) + 1
                            )
                            # Enrich artefacts from scraped page text
                            if scrape_data:
                                page_emails = scrape_data.get('emails', [])
                                if page_emails:
                                    artefacts.setdefault('emails', [])
                                    artefacts['emails'] = list(
                                        dict.fromkeys(artefacts['emails'] + page_emails)
                                    )[:20]
                        except Exception as e:
                            if debug_mode:
                                print(f"    {Colors.O}[scrape error] {e}{Colors.END}")

                    enriched = {
                        'title':       title,
                        'description': description,
                        'site_url':    site_url,
                        'breach_query': query,
                        'severity':    severity,
                        'category':    category,
                        'artefacts':   artefacts,
                        'scrape_data': scrape_data,
                    }
                    all_results.append(enriched)

                    sev_col = SEVERITY_COLOR.get(severity, Colors.GR)
                    print(
                        f"  {sev_col}[{severity}]{Colors.END} "
                        f"{Colors.P}{title}{Colors.END}\n"
                        f"  {Colors.GR}{site_url}{Colors.END}\n"
                        f"  {Colors.GR}category={category}{Colors.END}"
                    )
                    if artefacts:
                        for k, v in artefacts.items():
                            print(f"  {Colors.C}{k}{Colors.END}: {v}")

                if new_count == 0:
                    print(f"  {Colors.GR}No new results.{Colors.END}")

            except KeyboardInterrupt:
                print(f"{Colors.BOLD + Colors.R} Quitting... {Colors.END}")
                break
            except Exception as e:
                print(f"  {Colors.BOLD + Colors.O}Error: {e}{Colors.END}")
                if debug_mode:
                    import traceback
                    traceback.print_exc()

            # Rate limit between queries
            if q_idx < len(queries):
                _time.sleep(query_delay)

        severity_counts = {}
        category_counts = {}
        for r in all_results:
            severity_counts[r['severity']]  = severity_counts.get(r['severity'], 0) + 1
            category_counts[r['category']]  = category_counts.get(r['category'], 0) + 1

        print(f"\n{Colors.BOLD + Colors.C}[ Breach Intel Complete ]{Colors.END}")
        print(f"{Colors.BOLD}Total unique results : {Colors.END}{len(all_results)}")
        print(f"{Colors.BOLD}Queries run          : {Colors.END}{len(queries)}")
        if severity_counts:
            print(f"{Colors.BOLD}By severity          : {Colors.END}", end='')
            for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'INFO']:
                if sev in severity_counts:
                    sc = SEVERITY_COLOR.get(sev, Colors.GR)
                    print(f"{sc}{sev}={severity_counts[sev]}{Colors.END} ", end='')
            print()
        if category_counts:
            cats = ', '.join(f"{k}={v}" for k, v in sorted(category_counts.items()))
            print(f"{Colors.BOLD}By category          : {Colors.END}{cats}")

        if output_file and all_results:
            ext = os.path.splitext(output_file)[1].lower()
            if ext == '.json':
                payload = {
                    'target':       target,
                    'target_type':  target_type,
                    'engine':       engine_key,
                    'query_count':  len(queries),
                    'result_count': len(all_results),
                    'severity_summary':  severity_counts,
                    'category_summary':  category_counts,
                    'results': [
                        {
                            'title':        r['title'],
                            'url':          r['site_url'],
                            'description':  r['description'],
                            'breach_query': r['breach_query'],
                            'severity':     r['severity'],
                            'category':     r['category'],
                            'artefacts':    r['artefacts'],
                        }
                        for r in all_results
                    ],
                }
                os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
                with open(output_file, 'w', encoding='utf-8') as f:
                    import json as _json
                    _json.dump(payload, f, indent=2, ensure_ascii=False)
                print(f"\n{Colors.BOLD + Colors.C}[ Saved -> {os.path.abspath(output_file)} ]{Colors.END}")
            else:
                # Fall back to ResultSaver for csv/txt
                saver = ResultSaver(output_file, query=f"breach:{target}", engine=engine_key)
                for r in all_results:
                    saver.add(
                        r['title'],
                        f"[{r['severity']}][{r['category']}] "
                        f"query={r['breach_query']} | {r['description']} | "
                        f"artefacts={r['artefacts']}",
                        r['site_url'],
                    )
                saver.save()
                saver.print_summary()



def darkdump_main():
    clr = Colors()
    bn  = Banner()

    Platform(True).clean_screen()
    Platform(True).get_operating_system_descriptor()
    bn.LoadDarkdumpBanner()
    print(notice)

    engine_help = (
        f"search engine to use (default: ahmia). choices: {', '.join(Configuration.VALID_ENGINES)}. "
        "ahmia: clearnet + Tor, Tor Project-endorsed, strict abuse filtering. "
        "notevil: Tor-only, Ahmia fork, partial content filtering. "
        "tordex: clearnet + Tor, fully uncensored index (UNFILTERED, prompt required). "
        "tor66: Tor-only, crawled index with directory (UNFILTERED, prompt required). "
        "onionland: Tor-only, indexes Tor + I2P + clearnet (UNFILTERED, prompt required). "
        "excavator: Tor-only, general dark web index (UNFILTERED, prompt required)."
    )

    parser = argparse.ArgumentParser(
        description="Darkdump is an interface for scraping the deepweb. Made by yours truly."
    )
    parser.add_argument("-v", "--version", help="returns darkdump's version", action="store_true")
    parser.add_argument("-q", "--query",   help="the keyword or string you want to search on the deepweb", type=str)
    parser.add_argument("-a", "--amount",  help="the amount of results you want to retrieve", type=int, default=10)
    parser.add_argument("-p", "--proxy",   help="use tor proxy for scraping", action="store_true")
    parser.add_argument("-i", "--images",  help="scrape images and visual content from the site", action="store_true")
    parser.add_argument("-s", "--scrape",  help="scrape the actual site for content and look for keywords", action="store_true")
    parser.add_argument("-d", "--debug",   help="enable debug output", action="store_true")
    parser.add_argument("-u", "--unique",  help="hide duplicate results that share the same title and description (metadata-based deduplication)", action="store_true")
    parser.add_argument("-e", "--engine",  help=engine_help, type=str, default='ahmia',
                        choices=Configuration.VALID_ENGINES, metavar='ENGINE')
    parser.add_argument(
        "--breach",
        help=(
            "run an advanced breach/credential leak intelligence scan for the given -q target. "
            "auto-detects email/domain/keyword and generates targeted queries including "
            "paste-site operators, hash types, username permutations, and stealer log terms. "
            "extracts credential artefacts from result snippets and classifies results by "
            "severity (CRITICAL/HIGH/MEDIUM/INFO) and category (paste-site/forum/market/leak-index). "
            "example: darkdump.py --breach -q admin@example.com -e notevil -p"
        ),
        action="store_true",
    )
    parser.add_argument(
        "--breach-deep",
        help="combine breach scan with deep scraping of each result page (requires -p/Tor)",
        action="store_true",
        dest="breach_deep",
    )
    parser.add_argument(
        "--breach-delay",
        help="seconds to wait between breach queries to avoid rate limits (default: 1.5)",
        type=float,
        default=1.5,
        dest="breach_delay",
        metavar="SECONDS",
    )
    parser.add_argument(
        "-o", "--output",
        help=(
            "save results to a file. format inferred from extension: "
            ".json -> JSON, .csv -> CSV, anything else -> plain text. "
            "example: -o results.json"
        ),
        type=str, default=None, metavar='FILE',
    )

    args = parser.parse_args()

    if args.version:
        print(Colors.BOLD + Colors.B + f"Darkdump Version: {__version__}\n" + Colors.END)

    if args.proxy and not args.scrape and not args.breach and not args.breach_deep:
        print(Colors.BOLD + Colors.R +
              "Error: Proxy option '-p' must be used with the scraping option '-s' (or --breach)." + Colors.END)
        parser.print_help()
        sys.exit(1)

    if args.images and not args.scrape:
        print(Colors.BOLD + Colors.R +
              "Error: Images option '-i' must be used with the scraping option '-s'." + Colors.END)
        parser.print_help()
        sys.exit(1)

    if args.debug:
        print(f"{Colors.R}DEBUG mode is on.{Colors.W}")

    if args.output:
        fmt      = os.path.splitext(args.output)[1].lower() or '.txt'
        fmt_name = {'.json': 'JSON', '.csv': 'CSV'}.get(fmt, 'TXT')
        print(f"{Colors.BOLD + Colors.C}[ Output: {args.output} ({fmt_name}) ]{Colors.END}")

    if args.breach:
        if not args.query:
            print(Colors.BOLD + Colors.R +
                  "Error: --breach requires a target via -q (email, domain, username, or keyword)." + Colors.END)
            sys.exit(1)
        engine = Configuration.SEARCH_ENGINES.get(args.engine, {})
        if not engine.get('filtered', True):
            print(
                f"\n{Colors.BOLD + Colors.R}[!] WARNING: {engine.get('name', args.engine)} is an unfiltered engine.{Colors.END}\n"
                f"{Colors.BOLD + Colors.O}    Results may include illegal or harmful content. "
                f"Use for legitimate research only.{Colors.END}\n"
            )
            try:
                confirm = input(f"{Colors.BOLD}    Continue? [y/N]: {Colors.END}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = 'n'
            if confirm != 'y':
                print(f"{Colors.BOLD + Colors.R}Aborted.{Colors.END}")
                sys.exit(0)
        Darkdump().breach_intel(
            args.query,
            amount=args.amount,
            engine_key=args.engine,
            use_proxy=args.proxy,
            debug_mode=args.debug,
            output_file=args.output,
            deep_scrape=args.breach_deep,
            query_delay=args.breach_delay,
        )
    elif args.query:
        print(
            f"Searching For: {args.query} | Engine: {args.engine} | "
            f"Showing up to {args.amount} results...\n"
            f"Indexing is viable, skipping dead onions.\n"
        )
        Darkdump().crawl(
            args.query,
            args.amount,
            engine_key=args.engine,
            use_proxy=args.proxy,
            scrape_sites=args.scrape,
            scrape_images=args.images,
            debug_mode=args.debug,
            output_file=args.output,
            dedupe=args.unique,
        )
    else:
        print("[~] Note: No query arguments were passed. Please supply a query to search.")


if __name__ == "__main__":
    darkdump_main()