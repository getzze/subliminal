# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import subprocess
import os
import traceback
import re
import difflib
import logging
from babelfish import Error as BabelfishError, Language
import enzyme
from subliminal.subtitle import get_subtitle_path
from subliminal.video import Video, Movie, Episode

logger = logging.getLogger(__name__)

def scan_embedded_subtitle_languages(path):
    """Search for embedded subtitles from a video `path` and return their language

    :param string path: path to the video
    :return: found subtitle languages
    :rtype: set

    """
    dirpath, filename = os.path.split(path)
    subtitles = set()
    # enzyme
    try:
        if filename.endswith('.mkv'):
            with open(path, 'rb') as f:
                mkv = enzyme.MKV(f)
            if mkv.subtitle_tracks:
                # embedded subtitles
                for st in mkv.subtitle_tracks:
                    if st.language:
                        try:
                            subtitles.add(babelfish.Language.fromalpha3b(st.language))
                        except babelfish.Error:
                            logger.error('Embedded subtitle track language %r is not a valid language', st.language)
                            subtitles.add(babelfish.Language('und'))
                    elif st.name:
                        try:
                            subtitles.add(babelfish.Language.fromname(st.name))
                        except babelfish.Error:
                            logger.error('Embedded subtitle track name %r is not a valid language', st.name)
                            subtitles.add(babelfish.Language('und'))
                    else:
                        subtitles.add(babelfish.Language('und'))
                logger.debug('Found embedded subtitle %r with enzyme', subtitles)
            else:
                logger.debug('MKV has no subtitle track')
    except enzyme.Error:
        logger.error('Parsing video metadata with enzyme failed')
    return subtitles

def scan_external_subtitles(path, default=Language('und'), subtitle_extensions=['.srt']):
    """Search for external subtitles from a video `path` and their associated language.

    :param str path: path to the video.
    :return: found subtitles with their languages.
    :rtype: dict

    """
    dirpath, filename = os.path.split(path)
    dirpath = dirpath or '.'
    fileroot, fileext = os.path.splitext(filename)
    subtitles = {}
    for p in os.listdir(dirpath):
        # keep only valid subtitle filenames
        if not p.startswith(fileroot) or not p.endswith(subtitle_extensions):
            continue

        # extract the potential language code
        language_lookup = os.path.splitext(p)[0][len(fileroot):]
        match = re.search(r'[a-zA-Z]{2,3}[_-]?[a-zA-Z]{2,3}?', language_lookup)
        if match:
            language_code = match.group(0).replace('_', '-')
        else:
            language_code = None

        # default language is undefined
        language = default

        # attempt to parse
        if language_code:
            try:
                language = Language.fromietf(language_code)
            except ValueError:
                logger.error('Cannot parse language code %r', language_code)

        subtitles[p] = language

    logger.debug('Found subtitles %r', subtitles)

    return subtitles

def sort_video(video, savepath):
    """Try to sort the video according to its type and name

    :param video: video to sort
    :param savepath: root path where the file will be stored
    :return extrapath: additional arborescence.
    """
    if isinstance(video, Episode):
        try:
            video.fromimdb()
        except AttributeError:
            logger.debug('Update from imdbID not implemented.')
        series_path = os.path.join(savepath, 'Series')
        series_name=""
        if os.path.exists(series_path):        
            series_name_list=difflib.get_close_matches(video.series, os.walk(os.path.join(savepath, "Series")).next()[1], 1, cutoff=0.8)
            if len(series_name_list)>0:
                series_name=series_name_list[0]
        if len(series_name)==0:
            series_name = video.series
        arborescence = os.path.join("Series", series_name, "Season %d" % video.season)
    elif isinstance(video, Movie):
        arborescence = "Films"
    else:
        logger.info("Video must be Movie or Episode") 
        arborescence = "Others"
    return os.path.join(savepath, arborescence)

def simlink_movie(video, save_dir, video_path, sort_by=['country','genre']):
    """Create a symbolic link of the video to the country and arborescence

    :param video: video to sort
    :param save_dir: root directory for the video arborescence
    :param video_path: real path of the convert video. The softlinks will point to this path.
    :param list sort_by: List of parameters to make an arborescence with. For ex., 'country', will create the arborescence savepath/By country/<video country>/softlink 
    """
    if not os.path.isfile(real_path_video):
        logger.info("Original video does not exist: '%s'" % real_path_video)
        return

    movie_dir = "Films"
    sort_regex = "Par {}" 
    available_sorting = {'lang':'Langue', 'country':'Pays', 'genre':'Genre'}
    if isinstance(video, Episode):
        # Only for Movie type of videos
        return
    if not video.imdb_id:
        video.getimdb()
    links = []
    for sort in sort_by:
        if sort not in available_sorting:
            return

        if not getattr(video, sort, None) and video.imdb_id:
            video.fromimdb()
        if hasattr(video, sort):
            kinds = getattr(video, sort, '').split(', ')
            for kind in kinds: 
                arborescence = os.path.join(movie_dir, sort_regex.format(available_sorting[sort].title()), kind.title())
                link_dir = os.path.join(save_dir, arborescence)
                # Create symbolic link directory
                if not os.path.isdir(link_dir):
                    os.makedirs(link_dir)
                link_dst = os.path.join(link_dir, os.path.basename(video_path))
                if os.path.islink(link_dst):
                    # Remove symlink if it already exists
                    os.remove(link_dst)                    
                    logger.info("Destination link already exists, overwritten: '%s'" % link_dst) 
                # Create symbolic link
                os.symlink(os.path.realpath(video_path), link_dst)
                links.append(link_dst)
                logger.info("Symbolic link created at: '%s'" % link_dst) 
    return links

def ffmpeg_convert(input_video, input_subtitle, lang, output_video, delete_subtitles=False):
    if not os.path.isfile(input_subtitle):
        logger.debug('Subtitle does not exist : %s', input_subtitle)
        return None
    
    # define command to ffmpeg to convert to .mkv and embed subtitle
    command = ["-i", input_video, "-i", input_subtitle, "-c", "copy", "-metadata:s:s:0", "language=%s"%(lang.alpha3), output_video]

    loglevel = logger.getEffectiveLevel()
    if loglevel >= 20:
        command = ["ffmpeg", "-loglevel", "panic"] + command
    else:
        command = ["ffmpeg"] + command

    logger.debug("Launching : '%s'", " ".join(command))
    Proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = Proc.communicate()
    
    video_dir, filename = os.path.split(input_video)
    logger.info('Converting video %s ------', filename)
    if stdout:
        logger.info(stdout)
    if stderr:
        logger.error(stderr)
    Proc.wait()
    logger.info('---- Conversion finished.')

    # delete subtitle .srt files after conversion
    if delete_subtitles:
        try:
            os.remove(input_subtitle)
            logger.info('Subtitle file removed: %s', os.path.split(input_subtitle)[1])
        except OSError as e:
            logger.exception("Could not remove subtitle file.")
            #logger.info("Failed with: %r", e.strerror) 
            #logger.info("Error code: %r", e.code) 
    return output_video

def mkvmerge_convert(input_video, embeddable_subtitles, output_video, delete_subtitles=False):
    command = []
    loglevel = logger.getEffectiveLevel()
    if loglevel >= 30:
        command = ['-q']
    elif loglevel == 10:
        command = ['-v']
      
    command = ['mkvmerge'] + command +['-o', output_video, input_video]
    for lang, input_subtitle in embeddable_subtitles.items():
        logger.debug('... embed %r subtitle', lang.alpha3)
        
        # check if subtitle exists
        input_subtitle = input_subtitle[0] # first subtitle
        if not os.path.isfile(input_subtitle):
            logger.debug('Subtitle does not exist : %s', input_subtitle)
            return None
        
        # define command to mkvmerge to embed the subtitle with `lang` language
        command += ['--language', '0:%s'%(lang.alpha3), input_subtitle] 

    logger.debug("Launching : '%s'", " ".join(command))
    Proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = Proc.communicate()

    video_dir, filename = os.path.split(input_video)
    logger.info('Converting video %s ------', filename)
    if stdout:
        logger.info(stdout)
    if stderr:
        logger.error(stderr)
    Proc.wait()
    logger.info('---- Conversion finished.')
        
    # delete subtitle .srt files after conversion
    if delete_subtitles:
        for lang in embeddable_subtitles.keys():
            # check if subtitle exists
            input_subtitle = get_subtitle_path(input_video, language=lang)
            if not os.path.isfile(input_subtitle):
                logger.debug('Subtitle does not exist : %s', input_subtitle)
                continue
            try:
                os.remove(input_subtitle)
                logger.info('Subtitle file removed: %s', os.path.split(input_subtitle)[1])
            except OSError as e: # name the Exception `e`
                logger.exception("Could not remove subtitle file.")
                #logger.info("Failed with: %r", e.strerror) 
                #logger.info("Error code: %r", e.code) 
    return output_video

def convert_video(video, languages=set(), subtitles_format='.srt', video_format='.mkv', subtitles=None, save_dir=None, single=True, delete_subtitles=False, force_copy=False, force_mkvmerge=False, create_soft_link=True):
    """Convert `video` in .mkv using ffmpeg, including subtitles with the existing languages if not specified by `languages`.

    :param video: video to convert in .mkv
    :type video: :class:`~subliminal.video.Video`
    :param languages: languages of subtitles to include in .mkv
    :type languages: set of :class:`babelfish.Language`
    :param str subtitles_format: subtitles format to be embedded in the video, only '.srt' is defined
    :param str video_format: format of the converted video, only '.mkv' is defined
    :param subtitles: subtitles to embed in the .mkv
    :type subtitles: dict with the subtitle paths as keys and language as values
    :param str save_dir: directory to save the output video. Same as input video if None.
    :param bool delete_subtitles: delete .srt file after conversion
    :param bool force_copy: do not take into account already existing .mkv files
    """
    if not video:
        logger.info('No video to convert')
        return None
    if not languages:
        logger.info('At least one language must be selected')
        return None
    logger.debug('Subtitles to embed: %r', languages)

    path = video.name
    input_video_path = path
    embedded_subtitles = set()

    video_dir, filename = os.path.split(path)
    name, extension = os.path.splitext(filename)
    logger.debug('Video %r is being converted', filename)
    
    # define path for the output video and check if the output video already exists
    if save_dir:
        output_video_dir = sort_video(video, save_dir)
    else:
        output_video_dir = video_dir
    
    if video.title is not None:
        try:
            name = "%02d - %s" % (video.episode, video.title)
        except AttributeError:
            name = video.title

    output_video_path = os.path.join(output_video_dir, name + video_format)
    if os.path.isfile(output_video_path) and (not force_copy):
        # check if .mkv contains the subtitles for these languages   
        embedded_subtitles = scan_embedded_subtitle_languages(output_video_path)
        logger.info('Embedded subtitles : %r', embedded_subtitles)
        # avoid video if it has already been encoded with the wanted subtitles
        if  languages <= embedded_subtitles:
            logger.debug('Video %r already converted', path)
            return video
        if len(embedded_subtitles)>0:
            input_video_path = output_video_path

    # check which subtitles are available to embed in the video
    if subtitles:
        available_subtitles = subtitles
    else: 
        available_subtitles = scan_external_subtitles(path, default=list(languages)[0], subtitle_extensions=[subtitles_format])
    
    # define the subtitles to be embedded
    embeddable_subtitles = {}
    for p, lang in available_subtitles.items():
       if lang not in embedded_subtitles:
          embeddable_subtitles[lang] = embeddable_subtitles.get(lang, [])
          embeddable_subtitles[lang].append(os.path.join(video_dir, p))

    logger.info('Subtitles to be embedded: %r', embeddable_subtitles)

    # for one single subtitle to embed, ffmpeg is used
    if not force_mkvmerge and (single or len(embeddable_subtitles)==1):
        if not single:
            lang, input_subtitle_path = embeddable_subtitles.popitem()
            input_subtitle_path = input_subtitle_path[0]   # first subtitle 
        else:
            lang = languages.pop()
            input_subtitle_path = embeddable_subtitles.get(lang)[0]
        logger.debug('One subtitle to embed, language %r', lang.alpha3)

        converted_video = ffmpeg_convert(path, input_subtitle_path, lang, output_video_path, delete_subtitles=delete_subtitles)
    
    # for multiple subtitles, mkvmerge is used
    elif (force_mkvmerge and len(embeddable_subtitles)>=0) or (not single and len(embeddable_subtitles)>=2):
        # Use input_video_path not to overwrite existing .mkv file
        converted_video = mkvmerge_convert(input_video_path, embeddable_subtitles, output_video_path, delete_subtitles=delete_subtitles)

    else:
        logger.debug('No subtitles to embed')
        converted_video = output_video_path

    if converted_video is None:
        return None

    # Create second arborescence for Movies with symbolic links
    if save_dir is not None and create_soft_link:
        try:
            simlink_movie(video, save_dir, converted_video)
        except OSError as e:
            logger.exception("Symlink creation failed.")
            #logger.info("Symlink creation failed with: {} {}".format(e.code, e.strerror))

    return converted_video

def convert_videos(videos, languages=None, language=None, subtitles_format='.srt', video_format='.mkv', video_savepath=None, single=True, delete_subtitles=False, force_copy=False, force_mkvmerge=False, create_soft_link=True):
    """Convert `videos` in .mkv using ffmpeg, including subtitles with the existing languages if not specified by `languages`.

    :param videos: videos to convert in .mkv
    :type videos: set of :class:`~subliminal.video.Video`
    :param languages: languages of subtitles to include in .mkv
    :type languages: set of :class:`babelfish.Language`
    :param language: language for a single subtitle, or with `single` set to True.
    :type languages: :class:`babelfish.Language`
    :param str subtitles_format: subtitles format to be embedded in the video, only 'srt' is defined
    :param str video_format: format of the converted video, only 'mkv' is defined
    :param str video_savepath: path to save the output video. Same as input video if None.
    :param str loglevel: loglevel, default 'WARNING', set to 'DEBUG' to show strout from ffmpeg
    :param bool delete_subtitles: delete .srt file after conversion
    :param bool force_copy: do not take into account already existing .mkv files
    """
    converted_videos = set()
    if not language and single:
        logger.info('Language not specified, `eng` chosen')
        language = Language('eng')
        
    if not languages and not single:
        if not language:
            logger.warning('At least one language must be selected')
            return set()
        else:
            logger.info('%r selected', language)
            languages = {language}

    logger.debug('Subtitles to embed: %r', languages)
    if not videos:
        logger.info('No video to convert')
        return set()

    subtitles_format = '.' + subtitles_format.strip('.')
    video_format = '.' + video_format.strip('.')

    for video in videos:
        converted_video = convert_video(video, languages=languages, subtitles_format=subtitles_format, video_format=video_format, susbtitles=subtitles, save_dir=save_dir, single=single, delete_subtitles=delete_subtitles, force_copy=force_copy, force_mkvmerge=force_mkvmerge, create_soft_link=create_soft_link, loglevel=loglevel)
        if converted_video:
            converted_videos.add(video)
    return converted_videos
