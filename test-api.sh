#!/bin/bash

BACKEND_URL="http://localhost:8000"

# Test 1: Health check
echo "=== Health Check ==="
curl -s $BACKEND_URL/health | jq .

# Test 2: Add torrent (using Ubuntu ISO as example)
echo -e "\n=== Add Torrent ==="
TORRENT_RESPONSE=$(curl -s -X POST $BACKEND_URL/torrent/add \
  -H "Content-Type: application/json" \
  -d '{"magnet":"magnet:?xt=urn:btih:a3483dd9545dc02ca9c30e38a364be641580f156"}')
echo $TORRENT_RESPONSE | jq .
HASH=$(echo $TORRENT_RESPONSE | jq -r '.hash')
echo "Torrent hash: $HASH"

# Test 3: Get torrent status (wait a moment first)
echo -e "\n=== Wait 3 seconds for torrent to be ready ==="
sleep 3

echo -e "\n=== Get Torrent Status ==="
curl -s $BACKEND_URL/torrent/$HASH/status | jq .

# Test 4: List all torrents
echo -e "\n=== List All Torrents ==="
curl -s $BACKEND_URL/torrents | jq .

# Test 5: Get torrent files
echo -e "\n=== Get Torrent Files ==="
curl -s $BACKEND_URL/torrent/$HASH/files | jq .

# Test 6: Pause torrent
echo -e "\n=== Pause Torrent ==="
curl -s -X POST $BACKEND_URL/torrent/$HASH/pause | jq .

# Test 7: Resume torrent
echo -e "\n=== Resume Torrent ==="
curl -s -X POST $BACKEND_URL/torrent/$HASH/resume | jq .

# Test 8: Remove torrent (without deleting files)
echo -e "\n=== Remove Torrent ==="
curl -s -X DELETE "$BACKEND_URL/torrent/$HASH?delete_files=false" | jq .