"""Generate the demo voiceovers with edge-tts: python tts.py assets"""
import asyncio, os, sys, certifi
# Behind a TLS-intercepting proxy, point edge-tts at that CA bundle: EDGE_TTS_CA_BUNDLE=/path/ca.crt
if os.environ.get("EDGE_TTS_CA_BUNDLE"):
    certifi.where = lambda: os.environ["EDGE_TTS_CA_BUNDLE"]
import edge_tts
LINES = [
 "Mỗi ngày đọc mười trang sách. Nghe thì nhỏ, nhưng một năm là hơn ba nghìn trang.",
 "Ba nghìn trang là khoảng mười lăm cuốn sách, đủ để thay đổi cách bạn nghĩ.",
 "Bắt đầu từ hôm nay. Chỉ mười trang thôi.",
]
async def main(out):
    for i, t in enumerate(LINES, 1):
        await edge_tts.Communicate(t, "vi-VN-HoaiMyNeural", rate="+5%").save(f"{out}/vo{i}.mp3")
asyncio.run(main(sys.argv[1]))
