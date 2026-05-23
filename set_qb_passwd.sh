#!/bin/bash

# qBittorrent Password Setup Script
# This script helps set up qBittorrent with a persistent password for your API

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
QB_DOCKER_NAME="qbittorrent"
QB_CONFIG_DIR="$HOME/.config/qBittorrent"
QB_USERNAME="admin"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   qBittorrent Password Setup Script   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"

# ============================================================================
# Function to generate password hash
# ============================================================================

generate_password_hash() {
    local password=$1
    
    python3 << PYTHON_SCRIPT
import hashlib
import base64
import os
import sys

password = "$password"
salt = os.urandom(8)
derived = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)

salt_b64 = base64.b64encode(salt).decode()
derived_b64 = base64.b64encode(derived).decode()

hash_value = f"@ByteArray({salt_b64}:{derived_b64})"
print(hash_value)
PYTHON_SCRIPT
}

# ============================================================================
# Function to detect qBittorrent installation
# ============================================================================

detect_qbittorrent() {
    echo -e "${BLUE}Detecting qBittorrent installation...${NC}"
    
    # Check if running in Docker
    if docker ps 2>/dev/null | grep -q "$QB_DOCKER_NAME"; then
        echo -e "${GREEN}✓ Found Docker container: $QB_DOCKER_NAME${NC}"
        QB_MODE="docker"
        return 0
    fi
    
    # Check if running locally
    if command -v qbittorrent-nox &> /dev/null || command -v qbittorrent &> /dev/null; then
        echo -e "${GREEN}✓ Found local qBittorrent installation${NC}"
        QB_MODE="local"
        return 0
    fi
    
    # Not found
    echo -e "${RED}✗ qBittorrent not found!${NC}"
    echo "Install with:"
    echo "  Docker: docker run -d -p 8080:8080 linuxserver/qbittorrent:latest"
    echo "  Ubuntu: sudo apt-get install qbittorrent-nox"
    echo "  macOS: brew install qbittorrent"
    return 1
}

# ============================================================================
# Function to check current password
# ============================================================================

check_current_password() {
    echo -e "\n${BLUE}Checking current password status...${NC}"
    
    if [ "$QB_MODE" = "docker" ]; then
        # Check if Docker container is running
        if ! docker ps | grep -q "$QB_DOCKER_NAME"; then
            echo -e "${YELLOW}! qBittorrent Docker container is not running${NC}"
            echo "  Start with: docker start $QB_DOCKER_NAME"
            return 1
        fi
        
        # Get logs
        echo "Checking Docker logs for temporary password..."
        docker logs "$QB_DOCKER_NAME" | grep -i "temporary password" || {
            echo -e "${GREEN}✓ No temporary password found (password already set)${NC}"
        }
    else
        # Local installation - check config file
        if [ -f "$QB_CONFIG_DIR/qBittorrent.conf" ]; then
            echo "Checking config file..."
            if grep -q "WebUI\\\\Password_PBKDF2" "$QB_CONFIG_DIR/qBittorrent.conf"; then
                echo -e "${GREEN}✓ Password is already configured${NC}"
            else
                echo -e "${YELLOW}! Password not yet configured${NC}"
            fi
        fi
    fi
}

# ============================================================================
# Function to set password interactively
# ============================================================================

set_password_interactive() {
    echo -e "\n${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║        Set qBittorrent Password        ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"
    
    # Get password from user
    read -sp "Enter new password for admin: " QB_PASSWORD
    echo ""
    
    read -sp "Confirm password: " QB_PASSWORD_CONFIRM
    echo ""
    
    # Check if passwords match
    if [ "$QB_PASSWORD" != "$QB_PASSWORD_CONFIRM" ]; then
        echo -e "${RED}✗ Passwords do not match!${NC}"
        return 1
    fi
    
    # Check password length
    if [ ${#QB_PASSWORD} -lt 6 ]; then
        echo -e "${RED}✗ Password must be at least 6 characters!${NC}"
        return 1
    fi
    
    echo -e "\n${BLUE}Generating password hash...${NC}"
    PASSWORD_HASH=$(generate_password_hash "$QB_PASSWORD")
    
    if [ -z "$PASSWORD_HASH" ]; then
        echo -e "${RED}✗ Failed to generate password hash!${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✓ Password hash generated${NC}"
    
    # Set in config file
    set_password_in_config "$PASSWORD_HASH"
}

# ============================================================================
# Function to set password in config file
# ============================================================================

set_password_in_config() {
    local password_hash=$1
    
    if [ "$QB_MODE" = "docker" ]; then
        echo -e "\n${BLUE}Updating Docker configuration...${NC}"
        
        # Get Docker config path
        DOCKER_CONFIG_PATH="/config/qBittorrent/qBittorrent.conf"
        
        # Check if we can access the config
        docker exec "$QB_DOCKER_NAME" test -f "$DOCKER_CONFIG_PATH" 2>/dev/null || {
            echo -e "${YELLOW}! Config file not found in Docker. Creating...${NC}"
            docker exec "$QB_DOCKER_NAME" mkdir -p /config/qBittorrent
        }
        
        # Remove old password if exists
        docker exec "$QB_DOCKER_NAME" sed -i '/WebUI\\Password_PBKDF2/d' "$DOCKER_CONFIG_PATH" 2>/dev/null || true
        
        # Add new password
        docker exec "$QB_DOCKER_NAME" bash -c "echo 'WebUI\\Password_PBKDF2=\"$password_hash\"' >> $DOCKER_CONFIG_PATH"
        
        echo -e "${GREEN}✓ Docker config updated${NC}"
        
        # Restart container
        echo -e "\n${BLUE}Restarting Docker container...${NC}"
        docker restart "$QB_DOCKER_NAME"
        sleep 3
        
        if docker ps | grep -q "$QB_DOCKER_NAME"; then
            echo -e "${GREEN}✓ Container restarted successfully${NC}"
        else
            echo -e "${RED}✗ Container failed to restart!${NC}"
            return 1
        fi
    else
        echo -e "\n${BLUE}Updating local configuration...${NC}"
        
        # Create config directory if needed
        mkdir -p "$QB_CONFIG_DIR"
        
        # Check if qBittorrent is running
        if pgrep -x "qbittorrent" > /dev/null || pgrep -x "qbittorrent-nox" > /dev/null; then
            echo -e "${YELLOW}! qBittorrent is running. Stopping...${NC}"
            pkill -f qbittorrent || true
            sleep 2
        fi
        
        # Backup original config
        if [ -f "$QB_CONFIG_DIR/qBittorrent.conf" ]; then
            BACKUP_FILE="$QB_CONFIG_DIR/qBittorrent.conf.backup"
            cp "$QB_CONFIG_DIR/qBittorrent.conf" "$BACKUP_FILE"
            echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
            
            # Remove old password if exists
            sed -i '/WebUI\\Password_PBKDF2/d' "$QB_CONFIG_DIR/qBittorrent.conf"
        fi
        
        # Add new password
        echo "WebUI\\Password_PBKDF2=\"$password_hash\"" >> "$QB_CONFIG_DIR/qBittorrent.conf"
        
        echo -e "${GREEN}✓ Config file updated: $QB_CONFIG_DIR/qBittorrent.conf${NC}"
        
        echo -e "\n${YELLOW}! Please restart qBittorrent manually:${NC}"
        echo "  qbittorrent-nox"
        echo "  or"
        echo "  qbittorrent"
    fi
}

# ============================================================================
# Function to save credentials to environment file
# ============================================================================

save_env_file() {
    local password=$1
    local env_file=".env"
    
    echo -e "\n${BLUE}Save credentials for API?${NC}"
    read -p "Save to .env file? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cat > "$env_file" << EOF
# qBittorrent Configuration
QB_HOST=localhost
QB_PORT=8080
QB_USERNAME=admin
QB_PASSWORD=$password
EOF
        
        echo -e "${GREEN}✓ Saved to $env_file${NC}"
        echo -e "${YELLOW}! WARNING: Do not commit .env to git!${NC}"
    fi
}

# ============================================================================
# Function to test connectivity
# ============================================================================

test_connectivity() {
    echo -e "\n${BLUE}Testing qBittorrent connectivity...${NC}"
    
    local username=$1
    local password=$2
    
    RESPONSE=$(curl -s -u "$username:$password" "http://localhost:8080/api/v2/app/webapiVersion")
    
    if [ -n "$RESPONSE" ]; then
        echo -e "${GREEN}✓ Successfully connected to qBittorrent${NC}"
        echo -e "  Version: $RESPONSE"
        return 0
    else
        echo -e "${RED}✗ Failed to connect to qBittorrent${NC}"
        echo "  Make sure qBittorrent is running on port 8080"
        return 1
    fi
}

# ============================================================================
# Main Script
# ============================================================================

main() {
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}✗ Python 3 is required to generate password hashes!${NC}"
        echo "Install with: sudo apt-get install python3"
        exit 1
    fi
    
    # Detect qBittorrent
    if ! detect_qbittorrent; then
        exit 1
    fi
    
    echo ""
    
    # Check current status
    check_current_password
    
    echo ""
    
    # Ask if user wants to set password
    read -p "Do you want to set a new password? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if set_password_interactive; then
            # Test connectivity (wait for service to be ready)
            echo -e "\n${BLUE}Waiting for qBittorrent to be ready...${NC}"
            sleep 5
            
            if test_connectivity "$QB_USERNAME" "$QB_PASSWORD"; then
                echo -e "\n${GREEN}╔════════════════════════════════════════╗${NC}"
                echo -e "${GREEN}║    Password Setup Complete!            ║${NC}"
                echo -e "${GREEN}╚════════════════════════════════════════╝${NC}\n"
                
                echo "Your qBittorrent credentials:"
                echo "  Username: $QB_USERNAME"
                echo "  Password: $QB_PASSWORD"
                echo ""
                
                # Save to env file
                save_env_file "$QB_PASSWORD"
                
                # Show API usage
                echo -e "\n${BLUE}Using with your API:${NC}"
                echo "  QB_USERNAME=admin QB_PASSWORD=$QB_PASSWORD python main.py"
                echo ""
                echo "Or in your code:"
                echo "  auth = aiohttp.BasicAuth('$QB_USERNAME', '$QB_PASSWORD')"
            fi
        fi
    fi
}

# Run main function
main