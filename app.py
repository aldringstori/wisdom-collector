import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Menu, Listbox, END
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import json
import subprocess
import queue
import threading
import logging
from pytube import Playlist
import PyPDF2
from googletrans import Translator
from docx import Document

config_file = "settings.json"
config = {}
download_queue = queue.Queue()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configs and Settings
def load_config(config_filename):
    global config
    try:
        with open(config_filename, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {
            "download_folder": os.path.join(os.getcwd(), "Transcriptions")
        }
        with open(config_filename, 'w') as f:
            json.dump(config, f)
    if 'download_folder' not in config:
        config['download_folder'] = os.path.join(os.getcwd(), "Transcriptions")
        save_config(config, config_filename)
    return config

def save_config(config, config_filename):
    with open(config_filename, 'w') as f:
        json.dump(config, f)

def create_folder(folder_name):
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

def change_downloads_location():
    global config
    folder_selected = filedialog.askdirectory(initialdir=config.get('download_folder', os.getcwd()))
    if folder_selected:
        config['download_folder'] = folder_selected
        save_config(config, config_file)
        messagebox.showinfo("Success", f"Download location changed to {config['download_folder']}")

def open_explorer_at_location(path=None):
    if path is None:
        path = os.getcwd()
    if os.name == 'nt':
        subprocess.run(['explorer', path], check=True)
    elif os.name == 'posix':
        subprocess.run(['open', path] if os.uname().sysname == 'Darwin' else ['xdg-open', path], check=True)
    else:
        raise OSError("Unsupported operating system")

def process_video_urls(video_urls):
    total = len(video_urls)
    for index, url in enumerate(video_urls):
        update_global_progress(index + 1, total)

def get_channel_name_from_url(channel_url):
    parts = channel_url.split('@')
    if len(parts) > 1:
        channel_name_part = parts[-1].split('/', 1)[0]
        return channel_name_part
    return None

def get_channel_name_from_shorts_url(shorts_url):
    match = re.search(r"youtube\.com/[@]([^/]+)/shorts", shorts_url)
    if match:
        return match.group(1)
    else:
        return "UnknownChannel"

def get_video_title(video_url):
    response = requests.get(video_url)
    if response.ok:
        title_match = re.search(r'"title":"([^"]+)"', response.text)
        if title_match:
            return re.sub(r'[\\/*?:"<>|]', '', title_match.group(1))
        else:
            video_id_match = re.search(r"v=([a-zA-Z0-9_-]+)", video_url)
            return video_id_match.group(1) if video_id_match else "unknown_title"
    return "unknown_title"

def get_playlist_id_from_url(playlist_url):
    match = re.search(r"list=([a-zA-Z0-9_-]+)", playlist_url)
    if match:
        return match.group(1)
    raise ValueError("Invalid YouTube playlist URL")

def get_playlist_videos_py(p_url):
    playlist = Playlist(p_url)
    video_urls = playlist.video_urls
    return video_urls

def update_global_progress(progress_var, current, total):
    percentage = (current / total) * 100
    progress_var.set(percentage)
    status_label.config(text=f"Processed {current} of {total} videos")
    root.update_idletasks()

def scrape_youtube(video_urls):
    videos_info = []
    for index, video_url in enumerate(video_urls):
        update_global_progress(index + 1, len(video_urls))
        video_data = fetch_video_data(video_url)
        videos_info.append(video_data)
    return videos_info

def fetch_video_data(video_url):
    video_id = get_video_id_from_url(video_url)
    response = requests.get(video_url)
    soup = bs(response.text, 'html.parser')
    video_details = utube_service.get_video_details(soup)
    return {
        "title": video_details.get("title", ""),
        "channel": video_details.get("channel", ""),
        "description": video_details.get("description", ""),
        "video_id": video_id,
        "external_link": f"https://www.youtube.com/watch?v={video_id}"
    }

def pdf_to_text():
    pdf_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
    if pdf_path:
        threading.Thread(target=process_pdf, args=(pdf_path,)).start()
    else:
        messagebox.showwarning("No File Selected", "Please select a PDF file to convert.")

def process_pdf(pdf_path):
    global progress_var
    folder = config.get('download_folder', os.path.join(os.getcwd(), "Transcriptions"))
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        num_pages = len(pdf_reader.pages)
        text_content = []

        for i, page in enumerate(pdf_reader.pages):
            text = page.extract_text()
            if text:
                text_content.append(text)
            update_progress(i + 1, num_pages)

    text_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".txt"
    text_file_path = os.path.join(folder, text_filename)
    with open(text_file_path, "w", encoding='utf-8') as text_file:
        text_file.write("\n".join(text_content))

    messagebox.showinfo("Success", f"PDF converted to text and saved as {text_file_path}")

def docx_to_text():
    docx_path = filedialog.askopenfilename(filetypes=[("DOCX Files", "*.docx")])
    if docx_path:
        threading.Thread(target=process_docx, args=(docx_path,)).start()
    else:
        messagebox.showwarning("No File Selected", "Please select a DOCX file to convert.")

def process_docx(docx_path):
    global progress_var
    folder = config.get('download_folder', os.path.join(os.getcwd(), "Transcriptions"))
    doc = Document(docx_path)
    text_content = []

    for para in doc.paragraphs:
        text_content.append(para.text)

    text_filename = os.path.splitext(os.path.basename(docx_path))[0] + ".txt"
    text_file_path = os.path.join(folder, text_filename)
    with open(text_file_path, "w", encoding='utf-8') as text_file:
        text_file.write("\n".join(text_content))

    messagebox.showinfo("Success", f"DOCX converted to text and saved as {text_file_path}")

def fetch_and_save_transcript(video_url, listbox, config):
    try:
        title = get_video_title(video_url)
        transcript = fetch_transcript(video_url)
        if transcript:
            save_transcript_to_text(transcript, sanitize_filename(title), config['download_folder'])
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Error fetching/saving transcript for {video_url}: {str(e)}")
        return False

def process_videos(video_urls, listbox, config):
    for video_url in video_urls:
        try:
            success = fetch_and_save_transcript(video_url, listbox, config)
            listbox.insert(END, f"Processed: {get_video_title(video_url)} - {'Success' if success else 'Failed'}")
            listbox.update_idletasks()
            logging.info(f"Processed {get_video_title(video_url)}: {'Success' if success else 'Failed'}")
        except Exception as e:
            logging.error(f"Failed to process video {video_url}: {str(e)}")
        time.sleep(5)

def threaded_process_videos(video_urls, listbox, config):
    thread = threading.Thread(target=process_videos, args=(video_urls, listbox, config))
    thread.start()

def update_progress(current, total):
    progress = (current / total) * 100
    root.after(50, lambda: progress_var.set(progress))
    root.after(50, lambda: status_label.config(text=f"Processed {current} of {total} pages"))

def get_all_playlist_videos(playlist_id, sleep=1):
    try:
        videos = []
        for video in scrapetube.get_playlist(playlist_id, sleep=sleep):
            video_data = {
                'id': video['videoId'],
                'title': video['title']
            }
            videos.append(video_data)
            if len(videos) % 100 == 0:
                print(f"Retrieved {len(videos)} videos so far...")
        return videos
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def fetch_videos_from_channel_selenium(channel_url):
    driver = webdriver.Chrome()
    driver.get(channel_url)
    time.sleep(5)
    last_height = driver.execute_script("return document.documentElement.scrollHeight")

    while True:
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(5)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    videos_data = []
    videos = driver.find_elements(By.CSS_SELECTOR, "a#video-title-link")
    for video in videos:
        video_url = video.get_attribute('href')
        video_title = video.get_attribute('title')
        videos_data.append((video_url, video_title))

    driver.quit()
    return videos_data

def fetch_videos_from_shorts_page(shorts_url):
    driver = webdriver.Chrome()
    driver.get(shorts_url)
    time.sleep(5)
    last_height = driver.execute_script("return document.documentElement.scrollHeight")

    while True:
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(5)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    videos_data = []
    videos = driver.find_elements(By.CSS_SELECTOR, "a.yt-simple-endpoint.style-scope.ytd-rich-grid-slim-media")
    for video in videos:
        href = video.get_attribute('href')
        title = video.find_element(By.ID, "video-title").text
        videos_data.append((href, title))

    driver.quit()
    return videos_data

def fetch_playlist_videos(playlist_id):
    videos = []
    try:
        for video in scrapetube.get_playlist(playlist_id):
            videos.append(video['videoId'])
    except Exception as e:
        print(f"An error occurred while fetching videos from the playlist: {e}")
    return videos

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '', filename)

def download_all_shorts_transcripts(shorts_url, config):
    print(f"Starting download process for shorts from URL: {shorts_url}")
    channel_name = get_channel_name_from_shorts_url(shorts_url)
    if not channel_name:
        print("Could not extract channel name from URL. Please check the URL and try again.")
        return

    folder_name = os.path.join(config['download_folder'], channel_name)
    print(f"Downloading transcripts to folder: {folder_name}")
    create_folder(folder_name)

    shorts_data = fetch_videos_from_shorts_page(shorts_url)
    print(f"Found {len(shorts_data)} shorts to process.")
    if not shorts_data:
        print("No shorts data found after fetching the page. Please check the URL and try again.")
        return

    for url, title in shorts_data:
        sanitized_title = re.sub(r'[\\/*?:"<>|]', '', title)
        print(f"Processing short: {sanitized_title} with URL {url}")

        video_url = f"https://www.youtube.com{url}"
        print(f"Transformed URL: {video_url}")

        try:
            transcript, error = fetch_shorts_transcript(video_url)
            if error:
                print(f"Error downloading transcript for {sanitized_title}: {error}")
                continue
            if not transcript:
                print(f"No transcript available for {sanitized_title}.")
                continue

            print(f"Transcript fetched for {sanitized_title}.")
            save_path = save_transcript_to_text(transcript, sanitized_title, folder_name)
            print(f"Transcript for {sanitized_title} saved to {save_path}.")
        except Exception as e:
            print(f"An unexpected error occurred while processing {sanitized_title}: {str(e)}")

def fetch_shorts_transcript(shorts_url):
    shorts_url = shorts_url.replace("/shorts/", "/watch?v=")
    match = re.search(r"v=([a-zA-Z0-9_-]+)", shorts_url)
    if match is None:
        return None, "Could not find a valid video ID in the URL."

    video_id = match.group(1)
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en']).fetch()
        return transcript, None
    except NoTranscriptFound:
        return None, "No transcript found for the provided video ID."
    except TranscriptsDisabled:
        return None, "Transcripts are disabled for this video."

def fetch_transcript(video_url):
    video_id = re.search(r"v=([a-zA-Z0-9_-]+)", video_url).group(1)
    translator = Translator()

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(['en']).fetch()
            return ' '.join([entry['text'] for entry in transcript])
        except NoTranscriptFound:
            try:
                pt_transcript = transcript_list.find_transcript(['pt']).fetch()
                translated_text = ' '.join([translator.translate(entry['text'], src='pt', dest='en').text for entry in pt_transcript])
                return translated_text
            except Exception as e:
                print(f"Failed to fetch or translate Portuguese transcript for video {video_id}: {str(e)}")
    except Exception as e:
        print(f"Unable to fetch any transcripts for video {video_id}: {str(e)}")
        return None

def fetch_videos_with_transcripts(channel_url):
    videos_data = fetch_videos_from_channel_selenium(channel_url)
    results = []

    for video_url, video_title in videos_data:
        transcript = fetch_transcript(video_url)
        if transcript is not None:
            results.append({'url': video_url, 'title': video_title, 'transcript': transcript})

    return results

def save_transcript_to_text(transcript, filename, folder):
    if transcript is None:
        print(f"No transcript available to save for {filename}.")
        return None

    if not os.path.exists(folder):
        create_folder(folder)
    file_path = os.path.join(folder, f"{filename}.txt")

    if isinstance(transcript, list):
        transcript = '\n'.join([segment.get('text', '') for segment in transcript])

    with open(file_path, "w", encoding='utf-8') as file:
        file.write(transcript)

    return file_path

def process_video_downloads():
    while not download_queue.empty():
        channel_url = download_queue.get()
        videos = fetch_videos_from_channel_selenium(channel_url)
        for video_url, title in videos:
            print(f"Downloading {title} from {video_url}")
        download_queue.task_done()
    messagebox.showinfo("Download Complete", "All queued videos have been downloaded.")

def add_to_queue(url, listbox):
    if url:
        download_queue.put(url)
        listbox.insert(tk.END, url)
        messagebox.showinfo("Queue Update", "URL added to queue.")
    else:
        messagebox.showwarning("Input Error", "Please enter a valid URL.")

def start_queue_download(listbox):
    def process_next_channel():
        while not download_queue.empty():
            url = download_queue.get()
            try:
                on_submit_channel(url, config)
                listbox.delete(0)
            except Exception as e:
                messagebox.showerror("Download Error", f"Failed to download from {url}: {str(e)}")
            download_queue.task_done()
            if not download_queue.empty():
                root.after(100, process_next_channel)
            else:
                messagebox.showinfo("Download Complete", "All items in the queue have been processed.")
    root.after(100, process_next_channel)

def on_submit_video(video_url, config):
    if not video_url.strip():
        tk.messagebox.showwarning("Warning", "Please enter a valid YouTube URL.")
        return

    try:
        transcript = fetch_transcript(video_url)
        if transcript is None:
            raise ValueError("Failed to fetch transcript. It may not be available.")

        filename = get_video_title(video_url)
        if filename == "ErrorFetchingTitle" or not filename:
            raise ValueError("Failed to fetch video title.")

        save_transcript_to_text(transcript, filename, config['download_folder'])
        tk.messagebox.showinfo("Success", f"Transcript downloaded successfully and saved to '{os.path.join(config['download_folder'], filename)}.txt'.")

    except Exception as e:
        tk.messagebox.showerror("Error", f"An error occurred: {e}")

def on_submit_shorts(shorts_url, config):
    try:
        transcript, error = fetch_shorts_transcript(shorts_url)
        if error:
            messagebox.showerror("Error", error)
            return
        title = get_video_title(shorts_url)
        if not title:
            messagebox.showerror("Error", "Failed to retrieve video title.")
            return
        save_path = save_transcript_to_text(transcript, title, config['download_folder'])
        if save_path:
            messagebox.showinfo("Success", f"Transcript saved to {save_path}")
        else:
            messagebox.showerror("Error", "Failed to save the transcript.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def on_submit_channel(channel_url, config):
    if not channel_url:
        messagebox.showerror("Error", "Please enter a valid channel URL.")
        return
    channel_name = get_channel_name_from_url(channel_url)
    if not channel_name:
        messagebox.showerror("Error", "Could not determine the channel name from URL.")
        return
    create_folder(os.path.join(config['download_folder'], channel_name))
    videos_data = fetch_videos_from_channel_selenium(channel_url)
    total_videos = len(videos_data)
    for i, (video_url, video_title) in enumerate(videos_data):
        try:
            video_id = re.search(r"v=([a-zA-Z0-9_-]+)", video_url).group(1)
            transcript = fetch_transcript(video_url)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
            save_transcript_to_text(transcript, safe_title, os.path.join(config['download_folder'], channel_name))
        except Exception as e:
            messagebox.showerror("Error", f"Error occurred for video {video_title}: {e}")

def on_submit_all_shorts(url_entry_widget, config):
    shorts_url = url_entry_widget.get()
    if not shorts_url.strip():
        messagebox.showwarning("Warning", "Please enter a valid YouTube channel URL.")
        return

    try:
        download_all_shorts_transcripts(shorts_url, config)
        messagebox.showinfo("Success", "All transcripts for shorts have been downloaded.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def on_submit_playlist(playlist_url, config):
    if not playlist_url.strip():
        messagebox.showwarning("Warning", "Please enter a valid YouTube playlist URL.")
        return

    try:
        video_urls = get_playlist_videos_py(playlist_url)
        if not video_urls:
            messagebox.showerror("Error", "Could not fetch videos from the playlist.")
            return

        folder_name = f"Playlist_{get_playlist_id_from_url(playlist_url)}"
        full_folder_path = os.path.join(config['download_folder'], folder_name)
        create_folder(full_folder_path)

        total_videos = len(video_urls)
        for index, video_url in enumerate(video_urls, start=1):
            video_title = get_video_title(video_url)
            try:
                transcript = fetch_transcript(video_url)
                if not transcript:
                    print(f"No transcript available for video titled '{video_title}'")
                    continue

                filename = sanitize_filename(video_title)
                save_transcript_to_text(transcript, filename, full_folder_path)
                update_global_progress(progress_var, total_videos, index)
                print(f"Transcript for {video_title} saved to {filename}.txt")
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {e}")

        messagebox.showinfo("Success", f"All transcripts have been downloaded. Total: {total_videos}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def start_threaded_process(video_urls, listbox):
    thread = threading.Thread(target=process_videos, args=(video_urls, listbox))
    thread.start()

# UI
def setup_ui(root, config):
    main_frame = tk.Frame(root, padx=15, pady=15)
    main_frame.pack(expand=True, fill=tk.BOTH)

    menu_bar = Menu(root)
    root.config(menu=menu_bar)

    file_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Open Downloads Location", command=open_explorer_at_location)

    settings_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="Settings", menu=settings_menu)
    settings_menu.add_command(label="Change Downloads Location", command=change_downloads_location)

    global progress_var
    progress_var = tk.DoubleVar()

    global progress_bar
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress_bar.pack(fill='x', padx=5, pady=5)

    global status_label
    status_label = tk.Label(root, text="")
    status_label.pack(fill='x', padx=5, pady=5)

    single_frame = tk.LabelFrame(main_frame, text="Single", borderwidth=2, relief="groove")
    single_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    video_frame = tk.LabelFrame(single_frame, text="Single YouTube Video Download", borderwidth=2, relief="groove")
    video_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(video_frame, text="Enter YouTube Video URL:").pack(side="top", fill='x', padx=5, pady=5)
    url_entry = tk.Entry(video_frame, width=50)
    url_entry.pack(side="top", fill='x', padx=5, pady=5)
    submit_btn = tk.Button(video_frame, text="Download Transcript for Video", command=lambda: on_submit_video(url_entry.get(), config))
    submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    shorts_frame = tk.LabelFrame(single_frame, text="Single YouTube Shorts Download", borderwidth=2, relief="groove")
    shorts_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(shorts_frame, text="Enter YouTube Shorts URL:").pack(side="top", fill='x', padx=5, pady=5)
    shorts_url_entry = tk.Entry(shorts_frame, width=50)
    shorts_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    shorts_submit_btn = tk.Button(shorts_frame, text="Download Transcript for Shorts", command=lambda: on_submit_shorts(shorts_url_entry.get(), config))
    shorts_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    massive_frame = tk.LabelFrame(main_frame, text="Massive", borderwidth=2, relief="groove")
    massive_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    channel_frame = tk.LabelFrame(massive_frame, text="Channel Videos", borderwidth=2, relief="groove")
    channel_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(channel_frame, text="All transcriptions from all videos of a channel:").pack(side="top", fill='x', padx=5, pady=5)
    channel_url_entry = tk.Entry(channel_frame, width=50)
    channel_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    channel_submit_btn = tk.Button(channel_frame, text="Download Transcripts for Channel", command=lambda: on_submit_channel(channel_url_entry.get(), config))
    channel_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    all_shorts_frame = tk.LabelFrame(massive_frame, text="Channel Shorts", borderwidth=2, relief="groove")
    all_shorts_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(all_shorts_frame, text="All transcriptions from all shorts of a channel:").pack(side="top", fill='x', padx=5, pady=5)
    all_shorts_url_entry = tk.Entry(all_shorts_frame, width=50)
    all_shorts_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    all_shorts_submit_btn = tk.Button(all_shorts_frame, text="Download All Shorts Transcripts", command=lambda: on_submit_all_shorts(all_shorts_url_entry, config))
    all_shorts_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    playlist_frame = tk.LabelFrame(massive_frame, text="Playlist Videos", borderwidth=2, relief="groove")
    playlist_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(playlist_frame, text="Enter YouTube Playlist URL:").pack(side="top", fill='x', padx=5, pady=5)
    playlist_url_entry = tk.Entry(playlist_frame, width=50)
    playlist_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    playlist_submit_btn = tk.Button(playlist_frame, text="Download Playlist Transcripts", command=lambda: on_submit_playlist(playlist_url_entry.get(), config))
    playlist_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    converter_frame = tk.LabelFrame(main_frame, text="Converter", borderwidth=2, relief="groove")
    converter_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

    pdf_frame = tk.LabelFrame(converter_frame, text="PDF to Text", borderwidth=2, relief="groove")
    pdf_frame.pack(fill='x', padx=5, pady=5, expand=True)
    pdf_convert_btn = tk.Button(pdf_frame, text="Convert PDF to Text", command=pdf_to_text)
    pdf_convert_btn.pack(side="top", fill='x', padx=5, pady=5)

    docx_frame = tk.LabelFrame(converter_frame, text="DOCX to Text", borderwidth=2, relief="groove")
    docx_frame.pack(fill='x', padx=5, pady=5, expand=True)
    docx_convert_btn = tk.Button(docx_frame, text="Convert DOCX to Text", command=docx_to_text)
    docx_convert_btn.pack(side="top", fill='x', padx=5, pady=5)

    queue_frame = tk.LabelFrame(main_frame, text="Queue Management", borderwidth=2, relief="groove")
    queue_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

    queue_display = tk.Listbox(queue_frame, height=20, width=50)
    queue_display.pack(padx=10, pady=10, expand=True, fill='both')

    for video_url, video_title in videos_data:
        try:
            video_id = re.search(r"v=([a-zA-Z0-9_-]+)", video_url).group(1)
            transcript = fetch_transcript(video_url)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", video_title)
            save_transcript_to_text(transcript, safe_title, os.path.join(config['download_folder'], channel_name))
        except Exception as e:
            messagebox.showerror("Error", f"Error occurred for video {video_title}: {e}")


def on_submit_all_shorts(url_entry_widget, config):
    shorts_url = url_entry_widget.get()
    if not shorts_url.strip():
        messagebox.showwarning("Warning", "Please enter a valid YouTube channel URL.")
        return

    try:
        download_all_shorts_transcripts(shorts_url, config)
        messagebox.showinfo("Success", "All transcripts for shorts have been downloaded.")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def on_submit_playlist(playlist_url, config):
    if not playlist_url.strip():
        messagebox.showwarning("Warning", "Please enter a valid YouTube playlist URL.")
        return

    try:
        video_urls = get_playlist_videos_py(playlist_url)
        if not video_urls:
            messagebox.showerror("Error", "Could not fetch videos from the playlist.")
            return

        folder_name = f"Playlist_{get_playlist_id_from_url(playlist_url)}"
        full_folder_path = os.path.join(config['download_folder'], folder_name)
        create_folder(full_folder_path)

        total_videos = len(video_urls)
        for index, video_url in enumerate(video_urls, start=1):
            video_title = get_video_title(video_url)
            try:
                transcript = fetch_transcript(video_url)
                if not transcript:
                    print(f"No transcript available for video titled '{video_title}'")
                    continue

                filename = sanitize_filename(video_title)
                save_transcript_to_text(transcript, filename, full_folder_path)
                update_global_progress(progress_var, total_videos, index)
                print(f"Transcript for {video_title} saved to {filename}.txt")
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred: {e}")

        messagebox.showinfo("Success", f"All transcripts have been downloaded. Total: {total_videos}")
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def start_threaded_process(video_urls, listbox):
    thread = threading.Thread(target=process_videos, args=(video_urls, listbox))
    thread.start()

# UI
def setup_ui(root, config):
    main_frame = tk.Frame(root, padx=15, pady=15)
    main_frame.pack(expand=True, fill=tk.BOTH)

    menu_bar = Menu(root)
    root.config(menu=menu_bar)

    file_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="File", menu=file_menu)
    file_menu.add_command(label="Open Downloads Location", command=open_explorer_at_location)

    settings_menu = Menu(menu_bar, tearoff=0)
    menu_bar.add_cascade(label="Settings", menu=settings_menu)
    settings_menu.add_command(label="Change Downloads Location", command=change_downloads_location)

    global progress_var
    progress_var = tk.DoubleVar()

    global progress_bar
    progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100)
    progress_bar.pack(fill='x', padx=5, pady=5)

    global status_label
    status_label = tk.Label(root, text="")
    status_label.pack(fill='x', padx=5, pady=5)

    single_frame = tk.LabelFrame(main_frame, text="Single", borderwidth=2, relief="groove")
    single_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    video_frame = tk.LabelFrame(single_frame, text="Single YouTube Video Download", borderwidth=2, relief="groove")
    video_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(video_frame, text="Enter YouTube Video URL:").pack(side="top", fill='x', padx=5, pady=5)
    url_entry = tk.Entry(video_frame, width=50)
    url_entry.pack(side="top", fill='x', padx=5, pady=5)
    submit_btn = tk.Button(video_frame, text="Download Transcript for Video", command=lambda: on_submit_video(url_entry.get(), config))
    submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    shorts_frame = tk.LabelFrame(single_frame, text="Single YouTube Shorts Download", borderwidth=2, relief="groove")
    shorts_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(shorts_frame, text="Enter YouTube Shorts URL:").pack(side="top", fill='x', padx=5, pady=5)
    shorts_url_entry = tk.Entry(shorts_frame, width=50)
    shorts_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    shorts_submit_btn = tk.Button(shorts_frame, text="Download Transcript for Shorts", command=lambda: on_submit_shorts(shorts_url_entry.get(), config))
    shorts_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    massive_frame = tk.LabelFrame(main_frame, text="Massive", borderwidth=2, relief="groove")
    massive_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    channel_frame = tk.LabelFrame(massive_frame, text="Channel Videos", borderwidth=2, relief="groove")
    channel_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(channel_frame, text="All transcriptions from all videos of a channel:").pack(side="top", fill='x', padx=5, pady=5)
    channel_url_entry = tk.Entry(channel_frame, width=50)
    channel_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    channel_submit_btn = tk.Button(channel_frame, text="Download Transcripts for Channel", command=lambda: on_submit_channel(channel_url_entry.get(), config))
    channel_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    all_shorts_frame = tk.LabelFrame(massive_frame, text="Channel Shorts", borderwidth=2, relief="groove")
    all_shorts_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(all_shorts_frame, text="All transcriptions from all shorts of a channel:").pack(side="top", fill='x', padx=5, pady=5)
    all_shorts_url_entry = tk.Entry(all_shorts_frame, width=50)
    all_shorts_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    all_shorts_submit_btn = tk.Button(all_shorts_frame, text="Download All Shorts Transcripts", command=lambda: on_submit_all_shorts(all_shorts_url_entry, config))
    all_shorts_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    playlist_frame = tk.LabelFrame(massive_frame, text="Playlist Videos", borderwidth=2, relief="groove")
    playlist_frame.pack(fill='x', padx=5, pady=5, expand=True)
    tk.Label(playlist_frame, text="Enter YouTube Playlist URL:").pack(side="top", fill='x', padx=5, pady=5)
    playlist_url_entry = tk.Entry(playlist_frame, width=50)
    playlist_url_entry.pack(side="top", fill='x', padx=5, pady=5)
    playlist_submit_btn = tk.Button(playlist_frame, text="Download Playlist Transcripts", command=lambda: on_submit_playlist(playlist_url_entry.get(), config))
    playlist_submit_btn.pack(side="top", fill='x', padx=5, pady=5)

    converter_frame = tk.LabelFrame(main_frame, text="Converter", borderwidth=2, relief="groove")
    converter_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

    pdf_frame = tk.LabelFrame(converter_frame, text="PDF to Text", borderwidth=2, relief="groove")
    pdf_frame.pack(fill='x', padx=5, pady=5, expand=True)
    pdf_convert_btn = tk.Button(pdf_frame, text="Convert PDF to Text", command=pdf_to_text)
    pdf_convert_btn.pack(side="top", fill='x', padx=5, pady=5)

    docx_frame = tk.LabelFrame(converter_frame, text="DOCX to Text", borderwidth=2, relief="groove")
    docx_frame.pack(fill='x', padx=5, pady=5, expand=True)
    docx_convert_btn = tk.Button(docx_frame, text="Convert DOCX to Text", command=docx_to_text)
    docx_convert_btn.pack(side="top", fill='x', padx=5, pady=5)

    queue_frame = tk.LabelFrame(main_frame, text="Queue Management", borderwidth=2, relief="groove")
    queue_frame.grid(row=0, column=3, rowspan=2, padx=5, pady=5, sticky="nsew")

    queue_display = tk.Listbox(queue_frame, height=20, width=50)
    queue_display.pack(padx=10, pady=10, expand=True, fill='both')

    add_to_queue_btn = tk.Button(queue_frame, text="Add to Queue", command=lambda: add_to_queue(channel_url_entry.get(), queue_display))
    add_to_queue_btn.pack(side=tk.TOP, padx=5, pady=5)

    start_queue_btn = tk.Button(queue_frame, text="Start Download from Queue", command=lambda: start_queue_download(queue_display))
    start_queue_btn.pack(side=tk.TOP, padx=5, pady=5)

    main_frame.grid_columnconfigure(0, weight=1)
    main_frame.grid_columnconfigure(1, weight=1)
    main_frame.grid_columnconfigure(2, weight=1)
    main_frame.grid_columnconfigure(3, weight=1)
    main_frame.grid_rowconfigure(0, weight=1)
    main_frame.grid_rowconfigure(1, weight=1)

    return main_frame, queue_display


def main():
    global config
    config = load_config(config_file)

    global root
    root = tk.Tk()
    root.title("YouTube Transcript Downloader")
    root.geometry("1280x720")

    sherlock_ascii = """
        ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠀⠀⣠⣴⣾⣿⣿⣷⣶⣤⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⢀⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⢀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠾⠿⠿⠟⠛⠛⠛⠛⠛⣛⣛⣛⣛⣛⡛⠛⠛⠛⠂⠀⠀⠀⠀⠀⠀⠀
        ⠀⠀⠀⠀⠀⠀⠰⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠀⠀⠀⠀⢀⣤⣤⡀⠀⠀
        ⠀⠀⠀⠀⢀⣴⡄⠙⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⢀⣾⠋⡈⢿⡄⠀
        ⠀⠀⢠⣾⣿⣿⣿⣦⡀⠻⢿⣿⣿⣿⣿⣿⣿⠛⠛⠃⠀⠀⠀⣼⡇⠀⠁⢸⡇⠀
        ⠀⣠⣤⣤⣌⣉⠙⠻⢿⣦⣄⠙⠻⠿⣿⡿⠃⠰⣦⠀⠀⠀⠀⣿⡄⠀⠀⣼⠇⠀
        ⠀⣿⣿⣿⣿⣿⣿⣶⣤⣈⠛⢿⣶⣄⠀⠀⠀⠀⢸⠇⠀⠀⠀⠸⣧⣀⣰⠏⠀⠀
        ⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣦⡈⠛⢷⠀⠀⠀⣾⠀⠀⠀⠀⠀⢸⡿⠁⠀⠀⠀
        ⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣄⠀⠀⢸⣿⣿⣷⣦⠀⠀⢸⡇⠀⠀⠀⠀
        ⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣇⠀⠘⠿⣿⠿⠋⠀⠀⣸⡇⠀⠀⠀⠀
        ⠀⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠛⠀⠀⠀⠀⠀⠀⠀⠀⠛⠁⠀⠀⠀⠀
    """
    ascii_label = tk.Label(root, text=sherlock_ascii, font=('Hack', 13), justify="center")
    ascii_label.pack()

    def load_main_ui():
        ascii_label.pack_forget()
        setup_ui(root, config)

    root.after(1000, load_main_ui)
    root.mainloop()
    save_config(config, config_file)

if __name__ == "__main__":
    main()

