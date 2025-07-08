# -*- coding: utf-8 -*-
"""
LOF基金套利分析工具 - RESTful API版本

提供LOF基金套利机会的RESTful API服务
支持访问频率限制（至少30秒调用一次）
适合生产环境部署

"""

import akshare as ak
import pandas as pd
import numpy as np
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string
from flask.logging import default_handler
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        TimedRotatingFileHandler('lof_api.log', when='midnight', interval=1, backupCount=7)
    ]
)

logger = logging.getLogger(__name__)

# 缓存数据和上次更新时间
fund_data_cache = None
last_update_time = 0
CACHE_EXPIRY = 30  # 缓存有效期（秒）

def fetch_fund_data():
    """获取并处理来自Akshare的数据"""
    logger.info("开始获取基金数据")

    def fetch_lof_spot():
        return ak.fund_lof_spot_em()

    def fetch_value_estimation():
        return ak.fund_value_estimation_em()

    def fetch_purchase_info():
        return ak.fund_purchase_em().drop(columns=["序号", "基金简称"])

    try:
        with ThreadPoolExecutor() as executor:
            lof_future = executor.submit(fetch_lof_spot)
            value_estimation_future = executor.submit(fetch_value_estimation)
            purchase_info_future = executor.submit(fetch_purchase_info)

            fund_lof_spot_df = lof_future.result()
            fund_value_estimation_df = value_estimation_future.result()
            fund_purchase_df = purchase_info_future.result()

        fund_lof_spot_df = fund_lof_spot_df.reset_index()[['代码', '最新价', '成交额', '涨跌幅', '换手率']]
        lof_list = fund_lof_spot_df["代码"].values

        fund_value_estimation_df = fund_value_estimation_df[fund_value_estimation_df['基金代码'].isin(lof_list)]
        fund_value_estimation_df = fund_value_estimation_df.drop(fund_value_estimation_df.columns[[0, 4, 5, 6, 7, 8]], axis=1)
        fund_value_estimation_df = fund_value_estimation_df.rename(columns={fund_value_estimation_df.columns[2]: '估值'})

        result_df = pd.merge(fund_value_estimation_df, fund_lof_spot_df, left_on='基金代码', right_on='代码', how='left')
        result_df = result_df.drop(columns=['代码'])
        result_df = pd.merge(result_df, fund_purchase_df, on='基金代码', how='left')

        logger.info("基金数据获取成功")
        return result_df
    except Exception as e:
        logger.error(f"获取基金数据失败: {str(e)}")
        raise

def preprocess_data(df):
    """预处理获取的数据"""
    logger.info("开始预处理数据")

    try:
        df = df.replace('---', np.nan)
        df['估值'] = df['估值'].astype(float)
        df['最新价'] = df['最新价'].astype(float)
        df['成交额'] = df['成交额'].fillna(0).astype(int)
        df['涨跌幅'] = df['涨跌幅'].astype(float)
        df['换手率'] = df['换手率'].astype(float)
        df['最新净值'] = df['最新净值/万份收益'].astype(float)
        df['购买起点'] = df['购买起点'].astype(int)
        df['日累计限定金额'] = df['日累计限定金额'].astype('int64')
        df['手续费'] = df['手续费'].astype(float)

        logger.info("数据预处理完成")
        return df
    except Exception as e:
        logger.error(f"数据预处理失败: {str(e)}")
        raise

def calculate_premium_rate(df):
    """计算基金溢价率"""
    logger.info("开始计算溢价率")

    try:
        # 计算基金溢价率。尽量用最新估值计算，如无法估值则用最新净值（QDII）
        def calc_rate(row):
            if pd.notnull(row['估值']):
                return row['最新价'] / row['估值'] - 1
            else:
                return row['最新价'] / row['最新净值'] - 1

        df['溢价率'] = df.apply(calc_rate, axis=1) * 100
        df['溢价率'] = df['溢价率'].round(2)
        df['溢价率abs'] = abs(df['溢价率'])

        logger.info("溢价率计算完成")
        return df
    except Exception as e:
        logger.error(f"溢价率计算失败: {str(e)}")
        raise

def filter_funds(df):
    """根据交易量和溢价率标准筛选基金"""
    logger.info("开始筛选基金")

    try:
        # 筛选成交额较高、折价或溢价明显、有潜在套利机会的基金
        df = df[df["成交额"] >= 5000000]
        df = df[((df["溢价率"] >= 0.8) & (df["申购状态"] != "暂停申购")) |
                ((df["溢价率"] <= -0.6) & (df["赎回状态"] != "暂停赎回"))]

        logger.info(f"基金筛选完成，符合条件的基金数量: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"基金筛选失败: {str(e)}")
        raise

def format_dataframe(df):
    """格式化数据框列和顺序"""
    logger.info("开始格式化数据")

    try:
        df = df.sort_values(by='溢价率abs', ascending=False)
        new_column_order = [
            '基金代码', '基金名称', '溢价率', '成交额', '日累计限定金额', '换手率',
            '手续费', '申购状态', '赎回状态', '最新价', '最新净值/万份收益', '估值',
            '购买起点', '涨跌幅', '基金类型', '最新净值/万份收益-报告时间',
            '最新净值', '下一开放日', '溢价率abs'
        ]
        df = df.reindex(columns=new_column_order)
        df = df.drop(columns=['购买起点', '下一开放日', '溢价率abs', '最新净值/万份收益'])
        df = df.rename(columns={'最新净值/万份收益-报告时间': '净值日期', '日累计限定金额': '限额'})

        logger.info("数据格式化完成")
        return df
    except Exception as e:
        logger.error(f"数据格式化失败: {str(e)}")
        raise

def get_fund_data():
    """获取基金数据，使用缓存机制减少API调用频率"""
    global fund_data_cache, last_update_time

    current_time = time.time()
    if fund_data_cache is None or (current_time - last_update_time) > CACHE_EXPIRY:
        logger.info(f"缓存过期或不存在，更新数据 (距上次更新: {current_time - last_update_time:.2f}秒)")
        try:
            result_df = fetch_fund_data()
            result_df = preprocess_data(result_df)
            result_df = calculate_premium_rate(result_df)
            result_df = filter_funds(result_df)
            result_df = format_dataframe(result_df)

            # 更新缓存和时间戳
            fund_data_cache = result_df
            last_update_time = current_time

            logger.info("数据更新完成，已缓存")
        except Exception as e:
            logger.error(f"更新数据失败: {str(e)}")
            if fund_data_cache is None:
                # 如果没有缓存数据可用，则抛出异常
                raise
            logger.info("使用旧的缓存数据")
    else:
        time_diff = current_time - last_update_time
        logger.info(f"使用缓存数据 (缓存剩余有效期: {CACHE_EXPIRY - time_diff:.2f}秒)")

    return fund_data_cache

def rate_limit(f):
    """装饰器：限制API访问频率"""
    last_calls = {}

    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()

        if client_ip in last_calls:
            time_diff = current_time - last_calls[client_ip]

            if time_diff < CACHE_EXPIRY:
                wait_time = CACHE_EXPIRY - time_diff
                logger.warning(f"客户端 {client_ip} 请求过于频繁，距离上次请求仅 {time_diff:.2f} 秒")
                return jsonify({
                    "error": "请求过于频繁",
                    "message": f"请等待 {wait_time:.2f} 秒后再试",
                    "next_available": last_calls[client_ip] + CACHE_EXPIRY
                }), 429

        # 更新最后调用时间
        last_calls[client_ip] = current_time
        return f(*args, **kwargs)

    return decorated_function

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)

    @app.route('/lof', methods=['GET'])
    @rate_limit
    def lof_api():
        """LOF基金套利机会API端点"""
        try:
            df = get_fund_data()
            result = df.to_dict(orient='records')

            return jsonify({
                "status": "success",
                "update_time": datetime.fromtimestamp(last_update_time).strftime('%Y-%m-%d %H:%M:%S'),
                "count": len(result),
                "data": result
            })
        except Exception as e:
            logger.error(f"API请求处理失败: {str(e)}")
            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    @app.route('/', methods=['GET'])
    def home():
        """首页 - 提供简单的API文档和HTML视图"""
        try:
            df = get_fund_data()

            return render_template_string(
                """
                <!doctype html>
                <html lang="zh-cn">
                  <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
                    <title>LOF套利分析工具</title>
                    <style>
                      body { font-family: Arial, sans-serif; margin: 0; padding: 20px; line-height: 1.6; }
                      h1, h2 { color: #333; }
                      table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                      th { background-color: #f2f2f2; }
                      tr:nth-child(even) { background-color: #f9f9f9; }
                      code { background: #f5f5f5; padding: 2px 5px; border-radius: 3px; }
                      .api-section { margin-bottom: 30px; padding: 15px; background: #f8f8f8; border-radius: 5px; }
                    </style>
                  </head>
                  <body>
                    <h1>LOF套利分析工具 API</h1>
                    <div class="api-section">
                      <h2>API 文档</h2>
                      <p>访问 <code>/lof</code> 端点获取 JSON 格式的数据</p>
                      <p>请求频率限制: 每 {{ cache_expiry }} 秒一次</p>
                      <p>示例: <a href="/lof">/lof</a></p>
                    </div>

                    <h2>数据预览</h2>
                    <p>上次更新时间: {{ update_time }}</p>
                    <table>
                      <thead>
                        <tr>
                          {% for col in df.columns %}
                          <th>{{ col }}</th>
                          {% endfor %}
                        </tr>
                      </thead>
                      <tbody>
                        {% for row in df.iterrows() %}
                        <tr>
                          {% for cell in row[1] %}
                          <td>{{ cell }}</td>
                          {% endfor %}
                        </tr>
                        {% endfor %}
                      </tbody>
                    </table>
                  </body>
                </html>
                """,
                df=df,
                cache_expiry=CACHE_EXPIRY,
                update_time=datetime.fromtimestamp(last_update_time).strftime('%Y-%m-%d %H:%M:%S')
            )
        except Exception as e:
            logger.error(f"首页渲染失败: {str(e)}")
            return jsonify({
                "status": "error",
                "message": "服务暂时不可用，请稍后再试"
            }), 500

    return app

def main():
    """主函数 - 创建并运行Flask应用"""
    # 生产环境配置
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("DEBUG", "False").lower() in ('true', '1', 't')

    # 预热缓存
    try:
        get_fund_data()
    except Exception as e:
        logger.error(f"预热缓存失败: {str(e)}")

    # 创建并运行应用
    app = create_app()

    if __name__ == '__main__':
        logger.info(f"启动服务，端口: {port}, 调试模式: {debug}")
        app.run(host='0.0.0.0', port=port, debug=debug)
    else:
        # 生产环境下使用 gunicorn 或 uwsgi 运行时会用到
        logger.info("应用已创建，等待WSGI服务器启动")

    return app

# 运行主函数
application = main()
