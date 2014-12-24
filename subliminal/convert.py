# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
import subprocess
import os
import traceback
import difflib
import logging
import babelfish
import enzyme
#from .subtitle import get_subtitle_path
from subliminal.subtitle import get_subtitle_path
from subliminal.video import Video, Movie, Episode
#from subliminal.video import scan_subtitle_languages

#: COUNTRY LONG NAMES
LONG_COUNTRIES = {v:k for k, v in babelfish.COUNTRIES.iteritems()}

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

def scan_available_subtitle_languages(path, sub_extensions='.srt'):
    """Search for '.srt' subtitles with alpha2 extension from a video `path` and return their language

    :param string path: path to the video
    :return: found subtitle languages
    :rtype: set

    """
    language_extensions = tuple('.' + c for c in babelfish.language_converters['alpha2'].codes)
    dirpath, filename = os.path.split(path)
    subtitles = set()
    for pp in os.listdir(dirpath):
        p = pp
        if isinstance(pp, bytes):
           p = pp.decode('utf8')
        if p.startswith(os.path.splitext(filename)[0]) and p.endswith(sub_extensions):
            if os.path.splitext(p)[0].endswith(language_extensions):
                subtitles.add(babelfish.Language.fromalpha2(os.path.splitext(p)[0][-2:]))
            else:
                subtitles.add(babelfish.Language('und'))
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
            video.imdb_update()
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

def simlink_movie(video, savepath, real_path_video, sort_by=['country','genre']):
    """Create a symbolic link of the video to the country and arborescence

    :param video: video to sort
    :param savepath: root path for the video arborescence
    :param real_path_video: real path of the video that the softlink will direct to.
    :param list sort_by: List of parameters to make an arborescence with. For ex., 'country', will create the arborescence savepath/By country/<video country>/softlink 
    """
    if not os.path.isfile(real_path_video):
        logger.info("Original video does not exist: '%s'" % real_path_video)
        return

    available_sorting = {'lang':'Langue', 'country':'Pays', 'genre':'Genre'}
    if isinstance(video, Episode):
        # Only for Movie type of vidoes
        return
    if not video.imdb_id:
        video.getimdb()
    for sort in sort_by:
        if sort not in available_sorting:
            return

        if not video.__dict__.get(sort, None) and video.imdb_id:
            video.imdb_update()
        if video.__dict__.get(sort, None):
            Kinds = video.__dict__.get(sort, '').split(', ')
            for kind in Kinds: 
                arborescence = os.path.join("Films", "Par %s" %(available_sorting[sort].title()), kind.title())
                link_path = os.path.join(savepath, arborescence)
                # Create symbolic link directory
                if not os.path.isdir(link_path):
                    os.makedirs(link_path)
                dst = os.path.join(link_path, os.path.basename(real_path_video))
                if os.path.islink(dst):
                    # Remove symlink if it already exists
                    os.remove(dst)                    
                    logger.info("Destination link already exists, overwritten: '%s'" % dst) 
                # Create symbolic link
                os.symlink(os.path.realpath(real_path_video), dst)
                logger.info("Symbolic link created at: '%s'" % dst) 
    return  

def convert_videos(videos, languages=None, language=babelfish.Language('eng'), subtitles_format='.srt', video_format='.mkv', video_savepath=None, single=True, delete_subtitles=False, force_copy=False, force_mkvmerge=False, create_soft_link=True):
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
        logger.info('Language not specified, `und` chosen')
        language = babelfish.Language('und')
    if not languages and not single:
        if not language:
            logger.warning('At least one language must be selected')
            return convert_videos
        else:
            logger.info('%r selected', language)
            languages = {language}
    logger.debug('Subtitles to embed: %r', languages)
    if not videos:
        logger.info('No video to convert')
        return converted_videos
    loglevel = logger.getEffectiveLevel()
    for video in videos:
        path = video.name
        input_path = path
        embedded_subtitles = set()
        try:
            dirpath, filename = os.path.split(path)
            Name, VideoExtension = os.path.splitext(filename)
            logger.debug('Video %r is being converted', filename)
            
            sformat = '.' + subtitles_format.strip('.')
            outformat = '.' + video_format.strip('.')
            #lang = language.alpha3

            # define path for the output video and check if the output video already exists
            if video_savepath:
                output_video_path = sort_video(video, video_savepath)
            else:
                output_video_path = dirpath
            
#            # define path for the output video and check if the output video already exists
#            if video_savepath:
#                outpath = video_savepath
#            else:
#                outpath = dirpath
#            extrapath=""
#            if full_sorting:
#                extrapath=sort_video(video, outpath)
            if not video.title is None:
                try:
                    Name = "%02d - %s" % (video.episode, video.title)
                except AttributeError:
                    Name = video.title
#            outvid_apath = os.path.join(outpath, extrapath, Name + outformat)
            outvid_apath = os.path.join(output_video_path, Name + video_format)
            if os.path.isfile(outvid_apath) and (not force_copy):
#            if os.path.isfile(output_video) and (not force_copy):
                # check if .mkv contains the subtitles for these languages   
                embedded_subtitles = scan_embedded_subtitle_languages(outvid_apath)
                logger.info('Embedded subtitles : %r', embedded_subtitles)
                # avoid video if it has already been encoded with the wanted subtitles
                if  languages <= embedded_subtitles:
                    logger.debug('Video %r already converted', path)
                    continue
                if len(embedded_subtitles)>0:
                    input_path = outvid_apath

            # check which subtitles are available to embed in the video
            available_subtitles = scan_available_subtitle_languages(path, sub_extensions = sformat)
            
            # define the subtitles to be embedded
            embeddable_subtitles = languages.difference(embedded_subtitles) & available_subtitles
            logger.info('Subtitles to be embedded: %r', embeddable_subtitles)

            # for one single subtitle to embed, ffmpeg is used
            if not force_mkvmerge and (single or len(embeddable_subtitles)==1):
                if not single:
                    lang = embeddable_subtitles.pop()
                else:
                    lang = language
                logger.debug('One subtitle to embed, language %r', lang.alpha3)
                insub_apath = get_subtitle_path(path, language=None if single else lang)
                if not os.path.isfile(insub_apath):
                    logger.debug('Subtitle does not exist : %s', insub_apath)
                    continue
                
                # define command to ffmpeg to convert to .mkv and embed subtitle
                command = ["-i", path, "-i", insub_apath, "-c", "copy", "-metadata:s:s:0", "language=%s"%(lang.alpha3), outvid_apath]

                if loglevel >= 20:
                    command = ["ffmpeg", "-loglevel", "panic"] + command
                else:
                    command = ["ffmpeg"] + command

		logger.debug("Launching : '%s'", " ".join(command))
                Proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = Proc.communicate()
                logger.info('Converting video %s ------', filename)
                if stdout:
                    logger.info(stdout)
                if stderr:
                    logger.error(stderr)
                Proc.wait()
                logger.info('---- Conversion finished.')
                converted_videos.add(path)

                # delete subtitle .srt files after conversion
                if delete_subtitles:
                    try:
                        os.remove(insub_apath)
                        logger.info('Subtitle file removed: %s', os.path.split(insub_apath)[1])
                    except OSError as e: # name the Exception `e`
                        logger.info("Failed with: %r", e.strerror) 
                        logger.info("Error code: %r", e.code) 
            
            # for multiple subtitles, mkvmerge is used
            elif (force_mkvmerge and len(embeddable_subtitles)>=0) or (not single and len(embeddable_subtitles)>=2):
                command = []
                if loglevel >= 30:
                    command = ['-q']
                elif loglevel == 10:
                    command = ['-v']
                  
                # Use input_path not to overwrite existing .mkv file
                command = ['mkvmerge'] + command +['-o', outvid_apath, input_path]
                for lang in embeddable_subtitles:
                    logger.debug('... embed %r subtitle', lang.alpha3)

                    # check if subtitle exists
                    insub_apath = get_subtitle_path(path, language=lang)
                    #insub_apath = os.path.join(dirpath, Name + sformat)
                    if not os.path.isfile(insub_apath):
                        logger.debug('Subtitle does not exist : %s', insub_apath)
                        continue
                    
                    # define command to mkvmerge to embed the subtitle with `lang` language
                    command += ['--language', '0:%s'%(lang.alpha3), insub_apath] 

                logger.debug("Launching : '%s'", " ".join(command))
                Proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = Proc.communicate()
                logger.info('Converting video %s ------', filename)
                if stdout:
                    logger.info(stdout)
                if stderr:
                    logger.error(stderr)
                Proc.wait()
                logger.info('---- Conversion finished.')
                converted_videos.add(path)
                    
                # delete subtitle .srt files after conversion
                if delete_subtitles:
                    for lang in embeddable_subtitles:
                        # check if subtitle exists
                        insub_apath = get_subtitle_path(path, language=lang)
                        #insub_apath = os.path.join(dirpath, Name + sformat)
                        if not os.path.isfile(insub_apath):
                            logger.debug('Subtitle does not exist : %s', insub_apath)
                            continue
                        try:
                            os.remove(insub_apath)
                            logger.info('Subtitle file removed: %s', os.path.split(insub_apath)[1])
                        except OSError as e: # name the Exception `e`
                            logger.info("Failed with: %r", e.strerror) 
                            logger.info("Error code: %r", e.code) 
            else:
                logger.debug('No subtitles to embed')

            # Create second arborescence for Movies with symbolic links
            if video_savepath is not None and create_soft_link:
                try:
                    simlink_movie(video, video_savepath, outvid_apath)
                except OSError as e:
                    logger.info("Symlink creation failed with: {} {}".format(e.code, e.strerror))

        except Exception as e: # name the Exception `e`
            logger.exception("Failed to convert video %r : %r", path, e) 
            # continue to next video if error occured in one video
            continue 
    return converted_videos
