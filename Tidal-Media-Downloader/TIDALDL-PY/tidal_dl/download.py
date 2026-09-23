#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   download.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :
'''
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor

from decryption import *
from printf import *
from tidal import *

def get_file_type(file_path):
    """Uses the 'file' command to determine the true file type."""
    try:
        result = subprocess.run(['file', file_path], capture_output=True, text=True, check=True)
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error checking file type for {file_path}: {e}")
        return None

def __isSkip__(finalpath, url):
    if not SETTINGS.checkExist:
        return False
    curSize = aigpy.file.getSize(finalpath)
    if curSize <= 0:
        return False
    netSize = aigpy.net.getSize(url)
    return curSize >= netSize


def __encrypted__(stream, srcPath, descPath):
    if aigpy.string.isNull(stream.encryptionKey):
        os.replace(srcPath, descPath)
    else:
        key, nonce = decrypt_security_token(stream.encryptionKey)
        decrypt_file(srcPath, descPath, key, nonce)
        os.remove(srcPath)


def __parseContributors__(roleType, Contributors):
    if Contributors is None:
        return None
    try:
        ret = []
        for item in Contributors['items']:
            if item['role'] == roleType:
                ret.append(item['name'])
        return ret
    except:
        return None


def __setMetaData__(track: Track, album: Album, filepath, contributors, lyrics):
    obj = aigpy.tag.TagTool(filepath)
    obj.album = track.album.title
    obj.title = track.title
    if not aigpy.string.isNull(track.version):
        obj.title += ' (' + track.version + ')'

    obj.artist = list(map(lambda artist: artist.name, track.artists))
    obj.copyright = track.copyRight
    obj.tracknumber = track.trackNumber
    obj.discnumber = track.volumeNumber
    obj.composer = __parseContributors__('Composer', contributors)
    obj.isrc = track.isrc

    obj.albumartist = list(map(lambda artist: artist.name, album.artists))
    obj.date = album.releaseDate
    obj.totaldisc = album.numberOfVolumes
    obj.lyrics = lyrics
    if obj.totaldisc <= 1:
        obj.totaltrack = album.numberOfTracks
    coverpath = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    obj.save(coverpath)


def downloadCover(album):
    if album is None:
        return
    path = getAlbumPath(album) + '/cover.jpg'
    url = TIDAL_API.getCoverUrl(album.cover, "1280", "1280")
    aigpy.net.downloadFile(url, path)


def downloadAlbumInfo(album, tracks):
    if album is None:
        return

    path = getAlbumPath(album)
    aigpy.path.mkdirs(path)

    path += '/AlbumInfo.txt'
    infos = ""
    infos += "[ID]          %s\n" % (str(album.id))
    infos += "[Title]       %s\n" % (str(album.title))
    infos += "[Artists]     %s\n" % (TIDAL_API.getArtistsName(album.artists))
    infos += "[ReleaseDate] %s\n" % (str(album.releaseDate))
    infos += "[SongNum]     %s\n" % (str(album.numberOfTracks))
    infos += "[Duration]    %s\n" % (str(album.duration))
    infos += '\n'

    for index in range(0, album.numberOfVolumes):
        volumeNumber = index + 1
        infos += f"===========CD {volumeNumber}=============\n"
        for item in tracks:
            if item.volumeNumber != volumeNumber:
                continue
            infos += '{:<8}'.format("[%d]" % item.trackNumber)
            infos += "%s\n" % item.title
    aigpy.file.write(path, infos, "w+")


def downloadVideo(video: Video, album: Album = None, playlist: Playlist = None):
    try:
        stream = TIDAL_API.getVideoStreamUrl(video.id, SETTINGS.videoQuality)
        path = getVideoPath(video, album, playlist)

        Printf.video(video, stream)
        logging.info("[DL Video] name=" + aigpy.path.getFileName(path) + "\nurl=" + stream.m3u8Url)

        m3u8content = requests.get(stream.m3u8Url).content
        if m3u8content is None:
            Printf.err(f"DL Video[{video.title}] getM3u8 failed.{str(e)}")
            return False, f"GetM3u8 failed.{str(e)}"

        urls = aigpy.m3u8.parseTsUrls(m3u8content)
        if len(urls) <= 0:
            Printf.err(f"DL Video[{video.title}] getTsUrls failed.{str(e)}")
            return False, "GetTsUrls failed.{str(e)}"

        check, msg = aigpy.m3u8.downloadByTsUrls(urls, path)
        if check:
            Printf.success(video.title)
            return True
        else:
            Printf.err(f"DL Video[{video.title}] failed.{msg}")
            return False, msg
    except Exception as e:
        Printf.err(f"DL Video[{video.title}] failed.{str(e)}")
        return False, str(e)


def downloadTrack(track: Track, album=None, playlist=None, userProgress=None, partSize=1048576):
    try:
        stream = TIDAL_API.getStreamUrl(track.id, SETTINGS.audioQuality)
        path = getTrackPath(track, stream, album, playlist)

        # STRICT WAV CHECK REMOVED
        # if 'wav' not in stream.codec:
        #     Printf.err(f"Skipping '{track.title}': Codec is '{stream.codec}', not WAV. (User requested WAV only)")
        #     return False, 'Skipped: Not WAV'
        
        # STRICT HIFI/MASTER CHECK
        if stream.soundQuality not in ['HIGH', 'LOSSLESS', 'HI_RES', 'HI_RES_LOSSLESS']:
            Printf.err(f"Skipping '{track.title}': Quality is '{stream.soundQuality}', not High/HiFi/Master.")
            return False, f"Skipped: Quality is {stream.soundQuality}, not High/HiFi/Master"

        if SETTINGS.showTrackInfo and not SETTINGS.multiThread:
            Printf.track(track, stream)

        if userProgress is not None:
            userProgress.updateStream(stream)

        # check exist
        if __isSkip__(path, stream.url):
            Printf.success(aigpy.path.getFileName(path) + " (skip:already exists!)")
            return True, ''

        # download
        logging.info("[DL Track] name=" + aigpy.path.getFileName(path) + "\nurl=" + stream.url)

        tool = aigpy.download.DownloadTool(path + '.part', stream.urls)
        tool.setUserProgress(userProgress)
        tool.setPartSize(partSize)
        check, err = tool.start(SETTINGS.showProgress and not SETTINGS.multiThread)
        if not check:
            Printf.err(f"DL Track '{track.title}' failed: {str(err)}")
            return False, str(err)

        # encrypted -> decrypt and remove encrypted file
        __encrypted__(stream, path + '.part', path)

        # check file type and rename if necessary
        try:
            file_type_info = get_file_type(path)
            if file_type_info and ('.flac' in path.lower()) and ('iso media' in file_type_info.lower() or 'mp4' in file_type_info.lower()):
                base, _ = os.path.splitext(path)
                new_path = base + '.m4a'
                os.rename(path, new_path)
                path = new_path
                Printf.info(f"Renamed to {os.path.basename(path)}")
        except Exception as e:
            Printf.err(f"Could not check/rename file: {e}")

        # VERIFY ACTUAL CODEC (Paranoid Check)
        try:
            probe_cmd = [
                'ffprobe', 
                '-v', 'error', 
                '-select_streams', 'a:0', 
                '-show_entries', 'stream=codec_name', 
                '-of', 'default=noprint_wrappers=1:nokey=1', 
                path
            ]
            codec_result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            actual_codec = codec_result.stdout.strip().lower()

            if actual_codec == 'aac' and stream.soundQuality != 'HIGH':
                Printf.err(f"Skipped: Actual content is AAC (Lossy) despite metadata promises. File deleted.")
                os.remove(path)
                return False, 'Skipped: Fake FLAC (AAC detected)'
            
            if actual_codec == 'aac':
                Printf.success(f"Accepted Lossy Codec (Quality is HIGH): {actual_codec}")
            else:
                Printf.success(f"Verified Lossless Codec: {actual_codec}")

        except Exception as e:
            Printf.err(f"Warning: Could not verify codec with ffprobe (proceeding anyway): {e}")

        # CONVERT TO WAV
        try:
            base, ext = os.path.splitext(path)
            wav_path = base + ".wav"
            
            # Use ffmpeg to convert to WAV (PCM 16-bit or 24-bit depending on source, let ffmpeg decide or force high quality)
            # -y overwrites output
            # -loglevel error quiets output
            cmd = ['ffmpeg', '-y', '-i', path, wav_path, '-loglevel', 'error']
            
            # Run conversion
            subprocess.run(cmd, check=True)
            
            if os.path.exists(wav_path):
                # Remove original file (FLAC/M4A)
                os.remove(path)
                path = wav_path
                Printf.success(f"Converted to WAV: {os.path.basename(path)}")
            else:
                Printf.err(f"WAV conversion failed (output not found) for {os.path.basename(path)}")

        except Exception as e:
            Printf.err(f"Error converting to WAV: {e}")


        # contributors
        try:
            contributors = TIDAL_API.getTrackContributors(track.id)
        except:
            contributors = None

        # lyrics
        try:
            lyrics = TIDAL_API.getLyrics(track.id).subtitles
            if SETTINGS.lyricFile:
                lrcPath = path.rsplit(".", 1)[0] + '.lrc'
                aigpy.file.write(lrcPath, lyrics, 'w')
        except:
            lyrics = ''

        __setMetaData__(track, album, path, contributors, lyrics)
        Printf.success(track.title)

        return True, ''
    except Exception as e:
        Printf.err(f"DL Track '{track.title}' failed: {str(e)}")
        return False, str(e)


def downloadTracks(tracks, album: Album = None, playlist: Playlist = None):
    failed_tracks = []

    def __getAlbum__(item: Track):
        album = TIDAL_API.getAlbum(item.album.id)
        if SETTINGS.saveCovers and not SETTINGS.usePlaylistFolder:
            downloadCover(album)
        return album

    def __download__(item: Track, itemAlbum: Album, playlist: Playlist):
        success, msg = downloadTrack(item, itemAlbum, playlist)
        if not success:
            failed_tracks.append(item)

    if not SETTINGS.multiThread:
        for index, item in enumerate(tracks):
            itemAlbum = album
            if itemAlbum is None:
                itemAlbum = __getAlbum__(item)
                item.trackNumberOnPlaylist = index + 1
            __download__(item, itemAlbum, playlist)
    else:
        thread_pool = ThreadPoolExecutor(max_workers=5)
        for index, item in enumerate(tracks):
            itemAlbum = album
            if itemAlbum is None:
                itemAlbum = __getAlbum__(item)
                item.trackNumberOnPlaylist = index + 1
            thread_pool.submit(__download__, item, itemAlbum, playlist)
        thread_pool.shutdown(wait=True)

    if len(failed_tracks) > 0:
        import time
        for i in range(3):
            Printf.info(f"Retrying {len(failed_tracks)} failed downloads (Attempt {i+1}/3)...")
            time.sleep(5 * (i + 1))
            
            still_failed = []
            for item in failed_tracks:
                itemAlbum = album
                if itemAlbum is None:
                    itemAlbum = __getAlbum__(item)
                success, msg = downloadTrack(item, itemAlbum, playlist)
                if not success:
                    still_failed.append(item)
            
            failed_tracks = still_failed
            if len(failed_tracks) == 0:
                break

        if len(failed_tracks) > 0:
            Printf.err(f"{len(failed_tracks)} tracks failed to download after multiple retries.")
            for item in failed_tracks:
                Printf.err(f"- {item.title}")


def downloadVideos(videos, album: Album, playlist=None):
    for item in videos:
        downloadVideo(item, album, playlist)
