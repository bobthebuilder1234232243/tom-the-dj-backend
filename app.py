import os
import threading
import time
import subprocess
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client
import yt_dlp

app = Flask(__name__)
CORS(app)

SUPABASE_URL = "https://wdqrwtdktnfanejftqr.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_SERVICE_KEY else None

CODEBERG_REPO = "https://math123934:a7856ae1941636a3f6790971ded54722237a4fb1@codeberg.org/Math123934/Tom-The-DJ.git"
TEMP_DIR = "/tmp/downloads"
if not os.path.exists(TEMP_DIR): os.makedirs(TEMP_DIR)

# --- HELPER: Push to Codeberg ---
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

# --- CORE: Multi-Tier Download Function ---
def download_song(song_title, artist, spotify_url=None):
    # Base options
    base_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'quiet': True,
        'js_runtimes': {'deno': {}},
        'extractor_args': {
            'youtubepot-bgutilhttp': {
                'base_url': ['http://127.0.0.1:4416']
            }
        },
        'retries': 2,
        'fragment_retries': 2,
        'sleep_interval': 3,
    }

    # --- Tier 1: android_vr client (JS-less) ---
    print("Tier 1: Trying android_vr client...")
    opts = base_opts.copy()
    opts['extractor_args'] = {**base_opts['extractor_args'], 'youtube': {'player_client': ['android_vr']}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            url = spotify_url if spotify_url else f"ytsearch1:{song_title} {artist} official audio"
            info = ydl.extract_info(url, download=True)
            if 'entries' in info: info = info['entries'][0]
            mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
            safe_path = os.path.join(TEMP_DIR, safe_filename)
            if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                os.rename(mp3_filename, safe_path)
            return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
    except Exception as e:
        print(f"Tier 1 failed: {e}")

    # --- Tier 2: ios / web_creator clients ---
    print("Tier 2: Trying ios / web_creator clients...")
    for client in ['ios', 'web_creator']:
        opts = base_opts.copy()
        opts['extractor_args'] = {**base_opts['extractor_args'], 'youtube': {'player_client': [client]}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                url = spotify_url if spotify_url else f"ytsearch1:{song_title} {artist} official audio"
                info = ydl.extract_info(url, download=True)
                if 'entries' in info: info = info['entries'][0]
                mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
                safe_path = os.path.join(TEMP_DIR, safe_filename)
                if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                    os.rename(mp3_filename, safe_path)
                return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
        except Exception as e:
            print(f"Tier 2 ({client}) failed: {e}")

    # --- Tier 3: Invidious API Fallback ---
    print("Tier 3: Trying Invidious API fallback...")
    # List of public Invidious instances (these change often)
    invidious_instances = [
        "https://inv.tux.pizza",
        "https://invidious.io.lol",
        "https://iv.melmac.space"
    ]
    for instance in invidious_instances:
        try:
            # Search for the video
            search_url = f"{instance}/api/v1/search?q={song_title} {artist} official audio&type=video"
            r = requests.get(search_url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    video_id = data[0]['videoId']
                    # Use yt-dlp to download the video ID via the Invidious instance
                    opts = base_opts.copy()
                    opts['extractor_args'] = {'youtube': {'player_client': ['web']}}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                        mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
                        safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
                        safe_path = os.path.join(TEMP_DIR, safe_filename)
                        if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                            os.rename(mp3_filename, safe_path)
                        print(f"Success via Invidious instance: {instance}")
                        return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
        except Exception as e:
            print(f"Invidious instance {instance} failed: {e}")
            continue

    raise Exception("All download tiers failed. YouTube's datacenter block is too strong right now.")

# --- ROUTES ---
@app.route('/test', methods=['GET'])
def test_pipeline():
    try:
        # Using a known video for testing
        filename, title, artist = download_song("Never Gonna Give You Up", "Rick Astley", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
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
                try:
                    filename, real_title, real_artist = download_song(song['title'], song['artist'], song.get('spotify_url'))
                    if push_to_codeberg(filename):
                        supabase.table('songs').update({
                            "file_path": filename, "status": "completed",
                            "title": real_title, "artist": real_artist
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
