#!python3

import sys
import os.path
import random
import feedparser
import sqlite3 as sql

DB_PATH = "/tmp/rss.sqlite"

SRC_URLS = ("http://feeds.reuters.com/reuters/technologyNews",
            "http://rss.cnn.com/rss/cnn_tech",
            "http://rss.cnn.com/rss/cnn_topstories.rss",
            "http://www.npr.org/rss/rss.php",
            "http://rss.csmonitor.com/feeds/csm",
            "http://feeds.foxnews.com/foxnews/latest",
           )

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

        cur.execute("CREATE TABLE Source(id INT, name TEXT, url TEXT, timestamp DATE)")
        cur.execute("CREATE TABLE Article(id INT, title TEXT, url TEXT, source_id INT)")
        cur.execute("CREATE TABLE State(name TEXT, value TEXT)")

        cur.execute("INSERT INTO State VALUES(?, ?)", ("current_article", "0"))

    return con

def add_source(cur, source_id, source_url):
    d = feedparser.parse(source_url)

    try:
        if 'updated' in d:
            updated = d['updated']
        elif 'updated' in d['feed']:
            updated = d['feed']['updated']
        cur.execute("INSERT INTO Source VALUES(?, ?, ?, ?)", (source_id, d['feed']['title'], source_url, updated))
    except KeyError as e:
        print(source_url)
        print(repr(d))
        print(str(e))
        sys.exit(1)

    entries = []
    i = get_article_count(cur)
    for e in d['entries']:
        cur.execute("INSERT INTO Article VALUES(?, ?, ?, ?)",(i, e['title'], e['link'], source_id))
        i += 1

def add_sources(cur):
    for id,url in enumerate(SRC_URLS):
        add_source(cur, id, url)

def get_current_article_id(cur):
    cur.execute("SELECT value FROM State WHERE name='current_article'")
    data = cur.fetchone()
    return int(data[0])

def get_article_title(cur, id):
    cur.execute("SELECT title FROM Article WHERE id=?", (str(id),))
    data = cur.fetchone()
    return data[0]

def get_article_url(cur, id):
    cur.execute("SELECT url FROM Article WHERE id=?", (str(id),))
    data = cur.fetchone()
    return data[0]

def get_article_count(cur):
    with con:
        cur.execute("SELECT count() FROM Article")
        data = cur.fetchone()
        return int(data[0])

def choose_random_article(con, cur):
    with con:
        new_val = random.randrange(get_article_count(cur))
        cur.execute("UPDATE State SET value=? WHERE name='current_article'", (str(new_val),))
    return new_val

#----------------------------------------------------------------------------
if __name__ == "__main__":
    if sys.argv[1] == "-h":
        print("rss [--create] [-t] [-h]")
        sys.exit(0)

    if sys.argv[1] == "--create":
        con = create_db()
        with con:
            cur = con.cursor()
            add_sources(cur)
        with con:
            choose_random_article(con, cur)

        sys.exit(0)

    con = open_db()
    cur = con.cursor()

    if sys.argv[1] == "-t":
        current_article = choose_random_article(con, cur)
        try:
            print(get_article_title(cur, current_article))
        except TypeError as e:
            print("current_article:", current_article)
            print(e)
    elif sys.argv[1] == "-u":
        current_article = get_current_article_id(cur)
        print(get_article_url(cur, current_article))
