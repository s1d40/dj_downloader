#!/usr/bin/env python3
import sys
import os
import logging

# Set up paths to import tidal_dl modules
current_dir = os.path.dirname(os.path.abspath(__file__))
tidal_dl_path = os.path.join(current_dir, "Tidal-Media-Downloader", "TIDALDL-PY", "tidal_dl")
sys.path.append(tidal_dl_path)

try:
    from settings import SETTINGS, TOKEN
    from tidal import TIDAL_API
    from paths import getProfilePath, getTokenPath
    from enums import Type, AudioQuality
    from download import downloadTracks
    import apiKey
    from printf import Printf
    from events import loginByConfig, loginByWeb, changeApiKey
except ImportError as e:
    print(f"Error importing tidal_dl modules: {e}")
    print(f"PYTHONPATH: {sys.path}")
    sys.exit(1)

def setup_logging():
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    setup_logging()
    print("Welcome to the DJ Downloader (WAV Scraper Edition)!")

    # 1. Load Configuration & Login
    try:
        SETTINGS.read(getProfilePath())
        TOKEN.read(getTokenPath())
        
        # Set API Key
        # Index 5 (Tiddl) is currently the only one working reliably in 2026
        if SETTINGS.apiKeyIndex != 5:
            SETTINGS.apiKeyIndex = 5
            SETTINGS.save()
            
        TIDAL_API.apiKey = apiKey.getItem(SETTINGS.apiKeyIndex)
        print(f"Using API Key: {TIDAL_API.apiKey['platform']} (Index: {SETTINGS.apiKeyIndex})")
        
        # Robust Login (from tidal-dl logic)
        login_success = False
        if apiKey.isItemValid(SETTINGS.apiKeyIndex):
            if loginByConfig():
                login_success = True
            else:
                print("Login expired or missing. Starting web login...")
                if loginByWeb():
                    login_success = True
        
        if not login_success:
            print("Login failed with current key. Trying Index 4 (Android Auto) as fallback...")
            SETTINGS.apiKeyIndex = 4
            TIDAL_API.apiKey = apiKey.getItem(4)
            if loginByWeb():
                login_success = True
                SETTINGS.save() # Save the working index
            else:
                print("Web login failed again. Exiting.")
                return
        
        # FORCE MASTER QUALITY for highest quality source before conversion
        SETTINGS.audioQuality = AudioQuality.Master
        print("Audio Quality set to MASTER (will be converted to WAV).")

    except Exception as e:
        print(f"Error during initialization/login: {e}")
        return

    print("Login successful!")

    # 3. Scraper Loop
    while True:
        print("\n--- New Request ---")
        input_str = input("Enter genre, search term, or Tidal URL (or 'q' to quit): ").strip()
        if input_str.lower() == 'q':
            break
        if not input_str:
            continue

        try:
            # Check if input is a Tidal URL
            etype, sid = TIDAL_API.parseUrl(input_str)

            if etype != Type.Null:
                # It is a URL
                print(f"Detected URL of type: {etype.name}")
                
                if etype == Type.Track:
                    print(f"Fetching track {sid}...")
                    track = TIDAL_API.getTrack(sid)
                    # Get album for metadata
                    album = TIDAL_API.getAlbum(track.album.id)
                    downloadTracks([track], album)
                    print(f"Finished downloading track: {track.title}")

                elif etype == Type.Album:
                    print(f"Fetching album {sid}...")
                    album = TIDAL_API.getAlbum(sid)
                    tracks, videos = TIDAL_API.getItems(sid, Type.Album)
                    print(f"Found {len(tracks)} tracks in album '{album.title}'. Starting download...")
                    downloadTracks(tracks, album)
                    print(f"Finished downloading album: {album.title}")

                elif etype == Type.Playlist:
                    print(f"Fetching playlist {sid}...")
                    playlist = TIDAL_API.getPlaylist(sid)
                    tracks, videos = TIDAL_API.getItems(sid, Type.Playlist)
                    print(f"Found {len(tracks)} tracks in playlist '{playlist.title}'. Starting download...")
                    downloadTracks(tracks, None, playlist)
                    print(f"Finished downloading playlist: {playlist.title}")
                
                else:
                    print(f"Unsupported URL type: {etype.name}. Only Track, Album, and Playlist are supported currently.")

            else:
                # Treat as Search Term
                print(f"Scraping TIDAL for '{input_str}' tracks (Top 50)...")
                
                # Search for tracks
                limit = 50 
                search_result = TIDAL_API.search(input_str, Type.Track, limit=limit)
                
                tracks = search_result.tracks.items
                if not tracks:
                    print("No tracks found.")
                    continue
                    
                print(f"Found {len(tracks)} tracks. Starting automated download...")
                
                # 5. Download (Automated)
                downloadTracks(tracks)
                print(f"Finished downloading batch for '{input_str}'.")

        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
