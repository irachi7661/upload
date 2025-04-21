import os
import time
import requests
import dropbox
import subprocess # ffmpeg চালানোর জন্য
import uuid # টেম্পোরারি ফাইলের ইউনিক নাম দেওয়ার জন্য
from flask import Flask, render_template, request, flash, redirect, url_for, make_response
from dropbox.exceptions import ApiError, AuthError
from dropbox.files import WriteMode, SaveUrlResult
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'your_very_secret_key_change_it' # একটি ভিন্ন সিক্রেট কী দিন

# --- Dropbox Configuration ---
DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_ACCESS_TOKEN", "sl.u.AFqPRrNxm7Gm1R_S--vEUVSkYMidXL-kWuA4A_cgtaqSpyKgY6ofuY6VSRERhfS3i8zMEOryx45XxLhRCXyYz_NJdwxyDZqZvgFowiKOoZ5VPZprkelIT6kL5PtcBMCqZ2b6hgZavQ56Ah0SwXNrm1IcLRYgH4LQY3g_tVMopqUcHXf1I3BrTcJwVi1SpjWePG2SW0cwN4b0zgWiG7QU6M3BbK-T1L9iosm1GU34RF7IOo1i9h446Fpr5ncSo4qqczUgHpTYB7ccDYhsyPidNK1ipWaiXkSwl4_qTniABrkU4ldK2KUNFT6QjUdO3VaTEGica408TcejC7ehH-6Q8R9a4usIMNvDLwOSRVjHwGRvHxKdphL0yEwxRY2sUMBN4X2bt4Z9FiEz_ob0uE8vdyYAWnb290LpvnJSvixeKa6TqbaDdlpoDHxm6YfQbDok9fsBbf-TRsWMvOuocdnTG5nLL_hj-URQtMPFcO0kWhUWWe6VL4xcNQ3GKCXmUkrWy9dhMtH12Hj6ZGrLvfgNDyVNYybict7jnHYOALKM9eyOgo8L87Xx2Sk6Oyrsgkrdb-t9wHWdZJw4NVeBxMQ2qDdAoIsaz31IU2NkqMK5S-h5hlLawbtrYITd_iAf0FVvbeXaqlcqeIJ4Qk5ZzedSg3fjGJOTH2rZ0M4HO_1IndNcqBp2kB3I9QIDknrC2eolhrKpiR0dh0loEm3CVMI2V74UihZ8c37nJx49khzWdL2at11M5biOiBoNXhpzwqEyovFQWqhqVZHud2lTk5P1R_9i6jFx-qNB-WehWp_33o50k9NTVnLe4fqsVjeJ-gy7LPZ7AS0mq9UKa3411G5-ilV7w6T3JpCcJeVSc_SSuVk8vFpNt3KE4bkbnC2_r6HkAn6zsFigNexPlzb1mUeQCTW_Dv0bdU29-z05gPWEn1lQaEEtyb5lB9oKQiNVs2-ZPlDKHuis0BRN7mW7dfhiyrTKhwaVDvumIsaabSJFk_MxMxLF7rO_HuPdlMoegV1EFzEUomsmxG1xGp0B1HsOLMNUJ8L2XxSj-Tt33OFroT42NBMkVyjThMxJM__IXEt6W1BFuNfKRLCqE8ZP7dDRPwo3tJ5_P4ekG85sV627kPAzTOBzbuaK8KejZuSbFtVYu8gATVOT0vjKZTiCCAIdr30xKwHNivl6kvWD8kQKN5ifPgvZ3SPdVzrUrPJLvKUVGn8fseVW7MPTTupFm0VldHroyUrwzLJGa73qZDip0iVys78Lnp8EXkv0JmQFdQKAk2HqELSTCJnsKSS3GEudg5msBFsgvexUhSbCe9W5S3Ft2CqyZlDMQL6qCek6VTHQEEFuqNMCpyL1UdP766pKFSBNNrUJm-vpQQyROdHNy78LmAkDnEP8A3AVGo8nBYGJ7UVLJflEClEBn1oJlibqmWjj6XA7g6lxBSLB8fiGLMVIFOq7c_HTJ0brqiopO5hY0XA") # পরিবেশ ভেরিয়েবল থেকে টোকেন নিন

# --- Base URL (শুধুমাত্র UID মোডের জন্য) ---
BASE_URL_UID_MODE = "https://vigilant-fishstick-2fuv.onrender.com/"

# --- Temporary File Directory ---
TEMP_DIR = "temp_files"
if not os.path.exists(TEMP_DIR):
    try:
        os.makedirs(TEMP_DIR)
        print(f"Created temporary directory: {TEMP_DIR}")
    except OSError as e:
        print(f"Error creating temporary directory {TEMP_DIR}: {e}")
        TEMP_DIR = "." # ফলব্যাক হিসেবে বর্তমান ডিরেক্টরি ব্যবহার করুন

# --- Initialize Dropbox Client ---
dbx = None
if DROPBOX_ACCESS_TOKEN != "YOUR_DROPBOX_ACCESS_TOKEN_FALLBACK":
    try:
        dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)
        dbx.users_get_current_account()
        print("Successfully connected to Dropbox.")
    except AuthError:
        print("ERROR: Invalid Dropbox access token. Check environment variable or token.")
        dbx = None
    except Exception as e:
        print(f"ERROR: Could not connect to Dropbox: {e}")
        dbx = None
else:
    print("WARNING: Dropbox access token not found in environment variable. Set DROPBOX_ACCESS_TOKEN.")


# --- Helper Function to derive filename from URL ---
def get_filename_from_url(url, default_prefix="video"):
    try:
        path = urlparse(url).path
        filename = os.path.basename(path)
        if not filename: # যদি path খালি থাকে বা '/' দিয়ে শেষ হয়
             # একটি ইউনিক নাম তৈরি করা
             filename = f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"
        # ফাইলের নামে অবৈধ অক্ষর বাদ দেওয়া (ঐচ্ছিক কিন্তু ভালো)
        # filename = "".join(c for c in filename if c.isalnum() or c in ['.', '_', '-']).strip()
        return filename or f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"
    except Exception:
        return f"{default_prefix}_{uuid.uuid4().hex[:8]}.mp4"

# --- Helper Function to download a file locally ---
def download_file_local(url, local_path):
    print(f"Downloading {url} to {local_path}")
    try:
        with requests.get(url, stream=True, timeout=180) as r: # Long timeout
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192*4): # Larger chunk size
                    f.write(chunk)
        print(f"Successfully downloaded to {local_path}")
        return True, None # Success, No error message
    except requests.exceptions.RequestException as e:
        error_msg = f"ডাউনলোড ত্রুটি ({url}): {e}"
        print(error_msg)
        return False, error_msg # Failure, Error message
    except Exception as e:
        error_msg = f"অজানা ডাউনলোড ত্রুটি ({url}): {e}"
        print(error_msg)
        return False, error_msg # Failure, Error message

# --- Helper Function to Process a Single URL via save_url ---
def process_single_url_save_url(download_url, dropbox_path, dbx_client):
    result = {
        "filename": get_filename_from_url(download_url),
        "status": "ব্যর্থ (Failed)", "message": "", "link": None, "file_number": None
    }
    print(f"Initiating save_url: {download_url} -> {dropbox_path}")
    # ... (process_single_url এর আগের save_url লজিক এখানে থাকবে) ...
    # ... (Error handling, polling, link generation) ...
    try:
        save_url_job = dbx_client.files_save_url(path=dropbox_path, url=download_url)
        job_id = None
        job_complete_successfully = False
        if save_url_job.is_async_job_id():
            job_id = save_url_job.get_async_job_id(); print(f"Async Job ID: {job_id}")
            max_retries = 15; retry_delay = 5
            for attempt in range(max_retries):
                print(f"Checking job status {job_id} ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                try:
                    job_status = dbx_client.files_save_url_check_job_status(job_id)
                    if job_status.is_complete(): job_complete_successfully = True; print(f"Job {job_id} complete."); break
                    if job_status.is_failed(): result["message"] = f"Save_url জব ফেইল্ড: {job_status.get_failed()}"; print(result["message"]); break
                    print(f"Job {job_id} in progress.")
                except ApiError as e: result["message"] = f"স্ট্যাটাস চেক API ত্রুটি: {e}"; print(result["message"]); break
            if not job_complete_successfully and result["message"] == "": result["message"] = "Save_url Timeout/Failed after polling."
        elif save_url_job.is_complete(): job_complete_successfully = True; print("Save URL sync complete.")

        if job_complete_successfully:
            result["message"] = "সরাসরি ড্রপবক্সে সেভ সফল।"
            # Get link
            try:
                settings = dropbox.sharing.SharedLinkSettings(requested_visibility=dropbox.sharing.RequestedVisibility.public)
                link_metadata = dbx_client.sharing_create_shared_link_with_settings(dropbox_path, settings=settings)
                raw_link = link_metadata.url.replace('dl=0', 'raw=1')
                result["link"] = raw_link; result["status"] = "সফল (Success)"; print("Link generated.")
            except ApiError as e:
                if e.error.is_shared_link_already_exists():
                    links = dbx_client.sharing_list_shared_links(path=dropbox_path, direct_only=True).links
                    if links: result["link"] = links[0].url.replace('dl=0', 'raw=1'); result["status"] = "সফল (Success)"; result["message"] += " (বিদ্যমান লিঙ্ক)"; print("Existing link fetched.")
                    else: result["message"] += " লিঙ্ক তৈরি/পুনরুদ্ধার করা যায়নি।"; print("Error fetching existing link.")
                else: result["message"] += f" লিঙ্ক তৈরিতে ত্রুটি: {e}"; print(f"Error creating share link: {e}")
            if result["link"] is None: result["status"] = "ব্যর্থ (Failed)"
    except ApiError as e: result["message"] = f"Save_url API ত্রুটি: {e}"; print(result["message"])
    except Exception as e: result["message"] = f"Save_url অজানা ত্রুটি: {e}"; print(result["message"])
    return result


# --- Main Route ---
@app.route('/', methods=['GET', 'POST'])
def index():
    # GET request: Show the main page
    if request.method == 'GET':
        # Check if ffmpeg is available on GET request for user feedback
        try:
            subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("ffmpeg found.")
        except (subprocess.CalledProcessError, FileNotFoundError):
            flash("সতর্কবার্তা: সার্ভারে 'ffmpeg' কমান্ড পাওয়া যায়নি। ভিডিও+অডিও মার্জ মোড কাজ করবে না।", "warning")
            print("WARNING: ffmpeg command not found.")
        return render_template('index.html', results=None)

    # POST request: Handle form submission (now via AJAX)
    if request.method == 'POST':
        if not dbx:
            flash("Dropbox সংযোগ স্থাপন করা যায়নি। Access Token পরীক্ষা করুন।", "error")
            # AJAX এর জন্য সরাসরি HTML পার্সিয়াল রিটার্ন করতে হবে
            return render_template('_results.html', results=None), 503 # Service Unavailable

        # Get common fields
        mode = request.form.get('input_mode')
        category = request.form.get('category')
        folder_1_name = request.form.get('folder_1_name')
        folder_2_name = request.form.get('folder_2_name')
        results = []

        # Validate common fields
        if not all([mode, category, folder_1_name, folder_2_name]):
             flash("অনুগ্রহ করে মোড, ক্যাটাগরি এবং ফোল্ডারের নাম পূরণ করুন।", "error")
             return render_template('_results.html', results=None), 400 # Bad Request

        base_dropbox_path_prefix = f"/{category}/{folder_1_name}/{folder_2_name}"

        # --- Logic based on input mode ---
        try:
            if mode == 'uid':
                uid = request.form.get('uid')
                number_str = request.form.get('number')
                if not uid or not number_str: raise ValueError("UID মোডের জন্য UID এবং ফাইলের সংখ্যা আবশ্যক।")
                number = int(number_str)
                if number <= 0: raise ValueError("ফাইলের সংখ্যা অবশ্যই ধনাত্মক হতে হবে।")

                print(f"Processing UID Mode: UID={uid}, Range=1-{number}, Path Prefix={base_dropbox_path_prefix}")
                for i in range(1, number + 1):
                    video_filename = f"see{i}.mp4"
                    download_url = f"{BASE_URL_UID_MODE}/{uid}/{video_filename}"
                    dropbox_path = f"{base_dropbox_path_prefix}/{video_filename}"
                    file_result = process_single_url_save_url(download_url, dropbox_path, dbx)
                    file_result["file_number"] = i
                    results.append(file_result)

            elif mode == 'link':
                direct_link = request.form.get('direct_link')
                if not direct_link: raise ValueError("লিঙ্ক মোডের জন্য সরাসরি লিঙ্ক আবশ্যক।")
                parsed_url = urlparse(direct_link)
                if not all([parsed_url.scheme, parsed_url.netloc]): raise ValueError("অবৈধ URL ফরম্যাট।")

                print(f"Processing Link Mode: URL={direct_link}, Path Prefix={base_dropbox_path_prefix}")
                extracted_filename = get_filename_from_url(direct_link)
                dropbox_path = f"{base_dropbox_path_prefix}/{extracted_filename}"
                file_result = process_single_url_save_url(direct_link, dropbox_path, dbx)
                results.append(file_result)

            elif mode == 'merge':
                video_link = request.form.get('video_link')
                audio_link = request.form.get('audio_link')
                if not video_link or not audio_link: raise ValueError("মার্জ মোডের জন্য ভিডিও এবং অডিও লিঙ্ক উভয়ই আবশ্যক।")
                # Validate URLs (basic)
                pv = urlparse(video_link); pa = urlparse(audio_link)
                if not all([pv.scheme, pv.netloc]) or not all([pa.scheme, pa.netloc]): raise ValueError("ভিডিও বা অডিও লিঙ্ক অবৈধ।")

                print(f"Processing Merge Mode: Video={video_link}, Audio={audio_link}, Path Prefix={base_dropbox_path_prefix}")

                # --- Merge Specific Logic ---
                # 1. Define temp file paths
                task_id = uuid.uuid4().hex # Unique ID for this task's files
                base_filename = get_filename_from_url(video_link, "merged_video")
                local_video_path = os.path.join(TEMP_DIR, f"{task_id}_video.tmp")
                local_audio_path = os.path.join(TEMP_DIR, f"{task_id}_audio.tmp")
                local_output_path = os.path.join(TEMP_DIR, f"{task_id}_{base_filename}")
                dropbox_path = f"{base_dropbox_path_prefix}/{base_filename}"

                merge_result = { "filename": base_filename, "status": "ব্যর্থ (Failed)", "message": "", "link": None, "file_number": None }
                download_ok = False
                ffmpeg_ok = False

                try:
                    # 2. Download video and audio
                    video_dl_ok, video_err = download_file_local(video_link, local_video_path)
                    if not video_dl_ok: merge_result["message"] = f"ভিডিও ডাউনলোড ব্যর্থ: {video_err}"; raise Exception(merge_result["message"])

                    audio_dl_ok, audio_err = download_file_local(audio_link, local_audio_path)
                    if not audio_dl_ok: merge_result["message"] = f"অডিও ডাউনলোড ব্যর্থ: {audio_err}"; raise Exception(merge_result["message"])
                    download_ok = True

                    # 3. Run ffmpeg
                    print(f"Running ffmpeg to merge into {local_output_path}")
                    ffmpeg_command = [
                        'ffmpeg',
                        '-i', local_video_path,
                        '-i', local_audio_path,
                        '-c:v', 'copy',        # Copy video stream
                        '-c:a', 'aac',         # Encode audio to AAC
                        '-map', '0:v:0',       # Map video from first input
                        '-map', '1:a:0',       # Map audio from second input
                        '-y',                  # Overwrite output file if exists
                        '-hide_banner', '-loglevel', 'error', # Less verbose output
                        local_output_path
                    ]
                    try:
                        process = subprocess.run(ffmpeg_command, check=True, capture_output=True, text=True)
                        print("ffmpeg merge successful.")
                        ffmpeg_ok = True
                    except FileNotFoundError:
                         merge_result["message"] = "মার্জ ত্রুটি: সার্ভারে 'ffmpeg' কমান্ড পাওয়া যায়নি।"
                         print(merge_result["message"])
                         raise Exception(merge_result["message"])
                    except subprocess.CalledProcessError as e:
                        merge_result["message"] = f"FFmpeg মার্জ ত্রুটি: {e.stderr}"
                        print(f"FFmpeg Error:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
                        raise Exception(merge_result["message"])

                    # 4. Upload merged file
                    print(f"Uploading merged file {local_output_path} to {dropbox_path}")
                    try:
                        with open(local_output_path, 'rb') as f:
                            # Use chunked upload for potentially large files
                            file_size = os.path.getsize(local_output_path)
                            chunk_size = 100 * 1024 * 1024 # 100MB chunks

                            if file_size <= chunk_size:
                                dbx.files_upload(f.read(), dropbox_path, mode=WriteMode('overwrite'))
                            else:
                                upload_session_start_result = dbx.files_upload_session_start(f.read(chunk_size))
                                cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id, offset=f.tell())
                                commit = dropbox.files.CommitInfo(path=dropbox_path, mode=WriteMode('overwrite'))
                                while f.tell() < file_size:
                                    if (file_size - f.tell()) <= chunk_size:
                                        dbx.files_upload_session_finish(f.read(chunk_size), cursor, commit)
                                        print("Chunked upload finished.")
                                    else:
                                        dbx.files_upload_session_append_v2(f.read(chunk_size), cursor)
                                        cursor.offset = f.tell()
                                        print(f"Uploaded chunk, offset: {cursor.offset}")

                        print("Upload successful.")
                        merge_result["message"] = "ডাউনলোড, মার্জ ও আপলোড সফল।"

                        # 5. Get share link
                        try:
                            settings = dropbox.sharing.SharedLinkSettings(requested_visibility=dropbox.sharing.RequestedVisibility.public)
                            link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path, settings=settings)
                            raw_link = link_metadata.url.replace('dl=0', 'raw=1')
                            merge_result["link"] = raw_link
                            merge_result["status"] = "সফল (Success)"
                            print("Share link generated.")
                        except ApiError as e:
                             # Handle link generation error (as in other modes)
                             if e.error.is_shared_link_already_exists():
                                links = dbx.sharing_list_shared_links(path=dropbox_path, direct_only=True).links
                                if links: merge_result["link"] = links[0].url.replace('dl=0', 'raw=1'); merge_result["status"] = "সফল (Success)"; merge_result["message"] += " (বিদ্যমান লিঙ্ক)"; print("Existing link fetched.")
                                else: merge_result["message"] += " লিঙ্ক তৈরি/পুনরুদ্ধার করা যায়নি।"; print("Error fetching existing link.")
                             else: merge_result["message"] += f" লিঙ্ক তৈরিতে ত্রুটি: {e}"; print(f"Error creating share link: {e}")
                             if merge_result["link"] is None: merge_result["status"] = "ব্যর্থ (Failed)" # Mark failed if no link

                    except ApiError as e:
                        merge_result["message"] = f"Dropbox আপলোড ত্রুটি: {e}"
                        print(f"Dropbox Upload API Error: {e}")
                        raise Exception(merge_result["message"])
                    except Exception as e:
                         merge_result["message"] = f"আপলোড করার সময় অজানা ত্রুটি: {e}"
                         print(f"Unknown upload error: {e}")
                         raise Exception(merge_result["message"])

                except Exception as final_error:
                     # Error occurred during download, ffmpeg, or upload
                     print(f"Error in merge process: {final_error}")
                     # Message should already be set in merge_result

                finally:
                    # 6. Cleanup temporary files ALWAYS
                    print("Cleaning up temporary files...")
                    for temp_file in [local_video_path, local_audio_path, local_output_path]:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                                print(f"Removed temp file: {temp_file}")
                            except OSError as e:
                                print(f"Error removing temp file {temp_file}: {e}")
                results.append(merge_result)


            else:
                raise ValueError("অজানা ইনপুট মোড সিলেক্ট করা হয়েছে।")

        # Handle potential validation errors caught earlier
        except ValueError as e:
            flash(str(e), "error")
            # Return partial HTML with error flash message
            return render_template('_results.html', results=None), 400 # Bad Request
        except Exception as e:
             # Catch unexpected errors during processing
             print(f"Unexpected Error: {e}")
             flash(f"একটি অপ্রত্যাশিত ত্রুটি ঘটেছে: {e}", "error")
             return render_template('_results.html', results=None), 500 # Internal Server Error


        # --- Provide feedback (Flash messages are now part of the partial) ---
        # Determine overall status for flash message in partial template
        if not results:
             flash("কোনো ফাইল প্রসেস করার জন্য পাওয়া যায়নি।", "warning")
        elif all(r['status'] == "সফল (Success)" for r in results):
             flash("সকল ফাইল সফলভাবে প্রসেস করা হয়েছে।", "success")
        elif all(r['status'] == "ব্যর্থ (Failed)" for r in results):
             flash("সকল ফাইল প্রসেস করতে সমস্যা হয়েছে।", "error")
        else:
             flash("প্রক্রিয়া সম্পন্ন হয়েছে কিন্তু কিছু ত্রুটি ছিল।", "warning")

        # Return ONLY the results partial HTML for AJAX request
        return render_template('_results.html', results=results)

if __name__ == '__main__':
     # Important: Set host to '0.0.0.0' to be accessible within Docker
     app.run(debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true", host='0.0.0.0', port=5000)
