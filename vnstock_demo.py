import sys
import pandas as pd
from vnstock import Vnstock
from datetime import datetime, timedelta
import os
import time
import re

def parse_interval(interval_str):
    """
    Phân tích chuỗi interval (ví dụ '2m', '1H', '3D') thành (giá trị, đơn vị).
    Đơn vị: m (phút), H (giờ), D (ngày), W (tuần), M (tháng).
    """
    match = re.match(r"(\d+)([mHdwWDM])", interval_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        # Chuẩn hóa một chút: h -> H, d -> D, w -> W
        if unit == 'h': unit = 'H'
        if unit == 'd': unit = 'D'
        if unit == 'w': unit = 'W'
        return value, unit
    return 1, 'D'

def get_binance_interval(interval_str):
    """
    Trả về interval gần nhất mà Binance hỗ trợ trực tiếp.
    Binance supports: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
    """
    value, unit = parse_interval(interval_str)
    low_unit = unit.lower()
    
    mapping = {
        'm': ['1', '3', '5', '15', '30'],
        'h': ['1', '2', '4', '6', '8', '12'],
        'd': ['1', '3'],
        'w': ['1'],
        'M': ['1']
    }
    
    if low_unit in mapping:
        supported_values = mapping[low_unit]
        # Tìm giá trị lớn nhất trong các giá trị hỗ trợ mà là ước của value
        # Nếu không thấy ước nào, lấy '1' mặc định của đơn vị đó
        best_val = '1'
        for v in supported_values:
            if value % int(v) == 0:
                best_val = v
        
        # Quay về chuỗi format của Binance
        if low_unit == 'h': return f"{best_val}h"
        if low_unit == 'd': return f"{best_val}d"
        if low_unit == 'w': return f"{best_val}w"
        if low_unit == 'M': return f"{best_val}M"
        return f"{best_val}m"
        
    return '1d'

def resample_data(df, target_interval):
    """
    Resample dataframe sang khung thời gian đích.
    target_interval ví dụ: '2m', '2H', '2D', '1W'
    """
    if df.empty: return df
    
    # Chuẩn hóa target_interval cho pandas
    # m -> min, H -> H, D -> D, W -> W, M -> ME (Month End) hoặc MS (Month Start)
    value, unit = parse_interval(target_interval)
    pd_unit = unit
    if unit == 'm': pd_unit = 'min'
    elif unit == 'M': pd_unit = 'ME'
    
    rule = f"{value}{pd_unit}"
    
    # Đảm bảo cột 'time' là datetime và làm index
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    
    # Giữ lại các cột khác nếu có
    for col in df.columns:
        if col not in ohlc_dict:
            ohlc_dict[col] = 'last'
            
    resampled = df.resample(rule, label='left', closed='left').agg(ohlc_dict)
    resampled = resampled.dropna(subset=['close']) # Loại bỏ các nến trống
    resampled = resampled.reset_index()
    return resampled

def analyze_stock(v, sym, limit, minimal_mode, interval='1D'):
    """
    Hàm phân tích một mã cổ phiếu cụ thể với hỗ trợ khung thời gian linh hoạt.
    """
    try:
        value, unit = parse_interval(interval)
        
        if sym == 'GOLD':
            import requests
            print(f"\n" + "="*50)
            print(f"      PHÂN TÍCH MÃ: {sym} (Binance Spot Gold) ")
            print(f"      Khung thời gian: {interval}")
            print("="*50)
            
            binance_base_interval = get_binance_interval(interval)
            
            # Nếu interval không được hỗ trợ trực tiếp, ta sẽ lấy limit nhiều hơn để resample
            fetch_limit = limit
            is_native = (f"{value}{unit.lower()}" == binance_base_interval) or \
                        (unit == 'H' and f"{value}h" == binance_base_interval) or \
                        (unit == 'M' and f"{value}M" == binance_base_interval)
            
            if not is_native:
                # Tính toán sơ bộ số lượng nến cần lấy để sau khi resample vẫn đủ limit
                base_val, _ = parse_interval(binance_base_interval)
                ratio = value / base_val
                fetch_limit = int(limit * ratio) + 10 # Buffer
                if fetch_limit > 1000: fetch_limit = 1000 # Max Binance limit
            
            url = f"https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval={binance_base_interval}&limit={fetch_limit}"
            
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
                    
                    # Resample if needed
                    if not is_native:
                        df_hist = resample_data(df_hist, interval)
                    
                    # Formatting time
                    if unit in ['m', 'H']:
                        df_hist['time_str'] = df_hist['time'].dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        df_hist['time_str'] = df_hist['time'].dt.strftime('%Y-%m-%d')
                        
                    df_hist['change'] = df_hist['close'].diff()
                    df_hist['pct_change'] = df_hist['close'].pct_change() * 100
                    
                    pd.options.display.float_format = '{:,.2f}'.format
                    print(f"\n--- [ LỊCH SỬ GIÁ {sym} ] ---")
                    print(df_hist.tail(limit)[['time_str', 'open', 'high', 'low', 'close', 'change', 'pct_change', 'volume']])
                else:
                    print(f"Không tìm thấy dữ liệu hoặc lỗi API cho mã {sym}.")
            except Exception as e:
                print(f"Lỗi truy xuất Binance cho {sym}: {e}")
            return

        stock = v.stock(symbol=sym, source='KBS')
        
        print(f"\n" + "="*50)
        print(f"      PHÂN TÍCH MÃ: {sym} ")
        print(f"      Khung thời gian: {interval}")
        print("="*50)

        # 3. Dữ liệu Giao dịch Lịch sử
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            now = datetime.now()
            
            # Chọn base interval để fetch từ Vnstock
            # Vnstock hỗ trợ: 1m, 5m, 15m, 30m, 1H, 1D, 1W, 1M
            supported_base = ['1m', '5m', '15m', '30m', '1H', '1D', '1W', '1M']
            
            vn_base = '1D'
            if unit == 'm':
                for b in ['30m', '15m', '5m', '1m']:
                    bv, _ = parse_interval(b)
                    if value % bv == 0:
                        vn_base = b
                        break
                else: vn_base = '1m'
            elif unit == 'H':
                vn_base = '1H'
            elif unit == 'D':
                vn_base = '1D'
            elif unit == 'W':
                vn_base = '1W'
            elif unit == 'M':
                vn_base = '1M'

            # Tính toán start_date dựa trên interval và limit
            # Cần cộng thêm buffer cho việc resample
            days_offset = 0
            if unit == 'm':
                # Giả sử 1 ngày có 240 phút giao dịch (VN Market)
                total_minutes = value * limit * 1.5 # Buffer 50%
                days_offset = max(2, int(total_minutes / 240) + 1)
            elif unit == 'H':
                # Giả sử 1 ngày có 4 tiếng giao dịch
                total_hours = value * limit * 1.5
                days_offset = max(5, int(total_hours / 4) + 1)
            elif unit == 'D':
                days_offset = value * limit * 2
            elif unit == 'W':
                days_offset = value * limit * 8
            elif unit == 'M':
                days_offset = value * limit * 45
            else:
                days_offset = limit * 3
                
            start_date = (now - timedelta(days=days_offset)).strftime('%Y-%m-%d')
            
            df_hist = stock.quote.history(start=start_date, end=end_date, interval=vn_base)
            
            if not df_hist.empty:
                df_hist = df_hist.sort_values('time')
                
                # Resample if requested interval != base interval
                if interval.upper() != vn_base.upper():
                    df_hist = resample_data(df_hist, interval)
                
                df_hist['change'] = df_hist['close'].diff()
                df_hist['pct_change'] = df_hist['close'].pct_change() * 100
                
                result = df_hist.tail(limit).copy()
                pd.options.display.float_format = '{:,.2f}'.format
                
                if unit in ['m', 'H']:
                    result['time_str'] = pd.to_datetime(result['time']).dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    result['time_str'] = pd.to_datetime(result['time']).dt.strftime('%Y-%m-%d')
                
                print(f"\n--- [ LỊCH SỬ GIÁ {sym} ] ---")
                print(result[['time_str', 'open', 'high', 'low', 'close', 'change', 'pct_change', 'volume']])
            else:
                print(f"Không tìm thấy dữ liệu lịch sử cho mã {sym} với khung {vn_base}.")
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
    Cố định khung 1D để lọc.
    """
    print("\n" + "="*50)
    print("      ĐANG LỌC CỔ PHIẾU SÀN HOSE (TARGET)       ")
    print("="*50)
    
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

    results = []
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    print(f"[2/4] Đang phân tích kỹ thuật từng mã (Khung 1D)...")
    
    count = 0
    total = len(hose_symbols)

    for sym in hose_symbols:
        count += 1
        if count % 10 == 0:
            print(f"Tiến độ: {count}/{total} mã...")

        try:
            time.sleep(3.5)
            s = v.stock(symbol=sym, source='KBS')
            df_full = s.quote.history(start=start_date, end=end_date)
            
            if df_full.empty or len(df_full) < 50:
                continue

            df = df_full.sort_values('time').copy()
            df['sma20'] = df['close'].rolling(window=20).mean()
            df['sma50'] = df['close'].rolling(window=50).mean()
            df['vami20'] = df['volume'].rolling(window=20).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            if not (latest['vami20'] > 100000 and latest['close'] > 5.0): continue
            if not (latest['close'] > latest['sma20'] and latest['close'] > latest['sma50']): continue

            last_20 = df.tail(20)
            range_pct = (last_20['high'].max() - last_20['low'].min()) / last_20['low'].min()
            if range_pct > 0.15: continue

            price_inc = (latest['close'] - prev['close']) / prev['close']
            if price_inc > 0.02 and latest['close'] >= (latest['high'] + latest['low']) / 2 and latest['volume'] > 1.5 * latest['vami20']:
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
            continue

    print(f"[3/4] Tìm thấy {len(results)} mã thỏa mãn điều kiện.")

    print("[4/4] Đang ghi kết quả vào file result.txt...")
    with open('result.txt', 'w', encoding='utf-8') as f:
        f.write(f"BÁO CÁO LỌC CỔ PHIẾU HOSE (TARGET) - {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
        f.write("="*70 + "\n")
        f.write(f"{'MÃ':<8} | {'GIÁ':<10} | {'TĂNG%':<10} | {'VOL/AVG20':<12} | {'BIÊN NỀN%':<10}\n")
        f.write("-"*70 + "\n")
        for r in results:
            f.write(f"{r['symbol']:<8} | {r['price']:<10.2f} | {r['pct']:<10.2f} | {r['vol_ratio']:<12.2f} | {r['range_20p']:<10.2f}\n")
        f.write("="*70 + "\n")

    print(f"XONG! Kết quả đã lưu tại 'result.txt'.")

def main():
    if len(sys.argv) > 1 and sys.argv[1].upper() == 'SCREEN_HOSE':
        v = Vnstock()
        screen_hose_stocks(v)
        return

    input_syms = sys.argv[1] if len(sys.argv) > 1 else 'FPT'
    if ',' in input_syms:
        symbols = [s.strip().upper() for s in input_syms.split(',')]
    else:
        symbols = [s.strip().upper() for s in input_syms.split()]
        
    try:
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    except:
        limit = 20
        
    minimal_mode = (sys.argv[3] == '1') if len(sys.argv) > 3 else False
    interval = sys.argv[4] if len(sys.argv) > 4 else '1D'
             
    v = Vnstock()
    
    print("==================================================")
    print(f"      VNSTOCK 3.x MULTI-STOCK DEMO               ")
    print(f"      Danh sách: {', '.join(symbols)}")
    print(f"      Khung: {interval}, Số lượng: {limit}")
    print("==================================================")

    for sym in symbols:
        if sym:
            analyze_stock(v, sym, limit, minimal_mode, interval)

    print("\n" + "="*50)
    print("      HOÀN THÀNH PHÂN TÍCH TẤT CẢ CÁC MÃ          ")
    print("="*50)

if __name__ == "__main__":
    main()

