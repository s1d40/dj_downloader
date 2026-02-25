# DJ Downloader (WAV Scraper Edition)

DJ Downloader is a specialized tool built upon the foundation of the `tidal-dl` project. While the original library provides excellent core functionality, it has certain limitations regarding the verification of audio codecs and strict format adherence required for professional DJ use. 

This project includes a **modified and improved version** of the `tidal-dl` internal library to fix these flaws and provide a reliable, automated pipeline for high-quality audio scraping.

## Why this version?

The original `tidal-dl` occasionally downloads files labeled as FLAC that actually contain AAC (lossy) streams. For DJs, this "fake lossless" content is unacceptable. This tool was built to:
1. **Fix Codec Misreporting:** We modified the core library to verify the actual internal bitstream using `ffprobe`.
2. **Automate DJ Preparation:** Instead of just downloading, it handles the verification and conversion to PCM WAV in one step.
3. **Streamline Scraping:** Built-in loops for batch-downloading search results.

## Features

- **Forced Lossless/Master Quality:** Automatically sets the highest available quality (Master/HiFi) and skips any lossy formats.
- **Fake FLAC Detection (Library Fix):** Uses `ffprobe` to verify the internal codec of downloaded files. If a file is labeled as FLAC but contains AAC data (a "fake FLAC"), it is automatically detected, deleted, and reported.
- **Automated WAV Conversion:** Converts all verified lossless downloads to 16-bit or 24-bit WAV files (PCM) using `ffmpeg`, ensuring maximum compatibility with all DJ hardware and software (Pioneer CDJs, Rekordbox, Serato, etc.).
- **Interactive Scraper Loop:** A streamlined CLI interface that allows for continuous searching by genre, artist, or track names, downloading the top 50 results automatically.
- **URL Support:** Directly paste Tidal Track, Album, or Playlist URLs for targeted downloading.

## Requirements

### System Dependencies
- **Python 3.x**
- **FFmpeg & FFprobe:** Must be installed and available in your system's PATH. This is used for codec verification and WAV conversion.

### Python Dependencies
Install the required Python packages using:
```bash
pip install -r requirements.txt
```

## Setup & Usage

1. **Clone the repository:**
   ```bash
   git clone --recursive https://github.com/s1d40/dj_downloader.git
   cd dj_downloader
   ```

2. **Login to Tidal:**
   Since this tool uses `tidal-dl` as a base, you first need to login via the standard `tidal-dl` interface to generate your access token:
   ```bash
   python Tidal-Media-Downloader/TIDALDL-PY/tidal_dl/__init__.py
   ```
   Follow the prompts to login. Once successful, you can exit `tidal-dl`.

3. **Run the DJ Downloader:**
   ```bash
   python dj_downloader.py
   ```

4. **Scraping:**
   - Enter a search term (e.g., "Deep House 2024") to fetch and download the top 50 tracks.
   - Paste a Tidal URL to download specific content.
   - Enter `q` to quit.

## Credits
This tool is an extension of the excellent [Tidal-Media-Downloader](https://github.com/yaronzz/Tidal-Media-Downloader) by yaronzz. All credit for the core API interaction and decryption logic goes to the original authors.

## Disclaimer
This tool is for educational and personal use only. Please respect the artists and the platform by using it responsibly.
