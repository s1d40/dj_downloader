#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   tidal.py
@Time    :   2019/02/27
@Author  :   Yaronzz
@VERSION :   3.0
@Contact :   yaronhuang@foxmail.com
@Desc    :   tidal api
'''
import random
import re
import time
import json
import base64
import logging
import uuid
from typing import List
from xml.etree import ElementTree

import requests
import aigpy

from model import *
from settings import *

# SSL Warnings | retry number
requests.packages.urllib3.disable_warnings()
requests.adapters.DEFAULT_RETRIES = 5


class TidalAPI(object):
    def __init__(self):
        self.key = LoginKey()
        self.apiKey = {'clientId': 'OmDtrzFgyVVL6uW56OnFA2COiabqm',
                       'clientSecret': 'zxen1r3pO0hgtOC7j6twMo9UAqngGrmRiWpV7QC1zJ8='}
        self.session = requests.Session()
        self.user_agent = "TIDAL_ANDROID/2.87.1"

    def __handle_response__(self, response, method, path):
        if response.status_code == 200:
            return response.json()
        
        # Handle DataDome / WAF logic
        if response.status_code == 403:
            logging.error(f"Access Denied (403) at {path}. Heuristics block detected.")
            try:
                data = response.json()
                if "cookie" in data:
                    logging.warning("Found DataDome cookie in 403 response. Injecting.")
                    self.session.cookies.set("datadome", data["cookie"])
                    return {"status": 403, "sub_status": 0, "userMessage": "WAF Interception - Cookie updated"}
            except:
                pass
            return {"status": 403, "sub_status": 0, "userMessage": "Access Denied (WAF Block)"}

        if response.status_code == 401:
            try: return response.json()
            except: return {"status": 401, "sub_status": 0, "userMessage": "Unauthorized"}

        try: return response.json()
        except: raise Exception(f"Non-JSON response ({response.status_code}) from {path}: {response.text[:200]}")

    def __get__(self, path, params=None, urlpre='https://api.tidal.com/v1/'):
        if params is None: params = {}
        headers = {
            'Authorization': f'Bearer {self.key.accessToken}',
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
            'X-Tidal-Token': self.apiKey['clientId']
        }
        if self.key.sessionId: headers['X-Tidal-SessionId'] = self.key.sessionId
        if self.key.countryCode: params['countryCode'] = self.key.countryCode
            
        for index in range(0, 3):
            try:
                respond = self.session.get(urlpre + path, headers=headers, params=params, verify=False, timeout=15)
                if respond.status_code == 401:
                    try:
                        result = respond.json()
                        if result.get('subStatus') == 6001 and index == 0:
                            self.loginByAccessToken(self.key.accessToken)
                            if self.key.sessionId:
                                headers['X-Tidal-SessionId'] = self.key.sessionId
                                continue
                    except: pass
                    raise Exception("User does not have a valid session")
                
                result = self.__handle_response__(respond, "GET", path)
                if 'status' not in result: return result
                break
            except Exception as e:
                if index >= 2: raise e
        return result

    def __post__(self, path, data, auth=None, urlpre='https://auth.tidal.com/v1/oauth2'):
        for index in range(3):
            try:
                # For auth requests, use requests.post directly to avoid session header issues
                # and match tiddl's working implementation
                respond = requests.post(urlpre + path, data=data, auth=auth, verify=False, timeout=15)
                result = self.__handle_response__(respond, "POST", path)
                if result.get("status") == 403 and "Cookie updated" in result.get("userMessage", ""):
                    continue
                return result
            except Exception as e:
                if index == 2: raise e
                time.sleep(2)

    def getDeviceCode(self) -> str:
        data = {'client_id': self.apiKey['clientId'], 'scope': 'r_usr+w_usr+w_sub'}
        result = self.__post__('/device_authorization', data)
        if result.get('status') and result['status'] != 200:
            raise Exception(f"Device authorization failed: {result.get('userMessage', 'Unknown error')}")
        self.key.deviceCode = result['deviceCode']
        self.key.userCode = result['userCode']
        self.key.verificationUrl = result['verificationUri']
        self.key.authCheckTimeout = result['expiresIn']
        self.key.authCheckInterval = result['interval']
        return "http://" + self.key.verificationUrl + "/" + self.key.userCode

    def checkAuthStatus(self) -> bool:
        data = {
            'client_id': self.apiKey['clientId'],
            'device_code': self.key.deviceCode,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'scope': 'r_usr+w_usr+w_sub'
        }
        auth = (self.apiKey['clientId'], self.apiKey['clientSecret'])
        result = self.__post__('/token', data, auth)
        if result.get('status') and result['status'] != 200:
            return False
        self.key.userId = result['user']['userId']
        self.key.countryCode = result['user']['countryCode']
        self.key.accessToken = result['access_token']
        self.key.refreshToken = result['refresh_token']
        self.key.expiresIn = result['expires_in']
        try: self.loginByAccessToken(self.key.accessToken)
        except: pass
        return True

    def refreshAccessToken(self, refreshToken) -> bool:
        data = {
            'client_id': self.apiKey['clientId'],
            'refresh_token': refreshToken,
            'grant_type': 'refresh_token',
            'scope': 'r_usr+w_usr+w_sub'
        }
        auth = (self.apiKey['clientId'], self.apiKey['clientSecret'])
        result = self.__post__('/token', data, auth)
        if result.get('status') and result['status'] != 200: return False
        self.key.userId = result['user']['userId']
        self.key.countryCode = result['user']['countryCode']
        self.key.accessToken = result['access_token']
        self.key.expiresIn = result['expires_in']
        self.loginByAccessToken(self.key.accessToken)
        return True

    def loginByAccessToken(self, accessToken, userid=None):
        if not self.key.deviceId: self.key.deviceId = str(uuid.uuid4()).replace('-', '')[:16]
        urls = ['https://api.tidal.com/v1/sessions', 'https://api.tidalhifi.com/v1/sessions']
        final_res = None
        for url in urls:
            strats = [
                {"headers": {'Authorization': f'Bearer {accessToken}', 'X-Tidal-Token': self.apiKey['clientId'], 'User-Agent': self.user_agent, 'Accept': 'application/json'}, "params": {}},
                {"headers": {'Authorization': f'Bearer {accessToken}', 'User-Agent': self.user_agent, 'Accept': 'application/json'}, "params": {'deviceId': self.key.deviceId}}
            ]
            for strat in strats:
                try:
                    r = self.session.get(url, headers=strat['headers'], params=strat['params'], verify=False, timeout=10)
                    if r.status_code == 200:
                        final_res = r
                        break
                except: continue
            if final_res: break
        if not final_res: raise Exception("User does not have a valid session")
        result = final_res.json()
        self.key.userId, self.key.countryCode, self.key.accessToken, self.key.sessionId = result['userId'], result['countryCode'], accessToken, result['sessionId']

    def getAlbum(self, id) -> Album: return aigpy.model.dictToModel(self.__get__('albums/' + str(id)), Album())
    def getPlaylist(self, id) -> Playlist: return aigpy.model.dictToModel(self.__get__('playlists/' + str(id)), Playlist())
    def getPlaylistSelf(self) -> List[Playlist]:
        ret = self.__get__(f'users/{self.key.userId}/playlists')
        return [aigpy.model.dictToModel(item, Playlist()) for item in ret['items']]
    def getArtist(self, id) -> Artist: return aigpy.model.dictToModel(self.__get__('artists/' + str(id)), Artist())
    def getTrack(self, id) -> Track: return aigpy.model.dictToModel(self.__get__('tracks/' + str(id)), Track())
    def getVideo(self, id) -> Video: return aigpy.model.dictToModel(self.__get__('videos/' + str(id)), Video())
    def getMix(self, id) -> Mix:
        mix = Mix(); mix.id = id; mix.tracks, mix.videos = self.getItems(id, Type.Mix)
        return None, mix
    def getTypeData(self, id, type: Type):
        mapping = {Type.Album: self.getAlbum, Type.Artist: self.getArtist, Type.Track: self.getTrack, Type.Video: self.getVideo, Type.Playlist: self.getPlaylist, Type.Mix: self.getMix}
        return mapping[type](id) if type in mapping else None
    def search(self, text: str, type: Type, offset: int = 0, limit: int = 10) -> SearchResult:
        typeStr = type.name.upper() + "S" if type != Type.Null else "ARTISTS,ALBUMS,TRACKS,VIDEOS,PLAYLISTS"
        params = {"query": text, "offset": offset, "limit": limit, "types": typeStr}
        return aigpy.model.dictToModel(self.__get__('search', params=params), SearchResult())
    def getItems(self, id, type: Type):
        path_map = {Type.Playlist: f'playlists/{id}/items', Type.Album: f'albums/{id}/items', Type.Mix: f'mixes/{id}/items'}
        if type not in path_map: raise Exception("invalid Type!")
        data = self.__getItems__(path_map[type]); tracks, videos = [], []
        for item in data:
            model, target = (Track(), tracks) if item['type'] == 'track' else (Video(), videos)
            if item['item'].get('streamReady'): target.append(aigpy.model.dictToModel(item['item'], model))
        return tracks, videos
    def __getItems__(self, path, params=None):
        params = (params or {}).copy(); params.update({'limit': 50, 'offset': 0}); ret = []
        while True:
            data = self.__get__(path, params); total = data.get('totalNumberOfItems', 0); ret += data["items"]
            if total > 0 and total <= len(ret) or len(data["items"]) < 50: return ret
            params['offset'] += len(data["items"])
    def getStreamUrl(self, id, quality: AudioQuality):
        qual_map = {
            AudioQuality.Max: "HI_RES_LOSSLESS",
            AudioQuality.Master: "HI_RES_LOSSLESS",
            AudioQuality.HiFi: "LOSSLESS",
            AudioQuality.High: "HIGH",
            AudioQuality.Normal: "LOW"
        }
        paras = {"audioquality": qual_map.get(quality, "LOW"), "playbackmode": "STREAM", "assetpresentation": "FULL"}
        resp = aigpy.model.dictToModel(self.__get__(f'tracks/{str(id)}/playbackinfopostpaywall', paras), StreamRespond())
        ret = StreamUrl(); ret.trackid, ret.soundQuality = resp.trackid, resp.audioQuality
        if "vnd.tidal.bt" in resp.manifestMimeType:
            manifest = json.loads(base64.b64decode(resp.manifest).decode('utf-8'))
            ret.codec, ret.encryptionKey, ret.url = manifest['codecs'], manifest.get('keyId', ""), manifest['urls'][0]; ret.urls = [ret.url]
        elif "dash+xml" in resp.manifestMimeType:
            xmldata = base64.b64decode(resp.manifest).decode('utf-8'); ret.codec, ret.encryptionKey = aigpy.string.getSub(xmldata, 'codecs="', '"'), ""; ret.urls = self.parse_mpd(xmldata)[0]
            if ret.urls: ret.url = ret.urls[0]
        return ret
    def parse_mpd(self, xml: bytes) -> list:
        xml = re.sub(r'xmlns="[^"]+"', '', xml.decode() if isinstance(xml, bytes) else xml, count=1); root = ElementTree.fromstring(xml); tracks = []
        for rep in root.findall('.//Representation'):
            seg = rep.find('SegmentTemplate'); urls = [seg.get('initialization')]
            if seg.find('SegmentTimeline') is not None:
                cur = 0
                for s in seg.findall('.//S'):
                    if s.get('t'): cur = int(s.get('t'))
                    for _ in range(int(s.get('r') or 0) + 1): urls.append(seg.get('media').replace('$Number$', str(len(urls)))); cur += int(s.get('d'))
            tracks.append(urls)
        return tracks

    def getTrackContributors(self, id): return self.__get__(f'tracks/{str(id)}/contributors')
    def getCoverUrl(self, sid, width="320", height="320"): return f"https://resources.tidal.com/images/{sid.replace('-', '/')}/{width}x{height}.jpg" if sid else ""
    def getCoverData(self, sid, width="320", height="320"):
        try: return requests.get(self.getCoverUrl(sid, width, height)).content
        except: return ''
    def getArtistsName(self, artists=[]): return ", ".join(list(item.name for item in artists))
    def getFlag(self, data, type: Type, short=True, separator=" / "):
        master = False; atmos = False; explicit = False
        if type == Type.Album or type == Type.Track:
            if data.audioQuality == "HI_RES": master = True
            if type == Type.Album and data.audioModes and "DOLBY_ATMOS" in data.audioModes: atmos = True
            if data.explicit is True: explicit = True
        if type == Type.Video and data.explicit is True: explicit = True
        if not master and not atmos and not explicit: return ""
        array = []
        if master: array.append("M" if short else "Master")
        if atmos: array.append("A" if short else "Dolby Atmos")
        if explicit: array.append("E" if short else "Explicit")
        return separator.join(array)

    def getLyrics(self, id) -> Lyrics:
        data = self.__get__(f'tracks/{str(id)}/lyrics')
        return aigpy.model.dictToModel(data, Lyrics())

    def parseUrl(self, url):
        if "tidal.com" not in url: return Type.Null, url
        for item in Type:
            if item.name.lower() in url.lower(): sid = aigpy.string.getSub(url.lower(), item.name.lower() + '/', '/'); return item, (sid.split('?')[0] if '?' in sid else sid)
        return Type.Null, url

# Singleton
TIDAL_API = TidalAPI()
