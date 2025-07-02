#!/bin/bash
# Dataset Harvester - Production Setup Script
# Run this on your remote server to set up everything
# 
# The enhanced version includes all original functionality plus:
# - File browser
# - Archive extraction
# - File management
# - Enhanced UI with tabs

set -e  # Exit on any error

echo "======================================"
echo "Dataset Harvester - Production Setup"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOWNLOAD_DIR="/var/downloads"
SERVICE_USER="harvester"
INSTALL_DIR="/opt/dataset-harvester"
LOG_DIR="/var/log/dataset-harvester"

echo -e "${BLUE}Checking system requirements...${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    echo "Please run: sudo $0"
    exit 1
fi

# Detect OS
if [ -f /etc/debian_version ]; then
    OS="debian"
    echo -e "${GREEN}✓ Detected Debian/Ubuntu system${NC}"
elif [ -f /etc/redhat-release ]; then
    OS="redhat"
    echo -e "${GREEN}✓ Detected RedHat/CentOS/Fedora system${NC}"
else
    echo -e "${YELLOW}⚠ Unknown OS, continuing anyway...${NC}"
    OS="unknown"
fi

# Update package manager
echo -e "${BLUE}Updating package manager...${NC}"
if [ "$OS" = "debian" ]; then
    apt-get update -y
elif [ "$OS" = "redhat" ]; then
    yum update -y
fi

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
if [ "$OS" = "debian" ]; then
    apt-get install -y python3 python3-pip aria2 curl wget unzip nginx ufw
elif [ "$OS" = "redhat" ]; then
    yum install -y python3 python3-pip aria2 curl wget unzip nginx firewalld
fi

# Install Python packages
echo -e "${BLUE}Installing Python packages...${NC}"
# Install core dependencies
pip3 install --break-system-packages --ignore-installed flask aria2p flask-cors gunicorn

# Install additional Python dependencies for archive support
echo -e "${BLUE}Installing archive support packages...${NC}"
pip3 install --break-system-packages --ignore-installed patool py7zr rarfile || echo "Warning: Some packages had installation issues but continuing..."

# Create service user
echo -e "${BLUE}Creating service user...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $INSTALL_DIR $SERVICE_USER
    echo -e "${GREEN}✓ Created user: $SERVICE_USER${NC}"
else
    echo -e "${YELLOW}⚠ User $SERVICE_USER already exists${NC}"
fi

# Create directories
echo -e "${BLUE}Creating directories...${NC}"
mkdir -p $INSTALL_DIR
mkdir -p $DOWNLOAD_DIR
mkdir -p $LOG_DIR

# Set permissions
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
chown -R $SERVICE_USER:$SERVICE_USER $DOWNLOAD_DIR
chown -R $SERVICE_USER:$SERVICE_USER $LOG_DIR
chmod 755 $DOWNLOAD_DIR

echo -e "${GREEN}✓ Created directories${NC}"

# Copy application files
echo -e "${BLUE}Setting up application files...${NC}"
if [ -f "app.py" ] && [ -f "index.html" ]; then
    cp app.py $INSTALL_DIR/
    cp index.html $INSTALL_DIR/
    chown $SERVICE_USER:$SERVICE_USER $INSTALL_DIR/app.py $INSTALL_DIR/index.html
    chmod 644 $INSTALL_DIR/app.py $INSTALL_DIR/index.html
    echo -e "${GREEN}✓ Copied application files${NC}"
else
    echo -e "${RED}Error: app.py and index.html files not found in current directory${NC}"
    echo "Please run this script from the directory containing your application files"
    exit 1
fi

# Create systemd service for Dataset Harvester
echo -e "${BLUE}Creating systemd service...${NC}"
cat > /etc/systemd/system/dataset-harvester.service << EOF
[Unit]
Description=Dataset Harvester Web Interface
After=network.target

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/app.log
StandardError=append:$LOG_DIR/app-error.log

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$DOWNLOAD_DIR $LOG_DIR
ProtectHome=yes

[Install]
WantedBy=multi-user.target
EOF

# Configure nginx
echo -e "${BLUE}Configuring nginx reverse proxy...${NC}"

# Add rate limiting to nginx.conf if not already present
if ! grep -q "limit_req_zone" /etc/nginx/nginx.conf; then
    echo -e "${BLUE}Adding rate limiting to nginx.conf...${NC}"
    sed -i '/http {/a \    # Rate limiting\n    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;\n    limit_req_zone $binary_remote_addr zone=downloads:10m rate=10r/m;' /etc/nginx/nginx.conf
fi

# Create site configuration
cat > /etc/nginx/sites-available/dataset-harvester << 'EOF'
server {
    listen 80;
    server_name _;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy strict-origin-when-cross-origin;
    
    # Main application
    location / {
        limit_req zone=api burst=60 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # API endpoints with stricter rate limiting
    location /downloads {
        limit_req zone=downloads burst=20 nodelay;
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Health check
    location /health {
        proxy_pass http://127.0.0.1:5000;
        access_log off;
    }
    
    # Deny access to sensitive files
    location ~ /\. {
        deny all;
    }
    
    location ~* \.(log|conf)$ {
        deny all;
    }
}
EOF

# Enable nginx site
if [ "$OS" = "debian" ]; then
    ln -sf /etc/nginx/sites-available/dataset-harvester /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
elif [ "$OS" = "redhat" ]; then
    mkdir -p /etc/nginx/conf.d
    ln -sf /etc/nginx/sites-available/dataset-harvester /etc/nginx/conf.d/dataset-harvester.conf
fi

# Test nginx configuration
nginx -t
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
else
    echo -e "${RED}✗ Nginx configuration error${NC}"
    exit 1
fi

# Configure firewall
echo -e "${BLUE}Configuring firewall...${NC}"
if [ "$OS" = "debian" ]; then
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow http
    ufw allow https
    ufw --force enable
    echo -e "${GREEN}✓ UFW firewall configured${NC}"
elif [ "$OS" = "redhat" ]; then
    systemctl enable firewalld
    systemctl start firewalld
    firewall-cmd --permanent --add-service=ssh
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --reload
    echo -e "${GREEN}✓ Firewalld configured${NC}"
fi

# Set up log rotation
echo -e "${BLUE}Setting up log rotation...${NC}"
cat > /etc/logrotate.d/dataset-harvester << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload dataset-harvester || true
    endscript
}
EOF

# Enable and start services
echo -e "${BLUE}Starting services...${NC}"
systemctl daemon-reload
systemctl enable dataset-harvester
systemctl enable nginx

# Start services
systemctl restart nginx
systemctl start dataset-harvester

# Wait a moment for services to start
sleep 3

# Check service status
echo -e "${BLUE}Checking service status...${NC}"
if systemctl is-active --quiet dataset-harvester; then
    echo -e "${GREEN}✓ Dataset Harvester service is running${NC}"
else
    echo -e "${RED}✗ Dataset Harvester service failed to start${NC}"
    echo "Check logs: journalctl -u dataset-harvester -f"
    exit 1
fi

if systemctl is-active --quiet nginx; then
    echo -e "${GREEN}✓ Nginx service is running${NC}"
else
    echo -e "${RED}✗ Nginx service failed to start${NC}"
    echo "Check logs: journalctl -u nginx -f"
    exit 1
fi

# Test the application
echo -e "${BLUE}Testing application...${NC}"
sleep 2
if curl -f -s http://localhost/health > /dev/null; then
    echo -e "${GREEN}✓ Application is responding${NC}"
else
    echo -e "${YELLOW}⚠ Application may not be ready yet, check logs${NC}"
fi

# Get server IP
SERVER_IP=$(curl -s http://checkip.amazonaws.com/ || curl -s http://ipinfo.io/ip || echo "UNKNOWN")

echo ""
echo -e "${GREEN}======================================"
echo "🎉 Installation Complete!"
echo "======================================${NC}"
echo ""
echo -e "${BLUE}Access your Dataset Harvester at:${NC}"
echo "  http://$SERVER_IP"
echo ""
echo -e "${BLUE}Service Management:${NC}"
echo "  Status:  systemctl status dataset-harvester"
echo "  Start:   systemctl start dataset-harvester"
echo "  Stop:    systemctl stop dataset-harvester"
echo "  Restart: systemctl restart dataset-harvester"
echo "  Logs:    journalctl -u dataset-harvester -f"
echo ""
echo -e "${BLUE}File Locations:${NC}"
echo "  Application: $INSTALL_DIR"
echo "  Downloads:   $DOWNLOAD_DIR"
echo "  Logs:        $LOG_DIR"
echo ""
echo -e "${BLUE}Security Notes:${NC}"
echo "  • Firewall is configured (SSH, HTTP, HTTPS only)"
echo "  • Nginx reverse proxy with rate limiting enabled"
echo "  • Application runs as dedicated user: $SERVICE_USER"
echo "  • Change the aria2 secret in app.py for production!"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Test the web interface"
echo "  2. Add SSL certificate for HTTPS (recommended)"
echo "  3. Configure DNS to point to $SERVER_IP"
echo "  4. Monitor logs and performance"
echo ""
echo -e "${GREEN}Happy downloading! 🚀${NC}"