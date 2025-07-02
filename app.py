#!/usr/bin/env python3
"""
Dataset Harvester - Enhanced with File Manager
A web interface for aria2 download management with file operations.
"""

from flask import Flask, request, jsonify, send_from_directory, render_template_string
from flask_cors import CORS
import aria2p
import json
import logging
import os
import hashlib
import time
import zipfile
import tarfile
import shutil
import mimetypes
from functools import wraps
from typing import Dict, List, Any, Optional
import subprocess
import signal
import atexit
from datetime import datetime
from pathlib import Path

# Configure logging
log_dir = '/var/log/dataset-harvester'
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{log_dir}/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins="*")

# Configuration
ARIA2_PORT = 6800
ARIA2_SECRET = "harvester2024"
DOWNLOAD_DIR = "/var/downloads"
MAX_CONCURRENT_DOWNLOADS = 10
MAX_DOWNLOAD_SPEED = "0"

# Global variables
aria2_client: Optional[aria2p.API] = None
aria2_process = None

def start_aria2c():
    """Start aria2c daemon with proper configuration."""
    global aria2_process
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Kill any existing aria2c processes first
    try:
        subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
        time.sleep(1)
    except:
        pass
    
    cmd = [
        "aria2c",
        "--enable-rpc",
        "--rpc-listen-all",
        "--rpc-allow-origin-all",
        f"--rpc-listen-port={ARIA2_PORT}",
        f"--rpc-secret={ARIA2_SECRET}",
        f"--dir={DOWNLOAD_DIR}",
        f"--max-concurrent-downloads={MAX_CONCURRENT_DOWNLOADS}",
        "--max-connection-per-server=4",
        "--min-split-size=1M",
        "--split=4",
        "--continue=true",
        "--file-allocation=none",
        "--check-integrity=true",
        "--daemon=true",
        "--log-level=info",
        f"--log={DOWNLOAD_DIR}/aria2.log"
    ]
    
    if MAX_DOWNLOAD_SPEED != "0":
        cmd.append(f"--max-overall-download-limit={MAX_DOWNLOAD_SPEED}")
    
    try:
        logger.info("Starting aria2c daemon...")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        time.sleep(3)
        logger.info("aria2c daemon started successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start aria2c: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("aria2c not found. Please install aria2.")
        return False

def stop_aria2c():
    """Stop aria2c daemon."""
    try:
        subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
        logger.info("aria2c daemon stopped")
    except:
        pass

# Register cleanup function
atexit.register(stop_aria2c)

def initialize_aria2_client() -> bool:
    """Initialize the aria2 client connection with version compatibility."""
    global aria2_client
    max_retries = 5
    for attempt in range(max_retries):
        try:
            aria2_client = aria2p.API(
                aria2p.Client(
                    host="http://localhost",
                    port=ARIA2_PORT,
                    secret=ARIA2_SECRET
                )
            )
            
            try:
                stats = aria2_client.get_global_stat()
            except AttributeError:
                try:
                    stats = aria2_client.get_global_stats()
                except AttributeError:
                    stats = aria2_client.client.get_global_stat()
            
            try:
                version = aria2_client.client.get_version()
            except:
                version = {'version': 'unknown'}
            
            logger.info(f"Connected to aria2c daemon v{version.get('version', 'unknown')}")
            return True
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                logger.error(f"Failed to connect to aria2c daemon after {max_retries} attempts")
                aria2_client = None
                return False

def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(size_bytes)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.1f} {units[unit_index]}"

def format_speed(speed_bytes: int) -> str:
    """Format download speed in human-readable format."""
    if speed_bytes == 0:
        return "0 B/s"
    
    units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
    unit_index = 0
    speed = float(speed_bytes)
    
    while speed >= 1024 and unit_index < len(units) - 1:
        speed /= 1024
        unit_index += 1
    
    return f"{speed:.1f} {units[unit_index]}"

def download_to_dict(download: aria2p.Download) -> Dict[str, Any]:
    """Convert aria2p Download object to dictionary."""
    try:
        if download.total_length and download.total_length > 0:
            progress = (download.completed_length / download.total_length) * 100
        else:
            progress = 0.0
        
        filename = "Unknown"
        if hasattr(download, 'name') and download.name:
            filename = download.name
        elif hasattr(download, 'files') and download.files and len(download.files) > 0:
            filename = download.files[0].path.name
        
        return {
            'gid': download.gid,
            'name': filename,
            'status': download.status,
            'progress': round(progress, 1),
            'download_speed': format_speed(getattr(download, 'download_speed', 0)),
            'total_length': getattr(download, 'total_length', 0),
            'completed_length': getattr(download, 'completed_length', 0),
            'total_size': format_size(getattr(download, 'total_length', 0)),
            'completed_size': format_size(getattr(download, 'completed_length', 0)),
            'eta': "Unknown"
        }
    except Exception as e:
        logger.error(f"Error converting download to dict: {e}")
        return {
            'gid': getattr(download, 'gid', 'unknown'),
            'name': 'Error',
            'status': 'error',
            'progress': 0,
            'download_speed': '0 B/s',
            'total_length': 0,
            'completed_length': 0,
            'total_size': '0 B',
            'completed_size': '0 B',
            'eta': 'Unknown'
        }

def is_valid_url(url: str) -> bool:
    """Validate URL format."""
    valid_schemes = ['http://', 'https://', 'ftp://', 'magnet:']
    return any(url.startswith(scheme) for scheme in valid_schemes)

def get_file_info(file_path: str) -> Dict[str, Any]:
    """Get file information including size, type, and modification time."""
    try:
        stat = os.stat(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return {
            'name': os.path.basename(file_path),
            'path': file_path,
            'size': stat.st_size,
            'size_formatted': format_size(stat.st_size),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'modified_formatted': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'is_directory': os.path.isdir(file_path),
            'mime_type': mime_type or 'unknown',
            'extension': os.path.splitext(file_path)[1].lower()
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
        return {
            'name': os.path.basename(file_path),
            'path': file_path,
            'size': 0,
            'size_formatted': '0 B',
            'modified': '',
            'modified_formatted': 'Unknown',
            'is_directory': False,
            'mime_type': 'unknown',
            'extension': '',
            'error': str(e)
        }

def is_archive(file_path: str) -> bool:
    """Check if file is an archive that can be extracted."""
    archive_extensions = ['.zip', '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.7z', '.rar']
    return any(file_path.lower().endswith(ext) for ext in archive_extensions)

def extract_archive(file_path: str, extract_to: str = None) -> Dict[str, Any]:
    """Extract archive file."""
    try:
        if extract_to is None:
            extract_to = os.path.splitext(file_path)[0]
        
        os.makedirs(extract_to, exist_ok=True)
        
        if file_path.lower().endswith('.zip'):
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
        elif file_path.lower().endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
            with tarfile.open(file_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_to)
        else:
            return {'success': False, 'error': 'Unsupported archive format'}
        
        return {'success': True, 'extract_path': extract_to}
    except Exception as e:
        logger.error(f"Error extracting {file_path}: {e}")
        return {'success': False, 'error': str(e)}

# Rate limiting decorator
request_counts = {}
def rate_limit(max_requests=60, window=60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            now = time.time()
            
            request_counts[client_ip] = [req_time for req_time in request_counts.get(client_ip, []) if now - req_time < window]
            
            if len(request_counts.get(client_ip, [])) >= max_requests:
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            request_counts.setdefault(client_ip, []).append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Existing routes (downloads, status, etc.)
@app.route('/')
def index():
    """Serve the main HTML interface."""
    try:
        with open('/opt/dataset-harvester/index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        return """
        <h1>Dataset Harvester</h1>
        <p>Error: index.html file not found.</p>
        <p>API is available at the following endpoints:</p>
        <ul>
            <li>GET /downloads - List downloads</li>
            <li>POST /downloads - Add download</li>
            <li>GET /status - Check status</li>
            <li>GET /files - Browse files</li>
        </ul>
        """, 404

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'timestamp': int(time.time())})

@app.route('/downloads', methods=['GET'])
@rate_limit(max_requests=120)
def get_downloads():
    """Get list of all current downloads."""
    if not aria2_client:
        return jsonify({'error': 'aria2c daemon not connected'}), 500
    
    try:
        downloads = aria2_client.get_downloads()
        download_list = [download_to_dict(download) for download in downloads]
        
        return jsonify({
            'downloads': download_list,
            'count': len(download_list),
            'timestamp': int(time.time())
        })
    except Exception as e:
        logger.error(f"Error getting downloads: {e}")
        return jsonify({'error': 'Failed to retrieve downloads'}), 500

@app.route('/downloads', methods=['POST'])
@rate_limit(max_requests=30)
def add_download():
    """Add a new download."""
    if not aria2_client:
        return jsonify({'error': 'aria2c daemon not connected'}), 500
    
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        url = data['url'].strip()
        if not url:
            return jsonify({'error': 'URL cannot be empty'}), 400
        
        if not is_valid_url(url):
            return jsonify({'error': 'Invalid URL format. Must start with http://, https://, ftp://, or magnet:'}), 400
        
        options = {}
        if 'dir' in data and data['dir']:
            custom_dir = os.path.join(DOWNLOAD_DIR, data['dir'].strip('/'))
            os.makedirs(custom_dir, exist_ok=True)
            options['dir'] = custom_dir
        
        download = aria2_client.add_uris([url], options=options)
        
        logger.info(f"Added download: {url}")
        return jsonify({
            'message': 'Download added successfully',
            'download': download_to_dict(download)
        }), 201
        
    except Exception as e:
        logger.error(f"Error adding download: {e}")
        return jsonify({'error': f'Failed to add download: {str(e)}'}), 500

# File management routes
@app.route('/files', methods=['GET'])
@rate_limit(max_requests=120)
def list_files():
    """List files in the download directory."""
    try:
        path = request.args.get('path', DOWNLOAD_DIR)
        
        # Security: ensure path is within download directory
        abs_path = os.path.abspath(path)
        abs_download_dir = os.path.abspath(DOWNLOAD_DIR)
        
        if not abs_path.startswith(abs_download_dir):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(abs_path):
            return jsonify({'error': 'Path not found'}), 404
        
        files = []
        for item in os.listdir(abs_path):
            item_path = os.path.join(abs_path, item)
            file_info = get_file_info(item_path)
            file_info['can_extract'] = is_archive(item_path) and not file_info['is_directory']
            files.append(file_info)
        
        # Sort: directories first, then by name
        files.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
        
        return jsonify({
            'files': files,
            'current_path': abs_path,
            'parent_path': os.path.dirname(abs_path) if abs_path != abs_download_dir else None,
            'download_dir': abs_download_dir,
            'count': len(files)
        })
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        return jsonify({'error': 'Failed to list files'}), 500

@app.route('/files/extract', methods=['POST'])
@rate_limit(max_requests=10)
def extract_file():
    """Extract an archive file."""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'error': 'file_path is required'}), 400
        
        file_path = data['file_path']
        
        # Security check
        abs_path = os.path.abspath(file_path)
        abs_download_dir = os.path.abspath(DOWNLOAD_DIR)
        
        if not abs_path.startswith(abs_download_dir):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(abs_path):
            return jsonify({'error': 'File not found'}), 404
        
        if not is_archive(abs_path):
            return jsonify({'error': 'File is not a supported archive'}), 400
        
        extract_to = data.get('extract_to')
        result = extract_archive(abs_path, extract_to)
        
        if result['success']:
            logger.info(f"Extracted {file_path} to {result['extract_path']}")
            return jsonify({
                'message': 'File extracted successfully',
                'extract_path': result['extract_path']
            })
        else:
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        logger.error(f"Error extracting file: {e}")
        return jsonify({'error': f'Failed to extract file: {str(e)}'}), 500

@app.route('/files/delete', methods=['POST'])
@rate_limit(max_requests=30)
def delete_file():
    """Delete a file or directory."""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'error': 'file_path is required'}), 400
        
        file_path = data['file_path']
        
        # Security check
        abs_path = os.path.abspath(file_path)
        abs_download_dir = os.path.abspath(DOWNLOAD_DIR)
        
        if not abs_path.startswith(abs_download_dir):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(abs_path):
            return jsonify({'error': 'File not found'}), 404
        
        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        
        logger.info(f"Deleted {file_path}")
        return jsonify({'message': 'File deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return jsonify({'error': f'Failed to delete file: {str(e)}'}), 500

@app.route('/files/download/<path:filename>')
def download_file(filename):
    """Download a file from the download directory."""
    try:
        # Security check
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        abs_path = os.path.abspath(file_path)
        abs_download_dir = os.path.abspath(DOWNLOAD_DIR)
        
        if not abs_path.startswith(abs_download_dir):
            return jsonify({'error': 'Access denied'}), 403
        
        if not os.path.exists(abs_path) or os.path.isdir(abs_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_from_directory(
            os.path.dirname(abs_path),
            os.path.basename(abs_path),
            as_attachment=True
        )
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return jsonify({'error': 'Failed to download file'}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """Get application status and aria2c connection info."""
    if aria2_client:
        try:
            try:
                stats = aria2_client.get_global_stat()
            except AttributeError:
                try:
                    stats = aria2_client.get_global_stats()
                except AttributeError:
                    stats = aria2_client.client.get_global_stat()
            
            try:
                version = aria2_client.client.get_version()
            except:
                version = {'version': 'unknown'}
            
            # Get download directory info
            try:
                total_files = len([f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))])
                total_size = sum(os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) 
                               for f in os.listdir(DOWNLOAD_DIR) 
                               if os.path.isfile(os.path.join(DOWNLOAD_DIR, f)))
            except:
                total_files = 0
                total_size = 0
            
            return jsonify({
                'status': 'connected',
                'active_downloads': getattr(stats, 'num_active', 0),
                'waiting_downloads': getattr(stats, 'num_waiting', 0),
                'stopped_downloads': getattr(stats, 'num_stopped', 0),
                'aria2_version': version.get('version', 'unknown'),
                'download_speed': format_speed(getattr(stats, 'download_speed', 0)),
                'upload_speed': format_speed(getattr(stats, 'upload_speed', 0)),
                'download_dir': DOWNLOAD_DIR,
                'max_concurrent': MAX_CONCURRENT_DOWNLOADS,
                'total_files': total_files,
                'total_size': format_size(total_size)
            })
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return jsonify({'status': 'disconnected', 'error': str(e)}), 500
    else:
        return jsonify({'status': 'disconnected', 'error': 'Client not initialized'}), 500

# Remaining routes (pause, resume, remove downloads)
@app.route('/downloads/<gid>/pause', methods=['POST'])
@rate_limit(max_requests=60)
def pause_download(gid: str):
    """Pause a specific download."""
    if not aria2_client:
        return jsonify({'error': 'aria2c daemon not connected'}), 500
    
    try:
        downloads = aria2_client.get_downloads()
        download = next((d for d in downloads if d.gid == gid), None)
        
        if not download:
            return jsonify({'error': 'Download not found'}), 404
        
        result = aria2_client.pause([download])
        
        if result:
            logger.info(f"Paused download: {gid}")
            return jsonify({'message': 'Download paused successfully'})
        else:
            return jsonify({'error': 'Failed to pause download'}), 500
            
    except Exception as e:
        logger.error(f"Error pausing download {gid}: {e}")
        return jsonify({'error': 'Failed to pause download'}), 500

@app.route('/downloads/<gid>/resume', methods=['POST'])
@rate_limit(max_requests=60)
def resume_download(gid: str):
    """Resume a specific download."""
    if not aria2_client:
        return jsonify({'error': 'aria2c daemon not connected'}), 500
    
    try:
        downloads = aria2_client.get_downloads()
        download = next((d for d in downloads if d.gid == gid), None)
        
        if not download:
            return jsonify({'error': 'Download not found'}), 404
        
        result = aria2_client.resume([download])
        
        if result:
            logger.info(f"Resumed download: {gid}")
            return jsonify({'message': 'Download resumed successfully'})
        else:
            return jsonify({'error': 'Failed to resume download'}), 500
            
    except Exception as e:
        logger.error(f"Error resuming download {gid}: {e}")
        return jsonify({'error': 'Failed to resume download'}), 500

@app.route('/downloads/<gid>/remove', methods=['POST'])
@rate_limit(max_requests=60)
def remove_download(gid: str):
    """Remove a specific download."""
    if not aria2_client:
        return jsonify({'error': 'aria2c daemon not connected'}), 500
    
    try:
        downloads = aria2_client.get_downloads()
        download = next((d for d in downloads if d.gid == gid), None)
        
        if not download:
            return jsonify({'error': 'Download not found'}), 404
        
        result = aria2_client.remove([download], force=True)
        
        if result:
            logger.info(f"Removed download: {gid}")
            return jsonify({'message': 'Download removed successfully'})
        else:
            return jsonify({'error': 'Failed to remove download'}), 500
            
    except Exception as e:
        logger.error(f"Error removing download {gid}: {e}")
        return jsonify({'error': 'Failed to remove download'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

if __name__ == '__main__':
    print("Dataset Harvester - Enhanced Production Server")
    print("==============================================")
    
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"✓ Download directory: {DOWNLOAD_DIR}")
    
    if start_aria2c():
        print("✓ aria2c daemon started")
        
        if initialize_aria2_client():
            print("✓ Connected to aria2c daemon")
            print("✓ Starting Flask server on all interfaces")
            print(f"✓ Web interface will be available at: http://localhost")
            print("✓ File manager features enabled")
            
            app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
        else:
            print("✗ Failed to connect to aria2c daemon")
            exit(1)
    else:
        print("✗ Failed to start aria2c daemon")
        exit(1)