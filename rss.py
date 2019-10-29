#!/usr/bin/env python3

import sys
import datetime
import os.path
import random
import argparse
import ssl
import feedparser
import sqlite3 as sql
from collections import namedtuple

import logging
logging.basicConfig(
    level=logging.INFO,
#     level=logging.DEBUG,
    filename='/tmp/rss.log',
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y/%m/%d %H:%M:%S')


DB_PATH = "/tmp/rss.sqlite"
WEB_PATH = "/tmp/rss.html"
MAX_SUMMARY_LEN = 60 # chars
MAX_HISTORY = 50 # article ids


SRC_URLS = (
            ("http://feeds.reuters.com/reuters/technologyNews", "Reuters"),
            ("http://rss.cnn.com/rss/cnn_tech", "CNNTech"),
            ("http://rss.cnn.com/rss/cnn_topstories.rss", "CNN"),
            ("http://www.npr.org/rss/rss.php", "NPR"),
            ("http://rss.csmonitor.com/feeds/csm", "CSMonitor"),
            ("http://feeds.foxnews.com/foxnews/latest", "FOX"),
            ("https://blogs.unity3d.com/feed/", "Unity"),
            ("http://feeds.bbci.co.uk/news/rss.xml", "BBC"),
            ("http://feeds.feedburner.com/TechCrunch/", "TechCrunch"),
            ("https://www.xyht.com/feed", "xyHt"),
            ("https://www.linuxjournal.com/node/feed", "Linux Journal"),
            ("https://medium.com/feed/one-zero", "Medium One-Zero"),
            ("https://medium.com/feed/topic/technology", "Medium Tech"),
            ("https://medium.com/feed/topic/programming", "Medium Programming"),
            ("https://medium.com/feed/topic/science", "Medium Science"),
            ("https://www.technologyreview.com/stories.rss", "MIT Tech Review"),
            ("https://news.mit.edu/rss", "MIT News"),
            ("http://feeds.feedburner.com/AllDiscovermagazinecomContent", "Discover"),
            ("https://www.techradar.com/rss", "TechRadar"),
            ("https://hexus.net/rss", "Hexus"),
            ("http://www.linux-magazine.com/rss/feed/lmi_news", "Linux Magazine"),
            ("https://www.esri.com/about/newsroom/feed", "Esri Newsroom"),
)

class RssDb:

    def __init__(self, db_path=DB_PATH, force_create=False):
        self.db_path = db_path
        if force_create or not os.path.exists(self.db_path):
            self.conn = self.create_db()
        else:
            self.conn = self.open_db()
        self.cur = self.conn.cursor()

    def open_db(self):
        if os.path.exists(self.db_path):
            return sql.connect(self.db_path)
        else:
            return self.create_db()

    def create_db(self):
        con = sql.connect(self.db_path)

        with con:
            self.cur = con.cursor()
            self.cur.execute("DROP TABLE IF EXISTS Source")
            self.cur.execute("DROP TABLE IF EXISTS Article")
            self.cur.execute("DROP TABLE IF EXISTS State")

            self.cur.execute("CREATE TABLE Source(id INT PRIMARY KEY, name TEXT, abbrev TEXT, url TEXT, timestamp DATE)")
            self.cur.execute("CREATE TABLE Article(id INT PRIMARY KEY, title TEXT, url TEXT, source_id INT, FOREIGN KEY (source_id) REFERENCES Source(id))")
            self.cur.execute("CREATE TABLE State(name TEXT PRIMARY KEY, value TEXT)")

            # The index of the current article being displayed on the show button
            self.cur.executemany("INSERT INTO State VALUES(?, ?)", (("current_index", "0"),
                                                                ("hold_current", "0"),
                                                                ("history", "0"),
                                                                ))

        return con

    def add_source(self, source_id, source_url, source_initials):
        d = feedparser.parse(source_url)

        try:
            updated = datetime.datetime.now()
            if 'updated' in d:
                updated = d.updated
            elif 'updated' in d.feed:
                updated = d.feed.updated
            with self.conn:
                self.cur.execute("INSERT INTO Source VALUES(?, ?, ?, ?, ?)", (source_id, d.feed.title, source_initials, source_url, updated))
        except KeyError as e:
            print(source_url)
            print(repr(d))
            print(str(e))
            sys.exit(1)

        articles = []
        i = self.get_article_count()
        for e in d.entries:
            if not e.title:
                e.title = e.summary[0:min(len(e.summary), MAX_SUMMARY_LEN)] + "..."
            articles.append((i, e.title, e.link, source_id))
            i += 1
        with self.conn:
            self.cur.executemany("INSERT INTO Article VALUES(?, ?, ?, ?)", articles)

    def add_sources(self):
        self.create_ssl_context()

        for id,url in enumerate(SRC_URLS):
            self.add_source(id, url[0], url[1])

    def hold_article(self):
        """ Return true if current_index is frozen """
        self.cur.execute("SELECT value from State WHERE name='hold_current'")
        data = self.cur.fetchone()
        return bool(int(data[0]))

    def release_hold(self):
        """ Remove the hold on the current_index """
        with self.conn:
            self.cur.execute("UPDATE State SET value=0 WHERE name='hold_current'")

    def set_hold(self):
        """ Remove the hold on the current_index """
        with self.conn:
            self.cur.execute("UPDATE State SET value=1 WHERE name='hold_current'")

    def get_current_article_index(self):
        self.cur.execute("SELECT value FROM State WHERE name='current_index'")
        data = self.cur.fetchone()
        return int(data[0])

    def set_current_index(self, index):
        index = min(index, len(self.get_history())-1)
        with self.conn:
            self.cur.execute("UPDATE State SET value=? WHERE name='current_index'", (str(index),))

    def get_current_article_id(self):
        articles = self.get_history()
        index = self.get_current_article_index()
        return int(articles[index])

    def get_article_title(self):
        id = self.get_current_article_id()
        self.cur.execute("SELECT title,source_id FROM Article WHERE id=?", (str(id),))
        data = self.cur.fetchone()
        self.cur.execute("SELECT abbrev FROM Source WHERE id=?", (str(data[1]),))
        data2 = self.cur.fetchone()
        return "[" + str(id) + "/" + str(self.get_article_count()) + "] " + data2[0] + " | " + data[0]
        # return data2[0] + " | " + data[0]

    def get_article_url(self):
        id = self.get_current_article_id()
        self.cur.execute("SELECT url FROM Article WHERE id=?", (str(id),))
        data = self.cur.fetchone()
        return data[0]

    def get_source_count(self):
        self.cur.execute("SELECT count() FROM Source")
        data = self.cur.fetchone()
        return int(data[0])

    def get_article_count(self):
        self.cur.execute("SELECT count() FROM Article")
        data = self.cur.fetchone()
        return int(data[0])

    def in_history(self):
        """ Return True if the current article is not the last item
            in the history list.
        """
        return self.get_current_article_index() != 0

    def get_history(self):
        """ Return article history as an array of strings """
        self.cur.execute("SELECT value FROM State WHERE name='history'")
        return self.cur.fetchone()[0].split()

    def add_to_history(self, new_article):
        """ Append new_article id to article_history """
        articles = [str(new_article)] + self.get_history()[0:MAX_HISTORY-1]  # only save last MAX_HISTORY ids
        with self.conn:
            self.cur.execute("UPDATE State SET value=? WHERE name='history'", (" ".join(articles),))
        self.set_current_index(0)

    def choose_random_article(self):
        """ Set the current_article index value in the database to a random
            number.
            Return that random number.
        """
        if not self.hold_article():
#            new_val = self.get_current_article_id()
#        else:
            new_val = random.randrange(self.get_article_count())
            self.add_to_history(new_val)

    def choose_next_article(self):
        self.set_current_index(max(self.get_current_article_index() - 1, 0))

    def choose_prev_article(self):
        self.set_current_index(min(self.get_current_article_index() + 1, MAX_HISTORY))

    def create_ssl_context(self):
        """ Allow unverified SSL contexts to avoid feedparser throwing a
            CERTIFICATE_VERIFY_FAILED Exception
        """
        if hasattr(ssl, '_create_unverified_context'):
            ssl._create_default_https_context = ssl._create_unverified_context

    def create_web_page(self):
        """ Output the database contents as HTML """
        html_page = '<html><head>RSS Feeds</head><body>{}</body></html>'
        html = ''

        # Get (id INT PRIMARY KEY, name TEXT, abbrev TEXT, url TEXT, timestamp DATE)
        Source = namedtuple("Source", "id name abbrev url timestamp")
        Article = namedtuple("Article", "id title url source_id")

        self.cur.execute("SELECT * from Source")

        for src in [Source(*s) for s in self.cur.fetchall()]:
            html += '<div class="source">\n'
            html += '<h2><a href="{}">{}</a> | {}</h2>\n'.format(src.url, src.abbrev, src.name)
            html += '<b>Updated {}</b>'.format(src.timestamp)
            html += '</div>\n'

            html += '<div class="articles">\n'
            # Get (id INT PRIMARY KEY, title TEXT, url TEXT, source_id INT)
            self.cur.execute("SELECT * FROM Article WHERE source_id=?", (src.id,))
            for art in [Article(*a) for a in self.cur.fetchall()]:
                html += '<a href="{}">{}</a><br/>\n'.format(art.url, art.title)
            html += '</div>\n'
        html_page = html_page.format(html)
        return html_page

    def show_debug_info(self):
        print("database contains {} articles".format(self.get_article_count()))
        print("current_index={}".format(self.get_current_article_index()))
        print("current_id={}".format(self.get_current_article_id()))
        print("in_history={}".format(self.in_history()))
        print("history={}".format(self.get_history()))
        print("hold_article={}".format(self.hold_article()))


#----------------------------------------------------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--create", action="store_true",
                        help="(re-)create the feed database")
    parser.add_argument("-r", "--random", action="store_true",
                        help="choose random article")
    parser.add_argument("-u", "--url", action="store_true",
                        help="print current article URL to stdout")
    parser.add_argument("-n", "--next", action="store_true",
                        help="choose the next article")
    parser.add_argument("-p", "--prev", action="store_true",
                        help="choose the previous article")
    parser.add_argument("-wp", "--webpage", action="store_true",
                        help="output the database contents as a web page to {}".format(WEB_PATH))
    parser.add_argument("-d", "--debug", action="store_true",
                        help="show database status information on stdout for debugging")
    parser.add_argument("-db", "--db", nargs=1, required=False,
                        help="use an alternate database (useful for debugging)")
    args = parser.parse_args()

    if 'db' in args and args.db:
        DB_PATH = args.db

    if args.create or not os.path.exists(DB_PATH):
        # Create or recreate and repopulate the database
        logging.info("(Re)creating database: " + DB_PATH)
        db = RssDb(db_path=DB_PATH, force_create=args.create)
        db.add_sources()
        logging.info("Database (re)created: {} articles from {} feeds".format(db.get_article_count(), db.get_source_count()))
        db.choose_random_article()

        # If we were just asked to create it, then quit
        if args.create:
            sys.exit(0)
    else:
        # Open the database
        db = RssDb(db_path=DB_PATH)

    if args.random:
        db.choose_random_article()
        title = db.get_article_title()
        print(title)
        logging.debug("Choosing random article ({})".format(db.get_current_article_id()))
        if not title or len(title.strip()) < 1:
            logging.warning("Article has blank title: ({}) {}".format(db.get_current_article_id(), db.get_article_url()))
        db.release_hold() # turn off the flag if this was the spurious fetch
    elif args.url:
        db.get_current_article_id()
        url = db.get_article_url()
        print(url)
        logging.debug("Retrieving current article ({})".format(db.get_current_article_id()))
        logging.info("Current article URL: " + url)
        db.release_hold()
    elif args.next:
        if db.in_history():
            db.choose_next_article()
            db.set_hold() # assert hold to overcome a spurious -r fetch
        else:
            db.choose_random_article()
            db.set_hold() # assert hold to overcome a spurious -r fetch
        logging.info("Choosing next article in history ({})".format(db.get_current_article_id()))
        # title = db.get_article_title()
        # print(title)
    elif args.prev:
        db.choose_prev_article()
        db.set_hold()
        logging.info("Choosing prev article in history ({})".format(db.get_current_article_id()))
        # title = db.get_article_title()
        # print(title)
    elif args.webpage:
        with open(WEB_PATH, "w") as html_out:
            html_out.write(db.create_web_page())
        logging.info("Writing HTML output to " + WEB_PATH)
    elif args.debug:
        logging.debug("Showing database debug info")
        db.show_debug_info()

    sys.exit(0)
