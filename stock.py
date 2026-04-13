import sys
import pandas as pd
from vnstock import Vnstock
from datetime import datetime, timedelta
import os
import time
import re
import warnings
import io
import argparse

# Đảm bảo đầu ra (stdout) luôn sử dụng UTF-8 (fix lỗi Unicode trên Windows)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Mapping cấu hình
TV_MAPPING = {
    'GOLD': ('XAUUSD', 'OANDA', 'Gold / USD (TradingView)')
}

YF_MAPPING = {
    'BTC': ('BTC-USD', 'Bitcoin / USD'),
    'ETH': ('ETH-USD', 'Ethereum / USD'),
    'BNB': ('BNB-USD', 'Binance Coin / USD'),
    'NAS100': ('NQ=F', 'Nasdaq 100 Futures'),
    'WTI': ('CL=F', 'Crude Oil WTI Futures'),
    'BRENT': ('BZ=F', 'Brent Crude Oil Futures')
}

def parse_interval(interval_str):
    """
    Phân tích chuỗi interval (ví dụ '2m', '1H', '3D') thành (giá trị, đơn vị).
    Đơn vị: m (phút), H (giờ), D (ngày), W (tuần), M (tháng).
    """
    match = re.match(r"(\d+)([mHdwWDM])", interval_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        # Chuẩn hóa: h -> H, d -> D, w -> W
        if unit == 'h': unit = 'H'
        if unit == 'd': unit = 'D'
        if unit == 'w': unit = 'W'
        return value, unit
    return 1, 'D'

def resample_data(df, target_interval):
    """
    Resample dataframe sang khung thời gian đích.
    """
    if df.empty: return df
    
    value, unit = parse_interval(target_interval)
    pd_unit = unit
    if unit == 'm': pd_unit = 'min'
    elif unit == 'M': pd_unit = 'ME'
    
    rule = f"{value}{pd_unit}"
    
    df['time'] = pd.to_datetime(df['time'])
    df = df.set_index('time').sort_index()
    
    ohlc_dict = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    
    for col in df.columns:
        if col not in ohlc_dict:
            ohlc_dict[col] = 'last'
            
    resampled = df.resample(rule, label='left', closed='left').agg(ohlc_dict)
    resampled = resampled.dropna(subset=['close'])
    resampled = resampled.reset_index()
    return resampled

def print_header(sym, full_name, interval):
    print(f"\n" + "="*50)
    print(f"      PHÂN TÍCH MÃ: {sym} ({full_name}) ")
    if interval:
        print(f"      Khung thời gian: {interval}")
    print("="*50)

def format_and_display_data(df_hist, sym, limit, unit, us_only=False):
    if df_hist is None or df_hist.empty:
        print(f"Không tìm thấy dữ liệu cho mã {sym}.")
        return

    df_hist = df_hist.reset_index()
    
    # Chuẩn hóa tên cột thời gian
    if 'datetime' in df_hist.columns:
        df_hist.rename(columns={'datetime': 'time'}, inplace=True)
    elif 'Date' in df_hist.columns:
        df_hist.rename(columns={'Date': 'time'}, inplace=True)
    elif 'Datetime' in df_hist.columns:
        df_hist.rename(columns={'Datetime': 'time'}, inplace=True)
        
    df_hist['time'] = pd.to_datetime(df_hist['time'])
    
    # Đảm bảo dữ liệu được sắp xếp và không bị trùng lặp thời gian
    df_hist = df_hist.sort_values('time').drop_duplicates('time', keep='last')
    
    # Tính toán giờ Việt Nam (UTC+7)
    if df_hist['time'].dt.tz is not None:
        df_hist['time_vn'] = df_hist['time'].dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)
    else:
        df_hist['time_vn'] = df_hist['time']
        
    # Lọc phiên Mỹ nếu có yêu cầu (20:00 tới 03:00 sáng hôm sau giờ VN)
    if us_only:
        df_hist = df_hist[df_hist['time_vn'].dt.hour.isin([20, 21, 22, 23, 0, 1, 2, 3])]
    
    df_hist['change'] = df_hist['close'].diff().fillna(0.0)
    df_hist['pct_change'] = (df_hist['close'].pct_change() * 100).fillna(0.0)
    
    if unit in ['m', 'H']:
        fmt = '%Y-%m-%d %H:%M:%S'
    else:
        fmt = '%Y-%m-%d'
        
    pd.options.display.float_format = '{:,.2f}'.format
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    
    print(f"\n--- [ LỊCH SỬ GIÁ {sym} {'(Phiên Mỹ)' if us_only else ''} ] ---")
    
    # Chuẩn bị DataFrame hiển thị
    show_df = df_hist.tail(limit).copy()
    show_df['time'] = show_df['time_vn'].dt.strftime(fmt)
    
    cols_to_show = ['time', 'symbol', 'open', 'high', 'low', 'close', 'change', 'pct_change', 'volume']
    cols_available = [c for c in cols_to_show if c in show_df.columns]
    
    print(show_df[cols_available].reset_index(drop=True))

def analyze_tv(sym, tv_config, interval, limit, value, unit):
    tv_sym, tv_exc, full_name = tv_config
    from tvDatafeed import TvDatafeed, Interval
    warnings.filterwarnings('ignore')
    
    print_header(sym, full_name, interval)
    
    try:
        tv = TvDatafeed()
        
        # Mapping interval
        tv_interval = Interval.in_daily
        if unit == 'm':
            if value <= 1: tv_interval = Interval.in_1_minute
            elif value <= 3: tv_interval = Interval.in_3_minute
            elif value <= 5: tv_interval = Interval.in_5_minute
            elif value <= 15: tv_interval = Interval.in_15_minute
            elif value <= 30: tv_interval = Interval.in_30_minute
            elif value <= 45: tv_interval = Interval.in_45_minute
            else: tv_interval = Interval.in_1_hour
        elif unit == 'H':
            if value == 1: tv_interval = Interval.in_1_hour
            elif value == 2: tv_interval = Interval.in_2_hour
            elif value <= 4: tv_interval = Interval.in_4_hour
            else: tv_interval = Interval.in_daily
        elif unit == 'D': tv_interval = Interval.in_daily
        elif unit == 'W': tv_interval = Interval.in_weekly
        elif unit == 'M': tv_interval = Interval.in_monthly
        
        df_hist = None
        for attempt in range(3):
            try:
                df_hist = tv.get_hist(symbol=tv_sym, exchange=tv_exc, interval=tv_interval, n_bars=limit + 5)
                if df_hist is not None and not df_hist.empty:
                    break
            except Exception:
                pass
            time.sleep(1.5)
            
        format_and_display_data(df_hist, sym, limit, unit, us_only=us_only)
    except Exception as e:
        print(f"Lỗi truy xuất TradingView cho {sym}: {e}")

def analyze_yf(sym, yf_config, interval, limit, value, unit, us_only=False):
    yf_sym, full_name = yf_config
    import yfinance as yf
    
    print_header(sym, full_name, interval)
    
    try:
        yf_interval_match = '1d'
        if unit == 'm':
            if value in [1, 2, 5, 15, 30, 60, 90]: yf_interval_match = f"{value}m"
            else: yf_interval_match = "1m"
        elif unit == 'H':
            yf_interval_match = "1h"
        elif unit == 'D':
            if value == 5: yf_interval_match = "5d"
            else: yf_interval_match = "1d"
        elif unit == 'W':
            yf_interval_match = "1wk"
        elif unit == 'M':
            if value == 3: yf_interval_match = "3mo"
            else: yf_interval_match = "1mo"
        
        days_buffer = limit * 2
        if unit == 'm': days_buffer = max(limit // 390 + 2, 7)
        elif unit == 'H': days_buffer = max(limit // 7 + 5, 30)
        elif unit == 'W': days_buffer = limit * 10
        elif unit == 'M': days_buffer = limit * 45
        
        period_str = f"{days_buffer}d"
        if unit in ['M', 'W'] or days_buffer > 730: period_str = "max"
        if yf_interval_match == '1m': period_str = "7d"
        
        df_hist = yf.download(tickers=yf_sym, interval=yf_interval_match, period=period_str, progress=False)
        
        if not df_hist.empty:
            df_hist = df_hist.copy() # Avoid SettingWithCopyWarning
            if isinstance(df_hist.columns, pd.MultiIndex):
                df_hist.columns = [col[0] for col in df_hist.columns]
            
            df_hist.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df_hist[numeric_cols] = df_hist[numeric_cols].apply(pd.to_numeric)
            
            df_hist = df_hist.reset_index()
            # Ensure proper time label for resample compatibility
            if 'Date' in df_hist.columns:
                df_hist.rename(columns={'Date': 'time'}, inplace=True)
            elif 'Datetime' in df_hist.columns:
                df_hist.rename(columns={'Datetime': 'time'}, inplace=True)
            
            is_native = (yf_interval_match == f"{value}{unit.lower()}" or 
                        (unit == 'H' and yf_interval_match == '1h' and value == 1) or
                        (yf_interval_match == '1d' and unit == 'D' and value == 1))
            
            if not is_native:
                df_hist = resample_data(df_hist, interval)
                
            format_and_display_data(df_hist, sym, limit, unit, us_only=us_only)
        else:
            print(f"Không tìm thấy dữ liệu API cho mã {sym}.")
    except Exception as e:
        print(f"Lỗi truy xuất API cho {sym}: {e}")

def analyze_vnstock(v, sym, limit, minimal_mode, interval, value, unit, us_only=False):
    print_header(sym, "", interval)
    
    try:
        end_date = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()
        
        vn_base = '1D'
        if unit == 'm':
            for b in ['30m', '15m', '5m', '1m']:
                bv, _ = parse_interval(b)
                if value % bv == 0:
                    vn_base = b
                    break
            else: vn_base = '1m'
        elif unit == 'H': vn_base = '1H'
        elif unit == 'D': vn_base = '1D'
        elif unit == 'W': vn_base = '1W'
        elif unit == 'M': vn_base = '1M'
        days_offset = limit * 3
        if unit == 'm':
            total_minutes = value * limit * 1.5
            days_offset = max(5, int(total_minutes / 240) + 3)
        elif unit == 'H':
            total_hours = value * limit * 1.5
            days_offset = max(7, int(total_hours / 4) + 3)
        elif unit == 'D': days_offset = value * limit * 2
        elif unit == 'W': days_offset = value * limit * 8
        elif unit == 'M': days_offset = value * limit * 45
            
        start_date = (now - timedelta(days=days_offset)).strftime('%Y-%m-%d')
        
        stock = v.stock(symbol=sym, source='KBS')
        df_hist = stock.quote.history(start=start_date, end=end_date, interval=vn_base)
        
        if not df_hist.empty:
            df_hist = df_hist.sort_values('time')
            if interval.upper() != vn_base.upper():
                df_hist = resample_data(df_hist, interval)
                
            format_and_display_data(df_hist, sym, limit, unit, us_only=us_only)
        else:
            print(f"Không tìm thấy dữ liệu lịch sử cho mã {sym} với khung {vn_base}.")
            
        if minimal_mode:
            return

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
        print(f"Lỗi truy xuất Vnstock cho {sym}: {e}")

def analyze_stock(v, sym, limit, minimal_mode, interval='1D', us_only=False):
    """
    Hàm phân tích một mã cổ phiếu cụ thể với hỗ trợ khung thời gian linh hoạt.
    Bộ điều hướng (Router) cho các loại tài sản khác nhau.
    """
    try:
        value, unit = parse_interval(interval)
        
        if sym in TV_MAPPING:
            analyze_tv(sym, TV_MAPPING[sym], interval, limit, value, unit, us_only=us_only)
        elif sym in YF_MAPPING:
            analyze_yf(sym, YF_MAPPING[sym], interval, limit, value, unit, us_only=us_only)
        else:
            analyze_vnstock(v, sym, limit, minimal_mode, interval, value, unit, us_only=us_only)
            
    except Exception as e:
        print(f"\nLỗi khởi tạo phân tích cho mã {sym}: {e}")

def screen_hose_stocks(v):
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
    parser = argparse.ArgumentParser(description="VNSTOCK & Global Market Analyzer")
    parser.add_argument("symbols", nargs="?", default="FPT", help="Danh sách mã (ví dụ: FPT,VNM hoặc BTC NAS100M)")
    parser.add_argument("limit", type=int, nargs="?", default=20, help="Số lượng phiên (mặc định: 20)")
    parser.add_argument("minimal", type=int, nargs="?", default=0, help="Chế độ rút gọn (1: Có, 0: Không)")
    parser.add_argument("interval", nargs="?", default="1D", help="Khung thời gian (1m, 1H, 1D, ...)")
    parser.add_argument("-o", "--output", help="Đường dẫn file để xuất kết quả")
    
    # Hỗ trợ lệnh SCREEN_HOSE
    args, unknown = parser.parse_known_args()
    
    if args.symbols.upper() == 'SCREEN_HOSE':
        v = Vnstock()
        screen_hose_stocks(v)
        return

    symbols_list = args.symbols.replace(',', ' ').split()
    limit = args.limit
    minimal_mode = (args.minimal == 1)
    interval = args.interval
    
    # Redirect stdout sang file nếu có tham số -o
    original_stdout = sys.stdout
    if args.output:
        f_output = open(args.output, 'w', encoding='utf-8')
        sys.stdout = f_output
             
    v = Vnstock()
    
    print("==================================================")
    print(f"      VNSTOCK 3.x MULTI-STOCK DEMO               ")
    print(f"      Danh sách: {', '.join(symbols_list)}")
    print(f"      Khung: {interval}, Số lượng: {limit}")
    print("==================================================")

    for sym in symbols_list:
        if sym:
            us_only = False
            if sym.endswith('M') and len(sym) > 1:
                sym = sym[:-1]
                us_only = True
            analyze_stock(v, sym, limit, minimal_mode, interval, us_only=us_only)

    print("\n" + "="*50)
    print("      HOÀN THÀNH PHÂN TÍCH TẤT CẢ CÁC MÃ          ")
    print("="*50)
    
    if args.output:
        sys.stdout = original_stdout
        f_output.close()
        print(f"Kết quả phân tích đã được lưu vào: {args.output}")

if __name__ == "__main__":
    main()
