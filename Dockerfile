FROM python:3.11-slim

# Install qBittorrent and FFmpeg
RUN apt-get update && apt-get install -y \
qbittorrent-nox \
ffmpeg \
&& rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy application
COPY main_r2.py main.py

# Create download directory
RUN mkdir -p /downloads && chmod 777 /downloads

# Create startup script
RUN echo '#!/bin/bash\nqbittorrent-nox --webui-port=8080 --confirm-legal-notice &\nsleep 5\npython /app/main.py' > /startup.sh && chmod +x /startup.sh

# Expose ports
EXPOSE 8000 6881-6889/udp

# Environment variables (can be overridden by .env)
ENV QB_HOST=localhost \
QB_PORT=8080 \
QB_USERNAME=admin \
QB_PASSWORD=adminadmin \
DOWNLOAD_DIR=/downloads

# Start
CMD ["/startup.sh"]