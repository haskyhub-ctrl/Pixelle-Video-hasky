# Bộ công cụ nghiên cứu ngách (Niche Research)

Bộ công cụ nằm ở menu bên trái của giao diện web (`./start_web.sh`), gồm 15 trang chia 6 nhóm:

| Nhóm | Trang | Dữ liệu cần |
|---|---|---|
| Tổng quan | Tổng quan, Kiểm tra kiếm tiền | YouTube API |
| Nghiên cứu | Đào ngách, Đào đa thị trường, Săn kênh nổ view, Phân tích kênh, Xu hướng đa nền tảng, Nghiên cứu từ khoá | YouTube API (+ TikHub cho TikTok/Douyin…) |
| Sáng tạo | Chủ đề thắng, Studio kịch bản, Lịch đăng | LLM |
| Tối ưu kênh | Kênh của tôi, Bác sĩ kênh, Tối ưu video (SEO) | YouTube API + LLM |
| Dữ liệu | Ngách đã lưu & kênh theo dõi | — |

Code chính: `pixelle_video/services/niche/` (công thức ở `formulas.py`), API ở `/api/niche/*`.

## Cấu hình

```yaml
niche:
  youtube_api_key: ""   # Google Cloud Console → bật YouTube Data API v3 → tạo API key (10.000 units/ngày miễn phí)
  tikhub_api_key: ""    # tuỳ chọn: TikTok, Douyin, Xiaohongshu, Kuaishou, Bilibili, Instagram, Threads, X, Weibo, Zhihu, Lemon8
  default_region: VN
  avd_ratio: 0.35       # % thời lượng xem trung bình giả định để ước tính giờ xem
```

Có thể nhập ngay trên giao diện: mục **⚙️ Cài đặt API nghiên cứu**.
Google Trends (độ quan tâm theo từ khoá) cần cài thêm `pip install pytrends`, nếu không có thì bỏ qua.

Chi phí quota YouTube: `search` = 100 units, `videos`/`channels`/`playlistItems` = 1 unit.
Một lần đào ngách 50 kết quả tốn khoảng 160 units, tức khoảng 60 lần đào mỗi ngày với quota miễn phí.

## Công thức tìm video vượt trội

Ký hiệu: **V** = views, **S** = sub của kênh, **M** = view trung vị các video gần đây của chính kênh đó
(không tính video đang xét), **t** = tuổi video (giờ), **L/C/Sh** = like/bình luận/chia sẻ.

| Chỉ số | Công thức | Ý nghĩa |
|---|---|---|
| Outlier | `V / M` (khi chưa có M thì dùng `V / max(S, 100)`) | Gấp bao nhiêu lần video bình thường của kênh. ≥2x là vượt trội, ≥5x là nổ |
| Views/Sub | `V / max(S, 100)` | > 1 nghĩa là video đã thoát khỏi tệp sub, được thuật toán đẩy |
| Views/giờ | `V / max(t, 1)` | Tốc độ tuyệt đối |
| Momentum | `V / t^0.7` | Tốc độ đã bù tuổi video, vì view dồn vào những ngày đầu |
| Tương tác | `(L + 2C + 3Sh) / V` | Bình luận và chia sẻ có trọng số cao hơn like |
| Độ nhỏ kênh | `1 − log10(S) / 6` | 1.0 với kênh mới, 0 với kênh 1M sub |

**Điểm vượt trội (0–100)**: mỗi chỉ số được nén về khoảng 0–1 bằng hàm logistic `f(x) = 1 / (1 + e^-(x − tâm)/độ dốc)`:

```
điểm = 100 × ( 0.35 · f(log10 Outlier;   tâm log10 2, dốc 0.25)
             + 0.25 · f(log10 Views/Sub; tâm 0,       dốc 0.40)
             + 0.20 · f(log10 Momentum;  tâm 2.5,     dốc 0.50)
             + 0.10 · f(Tương tác;       tâm 4%,      dốc 1.5%)
             + 0.10 · Độ nhỏ kênh )
```

Với nền tảng không có số sub, trọng số chuyển sang momentum (0.6), tương tác (0.3) và độ nhỏ (0.1).

**Nhãn tự động**:
- 🔥 Nổ view: outlier ≥ 5 hoặc views/sub ≥ 3
- 🚀 Vượt trội: outlier ≥ 2
- 🌱 Kênh nhỏ ăn view: sub < 10K và views ≥ sub
- ⚡ Đang lên nhanh: ≤ 7 ngày tuổi và ≥ 500 view/giờ
- 💬 Tương tác cao: ER ≥ 8%

## Điểm ngách (Đào ngách)

Tính trên tập kết quả tìm kiếm của một chủ đề:

```
nhu cầu    = f(log10 view trung vị; tâm 4 (=10K), dốc 0.6)   [trộn 70/30 với Google Trends nếu bật]
cơ hội     = % video của kênh < 100K sub có V ≥ S
cạnh tranh = 0.5 · %kênh ≥ 1M sub + 0.5 · f(log10 sub trung vị; tâm 5 (=100K), dốc 0.6)
độ mới     = % video đăng trong 30 ngày

điểm ngách = 100 × (0.35·nhu cầu + 0.30·cơ hội + 0.20·(1 − cạnh tranh) + 0.15·độ mới)
```

Đánh giá: ≥ 70 nên làm ngay · 55–70 khá, cần góc nhìn khác biệt · 40–55 cạnh tranh cao hoặc ít nhu cầu · < 40 không nên vào.

Bộ lọc **"chỉ hiện đúng chủ đề"**: bỏ dấu tiếng Việt, yêu cầu ≥ 60% từ của chủ đề xuất hiện trong tiêu đề, tags hoặc 300 ký tự đầu mô tả.
Với chủ đề tiếng Trung (không có dấu cách) thì so khớp chuỗi con.

## Săn kênh nổ view

Tìm video nhiều view trong khoảng thời gian chọn, giữ các kênh dưới ngưỡng sub, rồi tải 15 video gần nhất của từng kênh:

```
tỷ lệ gần đây = view trung vị 15 video gần nhất / S
hit rate      = % video có V > S
độ trẻ        = 1 − tuổi kênh / 730 ngày
tăng trưởng   = f(%sub tăng mỗi ngày; tâm 1%, dốc 0.7%)    ← từ snapshot giữa các lần quét
               (lần đầu chưa có snapshot thì dùng momentum của video tốt nhất)

điểm nổ = 100 × (0.30·f(log10 tỷ lệ gần đây) + 0.20·hit rate + 0.15·độ trẻ + 0.15·độ nhỏ + 0.20·tăng trưởng)
```

Tốc độ tăng sub mỗi ngày = `(S_cuối / S_đầu)^(1/số ngày) − 1`.

## Nghiên cứu từ khoá

Gợi ý lấy từ YouTube autocomplete (miễn phí): từ khoá gốc, từ khoá + a…z, và các tiền tố câu hỏi.
Mỗi từ khoá được chấm điểm dựa trên top 20 kết quả:

```
nhu cầu   = f(log10 view trung vị; tâm 10K)
đối thủ yếu = 1 − f(log10 sub trung vị; tâm 100K)
bão hoà   = f(log10 tổng số kết quả; tâm ~316K)
điểm = 100 × (0.45·nhu cầu + 0.35·đối thủ yếu + 0.20·(1 − bão hoà))
```

Từ khoá ≤ 3 từ là "ngắn", từ 4 từ trở lên là "dài (long-tail)".

## Đào đa thị trường

AI dịch từ khoá sang ngôn ngữ bản địa, rồi chấm điểm ngách ở từng quốc gia:
`điểm thị trường = điểm ngách × (0.6 + 0.4 × min(RPM / 5$, 1))`.
Cách này ưu tiên thị trường vừa dễ vào vừa trả tiền cao.

## Kiểm tra kiếm tiền

- **YPP đầy đủ**: ≥ 1.000 sub VÀ (≥ 4.000 giờ xem 12 tháng HOẶC ≥ 10M view Shorts 90 ngày).
- **YPP giai đoạn đầu**: ≥ 500 sub, ≥ 3 video trong 90 ngày VÀ (≥ 3.000 giờ HOẶC ≥ 3M view Shorts).
- Giờ xem ước tính = `Σ V × thời lượng × AVD% / 3600` của video dài đăng trong 12 tháng. Đây là ước tính lạc quan vì dùng view trọn đời.
- Thu nhập/tháng = `view video dài 30 ngày / 1000 × RPM + view Shorts 30 ngày / 1000 × RPM × 6%`,
  với `RPM = RPM quốc gia × hệ số ngách`. Bảng giá trị nằm trong `formulas.py` và chỉnh được. Khoảng dao động hiển thị là ×0.5 đến ×1.6.

## Bác sĩ kênh

Kiểm tra tự động (mỗi lỗi kèm số liệu gây ra nó): ngừng đăng > 14 ngày, < 1 video/tuần,
khoảng cách đăng không đều (hệ số biến thiên > 1), > 30% video flop (< 0.3× trung vị),
view/sub < 5%, tương tác < 2%, tiêu đề ngoài 40–70 ký tự, mô tả < 200 ký tự, > 50% video không có tags,
10 video gần nhất < 70% so với 10 video trước, và thua đối thủ về view hoặc tần suất.

`Điểm sức khoẻ = 100 − 20·(lỗi nặng) − 10·(lỗi vừa) − 4·(lỗi nhẹ)`. Sau đó AI viết chẩn đoán và kế hoạch 30 ngày.

## Khung giờ đăng tốt

Gom video theo (thứ, giờ GMT+7): `điểm khung = trung vị outlier × log2(1 + số video)`.
Cách tính này thưởng khung giờ vừa hiệu quả vừa có đủ mẫu.

## Tối ưu SEO (10 tiêu chí, tổng 100 điểm)

Tiêu đề 40–70 ký tự (15) · từ khoá trong tiêu đề (20) · từ khoá trong 40 ký tự đầu (10) · mô tả ≥ 200 ký tự (10) ·
từ khoá ở 2 dòng đầu mô tả (10) · 5–15 tags (10) · có tag chứa từ khoá (5) · 3–5 hashtag (5) · có chapters (10) ·
tiêu đề không viết HOA toàn bộ (5).

## Nền tảng ngoài YouTube

- **Reddit**: JSON công khai, không cần key. Reddit không công khai view nên dùng `views ≈ upvote × 30`.
- **TikHub** (TikTok, Douyin, Xiaohongshu, Kuaishou, Bilibili, Instagram, Threads, X, Weibo, Zhihu, Lemon8):
  bộ đọc tự nhận diện bài đăng trong JSON trả về (id + nội dung + bộ đếm). Vì vậy khi TikHub đổi cấu trúc thì vẫn chạy.
  Nếu TikHub đổi tên endpoint, sửa trong `niche.tikhub_endpoints`. Với nền tảng không công khai view, dùng `views ≈ like × 20`.

## Lưu trữ

SQLite tại `data/niche.db`: ngách đã lưu, kênh theo dõi, snapshot sub (để tính tăng trưởng), lịch đăng, lịch sử dùng API.
