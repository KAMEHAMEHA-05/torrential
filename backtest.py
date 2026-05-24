from media.media import analyze_media
from playback.strategies import determine_strategy
from pathlib import Path
import asyncio

print(asyncio.run(determine_strategy(asyncio.run(analyze_media(str(Path("~/Downloads/sample-2.mkv").expanduser()))), "test-session-id")))