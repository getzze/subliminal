# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import time
import logging
import babelfish

from collections import namedtuple
import difflib
import json, re, string

try:  # for python3.*
    from urllib.parse import urlencode
    from urllib.request import urlopen
    from urllib.request import Request
    from urllib.error import URLError
except ImportError:
    # for python2.*
    from urllib2 import urlopen
    from urllib import urlencode
    from urllib2 import Request
    from urllib2 import URLError

## Search omdb from https://github.com/Adys/python-omdb idea

## use_tvdb
from pytvdbapi import api as tvdbapi
__tvdb_apikey__ = "B43FF87DE395DF56"

## use_imdb
import imdb as imdbapi

## use_scrapper
from mechanize import Browser
from bs4 import BeautifulSoup
# Duckduckgo scrapper from http://github.com/djinn/python-duckduckgo
__ddg_version__ = 0.242
__search_engines__ = ['bing']

## use_tmdbsimple
import tmdbsimple
__tmdb_apikey__ = 'c2c73ebd1e25cbc29cf61158c04ad78a'

#import tmdb3


# internal client instances
_tvdb = tvdbapi.TVDB(__tvdb_apikey__)
_imdb = imdbapi.IMDb()
_tmdbsimple = tmdbsimple.TMDB(__tmdb_apikey__)


logger = logging.getLogger(__name__)


def get_imdbID_Episode(series, season, episode, year=None, **kwargs):
    """Get imdbID
    For Episode:
        require: `series`, `season`, `episode`, (optional `year`)
        return: dict with keys (imdb_id, series_imdb_id, tvdb_id, series_tvdb_id, tmdb_id, series_tmdb_id)    
    """
    # Time execution
    start_time = time.time()

    ids = dict()
    tvdb_lang = 'en'

    # Options
    use_tmdbsimple = kwargs.get('use_tmdbsimple', True)
    use_scrapper = kwargs.get('use_scrapper', True)
    use_scrapper_episode = kwargs.get('use_scrapper_episode', True) if use_scrapper else False
    use_tvdb = kwargs.get('use_tvdb', True)
    use_imdb = kwargs.get('use_imdb', True)
    use_omdb = kwargs.get('use_omdb', True)
    use_omdb_episode = kwargs.get('use_omdb_episode', True)
        
    
    # Get series imdbID
    if use_tmdbsimple:
        logger.debug('Use themoviedb.org to get series imdbID of %r' %(series))
        search = _tmdbsimple.Search().tv({'query':series, 'year':year})
        if search['total_results'] > 0:
            ids['series_tmdb_id'] = search['results'][0]['id']
            series_ids = _tmdbsimple.TV(ids['series_tmdb_id']).external_ids()
            ids['series_imdb_id'] = str2int_imdb(series_ids.get('imdb_id', None))
            ids['series_tvdb_id'] = series_ids.get('tvdb_id', None)
            logger.debug('Found ids for series: %r' %(ids))
        else:
            logger.debug('No ids found')
    if use_tvdb and not ids.get('series_tvdb_id',None) and not ids.get('series_imdb_id', None):
        logger.debug('Use thetvdb.org to get series imdbID of %r' %(series))
        search = _tvdb.search(series, tvdb_lang)
        if len(search) > 0:
            show_tvdb = search[0]
            ids['series_tvdb_id'] = str2int_imdb(show_tvdb.data.get('tvdbid',None))   
            ids['series_imdb_id'] = str2int_imdb(show_tvdb.data.get('imdbid',None))    
            logger.debug('Found ids for series: %r' %(ids))
        else:
            logger.debug('No ids found')
    if use_omdb_episode and not ids.get('series_imdb_id',None):
        logger.debug('Use omdbapi.com to get series imdbID of %r' %(series))
        data_series = omdb_search(series, match='string')
        for response in data_series:
            # check if one answer is of type `series`
            if response.get('Type',None) == 'series':
                series_imdbid = str2int_imdb(response.get('imdbID', None))
                logger.debug('Found ids for series: %r' %(ids))
                break

    
    # Get episode imdbID
    if use_tmdbsimple and ids.get('series_tmdb_id',None):
        logger.debug('Use themoviedb.org to get imdbID of %r %dx%d' %(series, season, episode))
        episode_ids = _tmdbsimple.TV_Episodes(ids['series_tmdb_id'], season, episode).external_ids()
        ids['tmdb_id'] = episode_ids.get('id', None)
        ids['imdb_id'] = str2int_imdb(episode_ids.get('imdb_id', None))
        ids['tvdb_id'] = episode_ids.get('tvdb_id', None)
        logger.debug('Found ids: %r' %(ids))
    if use_scrapper_episode and not ids.get('imdb_id',None) and ids.get('series_imdb_id',None):
        logger.debug('Use imdb scrapper to get imdbID of %r %dx%d' %(series, season, episode))
        url_base = 'http://akas.imdb.com/title/%s/episodes?season=%d'
        br = Browser()
        br.set_handle_robots(False)
        br.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.2;\
                            WOW64) AppleWebKit/537.11 (KHTML, like Gecko)\
                            Chrome/23.0.1271.97 Safari/537.11')]
        r = br.open(url_base %(int2str_imdb(ids['series_imdb_id']), season))
        soup = BeautifulSoup(r, 'lxml')
        for a in soup.find_all('a'):
            href = a.get('href','')
            match = re.search(r"/title/tt(?P<id>\d{7})/\?ref_=tt_ep_ep"+'%d'%episode, href)
            if match:
                ids['imdb_id'] = int(match.group('id'))
                logger.debug('Found ids: %r' %(ids))
                break
    if use_tvdb and (not ids.get('imdb_id',None)) and show_tvdb in locals():
        logger.debug('Use thetvdb.org to get imdbID of %r %dx%d' %(series, season, episode))
        try:
            episode_tvdb = show_tvdb.get(season, dict()).get(episode, dict()).get(data, dict())
            ids['imdb_id'] = str2int_imdb(episode_tvdb.get('imdbid',None))    
            ids['tvdb_id'] = str2int_imdb(episode_tvdb.get('tvdbid',None))    
            logger.debug('Found ids: %r' %(ids))
        except Exception as e:
            logger.debug('Could not find exact match on thetvdb.com for show %r, episode %dx%d: %r'%(show_tvdb, season, episode, e))
    if use_imdb and not ids.get('imdb_id',None) and ids.get('series_imdb_id',None):
        logger.debug('Use imdb.org to get imdbID of %r %dx%d' %(series, season, episode))
        #imdb = imdbapi.IMDb()
        try:
            show_imdb = _imdb.get_movie_episodes('%r' % ids['series_imdb_id']).get('data',dict()).get('episodes', dict())
            episode_imdb = show_imdb[season][episode]
            ids['imdb_id'] = str2int_imdb(episode_imdb.getID())
            logger.debug('Found ids: %r' %(ids))
        except Exception as e:
            logger.debug('Could not find exact match on imdb.com for show %s, episode %dx%d: %r'%(series, season, episode, e))
                    
    end_time = time.time()
    logger.info('Ids for "%s %dx%d" found in %.2f s: %r' %(series, season, episode, (end_time - start_time),ids))
    return ids
                  
def get_imdbID_Movie(title, year=None, use_tmdbsimple=True, use_omdb=True, use_omdb_movie=True, use_scrapper=True, **kwargs):
    """Get imdbID
    For Movie:
        require: `title`, (optional `year`)
        return: imdbid
    """
    # Time execution
    start_time = time.time()

    # match must be an ordered list
    matches = []

    # Options
    use_tmdbsimple = kwargs.get('use_tmdbsimple', True)
    use_scrapper = kwargs.get('use_scrapper', True)
    use_scrapper_movie = kwargs.get('use_scrapper_movie', True) if use_scrapper else False
    use_tvdb = kwargs.get('use_tvdb', True)
    use_imdb = kwargs.get('use_imdb', True)
    use_omdb = kwargs.get('use_omdb', True)
    use_omdb_movie = kwargs.get('use_omdb_movie', True) if use_omdb else False


    if use_tmdbsimple:
        logger.debug('Use themoviedb.org to get imdbID of %r' %(title))
        search = _tmdbsimple.Search().movie({'query':title, 'year':year})
        if search['total_results'] > 0:
            movie_tmdbsimple = _tmdbsimple.Movies(search['results'][0]['id'])
            dump_imdb = str2int_imdb(movie_tmdbsimple.info().get('imdb_id',None))    
            if dump_imdb not in matches:
                matches.append(dump_imdb)
                logger.debug('Found possible imdbID for title %s: %d'%(title, dump_imdb))

    if use_scrapper_movie:
        try:
            bangs =  __search_engines__
        except NameError:    
            bangs = ['bing']
            
        logger.debug('Use scrapper to get imdbID of %r from search engines: %r' %(title, bangs))
        for bang in bangs:
            query = title + (' %d'%(year) if type(year) in (int, float) else '')
            answer = imdb_query(query, bang=bang)
            if not answer:
                logger.debug('Could not make the search on duckduckgo with query %s and bang %s'%(query, bang))
                continue
            dump_imdb = str2int_imdb(answer)
            if dump_imdb not in matches:
                matches.append(dump_imdb)
                logger.debug('Found possible imdbID for title %s: %d'%(title, dump_imdb))
            else:
                logger.debug('ImdbID already matched for title %s: %d'%(title, dump_imdb))


    if use_omdb_movie:
        logger.debug('Use omdbapi.com to get imdbID of %r' %(title) + (' (%d)'%(year) if year else ''))
        data_series = omdb_search(title, year, match='string')
        for response in data_series:
            # only compute `movie` response
            if response.get('Type',None) == 'movie':
                dump_imdb = str2int_imdb(response.get('imdbID', None))
                if dump_imdb not in matches:
                    matches.append(dump_imdb)
                    logger.debug('Found possible imdbID for title %s: %d'%(title, dump_imdb))


    if len(matches) <= 0: ## No match
        end_time = time.time()
        logger.info('No perfect match for title "%s" in %.2f s.'%(title, end_time-start_time))
        return None
    elif len(matches) == 1: ## One single match
        end_time = time.time()
        logger.info('One single match for title "%s" found in %.2f s: imdbID %d'%(title, end_time-start_time, matches[0]))
        return matches[0]
    else:
        best_match = matches[0]
        ## TO DO : compare to best value
        #for match in matches[1:]:
            #response = omdb_search(int2str_imdb(match), match='imdbid')
            #if response.get('Type',None) == 'movie':
                #(title, year) = (response.get('Title',None),response.get('Year',None) )
        end_time = time.time()
        logger.info('Best match for title "%s" found in %.2f s: imdbID %d'%(title, end_time-start_time, best_match))
        return best_match


                    
def str2int_imdb(imdb):
    """Convert imdbID in string format to int
    """        
    if not imdb:
        return None
    if type(imdb) == int:
        return imdb
    else:
        match = re.search(r"t{0,2}(\d+)", imdb)
        if match:
            return int(match.group(1))
        else:
            return None

def int2str_imdb(imdb):
    """Convert imdbID in string format to int
    """        
    if type(imdb) is int:
        return 'tt%.7d' % imdb
    elif type(imdb) is str:
        match = re.search(r"t{0,2}(\d+)", imdb)
        if match:
            return 'tt' + match.group(1)
        else:
            return None
    else:
        return None

def omdb_search(query, year=None, match='string', n_match=None, **kwargs):
    """Search for information on omdbapi.com with title and (optional) year.
      `match` defines what to look for.

    :param string query: title of the video, or imdbID (ex.: 'tt1234567')
    :param double year: year of the video. Default None
    :param string match: 'string', 'title', 'imdbid' . Perform a query which matches the `title` or the `imdbid`. `string` returns a list of answers, the number of answers is defined by `n_match`.
    :param int n_match: if `match` is `string`, number of matches to return in the list.
    :param kwargs: arguments to add to the url. Ex: omdb_search(query, y=2003) to add '&y=2003' to the url
    :return: found movie
    :rtype: dict with keys such as: Title, Year, imdbID, Type.
              for perfect match:  Language, Country, Director, Writer, Actors, Plot, Poster, Runtime, Rating, Votes, Genre, Released, Rated
    """
    if not query:
        logger.debug('Query is empty: %r' % (type(query)))
        return dict()
    
    #: omdbapi.com url
    omdbapi_url = "http://www.omdbapi.com/?"

    query = query.encode("utf-8")
    match_search = 's'
    if match == 'title':
        match_search = 't'
    if match == 'imdbid':
        match_search = 'i'

    params = {'r':'json', match_search: query}
    if year:
        params.update({'y':year})
    params.update(kwargs)

    url = omdbapi_url + urlencode(params)
    try:
        data = urlopen(url).read().decode("utf-8")
        data = json.loads(data)
    except Exception as e:
        logger.debug('Error with url %r:\n %r'%(url, e))
        return dict()
        
    if data.get("Response") == "False":
        logger.debug(data.get("Error", "Unknown error"))
        return dict()

    if match in ('title', 'imdbid'):
        logger.debug('Information found for video %r: %r' %(query, data))
        return data
    else:
        ## Return only the first n_match. All if n_match is None
        if type(n_match) != int:
            n_match = None
        elif n_match > len(data.get("Search", [])):
            n_match = None

        result = data.get("Search", [])[:n_match]
        logger.debug('Search results for video %r: %r' %(query, result))
        return result

Response = namedtuple('Response', ['type', 'api_version',
                                   'heading', 'result',
                                   'related', 'definition',
                                   'abstract', 'redirect',
                                   'answer', 'error_code', 
                                   'error_msg'])
Result = namedtuple('Result', ['html',
                               'text', 'url',
                               'icon'])
Related = namedtuple('Related', ['html', 'text',
                                 'url', 'icon'])
Definition = namedtuple('Definition', ['primary','url', 'source'])

Abstract = namedtuple('Abstract', ['primary', 'url', 
                                   'text', 'source'])
Redirect = namedtuple('Redirect', ['primary',])
Icon = namedtuple('Icon', ['url', 'width', 'height'])
Topic = namedtuple('Topic',['name', 'results'])
Answer = namedtuple('Answer', ['primary', 'type'])

def ddg_query(query, bang=None, useragent='python-duckduckgo '+str(__ddg_version__), redirect=False, safesearch=True, html=False, meanings=True, **kwargs):
    """
    Query DuckDuckGo, returning a Results object.

    Here's a query that's unlikely to change:

    >>> result = ddg_query('1 + 1')
    >>> result.type
    'nothing'
    >>> result.answer.text
    '1 + 1 = 2'
    >>> result.answer.type
    'calc'

    Keword arguments:
    useragent: UserAgent to use while querying. Default: "python-duckduckgo %d" (str)
    safesearch: True for on, False for off. Default: True (bool)
    html: True to allow HTML in output. Default: False (bool)
    meanings: True to include disambiguations in results (bool)
    Any other keyword arguments are passed directly to DuckDuckGo as URL params.
    """ % __ddg_version__

    base_url = 'http://api.duckduckgo.com/?'
    safesearch = '1' if safesearch else '-1'
    html = '0' if html else '1'
    meanings = '0' if meanings else '1'
    no_redirect = '0' if redirect else '1'
    params = {
        'q': query,
        'o': 'json',
        'kp': safesearch,
        'no_redirect': no_redirect,
        'no_html': html,
        'd': meanings,
        }
    params.update(kwargs)
    encparams = urlencode(params)
    if bang:
        encparams = string.replace(encparams, 'q=', 'q=!%s+'%(bang))
    url = base_url + encparams
    request = Request(url, headers={'User-Agent': useragent})
    try:
        response = urlopen(request)
    except URLError, e:
        return Response(type='Error', api_version=__ddg_version__,
                        heading=None, redirect=None,
                        abstract=None,
                        definition=None,
                        answer=None,
                        related=None,
                        result=None, error_code=1,
                        error_msg=str(e))

    try:
        js = json.loads(response.read())
    except Exception, e:
        return Response(type='Error', api_version=__ddg_version__,
                        heading=None, redirect=None,
                        abstract=None,
                        definition=None,
                        answer=None,
                        related=None,
                        result=None, error_code=2,
                        error_msg='Data from api malformed')

    response.close()

    return process_results(js)

def imdb_query(query, bang=None):
    
    r = ddg_query('imbd ' + query, bang=bang)
    if 'redirect' in dir(r) and 'primary' in dir(r.redirect):
        url = r.redirect.primary
    else:
        logger.info('Could not find imdb searchpage from DuckDuckGo bang')
        return None
    
    br = Browser()
    br.set_handle_robots(False)
    br.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 6.2;\
                        WOW64) AppleWebKit/537.11 (KHTML, like Gecko)\
                        Chrome/23.0.1271.97 Safari/537.11')]

    r = br.open(url)
    soup = BeautifulSoup(r)


    for link in soup.find_all('a'):
        href = link.get('href','')
        match = re.search(r"imdb\.com/.*tt([^/]*)", href)
        if match:
            imdb_id = int(match.group(1))
            return imdb_id
    
    return None

def result_deserialize(dataset, obj_type):
    d = dataset
    topics = None
    if 'Topics' in d:
        results = [result_deserialize(t, Result) for t in d['Topics']]
        return Topic(d['Name'], results=results)
    text = d['Text']
    url = d['FirstURL']
    html = d['Result']
    i_url = d['Icon']['URL']
    i_width = d['Icon']['Width']
    i_height = d['Icon']['Height']
    icon = None
    if i_url != '':
        icon = Icon(url=i_url, width=i_width,
                    height=i_height)
    dt = obj_type(text=text, url=url, html=html,
                      icon=icon)
    return dt

def search_deserialize(dataset, prefix, obj_type):
    if dataset[prefix] == '':
        return None
    keys = dataset.keys()
    required = filter(lambda x: x.startswith(prefix) and x != prefix, keys)
    unq_required = [r.split(prefix)[1].lower() for r in required]
    args = {ur: dataset[r] for ur, r in map(None, unq_required, required)}
    if prefix in dataset:
        args['primary'] = dataset[prefix]
    return obj_type(**args)

def process_results(js):
    resp_type = {'A': 'answer', 
                 'D': 'disambiguation',
                 'C': 'category',
                 'N': 'name',
                 'E': 'exclusive', 
                 '': 'nothing'}.get(js.get('Type',''), '')
    if resp_type == 'Nothing':
        return Response(type='nothing', api_version=0.242, heading=None, 
                        result=None, related=None, definition=None, 
                        abstract=None, redirect=None, answer=None,
                        error_code=0, error_msg=None)
    
    redirect = search_deserialize(js, 'Redirect', Redirect)
    abstract = search_deserialize(js, 'Abstract', Abstract)
    definition = search_deserialize(js, 'Definition', Definition)
    js_results = js.get('Results', [])
    results = [result_deserialize(jr, Result) for jr in js_results]
    js_related = js.get('RelatedTopics', [])
    related = [result_deserialize(jr, Related) for jr in js_related]
    answer = search_deserialize(js, 'Answer', Answer)
    return Response(type=resp_type, api_version=__ddg_version__,
                    heading='', redirect=redirect,
                    abstract=abstract,
                    definition=definition,
                    answer=answer,
                    related=related,
                    result=results, error_code=0,
                    error_msg=None)

