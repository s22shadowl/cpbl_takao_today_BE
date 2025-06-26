# run_scraper.py

import argparse
import datetime
from app import scraper

def main(argv=None):
    """
    主執行函式，負責解析命令列參數並呼叫對應的爬蟲任務。
    """
    # 建立一個 ArgumentParser 物件，用於處理命令列參數
    parser = argparse.ArgumentParser(description="CPBL 數據爬蟲手動執行工具")
    # 建立子命令解析器，用於處理不同的執行模式
    subparsers = parser.add_subparsers(dest='mode', help='執行模式 (daily, monthly, yearly)', required=True)

    # --- 'daily' 子命令 ---
    parser_daily = subparsers.add_parser('daily', help='抓取指定單日的數據 (預設為今天)')
    parser_daily.add_argument('date', nargs='?', default=None, help="可選，指定日期，格式為YYYY-MM-DD")

    # --- 'monthly' 子命令 ---
    parser_monthly = subparsers.add_parser('monthly', help='抓取指定月份的所有數據 (預設為本月)')
    parser_monthly.add_argument('month', nargs='?', default=None, help="可選，指定月份，格式為YYYY-MM")
    
    # --- 'yearly' 子命令 ---
    parser_yearly = subparsers.add_parser('yearly', help='抓取指定年份的所有數據 (預設為本年)')
    parser_yearly.add_argument('year', nargs='?', default=None, help="可選，指定年份，格式為YYYY")
    
    # 解析傳入的命令列參數 (如果沒有提供，則使用 sys.argv)
    args = parser.parse_args(argv)

    # 根據解析出的模式，呼叫 app.scraper 中對應的功能函式
    if args.mode == 'daily':
        if args.date:
            try:
                # 驗證日期格式
                datetime.datetime.strptime(args.date, "%Y-%m-%d")
                scraper.scrape_single_day(specific_date=args.date)
            except ValueError:
                print("\n錯誤：日期格式不正確。請使用YYYY-MM-DD 格式。\n")
        else:
            scraper.scrape_single_day()
            
    elif args.mode == 'monthly':
        if args.month:
            try:
                # 驗證月份格式
                datetime.datetime.strptime(args.month, "%Y-%m")
                scraper.scrape_entire_month(month_str=args.month)
            except ValueError:
                print("\n錯誤：月份格式不正確。請使用YYYY-MM 格式。\n")
        else:
            scraper.scrape_entire_month()
            
    elif args.mode == 'yearly':
        if args.year:
            try:
                # 驗證年份格式
                if not (args.year.isdigit() and len(args.year) == 4): raise ValueError
                scraper.scrape_entire_year(year_str=args.year)
            except ValueError:
                print("\n錯誤：年份格式不正確。請使用YYYY 格式（例如：2025）。\n")
        else:
            scraper.scrape_entire_year()

if __name__ == '__main__':
    # 當直接執行此檔案時，呼叫 main() 函式
    main()