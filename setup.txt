# Dataset Harvester - Setup Instructions

## 🎯 Overview

Dataset Harvester is a web-based download manager with file management capabilities. It uses aria2c for downloading and provides a modern web interface for managing downloads and files.

## 🚀 Installation (Simple 3-Step Process)

### Step 1: Create Directory and Download Files

```bash
# Create project directory
mkdir dataset-harvester
cd dataset-harvester

# Download or copy these files into the directory:
# - app.py (Flask backend)
# - index.html (Web interface) 
# - setup.sh (Automated installation script)
```

### Step 2: Run the Setup Script

The setup script handles everything automatically:

```bash
# Make the setup script executable
chmod +x setup.sh

# Run the installation (requires root/sudo)
sudo ./setup.sh
```

### Step 3: Done!

That's it! The setup script automatically:
- ✅ Installs all dependencies (Python, aria2, nginx, etc.)
- ✅ Creates system user and proper permissions
- ✅ Sets up systemd service for auto-start
- ✅ Configures nginx reverse proxy with security
- ✅ Sets up firewall rules
- ✅ Creates desktop icons and start menu entries
- ✅ Configures log rotation
- ✅ Starts all services

## 🖥️ Accessing Dataset Harvester

After installation completes:

### Web Browser Access
```
http://YOUR_SERVER_IP
```
(The setup script displays your server's IP address)

### Desktop Icon
Click the **Dataset Harvester** icon that was created on your desktop

### Start Menu
Find **Dataset Harvester** in your applications menu under Network/Internet

## 🎛️ Service Management

### Check Status
```bash
sudo systemctl status dataset-harvester
```

### Control Service
```bash
# Start/Stop/Restart
sudo systemctl start dataset-harvester
sudo systemctl stop dataset-harvester
sudo systemctl restart dataset-harvester

# View logs
sudo journalctl -u dataset-harvester -f
```

## 🎯 Using the Application

### Download Manager Tab
- Add URLs for download (HTTP, HTTPS, FTP, BitTorrent)
- Monitor progress with real-time updates
- Pause, resume, and remove downloads
- Organize into subdirectories

### File Manager Tab
- Browse downloaded files
- Extract archives (ZIP, TAR, 7Z, RAR)
- Download files to your computer
- Delete files and directories

## 📁 Important Directories

| Directory | Purpose |
|-----------|---------|
| `/opt/dataset-harvester/` | Application files |
| `/var/downloads/` | Downloaded files |
| `/var/log/dataset-harvester/` | Application logs |

## 🛠️ Troubleshooting

### Service Issues
```bash
# Check service status
sudo systemctl status dataset-harvester

# View detailed logs
sudo journalctl -u dataset-harvester -n 50

# Restart everything
sudo systemctl restart dataset-harvester nginx
```

### Can't Access Web Interface
```bash
# Check if services are running
sudo systemctl status nginx dataset-harvester

# Test local connection
curl http://localhost/health
```

### Downloads Not Working
```bash
# Check aria2c logs
sudo tail -f /var/downloads/aria2.log

# Restart service
sudo systemctl restart dataset-harvester
```

## 🔐 Security Notes

The setup script automatically configures:
- ✅ Dedicated system user (non-root)
- ✅ Firewall (SSH, HTTP, HTTPS only)
- ✅ Nginx reverse proxy with rate limiting
- ✅ Application sandboxing
- ✅ Secure file permissions

**Recommended:** Change the aria2 secret in `/opt/dataset-harvester/app.py` for production use.

## 📊 Monitoring

### View Logs
```bash
# Application logs
sudo journalctl -u dataset-harvester -f

# Download logs  
sudo tail -f /var/downloads/aria2.log

# Web server logs
sudo tail -f /var/log/nginx/access.log
```

### Check Resources
```bash
# Disk usage
sudo du -sh /var/downloads/

# Service status
sudo systemctl status dataset-harvester
```

## 🎉 That's It!

Your Dataset Harvester is ready to use. The setup script handled everything automatically - just open your browser or click the desktop icon to start downloading and managing files!
