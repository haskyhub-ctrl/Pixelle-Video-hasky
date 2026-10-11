# Tập Làm Chị

Game HTML một file cho bé 4 tuổi chuẩn bị làm chị. Bé không cần biết đọc: mọi hướng dẫn được đọc to bằng giọng tiếng Việt của máy (Web Speech API), nút to, có gợi ý sáng lên khi bé chọn sai 2 lần.

- `index.html`: mở trực tiếp bằng trình duyệt (máy tính bảng, điện thoại, máy tính). Không cần mạng, chỉ trừ phông chữ Google Fonts.
- `game.html`: cùng nội dung, bản dùng để xuất bản thành Artifact (không có thẻ `<html>/<head>`).

## 8 trò chơi

| Trò chơi | Bé học gì | Dạng chơi |
|---|---|---|
| Rửa tay thật sạch | 5 bước rửa tay, chà đủ 20 nhịp đếm; khi nào cần rửa tay | Xếp thứ tự + xoa màn hình + phân loại |
| Thay tã cho búp bê | Đồ dùng thay tã, 7 bước, lau từ trước ra sau; với em thật bé làm "trợ lý" | Phân loại + xếp thứ tự + câu hỏi |
| Chạm nhẹ, thương em | Việc được / không được làm với em sơ sinh | Phân loại 11 tình huống |
| Vì sao em khóc? | Dấu hiệu đói, buồn ngủ, tã bẩn, muốn ôm; em sốt/khóc mãi thì gọi bố mẹ, không lắc em | 6 câu đố "thám tử" |
| Giường ngủ an toàn | Em nằm ngửa, một mình, cũi trống | Dọn cũi + câu hỏi |
| Thương mẹ | Mẹ sau sinh cần nước, gối, ăn, nghỉ, được ôm | Chọn đồ mang cho mẹ, đầy tim |
| Dọn nhà gọn gàng | Đồ nhỏ dễ hóc (bi, xu, pin, bóng bay) cất lên cao; lau bàn; đồ bẩn vào giỏ | Phân loại + lau vết bẩn + câu hỏi |
| Mẹ cần gì nhỉ? | Nghe và lấy đúng đồ của em (tã, khăn, áo, tất, mũ) | Nghe lời mẹ, chọn đồ |

Mỗi trò cho 1–3 sao theo số lần chọn sai và một huy hiệu. Tiến độ lưu trên trình duyệt của máy. Màn "Người lớn" cho phép đặt tên gọi của bé và em (vd: "chị Na", "em Bin") để giọng đọc gọi đúng tên.

## Cơ sở nghiên cứu

1. **Lớp chuẩn bị làm anh chị (Sibling Preparation / Big Sibling class)** ở các bệnh viện Mỹ (Loyola Medicine, Santa Barbara Cottage, Woman's Hospital, Elliot Hospital...), cho trẻ 3–8 tuổi: tập thay tã, cho ăn, mặc đồ, chơi với búp bê; học em bé sơ sinh trông thế nào và cách bế, chơi an toàn; cách giúp ở nhà. Game mô phỏng lại phần "tập với búp bê" và "cách giúp ở nhà".
2. **Viện Nhi khoa Hoa Kỳ (AAP / HealthyChildren.org)**: chuẩn bị tâm lý cho anh chị (đọc sách, giải thích đôi khi mẹ phải chăm em trước); giấc ngủ an toàn "ABC" (Alone, Back, Crib: một mình, nằm ngửa, cũi trống không gối/chăn dày/thú bông); dấu hiệu đói sớm (mút tay, quay đầu tìm vú).
3. **Pregnancy, Birth and Baby (Bộ Y tế Úc) và Safety 1st**: không để trẻ nhỏ ở một mình với em bé; dạy vuốt em bằng cả lòng bàn tay để tránh chọc, cào; anh chị chỉ được ôm em khi có người lớn, tập trước trên búp bê; ngồi trên ghế có gối đỡ rồi người lớn đặt em vào lòng.
4. **CDC / WHO**: rửa tay với xà phòng, chà ít nhất 20 giây (lòng bàn tay, mu bàn tay, kẽ ngón, móng); rửa tay trước khi chạm trẻ sơ sinh, sau khi đi vệ sinh, chơi với thú cưng. Người đang ốm nên đeo khẩu trang và hạn chế tiếp xúc gần với trẻ sơ sinh.
5. **Phòng hóc dị vật**: đồ chơi lọt qua lõi cuộn giấy vệ sinh là nguy cơ hóc với trẻ dưới 3 tuổi; pin cúc áo, đồng xu, bóng bay xẹp là các dị vật nguy hiểm hàng đầu.
6. **Hội chứng rung lắc trẻ em**: dạy trẻ khi em khóc mãi thì gọi người lớn, không bao giờ lắc em.
7. **Montessori "practical life"** cho trẻ 3–6 tuổi: cất đồ chơi, lau bàn, phân loại đồ giặt, dọn bàn, có người lớn giám sát và dụng cụ cỡ trẻ em.
8. **Chăm sóc hậu sản**: mẹ cho con bú cần uống nhiều nước, ăn đủ, nghỉ ngơi; trẻ lớn giảm ghen tị khi được giao "việc của chị" và được nhắc rằng mình vẫn được yêu thương.

Nguồn:
- https://www.healthychildren.org/English/ages-stages/prenatal/Pages/Preparing-Your-Family-for-a-New-Baby.aspx
- https://www.healthychildren.org/English/ages-stages/baby/sleep/Pages/a-parents-guide-to-safe-sleep.aspx
- https://www.cdc.gov/clean-hands/about/index.html
- https://www.pregnancybirthbaby.org.au/toddler-and-the-new-baby
- https://health.clevelandclinic.org/how-to-prepare-toddler-for-new-baby
- https://www.loyolamedicine.org/event/2025/08/23/big-sister-big-brother-sibling-preparation-class-august-23
- https://themontessorinotebook.com/age-appropriate-chores-for-children

Game không thay thế người lớn giám sát. Nội dung y khoa ở mức phổ thông; hỏi bác sĩ nhi khi cần.
