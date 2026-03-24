import sys
import pandas as pd
from vnstock import Vnstock
from datetime import datetime, timedelta
import os
import time

def analyze_stock(v, sym, limit, minimal_mode, interval='1D'):
    """
    Hàm phân tích một mã cổ phiếu cụ thể.
    """
    try:
        if sym == 'GOLD':
            import requests
            print(f"\n" + "="*50)
            print(f"      PHÂN TÍCH MÃ: {sym} (Binance Spot Gold) ")
            print("="*50)
            print(f"\n--- [ LỊCH SỬ GIÁ {sym} (Đơn vị: USD/Oz, Vol: Oz) ] ---")
            
            # Mapping vnstock intervals to Binance
            mapping = {
                '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m', 
                '1H': '1h', '1D': '1d', '1W': '1w', '1M': '1M'
            }
            binance_interval = mapping.get(interval, '1d')
            
            url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={binance_interval}&limit={limit}"
            
            try:
                response = requests.get(url, timeout=10)
                data = response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    df_hist = pd.DataFrame(data, columns=[
                        'time', 'open', 'high', 'low', 'close', 'volume', 
                        'close_time', 'quote_asset_volume', 'number_of_trades', 
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])
                    
                    # Convert types
                    df_hist['time'] = pd.to_datetime(df_hist['time'], unit='ms')
                    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
                    df_hist[numeric_cols] = df_hist[numeric_cols].apply(pd.to_numeric)
                    
                    # Formatting time
                    if binance_interval in ['1m', '5m', '15m', '30m', '1h']:
                        df_hist['time'] = df_hist['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        df_hist['time'] = df_hist['time'].dt.strftime('%Y-%m-%d')
                        
                    df_hist['change'] = df_hist['close'].diff()
                    df_hist['pct_change'] = df_hist['close'].pct_change() * 100
                    
                    pd.options.display.float_format = '{:,.2f}'.format
                    print(df_hist[['time', 'open', 'high', 'low', 'close', 'change', 'pct_change', 'volume']])
                else:
                    print(f"Không tìm thấy dữ liệu hoặc lỗi API cho mã {sym}.")
            except Exception as e:
                print(f"Lỗi truy xuất Binance cho {sym}: {e}")
            return

        stock = v.stock(symbol=sym, source='KBS')
        
        print(f"\n" + "="*50)
        print(f"      PHÂN TÍCH MÃ: {sym} ")
        print("="*50)

        # 3. Dữ liệu Giao dịch Lịch sử
        print(f"\n--- [ LỊCH SỬ GIÁ {sym} ] ---")
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            # Tính toán start_date an toàn và đủ số lượng nến dựa trên khung (interval)
            now = datetime.now()
            if interval == '1m':
                days_offset = max(2, limit // 200 + 1)
            elif interval == '5m':
                days_offset = max(3, limit // 40 + 1)
            elif interval == '15m':
                days_offset = max(5, limit // 15 + 1)
            elif interval == '30m':
                days_offset = max(7, limit // 8 + 1)
            elif interval == '1H':
                days_offset = max(10, limit // 4 + 1)
            elif interval == '1D':
                days_offset = limit * 2
            elif interval == '1W':
                days_offset = limit * 8
            elif interval == '1M':
                days_offset = limit * 45
            else:
                days_offset = limit * 3
                
            start_date = (now - timedelta(days=days_offset)).strftime('%Y-%m-%d')
            
            df_hist = stock.quote.history(start=start_date, end=end_date, interval=interval)
            
            if not df_hist.empty:
                df_hist = df_hist.sort_values('time')
                df_hist['change'] = df_hist['close'].diff()
                df_hist['pct_change'] = df_hist['close'].pct_change() * 100
                
                result = df_hist.tail(limit).copy()
                pd.options.display.float_format = '{:,.2f}'.format
                print(result[['time', 'open', 'high', 'low', 'close', 'change', 'pct_change', 'volume']])
            else:
                print(f"Không tìm thấy dữ liệu lịch sử cho mã {sym}.")
        except Exception as e:
            print(f"Lỗi History {sym}: {e}")

        if minimal_mode:
            return

        # 4. Các mục bổ sung
        print(f"\n--- [ TỔNG QUAN DOANH NGHIỆP {sym} ] ---")
        try:
            print(stock.company.overview())
        except: pass

        print(f"\n--- [ BÁO CÁO TÀI CHÍNH (IS) {sym} ] ---")
        try:
            print(stock.finance.income_statement(period='quarter', year_count=1).head(2))
        except: pass

        print(f"\n--- [ CHỈ SỐ TÀI CHÍNH {sym} ] ---")
        try:
            print(stock.finance.ratio().head(2))
        except: pass

    except Exception as e:
        print(f"\nLỗi khởi tạo mã {sym}: {e}")

def screen_hose_stocks(v):
    """
    Hàm lọc cổ phiếu sàn HOSE theo các tiêu chí kỹ thuật (Target) với cơ chế Retry.
    """
    print("\n" + "="*50)
    print("      ĐANG LỌC CỔ PHIẾU SÀN HOSE (TARGET)       ")
    print("="*50)
    
    # 1. Lấy danh sách mã trên sàn HOSE (có Retry)
    hose_symbols = []
    print("[1/4] Đang lấy danh sách mã niêm yết trên HOSE...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            temp_stock = v.stock(symbol='FPT', source='KBS')
            all_symbols_df = temp_stock.listing.all_symbols()
            
            if 'exchange' in all_symbols_df.columns:
                hose_symbols = all_symbols_df[all_symbols_df['exchange'] == 'HOSE']['symbol'].unique().tolist()
            else:
                hose_symbols = all_symbols_df['symbol'].unique().tolist()
            
            if hose_symbols:
                break
        except Exception as e:
            print(f"Lần thử {attempt + 1} thất bại: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print("Không thể lấy danh sách mã sau nhiều lần thử.")
                return

    if not hose_symbols:
        print("Không tìm thấy mã chứng khoán nào.")
        return

    print(f"Dự kiến quét {len(hose_symbols)} mã. Với gói Guest (3.5s/mã), quá trình này sẽ mất khoảng {len(hose_symbols)*3.5/60:.1f} phút.")
    print("Vui lòng kiên nhẫn hoặc nhấn Ctrl+C để dừng.")

    results = []
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    print(f"[2/4] Đang phân tích kỹ thuật từng mã...")
    
    count = 0
    total = len(hose_symbols)

    for sym in hose_symbols:
        count += 1
        if count % 10 == 0:
            print(f"Tiến độ: {count}/{total} mã...")

        try:
            # Tăng độ trễ lên 3.5 giây để khớp với giới hạn 20 req/phút của gói Guest
            time.sleep(3.5)
            
            s = v.stock(symbol=sym, source='KBS')
            df_full = s.quote.history(start=start_date, end=end_date)
            
            if df_full.empty or len(df_full) < 50:
                continue

            df = df_full.sort_values('time').copy()
            
            # Tính toán các chỉ số
            df['sma20'] = df['close'].rolling(window=20).mean()
            df['sma50'] = df['close'].rolling(window=50).mean()
            df['vami20'] = df['volume'].rolling(window=20).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # ĐIỀU KIỆN 1: THANH KHOẢN
            c1_vol = latest['vami20'] > 100000
            c1_price = latest['close'] > 5.0
            if not (c1_vol and c1_price): continue

            # ĐIỀU KIỆN 2: XU HƯỚNG TĂNG
            c2_trend = latest['close'] > latest['sma20'] and latest['close'] > latest['sma50']
            if not c2_trend: continue

            # ĐIỀU KIỆN 3: TÍCH LŨY (20 phiên gần nhất)
            last_20 = df.tail(20)
            range_pct = (last_20['high'].max() - last_20['low'].min()) / last_20['low'].min()
            if range_pct > 0.15: continue

            # ĐIỀU KIỆN 4: ĐIỂM KÍCH NỔ (Trigger)
            price_inc = (latest['close'] - prev['close']) / prev['close']
            c4_price = price_inc > 0.02
            c4_candle = latest['close'] >= (latest['high'] + latest['low']) / 2
            c4_vol = latest['volume'] > 1.5 * latest['vami20']

            if c4_price and c4_candle and c4_vol:
                results.append({
                    'symbol': sym,
                    'price': latest['close'],
                    'pct': price_inc * 100,
                    'vol_ratio': latest['volume'] / latest['vami20'],
                    'range_20p': range_pct * 100
                })
                print(f" -> Tìm thấy mã: {sym}")

        except Exception as e:
            if "Rate Limit" in str(e):
                print(f"\n[WARNING] Hệ thống báo Rate Limit tại mã {sym}. Đang chờ 35 giây...")
                time.sleep(35)
                # Có thể thêm logic retry tại đây nếu cần
            continue

    print(f"[3/4] Tìm thấy {len(results)} mã thỏa mãn điều kiện.")

    # 4. Xuất kết quả
    print("[4/4] Đang ghi kết quả vào file result.txt...")
    with open('result.txt', 'w', encoding='utf-8') as f:
        f.write(f"BÁO CÁO LỌC CỔ PHIẾU HOSE (TARGET) - {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write("="*70 + "\n")
        f.write(f"{'MÃ':<8} | {'GIÁ':<10} | {'TĂNG%':<10} | {'VOL/AVG20':<12} | {'BIÊN NỀN%':<10}\n")
        f.write("-"*70 + "\n")
        for r in results:
            f.write(f"{r['symbol']:<8} | {r['price']:<10.2f} | {r['pct']:<10.2f} | {r['vol_ratio']:<12.2f} | {r['range_20p']:<10.2f}\n")
        f.write("="*70 + "\n")
        f.write("\nTiêu chí lọc:\n")
        f.write("1. Thanh khoản: Volume AVG 20p > 100k, Giá > 5k\n")
        f.write("2. Xu hướng: Giá > SMA20 và Giá > SMA50\n")
        f.write("3. Tích lũy: Biên độ nền 20 phiên < 15%\n")
        f.write("4. Điểm nổ: Giá tăng > 2%, Nến đóng nửa trên, Vol > 1.5x AVG 20p\n")

    print(f"XONG! Kết quả đã lưu tại 'result.txt'.")

def main():
    """
    Chương trình demo Vnstock 3.x đa mã.
    Hỗ trợ tham số: python vnstock_demo.py <DANH_SÁCH_MÃ> <SỐ_PHIÊN> <MINIMAL_MODE> <INTERVAL>
    Hoặc: python vnstock_demo.py SCREEN_HOSE
    """
    
    if len(sys.argv) > 1 and sys.argv[1].upper() == 'SCREEN_HOSE':
        v = Vnstock()
        screen_hose_stocks(v)
        return

    # 1. Xử lý tham số đầu vào
    input_syms = sys.argv[1] if len(sys.argv) > 1 else 'FPT'
    # Hỗ trợ phân tách bằng dấu phẩy hoặc dấu cách
    if ',' in input_syms:
        symbols = [s.strip().upper() for s in input_syms.split(',')]
    else:
        symbols = [s.strip().upper() for s in input_syms.split()]
        
    try:
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    except:
        limit = 20
        
    minimal_mode = (sys.argv[3] == '1') if len(sys.argv) > 3 else False
    
    interval_input = sys.argv[4] if len(sys.argv) > 4 else '1D'
    # Chuẩn hóa linh hoạt
    low_interval = interval_input.lower()
    if low_interval in ['1m', '5m', '15m', '30m', '1h']:
        interval = low_interval if low_interval != '1h' else '1H' # vnstock thường dùng 1H
    elif low_interval in ['1d', '1w', '1m']: # 1M là tháng
        interval = interval_input.upper()
    else:
        # Nếu không khớp, thử đoán: 'm' ở cuối là phút, còn lại viết hoa
        if low_interval.endswith('m') and low_interval != '1m': # '1m' ở đây có thể là 1 month hoặc 1 minute tùy context, nhưng vnstock dùng 1M cho month
             interval = low_interval
        else:
             interval = interval_input.upper()
             
    # Danh sách các khung được vnstock hỗ trợ chính thức
    SUPPORTED_INTERVALS = ['1m', '5m', '15m', '30m', '1H', '1D', '1W', '1M']
    if interval not in SUPPORTED_INTERVALS:
        print(f"Cảnh báo: Khung '{interval}' có thể không được hỗ trợ. Các khung chuẩn: {', '.join(SUPPORTED_INTERVALS)}")
    
    # 2. Khởi tạo Vnstock
    v = Vnstock()
    
    print("==================================================")
    print(f"      VNSTOCK 3.x MULTI-STOCK DEMO               ")
    print(f"      Danh sách: {', '.join(symbols)}")
    print("==================================================")

    for sym in symbols:
        if sym:
            analyze_stock(v, sym, limit, minimal_mode, interval)

    print("\n" + "="*50)
    print("      HOÀN THÀNH PHÂN TÍCH TẤT CẢ CÁC MÃ          ")
    print("="*50)

if __name__ == "__main__":
    main()
