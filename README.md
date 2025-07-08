# LOF 基金套利分析工具

LOF 基金套利分析工具是一个 RESTful API 服务，用于分析 LOF 基金的套利机会。它通过分析 LOF 基金的溢价率、成交额等数据，筛选出潜在的套利机会。

fork 自 https://github.com/mydreamworldpolly/LOF-Fund-Tools

## 功能特点

- RESTful API 设计，提供 JSON 格式数据
- 支持频率限制（至少 30 秒调用一次）
- 数据缓存机制，减少 API 调用频率
- 完善的错误处理和日志记录
- 适合生产环境部署

## 安装

1. 克隆代码库：

```bash
git clone https://github.com/yourusername/LOF-Fund-Tools.git
cd LOF-Fund-Tools
```

2. 创建并激活虚拟环境：

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

3. 安装依赖：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

## 本地运行

```bash
python lof3.py
```

应用将在 http://localhost:5000 上运行。

- 访问 http://localhost:5000 查看 HTML 页面
- 访问 http://localhost:5000/lof 获取 JSON 格式数据

## 生产环境部署

### 使用 Gunicorn 部署（Linux/Mac）

```bash
gunicorn -w 4 -b 0.0.0.0:5001 lof3:application
```

### 使用 Docker 部署

1. 创建 Dockerfile：

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

COPY lof3.py .

ENV PORT=5000
ENV DEBUG=False

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "lof3:application"]
```

2. 构建并运行 Docker 容器：

```bash
docker build -t lof-fund-tools .
docker run -p 5000:5000 lof-fund-tools
```

## 环境变量

- `PORT`: 应用监听端口（默认：5000）
- `DEBUG`: 是否启用调试模式（默认：False）

## API 文档

### GET /lof

获取 LOF 基金套利机会列表

**响应示例**：

```json
{
  "status": "success",
  "update_time": "2024-06-15 22:30:45",
  "count": 10,
  "data": [
    {
      "基金代码": "501000",
      "基金名称": "XX LOF基金",
      "溢价率": 1.25,
      "成交额": 15000000,
      "限额": 5000000,
      "换手率": 0.85,
      "手续费": 0.15,
      "申购状态": "开放",
      "赎回状态": "开放",
      "最新价": 1.052,
      "估值": 1.039,
      "涨跌幅": 0.32,
      "基金类型": "股票型",
      "净值日期": "2024-06-14"
    }
    // 更多数据...
  ]
}
```

## 注意事项

- 该服务依赖于 akshare 库提供的数据
- 接口限制每 30 秒调用一次，以避免过于频繁的请求
- 建议在生产环境中使用反向代理（如 Nginx）进行部署

## 许可证

[MIT License](LICENSE)
