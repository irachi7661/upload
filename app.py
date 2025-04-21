import os
import time
import requests
import dropbox
import subprocess
import uuid
import json
import threading
from flask import Flask, render_template, request, flash, redirect, url_for, make_response, jsonify, Response, stream_with_context
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode, SaveUrlResult
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_change_it_again' # অবশ্যই পরিবর্তন করুন

# --- Global Task Storage ---
# Warning: In-memory storage is not persistent and not suitable for multi-worker setups (use Redis/DB instead)
tasks_status = {} # task_id -> {"status": "...", "progress": 0-100, "results": [], "done": False, "error": None}
tasks_locks = {} # task_id -> threading.Lock()

# --- Dropbox Configuration & Initialization (as before) ---
DROPBOX_ACCESS_TOKEN = "sl.u.AFrUVI6ZkP3ylRHtogmkFjyIsad1PU0XZTWV8vrRH1qqro4_jAf9enk7skPvGgD0d2nqGWq6KtadiTHTXrNp7Y3hn2AEK61qSyQZsreue7SlJGfcBrCCDtggyxIVoZf5Zqxtv5RSQsI3k9Yxl5lU7HM73Wg63FitYq79HwyEAemnc-WwCfKfnCjmxCVqKjMZnbfPa6FCYrVnzwsvcbea7aLXStWwBPbJx2DeklOL-ZHU4y1mlPcQn35Qc3p5yRexhJ2HaQikjE84Nj7xPE9Hvdm9uw7dCAZG-IV3O1wCW3OyMPD6u_IjljkJVHcNJR5Jr6_Z_-HTESI4abZ-xd3eV-tGWTmCUpNEQHt6b5nZIU7cywtrmD6u4dNcbw1AWOpA9wbqAt1-1aA7Ai0PbU1FlSRq3SJMNShAgqT2wOSe40m3bEXF4TgCFsD3h3iGMm1K9p4Ys25kgkFwgRWwLZHDORXW-lMTq8lkOxQF_dioaUjmHw3b7Y7-D9FYQcHyZ0X4R8JJyG5gLHKOcMgXhiMvITR5Si03MTYlYrcdq1OJT4C4967oVc4iqJnFCeCD-SGII7r0zIkiH3JF_RfX2hpaElmPEadibpOc7uB51Iv7XeNFl-ujiLP6vvEJogrCgtchQRN9ZUlstyJItQVrBh018NS2wQ2bcnpJhsIfdFaCek-YFDOj8AjVNCS4NUcJdhUjSedXMj9APAkm2yWin0IuIJSVjfz8esslYMfY21XXIK2sXLpZsE7t-Q6b_AaTLgytgp5SwSd-YVwAnZuIC3LEFe0G9zarMFYeEjOPjJqpzpPwoXZwHRK3Pzt3Ix5jRQSFPGKPPZp_d2k3fGDU5Ib-qI_cgs1vYABiScVFD0QOnxqC-E06x9cOzI7bFVedmLEHwyMvTARUF2xlaeuqcwTgoeIiS7-dxCPUOqnb8jU_drD0Be3awDVUudBAWXLENRtyp_hpWtXs_PpTw8BQJwOfgKKIpFM8vgnaiFnddFBAyXioH2bQniLU88qUUU5vrxP4CWAEt3e3d1mVZNwn0Olby_TpXvptXOnVYNJmynjabnatWqHkKxfaeiXxbnd_0zZH_rMz-MDuy6OpFZFixKZ557SxxZX4mCShEsTYEdnCwn8t8_7apHPFKfScbuNNFOSlXSl67etCDxbcLTlNHuv-pnAuBVK-3XJlNib49OopYYxkqUn5CfccgJ09F7hVULsnOUWZW5pZqmNKuGUtCK8ITpD1IlObW76w3SYeH0Gv6cZRJDK7hms-t6KbozxaW9JDGnyiJu_kYVX1vdvAhC25yKDELGMCyqlWZY9J6ZhBFPWGrHSTdg_wIzDoB3hRGnKykDCNb_-bfLckBNRHqkSnS8odMGtESea4vbQn4soCq8NIslekfuMmdYHEjMvQ_MjsLKBzEk6WOjmZ0fSamaj6V07rszB9Forv2yT8GjVwDMiikWygxewaWeZ6nkEjn-p_WY4"
BASE_URL_UID_MODE = "https://vigilant-fishstick-2fuv.onrender.com"
TEMP_DIR = "temp_files"
if not os.path.exists(TEMP_DIR):
    try:
        os.makedirs(TEMP_DIR)
    except OSError as e:
        print(f"Error creating temp dir {TEMP_DIR}: {e}")
        TEMP_DIR = "."

dbx = None
if DROPBOX_ACCESS_TOKEN != "YOUR_DROPBOX_ACCESS_TOKEN_FALLBACK":
    try:
        dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
        dbx.users_get_current_account()
        print("Successfully connected to Dropbox.")
    except Exception as e:
        print(f"ERROR: Could not connect to Dropbox: {e}")
        dbx = None
else:
    print("WARNING: Dropbox access token not found in environment variable.")

# --- Helper Functions (get_filename_from_url, download_file_local - as before) ---
def get_filename_from_url(url, default_prefix="video"):
    # ... ( আগের কোড ) ...
    try:
        path = urlparse(url).path
        filename = os.path.basename(path)
        if not filename: filename = f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"
        return filename or f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"
    except Exception:
        return f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"

def download_file_local(url, local_path, task_id, file_description="ফাইল"):
    update_status(task_id, f"{file_description} ডাউনলোড শুরু হচ্ছে...")
    print(f"[{task_id}] Downloading {url} to {local_path}")
    total_downloaded = 0
    last_update_time = time.time()
    try:
        with requests.get(url, stream=True, timeout=300) as r: # Increased timeout
            r.raise_for_status()
            total_length = int(r.headers.get('content-length', 0))
            print(f"[{task_id}] File size: {total_length}")
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192*4):
                    f.write(chunk)
                    total_downloaded += len(chunk)
                    # Update progress periodically
                    current_time = time.time()
                    if total_length > 0 and current_time - last_update_time > 1: # Update every 1 sec
                         progress = int(100 * total_downloaded / total_length)
                         update_status(task_id, f"{file_description} ডাউনলোড হচ্ছে...", progress=progress)
                         last_update_time = current_time

        update_status(task_id, f"{file_description} ডাউনলোড সম্পন্ন।", progress=100 if total_length > 0 else None)
        print(f"[{task_id}] Successfully downloaded to {local_path}")
        return True, None
    except requests.exceptions.RequestException as e:
        error_msg = f"ডাউনলোড ত্রুটি ({file_description} - {url}): {e}"
        print(f"[{task_id}] {error_msg}")
        update_status(task_id, error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"অজানা ডাউনলোড ত্রুটি ({file_description} - {url}): {e}"
        print(f"[{task_id}] {error_msg}")
        update_status(task_id, error_msg)
        return False, error_msg

# --- Status Update Helper (Thread-safe) ---
def update_status(task_id, status_message, progress=None, result_item=None, done=False, error_message=None):
    lock = tasks_locks.get(task_id)
    if not lock:
        print(f"[{task_id}] Error: Lock not found for task.")
        return

    with lock:
        if task_id in tasks_status:
            tasks_status[task_id]['status'] = status_message
            if progress is not None:
                tasks_status[task_id]['progress'] = progress
            if result_item:
                 tasks_status[task_id]['results'].append(result_item)
            if error_message:
                 tasks_status[task_id]['error'] = error_message
                 tasks_status[task_id]['done'] = True # Mark done on error
            if done:
                 tasks_status[task_id]['done'] = True
            print(f"[{task_id}] Status Updated: {status_message} (Done: {tasks_status[task_id]['done']})")
        else:
             print(f"[{task_id}] Error: Task status not found for update.")


# --- Background Task Execution Function ---
def run_task(task_id, form_data):
    """Runs the appropriate processing mode in a background thread."""
    if not dbx:
        update_status(task_id, "Dropbox ক্লায়েন্ট শুরু করা যায়নি।", error_message="Dropbox connection failed", done=True)
        return

    mode = form_data.get('input_mode')
    category = form_data.get('category')
    folder_1_name = form_data.get('folder_1_name')
    folder_2_name = form_data.get('folder_2_name')
    base_dropbox_path_prefix = f"/{category}/{folder_1_name}/{folder_2_name}"

    try:
        update_status(task_id, "প্রসেসিং শুরু হচ্ছে...")

        if mode == 'uid':
            # --- UID Mode Logic ---
            uid = form_data.get('uid')
            number_str = form_data.get('number')
            if not uid or not number_str: raise ValueError("UID ও সংখ্যা আবশ্যক।")
            number = int(number_str)
            if number <= 0: raise ValueError("সংখ্যা ধনাত্মক হতে হবে।")

            update_status(task_id, f"{number} টি ফাইল প্রসেস করা হচ্ছে...")
            for i in range(1, number + 1):
                update_status(task_id, f"ফাইল {i}/{number} প্রসেস শুরু...", progress=int(100*(i-1)/number))
                video_filename = f"see{i}.mp4"
                download_url = f"{BASE_URL_UID_MODE}/{uid}/{video_filename}"
                dropbox_path = f"{base_dropbox_path_prefix}/{video_filename}"

                # Use save_url for this mode
                # Note: save_url itself doesn't provide fine-grained progress
                update_status(task_id, f"ফাইল {i}/{number}: ড্রপবক্সে সেভ করা হচ্ছে...")
                file_result = process_single_url_save_url(download_url, dropbox_path, dbx) # This function needs dbx client
                file_result["file_number"] = i
                update_status(task_id, f"ফাইল {i}/{number} প্রসেস সম্পন্ন।", result_item=file_result, progress=int(100*i/number))

        elif mode == 'link':
            # --- Direct Link Mode Logic ---
            direct_link = form_data.get('direct_link')
            if not direct_link: raise ValueError("সরাসরি লিঙ্ক আবশ্যক।")
            parsed_url = urlparse(direct_link)
            if not all([parsed_url.scheme, parsed_url.netloc]): raise ValueError("অবৈধ URL ফরম্যাট।")

            update_status(task_id, "সরাসরি লিঙ্ক প্রসেস করা হচ্ছে...")
            extracted_filename = get_filename_from_url(direct_link)
            dropbox_path = f"{base_dropbox_path_prefix}/{extracted_filename}"

            # Use save_url for this mode
            update_status(task_id, "ড্রপবক্সে সেভ করা হচ্ছে...")
            file_result = process_single_url_save_url(direct_link, dropbox_path, dbx)
            update_status(task_id, "প্রসেস সম্পন্ন।", result_item=file_result, progress=100)


        elif mode == 'merge':
            # --- Merge Mode Logic ---
            video_link = form_data.get('video_link')
            audio_link = form_data.get('audio_link')
            if not video_link or not audio_link: raise ValueError("ভিডিও ও অডিও লিঙ্ক আবশ্যক।")
            pv = urlparse(video_link); pa = urlparse(audio_link)
            if not all([pv.scheme, pv.netloc]) or not all([pa.scheme, pa.netloc]): raise ValueError("ভিডিও বা অডিও লিঙ্ক অবৈধ।")

            task_uuid = uuid.uuid4().hex
            base_filename = get_filename_from_url(video_link, "merged_video")
            local_video_path = os.path.join(TEMP_DIR, f"{task_uuid}_video.tmp")
            local_audio_path = os.path.join(TEMP_DIR, f"{task_uuid}_audio.tmp")
            local_output_path = os.path.join(TEMP_DIR, f"{task_uuid}_{base_filename}")
            dropbox_path = f"{base_dropbox_path_prefix}/{base_filename}"
            merge_result = { "filename": base_filename, "status": "ব্যর্থ (Failed)", "message": "", "link": None, "file_number": None }
            ffmpeg_ok = False

            try:
                update_status(task_id, "মার্জিং প্রক্রিয়া শুরু...", progress=0)
                # 1. Download video
                video_dl_ok, video_err = download_file_local(video_link, local_video_path, task_id, "ভিডিও")
                if not video_dl_ok: raise Exception(f"ভিডিও ডাউনলোড ব্যর্থ: {video_err}")
                update_status(task_id, "ভিডিও ডাউনলোড সম্পন্ন।", progress=25)

                # 2. Download audio
                audio_dl_ok, audio_err = download_file_local(audio_link, local_audio_path, task_id, "অডিও")
                if not audio_dl_ok: raise Exception(f"অডিও ডাউনলোড ব্যর্থ: {audio_err}")
                update_status(task_id, "অডিও ডাউনলোড সম্পন্ন।", progress=50)

                # 3. Run ffmpeg
                update_status(task_id, "ভিডিও ও অডিও মার্জ করা হচ্ছে...", progress=60)
                print(f"[{task_id}] Running ffmpeg to merge into {local_output_path}")
                ffmpeg_command = [ 'ffmpeg', '-i', local_video_path, '-i', local_audio_path, '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0', '-y', '-hide_banner', '-loglevel', 'error', local_output_path ]
                try:
                    process = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True, timeout=600) # 10 min timeout for ffmpeg
                    print(f"[{task_id}] ffmpeg merge successful.")
                    ffmpeg_ok = True
                    update_status(task_id, "মার্জ সম্পন্ন।", progress=75)
                except FileNotFoundError: raise Exception("মার্জ ত্রুটি: সার্ভারে 'ffmpeg' কমান্ড পাওয়া যায়নি।")
                except subprocess.TimeoutExpired: raise Exception("মার্জ ত্রুটি: FFmpeg কমান্ড টাইম আউট হয়েছে।")
                except subprocess.CalledProcessError as e: raise Exception(f"FFmpeg মার্জ ত্রুটি: {e.stderr}")

                # 4. Upload merged file
                update_status(task_id, "মার্জ করা ফাইল আপলোড হচ্ছে...", progress=80)
                print(f"[{task_id}] Uploading merged file {local_output_path} to {dropbox_path}")
                try:
                    with open(local_output_path, 'rb') as f:
                        file_size = os.path.getsize(local_output_path)
                        chunk_size = 100 * 1024 * 1024 # 100MB
                        if file_size <= chunk_size:
                            dbx.files_upload(f.read(), dropbox_path, mode=WriteMode('overwrite'))
                            update_status(task_id, "আপলোড সম্পন্ন।", progress=95)
                        else: # Chunked upload
                            upload_session_start_result = dbx.files_upload_session_start(f.read(chunk_size))
                            cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id, offset=f.tell())
                            commit = dropbox.files.CommitInfo(path=dropbox_path, mode=WriteMode('overwrite'))
                            while f.tell() < file_size:
                                chunk = f.read(chunk_size)
                                uploaded_bytes = cursor.offset + len(chunk)
                                progress = 80 + int(15 * uploaded_bytes / file_size) # Progress between 80-95
                                if (file_size - cursor.offset) <= chunk_size:
                                    dbx.files_upload_session_finish(chunk, cursor, commit)
                                    print(f"[{task_id}] Chunked upload finished.")
                                else:
                                    dbx.files_upload_session_append_v2(chunk, cursor)
                                    cursor.offset = f.tell()
                                    print(f"[{task_id}] Uploaded chunk, offset: {cursor.offset}")
                                update_status(task_id, f"আপলোড হচ্ছে... {int(100*uploaded_bytes/file_size)}%", progress=progress)
                    print(f"[{task_id}] Upload successful.")
                    merge_result["message"] = "ডাউনলোড, মার্জ ও আপলোড সফল।"
                    update_status(task_id, "আপলোড সম্পন্ন।", progress=95)

                     # 5. Get share link
                    update_status(task_id, "শেয়ার লিঙ্ক তৈরি হচ্ছে...", progress=98)
                    try:
                        settings = dropbox.sharing.SharedLinkSettings(requested_visibility=dropbox.sharing.RequestedVisibility.public)
                        link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path, settings=settings)
                        raw_link = link_metadata.url.replace('dl=0', 'raw=1'); merge_result["link"] = raw_link; merge_result["status"] = "সফল (Success)"
                        print(f"[{task_id}] Share link generated.")
                    except ApiError as e:
                         # Handle link errors as before
                         if e.error.is_shared_link_already_exists():
                             links = dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True).links
                             if links: merge_result["link"] = links[0].url.replace('dl=0', 'raw=1'); merge_result["status"] = "সফল (Success)"; merge_result["message"] += " (বিদ্যমান লিঙ্ক)"
                             else: merge_result["message"] += " লিঙ্ক তৈরি/পুনরুদ্ধার করা যায়নি।"
                         else: merge_result["message"] += f" লিঙ্ক তৈরিতে ত্রুটি: {e}"
                         if merge_result["link"] is None: merge_result["status"] = "ব্যর্থ (Failed)"

                except Exception as upload_err:
                    raise Exception(f"আপলোড বা লিঙ্ক তৈরিতে ত্রুটি: {upload_err}")

            finally:
                # 6. Cleanup temporary files
                print(f"[{task_id}] Cleaning up temp files for merge...")
                for temp_file in [local_video_path, local_audio_path, local_output_path]:
                    if os.path.exists(temp_file):
                        try: os.remove(temp_file); print(f"[{task_id}] Removed: {temp_file}")
                        except OSError as e: print(f"[{task_id}] Error removing {temp_file}: {e}")
            # Add the final result for merge mode
            update_status(task_id, "মার্জ প্রক্রিয়া সম্পন্ন।", result_item=merge_result)


        else:
            raise ValueError("অজানা ইনপুট মোড।")

        # Mark task as done successfully
        update_status(task_id, "সকল কাজ সম্পন্ন হয়েছে।", done=True, progress=100)

    except Exception as e:
        print(f"[{task_id}] Error during task execution: {e}")
        # Mark task as done with error
        update_status(task_id, f"ত্রুটি: {e}", error_message=str(e), done=True)

# --- Route to Start the Task ---
@app.route('/start-task', methods=['POST'])
def start_task():
    task_id = str(uuid.uuid4())
    print(f"Starting task with ID: {task_id}")

    # Initialize status and lock
    tasks_locks[task_id] = threading.Lock()
    with tasks_locks[task_id]:
         tasks_status[task_id] = {"status": "অপেক্ষা করছে...", "progress": 0, "results": [], "done": False, "error": None}

    # Start background thread
    thread = threading.Thread(target=run_task, args=(task_id, request.form))
    thread.daemon = True # Allows app to exit even if threads are running (optional)
    thread.start()

    # Return task ID immediately
    return jsonify({"task_id": task_id})

# --- Route for Server-Sent Events (SSE) ---
@app.route('/status/<task_id>')
def stream_status(task_id):
    def generate():
        last_sent_status_json = None # Track last sent status to avoid duplicates
        try:
            while True:
                status_data = None
                done = False
                lock = tasks_locks.get(task_id)

                if lock:
                    with lock:
                        if task_id in tasks_status:
                            status_data = tasks_status[task_id].copy() # Get a copy
                            done = status_data.get("done", False)
                        else:
                             # Task might have been cleaned up or never existed
                             status_data = {"status": "টাস্ক পাওয়া যায়নি বা শেষ হয়েছে।", "done": True, "error": "Task not found"}
                             done = True
                else:
                     # Lock missing, assume task is done or gone
                     status_data = {"status": "টাস্কের অবস্থা অজানা।", "done": True, "error": "Task lock not found"}
                     done = True


                current_status_json = json.dumps(status_data)
                if current_status_json != last_sent_status_json:
                    yield f"data: {current_status_json}\n\n"
                    last_sent_status_json = current_status_json
                    print(f"[{task_id}] SSE Sent: {current_status_json}")

                if done:
                    print(f"[{task_id}] SSE stream closing (task done).")
                    break

                time.sleep(0.5) # Wait before checking again

        except GeneratorExit:
             print(f"[{task_id}] SSE connection closed by client.")
        finally:
            # Clean up task data after client disconnects or task finishes
            print(f"[{task_id}] Cleaning up task data.")
            tasks_status.pop(task_id, None)
            tasks_locks.pop(task_id, None)

    return Response(stream_with_context(generate()), content_type='text/event-stream')

# --- Main Route for Initial Page Load ---
@app.route('/', methods=['GET'])
def main_page():
     # Check if ffmpeg is available on GET request for user feedback
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("ffmpeg found.")
    except (subprocess.CalledProcessError, FileNotFoundError):
        flash("সতর্কবার্তা: সার্ভারে 'ffmpeg' কমান্ড পাওয়া যায়নি। ভিডিও+অডিও মার্জ মোড কাজ করবে না।", "warning")
        print("WARNING: ffmpeg command not found.")
    return render_template('index.html') # Render the main page structure

if __name__ == '__main__':
    # Set host to '0.0.0.0' to be accessible within Docker/network
    # Enable debugging based on environment variable for flexibility
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug_mode, host='0.0.0.0', port=5000, threaded=True) # threaded=True is important for handling multiple requests with background tasks
