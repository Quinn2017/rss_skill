# -*- coding: utf-8 -*-

import sys
from os.path import dirname, abspath, basename
import subprocess

from mycroft.skills.core import MycroftSkill
from adapt.intent import IntentBuilder
from mycroft.messagebus.message import Message

import time
import feedparser

import os
from os.path import dirname
from mycroft.util.log import getLogger

from nltk import pos_tag
from nltk.downloader import Downloader
import re
import unicodedata

try:
    # Python 2.6-2.7
    from HTMLParser import HTMLParser
except ImportError:
    from html.parser import HTMLParser

html_parser = HTMLParser()
sys.path.append(abspath(dirname(__file__)))

logger = getLogger(abspath(__file__).split('/')[-2])
__author__ = 'forslund'


def replace_specials(string):
    """ Replace special characters in string. """
    string = string.replace('&', 'and')
    string = string.replace('!', ' ')
    string = string.replace('.', ' ')
    string = string.replace('!', '')
    return string


def get_interesting_words(s):
    """ Isolate vers and nouns from the string and return them as list. """
    interesting_tags = ['NN', 'NNS', 'NNP', 'VBP', 'VB', 'VBP', 'JJ']
    return [w[0] for w in pos_tag(s.split()) if w[1] in interesting_tags]


def calc_rating(words, utterance):
    """ Rate how good a title matches an utterance. """
    rating = 0
    for w in words:
        if w.lower() in utterance.lower():
            rating += 1
    return rating


def clean_html(raw_html):
    """ Remove html tags from string. """
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    cleantext = html_parser.unescape(cleantext)
    return unicodedata.normalize('NFKD', cleantext).encode('ascii', 'ignore')


def get_best_matching_title(items, utterance):
    """ Check the items against the utterance and see which matches best. """
    item_rating_list = []
    for i in items:
        title = i.get('title', '')
        words = get_interesting_words(title)
        item_rating_list.append((calc_rating(words, utterance), i))
    return sorted(item_rating_list)[-1]


ALT_NLTK_DATA = 'https://pastebin.com/raw/D3TBY4Mj'


class RssSkill(MycroftSkill):
    def __init__(self):
        super(RssSkill, self).__init__('RssSkill')
        self._is_reading_headlines = False
        self.feeds = {}
        self.cached_items = {}
        self.cache_time = {}
        try:
            pos_tag('advance')
        except LookupError:
            logger.debug('Tagger not installed... Trying to download')
            dler = Downloader()
            if not dler.download('averaged_perceptron_tagger'):
                logger.debug('Trying alternative source...')
                dler = Downloader(ALT_NLTK_DATA)
                dler.download('averaged_perceptron_tagger',
                         raise_on_error=True)


    def cache(self, title, items):
        """ Add items to cache and set a timestamp for the cache."""
        self.cached_items[title] = items
        self.cache_time[title] = time.time()

    def initialize(self):
        print self.settings.keys()
        for i in range(5):
            url_key = "url{}".format(i)
            alias_key = "alias{}".format(i)
            url = self.settings.get(url_key)
            alias = self.settings.get(alias_key)
            print "loading from settings"
            print url_key, alias_key
            print alias, url
            if url:
                feed = feedparser.parse(url)
                title = alias or feed['channel']['title']
                items = feed.get('items', [])
                self.cache(title, items)

                title = replace_specials(title)
                print 'Loaded {}'.format(title)
                self.feeds[title] = url
                logger.info(title)
                self.register_vocabulary(title, 'TitleKeyword')

        intent = IntentBuilder('rssIntent')\
            .require('RssKeyword')\
            .require('TitleKeyword') \
            .build()
        self.register_intent(intent, self.handle_headlines)

        intent = IntentBuilder('readArticleIntent')\
            .require('ReadKeyword')\
            .build()
        self.register_intent(intent, self.handle_read)

        intent = IntentBuilder('readLatestIntent')\
            .require('ReadKeyword')\
            .require('LatestKeyword')\
            .require('TitleKeyword')\
            .build()
        self.register_intent(intent, self.handle_read_latest)
        logger.debug('Intialization done')

    def handle_headlines(self, message):
        """Speak the latest headlines from the selected feed."""
        title = message.data['TitleKeyword']
        feed = feedparser.parse(self.feeds[title])
        items = feed.get('items', [])

        # Only read three items
        if len(items) > 3:
            items = items[:3]
        self.cache(title, items)

        self._is_reading_headlines = True
        self.speak('Here\'s the latest headlines from ' +
                   message.data['TitleKeyword'])
        for i in items:
            if not self._is_reading_headlines:
                break
            logger.info('Headline: ' + i['title'])
            self.speak(i['title'])
            time.sleep(5)
        self._is_reading_headlines = False

    def get_items(self, name):
        """
            Get items from the named feed, if cache exists use cache otherwise
            fetch the feed and update.
        """
        cache_timeout = 10 * 60
        cached_time = float(self.cache_time.get(name, 0))

        if name in self.cached_items \
                and (time.time() - cached_time) < cache_timeout:
            logger.debug('Using cached feed...')
            return self.cached_items[name]
        else:
            logger.debug('Fetching feed and updating cache')
            feed = feedparser.parse(self.feeds[name])
            feed_items = feed.get('items', [])
            self.cache(name, feed_items)

            if len(feed_items) > 5:
                return feed_items[:5]
            else:
                return feed_items

    def handle_read(self, message):
        """
            Find and read a feed item summary that best matches the
            utterance.
        """
        utterance = message.data.get('utterance', '')
        items = []
        for f in self.feeds:
            items += self.get_items(f)
        best_match = get_best_matching_title(items, utterance)

        logger.debug("Reading " + best_match[1]['title'])
        if best_match[0] != 0:
            self.speak(clean_html(best_match[1]['summary']))

    def handle_read_latest(self, message):
        title = message.data['TitleKeyword']
        latest = self.get_items(title)[0]
        text = latest.get('description') or latest.get('summary')
        self.speak(clean_html(text))

    def stop(self):
        self._is_reading_headlines = False


def create_skill():
    return RssSkill()
