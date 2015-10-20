# -*- coding: utf-8 -*-


def test_video_get_imdb_movie(movies):
    video = movies['man_of_steel']
    video.get_imdb()
    assert video.imdb_id == 'tt0770828'


def test_video_get_imdb_episode(episodes):
    video = episodes['dallas_s01e03']
    video.get_imdb()
    assert video.imdb_id == 'tt2205526'
    assert video.series_imdb_id == 'tt1723760'


def test_fromimdb_movie(movies):
    video = movies['man_of_steel']
    video.imdb_id = 'tt0770828'
    video.fromimdb()
    assert video.title == "Man of Steel"
    assert video.country == 'USA, Canada, UK'
    assert video.genre == 'Action, Adventure, Fantasy'
    assert video.lang == 'English'


def test_fromimdb_episode(episodes):
    video = episodes['dallas_s01e03']
    video.imdb_id = 'tt2205526'
    video.series_imdb_id = 'tt1723760'
    video.fromimdb()
    assert video.series == "Dallas"
    assert video.title == "The Price You Pay"
    assert video.lang == 'English'
