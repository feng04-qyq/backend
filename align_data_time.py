"""
数据时间对齐工具
将所有币种的数据对齐到指定的起始时间
用于公平比较不同币种的历史表现
"""

import pandas as pd
import os
import json
from datetime import datetime

def align_data_to_time(input_file, output_file, start_time, report_list):
    """
    将单个文件的数据对齐到指定起始时间
    
    参数:
        input_file: 输入文件路径
        output_file: 输出文件路径
        start_time: 起始时间（datetime对象）
        report_list: 报告列表
    """
    filename = os.path.basename(input_file)
    print(f"\n处理: {filename}")
    
    try:
        # 读取数据
        df = pd.read_csv(input_file, encoding='utf-8')
        
        # 查找时间列
        time_col = None
        for col in df.columns:
            if col in ['开盘时间', 'open_time', 'Unnamed: 0']:
                time_col = col
                break
        
        if time_col is None:
            print(f"  ✗ 未找到时间列")
            return None
        
        # 转换时间列
        df[time_col] = pd.to_datetime(df[time_col])
        
        original_rows = len(df)
        original_start = df[time_col].min()
        original_end = df[time_col].max()
        
        print(f"  原始数据: {original_rows} 行")
        print(f"  原始时间范围: {original_start} 至 {original_end}")
        
        # 过滤数据，只保留起始时间之后的数据
        df_aligned = df[df[time_col] >= start_time].copy()
        
        aligned_rows = len(df_aligned)
        removed_rows = original_rows - aligned_rows
        
        if aligned_rows == 0:
            print(f"  ✗ 警告: 所有数据都在指定起始时间之前！")
            return None
        
        aligned_start = df_aligned[time_col].min()
        aligned_end = df_aligned[time_col].max()
        
        print(f"  对齐后数据: {aligned_rows} 行")
        print(f"  对齐后时间范围: {aligned_start} 至 {aligned_end}")
        print(f"  删除: {removed_rows} 行 ({removed_rows/original_rows*100:.2f}%)")
        
        # 保存对齐后的数据
        df_aligned.to_csv(output_file, encoding='utf-8', index=False)
        print(f"  ✓ 已保存到: {output_file}")
        
        # 记录报告
        report_list.append({
            'file': filename,
            'original_rows': int(original_rows),
            'aligned_rows': int(aligned_rows),
            'removed_rows': int(removed_rows),
            'removal_percentage': float(removed_rows/original_rows*100),
            'original_start': str(original_start),
            'original_end': str(original_end),
            'aligned_start': str(aligned_start),
            'aligned_end': str(aligned_end),
            'status': 'success'
        })
        
        return df_aligned
        
    except Exception as e:
        print(f"  ✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        
        report_list.append({
            'file': filename,
            'status': f'failed: {str(e)}'
        })
        
        return None


def main():
    """主函数"""
    print("="*70)
    print("数据时间对齐工具")
    print("="*70)
    
    # 默认起始时间：SOL上市时间
    default_start_time = "2020-09-14 15:00:00"
    
    print(f"\n默认起始时间: {default_start_time}")
    print("(SOL在Binance的上市时间)")
    
    custom_time = input("\n输入自定义起始时间（格式: YYYY-MM-DD HH:MM:SS，直接回车使用默认）: ").strip()
    
    if custom_time:
        try:
            start_time = pd.to_datetime(custom_time)
            print(f"使用自定义时间: {start_time}")
        except:
            print("时间格式错误，使用默认时间")
            start_time = pd.to_datetime(default_start_time)
    else:
        start_time = pd.to_datetime(default_start_time)
        print(f"使用默认时间: {start_time}")
    
    # 检查可用的数据源
    sources = {
        '1': ('klines_data_cleaned', 'klines_data_aligned', '清洗后的数据'),
        '2': ('klines_data_with_indicators_from_cleaned', 'klines_data_with_indicators_aligned', '带指标的清洗数据'),
        '3': ('klines_data', 'klines_data_aligned_raw', '原始数据'),
        '4': ('klines_data_with_indicators', 'klines_data_with_indicators_aligned_raw', '带指标的原始数据')
    }
    
    available_sources = []
    print("\n可用的数据源:")
    for key, (input_dir, _, desc) in sources.items():
        if os.path.exists(input_dir):
            csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv') and 'PERPETUAL' in f]
            if csv_files:
                available_sources.append(key)
                print(f"  {key}. {desc} ({input_dir}/) - {len(csv_files)} 个文件")
    
    if not available_sources:
        print("\n错误: 未找到可用的数据源")
        return
    
    choice = input(f"\n请选择数据源 ({'/'.join(available_sources)}，直接回车选择1): ").strip()
    
    if not choice:
        choice = '1'
    
    if choice not in available_sources:
        print("无效的选择")
        return
    
    input_dir, output_dir, desc = sources[choice]
    
    print(f"\n选择的数据源: {desc}")
    print(f"输入目录: {input_dir}/")
    print(f"输出目录: {output_dir}/")
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 查找所有CSV文件
    csv_files = [f for f in os.listdir(input_dir) if f.endswith('.csv') and 'PERPETUAL' in f]
    
    if not csv_files:
        print(f"\n错误: {input_dir}/ 中没有找到数据文件")
        return
    
    print(f"\n找到 {len(csv_files)} 个文件")
    
    confirm = input("\n确认开始对齐数据？(y/n，直接回车确认): ").strip().lower()
    if confirm and confirm != 'y':
        print("取消操作")
        return
    
    print("\n开始处理...")
    print("="*70)
    
    report_list = []
    success_count = 0
    
    for i, csv_file in enumerate(csv_files, 1):
        print(f"\n[{i}/{len(csv_files)}]")
        input_path = os.path.join(input_dir, csv_file)
        output_path = os.path.join(output_dir, csv_file)
        
        result = align_data_to_time(input_path, output_path, start_time, report_list)
        if result is not None:
            success_count += 1
    
    # 保存报告
    report = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'alignment_start_time': str(start_time),
        'input_directory': input_dir,
        'output_directory': output_dir,
        'total_files': len(csv_files),
        'successful': success_count,
        'failed': len(csv_files) - success_count,
        'files': report_list
    }
    
    report_file = os.path.join(output_dir, 'alignment_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 显示汇总
    print("\n" + "="*70)
    print("对齐完成！")
    print("="*70)
    print(f"对齐起始时间: {start_time}")
    print(f"成功: {success_count}/{len(csv_files)}")
    print(f"输出目录: {output_dir}/")
    print(f"报告文件: {report_file}")
    
    # 显示统计
    if report_list:
        successful_reports = [r for r in report_list if r['status'] == 'success']
        if successful_reports:
            total_removed = sum(r['removed_rows'] for r in successful_reports)
            total_original = sum(r['original_rows'] for r in successful_reports)
            avg_removal = total_removed / total_original * 100
            
            print(f"\n总体统计:")
            print(f"  总删除行数: {total_removed:,}")
            print(f"  总原始行数: {total_original:,}")
            print(f"  平均删除比例: {avg_removal:.2f}%")
            
            print(f"\n各文件删除情况:")
            for r in successful_reports:
                symbol = r['file'].split('_')[0]
                print(f"  {symbol}: 删除 {r['removed_rows']:,} 行 ({r['removal_percentage']:.2f}%)")
    
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

