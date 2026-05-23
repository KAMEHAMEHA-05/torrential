#!/bin/bash

# Test script to verify FFmpeg and transcode setup

echo "=== FFmpeg Test ==="
which ffmpeg
ffmpeg -version 2>/dev/null | head -1

echo ""
echo "=== Transcode Cache Directory ==="
CACHE_DIR="/tmp/transcode-cache"
mkdir -p $CACHE_DIR
ls -la $CACHE_DIR
echo "Cache dir: $CACHE_DIR"

echo ""
echo "=== Testing FFmpeg Transcode (create small test video) ==="

# Create a small test file to verify ffmpeg works
TEST_INPUT="/tmp/test_input.mp4"
TEST_OUTPUT="/tmp/test_output.mp4"

# Generate 1-second test video with ffmpeg
echo "Creating test video (1 second)..."
ffmpeg -f lavfi -i testsrc=duration=1:size=320x240:rate=1 -f lavfi -i sine=frequency=1000:duration=1 -c:v libx264 -preset ultrafast -c:a aac "$TEST_INPUT" -y 2>&1 | grep -E "(error|Error|ERROR|Output)" || echo "✓ Test video created"

if [ -f "$TEST_INPUT" ]; then
  echo "✓ Input file created: $(ls -lh $TEST_INPUT | awk '{print $5}')"
  
  # Try transcoding
  echo "Testing transcode..."
  ffmpeg -i "$TEST_INPUT" -c:v libx264 -preset ultrafast -b:v 3000k -c:a aac -b:a 128k -movflags +faststart -y "$TEST_OUTPUT" 2>&1 | tail -5
  
  if [ -f "$TEST_OUTPUT" ]; then
    echo "✓ Output file created: $(ls -lh $TEST_OUTPUT | awk '{print $5}')"
    rm "$TEST_INPUT" "$TEST_OUTPUT"
    echo "✓ FFmpeg transcoding works!"
  else
    echo "✗ FFmpeg transcode failed"
  fi
else
  echo "✗ Could not create test input"
fi

echo ""
echo "=== Backend Health Check ==="
echo "Checking if backend is running..."
curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "Backend not responding on localhost:8000"

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Make sure your backend is running the fastapi_complete_with_transcode.py"
echo "2. Verify FFmpeg is installed: apt-get install ffmpeg"
echo "3. Try playing an MKV file - it should transcode automatically"