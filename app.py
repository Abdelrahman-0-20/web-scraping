import os
import time
import subprocess
import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
import streamlit as st
from urllib.parse import urljoin, urlparse

# --- Page Config ---
st.set_page_config(page_title="Web Scraper & Downloader", layout="wide")
st.title("Web Scraper & Media Downloader")
st.markdown("Scrape links, download MP3/MP4, detect playlists, and download torrents.")

# --- Constants ---
DIRECT_EXTENSIONS = (
    '.mp3', '.mp4', '.mkv', '.avi', '.mov', '.wav', '.flac',
    '.pdf', '.zip', '.rar', '.exe', '.apk', '.jpg', '.jpeg',
    '.png', '.gif', '.docx', '.xlsx', '.csv'
)
BITRATE_OPTIONS = ["128", "192", "320"]
FORMAT_OPTIONS = ["mp3", "mp4", "mkv", "avi", "wav", "flac", "best (auto)"]
MEDIA_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.flac', '.webm', '.m4a', '.ogg')

# --- Sidebar ---
st.sidebar.header("Settings")
save_dir = st.sidebar.text_input("Save Directory", value="downloads")
os.makedirs(save_dir, exist_ok=True)
st.sidebar.markdown("---")
st.sidebar.info("Torrent downloading works locally only (aria2 required).")

# --- Helper Functions ---

def scrape_links(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, timeout=15, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        raw_links = [a.get('href') for a in soup.find_all('a') if a.get('href')]
        full_links = [urljoin(url, l) for l in raw_links]
        seen = set()
        unique = []
        for l in full_links:
            if l not in seen and l.startswith('http'):
                seen.add(l)
                unique.append(l)
        return unique
    except Exception as e:
        st.error(f"Error scraping: {e}")
        return []

def is_direct_link(url):
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DIRECT_EXTENSIONS)

def download_direct(url, save_dir):
    """Download a direct file link."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, stream=True, timeout=30, headers=headers)
        filename = os.path.basename(urlparse(url).path) or "downloaded_file"
        filepath = os.path.join(save_dir, filename)
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath, None
    except Exception as e:
        return None, str(e)

def get_playlist_info(url):
    """Detect if URL is a playlist and return its info."""
    try:
        ydl_opts = {'extract_flat': True, 'quiet': True, 'skip_download': True, 'no_warnings': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info and info.get('_type') == 'playlist':
            entries = info.get('entries', [])
            return {
                'is_playlist': True,
                'title': info.get('title', 'Unknown Playlist'),
                'uploader': info.get('uploader', 'Unknown'),
                'count': len(entries),
                'entries': [
                    {
                        'title': e.get('title', f'Video {i+1}'),
                        'url': e.get('url') or e.get('webpage_url', ''),
                        'duration': e.get('duration'),
                        'id': e.get('id', '')
                    }
                    for i, e in enumerate(entries) if e
                ]
            }
        elif info:
            return {'is_playlist': False, 'title': info.get('title', 'Unknown'),
                    'uploader': info.get('uploader', 'Unknown'), 'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail')}
        return None
    except Exception as e:
        return {'error': str(e)}

def download_media(url, format_type, save_dir, bitrate="192"):
    """Download video/audio using yt-dlp."""
    try:
        ydl_opts = {
            'outtmpl': os.path.join(save_dir, '%(uploader)s/%(title)s.%(ext)s'),
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,
            'writethumbnail': False,
        }
        if format_type in ['mp3', 'wav', 'flac']:
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': format_type,
                    'preferredquality': bitrate
                }]
            })
        elif format_type in ['mp4', 'mkv', 'avi']:
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': format_type
            })
        else:
            ydl_opts['format'] = 'best'

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True, None
    except Exception as e:
        return False, str(e)

def find_aria2c():
    """Locate aria2c executable."""
    local = os.path.join(os.getcwd(), "aria2c.exe")
    if os.path.exists(local):
        return local
    for item in os.listdir(os.getcwd()):
        full_path = os.path.join(os.getcwd(), item)
        if os.path.isdir(full_path):
            candidate = os.path.join(full_path, "aria2c.exe")
            if os.path.exists(candidate):
                return candidate
    return None

def is_ffmpeg_available():
    """Check if ffmpeg is in PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except:
        return False

def convert_file(input_path, convert_to, save_dir, bitrate="192"):
    output_filename = os.path.splitext(os.path.basename(input_path))[0] + f".{convert_to}"
    output_path = os.path.join(save_dir, output_filename)
    if convert_to in ['mp3', 'wav', 'flac']:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-b:a", f"{bitrate}k", output_path]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c:v", "copy", "-c:a", "copy", output_path]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return (True, output_path) if result.returncode == 0 else (False, result.stdout[-500:])
    except FileNotFoundError:
        return False, "ffmpeg not found."

def get_latest_file(folder):
    files = []
    for root, dirs, f_list in os.walk(folder):
        for f in f_list:
            if f.lower().endswith(MEDIA_EXTENSIONS):
                files.append(os.path.join(root, f))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def download_torrent_and_convert(torrent_source, save_dir, target_fmt, bitrate="192"):
    aria2_path = find_aria2c()
    if not aria2_path:
        return False, "aria2c.exe not found. Please install aria2 and place it in the app folder."

    # Download torrent with aria2
    cmd = [aria2_path, "--seed-time=0", f"--dir={save_dir}", torrent_source]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Display output in a streamlit container (append lines)
    output_container = st.empty()
    log_lines = []
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            log_lines.append(line.strip())
            # Show last 10 lines to avoid huge output
            output_container.code("\n".join(log_lines[-10:]), language="bash")
    process.wait()

    if process.returncode != 0:
        return False, f"Aria2 failed with return code {process.returncode}."

    if target_fmt == "Original":
        return True, "Download finished. File saved."

    # Convert if needed
    if not is_ffmpeg_available():
        return False, "ffmpeg not found. Cannot convert."

    st.info(f"Download finished. Converting to {target_fmt}...")
    latest_file = get_latest_file(save_dir)
    if latest_file:
        ok, res = convert_file(latest_file, target_fmt, save_dir, bitrate)
        if ok:
            return True, f"Downloaded and converted to: {res}"
        else:
            return False, f"Download OK but conversion failed: {res}"
    return True, "Download finished but no media file found to convert."

# --- UI Tabs ---
tab1, tab2, tab3 = st.tabs(["Scrape Links", "Video / Audio", "Torrent"])

#  SCRAPE TAB 
with tab1:
    st.subheader("Scrape Links")
    site = st.text_input("Enter URL to scrape", key="scrape_url")
    if st.button("Scrape"):
        links = scrape_links(site)
        if links:
            st.session_state['scraped_links'] = links
            st.success(f"Found {len(links)} links")
        else:
            st.warning("No links found or error.")

    if 'scraped_links' in st.session_state and st.session_state['scraped_links']:
        selected = st.multiselect("Select links to download", st.session_state['scraped_links'])
        # Only show format selection if we plan to use yt-dlp
        format_choice = st.selectbox("Format (for non-direct links)", FORMAT_OPTIONS)
        if st.button("Download Selected"):
            if not selected:
                st.warning("No links selected.")
            else:
                for link in selected:
                    with st.spinner(f"Processing {link}"):
                        if is_direct_link(link):
                            # Direct file download
                            path, err = download_direct(link, save_dir)
                            if path:
                                st.success(f" Downloaded: {os.path.basename(path)}")
                            else:
                                st.error(f" Failed: {err}")
                        else:
                            # Use yt-dlp
                            ok, err = download_media(link, format_choice, save_dir)
                            if ok:
                                st.success(f" Downloaded: {link}")
                            else:
                                st.error(f" {err}")

#  VIDEO / AUDIO TAB 
with tab2:
    st.subheader("Video / Audio Downloader")
    v_url = st.text_input("Paste URL (video, audio, playlist)", key="video_url")

    # Analyze URL for playlist detection
    if st.button("Analyze URL"):
        if v_url:
            with st.spinner("Checking..."):
                info = get_playlist_info(v_url)
            if info is None:
                st.warning("Could not fetch info.")
            elif 'error' in info:
                st.error(f"Error: {info['error']}")
            elif info['is_playlist']:
                st.success(f"Playlist found: **{info['title']}** ({info['count']} videos)")
                st.session_state['playlist_info'] = info
            else:
                st.success(f"Single video: **{info['title']}** by {info['uploader']}")
                st.session_state['playlist_info'] = None  # not a playlist
        else:
            st.warning("Please enter a URL.")

    # Download section
    if 'playlist_info' in st.session_state and st.session_state.get('playlist_info'):
        playlist = st.session_state['playlist_info']
        st.markdown(f"### Playlist: {playlist['title']}")

        # Option to download whole playlist or select videos
        download_mode = st.radio("Download mode:", ["Whole playlist", "Select videos"])
        if download_mode == "Select videos":
            entry_titles = [f"{e['title']} (ID: {e['id']})" for e in playlist['entries']]
            selected_titles = st.multiselect("Choose videos", entry_titles)
            selected_urls = [playlist['entries'][i]['url'] for i, t in enumerate(entry_titles) if t in selected_titles]
        else:
            selected_urls = [e['url'] for e in playlist['entries']]

        fmt = st.selectbox("Format", FORMAT_OPTIONS, key="pl_fmt")
        if st.button("Download Now"):
            if not selected_urls:
                st.warning("No videos selected.")
            else:
                for url in selected_urls:
                    with st.spinner(f"Downloading {url}"):
                        ok, err = download_media(url, fmt, save_dir)
                    if ok:
                        st.success(f" {url}")
                    else:
                        st.error(f" {err}")
    else:
        # Single video download (if URL was analyzed or just enter and go)
        col1, col2 = st.columns([3, 1])
        with col1:
            single_fmt = st.selectbox("Format", FORMAT_OPTIONS, key="single_fmt")
        with col2:
            st.write("")  # spacer
            st.write("")
            if st.button("Download Single Video"):
                if v_url:
                    with st.spinner("Downloading..."):
                        ok, err = download_media(v_url, single_fmt, save_dir)
                    if ok:
                        st.success(" Download complete!")
                    else:
                        st.error(f" {err}")
                else:
                    st.warning("Please enter a URL.")

#  TORRENT TAB 
with tab3:
    st.subheader("Torrent Downloader")

    # 1. Choose format
    target_format = st.selectbox("I want the file as:", ["Original", "mp3", "mp4", "mkv", "avi", "wav", "flac"])
    bit_rate = st.select_slider("Bitrate (for audio only)", ["128", "192", "320"], "192")

    # 2. Torrent source
    t_type = st.radio("Input method:", ["Magnet Link", ".torrent File"])
    if t_type == "Magnet Link":
        mag = st.text_input("Paste Magnet")
        if st.button("Start Magnet Download"):
            if mag:
                ok, res = download_torrent_and_convert(mag, save_dir, target_format, bit_rate)
                if ok:
                    st.success(res)
                else:
                    st.error(res)
            else:
                st.warning("Paste a magnet link.")
    else:
        up = st.file_uploader("Upload .torrent file", type=["torrent"])
        if up:
            t_path = os.path.join(save_dir, up.name)
            with open(t_path, "wb") as f:
                f.write(up.read())
            if st.button("Start Torrent Download"):
                ok, res = download_torrent_and_convert(t_path, save_dir, target_format, bit_rate)
                if ok:
                    st.success(res)
                else:
                    st.error(res)

st.caption(f"Files saved to: {os.path.abspath(save_dir)}")