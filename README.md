# VNSTOCK API DEMO (Vnstock 3.x)

Bộ công cụ demo tích hợp toàn diện các API của thư viện `vnstock` phiên bản 3.x (Bản mới nhất). Chương trình được thiết kế linh hoạt, cho phép tra cứu nhanh lịch sử giá và các chỉ số tài chính của bất kỳ mã chứng khoán nào.

## 1. Môi trường yêu cầu (Quan trọng)
Thư viện `vnstock` 3.x yêu cầu môi trường Python ổn định. Để tránh các lỗi tương thích (đặc biệt là lỗi `applymap` trên Pandas 3.0), hãy cài đặt theo các phiên bản sau:
- **Python**: >= 3.7
- **Pandas**: `< 3.0.0` (Khuyên dùng `2.2.3` hoặc `2.3.3`)
- **vnstock**: `>= 3.0.0`
- **pytz**: Cần thiết cho xử lý múi giờ.

## 2. Hướng dẫn cài đặt
Mở cmd/terminal và chạy lệnh sau để thiết lập môi trường chuẩn:
```bash
pip install vnstock pytz "pandas<3.0.0"
```

## 3. Cách chạy chương trình
Cấu trúc lệnh chạy:
```bash
python vnstock_demo.py "<DANH_SÁCH_MÃ>" <SỐ_PHIÊN> <CHẾ_ĐỘ_RÚT_GỌN>
```

### Các tham số truyền vào:
1.  **DANH_SÁCH_MÃ** (Mặc định: `FPT`): Danh sách mã chứng khoán, phân cách bằng dấu phẩy hoặc dấu cách (ví dụ: `HPG,PVD,VNM` hoặc `"HPG VCB"`).
2.  **SỐ_PHIÊN** (Mặc định: `20`): Số lượng phiên giao dịch gần nhất muốn hiển thị.
3.  **CHẾ_ĐỘ_RÚT_GỌN** (Mặc định: `0`):
    - `0`: Hiển thị đầy đủ (Lịch sử giá, Tổng quan công ty, Báo cáo tài chính, Chỉ số tài chính).
    - `1`: Chỉ hiển thị bảng lịch sử giá cho từng mã (Minimal Mode).

### Ví dụ sử dụng:
- **Xem nhiều mã đồng thời (Chế độ rút gọn)**:
  ```bash
  python vnstock_demo.py HPG,PVD,TCB 15 1
  ```
- **Tra cứu danh sách bằng dấu cách (Cần bọc trong ngoặc kép)**:
  ```bash
  python vnstock_demo.py "FPT VCB VNM" 20 1
  ```
- **Lọc cổ phiếu sàn HOSE theo Target (Cực kỳ mạnh mẽ)**:
  - Lệnh: `python vnstock_demo.py SCREEN_HOSE`
  - Chức năng: Quét toàn bộ ~400+ mã trên sàn HOSE dựa trên 4 bộ lọc kỹ thuật khắt khe:
    1. **Thanh khoản**: Loại bỏ rác, chỉ lấy mã có Vol 20p > 100k và Giá > 5k.
    2. **Xu hướng**: Chỉ lấy mã đang trong Uptrend (Giá > SMA20 và SMA50).
    3. **Tích lũy**: Tìm các mã có nền giá phẳng (Biên độ 20 phiên < 15%).
    4. **Điểm nổ (Trigger)**: Bắt các mã có phiên bùng nổ về Giá (>2%) và Khối lượng (>1.5x trung bình).
  - **Lưu ý cho gói Guest**: Vì giới hạn 20 yêu cầu/phút, chương trình đã được cấu hình tự động trễ 3.5 giây/mã. Quá trình quét toàn sàn HOSE sẽ mất khoảng 20-30 phút. Kết quả cuối cùng sẽ được ghi vào file `result.txt`.

## 4. Các tính năng nổi bật trong code
- **Cột tính toán bổ sung**: Bảng lịch sử giá tự động tính thêm 2 cột:
  - `change`: Mức tăng/giảm giá tuyệt đối so với phiên trước.
  - `pct_change`: Phần trăm (%) tăng/giảm so với phiên trước.
- **Nguồn dữ liệu**: Mặc định sử dụng nguồn `VCI` (VietCap) cho độ ổn định cao.
- **Xử lý lỗi**: Mỗi đầu mục API được đặt trong khối `try...except` riêng biệt, giúp chương trình vẫn chạy tiếp nếu một nguồn dữ liệu cụ thể gặp sự cố.

## 5. Cấu trúc đối tượng API (Vnstock 3.x)
Khác với các bản cũ, Vnstock 3.x sử dụng hướng đối tượng:
- `v = Vnstock()`: Khởi tạo thư viện.
- `stock = v.stock(symbol='XXX', source='VCI')`: Khởi tạo đối tượng cho mã cụ thể.
- `stock.quote.history(...)`: Lấy dữ liệu giá.
- `stock.finance.income_statement(...)`: Lấy báo cáo tài chính.
- `stock.company.overview()`: Lấy thông tin doanh nghiệp.

> [!TIP]
> Do thị trường chứng khoán Việt Nam không giao dịch vào cuối tuần và ngày lễ, tham số `SỐ_PHIÊN` sẽ tự động lấy dữ liệu trong khoảng thời gian rộng hơn (60 ngày) để đảm bảo trích xuất đủ số lượng phiên giao dịch thực tế bạn yêu cầu.
