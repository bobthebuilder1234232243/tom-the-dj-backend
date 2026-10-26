import os
import threading
import time
import subprocess
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import yt_dlp

app = Flask(__name__)
CORS(app)

SUPABASE_URL = "https://wdqrwtdktnfanehjftqr.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else None

CODEBERG_REPO = "https://math123934:a7856ae1941636a3f6790971ded54722237a4fb1@codeberg.org/Math123934/Tom-The-DJ.git"
TEMP_DIR = "/tmp/downloads"
if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)

# --- GIT PUSH LOGIC ---
def push_to_codeberg(filename):
    try:
        repo_dir = "/tmp/codeberg_repo"
        if not os.path.exists(repo_dir):
            subprocess.run(["git", "clone", CODEBERG_REPO, repo_dir], check=True)
        subprocess.run(["git", "pull", "origin", "main"], cwd=repo_dir, check=True)
        
        source_file = os.path.join(TEMP_DIR, filename)
        dest_file = os.path.join(repo_dir, filename)
        subprocess.run(["cp", source_file, dest_file], check=True)
        
        subprocess.run(["git", "add", filename], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "wen8395023@gmail.com"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.name", "math123934"], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", f"Auto-uploaded: {filename}"], cwd=repo_dir, check=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=repo_dir, check=True)
        
        if os.path.exists(source_file): os.remove(source_file)
        return True
    except Exception as e:
        print(f"Git Push Error: {e}")
        return False

# --- SPOTIFY OEMBED SCRAPER ---
def get_spotify_metadata(spotify_url):
    """Uses Spotify's public oEmbed API to get exact track info without API keys."""
    try:
        oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
        r = requests.get(oembed_url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # oEmbed returns title like "Song Name" and author_name like "Artist Name"
            title = data.get('title', '')
            artist = data.get('author_name', '')
            return f"{artist} {title}".strip()
    except Exception as e:
        print(f"oEmbed failed: {e}")
    return None

# --- CORE DOWNLOAD FUNCTION ---
@app.route('/test-all', methods=['GET'])
def test_all_sources():
    results = []
    spotify_url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT" # Rick Astley
    
    try:
        # Step 1: Get exact name from Spotify
        exact_query = get_spotify_metadata(spotify_url)
        if not exact_query:
            exact_query = "Rick Astley Never Gonna Give You Up" # Fallback
            
        results.append(f"🔍 <b>Spotify Query:</b> {exact_query}")
        
        # Step 2: Download from SoundCloud
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
            'quiet': True,
            'retries': 2
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"scsearch1:{exact_query}", download=True)
            if 'entries' in info: info = info['entries'][0]
            
            results.append(f"✅ <b>SoundCloud:</b> SUCCESS - Downloaded '{info['title']}' by {info.get('uploader', 'Unknown')}")
            
            # Clean up the test file immediately
            mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            if os.path.exists(mp3_filename):
                os.remove(mp3_filename)
                
    except Exception as e:
        results.append(f"❌ <b>Error:</b> {str(e)[:150]}")

    html_output = "<h1>Lightweight Accuracy Test</h1><ul>"
    for res in results:
        html_output += f"<li style='font-size: 1.2rem; margin-bottom: 10px;'>{res}</li>"
    html_output += "</ul>"
    return html_output, 200

# --- BACKGROUND WORKER ---
def download_worker():
    print("Background Downloader Started...")
    while True:
        if not supabase:
            time.sleep(10)
            continue

        try:
            response = supabase.table('songs').select('*').eq('status', 'pending').execute()
            for song in response.data:
                print(f"Found pending: {song['title']} - {song['artist']}")
                
                # If the user provided a Spotify URL, we get the exact metadata first
                search_query = f"{song['artist']} {song['title']}"
                if song.get('spotify_url'):
                    exact = get_spotify_metadata(song['spotify_url'])
                    if exact: search_query = exact

                try:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
                        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
                        'quiet': True,
                        'retries': 3
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"scsearch1:{search_query}", download=True)
                        if 'entries' in info: info = info['entries'][0]
                        
                        mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                        safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
                        safe_path = os.path.join(TEMP_DIR, safe_filename)
                        if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                            os.rename(mp3_filename, safe_path)

                        if push_to_codeberg(safe_filename):
                            supabase.table('songs').update({
                                "file_path": safe_filename, "status": "completed",
                                "title": info['title'], "artist": info.get('uploader', song['artist'])
                            }).eq('id', song['id']).execute()
                            print(f"✅ Successfully processed {safe_filename}")
                        else:
                            supabase.table('songs').update({"status": "failed"}).eq('id', song['id']).execute()
                except Exception as e:
                    print(f"Download failed: {e}")
                    supabase.table('songs').update({"status": "failed"}).eq('id', song['id']).execute()
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(10)

threading.Thread(target=download_worker, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
