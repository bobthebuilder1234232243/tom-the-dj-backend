import os
import threading
import time
import subprocess
import random
import requests
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

# --- PROXY HELPER ---
def get_proxy_list():
    """Fetches a list of free SOCKS5 proxies from a public list."""
    try:
        url = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"
        r = requests.get(url, timeout=10)
        proxies = [line.strip() for line in r.text.splitlines() if line.strip() and len(line) < 50]
        random.shuffle(proxies)
        return proxies[:50] # Test the first 50 random proxies
    except Exception as e:
        print(f"Failed to fetch proxies: {e}")
        return []

# --- CORE DOWNLOAD FUNCTION ---
def download_song(url):
    """Tries to download a URL using a series of fallback methods."""
    
    # METHOD 1: Try the android_vr client (bypasses visitor data issue)
    print("Attempting download with android_vr client...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'extractor_args': {
            'youtube': {
                'player_client': ['android_vr']
            }
        },
        'quiet': True,
        'retries': 1,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info: info = info['entries'][0]
            mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
            safe_path = os.path.join(TEMP_DIR, safe_filename)
            if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                os.rename(mp3_filename, safe_path)
            return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
    except Exception as e:
        print(f"android_vr client failed: {e}")

    # METHOD 2: Try SOCKS5 Proxies
    print("Falling back to SOCKS5 proxy farm...")
    proxies = get_proxy_list()
    for proxy in proxies:
        print(f"Testing proxy: {proxy}")
        ydl_opts['proxy'] = f'socks5://{proxy}'
        # Remove the specific client arg to use default
        if 'extractor_args' in ydl_opts: del ydl_opts['extractor_args']
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info: info = info['entries'][0]
                mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
                safe_path = os.path.join(TEMP_DIR, safe_filename)
                if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                    os.rename(mp3_filename, safe_path)
                print(f"Success with proxy: {proxy}")
                return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
        except Exception as e:
            print(f"Proxy {proxy} failed.")
            continue

    raise Exception("All download methods failed. YouTube is aggressively blocking this IP.")

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

# --- ROUTES ---
@app.route('/test', methods=['GET'])
def test_pipeline():
    try:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        filename, title, artist = download_song(url)
        if push_to_codeberg(filename):
            return f"✅ SUCCESS! Downloaded '{title}' and pushed to Codeberg.", 200
        else:
            return "❌ Downloaded, but failed to push to Codeberg.", 500
    except Exception as e:
        return f"❌ ERROR: {str(e)}", 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    playlist_id = request.form.get('playlist_id')
    if file.filename == '': return jsonify({"error": "No selected file"}), 400

    safe_filename = file.filename.replace(" ", "_")
    file_path = os.path.join(TEMP_DIR, safe_filename)
    file.save(file_path)

    if push_to_codeberg(safe_filename):
        if supabase:
            supabase.table('songs').insert({
                "playlist_id": playlist_id,
                "title": request.form.get('title', 'Unknown Title'),
                "artist": request.form.get('artist', 'Unknown Artist'),
                "file_path": safe_filename,
                "status": "completed"
            }).execute()
        return jsonify({"message": "File uploaded successfully"}), 200
    return jsonify({"error": "Failed to push to storage"}), 500

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
                url = song.get('spotify_url') or f"ytsearch1:{song['title']} {song['artist']} official audio"
                
                try:
                    filename, title, artist = download_song(url)
                    if push_to_codeberg(filename):
                        supabase.table('songs').update({
                            "file_path": filename,
                            "status": "completed",
                            "title": title, # Update with actual fetched title
                            "artist": artist
                        }).eq('id', song['id']).execute()
                        print(f"✅ Successfully processed {filename}")
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
