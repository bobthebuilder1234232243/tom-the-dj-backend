import os
import threading
import time
import subprocess
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

# --- THE TEST ALL FUNCTION ---
@app.route('/test-all', methods=['GET'])
def test_all_sources():
    query = "Never Gonna Give You Up Rick Astley"
    spotify_url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    results = []

    # 1. SoundCloud (via yt-dlp)
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{TEMP_DIR}/sc_%(title)s.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"scsearch1:{query}", download=True)
            if 'entries' in info: info = info['entries'][0]
            results.append(f"✅ <b>SoundCloud:</b> SUCCESS - {info['title']}")
    except Exception as e:
        results.append(f"❌ <b>SoundCloud:</b> FAILED - {str(e)[:100]}")

    # 2. Bandcamp (via yt-dlp)
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{TEMP_DIR}/bc_%(title)s.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # yt-dlp uses bcsearch1 for Bandcamp search
            info = ydl.extract_info(f"bcsearch1:{query}", download=True)
            if 'entries' in info: info = info['entries'][0]
            results.append(f"✅ <b>Bandcamp:</b> SUCCESS - {info['title']}")
    except Exception as e:
        results.append(f"❌ <b>Bandcamp:</b> FAILED - {str(e)[:100]}")

    # 3. SpotDL via SoundCloud (Direct Spotify accuracy)
    try:
        # We use spotdl CLI, forcing it to use soundcloud as the audio provider
        cmd = ["spotdl", "download", spotify_url, "--output", TEMP_DIR, "--format", "mp3", "--audio-providers", "soundcloud"]
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if process.returncode == 0:
            results.append(f"✅ <b>SpotDL (SoundCloud):</b> SUCCESS")
        else:
            error_msg = process.stderr or process.stdout
            results.append(f"❌ <b>SpotDL (SoundCloud):</b> FAILED - {error_msg[:150]}")
    except Exception as e:
        results.append(f"❌ <b>SpotDL (SoundCloud):</b> FAILED - {str(e)[:100]}")

    # Format output as HTML for the browser
    html_output = "<h1>Downloader Source Tests</h1>"
    html_output += "<ul>"
    for res in results:
        html_output += f"<li style='font-size: 1.2rem; margin-bottom: 10px;'>{res}</li>"
    html_output += "</ul>"
    
    return html_output, 200

# --- BACKGROUND WORKER (Uses the best fallbacks) ---
def download_song_robust(song_title, artist, spotify_url=None):
    # Priority 1: SoundCloud via yt-dlp (Fast, usually unblocked)
    query = f"{song_title} {artist}"
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}],
            'quiet': True,
            'retries': 2
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"scsearch1:{query}", download=True)
            if 'entries' in info: info = info['entries'][0]
            mp3_filename = os.path.splitext(ydl.prepare_filename(info))[0] + ".mp3"
            safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
            safe_path = os.path.join(TEMP_DIR, safe_filename)
            if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                os.rename(mp3_filename, safe_path)
            return safe_filename, info['title'], info.get('uploader', 'Unknown Artist')
    except Exception as e:
        print(f"SoundCloud failed, falling back to SpotDL: {e}")

    # Priority 2: SpotDL via SoundCloud
    if spotify_url:
        try:
            cmd = ["spotdl", "download", spotify_url, "--output", TEMP_DIR, "--format", "mp3", "--audio-providers", "soundcloud"]
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            
            # Find the newly downloaded file
            files = os.listdir(TEMP_DIR)
            if files:
                # Sort by newest
                newest_file = max([os.path.join(TEMP_DIR, f) for f in files], key=os.path.getctime)
                safe_filename = os.path.basename(newest_file).replace(" ", "_")
                safe_path = os.path.join(TEMP_DIR, safe_filename)
                if newest_file != safe_path:
                    os.rename(newest_file, safe_path)
                return safe_filename, song_title, artist
        except Exception as e:
            print(f"SpotDL failed: {e}")

    raise Exception("All non-YouTube sources failed.")

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
                    filename, real_title, real_artist = download_song_robust(song['title'], song['artist'], song.get('spotify_url'))
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
