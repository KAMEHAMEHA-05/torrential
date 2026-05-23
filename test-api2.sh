#!/bin/bash

# Diagnostic script for qBittorrent API testing

API_URL="http://localhost:8000"
QB_URL="http://localhost:8080"

echo "=== qBittorrent API Diagnostics ==="
echo ""

# Test 1: Direct qBittorrent connectivity with auth
echo "1. Testing qBittorrent direct connectivity..."
QB_TEST=$(curl -s -u admin:adminadmin "$QB_URL/api/v2/app/webapiVersion")
echo "   Response: $QB_TEST"
echo ""

# Test 2: FastAPI health check
echo "2. Testing FastAPI health endpoint..."
HEALTH=$(curl -s -i "$API_URL/health")
echo "   Response:"
echo "$HEALTH" | head -20
echo ""

# Test 3: Test adding a torrent
echo "3. Adding a test torrent..."
ADD_RESPONSE=$(curl -s -X POST "$API_URL/torrent/add" \
  -H "Content-Type: application/json" \
  -d '{
    "magnet": "magnet:?xt=urn:btih:1a7807d133a0e52228e84ac22199ee11b5ee4a72&dn=ubuntu"
  }')
echo "   Response: $ADD_RESPONSE"

# Extract hash
HASH=$(echo "$ADD_RESPONSE" | grep -o '"hash":"[^"]*' | cut -d'"' -f4)
echo "   Extracted hash: $HASH"
echo ""

if [ -z "$HASH" ]; then
    echo "ERROR: Could not extract hash from response!"
    exit 1
fi

# Test 4: Check torrent status
echo "4. Getting torrent status..."
STATUS=$(curl -s "$API_URL/torrent/$HASH/status")
echo "   Response: $STATUS"
echo ""

# Test 5: Test pause (which should work even during metaDL)
echo "5. Testing PAUSE endpoint..."
PAUSE=$(curl -s -w "\nHTTP Status: %{http_code}\n" -X POST "$API_URL/torrent/$HASH/pause")
echo "   Response: $PAUSE"
echo ""

# Test 6: Wait and try resume
echo "6. Testing RESUME endpoint..."
RESUME=$(curl -s -w "\nHTTP Status: %{http_code}\n" -X POST "$API_URL/torrent/$HASH/resume")
echo "   Response: $RESUME"
echo ""

# Test 7: Direct qBittorrent pause/resume test
echo "7. Testing qBittorrent pause directly..."
QB_PAUSE=$(curl -s -w "\nHTTP Status: %{http_code}\n" \
  -u admin:adminadmin \
  -X POST \
  "$QB_URL/api/v2/torrents/pause" \
  -d "hashes=$HASH")
echo "   Response: $QB_PAUSE"
echo ""

# Test 8: Remove torrent
echo "8. Removing torrent..."
REMOVE=$(curl -s -X DELETE "$API_URL/torrent/$HASH")
echo "   Response: $REMOVE"
echo ""

echo "=== Diagnostics Complete ==="