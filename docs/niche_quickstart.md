# Chạy app Nghiên cứu ngách trên máy của bạn (số liệu thật)

App chạy local hoàn toàn, chỉ gọi ra ngoài tới các API bạn cấp key. Không có máy chủ trung gian nào của bên thứ ba lưu dữ liệu của bạn — mọi thứ (ngách đã lưu, kênh theo dõi, lịch đăng) nằm trong `data/niche.db` trên máy bạn.

## 1. Cài đặt (một lần)

Cần Python ≥ 3.11 và [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-cua-ban>
cd Pixelle-Video-hasky
git checkout claude/brave-carson-cjfxhf
uv sync                       # cài toàn bộ thư viện
uv run playwright install chromium   # chỉ cần nếu bạn dùng tính năng render của Pixelle-Video
```

## 2. Nhập API key

Cách gọn nhất: tạo file `.env` ở thư mục gốc (sao từ `.env.example`):

```bash
cp .env.example .env
```

Rồi điền:

```ini
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
YOUTUBE_API_KEY=AIza...
TIKHUB_API_KEY=            # để trống nếu chưa dùng TikTok/Douyin...
NICHE_DEFAULT_REGION=VN
```

Hoặc nhập trực tiếp trong giao diện ở mục **⚙️ Cài đặt API nghiên cứu** (lưu vào `config.yaml`).

### Lấy key ở đâu
- **YouTube Data API v3** (bắt buộc, miễn phí 10.000 units/ngày): [Google Cloud Console](https://console.cloud.google.com) → tạo project → *APIs & Services* → bật **YouTube Data API v3** → *Credentials* → **Create credentials → API key**.
- **LLM** (bắt buộc cho phần AI): OpenAI, DeepSeek, Qwen, hoặc bất kỳ API tương thích OpenAI. Có thể dùng Ollama chạy local miễn phí (`LLM_BASE_URL=http://localhost:11434/v1`).
- **TikHub** (tuỳ chọn, trả phí theo request): [tikhub.io](https://tikhub.io) — mở khoá TikTok, Douyin, Xiaohongshu, Kuaishou, Bilibili, Instagram, Threads, X, Weibo, Zhihu, Lemon8.
- **Reddit & Google Trends**: không cần key (Google Trends cần `uv pip install pytrends`).

## 3. Kiểm tra kết nối (xác nhận chạy số liệu thật)

```bash
uv run python -m pixelle_video.services.niche.doctor --platform douyin
```

Kết quả mong đợi khi key đúng:

```
✅  YouTube Data API    1 units · ví dụ: Rick Astley - Never Gonna Give You Up
✅  LLM (AI)            model trả lời: OK
✅  Reddit              1 kết quả
✅  Google Trends       20 xu hướng (VN)
✅  TikHub · Douyin     18 bài
```

`❌` kèm lý do → xem lại key hoặc endpoint. `➖` nghĩa là chưa cấu hình (bỏ qua).

## 4. Chạy app

```bash
./start_niche.sh      # Linux/macOS  (Windows: start_niche.bat)
```

Mở trình duyệt tại **http://localhost:8501**. Menu bên trái chia 3 khu như DeepNiche:

| Khu | Trang |
|---|---|
| Tổng quan | Tổng quan · Kiểm tra kiếm tiền |
| Khu YouTube · Tìm ngách | Đào ngách · Đào đa thị trường · Săn kênh nổ view · Phân tích kênh · Mổ băng đối thủ · Xu hướng đa nền tảng · Nghiên cứu từ khoá |
| Khu YouTube · Sản xuất | Chủ đề thắng · Studio kịch bản (kèm sinh prompt ảnh/video) · Lịch đăng · Kênh của tôi · Bác sĩ kênh · Tối ưu video (SEO) |
| Khu TikTok Affiliate | Trung tâm Affiliate · Săn sản phẩm win · Kênh affiliate làm tốt · Phân tích kênh TikTok · Mổ băng video bán hàng · Xu hướng TikTok · Kịch bản video bán hàng · Lịch đăng video |
| Dữ liệu & Tài khoản | Ngách đã lưu & kênh · Kết nối API · Chi phí API |

Từ **Studio kịch bản** / **Kịch bản video bán hàng** bấm "🎬 Tạo video" để đẩy sang trình tạo video sẵn có của Pixelle-Video.

### Khu TikTok Affiliate & nguồn dữ liệu TikTok Shop
Khu Affiliate cần dữ liệu TikTok Shop (số đã bán, video gắn giỏ, điểm Win). Mặc định dùng **TikHub**
(`TIKHUB_API_KEY`). Khi **chưa cấu hình**, trang "Săn sản phẩm win" chạy bằng **dữ liệu mẫu** để xem trước —
công thức điểm Win và giao diện giữ nguyên, chỉ cần cắm key là ra số liệu thật. Nếu bạn dùng Kalodata/EchoTik,
báo mình endpoint để thêm adapter (xem `pixelle_video/services/niche/products.py`).

## 5. API (tuỳ chọn)

Nếu muốn gọi bằng code thay vì giao diện:

```bash
uv run python api/app.py        # http://localhost:8000/docs
```

Các endpoint ở nhóm **Niche Research** (`/api/niche/search`, `/api/niche/channel/analyze`, `/api/niche/keywords`, ...).

## Chi phí & quota
- Một lần **đào ngách** 50 kết quả ≈ 160 units YouTube → khoảng 60 lần/ngày với quota miễn phí. Trang nào cũng hiện "Dự kiến" trước khi chạy và "Đã dùng" sau khi chạy.
- **TikHub** tính tiền theo từng request; đặt giá ở `niche.tikhub_cost_per_request_usd` để app quy ra tiền.
- **LLM** tính theo token của nhà cung cấp bạn dùng.

Công thức chấm điểm và chi tiết từng chức năng: xem `docs/niche_research.md`.
