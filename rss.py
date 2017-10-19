#!python3

import sys
import os.path
import random
import argparse
import ssl
import feedparser
import sqlite3 as sql

DB_PATH = "/tmp/rss.sqlite"

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
           )

max_summary_len = 60 # chars

def open_db():
    if os.path.exists(DB_PATH):
        return sql.connect(DB_PATH)
    else:
        return create_db()

def create_db():
    con = sql.connect(DB_PATH)

    with con:
        cur = con.cursor()
        cur.execute("DROP TABLE IF EXISTS Source")
        cur.execute("DROP TABLE IF EXISTS Article")
        cur.execute("DROP TABLE IF EXISTS State")

        cur.execute("CREATE TABLE Source(id INT, name TEXT, abbrev TEXT, url TEXT, timestamp DATE)")
        cur.execute("CREATE TABLE Article(id INT, title TEXT, url TEXT, source_id INT)")
        cur.execute("CREATE TABLE State(name TEXT, value TEXT)")

        # The index of the current article being displayed on the show button
        cur.execute("INSERT INTO State VALUES(?, ?)", ("current_article", "0"))
        # True to freeze the current_article value
        cur.execute("INSERT INTO State VALUES(?, ?)", ("hold_current", "0"))

    return con

def add_source(cur, source_id, source_url, source_initials):
    d = feedparser.parse(source_url)

    try:
        if 'updated' in d:
            updated = d.updated
        elif 'updated' in d.feed:
            updated = d.feed.updated
        cur.execute("INSERT INTO Source VALUES(?, ?, ?, ?, ?)", (source_id, d.feed.title, source_initials, source_url, updated))
    except KeyError as e:
        print(source_url)
        print(repr(d))
        print(str(e))
        sys.exit(1)

    entries = []
    i = get_article_count(cur)
    for e in d.entries:
        if not e.title:
            e.title = e.summary[0:min(len(e.summary), max_summary_len)] + "..."
        cur.execute("INSERT INTO Article VALUES(?, ?, ?, ?)",(i, e.title, e.link, source_id))
        i += 1

def add_sources(cur):
    create_ssl_context()

    for id,url in enumerate(SRC_URLS):
        add_source(cur, id, url[0], url[1])

def hold_article(cur):
    """ Return true if current_article is frozen """
    cur.execute("SELECT value from State WHERE name=?", ("hold_current",))
    data = cur.fetchone()
    return bool(int(data[0]))

def release_hold(cur):
    """ Remove the hold on the current_article """
    cur.execute("UPDATE State SET value=? WHERE name=?", ("0", "hold_current"))

def set_hold(cur):
    """ Remove the hold on the current_article """
    cur.execute("UPDATE State SET value=? WHERE name=?", ("1", "hold_current"))

def get_current_article_id(cur):
    cur.execute("SELECT value FROM State WHERE name=?", ("current_article",))
    data = cur.fetchone()
    return int(data[0])

def get_article_title(cur, id):
    cur.execute("SELECT title,source_id FROM Article WHERE id=?", (str(id),))
    data = cur.fetchone()
    cur.execute("SELECT abbrev FROM Source WHERE id=?", (str(data[1]),))
    data2 = cur.fetchone()
    return data2[0] + " | " + data[0]

def get_article_url(cur, id):
    cur.execute("SELECT url FROM Article WHERE id=?", (str(id),))
    data = cur.fetchone()
    return data[0]

def get_article_count(cur):
    with con:
        cur.execute("SELECT count() FROM Article")
        data = cur.fetchone()
        return int(data[0])

def choose_article(con, cur, index):
    """ Set the current_article index value in the database to index.
        Return index.
    """
    with con:
        count = get_article_count(cur)
        cur.execute("UPDATE State SET value=? WHERE name='current_article'", (str(index % count),))
        release_hold(cur)
    return index

def choose_random_article(con, cur):
    """ Set the current_article index value in the database to a random
        number.
        Return that random number.
    """
    if hold_article(cur):
        new_val = get_current_article_id(cur)
    else:
        new_val = random.randrange(get_article_count(cur))
    return choose_article(con, cur, new_val)

def choose_next_article(con, cur):
    article_id = choose_article(con, cur, get_current_article_id(cur) + 1)
    set_hold(cur)
    return article_id

def choose_prev_article(con, cur):
    article_id = choose_article(con, cur, get_current_article_id(cur) - 1)
    set_hold(cur)
    return article_id

def create_ssl_context():
    """ Allow unverified SSL contexts to avoid feedparser throwing a
        CERTIFICATE_VERIFY_FAILED Exception
    """
    if hasattr(ssl, '_create_unverified_context'):
        ssl._create_default_https_context = ssl._create_unverified_context

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
    args = parser.parse_args()

    if args.create or not os.path.exists(DB_PATH):
        con = create_db()
        with con:
            cur = con.cursor()
            add_sources(cur)
        with con:
            choose_random_article(con, cur)

    if args.create:
        sys.exit(0)

    con = open_db()
    cur = con.cursor()

    if args.random:
        current_article = choose_random_article(con, cur)
        try:
            print(get_article_title(cur, current_article))
        except TypeError as e:
            print("current_article:", current_article)
            print(e)
    elif args.next:
        current_article = choose_next_article(con, cur)
        try:
            print(get_article_title(cur, current_article))
        except TypeError as e:
            print("current_article:", current_article)
            print(e)
    elif args.prev:
        current_article = choose_prev_article(con, cur)
        try:
            print(get_article_title(cur, current_article))
        except TypeError as e:
            print("current_article:", current_article)
            print(e)
    elif args.url:
        current_article = get_current_article_id(cur)
        print(get_article_url(cur, current_article))
