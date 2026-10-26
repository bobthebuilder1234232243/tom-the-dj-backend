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

if SUPABASE_SERVICE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    supabase = None

CODEBERG_REPO = "https://math123934:a7856ae1941636a3f6790971ded54722237a4fb1@codeberg.org/Math123934/Tom-The-DJ.git"
TEMP_DIR = "/tmp/downloads"

if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

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
        
        if os.path.exists(source_file):
            os.remove(source_file)
        return True
    except Exception as e:
        print(f"Git Push Error: {e}")
        return False

@app.route('/test', methods=['GET'])
def test_pipeline():
    try:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'quiet': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            raw_filename = ydl.prepare_filename(info)
            mp3_filename = os.path.splitext(raw_filename)[0] + ".mp3"
            safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
            
            safe_path = os.path.join(TEMP_DIR, safe_filename)
            if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                os.rename(mp3_filename, safe_path)
            
            push_success = push_to_codeberg(safe_filename)
            
            if push_success:
                return "✅ SUCCESS! Video downloaded and pushed to Codeberg.", 200
            else:
                return "❌ Downloaded, but failed to push to Codeberg. Check logs.", 500
                
    except Exception as e:
        return f"❌ ERROR: {str(e)}", 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    playlist_id = request.form.get('playlist_id')
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    safe_filename = file.filename.replace(" ", "_")
    file_path = os.path.join(TEMP_DIR, safe_filename)
    file.save(file_path)

    success = push_to_codeberg(safe_filename)
    
    if success and supabase:
        supabase.table('songs').insert({
            "playlist_id": playlist_id,
            "title": request.form.get('title', 'Unknown Title'),
            "artist": request.form.get('artist', 'Unknown Artist'),
            "file_path": safe_filename,
            "status": "completed"
        }).execute()
        return jsonify({"message": "File uploaded successfully"}), 200
    elif success:
        return jsonify({"message": "File pushed to Codeberg, but Supabase not connected."}), 200
    else:
        return jsonify({"error": "Failed to push to storage"}), 500

def download_worker():
    print("Background Downloader Started...")
    while True:
        if not supabase:
            time.sleep(10)
            continue

        try:
            response = supabase.table('songs').select('*').eq('status', 'pending').execute()
            pending_songs = response.data

            for song in pending_songs:
                print(f"Found pending: {song['title']} - {song['artist']}")
                
                url = song.get('spotify_url')
                if not url:
                    search_query = f"{song['title']} {song['artist']} official audio"
                    url = f"ytsearch1:{search_query}"
                
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': f'{TEMP_DIR}/%(title)s.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320',
                    }],
                    'quiet': True
                }

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if 'entries' in info:
                            info = info['entries'][0]
                        
                        raw_filename = ydl.prepare_filename(info)
                        mp3_filename = os.path.splitext(raw_filename)[0] + ".mp3"
                        safe_filename = os.path.basename(mp3_filename).replace(" ", "_")
                        
                        safe_path = os.path.join(TEMP_DIR, safe_filename)
                        if os.path.exists(mp3_filename) and mp3_filename != safe_path:
                            os.rename(mp3_filename, safe_path)

                        push_success = push_to_codeberg(safe_filename)

                        if push_success:
                            supabase.table('songs').update({
                                "file_path": safe_filename,
                                "status": "completed"
                            }).eq('id', song['id']).execute()
                            print(f"Successfully processed {safe_filename}")
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
